"""The fictional family, end to end with synthetic audio. Skipped without the `voice` extra.

This tests that the pipeline works. It is not evidence that Huddle helps real people."""
import pytest

pytest.importorskip("speechbrain")
pytest.importorskip("faster_whisper")

from family_sim import EXPECTED, run_family  # noqa: E402  (tests dir is on sys.path)

from server.voice import speaker_id  # noqa: E402


def test_fictional_family_end_to_end_with_synthetic_speech(live_server):
    rep = run_family(live_server)
    steps = rep["steps"]

    # Every utterance was attributed to the right sibling by voice alone
    assert [s["identified"] for s in steps] == [s["speaker"] for s in steps]
    assert all(s["score"] >= speaker_id.THRESHOLD for s in steps)

    # Whisper understood the scripted sentences closely enough for the dialogue to proceed
    assert sum(s["wer"] for s in steps) / len(steps) < 0.05
    assert [s["stage"] for s in steps if s["step"] == 3] == ["saved", "saved", "saved"]

    # What was stored through the MCP tool is what each sibling said
    for name, want in EXPECTED.items():
        got = rep["stored"][name]
        assert got["answered"], name
        for key, value in want.items():
            assert got["answer"][key] == value, (name, key, got["answer"])

    # The voice-only privacy rule held across the whole conversation
    assert not any(ch.isdigit() for line in rep["assistant_lines"] for ch in line)

    # The group result matches the same family's text-entry run (docs and e2e demo)
    res = rep["result"]["result"]
    assert res["gap_hours_bucket"] == "0-5 h" and res["gap_dollars_bucket"] == "$250-500"
    assert {a["name"] for a in res["assignments"]} == {"Maya", "Ben", "Chen"}
