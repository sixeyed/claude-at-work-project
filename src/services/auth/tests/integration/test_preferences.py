"""Per-user preferences (gh-5, issue Req 6; register D28).

`GET` and `PATCH /api/v1/users/me/preferences`. One row per user, global rather than
per workspace; reading never creates it; a `PATCH` merges the keys it carries and
`null` removes one. The merge is a single SQL statement, so two tabs setting
different keys do not lose each other's change.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from testkit import dexflow
from testkit.auth import DEMO_WORKSPACE
from testkit.dex import ADA, DEX_PASSWORD, GRACE
from testkit.dexflow import session_cookie

PATH = "/api/v1/users/me/preferences"
GONE = "This account no longer exists."


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def get(client: httpx.AsyncClient, tokens: dict[str, Any]) -> httpx.Response:
    return await client.get(PATH, headers=bearer(tokens))


async def patch(client: httpx.AsyncClient, tokens: dict[str, Any], body: Any) -> httpx.Response:
    return await client.patch(PATH, headers=bearer(tokens), json=body)


async def user_id(sessions, email: str) -> str:
    async with sessions() as session:
        found = await session.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": email}
        )
        return str(found.scalar_one())


async def row_count(sessions) -> int:
    async with sessions() as session:
        return (await session.execute(text("SELECT count(*) FROM user_preferences"))).scalar_one()


async def stored(sessions, uid: str) -> tuple[dict[str, Any], int]:
    async with sessions() as session:
        result = await session.execute(
            text("SELECT prefs, version FROM user_preferences WHERE user_id = CAST(:u AS uuid)"),
            {"u": uid},
        )
        prefs, version = result.one()
    return (json.loads(prefs) if isinstance(prefs, str) else prefs), version


async def delete_account(sessions, email: str) -> None:
    async with sessions() as session:
        await session.execute(
            text("UPDATE users SET deleted_at = now() WHERE email = :email"), {"email": email}
        )
        await session.commit()


async def test_no_preferences_read_as_an_empty_object_and_make_no_row(
    client: httpx.AsyncClient, sessions
) -> None:
    tokens = await sign_in(client)

    resp = await get(client, tokens)

    assert resp.status_code == 200
    assert resp.json() == {}
    assert await row_count(sessions) == 0


async def test_a_patch_is_read_back(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await patch(client, tokens, {"clock": "24h"})

    assert resp.status_code == 200
    assert resp.json() == {"clock": "24h"}
    assert (await get(client, tokens)).json() == {"clock": "24h"}


async def test_null_removes_a_key(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)
    assert (await patch(client, tokens, {"clock": "12h"})).json() == {"clock": "12h"}

    removed = await patch(client, tokens, {"clock": None})

    assert removed.status_code == 200
    assert removed.json() == {}
    assert (await get(client, tokens)).json() == {}


async def test_a_patch_merges_rather_than_replaces(client: httpx.AsyncClient, sessions) -> None:
    """A key the API doesn't know survives a write, and is left out of the answer."""
    tokens = await sign_in(client)
    uid = await user_id(sessions, ADA)
    async with sessions.begin() as session:
        await session.execute(
            text(
                "INSERT INTO user_preferences (user_id, prefs, version, updated_at) "
                "VALUES (CAST(:u AS uuid), CAST(:p AS jsonb), 0, now())"
            ),
            {"u": uid, "p": json.dumps({"clock": "12h", "legacy": 1})},
        )

    resp = await patch(client, tokens, {"clock": "24h"})

    assert resp.status_code == 200
    assert resp.json() == {"clock": "24h"}
    assert await stored(sessions, uid) == ({"clock": "24h", "legacy": 1}, 1)
    assert (await get(client, tokens)).json() == {"clock": "24h"}


async def test_an_unknown_key_is_400_on_that_key_and_nothing_changes(
    client: httpx.AsyncClient,
) -> None:
    tokens = await sign_in(client)
    assert (await patch(client, tokens, {"clock": "12h"})).status_code == 200

    resp = await patch(client, tokens, {"theme": "dark", "clock": "24h"})

    assert resp.status_code == 400
    assert "theme" in resp.json()["errors"]
    assert (await get(client, tokens)).json() == {"clock": "12h"}


@pytest.mark.parametrize("value", ["25h", 12], ids=["string", "number"])
async def test_a_bad_value_is_400_on_the_key(client: httpx.AsyncClient, value: Any) -> None:
    tokens = await sign_in(client)
    assert (await patch(client, tokens, {"clock": "12h"})).status_code == 200

    resp = await patch(client, tokens, {"clock": value})

    assert resp.status_code == 400
    assert set(resp.json()["errors"]) == {"clock"}
    assert (await get(client, tokens)).json() == {"clock": "12h"}


async def test_an_empty_patch_writes_nothing(client: httpx.AsyncClient, sessions) -> None:
    tokens = await sign_in(client)

    resp = await patch(client, tokens, {})

    assert resp.status_code == 200
    assert resp.json() == {}
    assert await row_count(sessions) == 0


async def test_two_first_patches_at_once_both_land(client: httpx.AsyncClient, sessions) -> None:
    """The first write is an upsert: two tabs racing it must not turn one into a 500."""
    tokens = await sign_in(client)

    first, second = await asyncio.gather(
        patch(client, tokens, {"clock": "12h"}), patch(client, tokens, {"clock": "24h"})
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert await row_count(sessions) == 1
    assert (await get(client, tokens)).json() in ({"clock": "12h"}, {"clock": "24h"})


async def test_preferences_belong_to_the_user_not_the_workspace(
    client: httpx.AsyncClient,
) -> None:
    ada, grace = await sign_in(client, ADA), await sign_in(client, GRACE)
    assert (await patch(client, ada, {"clock": "24h"})).status_code == 200
    listed = await client.get("/api/v1/workspaces", headers=bearer(ada))
    demo = next(w["id"] for w in listed.json()["items"] if w["name"] == DEMO_WORKSPACE)

    switched = await client.post(
        "/api/v1/auth/switch-workspace", json={"workspaceId": demo}, headers=session_cookie(ada)
    )
    assert switched.status_code == 200, switched.text

    assert (await get(client, switched.json())).json() == {"clock": "24h"}
    assert (await get(client, grace)).json() == {}


async def test_a_deleted_account_gets_404_with_its_detail(
    client: httpx.AsyncClient, sessions
) -> None:
    tokens = await sign_in(client)
    assert (await get(client, tokens)).status_code == 200
    await delete_account(sessions, ADA)

    read = await get(client, tokens)
    written = await patch(client, tokens, {"clock": "24h"})

    assert read.status_code == 404
    assert read.json()["detail"] == GONE
    assert written.status_code == 404
    assert written.json()["detail"] == GONE


async def test_preferences_need_a_token(client: httpx.AsyncClient) -> None:
    assert (await client.get(PATH)).status_code == 401
    assert (await client.patch(PATH, json={"clock": "24h"})).status_code == 401
