"""Scheduling service: private commitments, conflicts and their resolution, rules, find-a-time."""

import json
from datetime import datetime

import pytest

from server import notify
from server.engine import home as hm
from server.engine import rounds
from server.engine import schedule_service as ss

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


def f(title, circle, day, hh, minutes=60, **kw):
    return {
        "title": title,
        "circle": circle,
        "start": f"2026-10-{day:02d}T{hh:02d}:00",
        "minutes": minutes,
        **kw,
    }


def add(session, tok, who, fields, resolution=None):
    return ss.add_commitment(session, tok[who], fields, resolution, MON, "2026-10-05")


def mytime(session, tok, who):
    return ss.get_my_time(session, tok[who], None, MON, "2026-10-05")


# ---- privacy ---------------------------------------------------------------------------------------------------


def test_commitments_are_private_to_their_owner(session, tok):
    add(session, tok, "Maya", f("Therapy sentinelsecret", "personal", 7, 17))
    assert "sentinelsecret" in json.dumps(mytime(session, tok, "Maya"))
    for other in ("Ben", "Chen"):
        view = json.dumps(mytime(session, tok, other)) + json.dumps(hm.get_state(session, tok[other], MON))
        assert "sentinelsecret" not in view
        assert mytime(session, tok, other)["items"] == []


def test_rules_are_private_and_validated(session, tok):
    ss.set_rules(
        session,
        tok["Maya"],
        {
            "circle_rank": ["family", "friends", "work", "personal"],
            "max_evenings": 2,
            "protected": [{"days": [6], "start": "08:00", "end": "12:00", "label": "Sunday mornings"}],
        },
        MON,
    )
    assert mytime(session, tok, "Maya")["rules"]["max_evenings"] == 2
    assert mytime(session, tok, "Ben")["rules"]["max_evenings"] is None
    for bad in (
        {"circle_rank": ["nope"]},
        {"protected": [{"days": [9], "start": "08:00", "end": "09:00"}]},
        {"protected": [{"days": [1], "start": "10:00", "end": "09:00"}]},
        {"max_evenings": 9},
        {"work_start": "09:00"},
        {"buffer_minutes": 500},
    ):
        with pytest.raises(rounds.HuddleError):
            ss.set_rules(session, tok["Maya"], bad, MON)


def test_only_the_owner_can_change_a_commitment(session, tok):
    cid = add(session, tok, "Maya", f("Dinner", "friends", 8, 19))["commitment"]["id"]
    with pytest.raises(rounds.HuddleError) as e:
        ss.update_commitment(session, tok["Ben"], cid, {"status": "cancelled"}, None, MON)
    assert e.value.code == "not_yours"


# ---- adding, clashes and smart resolution ----------------------------------------------------------------------------


def test_a_free_slot_is_simply_added(session, tok):
    out = add(session, tok, "Maya", f("Dinner with Priya", "friends", 8, 19, 120))
    assert out["created"] is True and out["commitment"]["circle"] == "friends"


def test_a_clash_is_reported_with_options_and_nothing_is_added_until_chosen(session, tok):
    add(session, tok, "Maya", f("School concert", "family", 8, 18, 90, flexibility="fixed", importance=3))
    out = add(session, tok, "Maya", f("Dinner with Priya", "friends", 8, 19, 120))
    assert out["created"] is False
    clash = out["analysis"]["clashes"][0]
    assert clash["title"] == "School concert" and clash["options"]["recommended"] == "move_new"
    assert "family above friends" in clash["options"]["reason"] or "fixed" in clash["options"]["reason"]
    assert len(mytime(session, tok, "Maya")["items"]) == 1


