"""One person's time across family, friends, work and personal life.

Pure logic (no database). Times are floating local times: no time zones, no external calendars. A person's
commitments are private to them. The engine answers four questions:

* Which of my commitments overlap, and what should I do about it? (`conflicts`, `conflict_options`)
* If a group asks "does Thursday evening work?", what would I say, and why? (`suggest_answer`)
* When am I free? (`free_slots`, `alternatives`)
* Is my week too full, and how much free time do chores and care realistically have? (`week_summary`)

"Smart" here means explainable. Every recommendation carries its reasons, in terms of the person's own rules:
the order they rank their circles in, their protected windows, their work hours, whether an item is fixed,
movable or optional, and whether it is shared with other people (which makes it harder to move).
"""

from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta

CIRCLES = ("family", "friends", "work", "personal")
FLEX = ("fixed", "movable", "optional")
REPEATS = ("none", "daily", "weekly")
DEFAULT_RANK = ["family", "work", "friends", "personal"]
DEFAULT_FLEX = {"family": "fixed", "work": "fixed", "friends": "movable", "personal": "movable"}
WAKING_START, WAKING_END = time(7, 0), time(22, 0)
EVENING_START = time(17, 30)
WAKING_MINUTES_PER_DAY = 15 * 60
OVERBOOKED_ABOVE = 0.85  # committed time plus chores and care above this share of waking hours
FREE_TIME_SHARE_FOR_CHORES = 0.25  # a suggestion, never applied automatically
FLEX_WEIGHT = {"fixed": 8.0, "movable": 3.0, "optional": 0.0}


@dataclass(frozen=True)
class Window:
    """A protected stretch of time on certain weekdays (0 = Monday), such as Sunday mornings."""

    days: tuple[int, ...]
    start: time
    end: time
    label: str = "protected time"


@dataclass
class Rules:
    circle_rank: list[str] = field(default_factory=lambda: list(DEFAULT_RANK))
    protected: list[Window] = field(default_factory=list)
    work_start: time | None = None
    work_end: time | None = None
    max_evenings: int | None = None
    buffer_minutes: int = 0


@dataclass(frozen=True)
class Item:
    """One commitment (or one occurrence of a repeating one)."""

    id: str
    title: str
    circle: str
    start: datetime
    end: datetime
    flexibility: str = "movable"
    importance: int = 2
    shared: bool = False  # other people are part of it, so moving it means asking them
    tentative: bool = False
    repeat: str = "none"
    until: date | None = None
    skips: tuple[str, ...] = ()  # ISO dates of skipped occurrences

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


# ---- time helpers -------------------------------------------------------------------------------------------


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def part_of_day(dt: datetime) -> str:
    return "morning" if dt.time() < time(12, 0) else "afternoon" if dt.time() < EVENING_START else "evening"


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime, buffer: int = 0) -> bool:
    pad = timedelta(minutes=buffer)
    return a_start < b_end + pad and b_start < a_end + pad


def label(dt: datetime) -> str:
    return f"{dt.strftime('%a')} {dt.day} {dt.strftime('%b')}, {dt.strftime('%H:%M')}"


def span_label(start: datetime, end: datetime) -> str:
    return f"{label(start)} to {end.strftime('%H:%M')}"


# ---- expanding repeats ---------------------------------------------------------------------------------------


