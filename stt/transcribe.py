"""faster-whisper wrapper (verified against 1.2.1): lazy singleton model,
word timestamps, CPU int8. `transcribe` is CPU-bound and blocking — callers
run it in a thread executor (see api/capture/pipeline.py)."""
from __future__ import annotations

import threading
from typing import Any

from api.config import settings

_model = None
_lock = threading.Lock()


def get_model():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(
                settings.stt_model,
                device=settings.stt_device,
                compute_type=settings.stt_compute_type,
            )
        return _model


def transcribe_track(path: str) -> list[dict[str, Any]]:
    """Transcribe one WAV → list of segment dicts with word timestamps
    (the shape api.capture.assembler consumes)."""
    model = get_model()
    segments, _info = model.transcribe(path, word_timestamps=True)
    out: list[dict[str, Any]] = []
    for seg in segments:  # lazy generator — iteration runs the model
        out.append(
            {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text,
                "words": [
                    {"word": w.word, "start": float(w.start), "end": float(w.end)}
                    for w in (seg.words or [])
                ],
            }
        )
    return out
