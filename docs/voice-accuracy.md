# Voice accuracy (synthetic voices only)

Measured 2026-10-02 by `python tests/voice_eval.py`. **The clips are text-to-speech voices from macOS
`say`, not real people.** They show the enrol/identify/transcribe pipeline works and give a sanity check.
They do **not** tell us how accurate it is for real family members, who vary in mood, distance from the
microphone, background noise and colds. Real-voice numbers still need to be collected (plan P4/P6).

Voice identification here is a stand-in for Alexa person recognition. It separates profiles on a shared
device; it is not authentication.

## Setup
- Model: `speechbrain/spkrec-ecapa-voxceleb` (SpeechBrain ECAPA-TDNN), cosine similarity to a mean-of-3 profile.
- Enrolled voices (5): daniel, karen, moira, rishi, samantha. Enrolment: 3 clips each at 175 wpm.
- Test clips: 5 different sentences per voice at varied speaking rates (150-205 wpm), none seen at enrolment.
- Unknown speaker (never enrolled): tessa, same 5 sentences.
- Threshold for "recognized": cosine >= 0.5. It was set in the gap between these scores after a first run showed a 0.30 threshold passed with no margin, so these results are in-sample for the threshold. Re-calibrate with real voices.

## Speaker identification
- Closest-profile accuracy on enrolled speakers (no threshold): **25/25**
- Correct and above threshold: **25/25**
- Unknown-speaker clips rejected (below threshold): **5/5**
- Score against the correct profile: min 0.75, mean 0.85.
  Best-match score for the unknown speaker: max 0.30, mean 0.28.

Confusion matrix (counts, after threshold):

| true \ predicted | daniel | karen | moira | rishi | samantha | unknown |
|---|---|---|---|---|---|---|
| daniel | 5 | 0 | 0 | 0 | 0 | 0 |
| karen | 0 | 5 | 0 | 0 | 0 | 0 |
| moira | 0 | 0 | 5 | 0 | 0 | 0 |
| rishi | 0 | 0 | 0 | 5 | 0 | 0 |
| samantha | 0 | 0 | 0 | 0 | 5 | 0 |
| tessa | 0 | 0 | 0 | 0 | 0 | 5 |

## Transcription (local Whisper `base.en`, int8, faster-whisper)
Mean word error rate over 30 clips: **0.0%** (clean synthetic speech; real microphones will be worse).

Worst clips:

- daniel/t1: WER 0%, heard "I can do maybe 12 hours and $600 a month, but not nights."
- daniel/t2: WER 0%, heard "under $60 each, I would love good food and no crowds."
- daniel/t3: WER 0%, heard "remind everyone who has not answered yet."
