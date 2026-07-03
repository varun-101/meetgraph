"""§4.4 enforcement — single chokepoint.

Every cognee call site takes dataset names from `allowed_datasets` only.
The user never supplies a dataset name directly.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import OrgMember, ProjectMember, User

ORG_SHARED_DATASET = "ds_org_shared"


async def is_org_admin(session: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID) -> bool:
    row = await session.execute(
        select(OrgMember.role).where(
            OrgMember.user_id == user_id, OrgMember.org_id == org_id
        )
    )
    role = row.scalar_one_or_none()
    return role == "admin"


async def allowed_datasets(
    session: AsyncSession,
    user: User,
    org_id: uuid.UUID,
    write: bool = False,
) -> list[str]:
    """Return the dataset names this user may read (or write) in this org.

    Read: every project membership in the org + ds_org_shared.
    Write: manager-role projects only, + ds_org_shared if org admin (§4.4).
    Guests have no project_members rows → always [] for reads and writes (§4.3).
    """
    rows = (
        await session.execute(
            select(ProjectMember.project_id, ProjectMember.role).where(
                ProjectMember.user_id == user.id, ProjectMember.org_id == org_id
            )
        )
    ).all()

    if write:
        datasets = [f"ds_{r.project_id}" for r in rows if r.role == "manager"]
        if await is_org_admin(session, user.id, org_id):
            datasets.append(ORG_SHARED_DATASET)
        return datasets

    if not rows and not await is_org_admin(session, user.id, org_id):
        # Not in the org at all → nothing, not even org-shared.
        return []
    return [f"ds_{r.project_id}" for r in rows] + [ORG_SHARED_DATASET]


def dataset_for_project(project_id: uuid.UUID) -> str:
    """The only place the ds_{project_id} convention is spelled."""
    return f"ds_{project_id}"
