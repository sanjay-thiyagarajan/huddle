"""Round lifecycle: open, remind, deadline, defaults, close.

Both the REST API and the MCP tools call these functions, so the privacy rules live in
one place. Raw answers leave this module only through `my_answers` (owner only).
"""
import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from sqlmodel import Session, select

from .. import config
from ..db import Answer, Participant, Round
from . import everyday, privacy

MODES = {"everyday": everyday}
CHANNELS = ("voice", "link")


class HuddleError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _mode(name: str):
    if name not in MODES:
        raise HuddleError("bad_mode", f"Unknown mode '{name}'. Use one of {sorted(MODES)}.")
    return MODES[name]


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---- tokens: signed, expiring, bound to one participant -------------------------------------

def _sign(payload: str) -> str:
    mac = hmac.new(config.SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac)[:22].decode()


def make_token(participant_id: str, expires: datetime) -> str:
    payload = f"{participant_id}.{int(expires.replace(tzinfo=UTC).timestamp())}"
    return f"{payload}.{_sign(payload)}"


def _parse_token(token: str, now: datetime) -> str:
    try:
        pid, exp, sig = token.split(".")
        ok = hmac.compare_digest(sig, _sign(f"{pid}.{exp}"))
        expired = int(exp) < int(now.replace(tzinfo=UTC).timestamp())
    except ValueError:
        raise HuddleError("bad_token", "Invalid token.", 401) from None
    if not ok:
        raise HuddleError("bad_token", "Invalid token.", 401)
    if expired:
        raise HuddleError("token_expired", "This link has expired.", 401)
    return pid


def _auth(s: Session, token: str, now: datetime) -> tuple[Participant, Round]:
    pid = _parse_token(token, now)
    p = s.get(Participant, pid)
    if p is None:
        raise HuddleError("bad_token", "Invalid token.", 401)
    return p, s.get(Round, p.round_id)


def _participants(s: Session, round_id: str) -> list[Participant]:
    return list(s.exec(select(Participant).where(Participant.round_id == round_id)))


def _answers(s: Session, round_id: str) -> dict[str, Answer]:
    return {a.participant_id: a for a in s.exec(select(Answer).where(Answer.round_id == round_id))}


# ---- lifecycle --------------------------------------------------------------------------------

