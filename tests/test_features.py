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
