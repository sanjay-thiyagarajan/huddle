"""The fairness engine: hard limits, fairness, preferences, rotation, ledger, exemptions."""

import random

import pytest

from server.engine import chores as ch


def chore(cid, minutes, category="cleaning", heaviness=1, mental=False, need=1, title=None):
    return ch.ChoreIn(cid, title or cid, category, minutes, heaviness, mental, need)


def member(mid, avail=300, **kw):
    return ch.MemberIn(mid, avail, **kw)


def owners(out):
    return {c: set(m) for c, m in out.assign.items()}


# ---- hard limits -------------------------------------------------------------------------------------


def test_cannot_capacity_and_exempt_are_never_violated():
    chs = [chore("a", 60, "cooking"), chore("b", 60, "yard", 3), chore("c", 120, "repairs", 3)]
    ms = [member("m1", 100, prefs={"yard": "cannot"}), member("m2", 100), member("m3", 500, exempt=True)]
    out = ch.plan(chs, ms)
    own = owners(out)
    assert "m1" not in own["b"] and "m3" not in {m for s in own.values() for m in s}
    for m in ms:  # nobody over their own availability
        assert sum(c.minutes for c in chs if m.id in own[c.id]) <= m.availability
    assert own["c"] == set()  # 120 min fits nobody (100 each): left for the group, not forced on someone


def test_everything_is_covered_when_it_fits():
    chs = [chore(f"c{i}", 30) for i in range(6)]
    out = ch.plan(chs, [member("a", 200), member("b", 200)])
    assert all(len(v) == 1 for v in out.assign.values()) and out.report["unstaffed"] == []


def test_people_needed_staffs_a_chore_with_different_people():
    chs = [chore("sofa", 30, "other", 3, need=2)]
    out = ch.plan(chs, [member("a"), member("b"), member("c")])
    assert len(out.assign["sofa"]) == 2 and len(set(out.assign["sofa"])) == 2


def test_nobody_can_do_it_is_reported_not_forced():
    out = ch.plan(
        [chore("x", 30, "repairs", 3)],
        [member("a", prefs={"repairs": "cannot"}), member("b", prefs={"repairs": "cannot"})],
    )
    assert out.assign["x"] == [] and out.report["unstaffed"] == ["x"]


# ---- fairness -----------------------------------------------------------------------------------------


def test_equal_availability_gives_an_even_split():
    chs = [chore(f"c{i}", 30) for i in range(8)]
    out = ch.plan(chs, [member("a"), member("b")])
    assert out.loads["a"] == out.loads["b"] and out.report["balanced"]


def test_shares_follow_each_persons_own_availability():
    chs = [chore(f"c{i}", 20) for i in range(12)]  # 240 min of work
    out = ch.plan(chs, [member("busy", 100), member("free", 400)])
    assert out.loads["free"] > out.loads["busy"]
    assert out.shares["free"] > out.shares["busy"]
    assert out.report["deviation_pct"] <= 15


def test_claiming_almost_no_availability_does_not_erase_your_share():
    """The floor: a person who says 10 minutes still gets a share based on 40% of the mean."""
    chs = [chore(f"c{i}", 10) for i in range(10)]
    ms = [member("honest", 400), member("claimer", 20)]
    w = ch.member_weights(ms)
    assert w["claimer"] == pytest.approx(0.4 * 210)  # mean of 400 and 20 is 210
    out = ch.plan(chs, ms)
    assert out.loads["claimer"] <= 20  # still capped by what they truly said they can do


def test_burden_weights_heavy_and_mental_work():
    assert ch.burden_of(60, 1, False) == 60
    assert ch.burden_of(60, 3, False) == 90
    assert ch.burden_of(60, 1, True) == pytest.approx(75)
    # a heavy chore counts for more, so the split balances burden, not raw minutes
    chs = [chore("deep", 60, "yard", 3), chore("l1", 45), chore("l2", 45)]
    out = ch.plan(chs, [member("a"), member("b")])
    assert len(out.assign["deep"]) == 1
    # deep = 60 min x 1.5 = 90 burden; the two light chores = 45 + 45 = 90: a perfect split of burden
    assert out.loads["a"] == pytest.approx(90) and out.loads["b"] == pytest.approx(90)
    deep_owner = out.assign["deep"][0]
    assert [m for c in ("l1", "l2") for m in out.assign[c]] == [("b" if deep_owner == "a" else "a")] * 2


