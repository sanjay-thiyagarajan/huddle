"""Household service: a persistent home where members plan chores week after week.

Private to each member (owner-only, never in any group view): weekly availability, preferences, skills,
exemptions, decline reasons, how a week felt, and who a chore was offered to. Public to the household:
the chores, who owns what, and an aggregate fairness report. Chores can be added any time (ad hoc: the
agent asks the best-fit person, who can accept or decline, and it asks the next if they decline) or
pre-planned with a due date or a recurrence. The agent plans each week and keeps a rolling ledger.
"""

import secrets
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from .. import config, notify
from ..db import Assignment, Chore, Contact, Home, HomeEvent, HomePlan, Member, MemberProfile, WeekFelt
from . import chores as ch
from .rounds import HuddleError, _parse_token, make_token, now_utc

TOKEN_DAYS = 120
REMIND_AFTER = timedelta(hours=12)
EXPIRE_AFTER = timedelta(hours=24)
DECLINE_REASONS = ("cannot", "busy", "prefer_not", "other")
EXEMPT_CAP, EXEMPT_WINDOW_WEEKS = 2, 8
HISTORY_WEEKS = 8
PUBLIC_STATUS = {
    "unassigned": "open",
    "proposed": "pending",
    "planned": "planned",
    "done": "done",
    "skipped": "skipped",
}


# ---- small helpers -------------------------------------------------------------------------------------


def week_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _today(now: datetime | None) -> date:
    return (now or now_utc()).date()


def _log(
    s: Session, home_id: str, kind: str, now: datetime, actor: str | None = None, detail: str | None = None
) -> None:
    s.add(HomeEvent(home_id=home_id, at=now, kind=kind, actor=actor, detail=detail))


def _auth(s: Session, token: str, now: datetime) -> tuple[Member, Home]:
    pid = _parse_token(token, now)
    member = s.get(Member, pid[1:]) if pid.startswith("m") else None
    if member is None:
        raise HuddleError("bad_token", "Invalid token.", 401)
    return member, s.get(Home, member.home_id)


def _members(s: Session, home_id: str) -> list[Member]:
    return sorted(s.exec(select(Member).where(Member.home_id == home_id)), key=lambda m: m.name.lower())


def _profile(s: Session, member_id: str) -> MemberProfile:
    return s.get(MemberProfile, member_id) or MemberProfile(member_id=member_id)


def _chore_rows(s: Session, home_id: str) -> dict[str, Chore]:
    return {c.id: c for c in s.exec(select(Chore).where(Chore.home_id == home_id))}


def _week_rows(s: Session, home_id: str, week: date) -> list[Assignment]:
    return list(
        s.exec(
            select(Assignment)
            .where(Assignment.home_id == home_id, Assignment.week == week.isoformat())
            .order_by(Assignment.id)
        )
    )


