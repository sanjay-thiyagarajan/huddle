"""REST API for the simulator and the private link flow, plus the MCP mount at /mcp."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlmodel import Session

from . import config
from .agent import huddle_agent
from .db import get_session, init_db
from .engine import rounds
from .mcp_server import mcp


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
    return huddle_agent.parse_utterance(mode, body.text)


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