def occurrences(item: Item, window_start: datetime, window_end: datetime) -> list[Item]:
    """The occurrences of `item` that touch [window_start, window_end)."""
    if item.repeat == "none":
        return [item] if overlaps(item.start, item.end, window_start, window_end) else []
    step = timedelta(days=1 if item.repeat == "daily" else 7)
    out, k = [], 0
    length = item.end - item.start
    # jump straight to the first occurrence that can touch the window
    if window_start > item.end:
        k = max(0, int((window_start - item.start) // step) - 1)
    while True:
        start = item.start + step * k
        if start >= window_end or (item.until is not None and start.date() > item.until):
            break
        occ = replace(item, start=start, end=start + length, repeat="none", until=None, skips=())
        if start.date().isoformat() not in item.skips and overlaps(
            occ.start, occ.end, window_start, window_end
        ):
            out.append(occ)
        k += 1
        if k > 4000:  # a safety stop for a malformed series
            break
    return out


def expand(items: list[Item], window_start: datetime, window_end: datetime) -> list[Item]:
    out = [o for it in items for o in occurrences(it, window_start, window_end)]
    return sorted(out, key=lambda i: (i.start, i.end, i.id))


# ---- rules and priority ---------------------------------------------------------------------------------------


def _in_window(w: Window, start: datetime, end: datetime) -> bool:
    for offset in range(-1, (end.date() - start.date()).days + 1):
        day = start.date() + timedelta(days=offset)
        if day.weekday() in w.days and overlaps(
            start, end, datetime.combine(day, w.start), datetime.combine(day, w.end)
        ):
            return True
    return False


def rule_flags(item: Item, rules: Rules) -> list[str]:
    """Reasons an item sits badly with the person's own rules ("during Sunday mornings", "inside work hours")."""
    flags = [w.label for w in rules.protected if _in_window(w, item.start, item.end)]
    ws, we = rules.work_start, rules.work_end
    if ws and we and item.start.weekday() < 5 and item.circle != "work":
        if overlaps(
            item.start,
            item.end,
            datetime.combine(item.start.date(), ws),
            datetime.combine(item.start.date(), we),
        ):
            flags.append("work hours")
    return flags


def circle_weight(circle: str, rules: Rules) -> float:
    rank = rules.circle_rank + [c for c in CIRCLES if c not in rules.circle_rank]
    return float(len(rank) - rank.index(circle)) if circle in rank else 1.0


def priority(item: Item, rules: Rules) -> float:
    """How much this commitment should win a clash. Higher keeps its place."""
    return (
        circle_weight(item.circle, rules) * 10
        + item.importance * 3
        + FLEX_WEIGHT[item.flexibility]
        + (6.0 if item.shared else 0.0)
    )


# ---- conflicts ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Conflict:
    a: Item
    b: Item


def conflicts(
    items: list[Item], window_start: datetime, window_end: datetime, rules: Rules | None = None
) -> list[Conflict]:
    """Pairs of commitments that overlap (within the person's buffer), in time order."""
    rules = rules or Rules()
    occ = expand(items, window_start, window_end)
    out = []
    for i, a in enumerate(occ):
        for b in occ[i + 1 :]:
            if b.start >= a.end + timedelta(minutes=rules.buffer_minutes):
                break
            if a.id != b.id and overlaps(a.start, a.end, b.start, b.end, rules.buffer_minutes):
                out.append(Conflict(a, b))
    return out


def clashes_with(new: Item, items: list[Item], rules: Rules) -> list[Item]:
    """Existing occurrences that overlap a new item."""
    window_end = new.end + timedelta(days=1)
    occ = expand([i for i in items if i.id != new.id], new.start - timedelta(days=1), window_end)
    return [o for o in occ if overlaps(new.start, new.end, o.start, o.end, rules.buffer_minutes)]


# ---- free time ------------------------------------------------------------------------------------------------


def _free(start: datetime, end: datetime, busy: list[Item], rules: Rules) -> bool:
    if start.time() < WAKING_START or end.time() > WAKING_END or end.date() != start.date():
        return False
    if any(overlaps(start, end, b.start, b.end, rules.buffer_minutes) for b in busy):
        return False
    return not any(_in_window(w, start, end) for w in rules.protected)


def free_slots(
    items: list[Item],
    rules: Rules,
    day_from: date,
    day_to: date,
    duration: int,
    step: int = 60,
    limit: int = 40,
    earliest: time = WAKING_START,
    latest_end: time = WAKING_END,
) -> list[datetime]:
    """Start times in [day_from, day_to] where `duration` minutes fit between the person's commitments."""
    busy = expand(
        items, datetime.combine(day_from, time(0)), datetime.combine(day_to + timedelta(days=1), time(0))
    )
    out = []
    day = day_from
    while day <= day_to and len(out) < limit:
        cursor = datetime.combine(day, earliest)
        stop = datetime.combine(day, latest_end)
        while cursor + timedelta(minutes=duration) <= stop and len(out) < limit:
            if _free(cursor, cursor + timedelta(minutes=duration), busy, rules):
                out.append(cursor)
            cursor += timedelta(minutes=step)
        day += timedelta(days=1)
    return out


def alternatives(
    item: Item, items: list[Item], rules: Rules, count: int = 3, within_days: int = 7
) -> list[datetime]:
    """Good new times for `item`: free, outside protected windows, in the same part of the day first, then
    the fewest days away, preferring later over earlier."""
    others = [i for i in items if i.id != item.id]
    anchor = item.start
    slots = free_slots(
        others,
        rules,
        (anchor - timedelta(days=within_days)).date(),
        (anchor + timedelta(days=within_days)).date(),
        max(item.minutes, 15),
        step=30,
        limit=400,
    )
    now_floor = anchor - timedelta(days=within_days)
    cands = [s for s in slots if s != anchor and s >= now_floor]

    def closeness(s: datetime) -> tuple:
        days = abs((s.date() - anchor.date()).days)
        same_part = 0 if part_of_day(s) == part_of_day(anchor) else 1
        minutes = abs((s.hour * 60 + s.minute) - (anchor.hour * 60 + anchor.minute))
        # the part of the day matters most (a dinner stays an evening thing), then how few days away,
        # then later rather than earlier (when moving something, people usually mean later)
        return (same_part, days, s < anchor, minutes, s)

    return sorted(cands, key=closeness)[:count]


# ---- answering a group's "does this time work?" ----------------------------------------------------------------


def suggest_answer(
    items: list[Item], rules: Rules, start: datetime, duration: int, circle: str
) -> tuple[str, str]:
    """(yes | maybe | no, a private reason) for one candidate time, from the person's own commitments."""
    end = start + timedelta(minutes=duration)
    probe = Item("probe", "", circle, start, end)
    busy = clashes_with(probe, items, rules)
    for w in rules.protected:
        if _in_window(w, start, end):
            return "no", f"Overlaps your protected time ({w.label})"
    if start.time() < WAKING_START or end.time() > WAKING_END or end.date() != start.date():
        return "no", "Outside your waking hours"
    if any(b.flexibility == "fixed" or b.shared for b in busy):
        hard = next(b for b in busy if b.flexibility == "fixed" or b.shared)
        return (
            "no",
            f"Overlaps '{hard.title}' ({hard.circle}), which is {'shared' if hard.shared else 'fixed'}",
        )
    if busy:
        names = ", ".join(f"'{b.title}' ({b.circle})" for b in busy)
        return "maybe", f"You'd have to move {names}"
    flags = rule_flags(probe, rules)
    if flags:
        return "maybe", f"Falls in {', '.join(flags)}"
    return "yes", "You're free"


# ---- conflict conversation: options with reasons ----------------------------------------------------------------


def _why(keep: Item, give: Item, rules: Rules) -> str:
    if keep.shared and not give.shared:
        return f"'{keep.title}' is shared with other people, so it's harder to move."
    if keep.flexibility == "fixed" and give.flexibility != "fixed":
        return f"'{keep.title}' is fixed and '{give.title}' is flexible."
    if circle_weight(keep.circle, rules) > circle_weight(give.circle, rules):
        return f"You rank {keep.circle} above {give.circle}."
    if keep.importance > give.importance:
        return f"'{keep.title}' matters more to you."
    return "They are close, so it's your call."


def conflict_options(new: Item, existing: Item, items: list[Item], rules: Rules) -> dict:
    """Ranked ways to resolve a clash between a new item and an existing one, with a recommendation.

    Each option: key, label, detail and, when it involves moving something, concrete alternative times.
    """
    p_new, p_old = priority(new, rules), priority(existing, rules)
    keep_old = p_old >= p_new
    reason = _why(existing, new, rules) if keep_old else _why(new, existing, rules)
    can_move_old = existing.flexibility != "fixed" and not existing.shared
    opts = [
        {
            "key": "move_new",
            "label": f"Keep '{existing.title}' and move '{new.title}'",
            "detail": f"I'll look for another time for '{new.title}'.",
            "alternatives": alternatives(new, [i for i in items if i.id != new.id], rules),
        },
        {
            "key": "drop_new",
            "label": f"Keep '{existing.title}' and skip '{new.title}'",
            "detail": f"'{new.title}' won't go in your schedule.",
        },
    ]
    if can_move_old:
        opts.insert(
            1,
            {
                "key": "move_existing",
                "label": f"Keep '{new.title}' and move '{existing.title}'",
                "detail": f"I'll look for another time for '{existing.title}'.",
                "alternatives": alternatives(
                    existing, [i for i in items if i.id != existing.id] + [new], rules
                ),
            },
        )
        opts.append(
            {
                "key": "drop_existing",
                "label": f"Keep '{new.title}' and cancel '{existing.title}'",
                "detail": f"'{existing.title}' comes off your schedule.",
            }
        )
    elif existing.shared:
        opts.insert(
            1,
            {
                "key": "ask_others",
                "label": f"Keep '{new.title}' and ask the others about moving '{existing.title}'",
                "detail": "It's shared, so I'll start a find-a-time with the same people.",
            },
        )
    opts.append({"key": "decide_later", "label": "Decide later", "detail": "I'll leave both and remind you."})
    recommended = (
        "move_new"
        if keep_old
        else ("move_existing" if can_move_old else "ask_others" if existing.shared else "drop_new")
    )
    if keep_old and not any(o.get("alternatives") for o in opts if o["key"] == "move_new"):
        recommended = "drop_new"  # nowhere to move it to
    return {"recommended": recommended, "reason": reason, "options": opts}


# ---- overload and the week -------------------------------------------------------------------------------------------


def evenings_out(items: list[Item], week: date) -> int:
    """Evenings this week with a non-family commitment that reaches into the evening."""
    start = datetime.combine(week, time(0))
    days = set()
    for o in expand(items, start, start + timedelta(days=7)):
        if o.circle != "family" and o.end.time() > EVENING_START and o.end.date() == o.start.date():
            days.add(o.start.date())
        elif o.circle != "family" and o.end.date() != o.start.date():
            days.add(o.start.date())
    return len(days)


def week_summary(items: list[Item], rules: Rules, week: date, chore_care_minutes: int = 0) -> dict:
    """Hours per circle, free time, whether the week is overbooked, and a chore availability suggestion."""
    start = datetime.combine(week, time(0))
    occ = expand(items, start, start + timedelta(days=7))
    by_circle = {c: 0 for c in CIRCLES}
    committed = 0
    for o in occ:
        mins = min(o.minutes, 24 * 60)
        by_circle[o.circle] += mins
        committed += mins
    waking = WAKING_MINUTES_PER_DAY * 7
    free = max(0, waking - committed - chore_care_minutes)
    evenings = evenings_out(items, week)
    notes = []
    if committed + chore_care_minutes > OVERBOOKED_ABOVE * waking:
        notes.append("This week is very full once chores and care are counted.")
    if rules.max_evenings is not None and evenings > rules.max_evenings:
        notes.append(f"That's {evenings} evenings out, above your limit of {rules.max_evenings}.")
    return {
        "week": week.isoformat(),
        "minutes_by_circle": by_circle,
        "committed_minutes": committed,
        "chore_care_minutes": chore_care_minutes,
        "free_minutes": free,
        "evenings_out": evenings,
        "overbooked": committed + chore_care_minutes > OVERBOOKED_ABOVE * waking,
        "notes": notes,
        # A suggestion only: a share of the free time, for the person's chore availability
        "suggested_chore_minutes": max(0, min(2400, round(free * FREE_TIME_SHARE_FOR_CHORES / 5) * 5)),
    }


# ---- candidate times for a group ---------------------------------------------------------------------------------------


def generate_slots(
    day_from: date,
    day_to: date,
    duration: int,
    start_at: time = time(9),
    end_at: time = time(22),
    weekdays: tuple[int, ...] | None = None,
    step: int = 60,
    limit: int = 30,
) -> list[datetime]:
    """Candidate start times for a group to choose between."""
    out = []
    day = day_from
    while day <= day_to and len(out) < limit:
        if weekdays is None or day.weekday() in weekdays:
            cursor = datetime.combine(day, start_at)
            stop = datetime.combine(day, end_at)
            while cursor + timedelta(minutes=duration) <= stop and len(out) < limit:
                out.append(cursor)
                cursor += timedelta(minutes=step)
        day += timedelta(days=1)
    return out
