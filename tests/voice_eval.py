"""Measure speaker-ID and Whisper accuracy on the SYNTHETIC clips in tests/audio and write
docs/voice-accuracy.md. Needs `pip install '.[voice]'` (downloads models on first run).

    python tests/voice_eval.py
"""
import re
import statistics
import sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.voice import speaker_id, stt  # noqa: E402

AUDIO = Path(__file__).resolve().parent / "audio"
DOC = Path(__file__).resolve().parent.parent / "docs" / "voice-accuracy.md"
ENROLLED = sorted(p.name for p in (AUDIO / "enrol").iterdir() if p.is_dir())
UNKNOWN = sorted(p.name for p in (AUDIO / "test").iterdir() if p.is_dir() and p.name not in ENROLLED)
TRANSCRIPTS = dict(line.split("\t") for line in (AUDIO / "transcripts.tsv").read_text().splitlines())


_ONES = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen".split())}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}


def words(s: str) -> list[str]:
    """Normalise for scoring: '$600' == 'six hundred dollars', 'twelve' == '12'."""
    s = re.sub(r"\$(\d[\d,]*)", r"\1 dollars", s.lower()).replace(",", "")
    out, acc = [], None
    for w in re.sub(r"[^a-z0-9 ]", "", s).split():
        if w in _ONES or w in _TENS or w.isdigit():
            n = _ONES.get(w, _TENS.get(w, int(w) if w.isdigit() else 0))
            acc = n if acc is None else acc + n
        elif w == "hundred" and acc is not None:
            acc *= 100
        else:
            if acc is not None:
                out.append(str(acc))
                acc = None
            out.append(w)
    return out + ([str(acc)] if acc is not None else [])


def wer(ref: list[str], hyp: list[str]) -> float:
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[-1] / max(len(ref), 1)


def build_profiles() -> dict[str, np.ndarray]:
    return {
        n: speaker_id.enrol_profile(
            [speaker_id.embed(p) for p in sorted((AUDIO / "enrol" / n).glob("*.wav"))])
        for n in ENROLLED
    }


def main():
    profiles = build_profiles()
    cols = ENROLLED + ["unknown"]
    confusion = {t: dict.fromkeys(cols, 0) for t in ENROLLED + UNKNOWN}
    closest_ok = closest_n = 0
    own_scores, unknown_scores = [], []
    for who in ENROLLED + UNKNOWN:
        for clip in sorted((AUDIO / "test" / who).glob("*.wav")):
            vec = speaker_id.embed(clip)
            scores = {n: float(np.dot(vec, p)) for n, p in profiles.items()}
            best = max(scores, key=scores.get)
            confusion[who][best if scores[best] >= speaker_id.THRESHOLD else "unknown"] += 1
            if who in ENROLLED:
                closest_n += 1
                closest_ok += best == who
                own_scores.append(scores[who])
            else:
                unknown_scores.append(scores[best])
    correct = sum(confusion[t][t] for t in ENROLLED)
    unk_total = sum(sum(confusion[t].values()) for t in UNKNOWN)
    unk_rejected = sum(confusion[t]["unknown"] for t in UNKNOWN)

    wers = []
    for clip in sorted((AUDIO / "test").glob("*/*.wav")):
        hyp = stt.transcribe(clip)
        wers.append((clip.parent.name, clip.stem, wer(words(TRANSCRIPTS[clip.stem]), words(hyp)), hyp))
    mean_wer = statistics.mean(w for _, _, w, _ in wers)

    header = "| true \\ predicted | " + " | ".join(cols) + " |\n|" + "---|" * (len(cols) + 1) + "\n"
    body = "".join(f"| {t} | " + " | ".join(str(confusion[t][p]) for p in cols) + " |\n"
                   for t in ENROLLED + UNKNOWN)
    worst = "".join(f"- {v}/{c}: WER {w:.0%}, heard \"{h}\"\n"
                    for v, c, w, h in sorted(wers, key=lambda x: -x[2])[:3])
    DOC.write_text(f"""# Voice accuracy (synthetic voices only)

Measured {date.today()} by `python tests/voice_eval.py`. **The clips are text-to-speech voices from macOS
`say`, not real people.** They show the enrol/identify/transcribe pipeline works and give a sanity check.
They do **not** tell us how accurate it is for real family members, who vary in mood, distance from the
microphone, background noise and colds. Real-voice numbers still need to be collected (plan P4/P6).

Voice identification here is a stand-in for Alexa person recognition. It separates profiles on a shared
device; it is not authentication.

## Setup
- Model: `{speaker_id.MODEL_SOURCE}` (SpeechBrain ECAPA-TDNN), cosine similarity to a mean-of-3 profile.
- Enrolled voices ({len(ENROLLED)}): {", ".join(ENROLLED)}. Enrolment: 3 clips each at 175 wpm.
- Test clips: 5 different sentences per voice at varied speaking rates (150-205 wpm), none seen at enrolment.
- Unknown speaker (never enrolled): {", ".join(UNKNOWN)}, same 5 sentences.
- Threshold for "recognized": cosine >= {speaker_id.THRESHOLD}. It was set in the gap between these scores after a first run showed a 0.30 threshold passed with no margin, so these results are in-sample for the threshold. Re-calibrate with real voices.

## Speaker identification
- Closest-profile accuracy on enrolled speakers (no threshold): **{closest_ok}/{closest_n}**
- Correct and above threshold: **{correct}/{closest_n}**
- Unknown-speaker clips rejected (below threshold): **{unk_rejected}/{unk_total}**
- Score against the correct profile: min {min(own_scores):.2f}, mean {statistics.mean(own_scores):.2f}.
  Best-match score for the unknown speaker: max {max(unknown_scores):.2f}, mean {statistics.mean(unknown_scores):.2f}.

Confusion matrix (counts, after threshold):

{header}{body}
## Transcription (local Whisper `base.en`, int8, faster-whisper)
Mean word error rate over {len(wers)} clips: **{mean_wer:.1%}** (clean synthetic speech; real microphones will be worse).

Worst clips:

{worst}""")
    print(DOC.read_text())


if __name__ == "__main__":
    main()
