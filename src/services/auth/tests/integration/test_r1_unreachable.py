"""Auth with R1 unreachable (Conventions §5.2, register D1).

Two apps over one database and one signing key. `reachable` is the service as
normal, and signs people in — sign-in itself needs R1, for the login state and
the authorization code. `r1_down` is the same service with its cache URL on a
port nothing listens on. A token issued by one verifies in the other, so each
test signs in first and then makes the request under test while R1 is gone.

`r1_down` does not re-raise app exceptions, so an unhandled error arrives as the
500 a client would see rather than as an exception in the test.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from auth.main import create_app
from testkit import dexflow
from testkit.apps import asgi_client
from testkit.auth import A_SIGNING_KEY, build_settings
from testkit.dex import ADA, ALAN, DEX_PASSWORD, GRACE
from testkit.dexflow import issued_cookie, session_cookie

# Port 1 on loopback: refused at once, so the tests do not wait on a timeout.
UNREACHABLE_REDIS = "redis://127.0.0.1:1/0"


@pytest.fixture
async def reachable(
    postgres_dsn: str, redis_url: str, dex_issuer: str, engine
) -> AsyncIterator[httpx.AsyncClient]:
    settings = build_settings(postgres_dsn, redis_url, dex_issuer, auth_signing_key=A_SIGNING_KEY)
    async with asgi_client(create_app(settings)) as c:
        yield c


@pytest.fixture
async def r1_down(postgres_dsn: str, dex_issuer: str, engine) -> AsyncIterator[httpx.AsyncClient]:
    settings = build_settings(
        postgres_dsn, UNREACHABLE_REDIS, dex_issuer, auth_signing_key=A_SIGNING_KEY
    )
    transport = httpx.ASGITransport(app=create_app(settings), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def sign_in(client: httpx.AsyncClient, email: str) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def own_workspace(client: httpx.AsyncClient, tokens: dict[str, Any]) -> str:
    resp = await client.get("/api/v1/workspaces", headers=bearer(tokens))
    return next(w["id"] for w in resp.json()["items"] if w["role"] == "owner")


async def add(
    client: httpx.AsyncClient, tokens: dict[str, Any], workspace: str, **body: Any
) -> httpx.Response:
    return await client.post(
        f"/api/v1/workspaces/{workspace}/members", headers=bearer(tokens), json=body
    )


# --------------------------------------------------------------------------
# Signing out is not in the fail-closed set
# --------------------------------------------------------------------------


async def test_signing_out_still_ends_the_session_when_r1_is_unreachable(
    reachable: httpx.AsyncClient, r1_down: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The denylist write cannot happen; the rest of logout still must.

    The refresh token is in Postgres and the cookie is in the response, and
    neither needs R1. A 500 here leaves the user with a session that renews for
    thirty days after they pressed "sign out".

    What is lost is the access token's early death — it stays usable until it
    expires — so that gap is logged as a warning, without the token in it.
    """
    tokens = await sign_in(reachable, ADA)
    caplog.set_level("WARNING")

    resp = await r1_down.post(
        "/api/v1/auth/logout", headers={**bearer(tokens), **session_cookie(tokens)}
    )

    assert resp.status_code == 204
    assert issued_cookie(resp) == ""
    renewal = await reachable.post("/api/v1/auth/refresh", headers=session_cookie(tokens))
    assert renewal.status_code == 401

    warnings = [
        r
        for r in caplog.records
        if r.levelname == "WARNING"
        and r.name.startswith("collabhub.auth")
        and "denylist" in r.getMessage()
    ]
    assert len(warnings) == 1
    assert tokens["accessToken"] not in caplog.text


async def test_profile_and_preference_edits_fail_open_when_r1_is_unreachable(
    reachable: httpx.AsyncClient, r1_down: httpx.AsyncClient
) -> None:
    """Neither PATCH is in Conventions §5.2's sensitive set: they accept the token.

    The 503 tests below are the other side — membership writes refuse when R1 is
    down, so a 200 here is the route's choice, not R1 being ignored everywhere.
    """
    tokens = await sign_in(reachable, ADA)

    renamed = await r1_down.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": "Ada L"}
    )
    chosen = await r1_down.patch(
        "/api/v1/users/me/preferences", headers=bearer(tokens), json={"clock": "24h"}
    )

    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["displayName"] == "Ada L"
    assert chosen.status_code == 200, chosen.text
    assert chosen.json() == {"clock": "24h"}


# --------------------------------------------------------------------------
# Member writes fail closed (Conventions §5.2, doc 01 §3)
# --------------------------------------------------------------------------


async def test_adding_a_member_is_a_503_when_r1_is_unreachable(
    reachable: httpx.AsyncClient, r1_down: httpx.AsyncClient
) -> None:
    ada = await sign_in(reachable, ADA)
    await sign_in(reachable, GRACE)
    workspace = await own_workspace(reachable, ada)

    resp = await add(r1_down, ada, workspace, email=GRACE, role="member")

    assert resp.status_code == 503


async def test_changing_a_role_is_a_503_when_r1_is_unreachable(
    reachable: httpx.AsyncClient, r1_down: httpx.AsyncClient
) -> None:
    ada = await sign_in(reachable, ADA)
    await sign_in(reachable, GRACE)
    workspace = await own_workspace(reachable, ada)
    graces_id = (await add(reachable, ada, workspace, email=GRACE, role="member")).json()["user"][
        "id"
    ]

    resp = await r1_down.patch(
        f"/api/v1/workspaces/{workspace}/members/{graces_id}",
        headers=bearer(ada),
        json={"role": "owner"},
    )

    assert resp.status_code == 503


async def test_removing_a_member_is_a_503_when_r1_is_unreachable(
    reachable: httpx.AsyncClient, r1_down: httpx.AsyncClient
) -> None:
    ada = await sign_in(reachable, ADA)
    await sign_in(reachable, ALAN)
    workspace = await own_workspace(reachable, ada)
    alans_id = (await add(reachable, ada, workspace, email=ALAN, role="member")).json()["user"][
        "id"
    ]

    resp = await r1_down.delete(
        f"/api/v1/workspaces/{workspace}/members/{alans_id}", headers=bearer(ada)
    )

    assert resp.status_code == 503
