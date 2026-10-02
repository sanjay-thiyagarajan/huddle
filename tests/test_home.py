"""Household service: private profiles, ad-hoc and pre-planned chores, the ask/accept/decline loop,
weekly fair plans, the ledger, exemptions, reminders and the scheduler."""

import json
from datetime import datetime, timedelta

import pytest

from server import notify
from server.engine import home as hm
from server.engine import rounds

MON = datetime(2026, 10, 5, 9, 0, 0)  # a Monday
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


def make_home(session, names=NAMES, now=MON):
    out = hm.create_household(session, "The Okafors", [{"name": n} for n in names], now)
    return {m["name"]: m["token"] for m in out["members"]}


def state(session, tok, who, now=MON):
    return hm.get_state(session, tok[who], now)


def profile(session, tok, who, **kw):
    return hm.set_profile(session, tok[who], kw, MON)


def chore(session, tok, who, rec, **fields):
    return hm.add_chore(session, tok[who], fields, MON, rec)


def owners(st):
    return {a["title"]: a["owner"] for a in st["plan"]["assignments"] if a["owner"]}


# ---- households and tokens -----------------------------------------------------------------------


def test_create_validates_and_first_member_is_admin(session):
    out = hm.create_household(session, "Home", [{"name": "A"}, {"name": "B"}], MON)
    assert [m["is_admin"] for m in out["members"]] == [True, False]
    assert all(m["link"].startswith("/h/") for m in out["members"])
    for bad in (
        [{"name": "A"}],
        [{"name": "A"}, {"name": "a"}],
        [{"name": "A"}, {"name": ""}],
        [{"name": "A"}, {"name": "B", "email": "nope"}],
    ):
        with pytest.raises(rounds.HuddleError):
            hm.create_household(session, "Home", bad, MON)
    with pytest.raises(rounds.HuddleError):
        hm.create_household(session, "", [{"name": "A"}, {"name": "B"}], MON)


def test_tokens_are_scoped_to_one_household_and_not_interchangeable_with_rounds(session):
    a = make_home(session)
    b = make_home(session, ["Zed", "Yan"])
    r = rounds.create_round(session, "everyday", [{"name": "P"}, {"name": "Q"}], 3600, now=MON)
    with pytest.raises(rounds.HuddleError):
        hm.get_state(session, r["participants"][0]["token"], MON)  # a round token is not a household token
    with pytest.raises(rounds.HuddleError):
        rounds.status(session, a["Maya"], MON)  # and the reverse
    assert {m["name"] for m in state(session, a, "Maya")["members"]} == set(NAMES)
    assert {m["name"] for m in state(session, b, "Zed")["members"]} == {"Zed", "Yan"}
    with pytest.raises(rounds.HuddleError):
        hm.get_state(session, a["Maya"][:-2] + "xx", MON)


def test_only_the_admin_adds_people(session):
    tok = make_home(session)
    with pytest.raises(rounds.HuddleError) as e:
        hm.add_member(session, tok["Ben"], "Dee", None, MON)
    assert e.value.code == "admin_only"
    new = hm.add_member(session, tok["Maya"], "Dee", None, MON)
    assert hm.get_state(session, new["token"], MON)["me"]["name"] == "Dee"


# ---- private profile -----------------------------------------------------------------------------


def test_profile_is_validated_and_owner_only(session):
    tok = make_home(session)
    v = profile(
        session,
        tok,
        "Maya",
        availability=437,
        prefs={"cooking": "love", "yard": "cannot"},
        skills={"repairs": 2},
        learn=["laundry"],
        keywords=["sentinelplumbing"],
    )
    assert v["availability"] == 437 and v["prefs"] == {"cooking": "love", "yard": "cannot"}
    for bad in (
        {"availability": -1},
        {"availability": "x"},
        {"prefs": {"nonsense": "love"}},
        {"prefs": {"cooking": "adore"}},
        {"skills": {"cooking": 5}},
        {"learn": ["nope"]},
        {"keywords": ["x" * 40]},
    ):
        with pytest.raises(rounds.HuddleError):
            hm.set_profile(session, tok["Maya"], bad, MON)
    mine = json.dumps(state(session, tok, "Maya"))
    assert "437" in mine and "sentinelplumbing" in mine
    for other in ("Ben", "Chen"):
        theirs = json.dumps(state(session, tok, other))
        assert (
            "437" not in theirs
            and "sentinelplumbing" not in theirs
            and "yard" not in theirs.split("profile")[0]
        )