def _active_in_week(c: Chore, week: date) -> bool:
    if c.status != "active":
        return False
    start = date.fromisoformat(c.start_week) if c.start_week else week
    if c.cadence == "once":
        return date.fromisoformat(c.due) <= week + timedelta(days=6) if c.due else True
    if week < start:
        return False
    if c.cadence == "biweekly":
        return ((week - start).days // 7) % 2 == 0
    if c.cadence == "monthly":
        return 1 <= week.day <= 7
    return True  # daily, weekly


def _minutes_week(c: Chore) -> int:
    return c.minutes * ch.CADENCES[c.cadence]


def _chore_in(c: Chore, minutes: int | None = None, people: int | None = None) -> ch.ChoreIn:
    return ch.ChoreIn(
        c.id,
        c.title,
        c.category,
        minutes if minutes is not None else _minutes_week(c),
        c.heaviness,
        c.mental,
        people if people is not None else c.people_needed,
    )


def _burden(c: Chore, minutes: int) -> float:
    return ch.burden_of(minutes, c.heaviness, c.mental)


def _is_exempt(p: MemberProfile, week: date) -> bool:
    return week.isoformat() in (p.exempt_weeks or [])


def _member_in(s: Session, m: Member, week: date, prior_dev: float = 0.0) -> ch.MemberIn:
    p = _profile(s, m.id)
    felt = s.exec(
        select(WeekFelt).where(
            WeekFelt.member_id == m.id, WeekFelt.week == (week - timedelta(days=7)).isoformat()
        )
    ).first()
    return ch.MemberIn(
        m.id,
        p.availability,
        dict(p.prefs or {}),
        dict(p.skills or {}),
        list(p.learn or []),
        list(p.keywords or []),
        _is_exempt(p, week),
        felt.score if felt else None,
        prior_dev,
    )


def _history(s: Session, home_id: str, week: date, chores: dict[str, Chore]) -> tuple[dict, dict]:
    """(prior_dev per member, last_owner per chore): what recent weeks say about who carried what."""
    prior: dict[str, float] = {}
    for k in range(1, HISTORY_WEEKS + 1):
        w = week - timedelta(days=7 * k)
        plan = s.exec(
            select(HomePlan).where(HomePlan.home_id == home_id, HomePlan.week == w.isoformat())
        ).first()
        if not plan:
            continue
        carried: dict[str, float] = {}
        for a in _week_rows(s, home_id, w):
            if a.status == "done" and a.member_id and a.chore_id in chores:  # past weeks count what was DONE
                carried[a.member_id] = carried.get(a.member_id, 0.0) + _burden(chores[a.chore_id], a.minutes)
        total = sum(carried.values())
        if total <= 0:
            continue
        for mid, share in plan.shares.items():
            prior[mid] = prior.get(mid, 0.0) + carried.get(mid, 0.0) - share * total
    last: dict[str, set] = {}
    for a in _week_rows(s, home_id, week - timedelta(days=7)):
        if a.member_id and a.status in ("planned", "done"):
            last.setdefault(a.chore_id, set()).add(a.member_id)
    return prior, last


def _loads(
    s: Session, rows: list[Assignment], chores: dict[str, Chore], skip: int | None = None
) -> tuple[dict, dict]:
    """(burden, minutes) per member from assigned, done and pending-offer work this week."""
    burden: dict[str, float] = {}
    minutes: dict[str, int] = {}
    for a in rows:
        if a.id == skip or a.chore_id not in chores:
            continue
        owner = (
            a.member_id
            if a.status in ("planned", "done")
            else a.proposed_to
            if a.status == "proposed"
            else None
        )
        if owner:
            burden[owner] = burden.get(owner, 0.0) + _burden(chores[a.chore_id], a.minutes)
            minutes[owner] = minutes.get(owner, 0) + a.minutes
    return burden, minutes


def _notify(s: Session, home: Home, member: Member, kind: str, title: str, now: datetime, deliver) -> None:
    contact = s.get(Contact, "m" + member.id)
    link = f"{config.PUBLIC_URL}/h/{make_token('m' + member.id, now + timedelta(days=TOKEN_DAYS))}"
    deliveries = deliver(
        name=member.name, email=contact.email if contact else None, kind=kind, title=title, link=link
    )
    _log(
        s,
        home.id,
        "notified",
        now,
        actor=member.name,
        detail=f"{kind}: " + ", ".join(f"{d.channel} {d.status}" for d in deliveries),
    )


# ---- creating a household --------------------------------------------------------------------------------


def create_household(s: Session, name: str, members: list[dict], now: datetime | None = None) -> dict:
    now = now or now_utc()
    name = (name or "").strip()
    if not 1 <= len(name) <= 60:
        raise HuddleError("bad_home", "Give the household a name (up to 60 characters).")
    names = [str(m.get("name", "")).strip() for m in members]
    if (
        not 2 <= len(members) <= 6
        or any(not n for n in names)
        or len({n.lower() for n in names}) != len(names)
    ):
        raise HuddleError("bad_members", "A household needs 2 to 6 people with unique names.")
    for m in members:
        if m.get("email") and not notify.EMAIL_RE.match(str(m["email"]).strip()):
            raise HuddleError("bad_members", "That email address doesn't look right.")
    home = Home(id=secrets.token_hex(4), name=name, created_at=now)
    s.add(home)
    out = []
    for i, (m, n) in enumerate(zip(members, names)):
        mem = Member(id=secrets.token_hex(4), home_id=home.id, name=n, is_admin=(i == 0))
        s.add(mem)
        if m.get("email"):
            s.add(Contact(participant_id="m" + mem.id, email=str(m["email"]).strip()))
        token = make_token("m" + mem.id, now + timedelta(days=TOKEN_DAYS))
        out.append({"name": n, "is_admin": mem.is_admin, "token": token, "link": f"/h/{token}"})
    _log(s, home.id, "created", now, actor=names[0], detail=f"{len(names)} members")
    s.commit()
    return {"home_id": home.id, "name": name, "members": out}


def add_member(
    s: Session, token: str, name: str, email: str | None = None, now: datetime | None = None
) -> dict:
    now = now or now_utc()
    me, home = _auth(s, token, now)
    if not me.is_admin:
        raise HuddleError("admin_only", "Only the household admin can add people.", 403)
    existing = _members(s, home.id)
    name = (name or "").strip()
    if not name or name.lower() in {m.name.lower() for m in existing} or len(existing) >= 6:
        raise HuddleError("bad_members", "Names must be unique and a household has at most 6 people.")
    if email and not notify.EMAIL_RE.match(email.strip()):
        raise HuddleError("bad_members", "That email address doesn't look right.")
    mem = Member(id=secrets.token_hex(4), home_id=home.id, name=name)
    s.add(mem)
    if email:
        s.add(Contact(participant_id="m" + mem.id, email=email.strip()))
    _log(s, home.id, "member_added", now, actor=me.name, detail=name)
    s.commit()
    tok = make_token("m" + mem.id, now + timedelta(days=TOKEN_DAYS))
    return {"name": name, "token": tok, "link": f"/h/{tok}"}


# ---- private profile -------------------------------------------------------------------------------------


def set_profile(s: Session, token: str, changes: dict, now: datetime | None = None) -> dict:
    """Owner-only: availability, preferences, skills, things they'd like to learn, and exemption."""
    now = now or now_utc()
    me, home = _auth(s, token, now)
    p = _profile(s, me.id)
    if "availability" in changes:
        a = changes["availability"]
        if not isinstance(a, int) or isinstance(a, bool) or not 0 <= a <= 2400:
            raise HuddleError("bad_profile", "availability is whole minutes of chores per week, 0 to 2400.")
        p.availability = a
    if "prefs" in changes:
        prefs = changes["prefs"]
        if not isinstance(prefs, dict) or any(
            k not in ch.CATEGORIES or v not in ch.PREF_VALUES for k, v in prefs.items()
        ):
            raise HuddleError("bad_profile", f"prefs map a category to one of {ch.PREF_VALUES}.")
        p.prefs = {k: v for k, v in prefs.items() if v != "ok"}
    if "skills" in changes:
        skills = changes["skills"]
        if not isinstance(skills, dict) or any(
            k not in ch.CATEGORIES or v not in (0, 1, 2) for k, v in skills.items()
        ):
            raise HuddleError("bad_profile", "skills map a category to 0 (none), 1 (ok) or 2 (good).")
        p.skills = dict(skills)
    if "learn" in changes:
        learn = changes["learn"]
        if not isinstance(learn, list) or any(k not in ch.CATEGORIES for k in learn):
            raise HuddleError("bad_profile", "learn is a list of categories.")
        p.learn = list(dict.fromkeys(learn))
    if "keywords" in changes:
        kw = changes["keywords"]
        if (
            not isinstance(kw, list)
            or len(kw) > 8
            or any(not isinstance(k, str) or not 1 <= len(k) <= 30 for k in kw)
        ):
            raise HuddleError(
                "bad_profile", "keywords are up to 8 short words, like 'plumbing' or 'the car'."
            )
        p.keywords = [k.strip() for k in kw]
    if "exempt_this_week" in changes:
        wk = week_of(_today(now)).isoformat()
        weeks = [
            w
            for w in (p.exempt_weeks or [])
            if w >= (week_of(_today(now)) - timedelta(days=7 * (EXEMPT_WINDOW_WEEKS - 1))).isoformat()
        ]
        if changes["exempt_this_week"]:
            if wk not in weeks:
                if len(weeks) >= EXEMPT_CAP:
                    raise HuddleError(
                        "exemption_limit",
                        f"Exemptions are limited to {EXEMPT_CAP} weeks in any {EXEMPT_WINDOW_WEEKS}, so the "
                        "load stays fair. Lower your availability for this week instead.",
                    )
                weeks.append(wk)
        else:
            weeks = [w for w in weeks if w != wk]
        p.exempt_weeks = weeks
    p.updated_at = now
    s.add(p)
    _log(s, home.id, "profile_updated", now, actor=None)  # no actor, no content: it is private
    s.commit()
    return _profile_view(p, week_of(_today(now)))


def _profile_view(p: MemberProfile, week: date) -> dict:
    return {
        "availability": p.availability,
        "prefs": dict(p.prefs or {}),
        "skills": dict(p.skills or {}),
        "learn": list(p.learn or []),
        "keywords": list(p.keywords or []),
        "exempt_this_week": _is_exempt(p, week),
        "exempt_weeks_used": len(p.exempt_weeks or []),
    }


# ---- chores: ad hoc or pre-planned -------------------------------------------------------------------------


def add_chore(
    s: Session, token: str, fields: dict, now: datetime | None = None, deliver=notify.deliver_home
) -> dict:
    """Add a chore any time. If this week already has a plan, a chore that belongs to it is handled now:
    the agent asks the best-fit person, who can accept or decline. Otherwise (no plan yet, or a future due
    date, or a recurrence for later) the chore is simply held until its week is planned (pre-planned)."""
    now = now or now_utc()
    me, home = _auth(s, token, now)
    title = str(fields.get("title", "")).strip()
    if not 1 <= len(title) <= 80:
        raise HuddleError("bad_chore", "A chore needs a title (up to 80 characters).")
    category = fields.get("category") or "other"
    if category not in ch.CATEGORIES:
        raise HuddleError("bad_chore", f"category must be one of {ch.CATEGORIES}.")
    cadence = fields.get("cadence") or "once"
    if cadence not in ch.CADENCES:
        raise HuddleError("bad_chore", f"cadence must be one of {tuple(ch.CADENCES)}.")
    minutes = fields.get("minutes")
    estimated = minutes is None
    minutes = ch.DEFAULT_MINUTES[category] if minutes is None else minutes
    if not isinstance(minutes, int) or isinstance(minutes, bool) or not 5 <= minutes <= 480:
        raise HuddleError("bad_chore", "minutes is 5 to 480 for one occurrence.")
    heaviness = fields.get("heaviness") or ch.DEFAULT_HEAVINESS[category]
    if heaviness not in (1, 2, 3):
        raise HuddleError("bad_chore", "heaviness is 1 (light), 2 or 3 (heavy).")
    need = fields.get("people_needed") or 1
    n_members = len(_members(s, home.id))
    if not isinstance(need, int) or not 1 <= need <= min(3, n_members):
        raise HuddleError("bad_chore", "people_needed is 1 to 3 and no more than the household size.")
    due = fields.get("due")
    if due:
        try:
            date.fromisoformat(str(due))
        except ValueError:
            raise HuddleError("bad_chore", "due is a date like 2026-10-15.") from None
    mental = bool(fields.get("mental", category in ch.MENTAL_CATEGORIES))
    week = week_of(_today(now))
    c = Chore(
        id=secrets.token_hex(4),
        home_id=home.id,
        title=title,
        category=category,
        minutes=minutes,
        cadence=cadence,
        due=str(due) if due else None,
        heaviness=heaviness,
        people_needed=need,
        mental=mental,
        created_by=me.id,
        created_at=now,
        start_week=week.isoformat(),
        estimated=estimated,
    )
    s.add(c)
    _log(s, home.id, "chore_added", now, actor=me.name, detail=title)
    s.flush()
    outcome = "held"  # pre-planned: kept for the week it belongs to
    if _active_in_week(c, week):
        has_plan = s.exec(
            select(HomePlan).where(HomePlan.home_id == home.id, HomePlan.week == week.isoformat())
        ).first()
        if has_plan:
            for slot in range(need):
                row = Assignment(
                    home_id=home.id,
                    chore_id=c.id,
                    week=week.isoformat(),
                    slot=slot,
                    minutes=_minutes_week(c),
                    source="adhoc",
                )
                s.add(row)
                s.flush()
                _propose(s, home, row, c, week, now, deliver)
            outcome = "asked"
    s.commit()
    mine = [
        a
        for a in _week_rows(s, home.id, week)
        if a.chore_id == c.id and a.proposed_to == me.id and a.status == "proposed"
    ]
    return {"chore": _chore_view(c), "outcome": outcome, "proposed_to_you": [a.id for a in mine]}


def _chore_view(c: Chore) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "category": c.category,
        "minutes": c.minutes,
        "cadence": c.cadence,
        "due": c.due,
        "heaviness": c.heaviness,
        "people_needed": c.people_needed,
        "mental": c.mental,
        "status": c.status,
        "estimated": c.estimated,
    }


