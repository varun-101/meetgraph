"""Standalone STT worker (`python -m stt.worker`) — used by the compose `stt`
service. Polls for meetings stuck in `processing` without a transcript and runs
the capture pipeline. In native dev the API process runs the pipeline in-task,
so this worker is optional."""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from api.capture.pipeline import process_meeting
from api.db import async_session_maker
from api.models import Meeting, Transcript

log = logging.getLogger("stt.worker")
POLL_SECONDS = 15


async def run() -> None:
    log.info("STT worker started (poll=%ss)", POLL_SECONDS)
    while True:
        try:
            async with async_session_maker() as session:
                rows = (
                    await session.execute(
                        select(Meeting.id)
                        .outerjoin(Transcript, Transcript.meeting_id == Meeting.id)
                        .where(Meeting.status == "processing", Transcript.meeting_id.is_(None))
                    )
                ).scalars().all()
            for meeting_id in rows:
                log.info("processing meeting %s", meeting_id)
                await process_meeting(meeting_id)
        except Exception:
            log.exception("worker iteration failed")
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
