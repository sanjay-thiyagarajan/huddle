"""The scheduling engine: overlaps, repeats, rules, smart conflict options, suggested answers, the week."""

import random
from datetime import date, datetime, time, timedelta

from server.engine import schedule as sc

MON = date(2026, 10, 5)  # a Monday; Thursday is the 8th


def at(day, hh, mm=0):
    return datetime(2026, 10, day, hh, mm)


def item(i, title, circle, start, minutes=60, **kw):
    return sc.Item(i, title, circle, start, start + timedelta(minutes=minutes), **kw)


CONCERT = item(
    "c", "School concert", "family", at(8, 18, 30), 90, flexibility="fixed", importance=3, shared=True
)
DINNER = item("d", "Dinner with Priya", "friends", at(8, 19, 0), 120)


# ---- time and repeats --------------------------------------------------------------------------------------------


def test_overlap_and_buffer():
    assert sc.overlaps(at(8, 9), at(8, 10), at(8, 9, 30), at(8, 11))
    assert not sc.overlaps(at(8, 9), at(8, 10), at(8, 10), at(8, 11))  # back to back is fine
    assert sc.overlaps(at(8, 9), at(8, 10), at(8, 10), at(8, 11), buffer=15)  # but not with travel time


def test_weekly_repeat_expands_skips_and_ends():
    standup = item(
        "s", "Standup", "work", at(5, 9), 30, repeat="weekly", skips=("2026-10-12",), until=date(2026, 10, 26)
    )
    window = (datetime(2026, 10, 1), datetime(2026, 11, 30))
    days = [o.start.day for o in sc.occurrences(standup, *window)]
    assert days == [5, 19, 26]  # the 12th is skipped and the series stops after the 26th


def test_daily_repeat_and_jumping_to_a_far_window():
    daily = item("d", "Medication", "personal", at(5, 8), 5, repeat="daily")
    far = sc.occurrences(daily, datetime(2027, 3, 1), datetime(2027, 3, 4))
    assert [o.start.day for o in far] == [1, 2, 3]
    assert (
        sc.occurrences(item("o", "Once", "personal", at(5, 8)), datetime(2026, 11, 1), datetime(2026, 11, 2))
        == []
    )


def test_conflicts_across_circles_but_never_within_one_series():
    items = [CONCERT, DINNER, item("w", "Standup", "work", at(8, 9), 30, repeat="weekly")]
    found = sc.conflicts(items, datetime(2026, 10, 5), datetime(2026, 10, 12))
    assert [(c.a.title, c.b.title) for c in found] == [("School concert", "Dinner with Priya")]
    assert sc.conflicts([CONCERT, item("e", "Early", "friends", at(8, 17, 0), 60)], at(8, 0), at(9, 0)) == []
    close = [CONCERT, item("e", "Early", "friends", at(8, 17, 0), 60)]
    assert sc.conflicts(close, at(8, 0), at(9, 0), sc.Rules(buffer_minutes=45))  # not enough travel time


# ---- rules and priority ---------------------------------------------------------------------------------------------


def test_protected_windows_and_work_hours_flag_an_item():
    rules = sc.Rules(
        protected=[sc.Window((6,), time(8), time(12), "Sunday mornings")],
        work_start=time(9),
        work_end=time(17),
    )
    sunday = item("x", "Brunch", "friends", datetime(2026, 10, 11, 10, 0))
    assert sc.rule_flags(sunday, rules) == ["Sunday mornings"]
    assert sc.rule_flags(item("l", "Lunch with Sam", "friends", at(6, 12, 30)), rules) == ["work hours"]
    assert (
        sc.rule_flags(item("m", "Standup", "work", at(6, 10)), rules) == []
    )  # work is allowed in work hours
    assert sc.rule_flags(item("v", "Dinner", "friends", at(6, 19)), rules) == []


def test_priority_follows_the_persons_own_ranking_fixedness_and_sharing():
    default = sc.Rules()
    assert sc.priority(CONCERT, default) > sc.priority(DINNER, default)
    work_first = sc.Rules(circle_rank=["work", "friends", "family", "personal"])
    friends = item("f", "Drinks", "friends", at(8, 19), flexibility="fixed", importance=3)
    family_soft = item("m", "Visit", "family", at(8, 19), flexibility="optional", importance=1)
    assert sc.priority(friends, work_first) > sc.priority(family_soft, work_first)  # their ranking wins
    assert sc.priority(replace_shared(DINNER, True), default) > sc.priority(DINNER, default)


