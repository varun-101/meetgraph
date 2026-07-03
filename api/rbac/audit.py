"""§4.5 — every memory op writes an audit row."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from api.models import AuditLog


async def write_audit(
    session: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    op: str,
    dataset: str,
    meeting_id: uuid.UUID | None = None,
) -> None:
    """Insert an audit row. Caller owns the transaction (commit with the op it audits)."""
    session.add(
        AuditLog(org_id=org_id, user_id=user_id, op=op, dataset=dataset, meeting_id=meeting_id)
    )
    await session.flush()
