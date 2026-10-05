"""Reading and writing iCalendar (.ics) files: the file a person exports from Outlook, Google or Apple Calendar,
and the file Huddle hands back.

Pure logic (no database, no network). It reads a small, honest subset of RFC 5545 and counts what it does not
understand instead of guessing:

* events (`VEVENT`) with a title, a start, and an end or a duration
* repeats that are plainly daily or weekly (`RRULE` with `FREQ=DAILY|WEEKLY`, optional `UNTIL` or `COUNT`),
  and the dates removed from them (`EXDATE`)

Skipped and counted: all-day events, other repeat rules (monthly, every other week, several weekdays),
events that are shorter than 5 minutes or longer than 14 hours, and anything without a start.

Times are floating local times, like the rest of the scheduling code. A time written with a time zone or as UTC
is used as written, with no conversion, and the count of such events is returned so the person can be told.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .rounds import HuddleError
from .schedule import Item

MAX_BYTES = 2_000_000
MAX_EVENTS = 500
MIN_MINUTES, MAX_MINUTES = 5, 14 * 60
MAX_TITLE = 80
PRODID = "-//Huddle//Household planner//EN"


@dataclass
class IcsEvent:
    uid: str
    title: str
    start: datetime
    end: datetime
    repeat: str = "none"  # none | daily | weekly
    until: str | None = None  # ISO date a repeating series ends
    skips: list[str] = field(default_factory=list)  # ISO dates removed from a repeating series
    description: str = ""
    all_day: bool = False  # written only: start is the first day and end the day after the last


@dataclass
class ParseResult:
    events: list[IcsEvent]
    skipped: int  # events that were read but could not be used (see the module docstring)
    assumed_zone: int  # events whose time carried a zone or Z and was used as written
    reasons: dict[str, int] = field(default_factory=dict)  # why, by reason key (see SKIP_REASONS)


# The reason an event was left out, in words for a person. Keys are what the reader returns.
SKIP_REASONS = {
    "all_day": "all-day",
    "repeat": "with a repeat Huddle can't read (monthly, every other week or several weekdays)",
    "too_long": "longer than 14 hours (check that its end date is the same day)",
    "too_short": "shorter than 5 minutes",
    "no_start": "without a usable start time",
    "cancelled": "cancelled",
    "changed_day": "a changed single day of a repeating event",
    "removed_here": "removed here earlier, so not brought back",
    "invalid": "that didn't pass Huddle's checks",
}


def describe_skips(reasons: dict[str, int]) -> str:
    """'3 events were skipped: 1 longer than 14 hours (...), 2 all-day.' Empty when nothing was skipped."""
    total = sum(reasons.values())
    if not total:
        return ""
    parts = ", ".join(f"{n} {SKIP_REASONS.get(k, k)}" for k, n in sorted(reasons.items(), key=lambda kv: -kv[1]))
    return f"{total} event{'s were' if total != 1 else ' was'} skipped: {parts}."


# ---- reading ------------------------------------------------------------------------------------------------


def _unfold(text: str) -> list[str]:
    """RFC 5545 folds long lines by starting the continuation with a space or tab."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw.strip():
            lines.append(raw.rstrip())
    return lines


def _split(line: str) -> tuple[str, dict[str, str], str]:
    """`DTSTART;TZID=Europe/London:20261008T190000` -> ("DTSTART", {"TZID": "Europe/London"}, "2026...")."""
    head, _, value = line.partition(":")
    name, *params = head.split(";")
    pairs = {}
    for p in params:
        k, _, v = p.partition("=")
        pairs[k.upper()] = v.strip('"')
    return name.upper(), pairs, value


def _unescape(text: str) -> str:
    return re.sub(r"\\([\\;,nN])", lambda m: "\n" if m[1] in "nN" else m[1], text)


_DT = re.compile(r"^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})?)?(Z)?$")


def _when(value: str, params: dict[str, str]) -> tuple[datetime | None, bool, bool]:
    """(time, all_day, had_zone). All-day values are dates with no time."""
    m = _DT.match(value.strip())
    if not m:
        return None, False, False
    y, mo, d, hh, mm, ss, z = m.groups()
    try:
        if hh is None or params.get("VALUE") == "DATE":
            return datetime(int(y), int(mo), int(d)), True, False
        stamp = datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss or 0))
        return stamp, False, bool(z or params.get("TZID"))
    except ValueError:
        return None, False, False


_DUR = re.compile(r"^P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def _duration(value: str) -> timedelta | None:
    m = _DUR.match(value.strip())
    if not m or not any(m.groups()):
        return None
    w, d, h, mi, s = (int(g or 0) for g in m.groups())
    return timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)


def _rrule(value: str, start: datetime) -> tuple[str, str | None] | None:
    """(repeat, until) for a plainly daily or weekly rule, or None when it is anything more complicated."""
    parts = dict(p.split("=", 1) for p in value.split(";") if "=" in p)
    freq = parts.get("FREQ", "").upper()
    if freq not in ("DAILY", "WEEKLY") or parts.get("INTERVAL", "1") != "1":
        return None
    allowed = {"FREQ", "INTERVAL", "UNTIL", "COUNT", "WKST", "BYDAY"}
    if set(parts) - allowed:
        return None
    if "BYDAY" in parts:  # only the weekday the event already falls on
        days = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        if freq != "WEEKLY" or parts["BYDAY"].upper() != days[start.weekday()]:
            return None
    step = timedelta(days=1 if freq == "DAILY" else 7)
    until = None
    if "UNTIL" in parts:
        got, _, _ = _when(parts["UNTIL"], {})
        if got is None:
            return None
        until = got.date().isoformat()
    elif "COUNT" in parts:
        if not parts["COUNT"].isdigit() or not 1 <= int(parts["COUNT"]) <= 1000:
            return None
        until = (start + step * (int(parts["COUNT"]) - 1)).date().isoformat()
    return freq.lower(), until


