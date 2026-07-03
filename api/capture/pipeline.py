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
    async with async_session_maker() as session:
        recordings = (
            await session.execute(select(Recording).where(Recording.meeting_id == meeting_id))
        ).scalars().all()
        if not recordings:
            log.warning("no recordings for meeting %s — nothing to transcribe", meeting_id)
            return
        names = await _resolve_names(session, [r.participant_identity for r in recordings])

    # STT per track — CPU-bound, run in threads; per-track failure tolerated.
    from stt.transcribe import transcribe_track

    loop = asyncio.get_running_loop()
    results = await asyncio.gather(
        *[loop.run_in_executor(None, transcribe_track, r.file_path) for r in recordings],
        return_exceptions=True,
    )

    tracks = []
    for rec, segs in zip(recordings, results):
        if isinstance(segs, BaseException):
            log.error("STT failed for %s: %s", rec.file_path, segs)
            continue
        tracks.append((rec.participant_identity, names[rec.participant_identity], segs))
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
