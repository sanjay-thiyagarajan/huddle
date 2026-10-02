"""Generate the FICTIONAL family's spoken conversation as synthetic speech (macOS `say`).

The Alvarez siblings (Maya, Ben, Chen) are invented. Their "recordings" are text-to-speech voices,
not people, so they exercise the voice pipeline end to end but say NOTHING about whether Huddle helps
real families. Usage: python scripts/make_family_clips.py   (macOS only; writes tests/audio/family/)
"""
import json
from pathlib import Path

from make_voice_clips import render

OUT = Path(__file__).resolve().parent.parent / "tests" / "audio" / "family"

# Who speaks with which synthetic voice, and what each says in the voice-only dialogue.
FAMILY = {
    "Maya": {"voice": "Samantha", "rate": 170, "enrol_voice_dir": "samantha", "says": [
        "Just me, nobody is around.",
        "Yes, I agree to answer.",
        "I can do about twelve hours a week and six hundred dollars a month, but not nights.",
        "Save it.",
    ]},
    "Ben": {"voice": "Daniel", "rate": 165, "enrol_voice_dir": "daniel", "says": [
        "Just me, the house is quiet.",
        "Yes, I agree to answer.",
        "I live far away. I can give eight hours a week and five hundred dollars a month.",
        "Save it.",
    ]},
    "Chen": {"voice": "Rishi", "rate": 160, "enrol_voice_dir": "rishi", "says": [
        "Just me, I am alone.",
        "Yes, I agree to answer.",
        "I can do six hours a week and four hundred dollars a month, but I can't do transport.",
        "Save it.",
    ]},
}

if __name__ == "__main__":
    for name, p in FAMILY.items():
        (OUT / name.lower()).mkdir(parents=True, exist_ok=True)
        for i, text in enumerate(p["says"]):
            render(p["voice"], p["rate"], text, OUT / name.lower() / f"{i}.wav")
    (OUT / "family.json").write_text(json.dumps(FAMILY, indent=2))
    print("wrote", sum(1 for _ in OUT.rglob("*.wav")), "clips to", OUT)