def test_exemptions_are_capped_so_the_load_stays_fair(session):
    tok = make_home(session)
    weeks = [MON, MON + timedelta(days=7), MON + timedelta(days=14)]
    hm.set_profile(session, tok["Maya"], {"exempt_this_week": True}, weeks[0])
    hm.set_profile(session, tok["Maya"], {"exempt_this_week": True}, weeks[1])
    with pytest.raises(rounds.HuddleError) as e:
        hm.set_profile(session, tok["Maya"], {"exempt_this_week": True}, weeks[2])
    assert e.value.code == "exemption_limit" and "Lower your availability" in e.value.message
    assert (
        hm.set_profile(session, tok["Maya"], {"exempt_this_week": False}, weeks[1])["exempt_this_week"]
        is False
    )
    hm.set_profile(session, tok["Maya"], {"exempt_this_week": True}, weeks[2])  # room again


# ---- chores: pre-planned or ad hoc ---------------------------------------------------------------


def test_future_and_recurring_chores_are_held_until_their_week(session, rec):
    tok = make_home(session)
    far = chore(session, tok, "Maya", rec, title="Clean the gutters", category="yard", due="2026-11-20")
    assert far["outcome"] == "held"
    st = state(session, tok, "Maya")
    assert st["plan"]["exists"] is False and st["plan"]["assignments"] == []
    # planned for the week it is due
    later = hm.plan_week(session, tok["Maya"], "2026-11-16", False, MON, rec)
    assert later["plan"]["exists"] is False  # state shows the CURRENT week; plan for 11-16 is stored
    rows = hm._week_rows(
        session,
        session.exec(__import__("sqlmodel").select(hm.Home)).first().id,
        datetime(2026, 11, 16).date(),
    )
    assert [r.status for r in rows] == ["planned"]


def test_chores_added_before_the_first_plan_are_held_then_planned_together(session, rec):
    tok = make_home(session)
    out = [
        chore(session, tok, "Ben", rec, title=f"Chore {i}", category="tidying", minutes=10, cadence="weekly")
        for i in range(4)
    ]
    assert {o["outcome"] for o in out} == {"held"}  # no half-plan after the first one
    assert state(session, tok, "Ben")["plan"]["exists"] is False
    st = hm.plan_week(session, tok["Ben"], None, False, MON, rec)
    assert st["plan"]["exists"] and len(owners(st)) == 4 and "split" in st["plan"]["headline"]


def test_missing_minutes_are_estimated_and_flagged(session, rec):
    tok = make_home(session)
    out = chore(session, tok, "Maya", rec, title="Do the laundry", category="laundry")
    assert out["chore"]["minutes"] == 30 and out["chore"]["estimated"] is True
    assert (
        chore(session, tok, "Maya", rec, title="Mop", category="cleaning", minutes=25)["chore"]["estimated"]
        is False
    )


def test_planning_and_admin_chores_default_to_mental_load(session, rec):
    tok = make_home(session)
    assert (
        chore(session, tok, "Maya", rec, title="Book the dentist", category="admin")["chore"]["mental"]
        is True
    )
    assert chore(session, tok, "Maya", rec, title="Mop", category="cleaning")["chore"]["mental"] is False


def test_chore_validation(session, rec):
    tok = make_home(session)
    for bad in (
        {"title": ""},
        {"title": "x", "category": "nope"},
        {"title": "x", "minutes": 1},
        {"title": "x", "cadence": "hourly"},
        {"title": "x", "heaviness": 9},
        {"title": "x", "people_needed": 9},
        {"title": "x", "due": "tomorrow"},
    ):
        with pytest.raises(rounds.HuddleError):
            chore(session, tok, "Maya", rec, **bad)


# ---- the weekly plan -----------------------------------------------------------------------------


def seed_week(session, tok, rec):
    profile(session, tok, "Maya", availability=300)
    profile(session, tok, "Ben", availability=300)
    profile(session, tok, "Chen", availability=300, prefs={"cooking": "cannot"})
    for t, cat, cad, mins in [
        ("Cook dinners", "cooking", "weekly", 90),
        ("Dishes", "dishes", "daily", 10),
        ("Laundry", "laundry", "weekly", 40),
        ("Clean bathroom", "cleaning", "weekly", 45),
        ("Plan the meals", "planning", "weekly", 30),
        ("Pay the bills", "admin", "weekly", 30),
    ]:
        chore(session, tok, "Maya", rec, title=t, category=cat, cadence=cad, minutes=mins)
    return hm.plan_week(session, tok["Maya"], None, False, MON, rec)


