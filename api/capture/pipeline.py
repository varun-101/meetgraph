"""P2→P3 capture pipeline: recordings → STT per track → assemble → transcripts
row → hand off to memory ingest (§6 P3 order). Zero manual steps (P2 gate)."""
from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select

from api.capture.assembler import assemble_transcript
from api.db import async_session_maker
from api.models import Meeting, Recording, Transcript, User

log = logging.getLogger(__name__)


async def process_meeting(meeting_id: uuid.UUID) -> None:
    """Full post-meeting pipeline. Safe to re-run (upserts the transcript)."""
    tracks_src = await _load_recordings(meeting_id)
    if not tracks_src:
        log.warning("no recordings for meeting %s — nothing to transcribe", meeting_id)
        return
    async with async_session_maker() as session:
        names = await _resolve_names(session, [ident for ident, _, _ in tracks_src])

    # STT per track — CPU-bound and memory-hungry: run SEQUENTIALLY (parallel
    # tracks OOM'd on a 16GB box: mkl_malloc failures). Per-track failure tolerated.
    from stt.transcribe import transcribe_track

    loop = asyncio.get_running_loop()
    tracks = []
    for identity, path, offset in tracks_src:
        try:
            segs = await loop.run_in_executor(None, transcribe_track, path)
        except Exception as exc:  # noqa: BLE001
            log.error("STT failed for %s: %s", path, exc)
            continue
        # Shift this track onto the shared meeting timeline (tracks start when
        # their participant joins, not when the meeting does).
        if offset:
            for seg in segs:
                seg["start"] += offset
                seg["end"] += offset
                for w in seg.get("words", []):
                    w["start"] += offset
                    w["end"] += offset
        tracks.append((identity, names[identity], segs))
    if not tracks:
        log.error("all tracks failed STT for meeting %s", meeting_id)
        return

    utterances, canonical_text = assemble_transcript(tracks)

    async with async_session_maker() as session:
        existing = await session.get(Transcript, meeting_id)
        if existing is None:
            session.add(
                Transcript(
                    meeting_id=meeting_id,
                    canonical_text=canonical_text,
                    json_utterances=utterances,
                )
            )
        else:
            existing.canonical_text = canonical_text
            existing.json_utterances = utterances
        await session.commit()
    log.info("transcript stored for meeting %s (%d utterances)", meeting_id, len(utterances))

    # P3 handoff (CONTRACTS.md): memory failure leaves status=processing, not a crash.
    try:
        from api.memory.pipeline import ingest_meeting

        await ingest_meeting(meeting_id)
    except Exception:
        log.exception("memory ingest failed for meeting %s (status stays processing)", meeting_id)


async def _load_recordings(meeting_id: uuid.UUID) -> list[tuple[str, str, float]]:
    """(participant_identity, file_path, start_offset) per track. Retries
    briefly — the recorder bot inserts rows as its streams finalize, racing
    room_finished — then falls back to scanning the recordings directory
    (files survive even if row insertion was lost; offset unknown → 0)."""
    from pathlib import Path

    from api.config import settings

    for attempt in range(6):
        async with async_session_maker() as session:
            rows = (
                await session.execute(
                    select(Recording).where(Recording.meeting_id == meeting_id)
                )
            ).scalars().all()
        if rows:
            return [
                (r.participant_identity, r.file_path, r.start_offset or 0.0) for r in rows
            ]
        await asyncio.sleep(5)

    meeting_dir = Path(settings.recordings_dir) / str(meeting_id)
    wavs = sorted(meeting_dir.glob("*.wav")) if meeting_dir.exists() else []
    if wavs:
        log.warning("no recording rows for %s — using %d WAVs from disk", meeting_id, len(wavs))
    return [(p.stem, str(p), 0.0) for p in wavs if p.stem != "recorder-bot"]


async def _resolve_names(session, identities: list[str]) -> dict[str, str]:
    """identity is str(user_id) for members, 'guest_{id}' or arbitrary for guests."""
    names: dict[str, str] = {}
    user_ids: dict[str, uuid.UUID] = {}
    for ident in identities:
        try:
            user_ids[ident] = uuid.UUID(ident)
        except ValueError:
            names[ident] = ident.removeprefix("guest_") or ident
    if user_ids:
        rows = (
            await session.execute(select(User).where(User.id.in_(list(user_ids.values()))))
        ).scalars().all()
        by_id = {u.id: (u.name or u.email) for u in rows}
        for ident, uid in user_ids.items():
            names[ident] = by_id.get(uid, ident)
    return names


async def _meeting_org_project(session, meeting_id: uuid.UUID):
    """Helper shared with memory: (meeting, project, org_id)."""
    from api.models import Project

    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise ValueError(f"meeting {meeting_id} not found")
    project = await session.get(Project, meeting.project_id)
    return meeting, project, project.org_id
