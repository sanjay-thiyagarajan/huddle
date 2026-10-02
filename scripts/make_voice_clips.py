"""Generate SYNTHETIC speech clips with macOS `say` (16 kHz mono WAV) for the voice tests.

These are text-to-speech voices, not real people. They show the enrol/identify pipeline works;
they say nothing about accuracy on real household voices (see docs/voice-accuracy.md).
Usage: python scripts/make_voice_clips.py   (macOS only; output in tests/audio/)
"""
import subprocess
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "tests" / "audio"
VOICES = {"samantha": "Samantha", "daniel": "Daniel", "karen": "Karen", "rishi": "Rishi", "moira": "Moira"}

UNKNOWN = {"tessa": "Tessa"}  # never enrolled: used to check unknown speakers are rejected

ENROL = [  # (id, rate wpm, text)
    ("e1", 175, "Alexa, plan our Saturday."),
    ("e2", 175, "This is my voice, and I would like to set up my profile."),
    ("e3", 175, "I can do about ten hours a week."),
]
TEST = [
    ("t1", 160, "I can do maybe twelve hours and six hundred dollars a month, but not nights."),
    ("t2", 190, "Under sixty dollars each, I would love good food, and no crowds."),
    ("t3", 175, "Remind everyone who has not answered yet."),
    ("t4", 205, "Close the round now and show me the plan."),
    ("t5", 150, "I live far away, so I can give eight hours and five hundred dollars a month."),
]


def render(voice: str, rate: int, text: str, out: Path) -> None:
    with tempfile.TemporaryDirectory() as d:
        aiff = Path(d) / "x.aiff"
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(aiff), text], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(out)],
                       check=True)


if __name__ == "__main__":
    for key, voice in VOICES.items():
        for split, clips in (("enrol", ENROL), ("test", TEST)):
            (OUT / split / key).mkdir(parents=True, exist_ok=True)
            for cid, rate, text in clips:
                render(voice, rate, text, OUT / split / key / f"{cid}.wav")
    for key, voice in UNKNOWN.items():
        (OUT / "test" / key).mkdir(parents=True, exist_ok=True)
        for cid, rate, text in TEST:
            render(voice, rate, text, OUT / "test" / key / f"{cid}.wav")
    (OUT / "transcripts.tsv").write_text(
        "\n".join(f"{c}\t{t}" for c, _, t in ENROL + TEST) + "\n")
    print("wrote", sum(1 for _ in OUT.rglob("*.wav")), "clips to", OUT)
