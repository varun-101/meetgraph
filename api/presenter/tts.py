"""edge-tts narration → 48kHz mono s16 PCM (LiveKit AudioSource format).

Decoding/resampling via PyAV (already a faster-whisper dependency). Any
failure returns b"" — the presenter shows slides silently rather than dying.
"""
from __future__ import annotations

import io
import logging

from api.config import settings

log = logging.getLogger(__name__)

SAMPLE_RATE = 48_000


async def synth(text: str) -> bytes:
    if not text.strip():
        return b""
    try:
        import edge_tts

        mp3 = io.BytesIO()
        communicate = edge_tts.Communicate(text, settings.tts_voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3.write(chunk["data"])
        mp3.seek(0)
        return _decode_to_pcm(mp3)
    except Exception:
        log.exception("TTS failed — presenting this slide silently")
        return b""


def _decode_to_pcm(buf: io.BytesIO) -> bytes:
    import av

    out = io.BytesIO()
    with av.open(buf) as container:
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        for frame in container.decode(stream):
            for rf in resampler.resample(frame):
                out.write(bytes(rf.planes[0]))
        # flush resampler
        for rf in resampler.resample(None):
            out.write(bytes(rf.planes[0]))
    return out.getvalue()