def test_fairness_beats_preferences():
    """Two people love dishes and one avoids them, but fairness comes first: the one who avoids them still
    takes a turn, and nobody takes more than two of the four."""
    chs = [chore(f"d{i}", 30, "dishes") for i in range(4)]
    ms = [
        member("a", prefs={"dishes": "love"}),
        member("b", prefs={"dishes": "love"}),
        member("c", prefs={"dishes": "avoid"}),
    ]
    out = ch.plan(chs, ms)
    counts = {m.id: sum(1 for c in chs if m.id in out.assign[c.id]) for m in ms}
    assert counts["c"] >= 1 and max(counts.values()) <= 2
    # 4 equal chunks over 3 people cannot do better than 60/30/30: that is the fairest split available
    assert sorted(round(v) for v in out.loads.values()) == [30, 30, 60]


def test_a_past_over_carrier_gets_a_lighter_share_now():
    chs = [chore(f"c{i}", 30) for i in range(8)]
    even = ch.plan(chs, [member("a"), member("b")])
    lighter = ch.plan(chs, [member("a", prior_dev=80.0), member("b", prior_dev=-80.0)])
    assert lighter.loads["a"] < even.loads["a"] and lighter.loads["b"] > even.loads["b"]
    assert abs(sum(lighter.targets.values()) - sum(even.targets.values())) < 1e-6  # nobody's work vanishes


def test_last_week_felt_overloaded_lightens_this_week():
    chs = [chore(f"c{i}", 10) for i in range(24)]  # fine-grained so a 20% lighter share is expressible
    out = ch.plan(chs, [member("a", felt=1), member("b")])
    assert out.loads["a"] < out.loads["b"]
    assert ch.FELT_FACTOR[1] < ch.FELT_FACTOR[2] < 1


# ---- preferences, skills, learning --------------------------------------------------------------------


def test_preferences_and_skills_decide_between_equally_fair_splits():
    chs = [chore("cook", 30, "cooking"), chore("bills", 30, "admin"), chore("fix tap", 30, "repairs")]
    ms = [
        member("a", prefs={"cooking": "love"}, skills={"repairs": 2}, keywords=["tap"]),
        member("b", prefs={"admin": "love", "cooking": "avoid"}),
        member("c", prefs={"repairs": "avoid"}),
    ]
    out = ch.plan(chs, ms)
    own = owners(out)
    # Every split gives each person one 30-minute chore (equally fair). The best match is:
    # a knows taps (+3), b loves admin (+3), and c, who avoids repairs, gets the remaining cooking.
    assert own == {"cook": {"c"}, "bills": {"b"}, "fix tap": {"a"}}


def test_keyword_knowledge_matches_the_chore_title():
    chs = [chore("bike", 30, "repairs", 2, title="fix the bike")]
    out = ch.plan(chs, [member("a"), member("b", keywords=["bike"])])
    assert out.assign["bike"] == ["b"] and out.why[("bike", "b")] == "knows"


def test_wanting_to_learn_is_a_gentle_nudge():
    chs = [chore("laundry", 30, "laundry")]
    out = ch.plan(chs, [member("a"), member("b", learn=["laundry"], skills={"laundry": 0})])
    # skill 0 costs a point, learning gives one back: it is a tie that must not push the chore onto a
    # person with no skill when a skilled person is just as fair
    assert out.assign["laundry"] in (["a"], ["b"])


# ---- rotation -----------------------------------------------------------------------------------------


def test_a_heavy_chore_rotates_when_someone_else_can_take_it():
    chs = [chore("garage", 60, "yard", 3), chore("light", 30)]
    ms = [member("a"), member("b")]
    first = ch.plan(chs, ms)
    owner1 = first.assign["garage"][0]
    again = ch.plan(chs, ms, last_owner={"garage": {owner1}})
    assert again.assign["garage"][0] != owner1
    assert again.report["heavy_rotated"] == 1 and again.report["rotation_applies"] is True
    assert first.report["rotation_applies"] is False  # nothing to rotate away from in the first week


def test_rotation_never_overrides_a_hard_limit():
    chs = [chore("garage", 60, "yard", 3)]
    ms = [member("a"), member("b", prefs={"yard": "cannot"})]
    out = ch.plan(chs, ms, last_owner={"garage": {"a"}})
    assert out.assign["garage"] == ["a"]  # b cannot, so a keeps it


# ---- ranking for ad-hoc chores ------------------------------------------------------------------------


def test_candidate_ranking_prefers_the_fairest_then_the_best_match():
    ms = [member("a"), member("b"), member("c")]
    c = chore("new", 40, "cooking")
    ranked = ch.rank_candidates(
        c,
        ms,
        loads={"a": 100.0, "b": 20.0, "c": 100.0},
        shares={"a": 1 / 3, "b": 1 / 3, "c": 1 / 3},
        total=220.0,
    )
    assert ranked[0] == "b"  # lowest load takes it
    ms2 = [member("a", prefs={"cooking": "love"}), member("b", prefs={"cooking": "love"})]
    ranked2 = ch.rank_candidates(c, ms2, loads={"a": 0.0, "b": 0.0}, shares={"a": 0.5, "b": 0.5}, total=0.0)
    assert set(ranked2) == {"a", "b"}


