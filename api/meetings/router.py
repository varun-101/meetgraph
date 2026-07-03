"""Meetings: CRUD, LiveKit token minting (P1 — where RBAC meets WebRTC),
guest invites, transcript + action-item access."""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from livekit import api as lk_api
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.db import get_session
from api.deps import current_active_user
from api.models import ActionItem, Meeting, MeetingGuest, Transcript, User
from api.rbac.guards import ensure_project_access, get_project_role
from api.rbac.resolver import is_org_admin

router = APIRouter(tags=["meetings"])


# ----- schemas -----


class MeetingCreate(BaseModel):
    project_id: uuid.UUID
    title: str


class MeetingOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    livekit_room: str
    status: str
    started_at: datetime | None
    ended_at: datetime | None

    model_config = {"from_attributes": True}


class GuestInvite(BaseModel):
    email: EmailStr


class ActionPatch(BaseModel):
    status: str  # open | in_progress | done


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ----- meetings CRUD -----


@router.get("/meetings", response_model=list[MeetingOut])
async def list_meetings(
    project_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> list[Meeting]:
    await ensure_project_access(session, user, project_id, min_role="member")
    rows = (
        await session.execute(
            select(Meeting).where(Meeting.project_id == project_id).order_by(Meeting.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.post("/meetings", response_model=MeetingOut, status_code=201)
async def create_meeting(
    body: MeetingCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> Meeting:
    # §4.2: create/host meetings = manager+ (org admin passes via guard)
    await ensure_project_access(session, user, body.project_id, min_role="manager")
    meeting_id = uuid.uuid4()
    meeting = Meeting(
        id=meeting_id,
        project_id=body.project_id,
        title=body.title,
        livekit_room=f"mg_{meeting_id}",
        status="scheduled",
    )
    session.add(meeting)
    await session.commit()
    return meeting


@router.get("/meetings/{meeting_id}", response_model=MeetingOut)
async def get_meeting(
    meeting_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> Meeting:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "meeting not found")
    await ensure_project_access(session, user, meeting.project_id, min_role="member")
    return meeting


# ----- token minting (P1 note: RBAC → LiveKit grants) -----


def mint_livekit_token(
    *, identity: str, name: str, room: str, role: str, ttl_minutes: int = 240,
    can_publish: bool = True, hidden: bool = False, recorder: bool = False,
) -> str:
    # hidden+recorder matter for the bot: a visible participant keeps the room
    # open forever, so room_finished never fires after the humans leave.
    return (
        lk_api.AccessToken(api_key=settings.livekit_api_key, api_secret=settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(name)
        .with_metadata(json.dumps({"role": role}))
        .with_ttl(timedelta(minutes=ttl_minutes))
        .with_grants(
            lk_api.VideoGrants(
                room_join=True, room=room, can_subscribe=True, can_publish=can_publish,
                hidden=hidden, recorder=recorder,
            )
        )
        .to_jwt()
    )


@router.post("/meetings/{meeting_id}/token")
async def meeting_token(
    meeting_id: uuid.UUID,
    guest_token: str | None = None,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "meeting not found")

    role = await get_project_role(session, user.id, meeting.project_id)
    if role is None:
        # org-admin override
        from api.models import Project

        proj = await session.get(Project, meeting.project_id)
        if proj is not None and await is_org_admin(session, user.id, proj.org_id):
            role = "manager"
    if role is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "join blocked: not a project member")

    token = mint_livekit_token(
        identity=str(user.id),
        name=user.name or user.email,
        room=meeting.livekit_room,
        role=role,
    )
    return {"token": token, "livekit_url": settings.livekit_url}


@router.post("/meetings/{meeting_id}/guest-token")
async def guest_meeting_token(
    meeting_id: uuid.UUID,
    guest_token: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Unauthenticated guest join: single-room, time-boxed (§4.1). The raw token
    from the invite link is hashed and matched against meeting_guests."""
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "meeting not found")
    row = (
        await session.execute(
            select(MeetingGuest).where(
                MeetingGuest.meeting_id == meeting_id,
                MeetingGuest.token_hash == _hash_token(guest_token),
            )
        )
    ).scalar_one_or_none()
    if row is None or row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid or expired guest invite")
    token = mint_livekit_token(
        identity=f"guest_{row.id}",
        name=row.email,
        room=meeting.livekit_room,
        role="guest",
        ttl_minutes=settings.guest_token_ttl_minutes,
    )
    return {"token": token, "livekit_url": settings.livekit_url}


@router.post("/meetings/{meeting_id}/guests", status_code=201)
async def invite_guest(
    meeting_id: uuid.UUID,
    body: GuestInvite,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "meeting not found")
    await ensure_project_access(session, user, meeting.project_id, min_role="manager")

    raw = secrets.token_urlsafe(32)
    guest = MeetingGuest(
        meeting_id=meeting_id,
        email=body.email,
        token_hash=_hash_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.guest_token_ttl_minutes),
    )
    session.add(guest)
    await session.commit()
    return {
        "guest_id": str(guest.id),
        "email": body.email,
        "join_url": f"{settings.web_origin}/room/{meeting_id}?guest_token={raw}",
        "expires_at": guest.expires_at.isoformat(),
    }


# ----- transcript & actions -----


@router.get("/meetings/{meeting_id}/transcript")
async def get_transcript(
    meeting_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "meeting not found")
    await ensure_project_access(session, user, meeting.project_id, min_role="member")
    t = await session.get(Transcript, meeting_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "transcript not ready")
    return {
        "meeting_id": str(meeting_id),
        "canonical_text": t.canonical_text,
        "utterances": t.json_utterances,
    }


@router.get("/meetings/{meeting_id}/actions")
async def list_meeting_actions(
    meeting_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "meeting not found")
    await ensure_project_access(session, user, meeting.project_id, min_role="member")
    rows = (
        await session.execute(select(ActionItem).where(ActionItem.meeting_id == meeting_id))
    ).scalars().all()
    return [_action_out(a) for a in rows]


@router.get("/projects/{project_id}/actions")
async def list_project_actions(
    project_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    await ensure_project_access(session, user, project_id, min_role="member")
    rows = (
        await session.execute(
            select(ActionItem).where(ActionItem.project_id == project_id).order_by(ActionItem.created_at)
        )
    ).scalars().all()
    return [_action_out(a) for a in rows]


@router.patch("/actions/{action_id}")
async def patch_action(
    action_id: uuid.UUID,
    body: ActionPatch,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if body.status not in ("open", "in_progress", "done"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad status")
    action = await session.get(ActionItem, action_id)
    if action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "action not found")
    # §4.2: write memory = manager+; the item's owner may also update their own
    if action.owner_user_id != user.id:
        await ensure_project_access(session, user, action.project_id, min_role="manager")
    action.status = body.status
    await session.commit()

    # sync status change into the graph as an append-only doc (§5.1 note) —
    # fire-and-forget; failure must not block the UI mutation.
    try:
        import asyncio

        from api.memory.pipeline import sync_action_status

        asyncio.get_running_loop().create_task(sync_action_status(action.id))
    except Exception:  # noqa: BLE001
        pass
    return _action_out(action)


def _action_out(a: ActionItem) -> dict:
    return {
        "id": str(a.id),
        "meeting_id": str(a.meeting_id),
        "project_id": str(a.project_id),
        "text": a.text,
        "owner_user_id": str(a.owner_user_id) if a.owner_user_id else None,
        "deadline": a.deadline.isoformat() if a.deadline else None,
        "status": a.status,
    }