def test_resolving_by_moving_the_new_one_uses_a_suggested_time(session, tok):
    add(session, tok, "Maya", f("School concert", "family", 8, 18, 90, flexibility="fixed"))
    out = add(session, tok, "Maya", f("Dinner with Priya", "friends", 8, 19, 120))
    alt = out["analysis"]["clashes"][0]["options"]["options"][0]["alternatives"][0]
    done = add(
        session,
        tok,
        "Maya",
        f("Dinner with Priya", "friends", 8, 19, 120),
        {"choice": "move_new", "new_start": alt.isoformat() if hasattr(alt, "isoformat") else alt},
    )
    assert done["created"] is True and done["commitment"]["start"] == (
        alt if isinstance(alt, str) else alt.isoformat(timespec="minutes")
    )
    assert mytime(session, tok, "Maya")["conflicts"] == []


def test_dropping_or_keeping_both_and_dropping_the_existing(session, tok):
    add(session, tok, "Maya", f("Book club", "friends", 8, 19))
    clash = f("Pub", "friends", 8, 19)
    assert add(session, tok, "Maya", clash, {"choice": "drop_new"})["created"] is False
    assert len(mytime(session, tok, "Maya")["items"]) == 1
    both = add(session, tok, "Maya", clash, {"choice": "keep_both"})
    assert both["created"] is True and len(mytime(session, tok, "Maya")["conflicts"]) == 1
    add(session, tok, "Maya", f("Book club 2", "friends", 9, 19))
    swapped = add(session, tok, "Maya", f("Film", "personal", 9, 19), {"choice": "drop_existing"})
    assert swapped["created"] is True
    titles = {i["title"] for i in mytime(session, tok, "Maya")["items"]}
    assert "Film" in titles and "Book club 2" not in titles


def test_moving_an_existing_flexible_commitment(session, tok):
    add(session, tok, "Maya", f("Coffee", "personal", 8, 19))
    out = add(session, tok, "Maya", f("Family dinner", "family", 8, 19, flexibility="fixed", importance=3))
    opt = next(o for o in out["analysis"]["clashes"][0]["options"]["options"] if o["key"] == "move_existing")
    new_start = opt["alternatives"][0]
    new_start = new_start if isinstance(new_start, str) else new_start.isoformat(timespec="minutes")
    add(
        session,
        tok,
        "Maya",
        f("Family dinner", "family", 8, 19, flexibility="fixed", importance=3),
        {"choice": "move_existing", "existing_new_start": new_start},
    )
    view = {i["title"]: i for i in mytime(session, tok, "Maya")["items"]}
    assert view["Coffee"]["start"] == new_start and mytime(session, tok, "Maya")["conflicts"] == []


def test_the_agent_learns_a_rule_after_two_consistent_choices(session, tok):
    for day in (6, 7):
        add(session, tok, "Maya", f(f"Concert {day}", "family", day, 19, flexibility="fixed"))
    first = add(session, tok, "Maya", f("Pub 1", "friends", 6, 19), {"choice": "drop_new"})
    assert first["rule_suggestion"] is None
    second = add(session, tok, "Maya", f("Pub 2", "friends", 7, 19), {"choice": "drop_new"})
    assert second["rule_suggestion"] is None or second["rule_suggestion"] == {
        "prefer": "family",
        "over": "friends",
    }
    # default ranking already puts family first, so there is nothing new to learn
    ss.set_rules(session, tok["Maya"], {"circle_rank": ["friends", "family", "work", "personal"]}, MON)
    add(session, tok, "Maya", f("Pub 3", "friends", 6, 19), {"choice": "drop_existing"})
    third = add(session, tok, "Maya", f("Pub 4", "friends", 7, 19), {"choice": "drop_existing"})
    assert third["rule_suggestion"] is None  # friends over family is already their ranking


def test_a_repeating_commitment_can_skip_one_day(session, tok):
    cid = add(session, tok, "Maya", f("Standup", "work", 5, 9, 30, repeat="weekly"))["commitment"]["id"]
    ss.update_commitment(session, tok["Maya"], cid, {"status": "cancelled"}, "2026-10-12", MON)
    nxt = ss.get_my_time(session, tok["Maya"], "2026-10-12", MON, "2026-10-05")
    assert nxt["items"] == []
    assert len(ss.get_my_time(session, tok["Maya"], "2026-10-19", MON, "2026-10-05")["items"]) == 1