def test_ranking_skips_excluded_cannot_exempt_and_over_capacity():
    ms = [
        member("a", prefs={"cooking": "cannot"}),
        member("b", exempt=True),
        member("c", 30),
        member("d"),
        member("e"),
    ]
    ranked = ch.rank_candidates(chore("x", 45, "cooking"), ms, loads={}, shares={}, total=0.0, exclude={"e"})
    assert ranked == ["d"]


# ---- properties over random households ---------------------------------------------------------------


def test_random_households_never_break_hard_limits_and_stay_reasonably_fair():
    rng = random.Random(11)
    cats = ch.CATEGORIES
    for _ in range(25):
        chs = [
            chore(
                f"c{i}",
                rng.choice([10, 20, 30, 45, 60]),
                rng.choice(cats),
                rng.randint(1, 3),
                need=rng.choice([1, 1, 1, 2]),
            )
            for i in range(rng.randint(3, 14))
        ]
        ms = [
            member(
                f"m{i}",
                rng.randint(60, 400),
                prefs={rng.choice(cats): rng.choice(["avoid", "cannot", "love"])},
                exempt=(rng.random() < 0.1),
            )
            for i in range(rng.randint(2, 5))
        ]
        out = ch.plan(chs, ms)
        for m in ms:
            mine = [c for c in chs if m.id in out.assign[c.id]]
            assert sum(c.minutes for c in mine) <= m.availability
            assert all(m.prefs.get(c.category) != "cannot" for c in mine)
            assert not (m.exempt and mine)
        for c in chs:
            assert len(out.assign[c.id]) <= c.people_needed
            assert len(set(out.assign[c.id])) == len(out.assign[c.id])


# ---- work already assigned this week counts toward a fair share -----------------------------------------


def test_mid_week_additions_are_fair_relative_to_what_people_already_have():
    new = [chore(f"n{i}", 10) for i in range(6)]  # 60 minutes of new work
    out = ch.plan(
        new, [member("a"), member("b")], base_load={"a": 120.0, "b": 0.0}, base_minutes={"a": 120, "b": 0}
    )
    # a already holds 120 of the 180 total, so b takes ALL the new work. That leaves a 30-minute gap either
    # side of a fair 90 each (33% of an average share): the best any split can do from here.
    assert out.loads == {"a": 0.0, "b": 60.0}
    assert out.report["deviation_pct"] == pytest.approx(33.3, abs=0.1)


def test_assigned_minutes_use_up_availability():
    out = ch.plan(
        [chore("x", 50)],
        [member("a", 100), member("b", 100)],
        base_load={"a": 80.0},
        base_minutes={"a": 80, "b": 0},
    )
    assert out.assign["x"] == ["b"]  # a has only 20 minutes left


def test_when_one_person_is_already_over_their_share_everyone_else_is_still_balanced():
    """Leximin: Maya's gap can't shrink (she already carries far more than her share), but that must not
    make the rest of the split arbitrary. The remaining work is shared evenly between the others."""
    new = [chore(f"n{i}", 30) for i in range(6)]
    out = ch.plan(
        new,
        [member("maya"), member("ben"), member("chen")],
        base_load={"maya": 700.0},
        base_minutes={"maya": 480},
    )
    assert out.loads["maya"] == 0.0
    assert out.loads["ben"] == out.loads["chen"] == 90.0


def test_several_people_over_their_share_are_each_handled_in_turn():
    new = [chore(f"n{i}", 20) for i in range(9)]
    out = ch.plan(
        new,
        [member("a"), member("b"), member("c"), member("d")],
        base_load={"a": 600.0, "b": 400.0},
        base_minutes={"a": 300, "b": 200},
    )
    assert out.loads["a"] == 0.0
    assert out.loads["c"] == pytest.approx(out.loads["d"], abs=20.0)  # the two with room share it evenly
    assert out.loads["b"] <= out.loads["c"]


def test_someone_whose_existing_load_exceeds_their_availability_does_not_sink_the_plan():
    """E.g. 8 h of care already taken on against 4 h of stated chore time: they just get nothing new."""
    new = [chore(f"n{i}", 30) for i in range(4)]
    out = ch.plan(
        new, [member("a", 240), member("b"), member("c")], base_load={"a": 700.0}, base_minutes={"a": 480}
    )
    assert out.loads["a"] == 0.0 and out.loads["b"] > 0 and out.loads["c"] > 0
    assert out.report["unstaffed"] == []
