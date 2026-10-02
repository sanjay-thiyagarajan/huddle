"""Check-in, audit trail and trip mode."""
from datetime import datetime, timedelta

import pytest

from server.engine import rounds

T0 = datetime(2026, 10, 10, 9, 0, 0)
PEOPLE = [{"name": "Maya"}, {"name": "Ben"}, {"name": "Chen"}]


def ev(budget, **kw):
    return {"consent": True, "budget_ceiling": budget, "vibe": kw.get("vibe", []),
            "must_haves": [], "dealbreakers": kw.get("deal", [])}


def closed_round(session, mode="everyday", people=PEOPLE, answer=ev(200)):
    r = rounds.create_round(session, mode, people, 3600, now=T0)
    tok = {p["name"]: p["token"] for p in r["participants"]}
    for t in tok.values():
        rounds.submit_answer(session, t, answer, T0)
    return tok


def test_checkin_only_after_close_single_use_and_validated(session):
    r = rounds.create_round(session, "everyday", PEOPLE, 3600, now=T0)
    tok = {p["name"]: p["token"] for p in r["participants"]}
    with pytest.raises(rounds.HuddleError) as e:
        rounds.submit_checkin(session, tok["Maya"], 4, T0)
    assert e.value.code == "not_closed"
    for t in tok.values():
        rounds.submit_answer(session, t, ev(200), T0)
    for bad in (0, 6, True, "3"):
        with pytest.raises(rounds.HuddleError) as e:
            rounds.submit_checkin(session, tok["Maya"], bad, T0)
        assert e.value.code == "invalid_score"
    rounds.submit_checkin(session, tok["Maya"], 4, T0)
    with pytest.raises(rounds.HuddleError) as e:
        rounds.submit_checkin(session, tok["Maya"], 5, T0)
    assert e.value.code == "already_checked_in"


def test_checkin_summary_hidden_until_everyone_then_unattributed(session):
    tok = closed_round(session)
    first = rounds.submit_checkin(session, tok["Maya"], 5, T0)["summary"]
    assert first == {"checked_in": 1, "of": 3, "complete": False}  # nothing revealed early
    rounds.submit_checkin(session, tok["Ben"], 4, T0)
    done = rounds.submit_checkin(session, tok["Chen"], 2, T0)["summary"]
    assert done["complete"] and done["revisit"] is True and "not comfortable" in done["message"]
    assert done["comfortable_count"] == 2
    assert "Maya" not in str(done) and "Chen" not in str(done)
    assert rounds.get_result(session, tok["Ben"], T0)["checkin"] == done


def test_checkin_two_person_warning_and_no_count(session):
    tok = closed_round(session, people=PEOPLE[:2])
    rounds.submit_checkin(session, tok["Maya"], 5, T0)
    done = rounds.submit_checkin(session, tok["Ben"], 5, T0)["summary"]
    assert "infer your number" in done["warning"] and "comfortable_count" not in done
    assert done["revisit"] is False


def test_audit_trail_records_who_and_when_but_never_values(session):
    r = rounds.create_round(session, "everyday", PEOPLE, 3600, now=T0)
    tok = {p["name"]: p["token"] for p in r["participants"]}
    rounds.submit_answer(session, tok["Maya"], ev(437), T0 + timedelta(minutes=1))
    rounds.status(session, tok["Ben"], T0 + timedelta(minutes=31))          # reminder fires
    rounds.status(session, tok["Ben"], T0 + timedelta(hours=1, seconds=1))  # deadline: defaults
    events = rounds.status(session, tok["Ben"], T0 + timedelta(hours=2))["events"]
    assert [e["kind"] for e in events] == ["opened", "answered", "reminded", "closed"]
    assert events[1]["actor"] == "Maya" and "defaults" in events[3]["detail"]
    assert "437" not in str(events)