def replace_shared(it, shared):
    from dataclasses import replace

    return replace(it, shared=shared)


# ---- suggested answers to "does this time work?" --------------------------------------------------------------------------


def test_suggested_answers_say_yes_maybe_or_no_with_a_private_reason():
    rules = sc.Rules(protected=[sc.Window((4,), time(18), time(21), "Friday family night")])
    items = [
        CONCERT,
        item("b", "Book club", "friends", at(7, 19, 0), 120),
        item("g", "Gym", "personal", at(9, 12), 60),
    ]
    assert sc.suggest_answer(items, rules, at(6, 19), 120, "friends") == ("yes", "You're free")
    ans, why = sc.suggest_answer(items, rules, at(8, 19), 120, "friends")
    assert ans == "no" and "'School concert'" in why and "shared" in why
    ans, why = sc.suggest_answer(items, rules, at(7, 19), 120, "friends")
    assert ans == "maybe" and "'Book club'" in why and "move" in why
    ans, why = sc.suggest_answer(items, rules, at(9, 19), 120, "friends")
    assert ans == "no" and "Friday family night" in why
    assert sc.suggest_answer(items, rules, at(6, 21), 120, "friends")[0] == "no"  # runs past waking hours
    work = sc.Rules(work_start=time(9), work_end=time(17))
    assert sc.suggest_answer([], work, at(6, 12), 60, "friends")[0] == "maybe"  # inside work hours: your call


# ---- free time and alternatives ---------------------------------------------------------------------------------------------


def test_free_slots_avoid_commitments_and_protected_time():
    rules = sc.Rules(protected=[sc.Window((0, 1, 2, 3, 4, 5, 6), time(12), time(13), "lunch")])
    items = [item("m", "Meeting", "work", at(6, 9), 120)]
    slots = sc.free_slots(items, rules, MON + timedelta(days=1), MON + timedelta(days=1), 60, step=60)
    hours = [s.hour for s in slots]
    assert 9 not in hours and 10 not in hours and 12 not in hours and 7 in hours and 14 in hours


def test_alternatives_stay_close_to_the_original_time_and_never_clash():
    items = [CONCERT, DINNER, item("t", "Tennis", "personal", at(8, 20, 30), 60)]
    alts = sc.alternatives(DINNER, items, sc.Rules(), count=3)
    assert len(alts) == 3
    for s in alts:
        probe = item("p", "p", "friends", s, DINNER.minutes)
        assert not sc.clashes_with(probe, [CONCERT, items[2]], sc.Rules())
    assert all(sc.part_of_day(a) == "evening" for a in alts)  # a dinner stays an evening thing
    assert alts[0] == at(9, 19)  # Thursday evening is full, so the next evening, not a 4:30 pm 'dinner'


# ---- the smart part: options, a recommendation and the reasons -------------------------------------------------------------


def test_a_fixed_shared_family_event_beats_a_friends_dinner_and_the_dinner_gets_new_times():
    out = sc.conflict_options(DINNER, CONCERT, [CONCERT, DINNER], sc.Rules())
    assert out["recommended"] == "move_new"
    assert "shared" in out["reason"]
    keys = [o["key"] for o in out["options"]]
    assert keys[0] == "move_new" and "drop_new" in keys and keys[-1] == "decide_later"
    assert "ask_others" in keys and "move_existing" not in keys  # it is shared: you can't just move it
    assert out["options"][0]["alternatives"]


def test_a_higher_ranked_new_item_can_displace_a_flexible_existing_one():
    rules = sc.Rules(circle_rank=["friends", "family", "work", "personal"])
    flexible_family = item("v", "Visit gran", "family", at(8, 19), flexibility="movable", importance=1)
    new = item("n", "Priya's birthday", "friends", at(8, 19), flexibility="fixed", importance=3)
    out = sc.conflict_options(new, flexible_family, [flexible_family, new], rules)
    assert out["recommended"] == "move_existing"
    assert "rank friends above family" in out["reason"] or "fixed" in out["reason"]
    assert {"move_existing", "drop_existing"} <= {o["key"] for o in out["options"]}


