"""The household agent understands plain words: chores, and what people say to a voice assistant."""

import json
from datetime import date, datetime

import pytest

from server import config
from server.agent import chore_agent as ca
from server.agent import huddle_agent
from server.engine import home as hm

TODAY = date(2026, 10, 5)  # a Monday


def parse(text):
    return ca.parse_chore(text, TODAY)


# ---- understanding a chore -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "Clean the gutters by Saturday, about an hour",
            {
                "title": "Clean the gutters",
                "category": "yard",
                "minutes": 60,
                "due": "2026-10-10",
                "cadence": "once",
            },
        ),
        (
            "add take out the bins every Tuesday, 10 minutes",
            {"title": "Take out the bins", "category": "tidying", "minutes": 10, "cadence": "weekly"},
        ),
        (
            "Do the dishes every day, 15 minutes",
            {"title": "Do the dishes", "category": "dishes", "minutes": 15, "cadence": "daily"},
        ),
        (
            "mow the lawn every other week for 45 minutes",
            {"title": "Mow the lawn", "category": "yard", "minutes": 45, "cadence": "biweekly"},
        ),
        (
            "pay the council tax by Nov 15",
            {"title": "Pay the council tax", "category": "admin", "due": "2026-11-15", "mental": True},
        ),
        ("tomorrow buy groceries", {"title": "Buy groceries", "category": "shopping", "due": "2026-10-06"}),
        (
            "remind us to book the dentist next week",
            {"title": "Book the dentist", "category": "planning", "due": "2026-10-16", "mental": True},
        ),
        (
            "someone needs to deep clean the garage, two people, 2 hours",
            {"category": "cleaning", "minutes": 120, "heaviness": 3, "people_needed": 2},
        ),
        ("clean the kitchen in thirty minutes", {"category": "cleaning", "minutes": 30}),
        ("fix the squeaky door", {"title": "Fix the squeaky door", "category": "repairs"}),
        (
            "walk the dog every day half an hour",
            {"title": "Walk the dog", "category": "pets", "minutes": 30, "cadence": "daily"},
        ),
    ],
)
def test_plain_words_become_a_structured_chore(text, expected):
    fields = parse(text)["fields"]
    for key, value in expected.items():
        assert fields.get(key) == value, (text, key, fields)


def test_what_it_had_to_guess_is_reported_not_hidden():
    out = parse("fix the squeaky door")
    assert out["assumed"] == ["about 60 minutes"] and "minutes" not in out["fields"]
    assert parse("fix the door, 20 minutes")["assumed"] == []
    assert "the kind of chore" in parse("sort out the thing")["assumed"]


def test_nothing_to_go_on_asks_instead_of_guessing():
    out = parse("add")
    assert out["questions"] == ["What's the chore?"] and not out["fields"]["title"]


def test_dates_are_never_in_the_past_for_a_month_and_day():
    assert parse("renew the passport by Jan 3")["fields"]["due"] == "2027-01-03"  # next year, not last
    assert parse("book it by Oct 5")["fields"]["due"] == "2026-10-05"  # today is allowed


def test_a_weekday_means_the_next_one_and_next_means_the_following_week():
    assert parse("wash the car by Monday")["fields"]["due"] == "2026-10-05"  # today is Monday
    assert parse("wash the car next Monday")["fields"]["due"] == "2026-10-12"
    assert parse("wash the car by Friday")["fields"]["due"] == "2026-10-09"


# ---- what someone says ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,intent",
    [
        ("what's on my plate", "mine"),
        ("What do I have to do?", "mine"),
        ("show me my chores", "mine"),
        ("I did the bins", "done"),
        ("I've finished the laundry", "done"),
        ("mark the dishes as done", "done"),
        ("who has the laundry", "who"),
        ("who's doing the dishes?", "who"),
        ("hand back the laundry", "handback"),
        ("I can't do the bathroom", "handback"),
        ("what's the plan", "plan"),
        ("is the split fair", "plan"),
        ("plan the week", "make_plan"),
        ("accept", "accept"),
        ("I'll take it", "accept"),
        ("decline", "decline"),
        ("not this time", "decline"),
        ("add clean the gutters", "add"),
        ("we need to book the vet", "add"),
        ("someone should fix the tap", "add"),
        ("remind us to pay the rent", "add"),
        ("hello there", "unknown"),
    ],
)
def test_intents(text, intent):
    assert ca.interpret(text)["intent"] == intent, text


def test_matching_a_chore_by_the_words_used():
    titles = ["Take out the bins", "Do the dishes", "Laundry", "Clean the bathroom"]
    assert ca.best_match("I did the bins", titles) == 0
    assert ca.best_match("who has the dish", titles) == 1
    assert ca.best_match("hand back the bathroom", titles) == 3
    assert ca.best_match("the moon", titles) is None


# ---- the aws path: validated, and always falls back ----------------------------------------------


class FakeAgent:
    def __init__(self, out):
        self.out = out

    def __call__(self, prompt, structured_output_model=None):
        class R:
            structured_output = self.out

        return R()


def test_bedrock_parse_is_validated_and_marked(monkeypatch):
    monkeypatch.setattr(config, "MODE", "aws")
    out = ca.ChoreParse(title="Clean gutters", category="yard", minutes=60, due="2026-10-10")
    monkeypatch.setattr(huddle_agent, "_make_agent", lambda system: FakeAgent(out))
    got = ca.parse_chore_engine("clean the gutters by Saturday", TODAY)
    assert got["engine"] == "bedrock" and got["fields"]["minutes"] == 60 and got["assumed"] == []


