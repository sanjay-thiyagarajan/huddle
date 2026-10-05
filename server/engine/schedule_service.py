"""Scheduling service: a person's private time across family, friends, work and personal life, and
find-a-time decisions with friends, colleagues and family.

Privacy: a person's commitments (titles and times) and rules are returned only to them. A find-a-time is an
ordinary Huddle decision of mode "when": everyone sees the same candidate times, answers privately, and the
group is told the time that works and how well it fits, never who was busy or why. Members get *suggested*
answers computed from their own schedule (with private reasons); guests answer by a private link.

No external calendars are read or written: commitments are entered by the person, in words or on a form.
Times are floating local times.
"""

import ipaddress
import secrets
import socket
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from sqlmodel import Session, select

from .. import notify
from ..db import (
    CalendarFeed,
    CalendarImport,
    Commitment,
    Contact,
    Home,
    HomeEvent,
    Member,
    Participant,
    ParticipantMember,
    ReminderPref,
    Round,
    RoundHome,
    ScheduleRule,
)
from . import home as hm
from . import ical, rounds
from . import schedule as sc
from .rounds import HuddleError, now_utc

MAX_COMMITMENT_MINUTES = 14 * 60
LEARN_AFTER = 2  # after this many consistent choices the agent offers to remember a rule
STARTING_SOON = timedelta(minutes=30)  # how far ahead "starting soon" looks
FEED_EVERY = timedelta(hours=1)  # a subscribed calendar is read at most this often
FEED_GIVE_UP_AFTER = 5  # consecutive failed reads before the agent stops trying
DIGEST_DAY, DIGEST_FROM = 6, time(18, 0)  # Sunday evening, in the person's own time
REMINDER_KINDS = ("starting_soon", "digest")  # both are opt-in: times are floating, so the person's own offset is needed


# ---- helpers ------------------------------------------------------------------------------------------------


def _auth(s: Session, token: str, now: datetime) -> tuple[Member, Home]:
    return hm._auth(s, token, now)


def _today(now: datetime, today: str | None) -> date:
    """The person's local date. A browser passes its own; anything far from the server's is ignored."""
    if today:
        try:
            d = date.fromisoformat(today)
            if abs((d - now.date()).days) <= 2:
                return d
        except ValueError:
            pass
    return now.date()


def _t(text: str) -> time:
    h, m = text.split(":")
    return time(int(h), int(m))


def _hhmm(t: time) -> str:
    return t.strftime("%H:%M")


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="minutes")


def _dt(text: str) -> datetime:
    try:
        return datetime.fromisoformat(str(text)).replace(tzinfo=None)
    except ValueError:
        raise HuddleError("bad_time", "Times look like 2026-10-08T19:00.") from None


def _rules(s: Session, member_id: str) -> sc.Rules:
    r = s.get(ScheduleRule, member_id)
    if r is None:
        return sc.Rules()
    return sc.Rules(
        circle_rank=list(r.circle_rank or sc.DEFAULT_RANK),
        protected=[
            sc.Window(tuple(w["days"]), _t(w["start"]), _t(w["end"]), w.get("label", "protected time"))
            for w in (r.protected or [])
        ],
        work_start=_t(r.work_start) if r.work_start else None,
        work_end=_t(r.work_end) if r.work_end else None,
        max_evenings=r.max_evenings,
        buffer_minutes=r.buffer_minutes or 0,
    )


def rules_view(s: Session, member_id: str) -> dict:
    r = s.get(ScheduleRule, member_id)
    rules = _rules(s, member_id)
    return {
        "circle_rank": rules.circle_rank,
        "protected": [
            {"days": list(w.days), "start": _hhmm(w.start), "end": _hhmm(w.end), "label": w.label}
            for w in rules.protected
        ],
        "work_start": _hhmm(rules.work_start) if rules.work_start else None,
        "work_end": _hhmm(rules.work_end) if rules.work_end else None,
        "max_evenings": rules.max_evenings,
        "buffer_minutes": rules.buffer_minutes,
        "learned": dict(r.learned or {}) if r else {},
    }


def _items(s: Session, member_id: str) -> list[sc.Item]:
    out = []
    for c in s.exec(
        select(Commitment).where(Commitment.member_id == member_id, Commitment.status != "cancelled")
    ):
        out.append(
            sc.Item(
                id=c.id,
                title=c.title,
                circle=c.circle,
                start=c.start,
                end=c.end,
                flexibility=c.flexibility,
                importance=c.importance,
                shared=bool(c.shared_round_id),
                tentative=c.status == "tentative",
                repeat=c.repeat,
                until=date.fromisoformat(c.until) if c.until else None,
                skips=tuple(c.skips or ()),
            )
        )
    return out


def _view(o: sc.Item) -> dict:
    return {
        "id": o.id,
        "title": o.title,
        "circle": o.circle,
        "start": _iso(o.start),
        "end": _iso(o.end),
        "minutes": o.minutes,
        "flexibility": o.flexibility,
        "importance": o.importance,
        "shared": o.shared,
        "tentative": o.tentative,
        "repeat": o.repeat,
        "part": sc.part_of_day(o.start),
        "date": o.start.date().isoformat(),
    }


# ---- rules ---------------------------------------------------------------------------------------------------