def test_weekly_plan_respects_private_limits_and_reports_fairness(session, rec):
    tok = make_home(session)
    st = seed_week(session, tok, rec)
    own = owners(st)
    assert own["Cook dinners"] != "Chen"  # Chen said they cannot cook
    assert st["plan"]["report"]["slots_filled"] == st["plan"]["report"]["slots_total"] == 6
    assert st["plan"]["report"]["deviation_pct"] <= 25
    loads = st["plan"]["loads_minutes"]
    assert sum(loads.values()) == 90 + 70 + 40 + 45 + 30 + 30  # dishes: 10 min x 7 a week = 70
    mine = state(session, tok, "Ben")["mine"]
    assert mine["load"]["availability"] == 300 and mine["load"]["vs_fair_share_pct"] is not None


def test_only_the_admin_can_redo_an_existing_plan(session, rec):
    tok = make_home(session)
    seed_week(session, tok, rec)
    with pytest.raises(rounds.HuddleError) as e:
        hm.plan_week(session, tok["Ben"], None, True, MON, rec)
    assert e.value.code == "admin_only"
    hm.plan_week(session, tok["Maya"], None, True, MON, rec)


def test_replan_keeps_what_is_done(session, rec):
    tok = make_home(session)
    st = seed_week(session, tok, rec)
    victim = next(a for a in st["plan"]["assignments"] if a["title"] == "Laundry")
    who = victim["owner"]
    hm.complete(session, tok[who], victim["id"], MON)
    st2 = hm.plan_week(session, tok["Maya"], None, True, MON, rec)
    laundry = [a for a in st2["plan"]["assignments"] if a["title"] == "Laundry"]
    assert len(laundry) == 1 and laundry[0]["status"] == "done" and laundry[0]["owner"] == who


def test_a_member_is_exempt_gets_nothing_and_the_group_only_sees_a_count(session, rec):
    tok = make_home(session)
    profile(session, tok, "Ben", exempt_this_week=True)
    st = seed_week(session, tok, rec)
    assert "Ben" not in set(owners(st).values()) and st["plan"]["report"]["exempt_count"] == 1
    assert "exempt this week" in st["plan"]["headline"]
    assert "exempt" not in json.dumps(state(session, tok, "Chen")["mine"]["profile"]).replace("exempt_", "")


# ---- ad hoc: ask, accept, decline, re-ask --------------------------------------------------------


def adhoc(session, tok, rec, title="Fix the squeaky door", category="repairs", who="Maya", **kw):
    seed_week(session, tok, rec)
    return chore(session, tok, who, rec, title=title, category=category, minutes=30, **kw)


def pending_for(session, tok):
    return {n: state(session, tok, n)["mine"]["proposals"] for n in NAMES}


def test_adhoc_chore_is_offered_to_one_person_only_and_nobody_else_can_tell_who(session, rec):
    tok = make_home(session)
    adhoc(session, tok, rec)
    offers = pending_for(session, tok)
    asked = [n for n, o in offers.items() if o]
    assert len(asked) == 1
    for n in NAMES:  # everyone, including the person asked, sees a pending chore with no name on it
        row = next(
            a for a in state(session, tok, n)["plan"]["assignments"] if a["title"] == "Fix the squeaky door"
        )
        assert row["status"] == "pending" and row["owner"] is None
    # The audit trail records THAT someone was asked, never who (adding the chore is a different event)
    for n in NAMES:
        asking = [e for e in state(session, tok, n)["events"] if e["kind"] in ("asking", "reassigning")]
        assert asking and all(e["actor"] is None and e["detail"] == "Fix the squeaky door" for e in asking)


def test_accepting_makes_it_public_and_planned(session, rec):
    tok = make_home(session)
    adhoc(session, tok, rec)
    who = next(n for n, o in pending_for(session, tok).items() if o)
    a_id = state(session, tok, who)["mine"]["proposals"][0]["id"]
    st = hm.respond(session, tok[who], a_id, True, None, MON, rec)
    assert owners(st)["Fix the squeaky door"] == who
    assert st["mine"]["proposals"] == []
    assert next(a for a in st["mine"]["assignments"] if a["title"] == "Fix the squeaky door")["why"]


def test_only_the_person_asked_can_answer(session, rec):
    tok = make_home(session)
    adhoc(session, tok, rec)
    asked = next(n for n, o in pending_for(session, tok).items() if o)
    a_id = state(session, tok, asked)["mine"]["proposals"][0]["id"]
    other = next(n for n in NAMES if n != asked)
    with pytest.raises(rounds.HuddleError) as e:
        hm.respond(session, tok[other], a_id, True, None, MON, rec)
    assert e.value.code == "not_yours"


