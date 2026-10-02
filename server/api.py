"""REST API for the simulator and the private link flow, plus the MCP mount at /mcp."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlmodel import Session

from . import config
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


# Streamable HTTP MCP endpoint at /mcp (mounted last so the routes above win).
app.mount("/", mcp.streamable_http_app())
