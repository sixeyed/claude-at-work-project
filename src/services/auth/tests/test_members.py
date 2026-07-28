"""Workspace membership management (spec §3).

The reads are straightforward. What these tests are really for is the four ways
a membership write must refuse:

* a caller whose token names a different workspace (Conventions §5.4);
* a caller who is in the workspace but not entitled to administer it;
* a change that would leave the workspace with no owner;
* and — the one with teeth — a removal that leaves the removed user's refresh
  token still able to mint access tokens for the workspace they just left.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from tests import dexflow
from tests.conftest import ADA, ALAN, DEMO_WORKSPACE, DEX_PASSWORD, GRACE
from tests.dexflow import renewed, session_cookie

pytestmark = pytest.mark.integration


async def sign_in(client: httpx.AsyncClient, email: str) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def own_workspace(client: httpx.AsyncClient, tokens: dict[str, Any]) -> str:
    resp = await client.get("/api/v1/workspaces", headers=bearer(tokens))
    return next(w["id"] for w in resp.json()["items"] if w["role"] == "owner")


async def workspace_named(client: httpx.AsyncClient, tokens: dict[str, Any], name: str) -> str:
    resp = await client.get("/api/v1/workspaces", headers=bearer(tokens))
    return next(w["id"] for w in resp.json()["items"] if w["name"] == name)


async def switch_to(
    client: httpx.AsyncClient, tokens: dict[str, Any], workspace_id: str
) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/auth/switch-workspace",
        json={"workspaceId": workspace_id},
        headers=session_cookie(tokens),
    )
    assert resp.status_code == 200, resp.text
    # `renewed`, not `.json()`: switching rotates the cookie, and a caller that
    # kept the old session dict would be holding a token the server has retired.
    return renewed(resp)


async def add(
    client: httpx.AsyncClient, tokens: dict[str, Any], workspace: str, **body: Any
) -> httpx.Response:
    return await client.post(
        f"/api/v1/workspaces/{workspace}/members", headers=bearer(tokens), json=body
    )


@pytest.fixture
async def ada(client: httpx.AsyncClient) -> dict[str, Any]:
    return await sign_in(client, ADA)


@pytest.fixture
async def grace(client: httpx.AsyncClient) -> dict[str, Any]:
    return await sign_in(client, GRACE)


# --------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------


async def test_a_new_workspace_has_one_member(client: httpx.AsyncClient, ada) -> None:
    workspace = await own_workspace(client, ada)

    resp = await client.get(f"/api/v1/workspaces/{workspace}/members", headers=bearer(ada))

    assert resp.status_code == 200
    assert [m["role"] for m in resp.json()["items"]] == ["owner"]
    assert resp.json()["items"][0]["user"]["displayName"] == "ada"
    assert resp.json()["nextCursor"] is None


async def test_the_members_list_never_carries_an_email(client: httpx.AsyncClient, ada) -> None:
    """Members render as avatars and names; the address is not part of that."""
    workspace = await own_workspace(client, ada)

    resp = await client.get(f"/api/v1/workspaces/{workspace}/members", headers=bearer(ada))

    assert "email" not in resp.json()["items"][0]["user"]


async def test_listing_another_workspaces_members_is_refused(
    client: httpx.AsyncClient, ada, grace
) -> None:
    """The path workspace must be the token's workspace (Conventions §5.4)."""
    graces_own = await own_workspace(client, grace)

    resp = await client.get(f"/api/v1/workspaces/{graces_own}/members", headers=bearer(ada))

    assert resp.status_code == 403


async def test_members_are_paginated(client: httpx.AsyncClient, ada, grace) -> None:
    workspace = await own_workspace(client, ada)
    await sign_in(client, ALAN)
    await add(client, ada, workspace, email=GRACE, role="member")
    await add(client, ada, workspace, email=ALAN, role="member")

    first = await client.get(
        f"/api/v1/workspaces/{workspace}/members", headers=bearer(ada), params={"limit": 2}
    )
    assert len(first.json()["items"]) == 2
    assert first.json()["nextCursor"]

    second = await client.get(
        f"/api/v1/workspaces/{workspace}/members",
        headers=bearer(ada),
        params={"limit": 2, "cursor": first.json()["nextCursor"]},
    )

    assert len(second.json()["items"]) == 1
    assert second.json()["nextCursor"] is None
    seen = [m["user"]["id"] for m in first.json()["items"] + second.json()["items"]]
    assert len(set(seen)) == 3


async def test_a_malformed_cursor_is_a_400(client: httpx.AsyncClient, ada) -> None:
    workspace = await own_workspace(client, ada)

    resp = await client.get(
        f"/api/v1/workspaces/{workspace}/members",
        headers=bearer(ada),
        params={"cursor": "not-a-cursor!!"},
    )

    assert resp.status_code == 400