# ---- planning ---------------------------------------------------------------------------------------------


def plan_week(
    s: Session,
    token: str,
    week: str | None = None,
    replan: bool = False,
    now: datetime | None = None,
    deliver=notify.deliver_home,
) -> dict:
    now = now or now_utc()
    me, home = _auth(s, token, now)
    wk = date.fromisoformat(week) if week else week_of(_today(now))
    if wk.weekday() != 0:
        raise HuddleError("bad_week", "A week starts on a Monday.")
    if replan and not me.is_admin:
        raise HuddleError("admin_only", "Only the household admin can redo a plan that already exists.", 403)
    _plan_core(s, home, wk, replan, now, deliver, actor=me.name)
    s.commit()
    return get_state(s, token, now)


def _plan_core(
    s: Session, home: Home, week: date, replan: bool, now: datetime, deliver, actor: str | None
) -> None:
    chores = _chore_rows(s, home.id)
    rows = _week_rows(s, home.id, week)
    for a in rows:  # an open slot is always re-planned; replan also resets everything not yet done
        if a.status == "unassigned" or (replan and a.status in ("planned", "proposed")):
            s.delete(a)
    s.flush()
    rows = _week_rows(s, home.id, week)
    # a one-off chore left unfinished in an earlier week is retired there and planned afresh in this one
    for c in chores.values():
        if c.cadence == "once" and c.status == "active":
            for old in s.exec(
                select(Assignment).where(Assignment.chore_id == c.id, Assignment.week < week.isoformat())
            ):
                if old.status in ("planned", "proposed", "unassigned"):
                    old.status, old.proposed_to = "skipped", None
                    s.add(old)
    active = [c for c in chores.values() if _active_in_week(c, week)]
    held: dict[str, int] = {}
    for a in rows:
        held[a.chore_id] = held.get(a.chore_id, 0) + 1
    members = _members(s, home.id)
    prior, last_owner = _history(s, home.id, week, chores)
    min_in = [_member_in(s, m, week, prior.get(m.id, 0.0)) for m in members]
    base_load, base_min = _loads(s, rows, chores)
    to_plan = []
    for c in sorted(active, key=lambda c: c.id):
        missing = c.people_needed - held.get(c.id, 0)
        if missing > 0:
            to_plan.append(_chore_in(c, people=missing))
    out = ch.plan(to_plan, min_in, last_owner, prior, base_load=base_load, base_minutes=base_min)
    by_id = {c.id: c for c in to_plan}
    for ci in to_plan:
        owners = out.assign.get(ci.id, [])
        for k in range(ci.people_needed):
            if k < len(owners):
                s.add(
                    Assignment(
                        home_id=home.id,
                        chore_id=ci.id,
                        week=week.isoformat(),
                        slot=held.get(ci.id, 0) + k,
                        member_id=owners[k],
                        status="planned",
                        minutes=by_id[ci.id].minutes,
                        why=out.why.get((ci.id, owners[k])),
                        source="plan",
                    )
                )
            else:
                s.add(
                    Assignment(
                        home_id=home.id,
                        chore_id=ci.id,
                        week=week.isoformat(),
                        slot=held.get(ci.id, 0) + k,
                        status="unassigned",
                        minutes=by_id[ci.id].minutes,
                        source="plan",
                    )
                )
    report = dict(out.report)
    report["unstaffed"] = [by_id[i].title for i in report["unstaffed"] if i in by_id]
    report["exempt_count"] = sum(1 for m in min_in if m.exempt)
    existing = s.exec(
        select(HomePlan).where(HomePlan.home_id == home.id, HomePlan.week == week.isoformat())
    ).first()
    if existing:
        s.delete(existing)
        s.flush()
    s.add(
        HomePlan(
            home_id=home.id,
            week=week.isoformat(),
            shares=out.shares if out.shares else (existing.shares if existing else {}),
            report=report,
            created_at=now,
        )
    )
    _log(
        s,
        home.id,
        "planned",
        now,
        actor=actor,
        detail=f"week of {week.isoformat()}" + (", redone" if replan else ""),
    )
    s.flush()
    for m in members:
        _notify(s, home, m, "plan", "", now, deliver)


