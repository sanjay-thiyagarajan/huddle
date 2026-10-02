"""Voice-only dialogue: privacy gate, consent, collection, and the rule that private values are
never spoken back unless the person explicitly asks."""
import re

import pytest

from server.agent import dialogue as dl
from server.agent.huddle_agent import parse_utterance


def make(mode="care", name="Maya"):
    return dl.DialogueSession(mode, name, parse_utterance)


def to_collect(s):
    """Run the privacy and consent stages."""
    assert s.start().stage == "privacy"
    assert s.step("just me").stage == "consent"
    t = s.step("yes I agree")
    assert t.stage == "collect"
    return t


def test_full_care_dialogue_saves_through_confirm():
    s = make()
    to_collect(s)
    t = s.step("I can do maybe twelve hours but not nights")
    assert t.stage == "collect" and "dollars a month" in t.say  # one follow-up for the missing field
    t = s.step("about six hundred dollars a month")
    assert t.stage == "confirm"
    t = s.step("save it")
    assert t.done and t.stage == "saved" and "Saved, Maya" in t.say
    assert t.submit == {"hours_per_week": 12.0, "dollars_per_month": 600.0, "dealbreakers": ["nights"],
                        "consent": True}


def test_privacy_gate_offers_alternatives_when_someone_is_near():
    s = make()
    s.start()
    t = s.step("yes my brother is right here")  # someone nearby
    assert t.stage == "privacy" and "send me a link" in t.say and "use the screen" in t.say
    t = s.step("send me a link")
    assert t.done and t.handoff == "link" and t.submit is None


def test_screen_handoff_and_nothing_kept():
    s = make("everyday")
    to_collect(s)
    s.step("under sixty dollars")
    t = s.step("actually use the screen")
    assert t.handoff == "screen" and t.done and s.draft == {}


def test_someone_walks_in_mid_answer_pauses_and_discards_nothing_aloud():
    s = make()
    to_collect(s)
    s.step("about twelve hours")
    t = s.step("someone is coming")
    assert t.stage == "privacy" and "pausing" in t.say


def test_consent_required():
    s = make()
    s.start()
    s.step("nobody is around")
    t = s.step("no I don't agree")
    assert t.stage == "cancelled" and t.done and t.submit is None


def test_cancel_at_any_time_saves_nothing():
    s = make()
    to_collect(s)
    s.step("twelve hours and 600 dollars")
    t = s.step("never mind")
    assert t.stage == "cancelled" and t.submit is None and s.draft == {}


def test_change_it_starts_over():
    s = make("everyday")
    to_collect(s)
    assert s.step("under sixty dollars and I love food").stage == "confirm"
    t = s.step("change it")
    assert t.stage == "collect" and "starting over" in t.say and s.draft == {}


def test_three_misunderstandings_hand_off_instead_of_guessing():
    s = make()
    to_collect(s)
    s.step("blah"); s.step("hmm uh")  # noqa: E702
    t = s.step("mumble")
    assert t.handoff == "link" and t.done


def test_silence_does_not_advance():
    s = make()
    s.start()
    assert s.step("  ").stage == "privacy"


def test_read_back_is_opt_in_and_flagged():
    s = make()
    to_collect(s)
    s.step("twelve hours but not nights and 600 dollars a month")
    t = s.step("read it back")
    assert t.spoke_values is True and "12 hours a week" in t.say and "600 dollars a month" in t.say
    assert "overnight cover" in t.say
    assert s.step("save it").done


# ---- the rule: never echo a private value unless asked ---------------------------------------------

SCRIPTS = {
    "care": ["twenty hours a week but not nights and no transport", "$437 a month", "save it"],
    "everyday": ["I can spend up to $613 and I love food and no crowds", "save it"],
    "trip": ["Up to $829 for the trip, I love the beach and no flights", "save it"],
}
VALUES = {"care": ["20", "twenty", "437", "overnight", "night", "transport"],
          "everyday": ["613", "food", "crowds", "foodie"], "trip": ["829", "beach", "flights", "flying"]}


@pytest.mark.parametrize("mode", ["care", "everyday", "trip"])
def test_assistant_never_says_a_private_value_by_default(mode):
    s = make(mode)
    said = [s.start().say, s.step("just me").say, s.step("yes").say]
    for utterance in SCRIPTS[mode]:
        said.append(s.step(utterance).say)
    spoken = " ".join(said).lower()
    for value in VALUES[mode]:
        assert value not in spoken, f"assistant echoed {value!r}: {spoken}"
    assert not re.search(r"\d", spoken), f"digits in assistant speech: {spoken}"  # templates have no numbers


def test_follow_up_questions_never_repeat_what_was_just_said():
    s = make()
    to_collect(s)
    t = s.step("I can do 13.5 hours")
    assert "13" not in t.say and "hours a week" not in t.say.replace("About how many hours a week", "")


# ---- sessions are bound to the token, expire, and never expose the draft ----------------------------

def test_session_belongs_to_one_token_and_expires(monkeypatch):
    sid, first = dl.open_session("tokenA", "care", "Maya", parse_utterance)
    assert first.stage == "privacy"
    with pytest.raises(dl.DialogueError, match="belongs to someone else"):
        dl.take_turn(sid, "tokenB", "just me")
    assert dl.take_turn(sid, "tokenA", "just me").stage == "consent"
    real = dl.time.monotonic
    monkeypatch.setattr(dl.time, "monotonic", lambda: real() + dl.TTL_SECONDS + 5)
    with pytest.raises(dl.DialogueError, match="expired"):
        dl.take_turn(sid, "tokenA", "yes")


def test_finished_session_is_removed():
    sid, _ = dl.open_session("t", "everyday", "Ben", parse_utterance)
    for u in ("just me", "yes", "under 50 dollars", "save it"):
        turn = dl.take_turn(sid, "t", u)
    assert turn.done
    with pytest.raises(dl.DialogueError):
        dl.take_turn(sid, "t", "hello")