async def test_an_oversized_limit_is_refused(client: httpx.AsyncClient, ada) -> None:
    workspace = await own_workspace(client, ada)

    resp = await client.get(
        f"/api/v1/workspaces/{workspace}/members", headers=bearer(ada), params={"limit": 500}
    )

    assert resp.status_code == 400


# --------------------------------------------------------------------------
# Adding
# --------------------------------------------------------------------------


async def test_an_owner_can_add_a_member_by_email(client: httpx.AsyncClient, ada, grace) -> None:
    workspace = await own_workspace(client, ada)

    resp = await add(client, ada, workspace, email=GRACE, role="member")

    assert resp.status_code == 201
    assert resp.json()["role"] == "member"
    assert resp.json()["user"]["displayName"] == "grace"

    listed = await client.get(f"/api/v1/workspaces/{workspace}/members", headers=bearer(ada))
    assert len(listed.json()["items"]) == 2


async def test_an_owner_can_add_a_member_by_id(client: httpx.AsyncClient, ada, grace) -> None:
    workspace = await own_workspace(client, ada)
    graces_id = (await client.get("/api/v1/users/me", headers=bearer(grace))).json()["id"]

    resp = await add(client, ada, workspace, userId=graces_id, role="admin")

    assert resp.status_code == 201
    assert resp.json()["role"] == "admin"


async def test_adding_someone_twice_is_a_conflict(client: httpx.AsyncClient, ada, grace) -> None:
    workspace = await own_workspace(client, ada)
    await add(client, ada, workspace, email=GRACE, role="member")

    resp = await add(client, ada, workspace, email=GRACE, role="member")

    assert resp.status_code == 409


async def test_adding_an_unknown_address_is_a_404(client: httpx.AsyncClient, ada) -> None:
    """There is no invitations table, so an unknown address is not a pending invite."""
    workspace = await own_workspace(client, ada)

    resp = await add(client, ada, workspace, email="nobody@collabhub.dev", role="member")

    assert resp.status_code == 404


async def test_adding_with_an_unknown_role_is_refused(
    client: httpx.AsyncClient, ada, grace
) -> None:
    workspace = await own_workspace(client, ada)

    resp = await add(client, ada, workspace, email=GRACE, role="superuser")

    assert resp.status_code == 400
    assert "role" in resp.json()["errors"]


async def test_naming_both_an_id_and_an_email_is_refused(
    client: httpx.AsyncClient, ada, grace
) -> None:
    workspace = await own_workspace(client, ada)

    resp = await add(client, ada, workspace, email=GRACE, userId=str(uuid.uuid4()), role="member")

    assert resp.status_code == 400


async def test_naming_neither_an_id_nor_an_email_is_refused(client: httpx.AsyncClient, ada) -> None:
    workspace = await own_workspace(client, ada)

    resp = await add(client, ada, workspace, role="member")

    assert resp.status_code == 400


async def test_a_plain_member_cannot_add_anyone(client: httpx.AsyncClient, ada, grace) -> None:
    """Being in a workspace is not being able to administer it."""
    workspace = await own_workspace(client, ada)
    await add(client, ada, workspace, email=GRACE, role="member")
    await sign_in(client, ALAN)
    graces_token = await switch_to(client, grace, workspace)

    resp = await add(client, graces_token, workspace, email=ALAN, role="member")

    assert resp.status_code == 403


async def test_adding_to_a_workspace_the_token_does_not_name_is_refused(
    client: httpx.AsyncClient, ada, grace
) -> None:
    graces_own = await own_workspace(client, grace)

    resp = await add(client, ada, graces_own, email=ADA, role="owner")

    assert resp.status_code == 403


# --------------------------------------------------------------------------
# Changing a role
# --------------------------------------------------------------------------


async def test_an_owner_can_change_a_role(client: httpx.AsyncClient, ada, grace) -> None:
    workspace = await own_workspace(client, ada)
    added = await add(client, ada, workspace, email=GRACE, role="member")
    graces_id = added.json()["user"]["id"]

    resp = await client.patch(
        f"/api/v1/workspaces/{workspace}/members/{graces_id}",
        headers=bearer(ada),
        json={"role": "admin"},
    )

    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


async def test_the_last_owner_cannot_be_demoted(client: httpx.AsyncClient, ada) -> None:
    """A workspace with no owner has nobody who can grant the role back."""
    workspace = await own_workspace(client, ada)
    adas_id = (await client.get("/api/v1/users/me", headers=bearer(ada))).json()["id"]

    resp = await client.patch(
        f"/api/v1/workspaces/{workspace}/members/{adas_id}",
        headers=bearer(ada),
        json={"role": "member"},
    )

    assert resp.status_code == 409


