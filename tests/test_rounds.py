from datetime import datetime, timedelta

import pytest

from server.engine import rounds

T0 = datetime(2026, 10, 10, 9, 0, 0)
PEOPLE = [{"name": "Maya"}, {"name": "Ben", "channel": "link"}, {"name": "Chen"}]


def answer(budget, **kw):
    return {"consent": True, "budget_ceiling": budget, "vibe": kw.get("vibe", []),
            "must_haves": kw.get("must", []), "dealbreakers": kw.get("deal", [])}


def tokens(r):
    return {p["name"]: p["token"] for p in r["participants"]}


def test_full_round_closes_when_everyone_answers(session):
    r = rounds.create_round(session, "everyday", PEOPLE, 3600, now=T0)
    t = tokens(r)
    rounds.submit_answer(session, t["Maya"], answer(200, vibe=["foodie"]), T0)
    rounds.submit_answer(session, t["Ben"], answer(300, vibe=["relaxed"]), T0)
    out = rounds.submit_answer(session, t["Chen"], answer(150, vibe=["foodie"], deal=["crowds"]), T0)
    assert out["round_state"] == "closed"
    res = rounds.get_result(session, t["Maya"], T0)["result"]
    assert res["plan"]["name"] == "Museum and a sit-down dinner"
    assert res["defaults_applied"] is False


def test_lifecycle_remind_then_defaults_at_deadline(session):
    r = rounds.create_round(session, "everyday", PEOPLE, 3600, now=T0)
    t = tokens(r)
    rounds.submit_answer(session, t["Maya"], answer(200), T0)
    rounds.submit_answer(session, t["Ben"], answer(100), T0)
    assert rounds.status(session, t["Maya"], T0)["state"] == "collecting"
    assert rounds.status(session, t["Maya"], T0 + timedelta(minutes=31))["state"] == "reminded"
    assert rounds.nudge_pending(session, t["Maya"], T0 + timedelta(minutes=31))["pending"] == ["Chen"]
    late = T0 + timedelta(hours=1, seconds=1)
    res = rounds.get_result(session, t["Maya"], late)
    assert res["state"] == "closed" and res["result"]["defaults_applied"] is True


def test_single_use_consent_and_validation(session):
    t = tokens(rounds.create_round(session, "everyday", PEOPLE, 3600, now=T0))
    with pytest.raises(rounds.HuddleError) as e:
        rounds.submit_answer(session, t["Maya"], {**answer(100), "consent": False}, T0)
    assert e.value.code == "consent_required"
    with pytest.raises(rounds.HuddleError) as e:
        rounds.submit_answer(session, t["Maya"], answer(-5), T0)
    assert e.value.code == "invalid_answer"
    rounds.submit_answer(session, t["Maya"], answer(100), T0)
    with pytest.raises(rounds.HuddleError) as e:
        rounds.submit_answer(session, t["Maya"], answer(100), T0)
    assert e.value.code == "already_answered"


def test_tokens_forged_expired_and_host_only(session):
    t = tokens(rounds.create_round(session, "everyday", PEOPLE, 3600, now=T0))
    with pytest.raises(rounds.HuddleError):
        rounds.status(session, t["Maya"][:-2] + "xx", T0)
    with pytest.raises(rounds.HuddleError) as e:
        rounds.status(session, t["Maya"], T0 + timedelta(days=3))
    assert e.value.code == "token_expired"
    with pytest.raises(rounds.HuddleError) as e:
        rounds.close_round(session, t["Ben"], T0)
    assert e.value.code == "host_only"


def test_health_note_is_not_stored_and_warns(session):
    t = tokens(rounds.create_round(session, "everyday", PEOPLE, 3600, now=T0))
    out = rounds.submit_answer(session, t["Maya"], {**answer(100), "note": "she has dementia"}, T0)
    assert out["warnings"]
    assert "dementia" not in str(rounds.my_answers(session, t["Maya"], T0))


def test_two_person_everyday_shows_warning_and_hides_bucket(session):
    t = tokens(rounds.create_round(session, "everyday", PEOPLE[:2], 3600, now=T0))
    rounds.submit_answer(session, t["Maya"], answer(200, vibe=["foodie"]), T0)
    rounds.submit_answer(session, t["Ben"], answer(100, vibe=["foodie"]), T0)
    res = rounds.get_result(session, t["Maya"], T0)["result"]
    assert res["warnings"] and res["group_budget_bucket"] is None


def test_everyday_tradeoff_names_nobody(session):
    t = tokens(rounds.create_round(session, "everyday", PEOPLE, 3600, now=T0))
    rounds.submit_answer(session, t["Maya"], answer(500, vibe=["foodie", "social"], must=["alcohol"]), T0)
    rounds.submit_answer(session, t["Ben"], answer(500, vibe=["foodie", "cultural"]), T0)
    rounds.submit_answer(session, t["Chen"], answer(60, vibe=["foodie"]), T0)
    res = rounds.get_result(session, t["Maya"], T0)["result"]
    assert "budget" in res["tradeoff"]
    assert not any(n in res["tradeoff"] for n in ("Maya", "Ben", "Chen"))