def test_the_week_summary_ties_time_to_chores_and_care(session, tok):
    add(session, tok, "Maya", f("Standup", "work", 5, 9, 30, repeat="weekly"))
    s = mytime(session, tok, "Maya")["summary"]
    assert s["minutes_by_circle"]["work"] == 30 and s["suggested_chore_minutes"] > 0
    assert 0 <= s["suggested_chore_minutes"] <= 2400


# ---- find a time -----------------------------------------------------------------------------------------------------------

GATHER = {
    "title": "Drinks",
    "circle": "friends",
    "duration_minutes": 120,
    "windows": [{"date_from": "2026-10-08", "date_to": "2026-10-09", "from": "18:00", "to": "22:00"}],
    "members": ["Ben"],
    "guests": [{"name": "Priya"}],
}


def test_a_find_a_time_gives_members_suggested_answers_and_guests_a_link(session, tok, rec):
    add(session, tok, "Ben", f("Book club sentinelbook", "friends", 8, 19, 120))
    out = ss.start_gathering(session, tok["Maya"], GATHER, MON, rec)
    assert [g["name"] for g in out["guests"]] == ["Priya"] and out["guests"][0]["link"].startswith("/r/")
    assert len(out["slots"]) >= 4
    bens = mytime(session, tok, "Ben")["gatherings"][0]
    thursday_7 = next(x for x in bens["slots"] if x["start"].endswith("T19:00") and "08" in x["start"][:10])
    assert thursday_7["suggested"] == "maybe" and "Book club" in thursday_7["reason"]
    mayas = mytime(session, tok, "Maya")["gatherings"][0]
    assert all(x["suggested"] == "yes" for x in mayas["slots"])
    assert "Ben" not in json.dumps(mayas) and "sentinelbook" not in json.dumps(mayas)
    assert [c["name"] for c in rec.calls if c["kind"] == "gathering"] == ["Ben"]


def test_everyone_answers_and_the_time_lands_on_attendees_schedules_unattributed(session, tok, rec):
    add(session, tok, "Ben", f("Book club sentinelbook", "friends", 8, 19, 120))
    out = ss.start_gathering(session, tok["Maya"], GATHER, MON, rec)
    rid = out["round_id"]
    ss.answer_gathering(session, tok["Maya"], rid, None, True, MON)
    ss.answer_gathering(session, tok["Ben"], rid, None, True, MON)
    slots = out["slots"]
    guest = rounds.status(session, out["guests"][0]["token"], MON)
    assert guest["need"]["slots"] == slots  # the guest sees the same candidates
    ans = {s: ("no" if s.startswith("2026-10-08T19") else "yes") for s in slots}
    rounds.submit_answer(session, out["guests"][0]["token"], {"consent": True, "slots": ans}, MON)
    res = rounds.get_result(session, out["my_token"], MON)["result"]
    assert res["mode"] == "when" and res["plan"]["start"] != "2026-10-08T19:00"
    assert res["fit"] in ("everyone", "flex")
    blob = json.dumps(res)
    assert "sentinelbook" not in blob and "Ben" not in blob and "Priya" not in blob
    for who in ("Maya", "Ben"):
        titles = [
            i["title"] for i in ss.get_my_time(session, tok[who], "2026-10-05", MON, "2026-10-05")["items"]
        ]
        assert "Drinks" in titles
    assert ss.get_my_time(session, tok["Chen"], "2026-10-05", MON, "2026-10-05")["items"] == []  # not invited


