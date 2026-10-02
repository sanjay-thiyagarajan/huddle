"""One household identity: family decisions started from a household, and care flowing into chores."""

import json
from datetime import datetime, timedelta

import pytest

from server import notify
from server.engine import home as hm
from server.engine import rounds

MON = datetime(2026, 10, 5, 9, 0, 0)
NAMES = ["Maya", "Ben", "Chen"]
CARE_NEED = {
    "tasks": [
        {"id": "night", "label": "Overnight cover", "type": "overnight", "hours": 6},
        {"id": "calls", "label": "Daily check-in", "type": "checkin", "hours": 2},
    ],
    "dollars_per_month": 300,
}


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, **kw):
        self.calls.append(kw)
        return [notify.Delivery("in_app", "queued", "")]


@pytest.fixture
def rec():
    return Recorder()


def make_home(session, emails=None):
    members = [{"name": n, **({"email": emails[n]} if emails and n in emails else {})} for n in NAMES]
    out = hm.create_household(session, "Home", members, MON)
    return {m["name"]: m["token"] for m in out["members"]}


def state(session, tok, who, now=MON):
    return hm.get_state(session, tok[who], now)


def my_decision(session, tok, who, index=0):
    return state(session, tok, who)["mine"]["decisions"][index]


def answer_care(session, tok, hours):
    for who, h in hours.items():
        d = my_decision(session, tok, who)
        rounds.submit_answer(
            session,
            d["token"],
            {"consent": True, "hours_per_week": h, "dollars_per_month": 100, "dealbreakers": []},
            MON,
        )


# ---- one identity ------------------------------------------------------------------------------------------


def test_a_decision_is_started_for_the_same_people_with_no_retyping(session, rec):
    tok = make_home(session)
    out = hm.start_decision(session, tok["Maya"], "everyday", 3600, None, ["Chen"], MON, rec)
    assert set(out) == {"round_id", "mode", "deadline_at", "my_token", "my_link"}  # only the starter's token
    seen = {}
    for who in NAMES:
        d = my_decision(session, tok, who)
        seen[who] = d["token"]
        status = rounds.status(session, d["token"], MON)  # the round token is that member's own participant
        assert status["me"]["name"] == who and status["mode"] == "everyday"
        assert {p["name"] for p in status["participants"]} == set(NAMES)
    assert len(set(seen.values())) == 3 and seen["Maya"] == out["my_token"]
    maya = rounds.status(session, seen["Maya"], MON)
    assert maya["me"]["is_host"] is True
    assert next(p for p in maya["participants"] if p["name"] == "Chen")["channel"] == "link"
    assert next(p for p in maya["participants"] if p["name"] == "Ben")["channel"] == "voice"


def test_nobody_ever_sees_another_members_round_token(session, rec):
    tok = make_home(session)
    out = hm.start_decision(session, tok["Maya"], "everyday", 3600, None, None, MON, rec)
    others = {w: my_decision(session, tok, w)["token"] for w in ("Ben", "Chen")}
    maya_view = json.dumps(state(session, tok, "Maya")) + json.dumps(out)
    for t in others.values():
        assert t not in maya_view
    assert others["Ben"] not in json.dumps(state(session, tok, "Chen"))


def test_other_members_are_notified_without_names_or_private_data(session, rec):
    tok = make_home(session)
    hm.start_decision(session, tok["Maya"], "care", 3600, CARE_NEED, None, MON, rec)
    assert sorted(c["name"] for c in rec.calls if c["kind"] == "decision") == ["Ben", "Chen"]
    for c in rec.calls:
        blob = json.dumps({k: v for k, v in c.items() if k != "email"})
        assert not any(n in blob for n in NAMES if n != c["name"])


def test_answering_with_the_members_token_closes_it_and_it_appears_in_the_household_history(session, rec):
    tok = make_home(session)
    hm.start_decision(session, tok["Maya"], "everyday", 3600, None, None, MON, rec)
    for who in NAMES:
        d = my_decision(session, tok, who)
        assert d["answered"] is False and d["of"] == 3
        rounds.submit_answer(
            session,
            d["token"],
            {"consent": True, "budget_ceiling": 437, "vibe": [], "must_haves": [], "dealbreakers": []},
            MON,
        )
    st = state(session, tok, "Ben")
    assert st["mine"]["decisions"][0]["state"] == "closed" and st["mine"]["decisions"][0]["answered"] is True
    assert [p["mode"] for p in st["plans_so_far"]] == ["everyday"]
    assert "437" not in json.dumps(st["plans_so_far"])  # aggregate only