def test_trip_mode_same_engine_new_catalogue(session):
    answers = [ev(400, vibe=["beach"], deal=["flights"]), ev(900, vibe=["foodie"]),
               ev(350, vibe=["relaxed"], deal=["camping"])]
    r = rounds.create_round(session, "trip", PEOPLE, 3600, now=T0)
    for p, a in zip(r["participants"], answers, strict=True):
        rounds.submit_answer(session, p["token"], a, T0)
    res = rounds.get_result(session, r["participants"][0]["token"], T0)["result"]
    assert res["mode"] == "trip" and res["plan"]["name"] == "Beach house on the coast"
    assert res["plan"]["price_band"] == "$250-500"
    status = rounds.status(session, r["participants"][0]["token"], T0)
    assert any(o["id"] == "coast" for o in status["options"])


def test_trip_rejects_everyday_vocabulary(session):
    r = rounds.create_round(session, "trip", PEOPLE, 3600, now=T0)
    with pytest.raises(rounds.HuddleError) as e:
        rounds.submit_answer(session, r["participants"][0]["token"], ev(100, deal=["crowds"]), T0)
    assert e.value.code == "invalid_answer"


# ---- revisit round, fairness record, plan card ------------------------------------------------

def care_answer(hours, dollars=100, *deal):
    return {"consent": True, "hours_per_week": hours, "dollars_per_month": dollars,
            "dealbreakers": list(deal)}


def test_revisit_rules_and_nothing_carries_over(session):
    tok = closed_round(session)
    with pytest.raises(rounds.HuddleError) as e:
        rounds.revisit_round(session, tok["Ben"], now=T0)
    assert e.value.code == "host_only"
    open_round = rounds.create_round(session, "everyday", PEOPLE, 3600, now=T0)
    with pytest.raises(rounds.HuddleError) as e:
        rounds.revisit_round(session, open_round["participants"][0]["token"], now=T0)
    assert e.value.code == "not_closed"

    nxt = rounds.revisit_round(session, tok["Maya"], now=T0)
    new_tok = {p["name"]: p["token"] for p in nxt["participants"]}
    assert set(new_tok) == set(tok) and all(new_tok[n] != tok[n] for n in tok)
    st = rounds.status(session, new_tok["Maya"], T0)
    assert st["state"] == "collecting" and st["me"]["answered"] is False
    assert rounds.my_answers(session, new_tok["Maya"], T0)["answer"] is None  # fresh start
    assert any("follow-up to round" in (e["detail"] or "") for e in st["events"])
    assert rounds.status(session, tok["Maya"], T0)["round_id"] != st["round_id"]  # old round untouched


def test_revisit_can_change_the_care_need(session):
    r = rounds.create_round(session, "care", PEOPLE, 3600, now=T0)
    tok = {p["name"]: p["token"] for p in r["participants"]}
    rounds.close_round(session, tok["Maya"], T0)
    need = {"tasks": [{"id": "x", "label": "Daily check-in", "type": "checkin", "hours": 4}],
            "dollars_per_month": 900}
    nxt = rounds.revisit_round(session, tok["Maya"], need=need, now=T0)
    st = rounds.status(session, nxt["participants"][0]["token"], T0)
    assert st["need"]["dollars_per_month"] == 900 and len(st["need"]["tasks"]) == 1


HEAVY_NEED = {"tasks": [{"id": "night", "label": "Overnight cover", "type": "overnight", "hours": 6},
                        {"id": "calls", "label": "Daily check-in", "type": "checkin", "hours": 2}],
              "dollars_per_month": 0}


def run_care_round(session, first_tokens, answers):
    for name, tok in first_tokens.items():
        rounds.submit_answer(session, tok, answers[name], T0)
    return rounds.get_result(session, next(iter(first_tokens.values())), T0)["result"]


