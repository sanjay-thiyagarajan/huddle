"""Mock-mode utterance parser: numbers in words and digits, and negation scoping."""
import pytest

from server.agent.huddle_agent import _num, parse_utterance


@pytest.mark.parametrize("phrase,expected", [
    ("600", 600), ("1,200", 1200), ("twelve", 12), ("sixty", 60), ("eighty", 80),
    ("sixty five", 65), ("six hundred", 600), ("a hundred and fifty", 150),
    ("one hundred twenty", 120), ("twenty-five", 25),
])
def test_number_phrases(phrase, expected):
    assert _num(phrase) == expected


@pytest.mark.parametrize("text,budget", [
    ("Under sixty dollars each, I would love good food", 60),   # was parsed as 6
    ("Around eighty dollars, something relaxed", 80),
    ("Up to $75", 75),
    ("a hundred and fifty bucks", 150),
    ("a couple hundred bucks", None),                             # unreadable: ask, don't guess
])
def test_everyday_budget(text, budget):
    out = parse_utterance("everyday", text)
    assert out["draft"]["budget_ceiling"] == budget
    assert bool(out["missing"]) == (budget is None)


def test_care_words_and_digits():
    out = parse_utterance("care", "I can do maybe twelve hours but not nights, about $600 a month")
    assert out["draft"] == {"hours_per_week": 12, "dollars_per_month": 600, "dealbreakers": ["nights"]}
    out = parse_utterance("care", "Six hours, four hundred dollars a month, and I can't do transport")
    assert out["draft"]["hours_per_week"] == 6 and out["draft"]["dollars_per_month"] == 400
    assert out["draft"]["dealbreakers"] == ["transport"]


def test_missing_field_asks_one_followup():
    out = parse_utterance("care", "I live far away, can give 5 hours")
    assert out["missing"] == ["dollars_per_month"] and out["followup"]
    assert out["draft"]["dealbreakers"] == ["far_away"]


def test_trip_vocabulary_and_whole_trip_budget():
    out = parse_utterance("trip", "Up to $400 for the trip, I love the beach and good food, but no flights")
    assert out["draft"]["budget_ceiling"] == 400
    assert out["draft"]["dealbreakers"] == ["flights"]
    assert set(out["draft"]["vibe"]) == {"beach", "foodie"}
    out = parse_utterance("trip", "I like the mountains")
    assert "whole trip" in out["followup"]
