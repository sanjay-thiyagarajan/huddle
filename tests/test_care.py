import random
from datetime import datetime

from server.engine import care, rounds

T0 = datetime(2026, 10, 10, 9, 0, 0)
TASKS = care.DEFAULT_NEED["tasks"]


def a(hours, dollars, *deal):
    return {"hours_per_week": hours, "dollars_per_month": dollars, "dealbreakers": list(deal)}


def hours_by_person(split):
    return [sum(s.values()) for s in split]


def assert_valid(split, answers):
    """Every private limit is respected and no task is over-filled."""
    for s, ans in zip(split, answers):
        assert sum(s.values()) <= int(ans["hours_per_week"])
        blocked = care._blocked(ans)
        for tid in s:
            assert next(t for t in TASKS if t["id"] == tid)["type"] not in blocked
    for t in TASKS:
        assert sum(s.get(t["id"], 0) for s in split) <= t["hours"]


# Three siblings. Totals: 26 h and $1,500 against a need of 30 h and $1,800.
SCENARIO = [("Maya", a(12, 600, "nights")), ("Ben", a(8, 500, "far_away")),
            ("Chen", a(6, 400, "transport"))]


def test_three_person_scenario_expected_gap_and_valid_split():
    split = care.solve(TASKS, [x for _, x in SCENARIO])
    assert_valid(split, [x for _, x in SCENARIO])
    # Only Chen can cover overnight, only Maya appointments: the forced assignments.
    assert split[2].get("overnight") == 6
    assert split[0].get("appointments") == 6
    assert sum(hours_by_person(split)) == 26  # 4 h gap

    res = care.compute(SCENARIO, care.DEFAULT_NEED)
    assert res["gap_hours_bucket"] == "0-5 h"
    assert res["gap_dollars_bucket"] == "$250-500"  # $300 gap
    assert res["need"] == {"hours_per_week": 30, "dollars_per_month": 1800}
    assert res["options"] and res["unfilled_tasks"]
    assert "not medical, legal or financial advice" in res["disclaimer"]
    assert "hint at what a person is able to do" in res["assignment_caveat"]


def test_infeasible_inputs_give_a_gap_not_an_error():
    nobody = [a(0, 0), a(0, 0), a(0, 0)]
    split = care.solve(TASKS, nobody)
    assert hours_by_person(split) == [0, 0, 0]
    res = care.compute([(f"P{i}", x) for i, x in enumerate(nobody)], care.DEFAULT_NEED)
    assert res["gap_hours_bucket"] == "30-35 h" and res["assignments"] == []


def test_dealbreaker_conflict_leaves_task_unfilled_despite_spare_hours():
    everyone_no_nights = [a(40, 100, "nights") for _ in range(3)]
    split = care.solve(TASKS, everyone_no_nights)
    assert_valid(split, everyone_no_nights)
    assert sum(s.get("overnight", 0) for s in split) == 0
    assert sum(hours_by_person(split)) == 24  # everything except the 6 overnight hours


def test_spare_capacity_covers_everything_and_load_is_spread():
    answers = [a(20, 1000), a(20, 1000), a(20, 1000)]
    split = care.solve(TASKS, answers)
    assert sum(hours_by_person(split)) == 30
    assert max(hours_by_person(split)) <= 12  # not dumped on one person


def test_random_inputs_never_violate_limits():
    rng = random.Random(7)
    kinds = list(care.BLOCKS)
    for _ in range(40):
        answers = [a(rng.randint(0, 25), rng.randint(0, 900),
                     *rng.sample(kinds, rng.randint(0, 3))) for _ in range(rng.randint(2, 5))]
        assert_valid(care.solve(TASKS, answers), answers)


def test_non_responder_defaults_state_it_and_widen_the_gap(session):
    r = rounds.create_round(session, "care", [{"name": "Maya"}, {"name": "Ben"}, {"name": "Chen"}],
                            3600, now=T0)
    t = {p["name"]: p["token"] for p in r["participants"]}
    for name, ans in SCENARIO[:2]:
        rounds.submit_answer(session, t[name], {**ans, "consent": True}, T0)
    res = rounds.close_round(session, t["Maya"], T0)["result"]
    assert res["defaults_applied"] is True and "0 hours and $0" in res["defaults_note"]
    assert res["gap_dollars_bucket"] == "$500-1000"  # 1800 - 1100 = 700