def set_rules(s: Session, token: str, changes: dict, now: datetime | None = None) -> dict:
    """Owner-only: how the agent should weigh and protect your time."""
    now = now or now_utc()
    me, _ = _auth(s, token, now)
    r = s.get(ScheduleRule, me.id) or ScheduleRule(member_id=me.id)
    if "circle_rank" in changes:
        rank = changes["circle_rank"]
        if (
            not isinstance(rank, list)
            or not rank
            or any(c not in sc.CIRCLES for c in rank)
            or len(set(rank)) != len(rank)
        ):
            raise HuddleError("bad_rules", f"circle_rank is an ordered list of {sc.CIRCLES}.")
        r.circle_rank = rank
    if "protected" in changes:
        windows = changes["protected"]
        if not isinstance(windows, list) or len(windows) > 8:
            raise HuddleError("bad_rules", "protected is a list of up to 8 windows.")
        clean = []
        for w in windows:
            try:
                days = sorted({int(d) for d in w["days"]})
                a, b = _t(w["start"]), _t(w["end"])
            except (KeyError, ValueError, TypeError):
                raise HuddleError(
                    "bad_rules", "A protected window needs days (0 to 6), start and end like 08:00."
                ) from None
            if not days or any(d not in range(7) for d in days) or a >= b:
                raise HuddleError(
                    "bad_rules", "A protected window needs valid days and a start before its end."
                )
            clean.append(
                {
                    "days": days,
                    "start": _hhmm(a),
                    "end": _hhmm(b),
                    "label": str(w.get("label") or "protected time")[:40],
                }
            )
        r.protected = clean
    if "work_start" in changes or "work_end" in changes:
        ws, we = changes.get("work_start", r.work_start), changes.get("work_end", r.work_end)
        if (ws is None) != (we is None) or (ws and _t(ws) >= _t(we)):
            raise HuddleError(
                "bad_rules", "Give both work_start and work_end, with the start before the end."
            )
        r.work_start, r.work_end = ws, we
    if "max_evenings" in changes:
        v = changes["max_evenings"]
        if v is not None and (not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 7):
            raise HuddleError("bad_rules", "max_evenings is 0 to 7, or null.")
        r.max_evenings = v
    if "buffer_minutes" in changes:
        v = changes["buffer_minutes"]
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 120:
            raise HuddleError("bad_rules", "buffer_minutes is 0 to 120.")
        r.buffer_minutes = v
    r.updated_at = now
    s.add(r)
    s.commit()
    return rules_view(s, me.id)


# ---- analysing and adding a commitment ----------------------------------------------------------------------------


def _normalize(fields: dict, today: date) -> dict:
    title = str(fields.get("title", "")).strip()
    if not 1 <= len(title) <= 80:
        raise HuddleError("bad_commitment", "A commitment needs a title (up to 80 characters).")
    circle = fields.get("circle") or "personal"
    if circle not in sc.CIRCLES:
        raise HuddleError("bad_commitment", f"circle is one of {sc.CIRCLES}.")
    start = _dt(fields["start"]) if fields.get("start") else None
    if start is None:
        raise HuddleError("bad_commitment", "A commitment needs a start time.")
    if fields.get("end"):
        end = _dt(fields["end"])
    else:
        minutes = fields.get("minutes", 60)
        if not isinstance(minutes, int) or isinstance(minutes, bool):
            raise HuddleError("bad_commitment", "minutes is a whole number.")
        end = start + timedelta(minutes=minutes)
    if not timedelta(minutes=5) <= end - start <= timedelta(minutes=MAX_COMMITMENT_MINUTES):
        raise HuddleError("bad_commitment", "A commitment lasts 5 minutes to 14 hours.")
    flex = fields.get("flexibility") or sc.DEFAULT_FLEX[circle]
    if flex not in sc.FLEX:
        raise HuddleError("bad_commitment", f"flexibility is one of {sc.FLEX}.")
    importance = fields.get("importance") or 2
    if importance not in (1, 2, 3):
        raise HuddleError("bad_commitment", "importance is 1, 2 or 3.")
    repeat = fields.get("repeat") or "none"
    if repeat not in sc.REPEATS:
        raise HuddleError("bad_commitment", f"repeat is one of {sc.REPEATS}.")
    until = fields.get("until")
    if until:
        try:
            date.fromisoformat(str(until))
        except ValueError:
            raise HuddleError("bad_commitment", "until is a date like 2026-12-20.") from None
    return {
        "title": title,
        "circle": circle,
        "start": start,
        "end": end,
        "flexibility": flex,
        "importance": importance,
        "repeat": repeat,
        "until": str(until) if until else None,
    }


def _probe(f: dict) -> sc.Item:
    return sc.Item(
        "new",
        f["title"],
        f["circle"],
        f["start"],
        f["end"],
        f["flexibility"],
        f["importance"],
        False,
        False,
        f["repeat"],
        date.fromisoformat(f["until"]) if f["until"] else None,
    )


def analyze(
    s: Session, token: str, fields: dict, now: datetime | None = None, today: str | None = None
) -> dict:
    """Check a new commitment against what the person already has, without adding it."""
    now = now or now_utc()
    me, _ = _auth(s, token, now)
    f = _normalize(fields, _today(now, today))
    return _analysis(s, me, f)


def _analysis(s: Session, me: Member, f: dict) -> dict:
    items, rules = _items(s, me.id), _rules(s, me.id)
    probe = _probe(f)
    horizon = (probe.start, probe.start + timedelta(days=28) if probe.repeat != "none" else probe.end)
    clash_occ = []
    for occ in sc.occurrences(probe, *horizon):
        for c in sc.clashes_with(occ, items, rules):
            if all(not (c.id == k.id and c.start == k.start) for k in clash_occ):
                clash_occ.append(c)
    clash_occ.sort(key=lambda c: (c.start, c.id))
    out = []
    for c in clash_occ[:3]:
        first = next(
            o for o in sc.occurrences(probe, *horizon) if sc.overlaps(o.start, o.end, c.start, c.end)
        )
        out.append({**_view(c), "options": sc.conflict_options(first, c, items, rules)})
    week = sc.week_start(probe.start.date())
    summary = sc.week_summary([*items, probe] if probe.repeat == "none" else items, rules, week)
    return {
        "item": {**_view(probe), "id": "new"},
        "clashes": out,
        "rule_flags": sc.rule_flags(probe, rules),
        "notes": [n for n in summary["notes"] if "evenings out" in n],
    }


def _create(
    s: Session, me: Member, f: dict, now: datetime, status: str = "active", round_id: str | None = None
) -> Commitment:
    c = Commitment(
        id=secrets.token_hex(4),
        member_id=me.id,
        title=f["title"],
        circle=f["circle"],
        start=f["start"],
        end=f["end"],
        flexibility=f["flexibility"],
        importance=f["importance"],
        repeat=f["repeat"],
        until=f["until"],
        skips=[],
        status=status,
        shared_round_id=round_id,
        created_at=now,
    )
    s.add(c)
    return c


