"""Speaker enrolment and identification: a STAND-IN for Alexa person recognition.

It separates profiles on one shared device. It is not authentication. Voiceprints are
biometric data: they stay on this machine, and `forget` deletes one.
Uses SpeechBrain ECAPA-TDNN (speechbrain/spkrec-ecapa-voxceleb, Apache-2.0) when the `voice`
extra is installed; otherwise the API says so and the profile switcher is the fallback.
"""
import io
import os
from pathlib import Path

import numpy as np

MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
SAMPLE_RATE = 16000
# Cosine-similarity floor for "recognized". Placed in the gap between genuine and unknown-speaker scores
# measured on SYNTHETIC voices (docs/voice-accuracy.md); re-calibrate with real voices.
THRESHOLD = float(os.environ.get("HUDDLE_VOICE_THRESHOLD", "0.50"))

_classifier = None


class VoiceUnavailable(RuntimeError):
    pass


def _load_classifier():
    global _classifier
    if _classifier is None:
        try:
            from speechbrain.inference.speaker import EncoderClassifier
        except ImportError as e:  # extra not installed
            raise VoiceUnavailable("Voice ID needs the optional extra: pip install '.[voice]'") from e
        cache = Path(os.environ.get("HUDDLE_MODEL_DIR", Path.home() / ".cache" / "huddle")) / "ecapa"
        _classifier = EncoderClassifier.from_hparams(source=MODEL_SOURCE, savedir=str(cache),
                                                     run_opts={"device": "cpu"})
    return _classifier


def read_wav(data: bytes | str | Path) -> np.ndarray:
    """Mono float32 at 16 kHz from WAV bytes or a path."""
    try:
        import soundfile as sf
    except ImportError as e:
        raise VoiceUnavailable("Voice ID needs the optional extra: pip install '.[voice]'") from e
    audio, sr = sf.read(io.BytesIO(data) if isinstance(data, bytes) else str(data), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SAMPLE_RATE:
        import torch
        import torchaudio.functional as F

        audio = F.resample(torch.from_numpy(audio), sr, SAMPLE_RATE).numpy()
    return audio


def embed(data: bytes | str | Path) -> np.ndarray:
    import torch

    audio = read_wav(data)
    if len(audio) < SAMPLE_RATE // 2:
        raise ValueError("Recording is too short. Speak for at least a second.")
    with torch.no_grad():
        vec = _load_classifier().encode_batch(torch.from_numpy(audio).unsqueeze(0))
    v = vec.squeeze().cpu().numpy().astype("float64")
    return v / np.linalg.norm(v)


def enrol_profile(clips: list[np.ndarray]) -> np.ndarray:
    """A profile is the normalised mean of its enrolment embeddings."""
    m = np.mean(clips, axis=0)
    return m / np.linalg.norm(m)


def identify(vec: np.ndarray, profiles: dict[str, np.ndarray], threshold: float = THRESHOLD
             ) -> tuple[str | None, float]:
    """Best-matching profile and its cosine score; None when nothing clears the threshold."""
    if not profiles:
        return None, 0.0
    scores = {n: float(np.dot(vec, p)) for n, p in profiles.items()}
    best = max(scores, key=scores.get)
    return (best if scores[best] >= threshold else None), scores[best]
