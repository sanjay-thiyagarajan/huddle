"""The daily briefing: the caller's own day, as data and as sentences to read aloud."""

import json
from datetime import datetime

import pytest

from server.agent import schedule_agent as sa
from server.engine import briefing
from server.engine import home as hm
from server.engine import schedule_chat as chat
from server.engine import schedule_service as ss
from server.engine.rounds import HuddleError

MON = datetime(2026, 10, 5, 9, 0, 0)
NAMES = ["Maya", "Ben", "Chen"]


@pytest.fixture
def tok(session):
    out = hm.create_household(session, "Home", [{"name": n} for n in NAMES], MON)
    return {m["name"]: m["token"] for m in out["members"]}


def add(session, tok, who, title, circle, day, hh, minutes=60):
    return ss.add_commitment(
        session,
        tok[who],
        {"title": title, "circle": circle, "start": f"2026-10-{day:02d}T{hh:02d}:00", "minutes": minutes},
        {"choice": "keep_both"},
        MON,
        "2026-10-05",
    )


def brief(session, tok, who, day=None):
    return briefing.get_briefing(session, tok[who], day, MON, "2026-10-05")


def test_an_empty_day_says_so_and_offers_a_free_hour(session, tok):
    out = brief(session, tok, "Maya")
    assert out["items"] == [] and out["say"].startswith("Today your calendar is clear.")
    assert out["next_free"] == "2026-10-05T07:00"


def test_the_day_lists_the_callers_things_in_time_order(session, tok):
    add(session, tok, "Maya", "Dinner with Priya", "friends", 5, 19)
    add(session, tok, "Maya", "Dentist", "personal", 5, 9)
    out = brief(session, tok, "Maya")
    assert [i["title"] for i in out["items"]] == ["Dentist", "Dinner with Priya"]
    assert "Today you have 2 things: Dentist at 09:00, Dinner with Priya at 19:00." in out["say"]


def test_a_clash_is_named_with_a_pointer_to_options(session, tok):
    add(session, tok, "Maya", "Dinner", "friends", 5, 19)
    add(session, tok, "Maya", "Yoga", "personal", 5, 19)
    out = brief(session, tok, "Maya")
    assert len(out["clashes"]) == 1
    assert "overlap" in out["say"] and "Ask me for options." in out["say"]


def test_another_day_is_labelled_and_bad_days_are_an_error(session, tok):
    add(session, tok, "Maya", "Recital", "family", 9, 17)
    out = brief(session, tok, "Maya", "2026-10-09")
    assert out["say"].startswith("On Fri 9 Oct you have 1 thing: Recital at 17:00.")
    with pytest.raises(HuddleError) as e:
        brief(session, tok, "Maya", "tomorrow")
    assert e.value.code == "bad_day"


def test_chores_due_and_offers_are_the_callers_own(session, tok):
    hm.add_chore_any(session, tok["Maya"], {"title": "Take out bins", "category": "yard", "minutes": 20, "cadence": "weekly", "due": "2026-10-05"}, None, MON)
    hm.plan_week(session, tok["Maya"], "2026-10-05", False, MON)
    says = {n: brief(session, tok, n) for n in NAMES}
    owners = [n for n, b in says.items() if b["chores_due"]]
    assert len(owners) == 1
    assert "Chores due: Take out bins." in says[owners[0]]["say"]
    for n in NAMES:
        if n != owners[0]:
            assert "Take out bins" not in json.dumps(says[n])


def test_a_decision_waiting_for_the_callers_answer_is_mentioned_without_values(session, tok):
    hm.start_decision(session, tok["Maya"], "everyday", 3600, None, None, MON)
    out = brief(session, tok, "Ben")
    assert len(out["decisions_waiting"]) == 1
    assert "1 family decision is waiting for your private answer." in out["say"]
    assert not any(ch.isdigit() for ch in out["say"].replace("1 family decision", "").replace("07:00", ""))


def test_the_briefing_never_includes_anyone_elses_commitments(session, tok):
    add(session, tok, "Maya", "Mayasecret sentinelbrief", "personal", 5, 10)
    for other in ("Ben", "Chen"):
        assert "sentinelbrief" not in json.dumps(brief(session, tok, other))


def test_a_bad_token_is_refused(session, tok):
    with pytest.raises(HuddleError):
        briefing.get_briefing(session, "nope", None, MON)


# ---- in plain words ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,tomorrow",
    [("what's my day", False), ("What's on today?", False), ("tell me what's on tomorrow", True), ("give me my briefing", False), ("what do I have today", False)],
)
def test_day_questions_are_understood(text, tomorrow):
    got = sa.interpret(text)
    assert got["intent"] == "day" and got["tomorrow"] is tomorrow


@pytest.mark.parametrize(
    "text,intent",
    [("what's my week", "week"), ("show my schedule this week", "week"), ("when am I free", "free"), ("dinner with Priya tomorrow 7pm", "add"), ("export my week to my calendar", "export"), ("download my chores", "export")],
)
def test_other_phrases_keep_their_meaning(text, intent):
    assert sa.interpret(text)["intent"] == intent


def test_the_agent_reads_the_day_aloud_and_points_to_export(session, tok):
    add(session, tok, "Maya", "Dentist", "personal", 5, 9)
    said = chat.say(session, tok["Maya"], "what's my day", MON, "2026-10-05")
    assert said["intent"] == "day" and "Dentist at 09:00" in said["say"]
    tomorrow = chat.say(session, tok["Maya"], "what's on tomorrow", MON, "2026-10-05")
    assert "calendar is clear" in tomorrow["say"] and tomorrow["say"].startswith("On Tue 6 Oct")
    ex = chat.say(session, tok["Maya"], "export my chores", MON, "2026-10-05")
    assert ex["intent"] == "export" and ex["next"] == {"action": "export_calendar", "kind": "chore_plan"}