def _own(s: Session, me: Member, cid: str) -> Commitment:
    c = s.get(Commitment, cid)
    if c is None or c.member_id != me.id or c.status == "cancelled":
        raise HuddleError("not_yours", "That isn't one of your commitments.", 403)
    return c


def _remove_occurrence(c: Commitment, when: datetime) -> None:
    """Cancel one occurrence of a repeating commitment, or the whole commitment if it doesn't repeat."""
    if c.repeat == "none":
        c.status = "cancelled"
    else:
        c.skips = [*(c.skips or []), when.date().isoformat()]


def _learn(s: Session, me: Member, kept: str, given_up: str) -> dict | None:
    """Remember how the person chooses between circles. After a couple of consistent choices, offer a rule."""
    if kept == given_up:
        return None
    r = s.get(ScheduleRule, me.id) or ScheduleRule(member_id=me.id)
    learned = dict(r.learned or {})
    key = f"{kept}>{given_up}"
    learned[key] = learned.get(key, 0) + 1
    r.learned = learned
    s.add(r)
    ranked = r.circle_rank or sc.DEFAULT_RANK
    already = ranked.index(kept) < ranked.index(given_up) if kept in ranked and given_up in ranked else False
    if learned[key] == LEARN_AFTER and not already:
        return {"prefer": kept, "over": given_up}
    return None


def add_commitment(
    s: Session,
    token: str,
    fields: dict,
    resolution: dict | None = None,
    now: datetime | None = None,
    today: str | None = None,
) -> dict:
    """Add a commitment. If it clashes with something, say how (with options) unless a resolution is given:
    {choice: keep_both | decide_later | drop_new | move_new | move_existing | drop_existing | ask_others, ...}."""
    now = now or now_utc()
    me, _ = _auth(s, token, now)
    f = _normalize(fields, _today(now, today))
    analysis = _analysis(s, me, f)
    if analysis["clashes"] and not resolution:
        return {"created": False, "analysis": analysis}
    choice = (resolution or {}).get("choice", "keep_both")
    rule_suggestion, next_step = None, None
    first = analysis["clashes"][0] if analysis["clashes"] else None
    if choice == "drop_new":
        if first:
            rule_suggestion = _learn(s, me, first["circle"], f["circle"])
        s.commit()
        return {"created": False, "dropped": True, "rule_suggestion": rule_suggestion, "analysis": analysis}
    if choice == "move_new":
        new_start = _dt(resolution["new_start"])
        f = {**f, "start": new_start, "end": new_start + (f["end"] - f["start"])}
        if first:
            rule_suggestion = _learn(s, me, first["circle"], f["circle"])
    elif choice in ("move_existing", "drop_existing") and first:
        existing = _own(s, me, first["id"])
        kept_status = existing.status
        _remove_occurrence(existing, _dt(first["start"]))
        s.add(existing)
        if choice == "move_existing":
            nstart = _dt(resolution["existing_new_start"])
            moved = {
                "title": existing.title,
                "circle": existing.circle,
                "start": nstart,
                "end": nstart + (existing.end - existing.start),
                "flexibility": existing.flexibility,
                "importance": existing.importance,
                "repeat": "none",
                "until": None,
            }
            _create(s, me, moved, now, kept_status, existing.shared_round_id)
        rule_suggestion = _learn(s, me, f["circle"], first["circle"])
    elif choice == "ask_others" and first:
        next_step = {"action": "ask_others", "existing_id": first["id"]}
    c = _create(s, me, f, now)
    s.commit()
    return {
        "created": True,
        "commitment": _view(_item_of(c)),
        "rule_suggestion": rule_suggestion,
        "next": next_step,
        "analysis": _analysis(s, me, f) if choice in ("keep_both", "decide_later") else None,
    }


def _item_of(c: Commitment) -> sc.Item:
    return sc.Item(
        c.id,
        c.title,
        c.circle,
        c.start,
        c.end,
        c.flexibility,
        c.importance,
        bool(c.shared_round_id),
        c.status == "tentative",
        c.repeat,
        date.fromisoformat(c.until) if c.until else None,
        tuple(c.skips or ()),
    )


