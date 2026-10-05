"""Reminders for a person's own schedule: starting soon, and the Sunday digest. Opt-in, private, sent once."""

import json
from datetime import datetime, timedelta

import pytest

from server import notify
from server.engine import home as hm
from server.engine import schedule_service as ss
from server.engine.rounds import HuddleError

MON = datetime(2026, 10, 5, 9, 0, 0)
NAMES = ["Maya", "Ben", "Chen"]


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, **kw):
        self.calls.append(kw)
        return [notify.Delivery("in_app", "queued", "")]


@pytest.fixture
def rec():
    return Recorder()


@pytest.fixture
def tok(session):
    out = hm.create_household(session, "Home", [{"name": n} for n in NAMES], MON)
    return {m["name"]: m["token"] for m in out["members"]}


def add(session, tok, who, title, day, hh, mm=0):
    return ss.add_commitment(
        session,
        tok[who],
        {"title": title, "circle": "personal", "start": f"2026-10-{day:02d}T{hh:02d}:{mm:02d}", "minutes": 60},
        {"choice": "keep_both"},
        MON,
        "2026-10-05",
    )


def prefs(session, tok, who, **changes):
    return ss.set_reminder_prefs(session, tok[who], changes, MON)


# ---- preferences -------------------------------------------------------------------------------------------------


def test_reminders_are_off_until_the_person_turns_them_on(session, tok, rec):
    add(session, tok, "Maya", "Dentist", 5, 9, 20)
    assert ss.tick(session, MON, rec) == []
    assert rec.calls == []
    assert ss.reminder_view(session, "x") == {"kinds": [], "quiet_start": None, "quiet_end": None, "utc_offset_minutes": 0}


def test_prefs_are_validated(session, tok):
    for bad in (
        {"kinds": ["sms"]},
        {"kinds": "starting_soon"},
        {"quiet_start": "late"},
        {"quiet_start": "22:00"},  # needs an end too
        {"utc_offset_minutes": 9999},
        {"utc_offset_minutes": True},
    ):
        with pytest.raises(HuddleError) as e:
            prefs(session, tok, "Maya", **bad)
        assert e.value.code == "bad_reminders"


def test_prefs_are_the_callers_own_and_kept(session, tok):
    out = prefs(session, tok, "Maya", kinds=["digest", "starting_soon"], quiet_start="22:00", quiet_end="07:00", utc_offset_minutes=-300)
    assert out == {"kinds": ["digest", "starting_soon"], "quiet_start": "22:00", "quiet_end": "07:00", "utc_offset_minutes": -300}
    mine = ss.get_my_time(session, tok["Maya"], None, MON, "2026-10-05")["reminders"]
    assert {k: v for k, v in mine.items() if k != "due"} == out
    assert ss.get_my_time(session, tok["Ben"], None, MON, "2026-10-05")["reminders"]["kinds"] == []
    assert prefs(session, tok, "Maya", quiet_start=None, quiet_end=None)["quiet_start"] is None


# ---- starting soon -----------------------------------------------------------------------------------------------


def test_starting_soon_fires_once_inside_the_window(session, tok, rec):
    prefs(session, tok, "Maya", kinds=["starting_soon"])
    add(session, tok, "Maya", "Dentist", 5, 9, 20)  # 20 minutes after MON 09:00
    assert ss.tick(session, MON, rec) == [("starting_soon", "Dentist")]
    assert rec.calls[0]["kind"] == "starting_soon" and rec.calls[0]["title"] == "Dentist at 09:20"
    assert rec.calls[0]["name"] == "Maya"
    assert ss.tick(session, MON + timedelta(minutes=5), rec) == []  # not twice
    assert len(rec.calls) == 1


def test_not_before_the_window_and_not_after_it_started(session, tok, rec):
    prefs(session, tok, "Maya", kinds=["starting_soon"])
    add(session, tok, "Maya", "Dentist", 5, 10, 0)
    assert ss.tick(session, MON, rec) == []  # an hour away
    assert ss.tick(session, MON + timedelta(minutes=61), rec) == []  # already started


def test_a_repeating_commitment_reminds_once_per_day(session, tok, rec):
    prefs(session, tok, "Maya", kinds=["starting_soon"])
    ss.add_commitment(session, tok["Maya"], {"title": "Standup", "circle": "work", "start": "2026-10-05T09:15", "minutes": 15, "repeat": "daily"}, None, MON, "2026-10-05")
    assert len(ss.tick(session, MON, rec)) == 1
    assert len(ss.tick(session, MON + timedelta(days=1), rec)) == 1
    assert len(ss.tick(session, MON + timedelta(days=1, minutes=1), rec)) == 0


