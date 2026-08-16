"""The refresh-token cookie (register D22).

Every assertion here is about an attribute rather than a behaviour, which is
unusual and deliberate: on this cookie the attributes *are* the security control.
`HttpOnly` is what puts the token beyond reach of injected script, and
`SameSite=Strict` is what closes CSRF now that the browser attaches a credential
by itself. Dropping either would leave a working sign-in and a broken design, so
neither is something to find out about from a pen test.
"""

from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Any

import httpx
import pytest
from tests.conftest import ADA, DEMO_WORKSPACE, DEX_PASSWORD
from tests.dexflow import session_cookie

from auth.cookies import COOKIE_NAME, COOKIE_PATH
from tests import dexflow

pytestmark = pytest.mark.integration


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def attributes(response: httpx.Response) -> dict[str, str]:
    """The parsed `Set-Cookie` for the refresh cookie.

    Parsed from the raw header rather than read off httpx's jar, because the jar
    keeps the value and discards most of what is being asserted here.
    """
    for header in response.headers.get_list("set-cookie"):
        jar = SimpleCookie()
        jar.load(header)
        if COOKIE_NAME in jar:
            morsel = jar[COOKIE_NAME]
            return {
                "value": morsel.value,
                "httponly": morsel["httponly"],
                "secure": morsel["secure"],
                "samesite": morsel["samesite"],
                "path": morsel["path"],
                "max-age": morsel["max-age"],
            }
    raise AssertionError(f"no {COOKIE_NAME} cookie on {response.request.url}")


async def token_response(client: httpx.AsyncClient) -> httpx.Response:
    """The raw `/auth/token` response, before the helper tidies the jar away."""
    attempt = await dexflow.begin(client, email=ADA, password=DEX_PASSWORD)
    return await client.post(
        "/api/v1/auth/token",
        json={
            "grantType": "authorization_code",
            "code": attempt["code"],
            "codeVerifier": attempt["verifier"],
        },
    )


# --------------------------------------------------------------------------
# The attributes
# --------------------------------------------------------------------------


async def test_the_refresh_token_is_never_in_the_response_body(
    client: httpx.AsyncClient,
) -> None:
    """The whole of D22 in one assertion.

    A refresh token in the body is a refresh token in the JavaScript heap, which
    is exactly where injected script could reach it. If this ever passes again,
    the cookie has become decoration.
    """
    response = await token_response(client)

    assert response.status_code == 200
    assert "refreshToken" not in response.json()
    assert set(response.json()) == {"accessToken", "tokenType", "expiresIn"}


async def test_the_cookie_is_http_only(client: httpx.AsyncClient) -> None:
    assert attributes(await token_response(client))["httponly"] is True


async def test_the_cookie_is_same_site_strict(client: httpx.AsyncClient) -> None:
    """What closes CSRF. Without it, any site could trigger a renewal."""
    assert attributes(await token_response(client))["samesite"].lower() == "strict"


async def test_the_cookie_is_secure(client: httpx.AsyncClient) -> None:
    assert attributes(await token_response(client))["secure"] is True


async def test_the_cookie_is_scoped_to_the_auth_endpoints(client: httpx.AsyncClient) -> None:
    """Messaging, Canvas and Asset must never receive the refresh token.

    They have no use for it, and a path-scoped cookie cannot be logged by a
    service that never sees it.
    """
    assert attributes(await token_response(client))["path"] == COOKIE_PATH


async def test_the_cookie_expires_with_the_token(client: httpx.AsyncClient) -> None:
    """A browser that stops sending it matches a database that would refuse it."""
    assert int(attributes(await token_response(client))["max-age"]) == 30 * 86400


# --------------------------------------------------------------------------
# Rotation and revocation through the cookie
# --------------------------------------------------------------------------


async def test_refreshing_rotates_the_cookie(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    renewed = await client.post("/api/v1/auth/refresh", headers=session_cookie(tokens))

    assert attributes(renewed)["value"] != tokens["refreshCookie"]


async def test_switching_workspace_rotates_the_cookie(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)
    listed = await client.get(
        "/api/v1/workspaces", headers={"Authorization": f"Bearer {tokens['accessToken']}"}
    )
    demo = next(w["id"] for w in listed.json()["items"] if w["name"] == DEMO_WORKSPACE)

    switched = await client.post(
        "/api/v1/auth/switch-workspace",
        json={"workspaceId": demo},
        headers=session_cookie(tokens),
    )

    assert attributes(switched)["value"] != tokens["refreshCookie"]


async def test_refreshing_without_a_cookie_is_a_401(client: httpx.AsyncClient) -> None:
    """No body to fall back on: the cookie is the only way to name a session."""
    resp = await client.post("/api/v1/auth/refresh")

    assert resp.status_code == 401


async def test_a_refresh_token_cannot_be_supplied_in_the_body(
    client: httpx.AsyncClient,
) -> None:
    """A stolen token is worthless without a browser willing to send it.

    The endpoint reads the cookie and nothing else, so an attacker holding the
    value cannot present it from a context the browser would not have chosen.
    """
    tokens = await sign_in(client)

    resp = await client.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshCookie"]})

    assert resp.status_code == 401


async def test_signing_out_clears_the_cookie(client: httpx.AsyncClient) -> None:
    """A browser left holding a spent cookie looks signed in until it fails."""
    tokens = await sign_in(client)

    resp = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Authorization": f"Bearer {tokens['accessToken']}",
            **session_cookie(tokens),
        },
    )

    assert resp.status_code == 204
    cleared = attributes(resp)
    assert cleared["value"] == ""
    # Same path, or the browser treats it as a different cookie and keeps the original.
    assert cleared["path"] == COOKIE_PATH


async def test_signing_out_revokes_the_session_the_cookie_named(
    client: httpx.AsyncClient,
) -> None:
    tokens = await sign_in(client)

    await client.post(
        "/api/v1/auth/logout",
        headers={
            "Authorization": f"Bearer {tokens['accessToken']}",
            **session_cookie(tokens),
        },
    )

    resp = await client.post("/api/v1/auth/refresh", headers=session_cookie(tokens))
    assert resp.status_code == 401
