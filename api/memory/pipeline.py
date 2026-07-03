"""P3 memory pipeline (§6 order): transcript → add(doc, ds_{project}) →
cognify() once → extractor pass → meetings.status = ready. Every op audited."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from api.db import async_session_maker
from api.memory.extractor import extract_action_items
from api.memory.memory_service import memory_service
from api.models import ActionItem, Meeting, Project, Transcript, User
from api.rbac.audit import write_audit
from api.rbac.resolver import dataset_for_project

log = logging.getLogger(__name__)


def doc_header(project_name: str, participants: list[str], date_iso: str) -> str:
    """§5.2 convention — all sources, forever. Shared Person/Project/Topic
    strings are what let cognify merge entities across meetings."""
    return (
        f"[source: meeting] [project: {project_name}] "
        f"[participants: {', '.join(participants)}] [date: {date_iso}]"
    )


async def ingest_meeting(meeting_id: uuid.UUID) -> None:
    """Contract entrypoint (called by api.capture.pipeline after transcript upsert)."""
    async with async_session_maker() as session:
        meeting = await session.get(Meeting, meeting_id)
        if meeting is None:
            raise ValueError(f"meeting {meeting_id} not found")
        project = await session.get(Project, meeting.project_id)
        transcript = await session.get(Transcript, meeting_id)
        if transcript is None or not transcript.canonical_text:
            log.warning("no transcript for meeting %s — skipping ingest", meeting_id)
            return
        org_id = project.org_id
        dataset = dataset_for_project(project.id)
        participants = sorted(
            {u["speaker_name"] for u in (transcript.json_utterances or [])}
        )
        date_iso = (meeting.started_at or meeting.created_at or datetime.now(timezone.utc)).date().isoformat()

        doc = (
            doc_header(project.name, participants, date_iso)
            + f"\nMeeting: {meeting.title}\n\n"
            + transcript.canonical_text
        )

    # 1) add + 2) cognify — one cognify per meeting (§6 P3)
    await memory_service.add(org_id, dataset, doc)
    await memory_service.cognify(org_id, [dataset])

    # 3) extractor pass → action_items rows
    items = await extract_action_items(doc, participants)

    async with async_session_maker() as session:
        await write_audit(session, org_id, None, "add", dataset, meeting_id)
        await write_audit(session, org_id, None, "cognify", dataset, meeting_id)

        name_to_user = await _users_by_name(session, participants)
        for item in items:
            owner = name_to_user.get((item.get("owner_name") or "").strip().lower())
            deadline = _parse_deadline(item.get("deadline"))
            session.add(
                ActionItem(
                    meeting_id=meeting_id,
                    project_id=(await session.get(Meeting, meeting_id)).project_id,
                    text=item["text"],
                    owner_user_id=owner.id if owner else None,
                    deadline=deadline,
                    status="open",
                )
            )

        meeting = await session.get(Meeting, meeting_id)
        meeting.status = "ready"
        await session.commit()
    log.info("meeting %s ingested: dataset=%s actions=%d", meeting_id, dataset, len(items))


async def reingest_meeting(meeting_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Manager+ re-ingest (§8): superseding doc, same header; prune removes old."""
    await ingest_meeting(meeting_id)


async def sync_action_status(action_id: uuid.UUID) -> None:
    """§5.1: status changes sync into the graph via add() (append-only status
    doc), never by mutating graph nodes."""
    async with async_session_maker() as session:
        action = await session.get(ActionItem, action_id)
        if action is None:
            return
        project = await session.get(Project, action.project_id)
        dataset = dataset_for_project(project.id)
        org_id = project.org_id
        doc = (
            doc_header(project.name, [], datetime.now(timezone.utc).date().isoformat())
            + f'\nAction item status update: "{action.text}" is now {action.status}.'
        )
    try:
        await memory_service.add(org_id, dataset, doc)
        async with async_session_maker() as session:
            await write_audit(session, org_id, None, "add", dataset, action.meeting_id)
            await session.commit()
    except Exception:
        log.exception("action status sync failed for %s", action_id)


async def _users_by_name(session, names: list[str]) -> dict[str, User]:
    if not names:
        return {}
    rows = (await session.execute(select(User))).scalars().all()
    wanted = {n.strip().lower() for n in names}
    return {
        (u.name or u.email).strip().lower(): u
        for u in rows
        if (u.name or u.email).strip().lower() in wanted
    }


def _parse_deadline(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
