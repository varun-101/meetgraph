"""FastAPI permission dependencies (§4.2 matrix). 403 on failure, 404 never leaked."""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_session
from api.deps import current_active_user
from api.models import Project, ProjectMember, User
from api.rbac.resolver import is_org_admin

_ROLE_ORDER = {"member": 0, "manager": 1}


async def get_project_role(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> str | None:
    row = await session.execute(
        select(ProjectMember.role).where(
            ProjectMember.user_id == user_id, ProjectMember.project_id == project_id
        )
    )
    return row.scalar_one_or_none()


def require_org_admin(org_id_param: str = "org_id"):
    """Dependency factory: 403 unless current user is admin of the org named by
    the path/query param `org_id_param`."""

    async def dep(
        org_id: uuid.UUID,
        user: User = Depends(current_active_user),
        session: AsyncSession = Depends(get_session),
    ) -> User:
        if not await is_org_admin(session, user.id, org_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "org admin required")
        return user

    return dep


def require_project_role(min_role: str = "member"):
    """Dependency factory: 403 unless current user has >= min_role on the
    project (path param `project_id`). Org admins always pass (§4.2)."""

    async def dep(
        project_id: uuid.UUID,
        user: User = Depends(current_active_user),
        session: AsyncSession = Depends(get_session),
    ) -> User:
        role = await get_project_role(session, user.id, project_id)
        if role is not None and _ROLE_ORDER[role] >= _ROLE_ORDER[min_role]:
            return user
        # org admin override
        project = await session.get(Project, project_id)
        if project is not None and await is_org_admin(session, user.id, project.org_id):
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"project {min_role} required")

    return dep


async def ensure_project_access(
    session: AsyncSession, user: User, project_id: uuid.UUID, min_role: str = "member"
) -> Project:
    """Imperative variant for handlers that already have a session. Returns the
    project or raises 403/404."""
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    role = await get_project_role(session, user.id, project_id)
    if role is not None and _ROLE_ORDER[role] >= _ROLE_ORDER[min_role]:
        return project
    if await is_org_admin(session, user.id, project.org_id):
        return project
    raise HTTPException(status.HTTP_403_FORBIDDEN, f"project {min_role} required")