def test_open_decisions_show_progress_to_the_household(session, rec):
    tok = make_home(session)
    hm.start_decision(session, tok["Maya"], "everyday", 3600, None, None, MON, rec)
    d = my_decision(session, tok, "Maya")
    rounds.submit_answer(
        session,
        d["token"],
        {"consent": True, "budget_ceiling": 50, "vibe": [], "must_haves": [], "dealbreakers": []},
        MON,
    )
    assert my_decision(session, tok, "Ben")["answered_count"] == 1
    assert my_decision(session, tok, "Ben")["answered"] is False


def test_decisions_started_here_share_the_households_history_and_hints(session, rec):
    tok = make_home(session)
    hm.start_decision(session, tok["Maya"], "care", 3600, CARE_NEED, None, MON, rec)
    answer_care(session, tok, {"Maya": 8, "Ben": 0, "Chen": 0})
    hm.start_decision(session, tok["Maya"], "trip", 3600, None, None, MON + timedelta(hours=1), rec)
    d = state(session, tok, "Maya", MON + timedelta(hours=1))["mine"]["decisions"][0]
    hints = rounds.status(session, d["token"], MON + timedelta(hours=1))["hints"]
    assert hints and "heavy tasks" in hints[0]["message"]  # the care load reaches the trip decision
    ben = state(session, tok, "Ben", MON + timedelta(hours=1))["mine"]["decisions"][0]["token"]
    assert rounds.status(session, ben, MON + timedelta(hours=1))["hints"] == []


def test_member_emails_carry_over_to_round_reminders_and_are_never_returned(session, rec):
    tok = make_home(session, {"Ben": "ben.sentinel@example.test"})
    out = hm.start_decision(session, tok["Maya"], "everyday", 3600, None, None, MON, rec)
    assert "ben.sentinel" not in json.dumps(out) + json.dumps(state(session, tok, "Maya"))
    sent = []

    def capture(**kw):
        sent.append(kw)
        return [notify.Delivery("in_app", "queued", "")]

    rounds.tick(session, MON + timedelta(minutes=31), capture)
    assert {c["name"]: c["email"] for c in sent} == {
        "Maya": None,
        "Ben": "ben.sentinel@example.test",
        "Chen": None,
    }


# ---- care flows into chores -------------------------------------------------------------------------------


def seed_chores(session, tok, rec):
    for who in NAMES:
        hm.set_profile(session, tok[who], {"availability": 600}, MON)
    for i in range(6):
        hm.add_chore(
            session,
            tok["Maya"],
            {"title": f"Chore {i}", "category": "tidying", "minutes": 30, "cadence": "weekly"},
            MON,
            rec,
        )


def chore_minutes(st):
    return st["plan"]["loads_minutes"]


def test_a_person_carrying_care_gets_a_lighter_chore_share(session, rec):
    control = make_home(session)
    seed_chores(session, control, rec)
    even = chore_minutes(hm.plan_week(session, control["Maya"], None, False, MON, rec))
    assert max(even.values()) - min(even.values()) <= 30  # no care: an even split

    tok = make_home(session)
    hm.start_decision(session, tok["Maya"], "care", 3600, CARE_NEED, None, MON, rec)
    answer_care(session, tok, {"Maya": 8, "Ben": 0, "Chen": 0})  # Maya takes all the care: 8 h a week
    seed_chores(session, tok, rec)
    st = hm.plan_week(session, tok["Maya"], None, False, MON, rec)
    mins = chore_minutes(st)
    assert mins.get("Maya", 0) < min(mins["Ben"], mins["Chen"])  # Maya's care is counted
    assert st["plan"]["report"]["care_counted"] is True
    assert "Care already taken on is counted" in st["plan"]["headline"]
    assert state(session, tok, "Maya")["mine"]["load"]["care_minutes"] == 480
    assert state(session, tok, "Ben")["mine"]["load"]["care_minutes"] == 0


