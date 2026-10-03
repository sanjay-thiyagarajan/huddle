"""The scheduling agent: plain-words commitments and settling clashes by conversation."""

import json
from datetime import date, datetime

import pytest

from server.agent import schedule_agent as sa
from server.engine import home as hm
from server.engine import schedule_chat as chat
from server.engine import schedule_service as ss

MON = datetime(2026, 10, 5, 9, 0, 0)
TODAY = "2026-10-05"


@pytest.fixture
def tok(session):
    chat._PENDING.clear()
    out = hm.create_household(session, "Home", [{"name": n} for n in ("Maya", "Ben", "Chen")], MON)
    return {m["name"]: m["token"] for m in out["members"]}


def say(session, tok, who, text):
    return chat.say(session, tok[who], text, MON, TODAY)


def items(session, tok, who):
    return ss.get_my_time(session, tok[who], None, MON, TODAY)["items"]


@pytest.mark.parametrize(
    "text,title,circle,start,minutes,repeat",
    [
        (
            "dinner with Priya Thursday 7pm for 2 hours",
            "dinner with Priya",
            "friends",
            "2026-10-08T19:00",
            120,
            "none",
        ),
        (
            "Standup every Monday at 9:30am for 30 minutes",
            "Standup",
            "work",
            "2026-10-05T09:30",
            30,
            "weekly",
        ),
        (
            "school concert on 2026-10-08 6pm can't move",
            "school concert",
            "family",
            "2026-10-08T18:00",
            60,
            "none",
        ),
        ("gym tomorrow 7am", "gym", "personal", "2026-10-06T07:00", 60, "none"),
        ("team meeting Oct 9 at 14:00", "team meeting", "work", "2026-10-09T14:00", 60, "none"),
    ],
)
def test_parses_plain_words(text, title, circle, start, minutes, repeat):
    f = sa.parse_commitment(text, date(2026, 10, 5))["fields"]
    assert (f["title"], f["circle"], f["start"], f["minutes"], f["repeat"]) == (
        title,
        circle,
        start,
        minutes,
        repeat,
    )


def test_missing_day_or_time_is_asked_not_guessed(session, tok):
    r = say(session, tok, "Maya", "coffee with Sam")
    assert r["intent"] == "draft" and "day" in r["say"].lower() and items(session, tok, "Maya") == []
    r = say(session, tok, "Maya", "Friday at 5pm")
    assert r["intent"] == "add" and r["state_changed"]
    assert items(session, tok, "Maya")[0]["start"] == "2026-10-09T17:00"


def test_a_clash_is_explained_with_a_recommendation_and_the_person_answers(session, tok):
    say(session, tok, "Maya", "school concert Thursday 6pm for 90 minutes can't move")
    r = say(session, tok, "Maya", "dinner with Priya Thursday 7pm for 2 hours")
    assert r["intent"] == "clash" and "school concert" in r["say"] and "Yes, do that" in r["quick_replies"]
    assert len(items(session, tok, "Maya")) == 1  # nothing added until they answer
    r = say(session, tok, "Maya", "yes")
    assert r["intent"] == "clash_resolved" and r["state_changed"]
    mine = {i["title"]: i for i in items(session, tok, "Maya")}
    assert mine["dinner with Priya"]["start"] != "2026-10-08T19:00"
    assert ss.get_my_time(session, tok["Maya"], None, MON, TODAY)["conflicts"] == []


@pytest.mark.parametrize(
    "reply,added,count",
    [("skip it", False, 1), ("keep both", True, 2), ("move it to Friday 7pm", True, 2)],
)
def test_other_ways_to_answer_a_clash(session, tok, reply, added, count):
    say(session, tok, "Maya", "book club Thursday 7pm")
    say(session, tok, "Maya", "pub with Sam Thursday 7pm")
    say(session, tok, "Maya", reply)
    got = items(session, tok, "Maya")
    assert len(got) == count and (any(i["title"] == "pub with Sam" for i in got)) is added
    if "Friday" in reply:
        assert next(i for i in got if i["title"] == "pub with Sam")["start"] == "2026-10-09T19:00"


def test_numbers_pick_an_option(session, tok):
    say(session, tok, "Maya", "book club Thursday 7pm")
    r = say(session, tok, "Maya", "pub with Sam Thursday 7pm")
    assert "1." in r["say"]
    say(session, tok, "Maya", "1")
    assert len(items(session, tok, "Maya")) == 2


def test_an_unclear_reply_keeps_waiting(session, tok):
    say(session, tok, "Maya", "book club Thursday 7pm")
    say(session, tok, "Maya", "pub with Sam Thursday 7pm")
    r = say(session, tok, "Maya", "hmm")
    assert r["intent"] == "clash" and len(items(session, tok, "Maya")) == 1


def test_a_rule_is_offered_after_two_consistent_choices_and_applied_on_yes(session, tok):
    ss.set_rules(session, tok["Maya"], {"circle_rank": ["friends", "family", "work", "personal"]}, MON)
    for day, name in ((6, "Tuesday"), (7, "Wednesday")):
        say(session, tok, "Maya", f"parents' visit {name} 6pm")
        r = say(session, tok, "Maya", f"drinks with Ana {name} 6pm")
        r = say(session, tok, "Maya", "skip the new one")
    assert "make it a rule" in r["say"].lower()
    r = say(session, tok, "Maya", "make it a rule")
    assert r["intent"] == "rule"
    assert ss.rules_view(session, tok["Maya"])["circle_rank"][0] == "family"


def test_week_free_and_cancel(session, tok):
    assert "Nothing" in say(session, tok, "Maya", "what's my week")["say"]
    say(session, tok, "Maya", "dentist Wednesday 3pm")
    assert "personal" in say(session, tok, "Maya", "what's my week")["say"]
    assert "free" in say(session, tok, "Maya", "when am I free")["say"]
    r = say(session, tok, "Maya", "cancel the dentist")
    assert r["state_changed"] and items(session, tok, "Maya") == []


def test_find_a_time_by_voice_asks_members_and_makes_guests(session, tok):
    r = say(session, tok, "Maya", "find a time for drinks with Ben and Priya")
    assert r["intent"] == "find" and r["round_id"]
    assert ss.get_my_time(session, tok["Ben"], None, MON, TODAY)["gatherings"]


def test_the_conversation_never_shows_another_persons_schedule(session, tok):
    say(session, tok, "Maya", "therapy sentinelsecret Thursday 5pm")
    out = [
        say(session, tok, "Ben", t)
        for t in (
            "what's my week",
            "when am I free",
            "cancel therapy",
            "find a time for drinks with Maya",
        )
    ]
    assert "sentinelsecret" not in json.dumps(out)
    assert len(items(session, tok, "Maya")) == 1