def _propose(s: Session, home: Home, a: Assignment, chore: Chore, week: date, now: datetime, deliver) -> None:
    """Ask the best-fit person to take this chore, or mark it open if nobody can."""
    chores = _chore_rows(s, home.id)
    rows = _week_rows(s, home.id, week)
    members = _members(s, home.id)
    prior, last = _history(s, home.id, week, chores)
    min_in = [_member_in(s, m, week, prior.get(m.id, 0.0)) for m in members]
    burden, minutes = _loads(s, rows, chores, skip=a.id)
    plan = s.exec(
        select(HomePlan).where(HomePlan.home_id == home.id, HomePlan.week == week.isoformat())
    ).first()
    exclude = {e["member"] for e in (a.excluded or [])}
    exclude |= {x.member_id for x in rows if x.chore_id == a.chore_id and x.id != a.id and x.member_id}
    exclude |= {x.proposed_to for x in rows if x.chore_id == a.chore_id and x.id != a.id and x.proposed_to}
    ranked = ch.rank_candidates(
        _chore_in(chore, minutes=a.minutes, people=1),
        min_in,
        burden,
        plan.shares if plan else {},
        sum(burden.values()),
        exclude,
        last.get(chore.id, set()),
        minutes,
    )
    if ranked:
        a.status, a.proposed_to, a.proposed_at, a.member_id = "proposed", ranked[0], now, None
        _log(s, home.id, "asking", now, detail=chore.title)  # never says who
        s.add(a)
        s.flush()
        target = next(m for m in members if m.id == ranked[0])
        _notify(s, home, target, "proposal", chore.title, now, deliver)
    else:
        a.status, a.proposed_to, a.member_id = "unassigned", None, None
        _log(s, home.id, "needs_attention", now, detail=chore.title)
        s.add(a)
        s.flush()


