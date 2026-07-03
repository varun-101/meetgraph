"""§4.4 CI gate: cross-org and cross-project isolation via the resolver chokepoint.

'User A must get zero results from project B' — enforced here at the dataset
resolver, which is the only source of dataset names for every cognee call.
"""
import pytest

from api.rbac.resolver import ORG_SHARED_DATASET, allowed_datasets

pytestmark = pytest.mark.asyncio


async def test_cross_org_isolation(session, world):
    """User A (org1 only) gets ZERO datasets for org2 — not even org-shared."""
    got = await allowed_datasets(session, world["users"]["a"], world["orgs"]["org2"].id)
    assert got == []
    got_w = await allowed_datasets(
        session, world["users"]["a"], world["orgs"]["org2"].id, write=True
    )
    assert got_w == []


async def test_cross_project_isolation_same_org(session, world):
    """User A is in project X but not Y (same org): Y's dataset never appears."""
    got = await allowed_datasets(session, world["users"]["a"], world["orgs"]["org1"].id)
    assert f"ds_{world['projects']['x'].id}" in got
    assert f"ds_{world['projects']['y'].id}" not in got
    assert ORG_SHARED_DATASET in got


async def test_org2_user_sees_only_org2(session, world):
    got = await allowed_datasets(session, world["users"]["c"], world["orgs"]["org2"].id)
    assert got == [f"ds_{world['projects']['z'].id}", ORG_SHARED_DATASET]
    # and nothing from org1
    assert await allowed_datasets(session, world["users"]["c"], world["orgs"]["org1"].id) == []


async def test_write_excludes_member_role(session, world):
    """User B: manager of Y, member of X → write set is Y only (no org-shared,
    not org admin)."""
    got = await allowed_datasets(
        session, world["users"]["b"], world["orgs"]["org1"].id, write=True
    )
    assert got == [f"ds_{world['projects']['y'].id}"]


async def test_org_admin_write_gets_org_shared(session, world):
    """admin2 is org2 admin with no project memberships → write set is exactly
    org-shared."""
    got = await allowed_datasets(
        session, world["users"]["admin2"], world["orgs"]["org2"].id, write=True
    )
    assert got == [ORG_SHARED_DATASET]


async def test_guest_has_nothing(session, world):
    """§4.3: guests hold zero memory-query capability."""
    for org in world["orgs"].values():
        assert await allowed_datasets(session, world["users"]["guest"], org.id) == []
        assert (
            await allowed_datasets(session, world["users"]["guest"], org.id, write=True) == []
        )
