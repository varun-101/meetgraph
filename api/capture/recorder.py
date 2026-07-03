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
import time
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
        hidden=True,      # a visible bot keeps the room open forever —
        recorder=True,    # room_finished would never fire after humans leave
    )

    room = rtc.Room()
    tasks: set[asyncio.Task] = set()
    closed = asyncio.Event()
    t0 = time.monotonic()  # meeting timeline zero = recorder join

    @room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track, pub: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant
    ) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            offset = time.monotonic() - t0
            t = asyncio.create_task(
                _record_track(meeting_id, out_dir, track, participant.identity, offset)
            )
            tasks.add(t)
            t.add_done_callback(tasks.discard)

    @room.on("participant_disconnected")
    def on_participant_disconnected(*_args) -> None:
        if not room.remote_participants:
            closed.set()  # last human left — finalize now, don't wait for timeout

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
        with contextlib.suppress(Exception):
            await room.disconnect()
        if tasks:
            # Streams may not terminate on abrupt room deletion — bound the
            # wait, then cancel; _record_track finalizes on cancellation.
            done, pending = await asyncio.wait(tasks, timeout=30)
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        # Close the room server-side so room_finished fires immediately
        # (auto-created rooms otherwise linger for the empty-room timeout).
        with contextlib.suppress(Exception):
            await _delete_room(room_name)
        log.info("recorder left %s", room_name)


async def _delete_room(room_name: str) -> None:
    from livekit import api as lk_api

    http_url = settings.livekit_url.replace("ws://", "http://").replace("wss://", "https://")
    lk = lk_api.LiveKitAPI(http_url, settings.livekit_api_key, settings.livekit_api_secret)
    try:
        await lk.room.delete_room(lk_api.DeleteRoomRequest(room=room_name))
    finally:
        await lk.aclose()


async def _record_track(
    meeting_id: uuid.UUID, out_dir: Path, track: rtc.Track, identity: str,
    start_offset: float = 0.0,
) -> None:
    """Record one participant's audio track to WAV; one failure never kills others."""
    if identity == "recorder-bot":
        return
    path = out_dir / f"{_safe(identity)}.wav"
    frames_written = 0
    stream = rtc.AudioStream.from_track(
        track=track, sample_rate=SAMPLE_RATE, num_channels=NUM_CHANNELS
    )
    wf = None
    try:
        wf = wave.open(str(path), "wb")
        wf.setnchannels(NUM_CHANNELS)
        wf.setsampwidth(2)  # int16
        wf.setframerate(SAMPLE_RATE)
        async for event in stream:
            frame = event.frame
            wf.writeframes(frame.data)
            frames_written += frame.samples_per_channel
    except asyncio.CancelledError:
        pass  # room closed abruptly — keep and finalize what we captured
    except Exception:
        log.exception("track recording failed: meeting=%s identity=%s", meeting_id, identity)
    finally:
        if wf is not None:
            with contextlib.suppress(Exception):
                wf.close()  # must run or the WAV header stays a placeholder
        with contextlib.suppress(Exception):
            # aclose() can hang after an abrupt room teardown (observed live:
            # header patched but the row insert below never ran) — bound it.
            await asyncio.wait_for(stream.aclose(), timeout=5)

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
                start_offset=round(start_offset, 3),
            )
        )
        await session.commit()
    log.info("recorded %s (%.1fs) -> %s", identity, duration, path)


def _safe(identity: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in identity)