def create_round(s: Session, mode: str, participants: list[dict], deadline_seconds: int = 3600,
                 need: dict | None = None, now: datetime | None = None) -> dict:
    now = now or now_utc()
    m = _mode(mode)
    if not 2 <= len(participants) <= 6:
        raise HuddleError("bad_participants", "A huddle needs 2 to 6 people.")
    names = [str(p.get("name", "")).strip() for p in participants]
    if any(not n for n in names) or len({n.lower() for n in names}) != len(names):
        raise HuddleError("bad_participants", "Names must be non-empty and unique.")
    for p in participants:
        if p.get("channel", "voice") not in CHANNELS:
            raise HuddleError("bad_participants", f"channel must be one of {CHANNELS}.")
    if not 10 <= deadline_seconds <= 14 * 86400:
        raise HuddleError("bad_deadline", "deadline_seconds must be between 10 and 14 days.")
    need = getattr(m, "validate_need", lambda n: {})(need)

    deadline = now + timedelta(seconds=deadline_seconds)
    rnd = Round(id=secrets.token_hex(4), mode=mode, created_at=now, need=need,
                reminder_at=now + timedelta(seconds=deadline_seconds // 2), deadline_at=deadline)
    s.add(rnd)
    out = []
    for i, (p, name) in enumerate(zip(participants, names)):
        part = Participant(id=secrets.token_hex(4), round_id=rnd.id, name=name,
                           channel=p.get("channel", "voice"), is_host=(i == 0))
        s.add(part)
        token = make_token(part.id, deadline + timedelta(days=1))
        out.append({"name": name, "channel": part.channel, "is_host": part.is_host,
                    "token": token, "link": f"/r/{token}"})
    s.commit()
    return {"round_id": rnd.id, "mode": mode, "deadline_at": deadline.isoformat(),
            "participants": out}


def advance(s: Session, rnd: Round, now: datetime | None = None) -> Round:
    """Move collecting -> reminded -> closed according to the clock."""
    now = now or now_utc()
    if rnd.state == "closed":
        return rnd
    if now >= rnd.deadline_at:
        return _close(s, rnd)
    if rnd.state == "collecting" and now >= rnd.reminder_at:
        rnd.state = "reminded"
        s.add(rnd)
        s.commit()
    return rnd


def _close(s: Session, rnd: Round) -> Round:
    m = _mode(rnd.mode)
    parts = _participants(s, rnd.id)
    answers = _answers(s, rnd.id)
    real = [answers[p.id].data for p in parts if p.id in answers]
    defaulted = False
    for p in parts:
        if p.id not in answers:
            dflt = m.default_answer(real)
            s.add(Answer(participant_id=p.id, round_id=rnd.id, data=dflt, is_default=True,
                         created_at=now_utc()))
            answers[p.id] = Answer(participant_id=p.id, round_id=rnd.id, data=dflt)
            defaulted = True
    ordered = [(p.name, answers[p.id].data) for p in parts]
    rnd.result = m.compute(ordered, rnd.need, defaults_applied=defaulted)
    rnd.defaults_applied = defaulted
    rnd.state = "closed"
    s.add(rnd)
    s.commit()
    return rnd


def submit_answer(s: Session, token: str, payload: dict, now: datetime | None = None) -> dict:
    now = now or now_utc()
    p, rnd = _auth(s, token, now)
    rnd = advance(s, rnd, now)
    if rnd.state == "closed":
        raise HuddleError("round_closed", "This round is closed.", 409)
    if s.get(Answer, p.id) is not None:
        raise HuddleError("already_answered", "You already answered. Answers are single-use.", 409)
    payload = dict(payload)
    if payload.pop("consent", False) is not True:
        raise HuddleError("consent_required", "Every participant must opt in (consent: true).")
    note = payload.pop("note", None)
    warnings = [privacy.HEALTH_WARNING] if privacy.looks_like_health_text(note) else []
    m = _mode(rnd.mode)
    try:
        data = m.AnswerModel.model_validate(payload).model_dump()
    except ValidationError as e:
        msgs = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        raise HuddleError("invalid_answer", msgs) from None
    s.add(Answer(participant_id=p.id, round_id=rnd.id, data=data, created_at=now))
    s.commit()
    if len(_answers(s, rnd.id)) == len(_participants(s, rnd.id)):
        _close(s, rnd)
    return {"stored": True, "round_state": s.get(Round, rnd.id).state, "warnings": warnings}


def my_answers(s: Session, token: str, now: datetime | None = None) -> dict:
    """The only place a raw answer is returned, and only to its owner."""
    p, rnd = _auth(s, token, now or now_utc())
    a = s.get(Answer, p.id)
    return {"name": p.name, "answered": a is not None and not a.is_default,
            "answer": a.data if a and not a.is_default else None}


def status(s: Session, token: str, now: datetime | None = None) -> dict:
    now = now or now_utc()
    p, rnd = _auth(s, token, now)
    rnd = advance(s, rnd, now)
    answers = _answers(s, rnd.id)
    parts = _participants(s, rnd.id)
    return {
        "round_id": rnd.id, "mode": rnd.mode, "state": rnd.state,
        "deadline_at": rnd.deadline_at.isoformat(), "reminder_at": rnd.reminder_at.isoformat(),
        "need": rnd.need,
        "me": {"name": p.name, "is_host": p.is_host, "answered": p.id in answers},
        "participants": [{"name": q.name, "channel": q.channel, "answered": q.id in answers
                          and not answers[q.id].is_default} for q in parts],
        "options": getattr(_mode(rnd.mode), "OPTIONS", None),
    }


def nudge_pending(s: Session, token: str, now: datetime | None = None) -> dict:
    """Host-only: who has not answered yet (names only, never values)."""
    now = now or now_utc()
    p, rnd = _auth(s, token, now)
    if not p.is_host:
        raise HuddleError("host_only", "Only the host can nudge.", 403)
    rnd = advance(s, rnd, now)
    answers = _answers(s, rnd.id)
    pending = [q.name for q in _participants(s, rnd.id)
               if q.id not in answers or answers[q.id].is_default]
    return {"round_state": rnd.state, "pending": pending,
            "message": f"Reminder sent to {len(pending)} people." if pending else "Everyone answered."}


def close_round(s: Session, token: str, now: datetime | None = None) -> dict:
    now = now or now_utc()
    p, rnd = _auth(s, token, now)
    if not p.is_host:
        raise HuddleError("host_only", "Only the host can close the round.", 403)
    if rnd.state != "closed":
        _close(s, rnd)
    return get_result(s, token, now)


def get_result(s: Session, token: str, now: datetime | None = None) -> dict:
    now = now or now_utc()
    p, rnd = _auth(s, token, now)
    rnd = advance(s, rnd, now)
    if rnd.state != "closed":
        return {"ready": False, "state": rnd.state}
    return {"ready": True, "state": "closed", "result": rnd.result}


def server_holds(s: Session, token: str, now: datetime | None = None) -> dict:
    """Debug panel: proves answers are stored without showing any value."""
    p, rnd = _auth(s, token, now or now_utc())
    answers = _answers(s, rnd.id)
    return {"round_id": rnd.id,
            "stored": [{"name": q.name, "has_answer": q.id in answers and not answers[q.id].is_default,
                        "value": "held on server, not shown"} for q in _participants(s, rnd.id)]}
