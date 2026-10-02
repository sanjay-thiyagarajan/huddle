"""SQLite persistence (SQLModel). Private answers live only in the `answer` table."""

from pydantic import NaiveDatetime
from sqlalchemy import JSON, Column
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine

from . import config

_engine = None


class Round(SQLModel, table=True):
    id: str = Field(primary_key=True)
    mode: str
    state: str = "collecting"  # collecting -> reminded -> closed
    created_at: NaiveDatetime
    reminder_at: NaiveDatetime
    deadline_at: NaiveDatetime
    need: dict = Field(default_factory=dict, sa_column=Column(JSON))
    result: dict | None = Field(default=None, sa_column=Column(JSON))
    defaults_applied: bool = False


class Participant(SQLModel, table=True):
    id: str = Field(primary_key=True)
    round_id: str = Field(index=True)
    name: str
    channel: str  # voice | link
    is_host: bool = False


class Answer(SQLModel, table=True):
    participant_id: str = Field(primary_key=True)
    round_id: str = Field(index=True)
    data: dict = Field(default_factory=dict, sa_column=Column(JSON))
    is_default: bool = False
    created_at: NaiveDatetime


def init_db(url: str | None = None):
    """(Re)create the engine. In-memory URLs share one connection so tests can reset cheaply."""
    global _engine
    url = url or config.DB_URL
    kwargs = {"connect_args": {"check_same_thread": False}}
    if ":memory:" in url or url == "sqlite://":
        kwargs["poolclass"] = StaticPool
    _engine = create_engine(url, **kwargs)
    SQLModel.metadata.create_all(_engine)
    return _engine


def get_session() -> Session:
    if _engine is None:
        init_db()
    return Session(_engine, expire_on_commit=False)