def respond(
    s: Session,
    token: str,
    assignment_id: int,
    accept: bool,
    reason: str | None = None,
    now: datetime | None = None,
    deliver=notify.deliver_home,
) -> dict:
    now = now or now_utc()
    me, home = _auth(s, token, now)
    a = s.get(Assignment, assignment_id)
    if a is None or a.home_id != home.id or a.status != "proposed" or a.proposed_to != me.id:
        raise HuddleError("not_yours", "That request isn't waiting on you.", 403)
    chore = s.get(Chore, a.chore_id)
    week = date.fromisoformat(a.week)
    if accept:
        mi = _member_in(s, me, week)
        a.status, a.member_id, a.proposed_to = "planned", me.id, None
        a.why = ch.pref_score(mi, _chore_in(chore, minutes=a.minutes, people=1))[1]
        _log(s, home.id, "accepted", now, actor=me.name, detail=chore.title)
        s.add(a)
    else:
        if reason is not None and reason not in DECLINE_REASONS:
            raise HuddleError("bad_reason", f"reason is one of {DECLINE_REASONS}.")
        a.excluded = [
            *(a.excluded or []),
            {"member": me.id, "reason": reason or "other", "at": now.isoformat()},
        ]
        a.proposed_to = None
        _log(s, home.id, "reassigning", now, detail=chore.title)  # no name, no reason
        _propose(s, home, a, chore, week, now, deliver)
    s.commit()
    return get_state(s, token, now)


def hand_back(
    s: Session,
    token: str,
    assignment_id: int,
    reason: str | None = None,
    now: datetime | None = None,
    deliver=notify.deliver_home,
) -> dict:
    """The owner can't do it after all: the agent asks the next best person (never back to them)."""
    now = now or now_utc()
    me, home = _auth(s, token, now)
    a = s.get(Assignment, assignment_id)
    if a is None or a.home_id != home.id or a.member_id != me.id or a.status != "planned":
        raise HuddleError("not_yours", "You can only hand back a chore you own that isn't done.", 403)
    if reason is not None and reason not in (*DECLINE_REASONS, "handed_back"):
        raise HuddleError("bad_reason", f"reason is one of {DECLINE_REASONS}.")
    chore = s.get(Chore, a.chore_id)
    a.excluded = [
        *(a.excluded or []),
        {"member": me.id, "reason": reason or "handed_back", "at": now.isoformat()},
    ]
    a.member_id, a.source = None, "swap"
    _log(s, home.id, "handed_back", now, detail=chore.title)  # no name
    _propose(s, home, a, chore, date.fromisoformat(a.week), now, deliver)
    s.commit()
    return get_state(s, token, now)


