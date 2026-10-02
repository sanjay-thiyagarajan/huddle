"""REST API for the simulator and the private link flow, plus the MCP mount at /mcp."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from . import config
from .agent import dialogue, huddle_agent
from .db import VoiceProfile, get_session, init_db
from .engine import rounds
from .mcp_server import mcp
from .voice import speaker_id, stt


def _session():
    with get_session() as s:
        yield s


log = logging.getLogger("huddle.scheduler")


def _run_tick() -> int:
    with get_session() as s:
        return len(rounds.tick(s))


async def _scheduler():
    """Real reminders: every few seconds, send due reminders and close rounds that passed their deadline,
    whether or not anyone has a page open."""
    while True:
        await asyncio.sleep(config.TICK_SECONDS)
        try:
            await run_in_threadpool(_run_tick)
        except Exception:  # noqa: BLE001  a bad tick must never stop the scheduler
            log.exception("reminder tick failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(_scheduler())
    try:
        async with mcp.session_manager.run():
            yield
    finally:
        task.cancel()


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


class CheckinIn(BaseModel):
    token: str
    score: int


@app.post("/api/checkin")
def checkin(body: CheckinIn, s: Session = Depends(_session)):
    return rounds.submit_checkin(s, body.token, body.score)


@app.get("/api/plan-card")
def plan_card(token: str, s: Session = Depends(_session)):
    return rounds.plan_card(s, token)


@app.get("/api/household")
def household(token: str, s: Session = Depends(_session)):
    """The household's closed plans so far (aggregate only)."""
    return rounds.household_history(s, token)


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


class VoiceTurnIn(BaseModel):
    token: str
    session_id: str | None = None
    utterance: str = Field(default="", max_length=500)


@app.post("/api/agent/turn")
async def agent_turn(body: VoiceTurnIn, s: Session = Depends(_session)):
    """One turn of the voice-only conversation. The reply is what the assistant SAYS: it never contains
    the person's private values (unless they ask for a read-back). The draft stays server-side and is
    saved through the MCP tool, so a screen showing this reply cannot reveal an answer."""
    info = rounds.status(s, body.token)
    if info["state"] == "closed":
        raise rounds.HuddleError("round_closed", "This round is closed.", 409)
    try:
        if body.session_id is None:
            sid, turn = dialogue.open_session(body.token, info["mode"], info["me"]["name"],
                                              huddle_agent.parse_with_engine)
        else:
            sid = body.session_id
            turn = await run_in_threadpool(dialogue.take_turn, sid, body.token, body.utterance)
    except dialogue.DialogueError as e:
        raise rounds.HuddleError("voice_session", str(e), 410) from None
    saved = False
    if turn.submit is not None:
        out = await huddle_agent.call_tool("submit_private_answer",
                                           {"token": body.token, "answer": turn.submit})
        saved = "error" not in out
        if not saved:
            turn = dialogue.Turn("Sorry, I couldn't save that. Let's use the screen instead.", "handoff",
                                 done=True, handoff="screen")
    return {"session_id": sid, "say": turn.say, "stage": turn.stage, "done": turn.done,
            "handoff": turn.handoff, "spoke_values": turn.spoke_values, "saved": saved}


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
