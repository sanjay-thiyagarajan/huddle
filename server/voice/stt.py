"""Server-side transcription fallback (local Whisper via faster-whisper, no cloud calls).

The simulator uses the browser's Web Speech API first; this covers browsers without it.
"""
import os
from pathlib import Path

from .speaker_id import VoiceUnavailable, read_wav

_model = None


def _load():
    global _model
    if _model is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise VoiceUnavailable("Transcription needs the optional extra: pip install '.[voice]'") from e
        download = Path(os.environ.get("HUDDLE_MODEL_DIR", Path.home() / ".cache" / "huddle")) / "whisper"
        _model = WhisperModel(os.environ.get("HUDDLE_WHISPER_MODEL", "base.en"), device="cpu",
                              compute_type="int8", download_root=str(download))
    return _model


def transcribe(path: str | Path) -> str:
    # Pass samples, not a path: faster-whisper's own decoder (PyAV) failed on this install.
    segments, _ = _load().transcribe(read_wav(path), language="en", beam_size=1)
    return " ".join(s.text.strip() for s in segments).strip()