def test_when_there_is_nowhere_to_move_it_the_agent_recommends_skipping():
    days = [
        item(f"x{d}", "Busy", "work", datetime(2026, 10, d, 7, 0), 15 * 60, flexibility="fixed", shared=True)
        for d in range(1, 16)
    ]
    new = item("n", "Drinks", "friends", at(8, 19))
    out = sc.conflict_options(new, days[7], days + [new], sc.Rules())
    assert out["recommended"] == "drop_new"


def test_a_tie_is_left_to_the_person():
    a = item("a", "Coffee with Sam", "friends", at(8, 10))
    b = item("b", "Coffee with Dee", "friends", at(8, 10))
    assert "your call" in sc.conflict_options(a, b, [a, b], sc.Rules())["reason"]


# ---- the week ---------------------------------------------------------------------------------------------------------------


def test_week_summary_counts_circles_free_time_evenings_and_suggests_chore_time():
    items = [
        CONCERT,
        DINNER.__class__("e", "Drinks", "friends", at(6, 19), at(6, 21)),
        item("w", "Standup", "work", at(5, 9), 30, repeat="weekly"),
    ]
    s = sc.week_summary(items, sc.Rules(max_evenings=1), MON, chore_care_minutes=300)
    assert s["minutes_by_circle"]["family"] == 90 and s["minutes_by_circle"]["friends"] == 120
    assert s["minutes_by_circle"]["work"] == 30
    assert s["committed_minutes"] == 240 and s["chore_care_minutes"] == 300
    assert s["free_minutes"] == 15 * 60 * 7 - 240 - 300
    assert s["evenings_out"] == 1  # family evenings don't count as "out"
    assert s["suggested_chore_minutes"] == round(s["free_minutes"] * 0.25 / 5) * 5
    assert s["overbooked"] is False and s["notes"] == []
    more = items + [item("x", "Pub", "friends", at(7, 19)), item("y", "Film", "personal", at(9, 20))]
    s2 = sc.week_summary(more, sc.Rules(max_evenings=1), MON)
    assert s2["evenings_out"] == 3 and any("3 evenings out" in n for n in s2["notes"])


def test_a_very_full_week_is_flagged_overbooked():
    days = [
        item(f"d{d}", "All day", "work", datetime(2026, 10, d, 7, 0), 14 * 60, flexibility="fixed")
        for d in range(5, 12)
    ]
    s = sc.week_summary(days, sc.Rules(), MON, chore_care_minutes=600)
    assert s["overbooked"] is True and s["free_minutes"] < 15 * 60 and s["suggested_chore_minutes"] <= 240


# ---- candidate times for a group -----------------------------------------------------------------------------------------------


def test_generate_slots_respects_weekdays_duration_and_limit():
    slots = sc.generate_slots(
        date(2026, 10, 5), date(2026, 10, 11), 120, time(17), time(22), weekdays=(3, 4), step=60
    )
    assert {s.weekday() for s in slots} == {3, 4}
    assert all(s.hour <= 20 for s in slots)  # a 2 h slot must end by 22:00
    assert len(sc.generate_slots(date(2026, 10, 5), date(2026, 12, 31), 60, limit=7)) == 7


# ---- property: free means free ------------------------------------------------------------------------------------------------


def test_free_slots_never_overlap_anything_or_protected_time():
    rng = random.Random(5)
    for _ in range(25):
        items = [
            item(
                f"i{k}",
                "x",
                rng.choice(sc.CIRCLES),
                datetime(2026, 10, rng.randint(5, 11), rng.randint(7, 20), rng.choice([0, 30])),
                rng.choice([30, 60, 90, 180]),
            )
            for k in range(rng.randint(0, 12))
        ]
        rules = sc.Rules(
            protected=[
                sc.Window((rng.randint(0, 6),), time(rng.randint(8, 12)), time(rng.randint(13, 17)), "p")
            ],
            buffer_minutes=rng.choice([0, 15]),
        )
        dur = rng.choice([30, 60, 120])
        for s in sc.free_slots(items, rules, date(2026, 10, 5), date(2026, 10, 11), dur, step=30):
            probe = item("p", "p", "friends", s, dur)
            assert not sc.clashes_with(probe, items, rules)
            assert not any(sc._in_window(w, probe.start, probe.end) for w in rules.protected)
            assert sc.suggest_answer(items, rules, s, dur, "friends")[0] in ("yes", "maybe")