def complete(s: Session, token: str, assignment_id: int, now: datetime | None = None) -> dict:
    now = now or now_utc()
    me, home = _auth(s, token, now)
    a = s.get(Assignment, assignment_id)
    if a is None or a.home_id != home.id or a.member_id != me.id or a.status != "planned":
        raise HuddleError("not_yours", "Only the owner can mark a planned chore done.", 403)
    a.status, a.completed_at = "done", now
    s.add(a)
    chore = s.get(Chore, a.chore_id)
    if chore.cadence == "once":
        rows = [x for x in s.exec(select(Assignment).where(Assignment.chore_id == chore.id))]
        if all(x.status == "done" for x in rows) and len(rows) >= chore.people_needed:
            chore.status = "done"
            s.add(chore)
    _log(s, home.id, "done", now, actor=me.name, detail=chore.title)
    s.commit()
    return get_state(s, token, now)


def checkin_week(s: Session, token: str, score: int, now: datetime | None = None) -> dict:
    """Private: how did this week feel? 1 (far too heavy) to 5 (comfortable). Feeds next week's share."""
    now = now or now_utc()
    me, home = _auth(s, token, now)
    if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
        raise HuddleError("invalid_score", "score must be a whole number from 1 to 5.")
    wk = week_of(_today(now)).isoformat()
    row = s.exec(select(WeekFelt).where(WeekFelt.member_id == me.id, WeekFelt.week == wk)).first()
    if row:
        row.score = score
    else:
        row = WeekFelt(member_id=me.id, week=wk, score=score)
    s.add(row)
    s.commit()
    return {"stored": True}


# ---- reminders, weekly auto-plan, proposal expiry ----------------------------------------------------


def tick(s: Session, now: datetime | None = None, deliver=notify.deliver_home) -> list[tuple[str, str]]:
    """Run by the scheduler. Plans each household's week when it has no plan, nudges and then re-asks
    unanswered offers, and reminds owners of chores due soon. Returns [(kind, detail)] for what it did."""
    now = now or now_utc()
    did: list[tuple[str, str]] = []
    for home in list(s.exec(select(Home))):
        week = week_of(_today(now))
        chores = _chore_rows(s, home.id)
        has_plan = s.exec(
            select(HomePlan).where(HomePlan.home_id == home.id, HomePlan.week == week.isoformat())
        ).first()
        had_prev = s.exec(
            select(HomePlan).where(
                HomePlan.home_id == home.id, HomePlan.week == (week - timedelta(days=7)).isoformat()
            )
        ).first()
        if (
            home.auto_plan
            and not has_plan
            and had_prev
            and any(_active_in_week(c, week) for c in chores.values())
        ):
            _plan_core(s, home, week, False, now, deliver, actor=None)
            did.append(("auto_plan", home.name))
        members = {m.id: m for m in _members(s, home.id)}
        for a in _week_rows(s, home.id, week):
            chore = chores.get(a.chore_id)
            if chore is None:
                continue
            if a.status == "proposed" and a.proposed_at:
                age = now - a.proposed_at
                events = [
                    e
                    for e in s.exec(
                        select(HomeEvent).where(HomeEvent.home_id == home.id, HomeEvent.kind == "nudged")
                    )
                    if e.detail == f"a{a.id}:{a.proposed_to}"
                ]
                if age >= EXPIRE_AFTER:  # no answer: treated as a pass, and the next person is asked
                    a.excluded = [
                        *(a.excluded or []),
                        {"member": a.proposed_to, "reason": "no_response", "at": now.isoformat()},
                    ]
                    a.proposed_to = None
                    _propose(s, home, a, chore, week, now, deliver)
                    did.append(("reasked", chore.title))
                elif age >= REMIND_AFTER and not events and a.proposed_to in members:
                    _notify(s, home, members[a.proposed_to], "nudge", chore.title, now, deliver)
                    _log(s, home.id, "nudged", now, detail=f"a{a.id}:{a.proposed_to}")
                    did.append(("nudge", chore.title))
            elif a.status == "planned" and chore.due and a.member_id in members:
                if date.fromisoformat(chore.due) - _today(now) <= timedelta(days=1):
                    already = s.exec(
                        select(HomeEvent).where(
                            HomeEvent.home_id == home.id,
                            HomeEvent.kind == "due_reminder",
                            HomeEvent.detail == f"a{a.id}",
                        )
                    ).first()
                    if not already:
                        _notify(s, home, members[a.member_id], "due", chore.title, now, deliver)
                        _log(s, home.id, "due_reminder", now, detail=f"a{a.id}")
                        did.append(("due", chore.title))
    s.commit()
    return did


# ---- views ------------------------------------------------------------------------------------------------


