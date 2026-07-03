"""LiveKit webhook receiver (§7): room_started → recorder bot + status live;
room_finished → status processing + capture pipeline.

Signature verification per livekit-api 1.1.1: WebhookReceiver(TokenVerifier).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from livekit.api import TokenVerifier, WebhookReceiver
from sqlalchemy import select

from api.config import settings
from api.db import async_session_maker
from api.models import Meeting

log = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

_receiver = WebhookReceiver(
    TokenVerifier(api_key=settings.livekit_webhook_key, api_secret=settings.livekit_api_secret)
)


async def _meeting_by_room(session, room_name: str) -> Meeting | None:
    return (
        await session.execute(select(Meeting).where(Meeting.livekit_room == room_name))
    ).scalar_one_or_none()


@router.post("/webhooks/livekit")
async def livekit_webhook(request: Request) -> dict:
    body = (await request.body()).decode("utf-8")
    auth = request.headers.get("Authorization", "")
    try:
        event = _receiver.receive(body, auth)
    except Exception as exc:  # bad signature / malformed
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid webhook signature") from exc

    kind = event.event
    room_name = event.room.name if event.room else ""
    log.info("livekit webhook: %s room=%s", kind, room_name)

    if not room_name.startswith("mg_"):
        return {"ok": True, "ignored": True}

    async with async_session_maker() as session:
        meeting = await _meeting_by_room(session, room_name)
        if meeting is None:
            return {"ok": True, "unknown_room": True}

        if kind == "room_started":
            meeting.status = "live"
            meeting.started_at = datetime.now(timezone.utc)
            await session.commit()
            from api.capture.recorder import start_recorder

            asyncio.get_running_loop().create_task(
                start_recorder(meeting.id, room_name), name=f"recorder-{room_name}"
            )

        elif kind == "room_finished":
            meeting.status = "processing"
            meeting.ended_at = datetime.now(timezone.utc)
            await session.commit()
            from api.capture.pipeline import process_meeting

            asyncio.get_running_loop().create_task(
                process_meeting(meeting.id), name=f"pipeline-{meeting.id}"
            )

        # participant_joined / others: no-op for MVP

    return {"ok": True}
