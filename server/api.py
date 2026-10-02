"""REST API for the simulator and the private link flow, plus the MCP mount at /mcp."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from . import config
from .agent import huddle_agent
from .db import VoiceProfile, get_session, init_db
from .engine import rounds
from .mcp_server import mcp
from .voice import speaker_id, stt


def _session():
    with get_session() as s:
        yield s


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Huddle", lifespan=lifespan)


@app.exception_handler(rounds.HuddleError)
async def _huddle_error(_: Request, e: rounds.HuddleError):
    return JSONResponse({"error": e.code, "message": e.message}, status_code=e.status)


class ParticipantIn(BaseModel):
    name: str
    channel: str = "voice"


class RoundIn(BaseModel):
    mode: str
    participants: list[ParticipantIn]
    deadline_seconds: int = 3600
    need: dict | None = None


class AnswerIn(BaseModel):
    token: str
    answer: dict


@app.get("/api/health")
def health():
    return {"ok": True, "mode": config.MODE}


@app.post("/api/rounds")
def create_round(body: RoundIn, s: Session = Depends(_session)):
    return rounds.create_round(s, body.mode, [p.model_dump() for p in body.participants],
                               body.deadline_seconds, body.need)


@app.get("/api/status")
def status(token: str, s: Session = Depends(_session)):
    return rounds.status(s, token)


@app.post("/api/answers")
def submit(body: AnswerIn, s: Session = Depends(_session)):
    return rounds.submit_answer(s, body.token, body.answer)


@app.get("/me/answers")
def me_answers(token: str, s: Session = Depends(_session)):
    return rounds.my_answers(s, token)


@app.get("/api/result")
def result(token: str, s: Session = Depends(_session)):
    return rounds.get_result(s, token)


@app.post("/api/close")
def close(token: str, s: Session = Depends(_session)):
    return rounds.close_round(s, token)


@app.post("/api/nudge")
def nudge(token: str, s: Session = Depends(_session)):
    return rounds.nudge_pending(s, token)


@app.get("/api/server-holds")
def holds(token: str, s: Session = Depends(_session)):
    return rounds.server_holds(s, token)


class ToolIn(BaseModel):
    name: str
    arguments: dict = {}


class ParseIn(BaseModel):
    token: str
    text: str = Field(max_length=1000)


@app.post("/api/agent/tool")
async def agent_tool(body: ToolIn):
    """The simulator's agent calls Huddle's MCP server over HTTP (Streamable HTTP) here."""
    if body.name not in huddle_agent.TOOLS:
        raise rounds.HuddleError("bad_tool", f"Unknown tool {body.name}.")
    return await huddle_agent.call_tool(body.name, body.arguments)


@app.post("/api/agent/parse")
def agent_parse(body: ParseIn, s: Session = Depends(_session)):
    """Turn one person's words into a draft answer. Nothing is stored until they confirm."""
    mode = rounds.status(s, body.token)["mode"]
    return huddle_agent.parse_with_engine(mode, body.text)


@app.get("/api/agent/explain")
def agent_explain(token: str, s: Session = Depends(_session)):
    """Plain-language explanation of the closed round's aggregate result (agent sees no raw answers)."""
    out = rounds.get_result(s, token)
    if not out["ready"]:
        raise rounds.HuddleError("not_ready", "The round is still open.", 409)
    return huddle_agent.explain(out["result"])


# ---- voice: speaker ID is a stand-in for Alexa person recognition, not security ----------------

MAX_AUDIO = 5_000_000


async def _audio(request: Request) -> bytes:
    data = await request.body()
    if not data or len(data) > MAX_AUDIO:
        raise rounds.HuddleError("bad_audio", "Send one WAV recording under 5 MB.")
    return data


def _voice(fn, *args):
    try:
        return fn(*args)
    except speaker_id.VoiceUnavailable as e:
        raise rounds.HuddleError("voice_unavailable", f"{e} The profile switcher still works.", 501) from None
    except ValueError as e:
        raise rounds.HuddleError("bad_audio", str(e)) from None


@app.post("/api/voice/enrol")
async def voice_enrol(name: str, request: Request, s: Session = Depends(_session)):
    """Add one enrolment clip (WAV) to a profile. Only the embedding is kept, not the audio."""
    vec = _voice(speaker_id.embed, await _audio(request))
    prof = s.get(VoiceProfile, name) or VoiceProfile(name=name, embeddings=[])
    prof.embeddings = [*prof.embeddings, vec.tolist()]
    s.add(prof)
    s.commit()
    return {"name": name, "clips": len(prof.embeddings)}


@app.post("/api/voice/identify")
async def voice_identify(request: Request, s: Session = Depends(_session)):
    """Who is speaking? Returns the best profile only when it clears the threshold."""
    import numpy as np

    vec = _voice(speaker_id.embed, await _audio(request))
    profiles = {p.name: speaker_id.enrol_profile([np.array(e) for e in p.embeddings])
                for p in s.exec(select(VoiceProfile)) if p.embeddings}
    name, score = speaker_id.identify(vec, profiles)
    return {"recognized": name is not None, "name": name, "score": round(score, 2),
            "note": "Voice ID separates profiles; it is not security."}


@app.post("/api/voice/transcribe")
async def voice_transcribe(request: Request):
    """Local Whisper fallback for browsers without the Web Speech API."""
    import tempfile

    data = await _audio(request)
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        f.write(data)
        f.flush()
        return {"text": _voice(stt.transcribe, f.name)}


@app.get("/api/voice/profiles")
def voice_profiles(s: Session = Depends(_session)):
    return {"enrolled": sorted(p.name for p in s.exec(select(VoiceProfile)))}


@app.delete("/api/voice/profiles/{name}")
def voice_forget(name: str, s: Session = Depends(_session)):
    prof = s.get(VoiceProfile, name)
    if prof:
        s.delete(prof)
        s.commit()
    return {"forgotten": name}


# Built simulator (web/dist), when present. In dev, Vite serves it and proxies /api and /mcp here.
_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if (_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    @app.get("/r/{token}", include_in_schema=False)
    def spa(token: str | None = None):
        return FileResponse(_DIST / "index.html")


# Streamable HTTP MCP endpoint at /mcp (mounted last so the routes above win).
app.mount("/", mcp.streamable_http_app())
