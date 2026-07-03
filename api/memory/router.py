"""RBAC-gated memory endpoints (§6 P3): cited Q&A, pre-meeting brief,
re-ingest, dataset delete. Dataset names come ONLY from allowed_datasets."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_session
from api.deps import current_active_user
from api.memory.memory_service import MemoryUnavailable, memory_service
from api.models import Project, User
from api.rbac.audit import write_audit
from api.rbac.guards import ensure_project_access
from api.rbac.resolver import allowed_datasets, dataset_for_project, is_org_admin

router = APIRouter(prefix="/memory", tags=["memory"])


class SearchIn(BaseModel):
    org_id: uuid.UUID
    project_id: uuid.UUID | None = None
    query: str
    search_type: str = "GRAPH_COMPLETION"


@router.post("/search")
async def search(
    body: SearchIn,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    datasets = await allowed_datasets(session, user, body.org_id)
    if body.project_id is not None:
        wanted = dataset_for_project(body.project_id)
        datasets = [d for d in datasets if d == wanted]
    if not datasets:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no queryable datasets in this org")
    try:
        result = await memory_service.search(body.org_id, datasets, body.query, body.search_type)
    except MemoryUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    for d in datasets:
        await write_audit(session, body.org_id, user.id, "search", d)
    await session.commit()
    return result


@router.get("/brief/{project_id}")
async def brief(
    project_id: uuid.UUID,
    force: bool = False,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Pre-meeting brief: open decisions, action items, recent topics.

    Cached in sync_state until the project's memory changes (fingerprint =
    latest add/cognify audit ts for the dataset). ?force=true regenerates.
    """
    import json

    from sqlalchemy import func, select as sa_select

    from api.models import AuditLog, SyncState

    project = await ensure_project_access(session, user, project_id, min_role="member")
    dataset = dataset_for_project(project_id)

    last_write = (
        await session.execute(
            sa_select(func.max(AuditLog.ts)).where(
                AuditLog.dataset == dataset, AuditLog.op.in_(["add", "cognify"])
            )
        )
    ).scalar_one_or_none()
    fingerprint = last_write.isoformat() if last_write else "empty"

    cache_key = f"brief:{project_id}"
    cached_row = await session.get(SyncState, cache_key)
    if cached_row and not force:
        try:
            cached = json.loads(cached_row.value or "{}")
            if cached.get("fingerprint") == fingerprint:
                return {
                    "project_id": str(project_id),
                    "markdown": cached["markdown"],
                    "citations": cached.get("citations", []),
                    "generated_at": cached.get("generated_at"),
                    "cached": True,
                }
        except (ValueError, KeyError):
            pass  # corrupt cache — regenerate

    query = (
        f"Produce a concise pre-meeting brief for project '{project.name}' as markdown "
        "with sections: Recent Decisions (with who made them), Open Action Items "
        "(with owners and deadlines), Active Topics. Cite the source meetings."
    )
    try:
        result = await memory_service.search(project.org_id, [dataset], query)
    except MemoryUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    from datetime import datetime, timezone

    generated_at = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(
        {
            "fingerprint": fingerprint,
            "markdown": result["answer"],
            "citations": result["citations"],
            "generated_at": generated_at,
        }
    )
    if cached_row:
        cached_row.value = payload
    else:
        session.add(SyncState(key=cache_key, value=payload))
    await write_audit(session, project.org_id, user.id, "search", dataset)
    await session.commit()
    return {
        "project_id": str(project_id),
        "markdown": result["answer"],
        "citations": result["citations"],
        "generated_at": generated_at,
        "cached": False,
    }


@router.post("/reingest/{meeting_id}", status_code=202)
async def reingest(
    meeting_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from api.models import Meeting

    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "meeting not found")
    # §4.2: write memory = manager+
    await ensure_project_access(session, user, meeting.project_id, min_role="manager")
    import asyncio

    from api.memory.pipeline import reingest_meeting

    asyncio.get_running_loop().create_task(reingest_meeting(meeting_id, user.id))
    return {"status": "queued"}


@router.delete("/project/{project_id}", status_code=202)
async def forget_project(
    project_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """§4.2: delete/forget dataset = org admin only. GDPR path (P5)."""
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    if not await is_org_admin(session, user.id, project.org_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "org admin required")
    dataset = dataset_for_project(project_id)
    try:
        await memory_service.forget_dataset(project.org_id, dataset)
    except MemoryUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    await write_audit(session, project.org_id, user.id, "forget", dataset)
    await session.commit()
    return {"status": "forgotten", "dataset": dataset}
