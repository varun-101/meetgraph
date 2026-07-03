"""Org/project/membership management + /rbac/me + audit view (§4.2 matrix)."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_session
from api.deps import current_active_user
from api.models import (
    AuditLog,
    Org,
    OrgMember,
    Project,
    ProjectMember,
    User,
)
from api.rbac.guards import ensure_project_access
from api.rbac.resolver import is_org_admin

router = APIRouter(prefix="/rbac", tags=["rbac"])


# ----- schemas -----


class OrgCreate(BaseModel):
    name: str


class ProjectCreate(BaseModel):
    org_id: uuid.UUID
    name: str


class MemberAdd(BaseModel):
    email: EmailStr
    role: str  # org: admin|member ; project: manager|member


class MembershipOut(BaseModel):
    org_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    name: str | None = None
    role: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None


class MeOut(BaseModel):
    user: UserOut
    orgs: list[MembershipOut]
    projects: list[MembershipOut]


class AuditOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    user_id: uuid.UUID | None
    op: str
    dataset: str
    meeting_id: uuid.UUID | None
    ts: datetime


# ----- me -----


@router.get("/me", response_model=MeOut)
async def me(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> MeOut:
    org_rows = (
        await session.execute(
            select(OrgMember, Org.name).join(Org, Org.id == OrgMember.org_id).where(
                OrgMember.user_id == user.id
            )
        )
    ).all()
    proj_rows = (
        await session.execute(
            select(ProjectMember, Project.name)
            .join(Project, Project.id == ProjectMember.project_id)
            .where(ProjectMember.user_id == user.id)
        )
    ).all()
    return MeOut(
        user=UserOut(id=user.id, email=user.email, name=user.name),
        orgs=[
            MembershipOut(org_id=m.OrgMember.org_id, name=m.name, role=m.OrgMember.role)
            for m in org_rows
        ],
        projects=[
            MembershipOut(
                project_id=m.ProjectMember.project_id,
                org_id=m.ProjectMember.org_id,
                name=m.name,
                role=m.ProjectMember.role,
            )
            for m in proj_rows
        ],
    )


# ----- orgs -----


@router.post("/orgs", status_code=201)
async def create_org(
    body: OrgCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    org = Org(name=body.name)
    session.add(org)
    await session.flush()
    session.add(OrgMember(org_id=org.id, user_id=user.id, role="admin"))
    await session.commit()
    return {"id": str(org.id), "name": org.name}


@router.post("/orgs/{org_id}/members", status_code=201)
async def add_org_member(
    org_id: uuid.UUID,
    body: MemberAdd,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not await is_org_admin(session, user.id, org_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "org admin required")
    if body.role not in ("admin", "member"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "role must be admin|member")
    target = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    session.add(OrgMember(org_id=org_id, user_id=target.id, role=body.role))
    await session.commit()
    return {"org_id": str(org_id), "user_id": str(target.id), "role": body.role}


# ----- projects -----


@router.post("/projects", status_code=201)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # §4.2: create/delete projects = org admin only
    if not await is_org_admin(session, user.id, body.org_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "org admin required")
    project = Project(org_id=body.org_id, name=body.name)
    session.add(project)
    await session.flush()
    # creator joins as manager so they can host meetings immediately
    session.add(
        ProjectMember(
            project_id=project.id, user_id=user.id, org_id=body.org_id, role="manager"
        )
    )
    await session.commit()
    return {"id": str(project.id), "org_id": str(body.org_id), "name": project.name}


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    if not await is_org_admin(session, user.id, project.org_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "org admin required")
    await session.delete(project)
    await session.commit()


@router.get("/projects")
async def list_projects(
    org_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    admin = await is_org_admin(session, user.id, org_id)
    if admin:
        rows = (
            await session.execute(select(Project).where(Project.org_id == org_id))
        ).scalars().all()
        member_roles: dict[uuid.UUID, str] = {}
    else:
        pairs = (
            await session.execute(
                select(Project, ProjectMember.role)
                .join(ProjectMember, ProjectMember.project_id == Project.id)
                .where(ProjectMember.user_id == user.id, Project.org_id == org_id)
            )
        ).all()
        rows = [p.Project for p in pairs]
        member_roles = {p.Project.id: p.role for p in pairs}
    return [
        {
            "id": str(p.id),
            "org_id": str(p.org_id),
            "name": p.name,
            "my_role": "admin" if admin else member_roles.get(p.id),
        }
        for p in rows
    ]


@router.post("/projects/{project_id}/members", status_code=201)
async def add_project_member(
    project_id: uuid.UUID,
    body: MemberAdd,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # managers and org admins may manage project membership
    project = await ensure_project_access(session, user, project_id, min_role="manager")
    if body.role not in ("manager", "member"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "role must be manager|member")
    target = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    session.add(
        ProjectMember(
            project_id=project_id, user_id=target.id, org_id=project.org_id, role=body.role
        )
    )
    await session.commit()
    return {"project_id": str(project_id), "user_id": str(target.id), "role": body.role}


# ----- audit (§4.5: admin sees all; manager sees own projects' datasets) -----


@router.get("/audit", response_model=list[AuditOut])
async def audit_log(
    org_id: uuid.UUID,
    limit: int = 200,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> list[AuditOut]:
    admin = await is_org_admin(session, user.id, org_id)
    q = select(AuditLog).where(AuditLog.org_id == org_id).order_by(desc(AuditLog.ts)).limit(limit)
    if not admin:
        managed = (
            await session.execute(
                select(ProjectMember.project_id).where(
                    ProjectMember.user_id == user.id,
                    ProjectMember.org_id == org_id,
                    ProjectMember.role == "manager",
                )
            )
        ).scalars().all()
        if not managed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin or manager required")
        q = q.where(AuditLog.dataset.in_([f"ds_{pid}" for pid in managed]))
    rows = (await session.execute(q)).scalars().all()
    return [AuditOut.model_validate(r, from_attributes=True) for r in rows]
