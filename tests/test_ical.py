"""iCalendar reading and writing: the subset we read, what we count instead of guessing, and the limits."""

from datetime import datetime

import pytest

from server.engine import ical
from server.engine.rounds import HuddleError
from server.engine.schedule import Item

NOW = datetime(2026, 10, 5, 9, 0, 0)


def cal(*events: str) -> str:
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "".join(events) + "END:VCALENDAR\r\n"


def ev(*lines: str) -> str:
    return "BEGIN:VEVENT\r\n" + "".join(f"{ln}\r\n" for ln in lines) + "END:VEVENT\r\n"


def test_reads_a_plain_event_with_an_end_a_duration_or_neither():
    out = ical.parse(
        cal(
            ev("UID:a", "SUMMARY:Dentist", "DTSTART:20261008T090000", "DTEND:20261008T094500"),
            ev("UID:b", "SUMMARY:Gym", "DTSTART:20261008T180000", "DURATION:PT1H30M"),
            ev("UID:c", "SUMMARY:Call", "DTSTART:20261009T100000"),
        )
    )
    a, b, c = out.events
    assert (a.title, a.start, a.end) == ("Dentist", datetime(2026, 10, 8, 9), datetime(2026, 10, 8, 9, 45))
    assert b.end == datetime(2026, 10, 8, 19, 30)
    assert c.end == datetime(2026, 10, 9, 11)  # no end: an hour
    assert out.skipped == 0


def test_unfolds_long_lines_and_unescapes_text():
    out = ical.parse(cal(ev("UID:a", "SUMMARY:Lunch\\, with\\nMum and a very long title that is folded", "  across two lines", "DTSTART:20261008T120000")))
    assert out.events[0].title == "Lunch, with Mum and a very long title that is folded across two lines"[:80]


def test_zone_and_utc_times_are_kept_as_written_and_counted():
    out = ical.parse(
        cal(
            ev("UID:a", "SUMMARY:UTC", "DTSTART:20261008T090000Z", "DTEND:20261008T100000Z"),
            ev("UID:b", "SUMMARY:Zoned", "DTSTART;TZID=Europe/London:20261008T090000", "DTEND;TZID=Europe/London:20261008T100000"),
            ev("UID:c", "SUMMARY:Floating", "DTSTART:20261008T090000", "DTEND:20261008T100000"),
        )
    )
    assert [e.start.hour for e in out.events] == [9, 9, 9]
    assert out.assumed_zone == 2


def test_repeats_daily_and_weekly_with_until_count_and_exdate():
    out = ical.parse(
        cal(
            ev("UID:d", "SUMMARY:Standup", "DTSTART:20261005T090000", "DTEND:20261005T091500", "RRULE:FREQ=DAILY;UNTIL=20261009T235959Z"),
            ev("UID:w", "SUMMARY:Yoga", "DTSTART:20261006T180000", "DTEND:20261006T190000", "RRULE:FREQ=WEEKLY;COUNT=4", "EXDATE:20261013T180000"),
            ev("UID:o", "SUMMARY:Class", "DTSTART:20261006T180000", "DTEND:20261006T190000", "RRULE:FREQ=WEEKLY;BYDAY=TU"),
        )
    )
    d, w, o = out.events
    assert (d.repeat, d.until) == ("daily", "2026-10-09")
    assert (w.repeat, w.until, w.skips) == ("weekly", "2026-10-27", ["2026-10-13"])  # 4 Tuesdays from Oct 6
    assert o.repeat == "weekly" and o.until is None  # BYDAY of the weekday it already falls on is the same rule


@pytest.mark.parametrize(
    "lines",
    [
        ["RRULE:FREQ=MONTHLY"],
        ["RRULE:FREQ=WEEKLY;INTERVAL=2"],
        ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE"],
        ["RRULE:FREQ=DAILY;BYHOUR=9"],
        ["DTEND:20261008T090200"],  # shorter than 5 minutes
        ["DTEND:20261009T100000"],  # longer than 14 hours
        ["STATUS:CANCELLED"],
        ["RECURRENCE-ID:20261008T090000"],  # one changed day of a series
    ],
)
def test_what_it_does_not_understand_is_counted_not_guessed(lines):
    out = ical.parse(cal(ev("UID:a", "SUMMARY:X", "DTSTART:20261008T090000", *lines)))
    assert out.events == [] and out.skipped == 1


