"""Permission-matrix basics (§4.2) via the imperative guard helpers."""
import pytest
from fastapi import HTTPException

from api.rbac.guards import ensure_project_access, get_project_role
from api.rbac.resolver import is_org_admin

pytestmark = pytest.mark.asyncio


async def test_roles_resolve(session, world):
    assert await get_project_role(session, world["users"]["a"].id, world["projects"]["x"].id) == "manager"
    assert await get_project_role(session, world["users"]["b"].id, world["projects"]["x"].id) == "member"
    assert await get_project_role(session, world["users"]["a"].id, world["projects"]["y"].id) is None
    assert await is_org_admin(session, world["users"]["admin2"].id, world["orgs"]["org2"].id)
    assert not await is_org_admin(session, world["users"]["a"].id, world["orgs"]["org1"].id)


async def test_member_cannot_act_as_manager(session, world):
    with pytest.raises(HTTPException) as e:
        await ensure_project_access(
            session, world["users"]["b"], world["projects"]["x"].id, min_role="manager"
        )
    assert e.value.status_code == 403


async def test_manager_passes(session, world):
    p = await ensure_project_access(
        session, world["users"]["a"], world["projects"]["x"].id, min_role="manager"
    )
    assert p.id == world["projects"]["x"].id


async def test_org_admin_override(session, world):
    """Org admin passes project checks without a membership row (§4.2 column 1)."""
    p = await ensure_project_access(
        session, world["users"]["admin2"], world["projects"]["z"].id, min_role="manager"
    )
    assert p.id == world["projects"]["z"].id


async def test_outsider_gets_403(session, world):
    with pytest.raises(HTTPException) as e:
        await ensure_project_access(
            session, world["users"]["c"], world["projects"]["x"].id, min_role="member"
        )
    assert e.value.status_code == 403