async def test_an_owner_can_be_demoted_once_there_is_another(
    client: httpx.AsyncClient, ada, grace
) -> None:
    workspace = await own_workspace(client, ada)
    adas_id = (await client.get("/api/v1/users/me", headers=bearer(ada))).json()["id"]
    await add(client, ada, workspace, email=GRACE, role="owner")

    resp = await client.patch(
        f"/api/v1/workspaces/{workspace}/members/{adas_id}",
        headers=bearer(ada),
        json={"role": "member"},
    )

    assert resp.status_code == 200


async def test_changing_the_role_of_a_non_member_is_a_404(
    client: httpx.AsyncClient, ada, grace
) -> None:
    workspace = await own_workspace(client, ada)
    graces_id = (await client.get("/api/v1/users/me", headers=bearer(grace))).json()["id"]

    resp = await client.patch(
        f"/api/v1/workspaces/{workspace}/members/{graces_id}",
        headers=bearer(ada),
        json={"role": "admin"},
    )

    assert resp.status_code == 404


# --------------------------------------------------------------------------
# Removing
# --------------------------------------------------------------------------


async def test_an_owner_can_remove_a_member(client: httpx.AsyncClient, ada, grace) -> None:
    workspace = await own_workspace(client, ada)
    graces_id = (await add(client, ada, workspace, email=GRACE, role="member")).json()["user"]["id"]

    resp = await client.delete(
        f"/api/v1/workspaces/{workspace}/members/{graces_id}", headers=bearer(ada)
    )

    assert resp.status_code == 204
    listed = await client.get(f"/api/v1/workspaces/{workspace}/members", headers=bearer(ada))
    assert [m["user"]["id"] for m in listed.json()["items"]] != [graces_id]
    assert len(listed.json()["items"]) == 1


async def test_removal_revokes_the_refresh_token_for_that_workspace(
    client: httpx.AsyncClient, ada, grace
) -> None:
    """The test this endpoint exists for.

    Without revocation, removal only stops Grace obtaining a *new* session — the
    refresh token she is already holding would keep minting access tokens for a
    workspace she is no longer in, for up to thirty days.
    """
    workspace = await own_workspace(client, ada)
    graces_id = (await add(client, ada, workspace, email=GRACE, role="member")).json()["user"]["id"]
    graces_session = await switch_to(client, grace, workspace)

    await client.delete(f"/api/v1/workspaces/{workspace}/members/{graces_id}", headers=bearer(ada))

    resp = await client.post("/api/v1/auth/refresh", headers=session_cookie(graces_session))
    assert resp.status_code == 401


async def test_removal_leaves_sessions_for_other_workspaces_alone(
    client: httpx.AsyncClient, ada, grace
) -> None:
    """Membership of one workspace says nothing about the others."""
    workspace = await own_workspace(client, ada)
    graces_id = (await add(client, ada, workspace, email=GRACE, role="member")).json()["user"]["id"]

    await client.delete(f"/api/v1/workspaces/{workspace}/members/{graces_id}", headers=bearer(ada))

    resp = await client.post("/api/v1/auth/refresh", headers=session_cookie(grace))
    assert resp.status_code == 200


async def test_the_last_owner_cannot_be_removed(client: httpx.AsyncClient, ada) -> None:
    workspace = await own_workspace(client, ada)
    adas_id = (await client.get("/api/v1/users/me", headers=bearer(ada))).json()["id"]

    resp = await client.delete(
        f"/api/v1/workspaces/{workspace}/members/{adas_id}", headers=bearer(ada)
    )

    assert resp.status_code == 409


async def test_removing_a_non_member_is_a_404(client: httpx.AsyncClient, ada) -> None:
    workspace = await own_workspace(client, ada)

    resp = await client.delete(
        f"/api/v1/workspaces/{workspace}/members/{uuid.uuid4()}", headers=bearer(ada)
    )

    assert resp.status_code == 404


async def test_a_plain_member_cannot_remove_anyone(client: httpx.AsyncClient, ada, grace) -> None:
    demo = await workspace_named(client, ada, DEMO_WORKSPACE)
    adas_id = (await client.get("/api/v1/users/me", headers=bearer(ada))).json()["id"]
    graces_token = await switch_to(client, grace, demo)

    resp = await client.delete(
        f"/api/v1/workspaces/{demo}/members/{adas_id}", headers=bearer(graces_token)
    )

    assert resp.status_code == 403