def test_all_day_events_and_events_without_a_start_are_skipped():
    out = ical.parse(
        cal(
            ev("UID:a", "SUMMARY:Holiday", "DTSTART;VALUE=DATE:20261008", "DTEND;VALUE=DATE:20261009"),
            ev("UID:b", "SUMMARY:No start"),
        )
    )
    assert out.events == [] and out.skipped == 2


def test_an_empty_title_becomes_busy():
    assert ical.parse(cal(ev("UID:a", "DTSTART:20261008T090000"))).events[0].title == "Busy"


def test_not_a_calendar_and_limits():
    with pytest.raises(HuddleError) as e:
        ical.parse("hello world")
    assert e.value.code == "bad_calendar"
    with pytest.raises(HuddleError):
        ical.parse(cal("") + "x" * (ical.MAX_BYTES + 1))
    many = cal(*[ev(f"UID:{i}", "SUMMARY:X", "DTSTART:20261008T090000") for i in range(ical.MAX_EVENTS + 1)])
    with pytest.raises(HuddleError):
        ical.parse(many)


def test_build_then_parse_round_trips_with_repeats_and_skips():
    item = Item("abc", "Yoga, with Priya; evening", "friends", datetime(2026, 10, 6, 18), datetime(2026, 10, 6, 19),
                repeat="weekly", until=datetime(2026, 10, 27).date(), skips=("2026-10-13",))
    text = ical.build([ical.event_of(item)], "Me (Huddle)", NOW)
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    back = ical.parse(text).events[0]
    assert (back.uid, back.title, back.start, back.end) == ("abc@huddle", item.title, item.start, item.end)
    assert (back.repeat, back.until, back.skips) == ("weekly", "2026-10-27", ["2026-10-13"])


def test_build_folds_long_lines_without_splitting_a_character():
    long = ical.IcsEvent("u", "é" * 70, datetime(2026, 10, 8, 9), datetime(2026, 10, 8, 10))
    text = ical.build([long], "x", NOW)
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    assert ical.parse(text).events[0].title == "é" * 70


def test_all_day_events_are_written_as_dates():
    e = ical.IcsEvent("u", "Chore: bins", datetime(2026, 10, 8), datetime(2026, 10, 9), all_day=True)
    text = ical.build([e], "x", NOW)
    assert "DTSTART;VALUE=DATE:20261008" in text and "DTEND;VALUE=DATE:20261009" in text


@pytest.mark.parametrize(
    "lines,reason",
    [
        (["RRULE:FREQ=MONTHLY"], "repeat"),
        (["DTEND:20261008T090200"], "too_short"),
        (["DTEND:20261009T100000"], "too_long"),
        (["STATUS:CANCELLED"], "cancelled"),
        (["RECURRENCE-ID:20261008T090000"], "changed_day"),
    ],
)
def test_each_skipped_event_says_why(lines, reason):
    out = ical.parse(cal(ev("UID:a", "SUMMARY:X", "DTSTART:20261008T090000", *lines)))
    assert out.reasons == {reason: 1}


def test_all_day_and_no_start_have_their_own_reasons():
    out = ical.parse(
        cal(
            ev("UID:a", "SUMMARY:Holiday", "DTSTART;VALUE=DATE:20261008"),
            ev("UID:b", "SUMMARY:No start"),
            ev("UID:c", "SUMMARY:Bad", "DTSTART:nonsense"),
        )
    )
    assert out.reasons == {"all_day": 1, "no_start": 2} and out.skipped == 3


def test_the_skip_note_names_the_reasons_most_common_first():
    assert ical.describe_skips({}) == ""
    assert ical.describe_skips({"too_long": 1}) == (
        "1 event was skipped: 1 longer than 14 hours (check that its end date is the same day)."
    )
    said = ical.describe_skips({"all_day": 2, "too_long": 1})
    assert said.startswith("3 events were skipped: 2 all-day, 1 longer than 14 hours")
