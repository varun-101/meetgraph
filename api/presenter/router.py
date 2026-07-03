"""Presenter endpoints: start / status / next / stop. Manager+ only (§4.2 —
presenting is hosting). Session registry is in-process, like the recorder."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_session
from api.deps import current_active_user
from api.models import Meeting, User
from api.presenter import bot
from api.rbac.guards import ensure_project_access

router = APIRouter(tags=["presenter"])


async def _live_meeting(session: AsyncSession, user: User, meeting_id: uuid.UUID) -> Meeting:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "meeting not found")
    await ensure_project_access(session, user, meeting.project_id, min_role="manager")
    return meeting


@router.post("/meetings/{meeting_id}/presenter", status_code=202)
async def start(
    meeting_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    meeting = await _live_meeting(session, user, meeting_id)
    if meeting.status != "live":
        raise HTTPException(status.HTTP_409_CONFLICT, "meeting is not live")
    try:
        s = bot.start_presenter(meeting_id)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"status": s.status}


@router.get("/meetings/{meeting_id}/presenter")
async def presenter_status(
    meeting_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "meeting not found")
    await ensure_project_access(session, user, meeting.project_id, min_role="member")
    s = bot.get_session(meeting_id)
    if s is None:
        return {"status": "none"}
    return {
        "status": s.status,
        "mode": s.mode,
        "current_slide": s.current_slide,
        "slide_count": s.slide_count,
        "handling_command": s.handling_command,
        "error": s.error,
    }


@router.post("/meetings/{meeting_id}/presenter/next")
async def advance(
    meeting_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _live_meeting(session, user, meeting_id)
    try:
        bot.next_slide(meeting_id)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"ok": True}


from pydantic import BaseModel, Field


class CommandIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@router.post("/meetings/{meeting_id}/presenter/command")
async def command(
    meeting_id: uuid.UUID,
    body: CommandIn,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Direct the presenter (V1): navigation or a memory question that becomes
    a new cited slide. Members may command; only managers stop (DELETE)."""
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "meeting not found")
    await ensure_project_access(session, user, meeting.project_id, min_role="member")
    try:
        bot.submit_command(meeting_id, user.id, body.text)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"ok": True}


@router.delete("/meetings/{meeting_id}/presenter", status_code=202)
async def stop(
    meeting_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _live_meeting(session, user, meeting_id)
    bot.stop_presenter(meeting_id)
    return {"status": "stopping"}