def test_care_in_chores_uses_only_public_ownership_never_private_hours(session, rec):
    tok = make_home(session)
    hm.start_decision(session, tok["Maya"], "care", 3600, CARE_NEED, None, MON, rec)
    answer_care(session, tok, {"Maya": 13.5, "Ben": 17.5, "Chen": 11.5})  # distinctive private hours
    shares = {
        w: [x for x in rounds.get_result(session, my_decision(session, tok, w)["token"], MON)["my_share"]]
        for w in NAMES
    }
    result = rounds.get_result(session, my_decision(session, tok, "Maya")["token"], MON)["result"]
    # the estimate is computed from the public result (owners and the tasks' total hours)...
    owners = {}
    for a in result["assignments"]:
        for t in a["tasks"]:
            owners[t["task_id"]] = owners.get(t["task_id"], 0) + 1
    expect = {
        a["name"]: round(
            sum(t_hours(CARE_NEED, t["task_id"]) * 60 / owners[t["task_id"]] for t in a["tasks"])
        )
        for a in result["assignments"]
    }
    for who in NAMES:
        assert state(session, tok, who)["mine"]["load"]["care_minutes"] == expect.get(who, 0)
    # ...and no member's household state contains anyone's private hours
    for who in NAMES:
        blob = json.dumps(state(session, tok, who))
        assert not any(secret in blob for secret in ("13.5", "17.5", "11.5"))
    assert shares  # the private shares exist; they are simply not used here


def t_hours(need, task_id):
    return next(t["hours"] for t in need["tasks"] if t["id"] == task_id)


def test_a_shared_care_task_is_split_evenly_as_an_estimate(session, rec):
    tok = make_home(session)
    need = {
        "tasks": [{"id": "meals", "label": "Meals", "type": "meals", "hours": 8}],
        "dollars_per_month": 100,
    }
    hm.start_decision(session, tok["Maya"], "care", 3600, need, None, MON, rec)
    answer_care(session, tok, {"Maya": 5, "Ben": 5, "Chen": 0})
    result = rounds.get_result(session, my_decision(session, tok, "Maya")["token"], MON)["result"]
    owners = [a["name"] for a in result["assignments"]]
    assert len(owners) == 2 and result["assignments"][0]["tasks"][0]["shared"] is True
    for who in owners:
        assert state(session, tok, who)["mine"]["load"]["care_minutes"] == 240  # 8 h / 2 owners


def test_care_plans_not_started_from_the_household_do_not_affect_chores(session, rec):
    tok = make_home(session)
    people = [{"name": n} for n in NAMES]
    r = rounds.create_round(session, "care", people, 3600, need=CARE_NEED, now=MON)
    for p in r["participants"]:
        rounds.submit_answer(
            session,
            p["token"],
            {"consent": True, "hours_per_week": 8, "dollars_per_month": 1, "dealbreakers": []},
            MON,
        )
    seed_chores(session, tok, rec)
    st = hm.plan_week(session, tok["Maya"], None, False, MON, rec)
    assert st["plan"]["report"]["care_counted"] is False
    assert state(session, tok, "Maya")["mine"]["load"]["care_minutes"] == 0


def test_a_newer_care_plan_replaces_the_older_one(session, rec):
    tok = make_home(session)
    hm.start_decision(session, tok["Maya"], "care", 3600, CARE_NEED, None, MON, rec)
    answer_care(session, tok, {"Maya": 8, "Ben": 0, "Chen": 0})
    assert state(session, tok, "Maya")["mine"]["load"]["care_minutes"] == 480
    later = MON + timedelta(days=1)
    hm.start_decision(session, tok["Ben"], "care", 3600, CARE_NEED, None, later, rec)
    for who, h in {"Maya": 0, "Ben": 8, "Chen": 0}.items():
        d = hm.get_state(session, tok[who], later)["mine"]["decisions"][0]
        rounds.submit_answer(
            session,
            d["token"],
            {"consent": True, "hours_per_week": h, "dollars_per_month": 1, "dealbreakers": []},
            later,
        )
    assert hm.get_state(session, tok["Maya"], later)["mine"]["load"]["care_minutes"] == 0
    assert hm.get_state(session, tok["Ben"], later)["mine"]["load"]["care_minutes"] == 480
