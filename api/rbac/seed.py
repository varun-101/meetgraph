"""Dev seed: two orgs, three users, two projects. Run: python -m api.rbac.seed"""
from __future__ import annotations

import asyncio
import uuid

from fastapi_users.password import PasswordHelper

from api.db import Base, async_session_maker, engine
from api.models import Org, OrgMember, Project, ProjectMember, User

USERS = [
    ("admin@acme.test", "Ada Admin", "password123"),
    ("manager@acme.test", "Mia Manager", "password123"),
    ("member@acme.test", "Max Member", "password123"),
]


async def seed() -> None:
    helper = PasswordHelper()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        users: list[User] = []
        for email, name, pw in USERS:
            u = User(
                id=uuid.uuid4(),
                email=email,
                name=name,
                hashed_password=helper.hash(pw),
                is_active=True,
                is_superuser=False,
                is_verified=True,
            )
            session.add(u)
            users.append(u)
        await session.flush()

        acme = Org(name="Acme Corp")
        globex = Org(name="Globex")  # second org — isolation testing
        session.add_all([acme, globex])
        await session.flush()

        session.add_all(
            [
                OrgMember(org_id=acme.id, user_id=users[0].id, role="admin"),
                OrgMember(org_id=acme.id, user_id=users[1].id, role="member"),
                OrgMember(org_id=acme.id, user_id=users[2].id, role="member"),
                OrgMember(org_id=globex.id, user_id=users[0].id, role="admin"),
            ]
        )

        apollo = Project(org_id=acme.id, name="Apollo")
        zephyr = Project(org_id=acme.id, name="Zephyr")
        session.add_all([apollo, zephyr])
        await session.flush()

        session.add_all(
            [
                ProjectMember(
                    project_id=apollo.id, user_id=users[1].id, org_id=acme.id, role="manager"
                ),
                ProjectMember(
                    project_id=apollo.id, user_id=users[2].id, org_id=acme.id, role="member"
                ),
                ProjectMember(
                    project_id=zephyr.id, user_id=users[1].id, org_id=acme.id, role="member"
                ),
            ]
        )
        await session.commit()

    print("Seeded. Logins (password123): " + ", ".join(e for e, _, _ in USERS))


if __name__ == "__main__":
    asyncio.run(seed())