def test_a_decline_asks_the_next_person_and_never_the_same_one_again(session, rec):
    tok = make_home(session)
    adhoc(session, tok, rec)
    seen = []
    for _ in range(2):
        who = next(n for n, o in pending_for(session, tok).items() if o)
        seen.append(who)
        a_id = state(session, tok, who)["mine"]["proposals"][0]["id"]
        hm.respond(session, tok[who], a_id, False, "busy", MON, rec)
    assert len(set(seen)) == 2
    last = [n for n, o in pending_for(session, tok).items() if o]
    assert len(last) == 1 and last[0] not in seen


def test_everyone_declining_leaves_the_chore_open_for_the_group_to_see(session, rec):
    tok = make_home(session)
    adhoc(session, tok, rec)
    for _ in range(3):
        who = next((n for n, o in pending_for(session, tok).items() if o), None)
        if who is None:
            break
        a_id = state(session, tok, who)["mine"]["proposals"][0]["id"]
        hm.respond(session, tok[who], a_id, False, "cannot", MON, rec)
    st = state(session, tok, "Maya")
    assert "Fix the squeaky door" in st["plan"]["attention"]
    assert (
        next(a for a in st["plan"]["assignments"] if a["title"] == "Fix the squeaky door")["status"] == "open"
    )


def test_declines_and_reasons_are_never_visible_to_others(session, rec):
    tok = make_home(session)
    adhoc(session, tok, rec)
    who = next(n for n, o in pending_for(session, tok).items() if o)
    a_id = state(session, tok, who)["mine"]["proposals"][0]["id"]
    hm.respond(session, tok[who], a_id, False, "prefer_not", MON, rec)
    for n in NAMES:
        blob = json.dumps(state(session, tok, n))
        assert "prefer_not" not in blob and "excluded" not in blob and "proposed_to" not in blob


def test_decline_reasons_are_validated(session, rec):
    tok = make_home(session)
    adhoc(session, tok, rec)
    who = next(n for n, o in pending_for(session, tok).items() if o)
    a_id = state(session, tok, who)["mine"]["proposals"][0]["id"]
    with pytest.raises(rounds.HuddleError) as e:
        hm.respond(session, tok[who], a_id, False, "because", MON, rec)
    assert e.value.code == "bad_reason"


def test_ad_hoc_offers_go_to_people_who_can_not_the_ones_who_cannot(session, rec):
    tok = make_home(session)
    seed_week(session, tok, rec)
    profile(session, tok, "Maya", prefs={"repairs": "cannot"})
    profile(session, tok, "Ben", prefs={"repairs": "cannot"})
    chore(session, tok, "Chen", rec, title="Fix the shelf", category="repairs", minutes=30)
    assert [n for n, o in pending_for(session, tok).items() if o] == ["Chen"]


def test_handing_back_asks_someone_else_never_the_owner(session, rec):
    tok = make_home(session)
    st = seed_week(session, tok, rec)
    mine = next(a for a in st["plan"]["assignments"] if a["title"] == "Laundry")
    owner = mine["owner"]
    hm.hand_back(session, tok[owner], mine["id"], "busy", MON, rec)
    now_asked = [n for n, o in pending_for(session, tok).items() if o]
    assert len(now_asked) == 1 and now_asked[0] != owner
    with pytest.raises(rounds.HuddleError):
        hm.hand_back(session, tok[owner], mine["id"], None, MON, rec)  # no longer theirs


def test_only_the_owner_completes_and_a_finished_one_off_closes(session, rec):
    tok = make_home(session)
    adhoc(session, tok, rec)
    who = next(n for n, o in pending_for(session, tok).items() if o)
    a_id = state(session, tok, who)["mine"]["proposals"][0]["id"]
    hm.respond(session, tok[who], a_id, True, None, MON, rec)
    other = next(n for n in NAMES if n != who)
    with pytest.raises(rounds.HuddleError) as e:
        hm.complete(session, tok[other], a_id, MON)
    assert e.value.code == "not_yours"
    st = hm.complete(session, tok[who], a_id, MON)
    assert next(a for a in st["plan"]["assignments"] if a["id"] == a_id)["status"] == "done"
    assert next(c for c in st["chores"] if c["title"] == "Fix the squeaky door")["status"] == "done"


# ---- the fair ledger and felt load ---------------------------------------------------------------


def recurring_home(session, rec):
    tok = make_home(session, ["Maya", "Ben"])
    for n in ("Maya", "Ben"):
        profile(session, tok, n, availability=300)
    for i in range(12):
        chore(session, tok, "Maya", rec, title=f"Task {i}", category="tidying", minutes=15, cadence="weekly")
    return tok


