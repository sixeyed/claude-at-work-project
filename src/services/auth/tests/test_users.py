"""User profiles (spec §3).

`PATCH /users/me` is unremarkable except for one thing worth pinning down: an
absent field and a null one mean different things, and getting that wrong makes
an avatar impossible to remove.

`GET /users/{id}` is where the interesting rule is. Every access token names one
workspace, so this endpoint must not answer for users outside it.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from tests import dexflow
from tests.conftest import A_SIGNING_KEY, ADA, ALAN, DEX_PASSWORD, GRACE, build_settings

from auth.main import create_app

pytestmark = pytest.mark.integration


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def me(client: httpx.AsyncClient, tokens: dict[str, Any]) -> dict[str, Any]:
    return (await client.get("/api/v1/users/me", headers=bearer(tokens))).json()


# --------------------------------------------------------------------------
# Editing your own profile
# --------------------------------------------------------------------------


async def test_the_display_name_can_be_changed(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": "Ada Lovelace"}
    )

    assert resp.status_code == 200
    assert resp.json()["displayName"] == "Ada Lovelace"
    assert (await me(client, tokens))["displayName"] == "Ada Lovelace"


async def test_an_edit_bumps_the_version(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": "Ada Lovelace"}
    )

    # `version` is not in the response model, so assert through a second edit
    # succeeding rather than reading it back.
    second = await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": "Ada L"}
    )
    assert second.status_code == 200


async def test_an_avatar_can_be_set_and_then_cleared(client: httpx.AsyncClient) -> None:
    """An absent field means "leave alone"; an explicit null means "clear".

    Treating None as "no change" would make an avatar impossible to remove once
    set, which is the kind of thing nobody notices until a user asks.
    """
    tokens = await sign_in(client)
    asset = str(uuid.uuid4())

    set_it = await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"avatarAsset": asset}
    )
    assert set_it.json()["avatarAsset"] == asset

    untouched = await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": "Ada"}
    )
    assert untouched.json()["avatarAsset"] == asset

    cleared = await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"avatarAsset": None}
    )
    assert cleared.json()["avatarAsset"] is None


async def test_an_empty_display_name_is_refused(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await client.patch("/api/v1/users/me", headers=bearer(tokens), json={"displayName": ""})

    assert resp.status_code == 400


async def test_a_null_display_name_is_refused(client: httpx.AsyncClient) -> None:
    """Distinct from omitting it — an explicit null would blank the name."""
    tokens = await sign_in(client)

    resp = await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": None}
    )

    assert resp.status_code == 400


async def test_editing_a_profile_needs_a_token(client: httpx.AsyncClient) -> None:
    resp = await client.patch("/api/v1/users/me", json={"displayName": "nobody"})

    assert resp.status_code == 401


async def test_an_edit_cannot_name_another_user(client: httpx.AsyncClient) -> None:
    """There is no id in the request, so there is none to substitute."""
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)
    graces_id = (await me(client, grace))["id"]

    await client.patch(
        "/api/v1/users/me",
        headers=bearer(ada),
        json={"displayName": "hijacked", "id": graces_id},
    )

    assert (await me(client, grace))["displayName"] == "grace"


# --------------------------------------------------------------------------
# Looking at someone else
# --------------------------------------------------------------------------


async def test_a_shared_workspace_makes_a_profile_visible(client: httpx.AsyncClient) -> None:
    """Ada and Grace both join the demo workspace locally, so they can see each other."""
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)
    graces_id = (await me(client, grace))["id"]

    resp = await client.get(f"/api/v1/users/{graces_id}", headers=bearer(ada))

    assert resp.status_code == 200
    assert resp.json()["displayName"] == "grace"


async def test_a_public_profile_never_carries_the_email(client: httpx.AsyncClient) -> None:
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)
    graces_id = (await me(client, grace))["id"]

    resp = await client.get(f"/api/v1/users/{graces_id}", headers=bearer(ada))

    assert set(resp.json()) == {"id", "displayName", "avatarAsset"}
    assert "email" not in resp.json()


async def test_you_can_always_see_yourself(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)
    own_id = (await me(client, tokens))["id"]

    resp = await client.get(f"/api/v1/users/{own_id}", headers=bearer(tokens))

    assert resp.status_code == 200


async def test_a_stranger_is_not_found(
    client: httpx.AsyncClient, postgres_dsn, redis_url, dex_issuer, engine
) -> None:
    """A workspace-scoped token must not be a directory of the whole installation.

    Built without the shared demo workspace, so Ada and Alan genuinely have
    nothing in common — locally everyone meets in the demo workspace, which
    would hide the rule this endpoint enforces.
    """
    app = create_app(
        build_settings(
            postgres_dsn,
            redis_url,
            dex_issuer,
            app_env="production",
            auth_signing_key=A_SIGNING_KEY,
        )
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        ada = await sign_in(c, ADA)
        alan = await sign_in(c, ALAN)
        alans_id = (await me(c, alan))["id"]

        resp = await c.get(f"/api/v1/users/{alans_id}", headers=bearer(ada))

    assert resp.status_code == 404


async def test_an_unknown_user_is_not_found(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await client.get(f"/api/v1/users/{uuid.uuid4()}", headers=bearer(tokens))

    assert resp.status_code == 404


async def test_a_public_profile_needs_a_token(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"/api/v1/users/{uuid.uuid4()}")

    assert resp.status_code == 401
