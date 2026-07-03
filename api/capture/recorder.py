"""Dev recorder bot (§3.3): hidden LiveKit participant that subscribes to every
remote audio track and writes per-track WAV. Replaced by Egress at P5.

Per-track capture is the product wedge — each WAV belongs to exactly one
participant, so speaker attribution is a fact (plan §2).

API verified against livekit (rtc) 1.1.13: sync @room.on callbacks spawning
tasks; AudioStream.from_track yields AudioFrameEvent with int16 PCM frames.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
import wave
from pathlib import Path

from livekit import rtc

from api.config import settings
from api.db import async_session_maker
from api.models import Recording

log = logging.getLogger(__name__)

SAMPLE_RATE = 48_000
NUM_CHANNELS = 1


async def start_recorder(meeting_id: uuid.UUID, room_name: str) -> None:
    """Connect the bot, record all remote audio tracks, return when the room closes."""
    from api.meetings.router import mint_livekit_token

    out_dir = Path(settings.recordings_dir) / str(meeting_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    token = mint_livekit_token(
        identity="recorder-bot",
        name="Recorder",
        room=room_name,
        role="recorder",
        ttl_minutes=24 * 60,
        can_publish=False,
    )

    room = rtc.Room()
    tasks: set[asyncio.Task] = set()
    closed = asyncio.Event()

    @room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track, pub: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant
    ) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            t = asyncio.create_task(
                _record_track(meeting_id, out_dir, track, participant.identity)
            )
            tasks.add(t)
            t.add_done_callback(tasks.discard)

    @room.on("disconnected")
    def on_disconnected(*_args) -> None:
        closed.set()

    try:
        await room.connect(settings.livekit_url, token)
        log.info("recorder joined %s", room_name)
        await closed.wait()
    except Exception:
        log.exception("recorder failed for %s", room_name)
    finally:
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        with contextlib.suppress(Exception):
            await room.disconnect()
        log.info("recorder left %s", room_name)


async def _record_track(
    meeting_id: uuid.UUID, out_dir: Path, track: rtc.Track, identity: str
) -> None:
    """Record one participant's audio track to WAV; one failure never kills others."""
    if identity == "recorder-bot":
        return
    path = out_dir / f"{_safe(identity)}.wav"
    frames_written = 0
    stream = rtc.AudioStream.from_track(
        track=track, sample_rate=SAMPLE_RATE, num_channels=NUM_CHANNELS
    )
    try:
        wf = wave.open(str(path), "wb")
        wf.setnchannels(NUM_CHANNELS)
        wf.setsampwidth(2)  # int16
        wf.setframerate(SAMPLE_RATE)
        try:
            async for event in stream:
                frame = event.frame
                wf.writeframes(frame.data)
                frames_written += frame.samples_per_channel
        finally:
            wf.close()
            await stream.aclose()
    except Exception:
        log.exception("track recording failed: meeting=%s identity=%s", meeting_id, identity)
        return

    duration = frames_written / SAMPLE_RATE
    if duration <= 0:
        return
    async with async_session_maker() as session:
        session.add(
            Recording(
                meeting_id=meeting_id,
                participant_identity=identity,
                file_path=str(path),
                duration=duration,
            )
        )
        await session.commit()
    log.info("recorded %s (%.1fs) -> %s", identity, duration, path)


def _safe(identity: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in identity)
