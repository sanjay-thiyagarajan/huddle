"""Find-a-time decision: choosing the slot, and what the group result may say."""

import pytest

from server.engine import when as w

NEED = {
    "title": "Drinks",
    "circle": "friends",
    "duration_minutes": 120,
    "slots": ["2026-10-08T18:00", "2026-10-08T20:00", "2026-10-09T18:00"],
}


def ans(a, b, c):
    return {"slots": dict(zip(NEED["slots"], (a, b, c)))}


def test_picks_the_slot_that_works_for_everyone():
    r = w.compute(
        [("A", ans("no", "yes", "yes")), ("B", ans("yes", "yes", "maybe")), ("C", ans("yes", "yes", "yes"))],
        NEED,
    )
    assert r["plan"]["start"] == "2026-10-08T20:00" and r["fit"] == "everyone"


def test_prefers_maybe_over_no():
    r = w.compute(
        [("A", ans("no", "maybe", "no")), ("B", ans("yes", "yes", "no")), ("C", ans("yes", "yes", "no"))],
        NEED,
    )
    assert r["plan"]["start"] == "2026-10-08T20:00" and r["fit"] == "flex"


def test_when_nothing_fits_it_says_closest_without_naming_anyone():
    r = w.compute(
        [("Ann", ans("no", "no", "no")), ("Bo", ans("yes", "no", "no")), ("Cy", ans("yes", "no", "no"))], NEED
    )
    assert r["fit"] == "most" and r["plan"]["start"] == "2026-10-08T18:00"
    assert not any(n in str(r) for n in ("Ann", "Bo", "Cy"))


def test_two_people_get_no_counts_and_a_warning():
    r = w.compute([("A", ans("no", "yes", "yes")), ("B", ans("yes", "yes", "yes"))], NEED)
    assert r["counts"] is None and r["warnings"]


@pytest.mark.parametrize(
    "bad",
    [
        {**NEED, "title": ""},
        {**NEED, "circle": "enemies"},
        {**NEED, "duration_minutes": 5},
        {**NEED, "slots": []},
        {**NEED, "slots": ["not a date"]},
        {**NEED, "slots": [f"2026-10-{d:02d}T18:00" for d in range(1, 30)] + ["2026-11-01T18:00"] * 20},
    ],
)
def test_bad_needs_are_rejected(bad):
    with pytest.raises(ValueError):
        w.validate_need(bad)
