"""The daily briefing: one person's day in a few sentences an assistant can read aloud.

It only puts together what the caller can already see: their own commitments and clashes, their own chores,
offers made to them, and the decisions waiting for their own private answer. Nothing about anyone else, and no
private limit is ever spoken. No new storage.
"""

from datetime import date, datetime, time, timedelta

from sqlmodel import Session

from . import home as hm
from . import schedule as sc
from . import schedule_service as ss
from .rounds import HuddleError, now_utc


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _day(now: datetime, day: str | None, today: str | None) -> date:
    if not day:
        return ss._today(now, today)
    try:
        return date.fromisoformat(day)
    except ValueError:
        raise HuddleError("bad_day", "A day looks like 2026-10-08.") from None


def get_briefing(
    s: Session, token: str, day: str | None = None, now: datetime | None = None, today: str | None = None
) -> dict:
    """The caller's own day: what is on, what clashes, chores due, offers and decisions waiting, and the next
    free hour. `say` is the same thing as sentences, for a voice."""
    now = now or now_utc()
    me, _ = ss._auth(s, token, now)
    d = _day(now, day, today)
    start = datetime.combine(d, time(0))
    items, rules = ss._items(s, me.id), ss._rules(s, me.id)
    occ = sc.expand(items, start, start + timedelta(days=1))
    clashes = sc.conflicts(items, start, start + timedelta(days=1), rules)
    free = sc.free_slots(items, rules, d, d, 60, limit=1)
    mine = hm.get_state(s, token, now)["mine"]
    chores = [
        a
        for a in mine["assignments"]
        if a["status"] == "planned" and a["due"] and date.fromisoformat(a["due"]) <= d
    ]
    offers = mine["proposals"]
    waiting = [x for x in mine["decisions"] if x["state"] != "closed" and not x["answered"]]

    spoken = []
    heading = "Today" if d == ss._today(now, today) else "On " + sc.label(start).rsplit(",", 1)[0]
    if occ:
        listed = ", ".join(f"{o.title} at {o.start.strftime('%H:%M')}" for o in occ[:5])
        more = f", and {len(occ) - 5} more" if len(occ) > 5 else ""
        spoken.append(f"{heading} you have {_plural(len(occ), 'thing')}: {listed}{more}.")
    else:
        spoken.append(f"{heading} your calendar is clear.")
    if clashes:
        k = clashes[0]
        extra = f", and {_plural(len(clashes) - 1, 'more clash')}".replace("clashs", "clashes") if len(clashes) > 1 else ""
        spoken.append(f"{k.a.title} and {k.b.title} overlap{extra}. Ask me for options.")
    if chores:
        spoken.append(f"Chores due: {', '.join(a['title'] for a in chores[:4])}.")
    if offers:
        spoken.append(f"{_plural(len(offers), 'chore')} {'is' if len(offers) == 1 else 'are'} waiting for you to accept or decline.")
    if waiting:
        spoken.append(f"{_plural(len(waiting), 'family decision')} {'is' if len(waiting) == 1 else 'are'} waiting for your private answer.")
    if free:
        spoken.append(f"Your next free hour is at {free[0].strftime('%H:%M')}.")
    return {
        "day": d.isoformat(),
        "items": [ss._view(o) for o in occ],
        "clashes": [{"a": ss._view(k.a), "b": ss._view(k.b)} for k in clashes],
        "chores_due": [{"id": a["id"], "title": a["title"], "due": a["due"], "minutes": a["minutes"]} for a in chores],
        "offers": len(offers),
        "decisions_waiting": [{"round_id": x["round_id"], "title": x["title"], "deadline_at": x["deadline_at"]} for x in waiting],
        "next_free": free[0].isoformat(timespec="minutes") if free else None,
        "say": " ".join(spoken),
    }