def _public_assignment(a: Assignment, chore: Chore, names: dict, today: date) -> dict:
    status = PUBLIC_STATUS[a.status]
    if status == "planned" and date.fromisoformat(a.week) + timedelta(days=6) < today:
        status = "missed"
    return {
        "id": a.id,
        "chore_id": a.chore_id,
        "title": chore.title,
        "category": chore.category,
        "minutes": a.minutes,
        "due": chore.due,
        "slot": a.slot,
        "status": status,
        "owner": names.get(a.member_id) if a.status in ("planned", "done") else None,
        "heaviness": chore.heaviness,
        "mental": chore.mental,
    }


def get_state(s: Session, token: str, now: datetime | None = None) -> dict:
    now = now or now_utc()
    me, home = _auth(s, token, now)
    today = _today(now)
    week = week_of(today)
    members = _members(s, home.id)
    names = {m.id: m.name for m in members}
    chores = _chore_rows(s, home.id)
    rows = _week_rows(s, home.id, week)
    plan = s.exec(
        select(HomePlan).where(HomePlan.home_id == home.id, HomePlan.week == week.isoformat())
    ).first()
    public = [_public_assignment(a, chores[a.chore_id], names, today) for a in rows if a.chore_id in chores]
    loads: dict[str, int] = {}
    for a in rows:
        if a.status in ("planned", "done") and a.member_id:
            loads[names[a.member_id]] = loads.get(names[a.member_id], 0) + a.minutes
    report = dict(plan.report) if plan else {}
    attention = [p["title"] for p in public if p["status"] == "open"]
    mine_rows = [a for a in rows if a.member_id == me.id and a.status in ("planned", "done")]
    proposals = [
        {
            "id": a.id,
            "title": chores[a.chore_id].title,
            "minutes": a.minutes,
            "category": chores[a.chore_id].category,
        }
        for a in rows
        if a.status == "proposed" and a.proposed_to == me.id and a.chore_id in chores
    ]
    profile = _profile(s, me.id)
    burden, _ = _loads(s, rows, chores)
    total = sum(burden.values())
    share = (plan.shares.get(me.id, 0.0) if plan else 0.0) * total
    mine_burden = burden.get(me.id, 0.0)
    return {
        "home": {
            "name": home.name,
            "week": week.isoformat(),
            "week_end": (week + timedelta(days=6)).isoformat(),
        },
        "me": {"name": me.name, "is_admin": me.is_admin},
        "members": [{"name": m.name, "is_admin": m.is_admin} for m in members],
        "chores": [
            _chore_view(c) for c in sorted(chores.values(), key=lambda c: (c.status, c.title.lower()))
        ],
        "plan": {
            "exists": plan is not None,
            "assignments": public,
            "loads_minutes": loads,
            "report": report,
            "headline": _headline(report),
            "attention": attention,
        },
        "mine": {
            "assignments": [
                {**_public_assignment(a, chores[a.chore_id], names, today), "why": _why_text(a.why)}
                for a in mine_rows
                if a.chore_id in chores
            ],
            "proposals": proposals,
            "profile": _profile_view(profile, week),
            "load": {
                "minutes": sum(a.minutes for a in mine_rows),
                "availability": profile.availability,
                "vs_fair_share_pct": round((mine_burden - share) / share * 100) if share > 0 else None,
            },
            "nudges": _nudges(s, me, profile, rows, mine_burden, share),
        },
        "events": [
            {"at": e.at.isoformat(), "kind": e.kind, "actor": e.actor, "detail": e.detail}
            for e in s.exec(
                select(HomeEvent)
                .where(
                    HomeEvent.home_id == home.id,
                    HomeEvent.kind != "notified",
                    HomeEvent.kind != "profile_updated",
                )
                .order_by(HomeEvent.id.desc())
            ).all()[:30]
        ],
    }


def _headline(report: dict) -> str:
    if not report:
        return "No plan yet for this week."
    parts = []
    dev = report.get("deviation_pct", 0.0)
    parts.append(
        f"This week's split is within {max(dev, 0):g}% of a fair share, judged by each person's own "
        "availability."
        if report.get("balanced")
        else f"This week's split is {dev:g}% from a fair share at its widest, the fairest the limits allow."
    )
    if report.get("heavy_chores"):
        parts.append(f"{report['heavy_rotated']} of {report['heavy_chores']} heavy chores changed hands.")
    if report.get("mental_chores") and report.get("mental_owners", 0) > 1:
        parts.append("Planning and admin tasks are shared.")
    if report.get("unstaffed"):
        parts.append(f"{len(report['unstaffed'])} chore(s) still need someone.")
    if report.get("exempt_count"):
        parts.append(f"{report['exempt_count']} person is exempt this week.")
    return " ".join(parts)


def _why_text(code: str | None) -> str | None:
    return {
        "love": "You said you enjoy this kind of chore.",
        "knows": "You know how to do this well.",
        "learn": "You wanted to learn this.",
        "rotation": "A heavy chore that rotates: it's your turn.",
        "fair": "This keeps the split fair.",
    }.get(code or "")


def _nudges(
    s: Session, me: Member, profile: MemberProfile, rows: list[Assignment], mine_burden: float, share: float
) -> list[str]:
    out = []
    if profile.updated_at is None:
        out.append("Set your availability and preferences so the plan fits you. Only you can see them.")
    declined = sum(
        1
        for a in rows
        for e in (a.excluded or [])
        if e.get("member") == me.id and e.get("reason") in ("prefer_not", "busy", "other", "no_response")
    )
    if declined >= 3 and share > 0 and mine_burden < share:
        out.append(
            "You've passed on several requests while carrying less than your share. If your week is "
            "full, lower your availability instead: it keeps things fair for everyone."
        )
    return out


