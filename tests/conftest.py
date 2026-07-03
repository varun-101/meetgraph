"""Test fixtures: async in-memory SQLite, tables from Base.metadata, seeded RBAC world."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db import Base
from api.models import Org, OrgMember, Project, ProjectMember, User


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _user(email: str) -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        name=email.split("@")[0],
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> dict:
    """Two orgs; org1 has projects X (userA manager, userB member) and Y (userB
    manager); org2 has project Z (userC member, admin2 org-admin). userA is NOT
    in org2 at all. guest has no memberships anywhere."""
    user_a, user_b, user_c, admin2, guest = (
        _user("a@t.test"), _user("b@t.test"), _user("c@t.test"),
        _user("admin2@t.test"), _user("guest@t.test"),
    )
    org1, org2 = Org(name="org1"), Org(name="org2")
    session.add_all([user_a, user_b, user_c, admin2, guest, org1, org2])
    await session.flush()

    proj_x = Project(org_id=org1.id, name="X")
    proj_y = Project(org_id=org1.id, name="Y")
    proj_z = Project(org_id=org2.id, name="Z")
    session.add_all([proj_x, proj_y, proj_z])
    await session.flush()

    session.add_all(
        [
            OrgMember(org_id=org1.id, user_id=user_a.id, role="member"),
            OrgMember(org_id=org1.id, user_id=user_b.id, role="member"),
            OrgMember(org_id=org2.id, user_id=user_c.id, role="member"),
            OrgMember(org_id=org2.id, user_id=admin2.id, role="admin"),
            ProjectMember(project_id=proj_x.id, user_id=user_a.id, org_id=org1.id, role="manager"),
            ProjectMember(project_id=proj_x.id, user_id=user_b.id, org_id=org1.id, role="member"),
            ProjectMember(project_id=proj_y.id, user_id=user_b.id, org_id=org1.id, role="manager"),
            ProjectMember(project_id=proj_z.id, user_id=user_c.id, org_id=org2.id, role="member"),
        ]
    )
    await session.commit()
    return {
        "users": {"a": user_a, "b": user_b, "c": user_c, "admin2": admin2, "guest": guest},
        "orgs": {"org1": org1, "org2": org2},
        "projects": {"x": proj_x, "y": proj_y, "z": proj_z},
    }