def test_a_maybe_becomes_a_tentative_commitment_that_the_person_confirms(session, tok, rec):
    add(session, tok, "Ben", f("Book club", "friends", 8, 19, 120))
    g = {
        **GATHER,
        "windows": [{"date_from": "2026-10-08", "date_to": "2026-10-08", "from": "19:00", "to": "21:00"}],
        "guests": [],
    }
    out = ss.start_gathering(session, tok["Maya"], g, MON, rec)
    ss.answer_gathering(session, tok["Maya"], out["round_id"], None, True, MON)
    ss.answer_gathering(session, tok["Ben"], out["round_id"], None, True, MON)  # Ben: maybe
    bens = ss.get_my_time(session, tok["Ben"], "2026-10-05", MON, "2026-10-05")
    assert [t["title"] for t in bens["tentative"]] == ["Drinks"] and len(bens["conflicts"]) == 1
    ss.confirm_tentative(session, tok["Ben"], bens["tentative"][0]["id"], False, MON)
    assert ss.get_my_time(session, tok["Ben"], "2026-10-05", MON, "2026-10-05")["tentative"] == []


def test_non_responders_get_nothing_and_the_result_says_so(session, tok, rec):
    out = ss.start_gathering(session, tok["Maya"], {**GATHER, "guests": []}, MON, rec)
    ss.answer_gathering(session, tok["Maya"], out["round_id"], None, True, MON)
    rounds.close_round(session, out["my_token"], MON)
    res = rounds.get_result(session, out["my_token"], MON)["result"]
    assert res["defaults_applied"] is True
    assert ss.get_my_time(session, tok["Ben"], "2026-10-05", MON, "2026-10-05")["items"] == []


def test_guests_must_be_named_and_members_must_exist(session, tok, rec):
    with pytest.raises(rounds.HuddleError):
        ss.start_gathering(session, tok["Maya"], {**GATHER, "members": ["Nobody"]}, MON, rec)
    with pytest.raises(rounds.HuddleError):
        ss.start_gathering(session, tok["Maya"], {**GATHER, "title": ""}, MON, rec)


def test_household_state_still_loads_after_a_find_a_time_closes(session, tok, rec):
    out = ss.start_gathering(session, tok["Maya"], {**GATHER, "guests": [], "members": ["Ben"]}, MON, rec)
    for who in ("Maya", "Ben"):
        ss.answer_gathering(session, tok[who], out["round_id"], None, True, MON)
    for who in ("Maya", "Ben", "Chen"):
        state = hm.get_state(session, tok[who], MON)
        assert state["me"]["name"] == who
    assert any(d["mode"] == "when" for d in hm.get_state(session, tok["Maya"], MON)["mine"]["decisions"])


async def test_every_round_route_copes_with_a_find_a_time(fresh_db):
    import httpx

    from server import api

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://t") as c:
        out = (await c.post("/api/home", json={"name": "H", "members": [{"name": n} for n in NAMES]})).json()
        tk = {m["name"]: m["token"] for m in out["members"]}
        g = (
            await c.post(
                "/api/time/gathering", json={"token": tk["Maya"], "fields": {**GATHER, "guests": []}}
            )
        ).json()
        mine = g["my_token"]
        r = await c.post("/api/agent/parse", json={"token": mine, "text": "any time works"})
        assert r.status_code < 500, r.text
        r = await c.post("/api/agent/turn", json={"token": mine})
        assert r.status_code < 500, r.text
        for who in ("Maya", "Ben"):
            await c.post(
                "/api/time/answer",
                json={"token": tk[who], "round_id": g["round_id"], "accept_suggestions": True},
            )
        for path in (
            "/api/status",
            "/api/result",
            "/api/plan-card",
            "/api/agent/explain",
            "/api/household",
            "/me/answers",
        ):
            r = await c.get(path, params={"token": mine})
            assert r.status_code < 500, (path, r.text)
        r = await c.post("/api/checkin", json={"token": mine, "score": 4})
        assert r.status_code < 500, r.text
        r = await c.post("/api/nudge", params={"token": mine})
        assert r.status_code < 500, r.text