def test_tentative_commitments_do_not_remind(session, tok, rec):
    prefs(session, tok, "Maya", kinds=["starting_soon"])
    add(session, tok, "Maya", "Maybe", 5, 9, 20)
    cid = ss.get_my_time(session, tok["Maya"], None, MON, "2026-10-05")["items"][0]["id"]
    c = session.get(ss.Commitment, cid)
    c.status = "tentative"
    session.add(c)
    session.commit()
    assert ss.tick(session, MON, rec) == []


def test_the_persons_own_offset_decides_what_soon_means(session, tok, rec):
    prefs(session, tok, "Maya", kinds=["starting_soon"], utc_offset_minutes=120)  # their clock is two hours ahead
    add(session, tok, "Maya", "Dentist", 5, 11, 20)  # 11:20 for them is 09:20 on the server
    assert ss.tick(session, MON, rec) == [("starting_soon", "Dentist")]


def test_quiet_hours_hold_reminders_back(session, tok, rec):
    prefs(session, tok, "Maya", kinds=["starting_soon"], quiet_start="08:00", quiet_end="09:30")
    add(session, tok, "Maya", "Dentist", 5, 9, 20)
    assert ss.tick(session, MON, rec) == []
    prefs(session, tok, "Maya", quiet_start=None, quiet_end=None)
    assert ss.tick(session, MON, rec) == [("starting_soon", "Dentist")]


@pytest.mark.parametrize(
    "start,end,hh,quiet",
    [("22:00", "07:00", 23, True), ("22:00", "07:00", 6, True), ("22:00", "07:00", 12, False), ("13:00", "14:00", 13, True), ("13:00", "14:00", 14, False)],
)
def test_quiet_window_arithmetic_including_across_midnight(start, end, hh, quiet):
    from datetime import time

    assert ss._in_quiet(time(hh, 0), start, end) is quiet


def test_reminders_only_name_the_recipient_and_their_own_item(session, tok, rec):
    prefs(session, tok, "Maya", kinds=["starting_soon"])
    prefs(session, tok, "Ben", kinds=["starting_soon"])
    add(session, tok, "Maya", "Mayasecret", 5, 9, 20)
    ss.tick(session, MON, rec)
    assert [c["name"] for c in rec.calls] == ["Maya"]
    assert "Ben" not in json.dumps(rec.calls) and "Chen" not in json.dumps(rec.calls)


def test_the_message_text_carries_only_the_recipients_own_item():
    subject, body = notify.home_message("starting_soon", "Maya", "Dentist at 09:20", "http://x/h/t")
    assert subject == "Huddle: coming up soon" and "Dentist at 09:20" in body and "Hi Maya" in body


def test_reminder_bookkeeping_is_not_shown_to_the_household(session, tok, rec):
    prefs(session, tok, "Maya", kinds=["starting_soon"])
    add(session, tok, "Maya", "Mayasecret", 5, 9, 20)
    ss.tick(session, MON, rec)
    for who in NAMES:
        events = hm.get_state(session, tok[who], MON)["events"]
        assert not [e for e in events if e["kind"] in ("starting_soon", "digest")]
        assert "Mayasecret" not in json.dumps(events)


# ---- the Sunday digest -------------------------------------------------------------------------------------------

SUN_EVENING = datetime(2026, 10, 11, 18, 30, 0)


def test_the_digest_is_opt_in_sunday_evening_and_once_a_week(session, tok, rec):
    add(session, tok, "Maya", "Dentist", 13, 9)
    add(session, tok, "Maya", "Dinner", 14, 19)
    assert ss.tick(session, SUN_EVENING, rec) == []  # not turned on
    prefs(session, tok, "Maya", kinds=["digest"])
    assert ss.tick(session, SUN_EVENING - timedelta(hours=2), rec) == []  # too early
    assert ss.tick(session, MON + timedelta(days=1), rec) == []  # wrong day
    assert ss.tick(session, SUN_EVENING, rec) == [("digest", "Home")]
    assert rec.calls[0]["kind"] == "digest" and rec.calls[0]["title"] == "2 commitments"
    assert ss.tick(session, SUN_EVENING + timedelta(hours=1), rec) == []


def test_the_digest_counts_clashes_chores_and_waiting_decisions(session, tok, rec):
    add(session, tok, "Maya", "A", 13, 9)
    add(session, tok, "Maya", "B", 13, 9)
    hm.start_decision(session, tok["Ben"], "everyday", 3600 * 24 * 7, None, None, MON)
    prefs(session, tok, "Maya", kinds=["digest"])
    ss.tick(session, SUN_EVENING, rec)
    assert rec.calls[0]["title"] == "2 commitments (1 clash), 1 decision waiting for your answer"


def test_an_empty_week_says_so(session, tok, rec):
    prefs(session, tok, "Maya", kinds=["digest"])
    ss.tick(session, SUN_EVENING, rec)
    assert rec.calls[0]["title"] == "nothing planned yet"


