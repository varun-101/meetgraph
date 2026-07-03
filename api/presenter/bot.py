"""Presenter bot: a VISIBLE LiveKit participant that screenshares a generated
deck (headless Chromium via Playwright) and narrates it (edge-tts).

Lifecycle: preparing (deck + browser + join) → live (slide loop) → stopped.
Self-stops when the last human leaves; the recorder bot then closes the room.
Any fatal error stops the session cleanly — never crashes the API process.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass, field

from livekit import rtc
from livekit.rtc import TrackPublishOptions, TrackSource, VideoBufferType

from api.config import settings

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 1280, 720
AUDIO_RATE = 48_000
FRAME_MS = 20  # audio frame size
BOT_IDENTITIES = {"recorder-bot", "presenter-bot"}
SLIDE_PAUSE_S = 2.0


@dataclass
class PresenterSession:
    meeting_id: uuid.UUID
    status: str = "preparing"  # preparing | live | stopped
    current_slide: int = 0
    slide_count: int = 0
    error: str | None = None
    task: asyncio.Task | None = None
    _advance: asyncio.Event = field(default_factory=asyncio.Event)
    _stop: asyncio.Event = field(default_factory=asyncio.Event)


_sessions: dict[uuid.UUID, PresenterSession] = {}


def get_session(meeting_id: uuid.UUID) -> PresenterSession | None:
    return _sessions.get(meeting_id)


def start_presenter(meeting_id: uuid.UUID) -> PresenterSession:
    existing = _sessions.get(meeting_id)
    if existing and existing.status != "stopped":
        raise RuntimeError("presenter already running for this meeting")
    session = PresenterSession(meeting_id=meeting_id)
    session.task = asyncio.get_running_loop().create_task(
        _run(session), name=f"presenter-{meeting_id}"
    )
    _sessions[meeting_id] = session
    return session


def next_slide(meeting_id: uuid.UUID) -> None:
    session = _sessions.get(meeting_id)
    if session is None or session.status != "live":
        raise RuntimeError("no live presenter for this meeting")
    session._advance.set()


def stop_presenter(meeting_id: uuid.UUID) -> None:
    session = _sessions.get(meeting_id)
    if session is None:
        return
    session._stop.set()


async def _run(session: PresenterSession) -> None:
    from api.capture.pipeline import _meeting_org_project  # (meeting, project, org_id)
    from api.db import async_session_maker
    from api.meetings.router import mint_livekit_token
    from api.presenter.deck import build_deck
    from api.presenter.surface import render_deck
    from api.presenter.tts import synth

    meeting_id = session.meeting_id
    browser = pw = room = None
    try:
        async with async_session_maker() as db:
            meeting, project, _org_id = await _meeting_org_project(db, meeting_id)
            room_name = meeting.livekit_room

        # 1) Deck (LLM) + surface (HTML)
        deck = await build_deck(project.id)
        session.slide_count = len(deck.slides)
        deck_path = render_deck(deck, meeting_id)

        # 2) Headless browser
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(args=["--force-device-scale-factor=1"])
        page = await browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        await page.goto(deck_path.as_uri())

        # 3) Join room, publish screenshare + audio
        token = mint_livekit_token(
            identity="presenter-bot",
            name="Presenter",
            room=room_name,
            role="presenter",
            ttl_minutes=8 * 60,
            can_publish=True,
            # visible on purpose — but never counts toward room occupancy
            # thanks to the bot-aware emptiness checks (see recorder.py)
        )
        room = rtc.Room()

        @room.on("participant_disconnected")
        def on_participant_disconnected(*_a) -> None:
            humans = [
                p for p in room.remote_participants.values()
                if p.identity not in BOT_IDENTITIES
            ]
            if not humans:
                session._stop.set()  # last human left — wrap up

        @room.on("disconnected")
        def on_disconnected(*_a) -> None:
            session._stop.set()

        await room.connect(settings.livekit_url, token)

        video_source = rtc.VideoSource(WIDTH, HEIGHT, is_screencast=True)
        video_track = rtc.LocalVideoTrack.create_video_track("deck", video_source)
        await room.local_participant.publish_track(
            video_track, TrackPublishOptions(source=TrackSource.SOURCE_SCREENSHARE)
        )
        audio_source = rtc.AudioSource(AUDIO_RATE, 1)
        audio_track = rtc.LocalAudioTrack.create_audio_track("narration", audio_source)
        await room.local_participant.publish_track(
            audio_track, TrackPublishOptions(source=TrackSource.SOURCE_MICROPHONE)
        )

        pump = asyncio.create_task(_video_pump(page, video_source, session))
        session.status = "live"
        log.info("presenter live in %s (%d slides)", room_name, session.slide_count)

        # 4) Slide loop: show → narrate → pause/advance
        try:
            for i, slide in enumerate(deck.slides):
                if session._stop.is_set():
                    break
                session.current_slide = i
                session._advance.clear()
                await page.evaluate(f"window.showSlide({i})")
                pcm = await synth(slide.narration)
                await _speak(audio_source, pcm, session)
                if session._stop.is_set():
                    break
                # brief pause; host can cut it short with "next"
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(session._advance.wait(), timeout=SLIDE_PAUSE_S)
            # hold the last slide until stopped or room empties
            if not session._stop.is_set():
                await session._stop.wait()
        finally:
            pump.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pump

    except Exception as exc:  # noqa: BLE001
        session.error = str(exc)
        log.exception("presenter failed for meeting %s", meeting_id)
    finally:
        session.status = "stopped"
        if room is not None:
            with contextlib.suppress(Exception):
                await room.disconnect()
        if browser is not None:
            with contextlib.suppress(Exception):
                await browser.close()
        if pw is not None:
            with contextlib.suppress(Exception):
                await pw.stop()
        log.info("presenter stopped for meeting %s", meeting_id)


async def _video_pump(page, source: rtc.VideoSource, session: PresenterSession) -> None:
    """Screenshot → RGBA → VideoFrame at settings.presenter_fps until cancelled."""
    import io

    from PIL import Image

    interval = 1.0 / max(1, settings.presenter_fps)
    while not session._stop.is_set():
        try:
            png = await page.screenshot(type="png")
            img = Image.open(io.BytesIO(png)).convert("RGBA")
            frame = rtc.VideoFrame(WIDTH, HEIGHT, VideoBufferType.RGBA, img.tobytes())
            source.capture_frame(frame)
        except Exception:
            log.debug("frame capture failed", exc_info=True)
        await asyncio.sleep(interval)


async def _speak(source: rtc.AudioSource, pcm: bytes, session: PresenterSession) -> None:
    """Push PCM as 20ms frames; AudioSource's queue paces playback. Interruptible."""
    if not pcm:
        return
    samples_per_frame = AUDIO_RATE * FRAME_MS // 1000
    bytes_per_frame = samples_per_frame * 2  # s16 mono
    for off in range(0, len(pcm) - bytes_per_frame + 1, bytes_per_frame):
        if session._stop.is_set() or session._advance.is_set():
            source.clear_queue()  # host skipped ahead — cut the narration
            return
        frame = rtc.AudioFrame(
            data=pcm[off : off + bytes_per_frame],
            sample_rate=AUDIO_RATE,
            num_channels=1,
            samples_per_channel=samples_per_frame,
        )
        await source.capture_frame(frame)
    # let the tail of the queue play out
    with contextlib.suppress(Exception):
        await source.wait_for_playout()