def parse(text: str) -> ParseResult:
    """Read the events in an .ics file. Raises HuddleError("bad_calendar") if it is not a calendar at all."""
    if len(text.encode("utf-8", "ignore")) > MAX_BYTES:
        raise HuddleError("bad_calendar", "That calendar file is too large (limit 2 MB).")
    lines = _unfold(text)
    if not any(ln.strip().upper() == "BEGIN:VCALENDAR" for ln in lines):
        raise HuddleError("bad_calendar", "That doesn't look like a calendar (.ics) file.")
    events: list[IcsEvent] = []
    skipped = assumed_zone = 0
    reasons: dict[str, int] = {}
    block: list[str] | None = None
    seen = 0
    for ln in lines:
        up = ln.upper()
        if up == "BEGIN:VEVENT":
            block = []
        elif up == "END:VEVENT" and block is not None:
            seen += 1
            if seen > MAX_EVENTS:
                raise HuddleError("bad_calendar", f"That calendar has more than {MAX_EVENTS} events.")
            got = _event(block)
            if isinstance(got, str):
                skipped += 1
                reasons[got] = reasons.get(got, 0) + 1
            else:
                ev, zoned = got
                events.append(ev)
                assumed_zone += zoned
            block = None
        elif block is not None:
            block.append(ln)
    return ParseResult(events, skipped, assumed_zone, reasons)


def _event(block: list[str]) -> tuple[IcsEvent, bool] | str:
    """The event and whether its time carried a zone, or the reason it can't be used (a key of SKIP_REASONS)."""
    props: dict[str, tuple[dict[str, str], str]] = {}
    exdates: list[str] = []
    for ln in block:
        name, params, value = _split(ln)
        if name == "EXDATE":
            for v in value.split(","):
                got, _, _ = _when(v, params)
                if got:
                    exdates.append(got.date().isoformat())
        else:
            props.setdefault(name, (params, value))
    if props.get("STATUS", ({}, ""))[1].upper() == "CANCELLED":
        return "cancelled"
    if "RECURRENCE-ID" in props:  # one changed day of a series: not read
        return "changed_day"
    if "DTSTART" not in props:
        return "no_start"
    start, all_day, zoned = _when(props["DTSTART"][1], props["DTSTART"][0])
    if start is None:
        return "no_start"
    if all_day:
        return "all_day"
    end = None
    if "DTEND" in props:
        end, end_all_day, _ = _when(props["DTEND"][1], props["DTEND"][0])
        if end_all_day:
            return "all_day"
    elif "DURATION" in props:
        dur = _duration(props["DURATION"][1])
        end = start + dur if dur else None
    else:
        end = start + timedelta(hours=1)
    if end is None:
        return "no_start"
    if end - start < timedelta(minutes=MIN_MINUTES):
        return "too_short"
    if end - start > timedelta(minutes=MAX_MINUTES):
        return "too_long"
    repeat, until = "none", None
    if "RRULE" in props:
        rule = _rrule(props["RRULE"][1], start)
        if rule is None:
            return "repeat"
        repeat, until = rule
    title = _unescape(props.get("SUMMARY", ({}, ""))[1]).strip().replace("\n", " ")[:MAX_TITLE] or "Busy"
    uid = props.get("UID", ({}, ""))[1].strip() or f"{start.isoformat()}-{title}"
    return (
        IcsEvent(uid[:200], title, start, end, repeat, until, sorted(set(exdates)) if repeat != "none" else []),
        zoned,
    )


# ---- writing ------------------------------------------------------------------------------------------------


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Fold at 75 octets, never inside a multi-byte character."""
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > (75 if not out else 74):
            out.append(cur)
            cur, size = "", 0
        cur += ch
        size += n
    out.append(cur)
    return "\r\n ".join(out)


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def build(events: list[IcsEvent], name: str, now: datetime) -> str:
    """An .ics file with floating local times (no zone), ready to add to any calendar app."""
    out = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_escape(name)}",
    ]
    for e in events:
        day = "%Y%m%d"
        out += [
            "BEGIN:VEVENT",
            f"UID:{e.uid}",
            f"DTSTAMP:{_stamp(now)}Z",
            f"DTSTART;VALUE=DATE:{e.start.strftime(day)}" if e.all_day else f"DTSTART:{_stamp(e.start)}",
            f"DTEND;VALUE=DATE:{e.end.strftime(day)}" if e.all_day else f"DTEND:{_stamp(e.end)}",
            f"SUMMARY:{_escape(e.title)}",
        ]
        if e.description:
            out.append(f"DESCRIPTION:{_escape(e.description)}")
        if e.repeat != "none":
            rule = f"FREQ={e.repeat.upper()}"
            if e.until:
                rule += f";UNTIL={date.fromisoformat(e.until).strftime('%Y%m%d')}T235959"
            out.append(f"RRULE:{rule}")
            for d in e.skips:
                out.append(f"EXDATE:{date.fromisoformat(d).strftime('%Y%m%d')}T{e.start.strftime('%H%M%S')}")
        out.append("END:VEVENT")
    out.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in out) + "\r\n"


def event_of(item: Item) -> IcsEvent:
    """A schedule item as an exportable event. The id is stable, so re-importing the file updates it."""
    return IcsEvent(
        uid=f"{item.id}@huddle",
        title=item.title,
        start=item.start,
        end=item.end,
        repeat=item.repeat,
        until=item.until.isoformat() if item.until else None,
        skips=list(item.skips),
    )