def test_create_care_round_validates_need_and_health_labels(session):
    bad = {"tasks": [{"id": "x", "label": "Dialysis runs", "type": "appointments", "hours": 3}],
           "dollars_per_month": 100}
    try:
        rounds.create_round(session, "care", [{"name": "A"}, {"name": "B"}], 3600, need=bad, now=T0)
    except rounds.HuddleError as e:
        assert e.code == "bad_need"
    else:
        raise AssertionError("health-detail label should be rejected")


# ---- the group result never shows per-person hours; each person sees only their own ---------------

def _closed_care(session, answers, need=None):
    from datetime import datetime

    t0 = datetime(2026, 10, 10, 9, 0, 0)
    people = [{"name": n} for n in answers]
    r = rounds.create_round(session, "care", people, 3600, need=need, now=t0)
    tok = {p["name"]: p["token"] for p in r["participants"]}
    for name, ans in answers.items():
        rounds.submit_answer(session, tok[name], {**ans, "consent": True}, t0)
    return tok, t0


SCENARIO_ANSWERS = {"Maya": a(12, 600, "nights"), "Ben": a(8, 500, "far_away"),
                    "Chen": a(6, 400, "transport")}


def test_group_result_has_ownership_but_no_per_person_hours(session):
    tok, t0 = _closed_care(session, SCENARIO_ANSWERS)
    res = rounds.get_result(session, tok["Maya"], t0)["result"]
    for a_ in res["assignments"]:
        assert set(a_) == {"name", "tasks"}
        for t in a_["tasks"]:
            assert set(t) == {"task_id", "label", "shared"}  # no hours key
    flat = str(res)
    assert "heavy_hours" not in flat and "_private" not in flat and "my_share" not in flat
    card = rounds.plan_card(session, tok["Maya"], t0)["text"]
    lines = card.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("Who owns what"))
    block = []
    for ln in lines[start + 1:]:
        if not ln.startswith("  ") or ln.startswith("  Still open"):
            break
        block.append(ln)
    assert len(block) == 3 and not any(ch.isdigit() for ln in block for ch in ln)  # owners only, no hours


def test_each_person_gets_only_their_own_hours(session):
    tok, t0 = _closed_care(session, SCENARIO_ANSWERS)
    shares = {n: rounds.get_result(session, tok[n], t0)["my_share"] for n in tok}
    res = rounds.get_result(session, tok["Maya"], t0)["result"]
    owners = {a_["name"]: {t["task_id"] for t in a_["tasks"]} for a_ in res["assignments"]}
    for name, mine in shares.items():
        # Your share lists exactly the tasks you own, nothing else
        assert {x["task_id"] for x in mine} == owners.get(name, set())
        assert all(set(x) == {"task_id", "label", "hours"} for x in mine)
    # Together the shares cover the hours the plan fills (26 of 30 here), and Maya's token never
    # returns Ben's or Chen's rows
    assert sum(x["hours"] for mine in shares.values() for x in mine) == 26
    assert shares["Chen"] == [{"task_id": "overnight", "label": "Overnight cover", "hours": 6}]
    assert "Overnight cover" not in str(shares["Maya"]) and "Meals" not in str(shares["Chen"])


def test_sole_owner_still_hints_at_capacity_and_the_caveat_says_so(session):
    tok, t0 = _closed_care(session, SCENARIO_ANSWERS)
    res = rounds.get_result(session, tok["Maya"], t0)["result"]
    # Chen alone owns overnight cover (6 h): everyone can infer Chen can do at least 6 h. We say so.
    chen = next(a_ for a_ in res["assignments"] if a_["name"] == "Chen")
    assert [(t["label"], t["shared"]) for t in chen["tasks"]] == [("Overnight cover", False)]
    assert "owns a task alone can cover at least that task's hours" in res["assignment_caveat"]
    assert "never anyone's hours" in res["assignment_caveat"]


def test_random_inputs_never_put_hours_in_the_group_result(session):
    import random

    rng = random.Random(3)
    kinds = list(care.BLOCKS)
    for _ in range(12):
        answers = {f"P{i}": a(rng.randint(0, 25), rng.randint(0, 900), *rng.sample(kinds, rng.randint(0, 2)))
                   for i in range(rng.randint(3, 5))}
        tok, t0 = _closed_care(session, answers)
        res = rounds.get_result(session, next(iter(tok.values())), t0)["result"]
        assert all("hours" not in t for a_ in res["assignments"] for t in a_["tasks"])
        assert "heavy_hours" not in str(res)
