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

from .. import config, notify
from ..db import (
    Answer,
    Checkin,
    Contact,
    Event,
    HouseholdLoad,
    Participant,
    PersonalShare,
    Round,
    RoundHousehold,
)
from . import card, care, everyday, privacy, trip

MODES = {"everyday": everyday, "care": care, "trip": trip}
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


def _log(s: Session, round_id: str, kind: str, now: datetime, actor: str | None = None,
         detail: str | None = None) -> None:
    """Append to the value-free audit trail (never records an answer)."""
    s.add(Event(round_id=round_id, at=now, kind=kind, actor=actor, detail=detail))


# ---- lifecycle --------------------------------------------------------------------------------

def create_round(s: Session, mode: str, participants: list[dict], deadline_seconds: int = 3600,
                 need: dict | None = None, now: datetime | None = None,
                 household_id: str | None = None, detail: str | None = None) -> dict:
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
        email = p.get("email")
        if email and not notify.EMAIL_RE.match(str(email).strip()):
            raise HuddleError("bad_participants", "That email address doesn't look right.")
    if not 10 <= deadline_seconds <= 14 * 86400:
        raise HuddleError("bad_deadline", "deadline_seconds must be between 10 and 14 days.")
    try:
        need = getattr(m, "validate_need", lambda n: {})(need)
    except ValueError as e:  # includes pydantic.ValidationError
        raise HuddleError("bad_need", str(e)) from None

    deadline = now + timedelta(seconds=deadline_seconds)
    rnd = Round(id=secrets.token_hex(4), mode=mode, created_at=now, need=need,
                reminder_at=now + timedelta(seconds=deadline_seconds // 2), deadline_at=deadline)
    s.add(rnd)
    out = []
    for i, (p, name) in enumerate(zip(participants, names)):
        part = Participant(id=secrets.token_hex(4), round_id=rnd.id, name=name,
                           channel=p.get("channel", "voice"), is_host=(i == 0))
        s.add(part)
        if p.get("email"):
            s.add(Contact(participant_id=part.id, email=str(p["email"]).strip()))
        token = make_token(part.id, deadline + timedelta(days=1))
        out.append({"name": name, "channel": part.channel, "is_host": part.is_host,
                    "token": token, "link": f"/r/{token}"})
    s.add(RoundHousehold(round_id=rnd.id, household_id=household_id or secrets.token_hex(6)))
    _log(s, rnd.id, "opened", now, actor=names[0], detail=detail or f"{len(names)} people, {mode}")
    s.commit()
    return {"round_id": rnd.id, "mode": mode, "deadline_at": deadline.isoformat(),
            "participants": out}


def advance(s: Session, rnd: Round, now: datetime | None = None) -> Round:
    """Move collecting -> reminded -> closed according to the clock."""
    now = now or now_utc()
    if rnd.state == "closed":
        return rnd
    if now >= rnd.deadline_at:
        return _close(s, rnd, now)
    if rnd.state == "collecting" and now >= rnd.reminder_at:
        rnd.state = "reminded"
        s.add(rnd)
        _log(s, rnd.id, "reminded", now)
        s.commit()
    return rnd


def _close(s: Session, rnd: Round, now: datetime | None = None) -> Round:
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
    kwargs = {"history": _history(s, rnd)} if rnd.mode == "care" else {}
    result = m.compute(ordered, rnd.need, defaults_applied=defaulted, **kwargs)
    private = result.pop("_private", None)  # per-person hours never go into the group result
    rnd.result = result
    if private:
        _record_private(s, rnd, private)
    rnd.defaults_applied = defaulted
    rnd.state = "closed"
    s.add(rnd)
    _log(s, rnd.id, "closed", now or now_utc(),
         detail="defaults applied for non-responders" if defaulted else "everyone answered")
    s.commit()
    return rnd


def _household(s: Session, round_id: str) -> str:
    link = s.get(RoundHousehold, round_id)
    return link.household_id if link else round_id


def _history(s: Session, rnd: Round) -> dict:
    """What EARLIER rounds in this household chain say about heavy tasks (internal; drives rotation)."""
    hh = _household(s, rnd.id)
    rows = [r for r in s.exec(select(HouseholdLoad).where(HouseholdLoad.household_id == hh))
            if r.round_id != rnd.id]
    heavy: dict[str, int] = {}
    held: dict[str, int] = {}
    for r in rows:
        key = r.person_name.lower()
        heavy[key] = heavy.get(key, 0) + r.heavy_hours
        held[key] = held.get(key, 0) + (1 if r.heavy_hours > 0 else 0)
    return {"rounds": len({r.round_id for r in rows}), "heavy": heavy, "held": held}


def _record_private(s: Session, rnd: Round, private: dict) -> None:
    hh = _household(s, rnd.id)
    for name, load in private["loads"].items():
        s.add(HouseholdLoad(household_id=hh, round_id=rnd.id, person_name=name,
                            heavy_hours=load["heavy"], total_hours=load["total"]))
    for name, tasks in private["shares"].items():
        for t in tasks:
            s.add(PersonalShare(round_id=rnd.id, person_name=name, task_id=t["task_id"],
                                label=t["label"], hours=t["hours"]))


def submit_answer(s: Session, token: str, payload: dict, now: datetime | None = None) -> dict:
    now = now or now_utc()
    p, rnd = _auth(s, token, now)
    rnd = advance(s, rnd, now)
    if rnd.state == "closed":
        raise HuddleError("round_closed", "This round is closed.", 409)
    existing = s.get(Answer, p.id)
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
    revised = existing is not None
    if revised:
        existing.data, existing.created_at = data, now
        s.add(existing)
        _log(s, rnd.id, "revised", now)  # deliberately no actor: the group never learns who changed
    else:
        s.add(Answer(participant_id=p.id, round_id=rnd.id, data=data, created_at=now))
        _log(s, rnd.id, "answered", now, actor=p.name)
    s.commit()
    if len(_answers(s, rnd.id)) == len(_participants(s, rnd.id)):
        _close(s, rnd, now)
    return {"stored": True, "revised": revised, "round_state": s.get(Round, rnd.id).state,
            "warnings": warnings}


def my_answers(s: Session, token: str, now: datetime | None = None) -> dict:
    """The only place a raw answer is returned, and only to its owner."""
    p, rnd = _auth(s, token, now or now_utc())
    a = s.get(Answer, p.id)
    return {"name": p.name, "answered": a is not None and not a.is_default,
            "answer": a.data if a and not a.is_default else None}


def _my_reminder(s: Session, rnd: Round, p: Participant, answers: dict) -> dict | None:
    """The latest reminder sent to ME while I still owe an answer (drives the banner on my own page)."""
    if p.id in answers and not answers[p.id].is_default:
        return None
    mine = [e for e in _reminder_events(s, rnd.id) if e.actor == p.name]
    if not mine:
        return None
    last = max(mine, key=lambda e: e.id)
    return {"at": last.at.isoformat(), "kind": (last.detail or "").split(":")[0]}


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
        "hints": _hints(s, rnd, p),
        "reminder": _my_reminder(s, rnd, p, answers),
        "participants": [{"name": q.name, "channel": q.channel, "answered": q.id in answers
                          and not answers[q.id].is_default} for q in parts],
        "options": getattr(_mode(rnd.mode), "OPTIONS", None),
        "events": [{"at": e.at.isoformat(), "kind": e.kind, "actor": e.actor, "detail": e.detail}
                   for e in s.exec(select(Event).where(Event.round_id == rnd.id).order_by(Event.id))],
    }


MANUAL_REMINDER_GAP = timedelta(minutes=10)


def _pending(s: Session, rnd: Round) -> list[Participant]:
    answers = _answers(s, rnd.id)
    return [q for q in _participants(s, rnd.id) if q.id not in answers or answers[q.id].is_default]


def _reminder_events(s: Session, round_id: str) -> list[Event]:
    return list(s.exec(select(Event).where(Event.round_id == round_id, Event.kind == "reminder_sent")))


def _send_reminder(s: Session, rnd: Round, p: Participant, kind: str, now: datetime, deliver) -> list:
    """Deliver one reminder to one person and record it (names and channels only, never content)."""
    contact = s.get(Contact, p.id)
    token = make_token(p.id, rnd.deadline_at + timedelta(days=1))
    deliveries = deliver(name=p.name, email=contact.email if contact else None, mode=rnd.mode,
                         link=f"{config.PUBLIC_URL}/r/{token}", kind=kind)
    summary = ", ".join(f"{d.channel} {d.status}" for d in deliveries)
    _log(s, rnd.id, "reminder_sent", now, actor=p.name, detail=f"{kind}: {summary}")
    s.commit()
    return deliveries


def tick(s: Session, now: datetime | None = None, deliver=notify.deliver) -> list[tuple[str, str, str]]:
    """Run by the background scheduler. For every open round: move it along the clock (including
    closing at the deadline with defaults) and send each pending person their first and final reminder
    once. Returns [(round_id, person, kind)] for what was sent."""
    now = now or now_utc()
    sent = []
    for rnd in list(s.exec(select(Round).where(Round.state != "closed"))):
        rnd = advance(s, rnd, now)
        if rnd.state == "closed":
            continue
        total = rnd.deadline_at - rnd.created_at
        final_at = rnd.deadline_at - min(timedelta(minutes=10), total * 0.1)
        already = {(e.actor, (e.detail or "").split(":")[0]) for e in _reminder_events(s, rnd.id)}
        for p in _pending(s, rnd):
            for kind, due in (("first", rnd.reminder_at), ("final", final_at)):
                if now >= due and (p.name, kind) not in already:
                    _send_reminder(s, rnd, p, kind, now, deliver)
                    sent.append((rnd.id, p.name, kind))
                    already.add((p.name, kind))
    return sent


def nudge_pending(s: Session, token: str, now: datetime | None = None, deliver=notify.deliver) -> dict:
    """Host only: remind everyone who hasn't answered, now. Delivery results are reported honestly
    (names, channels and statuses; never content). A person is not nudged twice within 10 minutes."""
    now = now or now_utc()
    p, rnd = _auth(s, token, now)
    if not p.is_host:
        raise HuddleError("host_only", "Only the host can nudge.", 403)
    rnd = advance(s, rnd, now)
    pending = [] if rnd.state == "closed" else _pending(s, rnd)
    last = {}
    for e in _reminder_events(s, rnd.id):
        last[e.actor] = max(last.get(e.actor, e.at), e.at)
    results = []
    for q in pending:
        if q.name in last and now - last[q.name] < MANUAL_REMINDER_GAP:
            results.append({"name": q.name, "channel": "all", "status": "skipped",
                            "detail": "reminded recently"})
            continue
        for d in _send_reminder(s, rnd, q, "manual", now, deliver):
            results.append({"name": q.name, "channel": d.channel, "status": d.status, "detail": d.detail})
    sent_to = sorted({r["name"] for r in results if r["status"] in ("queued", "sent")})
    return {"round_state": rnd.state, "pending": [q.name for q in pending], "deliveries": results,
            "message": (f"Reminded {', '.join(sent_to)}." if sent_to
                        else "Everyone answered." if not pending else "Nobody needed a new reminder yet.")}


def close_round(s: Session, token: str, now: datetime | None = None) -> dict:
    now = now or now_utc()
    p, rnd = _auth(s, token, now)
    if not p.is_host:
        raise HuddleError("host_only", "Only the host can close the round.", 403)
    if rnd.state != "closed":
        _close(s, rnd, now)
    return get_result(s, token, now)


def get_result(s: Session, token: str, now: datetime | None = None) -> dict:
    now = now or now_utc()
    p, rnd = _auth(s, token, now)
    rnd = advance(s, rnd, now)
    if rnd.state != "closed":
        return {"ready": False, "state": rnd.state}
    shares = [{"task_id": x.task_id, "label": x.label, "hours": x.hours}
              for x in s.exec(select(PersonalShare).where(PersonalShare.round_id == rnd.id,
                                                          PersonalShare.person_name == p.name))]
    return {"ready": True, "state": "closed", "result": rnd.result,
            "my_share": shares,  # this caller's own hours only
            "checkin": _checkin_summary(s, rnd)}


def revisit_round(s: Session, token: str, need: dict | None = None, deadline_seconds: int = 3600,
                  now: datetime | None = None, mode: str | None = None) -> dict:
    """Host only, after a round closes: open the household's next round for the same people.

    `mode` defaults to the same decision type (a follow-up) or can be another one (for example a
    weekend plan after a care plan). Nothing private carries over: everyone answers from scratch.
    The new round joins the same household, so the fairness record and care-load hints continue.
    """
    now = now or now_utc()
    p, rnd = _auth(s, token, now)
    rnd = advance(s, rnd, now)
    if not p.is_host:
        raise HuddleError("host_only", "Only the host can start the next round.", 403)
    if rnd.state != "closed":
        raise HuddleError("not_closed", "Finish this round before starting the next one.", 409)
    new_mode = mode or rnd.mode
    _mode(new_mode)
    if new_mode == "care":
        need = need or (rnd.need if rnd.mode == "care" else None)
    else:
        need = None
    people = []
    for q in _participants(s, rnd.id):
        entry = {"name": q.name, "channel": q.channel}
        contact = s.get(Contact, q.id)
        if contact:
            entry["email"] = contact.email  # kept server-side so reminders continue; never returned
        people.append(entry)
    detail = (f"follow-up to round {rnd.id}" if new_mode == rnd.mode
              else f"next decision ({new_mode}) after round {rnd.id}")
    return create_round(s, new_mode, people, deadline_seconds, need, now,
                        household_id=_household(s, rnd.id), detail=detail)


# Which leisure dealbreakers a heavy care load might make someone want to rule out.
_HINT_BY_MODE = {
    "everyday": [("early_start", "early starts"), ("long_drive", "long drives"),
                 ("physical", "physical effort")],
    "trip": [("early_start", "early starts"), ("long_drive", "long drives"),
             ("strenuous", "strenuous activity")],
}


def _hints(s: Session, rnd: Round, p: Participant) -> list[dict]:
    """Optional private hint for ONE person, from their own public care assignment in this household.

    Shown only to them and never applied automatically. Built from the published split
    (their own private hours), is shown only to them, and reveals nothing about anyone else.
    """
    options = _HINT_BY_MODE.get(rnd.mode)
    if not options:
        return []
    hh = _household(s, rnd.id)
    best = None
    for link in s.exec(select(RoundHousehold).where(RoundHousehold.household_id == hh)):
        other = s.get(Round, link.round_id)
        if other and other.mode == "care" and other.state == "closed" and other.result:
            closed_events = s.exec(select(Event).where(Event.round_id == other.id, Event.kind == "closed"))
            when = max((e.at for e in closed_events), default=None)
            if best is None or (when and when > best[0]):
                best = (when, other)
    if best is None:
        return []
    row = s.exec(select(HouseholdLoad).where(HouseholdLoad.round_id == best[1].id,
                                             HouseholdLoad.person_name == p.name)).first()
    heavy = row.heavy_hours if row else 0
    if heavy <= 0:
        return []
    labels = ", ".join(label for _, label in options)
    return [{
        "message": (f"In your household's latest care plan you carry {heavy} h/week of heavy tasks "
                    f"(overnight cover, appointments and transport). If that limits what you can do, you "
                    f"could rule out {labels}. Optional, and only you see this."),
        "suggested_dealbreakers": [key for key, _ in options],
    }]


def household_history(s: Session, token: str, now: datetime | None = None) -> dict:
    """The household's closed plans, oldest first. Aggregate only: the same things already shown to all."""
    p, rnd = _auth(s, token, now or now_utc())
    items = []
    for link in s.exec(select(RoundHousehold).where(RoundHousehold.household_id == _household(s, rnd.id))):
        r = s.get(Round, link.round_id)
        if not r or r.state != "closed" or not r.result:
            continue
        closed_events = s.exec(select(Event).where(Event.round_id == r.id, Event.kind == "closed"))
        closed = max((e.at for e in closed_events), default=r.created_at)
        res = r.result
        if r.mode == "care":
            summary = res["headline"]
        elif res.get("plan"):
            summary = f"{res['plan']['name']}, around {res['plan']['price_band']} per person"
        else:
            summary = "No plan fit every limit"
        checkin = _checkin_summary(s, r)
        items.append({"round_id": r.id, "mode": r.mode, "title": card.build_card(res)["title"],
                      "summary": summary, "at": closed.isoformat(),
                      "checkin": checkin.get("message") if checkin.get("complete") else None})
    items.sort(key=lambda i: i["at"])
    return {"plans": items}


def plan_card(s: Session, token: str, now: datetime | None = None) -> dict:
    """Copyable, printable, speakable summary of the closed round (aggregate only)."""
    out = get_result(s, token, now)
    if not out["ready"]:
        raise HuddleError("not_ready", "The round is still open.", 409)
    return card.build_card(out["result"], out.get("checkin"))


def submit_checkin(s: Session, token: str, score: int, now: datetime | None = None) -> dict:
    """Day-after check-in: how comfortable are you with the plan (1-5)? Private, single-use."""
    now = now or now_utc()
    p, rnd = _auth(s, token, now)
    rnd = advance(s, rnd, now)
    if rnd.state != "closed":
        raise HuddleError("not_closed", "The check-in opens once the plan is decided.", 409)
    if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
        raise HuddleError("invalid_score", "score must be a whole number from 1 to 5.")
    if s.get(Checkin, p.id) is not None:
        raise HuddleError("already_checked_in", "You already checked in.", 409)
    s.add(Checkin(participant_id=p.id, round_id=rnd.id, score=score, created_at=now))
    _log(s, rnd.id, "checked_in", now, actor=p.name)
    s.commit()
    return {"stored": True, "summary": _checkin_summary(s, rnd)}


def _checkin_summary(s: Session, rnd: Round) -> dict:
    """Unattributed. Shown only once everyone has checked in; never lists scores by name."""
    n = len(_participants(s, rnd.id))
    scores = [c.score for c in s.exec(select(Checkin).where(Checkin.round_id == rnd.id))]
    out: dict = {"checked_in": len(scores), "of": n, "complete": len(scores) == n}
    if not out["complete"]:
        return out
    policy = privacy.reveal_policy(n)
    uncomfortable = any(x <= 2 for x in scores)
    out["revisit"] = uncomfortable
    out["message"] = ("At least one person is not comfortable with the plan. Talk it through and "
                      "consider running a new round." if uncomfortable
                      else "Everyone is comfortable with the plan.")
    if policy.single_limit_detail:
        out["comfortable_count"] = sum(1 for x in scores if x >= 4)
    if policy.warning:
        out["warning"] = policy.warning
    return out


def server_holds(s: Session, token: str, now: datetime | None = None) -> dict:
    """Debug panel: proves answers are stored without showing any value."""
    p, rnd = _auth(s, token, now or now_utc())
    answers = _answers(s, rnd.id)
    return {"round_id": rnd.id,
            "stored": [{"name": q.name, "has_answer": q.id in answers and not answers[q.id].is_default,
                        "value": "held on server, not shown"} for q in _participants(s, rnd.id)]}