def test_someone_who_did_more_last_week_gets_a_lighter_share_this_week(session, rec):
    tok = recurring_home(session, rec)
    st = hm.plan_week(session, tok["Maya"], None, False, MON, rec)
    week1 = {n: [a for a in st["plan"]["assignments"] if a["owner"] == n] for n in ("Maya", "Ben")}
    assert abs(len(week1["Maya"]) - len(week1["Ben"])) <= 1
    for a in week1["Maya"]:  # Maya does everything assigned; Ben does nothing
        hm.complete(session, tok["Maya"], a["id"], MON)
    nxt = MON + timedelta(days=7)
    st2 = hm.plan_week(session, tok["Maya"], None, False, nxt, rec)
    own2 = [a["owner"] for a in st2["plan"]["assignments"]]
    assert own2.count("Maya") < own2.count("Ben")  # the ledger shifts work toward the one who carried less


def test_a_week_that_felt_too_heavy_lightens_the_next_one(session, rec):
    tok = recurring_home(session, rec)
    hm.plan_week(session, tok["Maya"], None, False, MON, rec)
    hm.checkin_week(session, tok["Ben"], 1, MON)
    nxt = MON + timedelta(days=7)
    st = hm.plan_week(session, tok["Maya"], None, False, nxt, rec)
    own = [a["owner"] for a in st["plan"]["assignments"]]
    assert own.count("Ben") < own.count("Maya")
    with pytest.raises(rounds.HuddleError):
        hm.checkin_week(session, tok["Ben"], 9, MON)


def test_the_felt_score_is_private(session, rec):
    tok = recurring_home(session, rec)
    hm.checkin_week(session, tok["Ben"], 1, MON)
    assert "felt" not in json.dumps(state(session, tok, "Maya")).lower()


# ---- scheduler: auto plan, nudges, expiry, due reminders -----------------------------------------


def test_the_scheduler_plans_each_new_week_after_the_first_plan_and_only_once(session, rec):
    tok = make_home(session)
    chore(session, tok, "Maya", rec, title="Dishes", category="dishes", minutes=10, cadence="daily")
    nxt = MON + timedelta(days=7)
    assert hm.tick(session, nxt, rec) == []  # a brand-new household is planned deliberately, not by itself
    hm.plan_week(session, tok["Maya"], None, False, MON, rec)
    assert ("auto_plan", "The Okafors") in hm.tick(session, nxt, rec)
    assert hm.tick(session, nxt, rec) == []  # only once
    assert state(session, tok, "Ben", nxt)["plan"]["exists"]


def test_an_unanswered_offer_is_nudged_then_passed_to_the_next_person(session, rec):
    tok = make_home(session)
    adhoc(session, tok, rec)
    first = next(n for n, o in pending_for(session, tok).items() if o)
    assert hm.tick(session, MON + timedelta(hours=1), rec) == []
    assert ("nudge", "Fix the squeaky door") in hm.tick(session, MON + timedelta(hours=13), rec)
    assert [d for d in hm.tick(session, MON + timedelta(hours=14), rec) if d[0] == "nudge"] == []  # once
    assert ("reasked", "Fix the squeaky door") in hm.tick(session, MON + timedelta(hours=25), rec)
    second = next(n for n, o in pending_for(session, tok).items() if o)
    assert second != first


def test_due_soon_reminders_go_to_the_owner_once(session, rec):
    tok = make_home(session)
    seed_week(session, tok, rec)
    chore(session, tok, "Maya", rec, title="Call the plumber", category="admin", minutes=15, due="2026-10-06")
    st = state(session, tok, "Maya")
    row = next(a for a in st["plan"]["assignments"] if a["title"] == "Call the plumber")
    if row["status"] == "pending":  # offered rather than planned: accept it
        who = next(n for n, o in pending_for(session, tok).items() if o)
        hm.respond(session, tok[who], row["id"], True, None, MON, rec)
    rec.calls.clear()
    did = hm.tick(session, MON + timedelta(hours=2), rec)
    assert ("due", "Call the plumber") in did
    assert [c["kind"] for c in rec.calls] == ["due"]
    assert [d for d in hm.tick(session, MON + timedelta(hours=3), rec) if d[0] == "due"] == []


def test_notifications_carry_no_names_of_others_and_no_private_data(session, rec):
    tok = make_home(session)
    adhoc(session, tok, rec)
    for call in rec.calls:
        blob = json.dumps({k: v for k, v in call.items() if k != "email"})
        for other in NAMES:
            if other != call["name"]:
                assert other not in blob
    subject, body = notify.home_message("proposal", "Ben", "Fix the squeaky door", "http://x/h/T")
    assert "Hi Ben" in body and "Maya" not in body and "Chen" not in body