def test_bedrock_failure_falls_back_and_says_so(monkeypatch):
    monkeypatch.setattr(config, "MODE", "aws")
    monkeypatch.setattr(
        huddle_agent, "_make_agent", lambda s: (_ for _ in ()).throw(RuntimeError("no credentials"))
    )
    got = ca.parse_chore_engine("clean the gutters by Saturday", TODAY)
    assert got["engine"] == "mock-fallback" and "no credentials" in got["engine_error"]
    assert got["fields"]["category"] == "yard"


def test_mock_mode_never_builds_an_agent(monkeypatch):
    monkeypatch.setattr(config, "MODE", "mock")
    monkeypatch.setattr(huddle_agent, "_make_agent", lambda s: pytest.fail("no agent in mock mode"))
    assert ca.parse_chore_engine("do the dishes", TODAY)["engine"] == "mock"


# ---- talking to the household --------------------------------------------------------------------

MON = datetime(2026, 10, 5, 9, 0, 0)


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, **kw):
        from server import notify

        self.calls.append(kw)
        return [notify.Delivery("in_app", "queued", "")]


@pytest.fixture
def home(session):
    out = hm.create_household(session, "Home", [{"name": "Maya"}, {"name": "Ben"}, {"name": "Chen"}], MON)
    return {m["name"]: m["token"] for m in out["members"]}


def talk(session, home, who, text, rec):
    return hm.say(session, home[who], text, MON, rec)


def test_a_chore_added_by_voice_is_held_then_planned_then_asked_about(session, home):
    rec = Recorder()
    out = talk(session, home, "Maya", "add clean the gutters by Saturday, about an hour", rec)
    assert "Added 'Clean the gutters'" in out["say"] and "planned" in out["say"] and out["state_changed"]
    assert talk(session, home, "Ben", "plan the week", rec)["say"].startswith("Planned the week.")
    later = talk(session, home, "Ben", "add fix the squeaky door", rec)
    assert "I guessed about 60 minutes" in later["say"]
    asked = [n for n in home if hm.get_state(session, home[n], MON)["mine"]["proposals"]]
    assert len(asked) == 1


def test_whats_on_my_plate_who_and_done_work_end_to_end(session, home):
    rec = Recorder()
    for text in (
        "add do the dishes every day, 10 minutes",
        "add do the laundry every week, 30 minutes",
        "add take out the bins every week, 10 minutes",
    ):
        talk(session, home, "Maya", text, rec)
    talk(session, home, "Maya", "plan the week", rec)
    owner = next(
        a["owner"]
        for a in hm.get_state(session, home["Maya"], MON)["plan"]["assignments"]
        if a["title"] == "Take out the bins"
    )
    assert talk(session, home, "Ben", "who has the bins", rec)["say"] == f"{owner} has 'Take out the bins'."
    mine = talk(session, home, owner, "what's on my plate", rec)["say"]
    assert "Take out the bins, 10 minutes" in mine
    other = next(n for n in home if n != owner)
    assert "belongs to someone else" in talk(session, home, other, "I did the bins", rec)["say"]
    assert (
        talk(session, home, owner, "I did the bins", rec)["say"] == "Nice, marked 'Take out the bins' done."
    )
    st = hm.get_state(session, home["Maya"], MON)
    assert next(a for a in st["plan"]["assignments"] if a["title"] == "Take out the bins")["status"] == "done"


def test_handing_back_and_accepting_by_voice(session, home):
    rec = Recorder()
    for text in ("add do the laundry every week, 30 minutes", "add mop the floor every week, 30 minutes"):
        talk(session, home, "Maya", text, rec)
    talk(session, home, "Maya", "plan the week", rec)
    st = hm.get_state(session, home["Maya"], MON)
    laundry = next(a for a in st["plan"]["assignments"] if a["title"] == "Do the laundry")
    owner = laundry["owner"]
    assert "ask someone else" in talk(session, home, owner, "hand back the laundry", rec)["say"]
    asked = next(n for n in home if hm.get_state(session, home[n], MON)["mine"]["proposals"])
    assert asked != owner
    assert "waiting for you" in talk(session, home, asked, "what's on my plate", rec)["say"]
    assert talk(session, home, asked, "I'll take it", rec)["say"] == "Okay, 'Do the laundry' is yours."
    assert talk(session, home, asked, "accept", rec)["say"] == "Nothing is waiting on you."


def test_replies_never_reveal_private_preferences_or_availability(session, home):
    rec = Recorder()
    hm.set_profile(
        session,
        home["Maya"],
        {"availability": 437, "keywords": ["sentinelplumbing"], "prefs": {"cooking": "cannot"}},
        MON,
    )
    for text in ("add cook dinner every week, 60 minutes", "add fix the sink, 30 minutes", "plan the week"):
        talk(session, home, "Ben", text, rec)
    blob = ""
    for who in home:
        for text in (
            "what's on my plate",
            "what's the plan",
            "who has the dinner",
            "who has the sink",
            "I did the sink",
            "hand back the sink",
            "hello",
        ):
            blob += talk(session, home, who, text, rec)["say"]
    assert "437" not in blob and "sentinelplumbing" not in blob.lower() and "cannot" not in blob.lower()


def test_unknown_gets_a_useful_help_line(session, home):
    out = talk(session, home, "Maya", "sing me a song", Recorder())
    assert out["intent"] == "unknown" and "add a chore" in out["say"] and not out["state_changed"]


def test_a_chore_with_no_title_asks_what_it_is(session, home):
    out = talk(session, home, "Maya", "add", Recorder())
    assert out["say"] == "What's the chore?" and out["state_changed"] is False
    assert json.dumps(hm.get_state(session, home["Maya"], MON)["chores"]) == "[]"