def test_fairness_rotates_heavy_tasks_between_equally_able_people(session):
    people = [{"name": "Maya"}, {"name": "Ben"}, {"name": "Chen"}]
    answers = {"Maya": care_answer(8), "Ben": care_answer(8), "Chen": care_answer(0)}
    r1 = rounds.create_round(session, "care", people, 3600, need=HEAVY_NEED, now=T0)
    t1 = {p["name"]: p["token"] for p in r1["participants"]}
    res1 = run_care_round(session, t1, answers)
    assert res1["fairness"] is None  # no history yet
    h1 = res1["heavy_hours_this_plan"]
    assert h1["Maya"] + h1["Ben"] == 6 and h1["Maya"] != h1["Ben"]  # overnight is split unevenly
    heavier = max(("Maya", "Ben"), key=h1.get)

    r2 = rounds.revisit_round(session, t1["Maya"], now=T0)
    t2 = {p["name"]: p["token"] for p in r2["participants"]}
    res2 = run_care_round(session, t2, answers)
    h2 = res2["heavy_hours_this_plan"]
    assert h2[heavier] < h2["Maya" if heavier == "Ben" else "Ben"]  # the bigger share rotated
    assert res2["fairness"]["plans"] == 2
    assert res2["fairness"]["heavy_hours"]["Maya"] == res2["fairness"]["heavy_hours"]["Ben"] == 6
    assert "never anyone's private limits" in res2["fairness"]["note"]
    assert res2["fairness"]["heavy_hours"]["Chen"] == 0


def test_fairness_never_costs_coverage_or_breaks_limits():
    from server.engine import care
    tasks = care.DEFAULT_NEED["tasks"]
    answers = [care_answer(12, 0, "nights"), care_answer(8, 0, "far_away"), care_answer(6, 0, "transport")]
    base = care.solve(tasks, answers)
    biased = care.solve(tasks, answers, prior_heavy=[40, 0, 5])
    assert sum(map(sum, (s.values() for s in base))) == sum(map(sum, (s.values() for s in biased)))
    for s, a in zip(biased, answers, strict=True):
        assert sum(s.values()) <= a["hours_per_week"]
        blocked = care._blocked(a)
        assert all(next(t for t in tasks if t["id"] == tid)["type"] not in blocked for tid in s)


def test_fairness_history_is_isolated_per_household(session):
    people = [{"name": "Maya"}, {"name": "Ben"}, {"name": "Chen"}]
    answers = {"Maya": care_answer(8), "Ben": care_answer(8), "Chen": care_answer(0)}
    a = rounds.create_round(session, "care", people, 3600, need=HEAVY_NEED, now=T0)
    run_care_round(session, {p["name"]: p["token"] for p in a["participants"]}, answers)
    # An unrelated group using the same names starts its own chain and sees no history.
    b = rounds.create_round(session, "care", people, 3600, need=HEAVY_NEED, now=T0)
    res = run_care_round(session, {p["name"]: p["token"] for p in b["participants"]}, answers)
    assert res["fairness"] is None


def test_plan_card_is_aggregate_only_and_needs_a_closed_round(session):
    r = rounds.create_round(session, "care", PEOPLE, 3600, now=T0)
    tok = {p["name"]: p["token"] for p in r["participants"]}
    with pytest.raises(rounds.HuddleError) as e:
        rounds.plan_card(session, tok["Maya"], T0)
    assert e.value.code == "not_ready"
    dollars = {"Maya": 437, "Ben": 613, "Chen": 829}
    for name, hours in (("Maya", 13.5), ("Ben", 17.5), ("Chen", 11.5)):
        rounds.submit_answer(session, tok[name], care_answer(hours, dollars[name]), T0)
    card = rounds.plan_card(session, tok["Ben"], T0)
    assert set(card) == {"title", "text", "markdown"}
    for secret in ("13.5", "17.5", "11.5", "437", "613", "829"):
        assert secret not in card["text"]
    assert "not medical, legal or financial advice" in card["text"]
    assert "never shown or attributed" in card["text"]
    assert card["markdown"].startswith("# Care plan")


def test_plan_card_everyday_and_checkin_line(session):
    tok = closed_round(session)
    for name, score in zip(tok, (5, 4, 4), strict=True):
        rounds.submit_checkin(session, tok[name], score, T0)
    card = rounds.plan_card(session, tok["Maya"], T0)
    assert card["title"] == "Weekend plan" and "Day-after check-in: Everyone is comfortable" in card["text"]