def test_email_goes_only_to_a_person_who_gave_an_address(session, monkeypatch):
    sent = []

    def fake_send(to, subject, body):
        sent.append((to, subject, body))
        return notify.Delivery("email", "sent", "")

    monkeypatch.setattr(notify, "send_email", fake_send)
    out = hm.create_household(session, "Home", [{"name": "Maya", "email": "maya@example.test"}, {"name": "Ben"}], MON)
    t = {m["name"]: m["token"] for m in out["members"]}
    for who in ("Maya", "Ben"):
        ss.set_reminder_prefs(session, t[who], {"kinds": ["starting_soon"]}, MON)
        ss.add_commitment(session, t[who], {"title": "Dentist", "circle": "personal", "start": "2026-10-05T09:20", "minutes": 60}, None, MON, "2026-10-05")
    assert len(ss.tick(session, MON)) == 2
    assert [(to, subject) for to, subject, _ in sent] == [("maya@example.test", "Huddle: coming up soon")]
    assert "Dentist at 09:20" in sent[0][2] and "Ben" not in sent[0][2]


# ---- the banner on the page: the same window as the reminder ------------------------------------------------------


def due(session, tok, who, now=MON):
    return ss.get_my_time(session, tok[who], None, now, "2026-10-05")["reminders"]["due"]


def test_the_banner_lists_what_starts_within_half_an_hour_with_minutes_to_go(session, tok):
    prefs(session, tok, "Maya", kinds=["starting_soon"])
    add(session, tok, "Maya", "Dentist", 5, 9, 20)
    add(session, tok, "Maya", "Later", 5, 11, 0)
    got = due(session, tok, "Maya")
    assert [(d["title"], d["start"], d["minutes_away"]) for d in got] == [("Dentist", "2026-10-05T09:20", 20)]
    assert due(session, tok, "Maya", MON + timedelta(minutes=19, seconds=30))[0]["minutes_away"] == 1  # rounded up
    assert due(session, tok, "Maya", MON + timedelta(minutes=20))[0]["minutes_away"] == 0  # at the start time
    assert due(session, tok, "Maya", MON + timedelta(minutes=21)) == []  # one minute after it started


def test_the_banner_goes_when_it_starts_and_is_empty_before_the_window(session, tok):
    prefs(session, tok, "Maya", kinds=["starting_soon"])
    add(session, tok, "Maya", "Dentist", 5, 10, 0)
    assert due(session, tok, "Maya", MON) == []  # an hour away
    assert len(due(session, tok, "Maya", MON + timedelta(minutes=45))) == 1
    assert due(session, tok, "Maya", MON + timedelta(minutes=61)) == []  # already started


def test_the_banner_needs_the_reminder_on_and_respects_quiet_hours_and_tentative(session, tok):
    add(session, tok, "Maya", "Dentist", 5, 9, 20)
    assert due(session, tok, "Maya") == []  # off by default
    prefs(session, tok, "Maya", kinds=["digest"])
    assert due(session, tok, "Maya") == []  # a different reminder is on
    prefs(session, tok, "Maya", kinds=["starting_soon"], quiet_start="08:00", quiet_end="09:30")
    assert due(session, tok, "Maya") == []
    prefs(session, tok, "Maya", quiet_start=None, quiet_end=None)
    assert len(due(session, tok, "Maya")) == 1
    cid = ss.get_my_time(session, tok["Maya"], None, MON, "2026-10-05")["items"][0]["id"]
    c = session.get(ss.Commitment, cid)
    c.status = "tentative"
    session.add(c)
    session.commit()
    assert due(session, tok, "Maya") == []


def test_the_banner_uses_the_persons_own_offset(session, tok):
    prefs(session, tok, "Maya", kinds=["starting_soon"], utc_offset_minutes=330)  # UTC+5:30
    add(session, tok, "Maya", "Late meeting", 5, 14, 40)  # server clock 09:00 is 14:30 for them: 10 minutes away
    assert [d["minutes_away"] for d in due(session, tok, "Maya")] == [10]


def test_the_banner_is_only_the_callers_own_and_matches_what_the_reminder_sends(session, tok, rec):
    prefs(session, tok, "Maya", kinds=["starting_soon"])
    prefs(session, tok, "Ben", kinds=["starting_soon"])
    add(session, tok, "Maya", "Mayasecret", 5, 9, 20)
    assert due(session, tok, "Ben") == [] and "Mayasecret" not in json.dumps(ss.get_my_time(session, tok["Ben"], None, MON, "2026-10-05"))
    sent = ss.tick(session, MON, rec)
    assert [title for _, title in sent] == [d["title"] for d in due(session, tok, "Maya")]