def update_commitment(
    s: Session,
    token: str,
    commitment_id: str,
    changes: dict,
    occurrence: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Edit or cancel one of your own commitments. For a repeating one, `occurrence` (a date) changes just
    that day; without it the whole series changes."""
    now = now or now_utc()
    me, _ = _auth(s, token, now)
    c = _own(s, me, commitment_id)
    if changes.get("status") == "cancelled":
        if occurrence and c.repeat != "none":
            c.skips = [*(c.skips or []), occurrence]
        else:
            c.status = "cancelled"
        s.add(c)
        s.commit()
        return {"cancelled": True}
    merged = {
        "title": changes.get("title", c.title),
        "circle": changes.get("circle", c.circle),
        "start": changes.get("start", _iso(c.start)),
        "end": changes.get("end") or None,
        "minutes": None if changes.get("end") else int((c.end - c.start).total_seconds() // 60),
        "flexibility": changes.get("flexibility", c.flexibility),
        "importance": changes.get("importance", c.importance),
        "repeat": changes.get("repeat", c.repeat),
        "until": changes.get("until", c.until),
    }
    if not merged["end"]:
        merged.pop("end")
    f = _normalize(merged, now.date())
    if occurrence and c.repeat != "none":  # change one day: skip it in the series and add a one-off
        c.skips = [*(c.skips or []), occurrence]
        s.add(c)
        new = _create(s, me, {**f, "repeat": "none", "until": None}, now, c.status, c.shared_round_id)
        s.commit()
        return {"commitment": _view(_item_of(new))}
    c.title, c.circle, c.start, c.end = f["title"], f["circle"], f["start"], f["end"]
    c.flexibility, c.importance, c.repeat, c.until = (
        f["flexibility"],
        f["importance"],
        f["repeat"],
        f["until"],
    )
    s.add(c)
    s.commit()
    return {"commitment": _view(_item_of(c))}


def confirm_tentative(
    s: Session, token: str, commitment_id: str, keep: bool, now: datetime | None = None
) -> dict:
    now = now or now_utc()
    me, _ = _auth(s, token, now)
    c = _own(s, me, commitment_id)
    c.status = "active" if keep else "cancelled"
    s.add(c)
    s.commit()
    return {"kept": keep}


# ---- my week ---------------------------------------------------------------------------------------------------------


def _chore_care_minutes(s: Session, home: Home, member: Member, week: date) -> int:
    rows = hm._week_rows(s, home.id, week)
    _, minutes, _ = hm._loads_with_care(s, home.id, rows, hm._chore_rows(s, home.id))
    return minutes.get(member.id, 0)


def get_my_time(
    s: Session, token: str, week: str | None = None, now: datetime | None = None, today: str | None = None
) -> dict:
    """The caller's own week across all their circles, their clashes, rules, gatherings, and a note on how
    much free time chores and care realistically have. Nobody else's schedule is ever included."""
    now = now or now_utc()
    me, home = _auth(s, token, now)
    wk = date.fromisoformat(week) if week else sc.week_start(_today(now, today))
    if wk.weekday() != 0:
        raise HuddleError("bad_week", "A week starts on a Monday.")
    items, rules = _items(s, me.id), _rules(s, me.id)
    start = datetime.combine(wk, time(0))
    end = start + timedelta(days=7)
    occ = sc.expand(items, start, end)
    clashes = sc.conflicts(items, start, end, rules)
    summary = sc.week_summary(items, rules, wk, _chore_care_minutes(s, home, me, wk))
    return {
        "week": wk.isoformat(),
        "items": [_view(o) for o in occ],
        "conflicts": [
            {
                "a": _view(c.a),
                "b": _view(c.b),
                "options": sc.conflict_options(
                    *((c.b, c.a) if sc.priority(c.a, rules) >= sc.priority(c.b, rules) else (c.a, c.b)),
                    items,
                    rules,
                ),
            }
            for c in clashes
        ],
        "tentative": [_view(o) for o in occ if o.tentative],
        "summary": summary,
        "rules": rules_view(s, me.id),
        "gatherings": my_gatherings(s, home, me, now),
        "reminders": {**reminder_view(s, me.id), "due": _due_now(s, me, now)},
        "feed": feed_view(s, me.id),
    }


# ---- find a time: friends, colleagues and family ----------------------------------------------------------------------


def _slots_from(fields: dict, duration: int) -> list[str]:
    if fields.get("slots"):
        return [_iso(_dt(x)) for x in fields["slots"]]
    out: list[datetime] = []
    for w in fields.get("windows") or []:
        try:
            d1, d2 = (
                date.fromisoformat(w["date_from"]),
                date.fromisoformat(w.get("date_to") or w["date_from"]),
            )
            a, b = _t(w.get("from", "17:00")), _t(w.get("to", "22:00"))
            days = tuple(int(x) for x in w["weekdays"]) if w.get("weekdays") else None
        except (KeyError, ValueError, TypeError):
            raise HuddleError(
                "bad_gathering", "A window needs date_from, optional date_to, from and to like 18:00."
            ) from None
        out += sc.generate_slots(d1, d2, duration, a, b, days, 60, 40)
    return [_iso(x) for x in sorted(set(out))[:40]]


def start_gathering(
    s: Session, token: str, fields: dict, now: datetime | None = None, deliver=notify.deliver_home
) -> dict:
    """Find a time for friends, colleagues or family. Household members answer from their own schedule;
    guests answer by a private link (returned to the host to share). Everyone sees the same candidate times."""
    now = now or now_utc()
    me, home = _auth(s, token, now)
    circle = fields.get("circle") or "friends"
    duration = fields.get("duration_minutes") or 120
    if not isinstance(duration, int) or isinstance(duration, bool):
        raise HuddleError("bad_gathering", "duration_minutes is a whole number.")
    need = {
        "title": fields.get("title", ""),
        "circle": circle,
        "duration_minutes": duration,
        "slots": _slots_from(fields, duration),
    }
    members = {m.name.lower(): m for m in hm._members(s, home.id)}
    chosen = []
    for name in fields.get("members") or []:
        m = members.get(str(name).strip().lower())
        if m is None:
            raise HuddleError("bad_gathering", f"'{name}' isn't in your household. Invite them as a guest.")
        if m.id != me.id and m not in chosen:
            chosen.append(m)
    guests = fields.get("guests") or []
    people = []
    for m in [me, *chosen]:
        contact = s.get(Contact, "m" + m.id)
        e = {"name": m.name, "channel": "voice"}
        if contact:
            e["email"] = contact.email
        people.append(e)
    for g in guests:
        e = {"name": str(g.get("name", "")).strip(), "channel": "link"}
        if g.get("email"):
            e["email"] = g["email"]
        people.append(e)
    created = rounds.create_round(
        s,
        "when",
        people,
        int(fields.get("deadline_seconds") or 86400),
        need,
        now,
        household_id=home.id,
        detail=f"find a time ({circle})",
    )
    s.add(RoundHome(round_id=created["round_id"], home_id=home.id))
    by_name = {
        p.name: p for p in s.exec(select(Participant).where(Participant.round_id == created["round_id"]))
    }
    for m in [me, *chosen]:
        s.add(ParticipantMember(participant_id=by_name[m.name].id, member_id=m.id))
    hm._log(s, home.id, "gathering_started", now, actor=me.name, detail=circle)
    s.commit()
    for m in chosen:
        hm._notify(s, home, m, "gathering", need["title"], now, deliver)
    out = {p["name"]: p for p in created["participants"]}
    return {
        "round_id": created["round_id"],
        "title": need["title"],
        "slots": need["slots"],
        "my_token": out[me.name]["token"],
        "my_link": out[me.name]["link"],
        "guests": [
            {"name": g["name"], "token": out[g["name"]]["token"], "link": out[g["name"]]["link"]}
            for g in people
            if g["channel"] == "link"
        ],
        "deadline_at": created["deadline_at"],
    }


def _my_participant(s: Session, rnd: Round, me: Member) -> Participant | None:
    for p in s.exec(select(Participant).where(Participant.round_id == rnd.id)):
        if s.get(ParticipantMember, p.id) and s.get(ParticipantMember, p.id).member_id == me.id:
            return p
    return None


def my_gatherings(s: Session, home: Home, me: Member, now: datetime) -> list[dict]:
    """Find-a-times the caller is part of, with suggested answers from their own schedule (private reasons)."""
    items, rules = _items(s, me.id), _rules(s, me.id)
    out = []
    for link in s.exec(select(RoundHome).where(RoundHome.home_id == home.id)):
        rnd = s.get(Round, link.round_id)
        if rnd is None or rnd.mode != "when":
            continue
        rnd = rounds.advance(s, rnd, now)
        p = _my_participant(s, rnd, me)
        if p is None:
            continue
        answers = rounds._answers(s, rnd.id)
        answered = p.id in answers and not answers[p.id].is_default
        need = rnd.need
        from_this = {
            c.id
            for c in s.exec(
                select(Commitment).where(Commitment.member_id == me.id, Commitment.shared_round_id == rnd.id)
            )
        }
        mine = [
            i for i in items if i.id not in from_this
        ]  # this decision's own result isn't a conflict with itself
        slots = []
        for slot in need["slots"]:
            ans, why = sc.suggest_answer(
                mine, rules, datetime.fromisoformat(slot), need["duration_minutes"], need["circle"]
            )
            slots.append(
                {
                    "start": slot,
                    "label": sc.label(datetime.fromisoformat(slot)),
                    "suggested": ans,
                    "reason": why,
                    "given": answers[p.id].data["slots"].get(slot) if answered else None,
                }
            )
        out.append(
            {
                "round_id": rnd.id,
                "title": need["title"],
                "circle": need["circle"],
                "duration_minutes": need["duration_minutes"],
                "state": rnd.state,
                "answered": answered,
                "token": rounds.make_token(p.id, rnd.deadline_at + timedelta(days=1)),
                "answered_count": sum(1 for a in answers.values() if not a.is_default),
                "of": len(list(s.exec(select(Participant).where(Participant.round_id == rnd.id)))),
                "slots": slots,
                "result": rnd.result if rnd.state == "closed" else None,
                "created": rnd.created_at.isoformat(),
            }
        )
    out.sort(key=lambda g: g["created"], reverse=True)
    return out[:6]


def answer_gathering(
    s: Session,
    token: str,
    round_id: str,
    answers: dict | None = None,
    accept_suggestions: bool = False,
    now: datetime | None = None,
) -> dict:
    """Answer a find-a-time from the caller's own schedule (accept the suggestions) or by hand."""
    now = now or now_utc()
    me, home = _auth(s, token, now)
    link = s.get(RoundHome, round_id)
    rnd = s.get(Round, round_id)
    if link is None or link.home_id != home.id or rnd is None or rnd.mode != "when":
        raise HuddleError("not_found", "That find-a-time isn't in your household.", 404)
    p = _my_participant(s, rnd, me)
    if p is None:
        raise HuddleError("not_yours", "You aren't part of that find-a-time.", 403)
    if accept_suggestions:
        items, rules = _items(s, me.id), _rules(s, me.id)
        slots = {
            slot: sc.suggest_answer(
                items, rules, datetime.fromisoformat(slot), rnd.need["duration_minutes"], rnd.need["circle"]
            )[0]
            for slot in rnd.need["slots"]
        }
    else:
        slots = {k: v for k, v in (answers or {}).items() if k in rnd.need["slots"]}
        slots = {k: slots.get(k, "no") for k in rnd.need["slots"]}
    rtoken = rounds.make_token(p.id, rnd.deadline_at + timedelta(days=1))
    out = rounds.submit_answer(s, rtoken, {"consent": True, "slots": slots}, now)
    return {"stored": out["stored"], "round_state": out["round_state"], "answers_given": len(slots)}


def on_round_closed(s: Session, rnd: Round) -> None:
    """When a find-a-time closes, put the agreed time on each attending member's private schedule.
    'Yes' becomes a commitment; 'maybe' becomes a tentative one they confirm. People who said no, or
    never answered, get nothing."""
    if rnd.mode != "when" or not rnd.result or not rnd.result.get("plan"):
        return
    plan, need = rnd.result["plan"], rnd.need
    answers = rounds._answers(s, rnd.id)
    for p in s.exec(select(Participant).where(Participant.round_id == rnd.id)):
        link = s.get(ParticipantMember, p.id)
        a = answers.get(p.id)
        if link is None or a is None or a.is_default:
            continue
        said = a.data["slots"].get(plan["start"], "no")
        if said == "no":
            continue
        exists = s.exec(
            select(Commitment).where(
                Commitment.member_id == link.member_id, Commitment.shared_round_id == rnd.id
            )
        ).first()
        if exists:
            continue
        member = s.get(Member, link.member_id)
        f = {
            "title": need["title"],
            "circle": need["circle"],
            "start": _dt(plan["start"]),
            "end": _dt(plan["end"]),
            "flexibility": "fixed",
            "importance": 2,
            "repeat": "none",
            "until": None,
        }
        _create(s, member, f, rnd.created_at, "active" if said == "yes" else "tentative", rnd.id)
    s.commit()


# ---- calendar files: import, export, subscribe ---------------------------------------------------------------------------
# These read and write a person's own commitments only. A calendar file is not stored: its events become ordinary
# private commitments (owner-only), and the file's own ids are kept so reading the same file again updates them.


def _imported_commitment(s: Session, me: Member, link: CalendarImport | None, uid: str) -> Commitment | None:
    """The commitment an event already became: by its calendar id, or, for a file Huddle exported, by our own id."""
    if link is not None:
        c = s.get(Commitment, link.commitment_id)
        return c if c is not None and c.member_id == me.id else None
    if uid.endswith("@huddle"):
        c = s.get(Commitment, uid.removesuffix("@huddle"))
        return c if c is not None and c.member_id == me.id else None
    return None


def _apply_events(
    s: Session, me: Member, parsed: ical.ParseResult, circle: str, now: datetime, today: str | None = None
) -> dict:
    """Turn parsed calendar events into the person's commitments. Counts only: never the event titles."""
    if circle not in sc.CIRCLES:
        raise HuddleError("bad_commitment", f"circle is one of {sc.CIRCLES}.")
    mapped = {r.uid: r for r in s.exec(select(CalendarImport).where(CalendarImport.member_id == me.id))}
    imported = updated = unchanged = 0
    skipped = parsed.skipped
    reasons = dict(parsed.reasons)
    touched: set[str] = set()
    for ev in parsed.events:
        try:
            f = _normalize(
                {
                    "title": ev.title,
                    "circle": circle,
                    "start": _iso(ev.start),
                    "end": _iso(ev.end),
                    "flexibility": "fixed",  # an event from a calendar is a fixed point until the person says otherwise
                    "repeat": ev.repeat,
                    "until": ev.until,
                },
                _today(now, today),
            )
        except HuddleError:
            skipped += 1
            reasons["invalid"] = reasons.get("invalid", 0) + 1
            continue
        c = _imported_commitment(s, me, mapped.get(ev.uid), ev.uid)
        if c is not None and c.status == "cancelled":
            skipped += 1  # the person removed it here; reading the file again doesn't bring it back
            reasons["removed_here"] = reasons.get("removed_here", 0) + 1
            continue
        if c is None:
            c = _create(s, me, f, now)
            c.skips = list(ev.skips)
            imported += 1
        else:
            same = (c.title, c.start, c.end, c.repeat, c.until, list(c.skips or [])) == (
                f["title"],
                f["start"],
                f["end"],
                f["repeat"],
                f["until"],
                list(ev.skips),
            )
            if same:
                unchanged += 1
            else:
                c.title, c.start, c.end, c.repeat, c.until, c.skips = (
                    f["title"],
                    f["start"],
                    f["end"],
                    f["repeat"],
                    f["until"],
                    list(ev.skips),
                )
                updated += 1
            s.add(c)
        link = mapped.setdefault(ev.uid, CalendarImport(member_id=me.id, uid=ev.uid, commitment_id=c.id))
        link.commitment_id = c.id
        s.add(link)
        touched.add(c.id)
    s.commit()
    td = _today(now, today)
    window = datetime.combine(td, time(0))
    clashes = sum(
        1
        for k in sc.conflicts(_items(s, me.id), window, window + timedelta(days=28), _rules(s, me.id))
        if k.a.id in touched or k.b.id in touched
    )
    notes = []
    if parsed.assumed_zone:
        notes.append(f"{parsed.assumed_zone} events had a time zone; their times were kept as written.")
    if skipped:
        notes.append(ical.describe_skips(reasons))
    if clashes:
        notes.append(f"{clashes} clash{'es' if clashes != 1 else ''} in the next four weeks: see your week.")
    return {
        "imported": imported,
        "updated": updated,
        "unchanged": unchanged,
        "skipped": skipped,
        "skipped_reasons": reasons,
        "clashes": clashes,
        "notes": notes,
    }


def import_calendar(
    s: Session,
    token: str,
    ics: str,
    circle: str = "personal",
    now: datetime | None = None,
    today: str | None = None,
) -> dict:
    """Owner-only: read the events in a calendar (.ics) file the person exported, as their own commitments."""
    now = now or now_utc()
    me, _ = _auth(s, token, now)
    return _apply_events(s, me, ical.parse(ics), circle, now, today)


def export_calendar(
    s: Session, token: str, kind: str = "my_time", now: datetime | None = None, today: str | None = None
) -> dict:
    """Owner-only: the caller's own commitments (`my_time`) or their planned chores this week (`chore_plan`) as
    an .ics file. Chores are all-day entries, because a chore has a due date but not a time."""
    now = now or now_utc()
    me, _ = _auth(s, token, now)
    td = _today(now, today)
    if kind == "my_time":
        original = {
            r.commitment_id: r.uid
            for r in s.exec(select(CalendarImport).where(CalendarImport.member_id == me.id))
        }
        events = []
        for it in _items(s, me.id):
            current = it.end.date() >= td if it.repeat == "none" else it.until is None or it.until >= td
            if it.tentative or not current:
                continue
            ev = ical.event_of(it)
            ev.uid = original.get(it.id, ev.uid)  # a calendar's own event keeps its id, so it isn't duplicated
            events.append(ev)
        return {
            "filename": "huddle-my-time.ics",
            "count": len(events),
            "ics": ical.build(events, f"{me.name} (Huddle)", now),
        }
    if kind == "chore_plan":
        state = hm.get_state(s, token, now)
        week = date.fromisoformat(state["home"]["week"])
        events = []
        for a in state["mine"]["assignments"]:
            if a["status"] != "planned":
                continue
            due = date.fromisoformat(a["due"]) if a["due"] else None
            first = due or week
            last = (due or week + timedelta(days=6)) + timedelta(days=1)  # the end of an all-day event is exclusive
            events.append(
                ical.IcsEvent(
                    uid=f"chore-{a['id']}@huddle",
                    title=f"Chore: {a['title']}" + ("" if due else " (this week)"),
                    start=datetime.combine(first, time(0)),
                    end=datetime.combine(last, time(0)),
                    description=f"About {a['minutes']} minutes.",
                    all_day=True,
                )
            )
        return {
            "filename": f"huddle-chores-{week.isoformat()}.ics",
            "count": len(events),
            "ics": ical.build(events, f"{me.name}: chores (Huddle)", now),
        }
    raise HuddleError("bad_export", "kind is my_time or chore_plan.")


def _feed_url(url: str) -> str:
    """A subscribed address must be https (a webcal:// address is the same thing), with no login in it."""
    parts = urlsplit(str(url).strip())
    if parts.scheme == "webcal":
        parts = parts._replace(scheme="https")
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise HuddleError("bad_feed", "A calendar address starts with https:// (or webcal://) and has no login in it.")
    if parts.port not in (None, 443):
        raise HuddleError("bad_feed", "A calendar address must use the standard https port.")
    return urlunsplit(parts)


def _check_host(host: str, resolve: Callable = socket.getaddrinfo) -> None:
    """Refuse an address that points inside a network (loopback, private, link-local), however it is spelled."""
    try:
        infos = resolve(host, 443)
    except OSError:
        raise HuddleError("feed_failed", "That calendar address couldn't be found.") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise HuddleError("bad_feed", "That address points inside a private network, so it isn't read.")


def _fetch_feed(url: str) -> str:
    """Read a calendar address: https only, a public host, a size cap, a timeout, and no redirect to another
    host. Errors name the class of problem, never the address (it works like a password)."""
    current = _feed_url(url)
    try:
        for _ in range(4):
            _check_host(urlsplit(current).hostname)
            with httpx.stream(
                "GET", current, timeout=10, follow_redirects=False, headers={"Accept": "text/calendar"}
            ) as r:
                if r.is_redirect:
                    nxt = _feed_url(urljoin(current, r.headers.get("location", "")))
                    if urlsplit(nxt).hostname != urlsplit(current).hostname:
                        raise HuddleError("feed_failed", "That calendar address redirects somewhere else, so it isn't read.")
                    current = nxt
                    continue
                if r.status_code != 200:
                    raise HuddleError("feed_failed", f"The calendar address answered with status {r.status_code}.")
                body = bytearray()
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > ical.MAX_BYTES:
                        raise HuddleError("feed_failed", "That calendar is too large (limit 2 MB).")
                return body.decode("utf-8", "replace")
    except httpx.HTTPError as e:
        raise HuddleError("feed_failed", f"The calendar address couldn't be read ({type(e).__name__}).") from None
    raise HuddleError("feed_failed", "That calendar address redirects too many times.")


def subscribe_calendar(
    s: Session,
    token: str,
    url: str | None = None,
    circle: str = "personal",
    now: datetime | None = None,
    today: str | None = None,
    fetch: Callable[[str], str] | None = None,
    refresh: bool = False,
) -> dict:
    """Owner-only: keep the caller's commitments in step with a calendar address (read-only, refreshed hourly).
    No url removes the subscription, or with refresh=True reads the saved address again right now; commitments
    already read stay. The address is never returned."""
    now = now or now_utc()
    me, _ = _auth(s, token, now)
    feed = s.get(CalendarFeed, me.id)
    if refresh and not url:
        return _refresh_now(s, me, feed, now, today, fetch)
    if not url:
        if feed is not None:
            s.delete(feed)
            s.commit()
        return {"subscribed": False}
    clean = _feed_url(url)
    result = _apply_events(s, me, ical.parse((fetch or _fetch_feed)(clean)), circle, now, today)
    feed = feed or CalendarFeed(member_id=me.id, url=clean)
    feed.url, feed.circle, feed.last_fetched, feed.last_status, feed.failures = clean, circle, now, "ok", 0
    s.add(feed)
    s.commit()
    return {"subscribed": True, "last_status": "ok", **result}


def _refresh_now(
    s: Session, me: Member, feed: CalendarFeed | None, now: datetime, today: str | None, fetch
) -> dict:
    """Read the saved address again, ignoring the hourly pause. A failure is recorded (and the error raised), and
    a successful read clears earlier failures, so a feed the agent had given up on is tried again."""
    if feed is None:
        raise HuddleError("no_feed", "You aren't following a calendar address yet.", 409)
    member_id, circle, url = me.id, feed.circle, feed.url
    try:
        result = _apply_events(s, me, ical.parse((fetch or _fetch_feed)(url)), circle, now, today)
    except HuddleError:
        s.rollback()
        feed = s.get(CalendarFeed, member_id)
        feed.last_fetched, feed.last_status, feed.failures = now, "failed", feed.failures + 1
        s.add(feed)
        s.commit()
        raise
    feed = s.get(CalendarFeed, member_id)
    feed.last_fetched, feed.last_status, feed.failures = now, "ok", 0
    s.add(feed)
    s.commit()
    return {"subscribed": True, "last_status": "ok", **result}


def feed_view(s: Session, member_id: str) -> dict:
    feed = s.get(CalendarFeed, member_id)
    if feed is None:
        return {"subscribed": False}
    return {
        "subscribed": True,
        "circle": feed.circle,
        "last_status": feed.last_status,
        "last_fetched": feed.last_fetched.isoformat(timespec="minutes") if feed.last_fetched else None,
    }


# ---- reminders: starting soon, and a Sunday digest -------------------------------------------------------------------


def reminder_view(s: Session, member_id: str) -> dict:
    p = s.get(ReminderPref, member_id)
    return {
        "kinds": list(p.kinds or []) if p else [],
        "quiet_start": p.quiet_start if p else None,
        "quiet_end": p.quiet_end if p else None,
        "utc_offset_minutes": p.utc_offset_minutes if p else 0,
    }


def set_reminder_prefs(s: Session, token: str, changes: dict, now: datetime | None = None) -> dict:
    """Owner-only: which reminders the caller wants (starting_soon, digest), when not to send them, and their own
    offset from the server clock (their times are floating, so this is how 'in 30 minutes' is worked out)."""
    now = now or now_utc()
    me, _ = _auth(s, token, now)
    p = s.get(ReminderPref, me.id) or ReminderPref(member_id=me.id)
    if "kinds" in changes:
        kinds = changes["kinds"]
        if not isinstance(kinds, list) or any(k not in REMINDER_KINDS for k in kinds):
            raise HuddleError("bad_reminders", f"kinds is a list of {REMINDER_KINDS}.")
        p.kinds = sorted(set(kinds))
    for key in ("quiet_start", "quiet_end"):
        if key in changes:
            v = changes[key]
            if v is not None:
                try:
                    _t(str(v))
                except ValueError:
                    raise HuddleError("bad_reminders", f"{key} is a time like 22:00.") from None
            setattr(p, key, v)
    if bool(p.quiet_start) != bool(p.quiet_end):
        raise HuddleError("bad_reminders", "Quiet hours need both a start and an end.")
    if "utc_offset_minutes" in changes:
        off = changes["utc_offset_minutes"]
        if not isinstance(off, int) or isinstance(off, bool) or not -14 * 60 <= off <= 14 * 60:
            raise HuddleError("bad_reminders", "utc_offset_minutes is a whole number between -840 and 840.")
        p.utc_offset_minutes = off
    p.updated_at = now
    s.add(p)
    s.commit()
    return reminder_view(s, me.id)


def _in_quiet(local: time, start: str | None, end: str | None) -> bool:
    if not start or not end:
        return False
    a, b = _t(start), _t(end)
    return a <= local < b if a <= b else local >= a or local < b


def _starting_soon(items: list[sc.Item], local: datetime) -> list[sc.Item]:
    """The caller's own occurrences that start within STARTING_SOON of `local` and haven't started. Used by both
    the reminder that is sent and the banner on the page, so the two never disagree."""
    return [o for o in sc.expand([i for i in items if not i.tentative], local, local + STARTING_SOON) if o.start >= local]


def _due_now(s: Session, me: Member, now: datetime) -> list[dict]:
    """What the 'starting soon' banner shows right now: empty unless the person turned that reminder on, and
    empty during their quiet hours. Only their own items."""
    pref = s.get(ReminderPref, me.id)
    if pref is None or "starting_soon" not in (pref.kinds or []):
        return []
    local = now + timedelta(minutes=pref.utc_offset_minutes)
    if _in_quiet(local.time(), pref.quiet_start, pref.quiet_end):
        return []
    return [
        {
            "id": o.id,
            "title": o.title,
            "start": _iso(o.start),
            "minutes_away": max(0, -(-int((o.start - local).total_seconds()) // 60)),  # rounded up
        }
        for o in _starting_soon(_items(s, me.id), local)
    ]


def _sent(s: Session, home_id: str, kind: str, key: str) -> bool:
    return (
        s.exec(
            select(HomeEvent).where(HomeEvent.home_id == home_id, HomeEvent.kind == kind, HomeEvent.detail == key)
        ).first()
        is not None
    )


def _digest_text(s: Session, home: Home, me: Member, week: date, now: datetime) -> str:
    """Counts and the person's own items for the coming week. Nothing about anyone else."""
    start = datetime.combine(week, time(0))
    items, rules = [i for i in _items(s, me.id) if not i.tentative], _rules(s, me.id)
    end = start + timedelta(days=7)
    plans = len(sc.expand(items, start, end))
    clashes = len(sc.conflicts(items, start, end, rules))
    chores = sum(1 for a in hm._week_rows(s, home.id, week) if a.member_id == me.id and a.status == "planned")
    waiting = sum(1 for d in hm._decisions(s, home, me, now) if d["state"] != "closed" and not d["answered"])
    parts = [
        f"{plans} commitment{'s' if plans != 1 else ''}" + (f" ({clashes} clash{'es' if clashes != 1 else ''})" if clashes else ""),
        f"{chores} chore{'s' if chores != 1 else ''} planned" if chores else "",
        f"{waiting} decision{'s' if waiting != 1 else ''} waiting for your answer" if waiting else "",
    ]
    return ", ".join(p for p in parts if p) if plans or chores or waiting else "nothing planned yet"


def _remind(s: Session, now: datetime, deliver) -> list[tuple[str, str]]:
    did: list[tuple[str, str]] = []
    for pref in list(s.exec(select(ReminderPref))):
        member = s.get(Member, pref.member_id)
        home = s.get(Home, member.home_id) if member else None
        kinds = list(pref.kinds or [])
        if home is None or not kinds:
            continue
        local = now + timedelta(minutes=pref.utc_offset_minutes)
        if _in_quiet(local.time(), pref.quiet_start, pref.quiet_end):
            continue
        if "starting_soon" in kinds:
            for o in _starting_soon(_items(s, member.id), local):
                key = f"c{o.id}:{o.start.isoformat(timespec='minutes')}"
                if _sent(s, home.id, "starting_soon", key):
                    continue
                hm._notify(s, home, member, "starting_soon", f"{o.title} at {o.start.strftime('%H:%M')}", now, deliver)
                hm._log(s, home.id, "starting_soon", now, detail=key)
                did.append(("starting_soon", o.title))
        if "digest" in kinds and local.weekday() == DIGEST_DAY and local.time() >= DIGEST_FROM:
            week = sc.week_start(local.date()) + timedelta(days=7)
            key = f"m{member.id}:{week.isoformat()}"
            if not _sent(s, home.id, "digest", key):
                hm._notify(s, home, member, "digest", _digest_text(s, home, member, week, now), now, deliver)
                hm._log(s, home.id, "digest", now, detail=key)
                did.append(("digest", home.name))
    return did


def _refresh_feeds(s: Session, now: datetime, fetch: Callable[[str], str] | None) -> list[tuple[str, str]]:
    did: list[tuple[str, str]] = []
    for feed in list(s.exec(select(CalendarFeed))):
        if feed.failures >= FEED_GIVE_UP_AFTER or (feed.last_fetched and now - feed.last_fetched < FEED_EVERY):
            continue
        member_id, circle, url = feed.member_id, feed.circle, feed.url
        me = s.get(Member, member_id)
        ok = False
        if me is not None:
            try:
                _apply_events(s, me, ical.parse((fetch or _fetch_feed)(url)), circle, now)
                ok = True
            except HuddleError:
                s.rollback()
        feed = s.get(CalendarFeed, member_id)
        feed.last_fetched, feed.last_status = now, "ok" if ok else "failed"
        feed.failures = 0 if ok else feed.failures + 1
        s.add(feed)
        s.commit()
        did.append(("feed", feed.last_status))
    return did


def tick(
    s: Session,
    now: datetime | None = None,
    deliver=notify.deliver_home,
    fetch: Callable[[str], str] | None = None,
) -> list[tuple[str, str]]:
    """Run by the scheduler. Reads subscribed calendars (at most hourly), sends 'starting soon' reminders and the
    Sunday digest to the people who turned them on. Returns [(kind, detail)] for what it did."""
    now = now or now_utc()
    did = _refresh_feeds(s, now, fetch) + _remind(s, now, deliver)
    s.commit()
    return did


rounds.CLOSE_HOOKS.append(on_round_closed)