# ---- plain words: the agent ------------------------------------------------------------------------------------


def add_chore_any(
    s: Session,
    token: str,
    fields: dict | None,
    text: str | None,
    now: datetime | None = None,
    deliver=notify.deliver_home,
) -> dict:
    """Add a chore from structured fields, or from plain words the agent understands."""
    now = now or now_utc()
    if text and not fields:
        from ..agent import chore_agent

        parsed = chore_agent.parse_chore_engine(text, _today(now))
        if not parsed["fields"].get("title"):
            return {
                "outcome": "need_more",
                "questions": parsed["questions"] or ["What's the chore?"],
                "parsed": parsed,
            }
        out = add_chore(s, token, parsed["fields"], now, deliver)
        out["parsed"] = {k: parsed[k] for k in ("assumed", "questions", "engine", "latency_ms")}
        return out
    return add_chore(s, token, fields or {}, now, deliver)


def say(
    s: Session, token: str, utterance: str, now: datetime | None = None, deliver=notify.deliver_home
) -> dict:
    """Talk to the household agent. Replies are about chores (which the household already shares), the
    caller's own offers and load, and the public plan. They never reveal anyone's private preferences."""
    from ..agent import chore_agent as ca

    now = now or now_utc()
    me, _ = _auth(s, token, now)
    st = get_state(s, token, now)
    intent = ca.interpret(utterance)
    kind = intent["intent"]
    mine = [a for a in st["mine"]["assignments"] if a["status"] == "planned"]
    public = st["plan"]["assignments"]

    def reply(text: str, changed: bool = False) -> dict:
        return {"say": text, "intent": kind, "state_changed": changed}

    if kind == "add":
        out = add_chore_any(s, token, None, utterance, now, deliver)
        if out["outcome"] == "need_more":
            return reply(out["questions"][0])
        title = out["chore"]["title"]
        guess = out["parsed"]["assumed"]
        extra = (
            f" I guessed {guess[0]}; tell me if that's off." if guess and guess[0].startswith("about") else ""
        )
        if out["outcome"] == "asked" and out["proposed_to_you"]:
            return reply(f"Added '{title}'. Can you take it? Say accept or decline.{extra}", True)
        if out["outcome"] == "asked":
            return reply(
                f"Added '{title}'. I've asked someone who fits, and I'll ask the next person if they can't.{extra}",
                True,
            )
        return reply(f"Added '{title}'. It will be in the plan when the week is planned.{extra}", True)
    if kind == "mine":
        if not mine and not st["mine"]["proposals"]:
            return reply("Nothing on your plate this week.")
        parts = [f"{a['title']}, {a['minutes']} minutes" for a in mine]
        offers = len(st["mine"]["proposals"])
        text = ("You have " + "; ".join(parts) + ".") if parts else ""
        if offers:
            text += f" {offers} request{'s are' if offers != 1 else ' is'} waiting for you. Say accept or decline."
        return reply(text.strip())
    if kind in ("done", "handback"):
        i = ca.best_match(intent["target"], [a["title"] for a in mine])
        if i is None:
            elsewhere = ca.best_match(
                intent["target"], [a["title"] for a in public if a["owner"] and a["owner"] != me.name]
            )
            return reply(
                "That one belongs to someone else."
                if elsewhere is not None
                else "I couldn't find that on your plate."
            )
        if kind == "done":
            complete(s, token, mine[i]["id"], now)
            return reply(f"Nice, marked '{mine[i]['title']}' done.", True)
        hand_back(s, token, mine[i]["id"], None, now, deliver)
        return reply(f"Okay, I'll ask someone else to take '{mine[i]['title']}'.", True)
    if kind == "who":
        i = ca.best_match(intent["target"], [a["title"] for a in public])
        if i is None:
            return reply("I couldn't find that chore this week.")
        a = public[i]
        if a["owner"]:
            return reply(f"{a['owner']} has '{a['title']}'.")
        return reply(
            f"'{a['title']}' is still being offered."
            if a["status"] == "pending"
            else f"Nobody has '{a['title']}' yet."
        )
    if kind == "plan":
        return reply(st["plan"]["headline"])
    if kind == "make_plan":
        st2 = plan_week(s, token, None, False, now, deliver)
        return reply("Planned the week. " + st2["plan"]["headline"], True)
    if kind in ("accept", "decline"):
        offers = st["mine"]["proposals"]
        if not offers:
            return reply("Nothing is waiting on you.")
        respond(
            s, token, offers[0]["id"], kind == "accept", None if kind == "accept" else "other", now, deliver
        )
        return reply(
            f"Okay, '{offers[0]['title']}' is yours." if kind == "accept" else "Okay, I'll ask someone else.",
            True,
        )
    return reply(
        "I can add a chore, tell you what's on your plate, mark something done, hand one back, or tell you who has a chore."
    )
