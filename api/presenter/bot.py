"""Presenter bot: a VISIBLE LiveKit participant that screenshares a generated
deck (headless Chromium via Playwright) and narrates it (edge-tts).

V1: directable. Commands ("show the action items", "what did we decide about
X?") arrive via POST /presenter/command, are resolved to intents (DeepSeek,
with a heuristic fallback), and can navigate the deck or synthesize a NEW
answer slide from project memory mid-meeting.

Lifecycle: preparing (deck + browser + join) → live (control loop) → stopped.
Self-stops when the last human leaves; the recorder bot then closes the room.
Any fatal error stops the session cleanly — never crashes the API process.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
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
COMMAND_QUEUE_MAX = 4

INTENT_SYSTEM = """You route a spoken/typed command for a slide presenter bot.
Return STRICT JSON: {"action": "next"|"prev"|"goto"|"answer",
"slide_index": int|null, "query": str|null}.
- "goto" when the command asks for an existing slide; pick slide_index from
  the numbered slide titles provided.
- "answer" when it asks a question or for content not on an existing slide;
  put the question in `query`.
- "next"/"prev" for navigation. When unsure, prefer "answer"."""


@dataclass
class PresenterSession:
    meeting_id: uuid.UUID
    status: str = "preparing"  # preparing | live | stopped
    current_slide: int = 0
    slide_count: int = 0
    handling_command: bool = False
    error: str | None = None
    task: asyncio.Task | None = None
    commands: asyncio.Queue = field(
        default_factory=lambda: asyncio.Queue(maxsize=COMMAND_QUEUE_MAX)
    )
    _interrupt: asyncio.Event = field(default_factory=asyncio.Event)
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
    _enqueue(meeting_id, ("nav", "next", None))


def submit_command(meeting_id: uuid.UUID, user_id: uuid.UUID, text: str) -> None:
    _enqueue(meeting_id, ("command", text, user_id))


def stop_presenter(meeting_id: uuid.UUID) -> None:
    session = _sessions.get(meeting_id)
    if session is None:
        return
    session._stop.set()
    session._interrupt.set()


def _enqueue(meeting_id: uuid.UUID, item: tuple) -> None:
    session = _sessions.get(meeting_id)
    if session is None or session.status != "live":
        raise RuntimeError("no live presenter for this meeting")
    try:
        session.commands.put_nowait(item)
        session._interrupt.set()  # cut current narration short
    except asyncio.QueueFull as exc:
        raise RuntimeError("presenter is busy — try again in a moment") from exc


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
            meeting, project, org_id = await _meeting_org_project(db, meeting_id)
            room_name = meeting.livekit_room

        deck = await build_deck(project.id)
        session.slide_count = len(deck.slides)
        deck_path = render_deck(deck, meeting_id)

        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(args=["--force-device-scale-factor=1"])
        page = await browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        await page.goto(deck_path.as_uri())

        token = mint_livekit_token(
            identity="presenter-bot",
            name="Presenter",
            room=room_name,
            role="presenter",
            ttl_minutes=8 * 60,
            can_publish=True,
        )
        room = rtc.Room()

        @room.on("participant_disconnected")
        def on_participant_disconnected(*_a) -> None:
            humans = [
                p for p in room.remote_participants.values()
                if p.identity not in BOT_IDENTITIES
            ]
            if not humans:
                stop_presenter(meeting_id)  # last human left — wrap up

        @room.on("disconnected")
        def on_disconnected(*_a) -> None:
            session._stop.set()
            session._interrupt.set()

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

        try:
            await _control_loop(
                session, page, deck, meeting_id, project, org_id, audio_source, synth, render_deck
            )
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


async def _control_loop(
    session, page, deck, meeting_id, project, org_id, audio_source, synth, render_deck
) -> None:
    """Present slide → wait for command/auto-advance → repeat. Auto-advance
    runs once through the initial deck; afterwards the bot idles awaiting
    commands until stopped."""
    i = 0
    auto_advanced_through = False
    await _present(session, page, deck, i, audio_source, synth)

    while not session._stop.is_set():
        last = len(deck.slides) - 1
        timeout = SLIDE_PAUSE_S if (not auto_advanced_through and i < last) else None
        try:
            item = await asyncio.wait_for(session.commands.get(), timeout)
        except asyncio.TimeoutError:
            i += 1  # auto-advance
            if i >= last:
                auto_advanced_through = True
            await _present(session, page, deck, i, audio_source, synth)
            continue

        kind, payload, user_id = item
        if kind == "nav":
            i = min(i + 1, last) if payload == "next" else max(i - 1, 0)
            if i == last:
                auto_advanced_through = True
            await _present(session, page, deck, i, audio_source, synth)
        elif kind == "command":
            session.handling_command = True
            try:
                new_index = await _handle_command(
                    session, page, deck, meeting_id, project, org_id, payload, user_id, render_deck
                )
                if new_index is not None:
                    i = new_index
                    session.slide_count = len(deck.slides)
                    await _present(session, page, deck, i, audio_source, synth)
            except Exception:
                log.exception("command handling failed: %r", payload)
            finally:
                session.handling_command = False


async def _present(session, page, deck, index, audio_source, synth) -> None:
    index = max(0, min(index, len(deck.slides) - 1))
    session.current_slide = index
    session._interrupt.clear()
    await page.evaluate(f"window.showSlide({index})")
    pcm = await synth(deck.slides[index].narration)
    await _speak(audio_source, pcm, session)


async def _handle_command(
    session, page, deck, meeting_id, project, org_id, text, user_id, render_deck
) -> int | None:
    """Resolve a command to an intent; may mutate the deck (answer slides)."""
    intent = await _resolve_intent(text, [s.title for s in deck.slides])
    action = intent.get("action")
    last = len(deck.slides) - 1

    if action == "next":
        return min(session.current_slide + 1, last)
    if action == "prev":
        return max(session.current_slide - 1, 0)
    if action == "goto":
        idx = intent.get("slide_index")
        if isinstance(idx, int) and 0 <= idx <= last:
            return idx
        return None

    # answer: query project memory → new cited slide appended to the deck
    query = (intent.get("query") or text).strip()
    from api.db import async_session_maker
    from api.memory.memory_service import memory_service
    from api.presenter.deck import Slide
    from api.rbac.audit import write_audit
    from api.rbac.resolver import dataset_for_project

    dataset = dataset_for_project(project.id)
    result = await memory_service.search(org_id, [dataset], query)
    async with async_session_maker() as db:
        await write_audit(db, org_id, user_id, "search", dataset, meeting_id)
        await db.commit()

    answer = (result.get("answer") or "").strip()
    if not answer:
        answer = "I could not find anything about that in this project's memory."
    sources = [
        c.get("source") for c in result.get("citations", [])
        if isinstance(c, dict) and c.get("source")
    ]
    bullets = [ln.strip("-• ").strip() for ln in answer.splitlines() if ln.strip()][:5]
    if sources:
        bullets.append("Sources: " + ", ".join(dict.fromkeys(sources)))

    deck.slides.append(
        Slide(
            title=query[:70] or "Answer",
            bullets=bullets or [answer[:100]],
            narration=answer[:600],
        )
    )
    # re-render the surface with the new slide and reload the page
    deck_path = render_deck(deck, meeting_id)
    await page.goto(deck_path.as_uri())
    return len(deck.slides) - 1


async def _resolve_intent(text: str, slide_titles: list[str]) -> dict:
    """DeepSeek JSON intent; heuristic fallback keeps commands working offline."""
    if settings.llm_api_key:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(base_url=settings.llm_endpoint, api_key=settings.llm_api_key)
            titles = "\n".join(f"{i}: {t}" for i, t in enumerate(slide_titles))
            resp = await client.chat.completions.create(
                model=settings.llm_model.split("/")[-1],
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": INTENT_SYSTEM},
                    {"role": "user", "content": f"Slides:\n{titles}\n\nCommand: {text}"},
                ],
                temperature=0.0,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            if data.get("action") in ("next", "prev", "goto", "answer"):
                return data
        except Exception:
            log.exception("intent resolution failed — falling back to heuristics")
    return parse_intent_fallback(text, slide_titles)


def parse_intent_fallback(text: str, slide_titles: list[str]) -> dict:
    """No-LLM intent routing: nav keywords → nav; title word overlap → goto;
    otherwise treat as a memory question."""
    t = text.lower().strip()
    if t in ("next", "next slide", "forward", "continue"):
        return {"action": "next", "slide_index": None, "query": None}
    if t in ("back", "prev", "previous", "go back", "previous slide"):
        return {"action": "prev", "slide_index": None, "query": None}
    words = set(t.replace("?", "").split())
    best_i, best_overlap = None, 0
    for i, title in enumerate(slide_titles):
        overlap = len(words & set(title.lower().split()))
        if overlap > best_overlap:
            best_i, best_overlap = i, overlap
    if best_i is not None and best_overlap >= 2:
        return {"action": "goto", "slide_index": best_i, "query": None}
    return {"action": "answer", "slide_index": None, "query": text}


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
    """Push PCM as 20ms frames; AudioSource's queue paces playback. Interrupted
    by stop or by any queued command (so the bot yields to the humans)."""
    if not pcm:
        return
    samples_per_frame = AUDIO_RATE * FRAME_MS // 1000
    bytes_per_frame = samples_per_frame * 2  # s16 mono
    for off in range(0, len(pcm) - bytes_per_frame + 1, bytes_per_frame):
        if session._stop.is_set() or session._interrupt.is_set():
            source.clear_queue()
            return
        frame = rtc.AudioFrame(
            data=pcm[off : off + bytes_per_frame],
            sample_rate=AUDIO_RATE,
            num_channels=1,
            samples_per_channel=samples_per_frame,
        )
        await source.capture_frame(frame)
    with contextlib.suppress(Exception):
        await source.wait_for_playout()
