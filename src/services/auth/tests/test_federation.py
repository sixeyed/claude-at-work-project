"""Federated sign-in through a real Dex (spec §5.1, register D5).

These are the tests that matter most in this service: everything else assumes an
identity, and this is where one comes from. They drive the genuine
authorization-code flow — Dex's login form and all — so a change that breaks
real sign-in cannot pass here.

The negative tests carry the weight. A login flow that works is easy; one that
also refuses a replayed state, a spent code, a stolen code without its verifier,
and an id_token minted for someone else is the point.
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from sqlalchemy import select
from tests.conftest import (
    ADA,
    AUTH_ISSUER,
    DEMO_WORKSPACE,
    DEX_CLIENT_ID,
    DEX_PASSWORD,
    GRACE,
    SPA_REDIRECT,
)

from auth import pkce
from auth.models import ExternalIdentity
from tests import dexflow

pytestmark = pytest.mark.integration


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def claims(tokens: dict[str, Any]) -> dict[str, Any]:
    return jwt.decode(tokens["accessToken"], options={"verify_signature": False})


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


async def test_a_dex_sign_in_issues_a_collabhub_token_pair(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    assert tokens["tokenType"] == "Bearer"
    assert tokens["expiresIn"] == 900
    assert tokens["accessToken"]
    assert tokens["refreshCookie"]


async def test_the_token_carries_the_identity_dex_asserted(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    body = claims(tokens)

    assert body["email"] == ADA
    assert body["name"] == "ada"
    assert uuid.UUID(body["sub"])
    assert uuid.UUID(body["wsp"])
    assert body["roles"] == ["owner"]


async def test_the_token_is_issued_by_collabhub_not_dex(client: httpx.AsyncClient) -> None:
    """Dex authenticates; CollabHub issues. The `iss` is ours (register D5)."""
    tokens = await sign_in(client)

    assert claims(tokens)["iss"] == AUTH_ISSUER
    assert claims(tokens)["aud"] == "collabhub"


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def test_signing_in_records_the_external_identity(
    client: httpx.AsyncClient, sessions
) -> None:
    """`external_identities` is what makes the second sign-in the same account.

    Asserted against the table rather than through behaviour, because the row is
    the thing register D5 was waiting on: it was created empty by the MVP and
    stayed empty until federation landed.
    """
    tokens = await sign_in(client)

    async with sessions() as session:
        rows = (await session.execute(select(ExternalIdentity))).scalars().all()

    assert len(rows) == 1
    assert rows[0].provider == "oidc:dex"
    assert rows[0].subject  # Dex's opaque subject, not the email
    assert rows[0].subject != ADA
    assert str(rows[0].user_id) == claims(tokens)["sub"]


async def test_signing_in_twice_links_no_second_identity(
    client: httpx.AsyncClient, sessions
) -> None:
    await sign_in(client)
    await sign_in(client)

    async with sessions() as session:
        rows = (await session.execute(select(ExternalIdentity))).scalars().all()

    assert len(rows) == 1


async def test_signing_in_twice_is_the_same_account(client: httpx.AsyncClient) -> None:
    first = claims(await sign_in(client))
    second = claims(await sign_in(client))

    assert first["sub"] == second["sub"]
    assert first["wsp"] == second["wsp"]


async def test_a_new_user_gets_their_own_workspace_and_the_demo_one(
    client: httpx.AsyncClient,
) -> None:
    tokens = await sign_in(client)

    resp = await client.get(
        "/api/v1/workspaces", headers={"Authorization": f"Bearer {tokens['accessToken']}"}
    )

    workspaces = resp.json()["items"]
    assert {w["role"] for w in workspaces} == {"owner", "member"}
    assert DEMO_WORKSPACE in {w["name"] for w in workspaces}


async def test_two_dex_users_are_two_accounts(client: httpx.AsyncClient) -> None:
    ada = claims(await sign_in(client, ADA))
    grace = claims(await sign_in(client, GRACE))

    assert ada["sub"] != grace["sub"]
    assert ada["email"] == ADA
    assert grace["email"] == GRACE


# --------------------------------------------------------------------------
# Beginning a login
# --------------------------------------------------------------------------


async def test_login_redirects_to_dex_with_pkce_and_state(client: httpx.AsyncClient) -> None:
    challenge = pkce.challenge_for(pkce.new_verifier())

    resp = await client.get("/api/v1/auth/login/dex", params={"codeChallenge": challenge})

    assert resp.status_code == 302
    query = parse_qs(urlparse(resp.headers["location"]).query)
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["client_id"] == [DEX_CLIENT_ID]
    assert query["state"] and query["nonce"] and query["code_challenge"]


async def test_our_own_pkce_challenge_is_not_the_spas(client: httpx.AsyncClient) -> None:
    """The two PKCE exchanges are independent — sharing them would leak the SPA's.

    If the challenge sent to Dex were the SPA's, then Dex (or anything that saw
    the authorization request) would hold the challenge protecting the
    CollabHub code as well.
    """
    challenge = pkce.challenge_for(pkce.new_verifier())

    resp = await client.get("/api/v1/auth/login/dex", params={"codeChallenge": challenge})

    sent_to_dex = parse_qs(urlparse(resp.headers["location"]).query)["code_challenge"][0]
    assert sent_to_dex != challenge


async def test_login_requires_a_code_challenge(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/login/dex")

    assert resp.status_code == 400


async def test_login_refuses_plain_pkce(client: httpx.AsyncClient) -> None:
    """`plain` proves nothing; accepting it would be a way to turn PKCE off."""
    challenge = pkce.challenge_for(pkce.new_verifier())

    resp = await client.get(
        "/api/v1/auth/login/dex",
        params={"codeChallenge": challenge, "codeChallengeMethod": "plain"},
    )

    assert resp.status_code == 400
    assert "codeChallengeMethod" in resp.json()["errors"]


async def test_an_unknown_provider_is_a_404(client: httpx.AsyncClient) -> None:
    challenge = pkce.challenge_for(pkce.new_verifier())

    resp = await client.get("/api/v1/auth/login/okta", params={"codeChallenge": challenge})

    assert resp.status_code == 404


# --------------------------------------------------------------------------
# The callback — everything here redirects rather than raises
# --------------------------------------------------------------------------


async def test_a_replayed_state_is_refused(client: httpx.AsyncClient) -> None:
    """`state` is single-use: the second callback with it finds nothing in R1."""
    attempt = await dexflow.begin(client, email=ADA, password=DEX_PASSWORD)

    replay = await client.get("/api/v1/auth/callback/dex", params=attempt["callback"])

    assert replay.status_code == 302
    assert parse_qs(urlparse(replay.headers["location"]).query)["error"] == ["invalid_state"]


async def test_an_unknown_state_is_refused(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/auth/callback/dex", params={"code": "anything", "state": "never-issued"}
    )

    assert resp.status_code == 302
    assert parse_qs(urlparse(resp.headers["location"]).query)["error"] == ["invalid_state"]


async def test_a_provider_error_is_passed_to_the_spa(client: httpx.AsyncClient) -> None:
    """A denied consent must reach the SPA, not a Problem Details page."""
    resp = await client.get("/api/v1/auth/callback/dex", params={"error": "access_denied"})

    assert resp.status_code == 302
    location = urlparse(resp.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == SPA_REDIRECT
    assert parse_qs(location.query)["error"] == ["access_denied"]


async def test_a_callback_without_a_code_is_refused(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/callback/dex", params={"state": "x"})

    assert resp.status_code == 302
    assert parse_qs(urlparse(resp.headers["location"]).query)["error"] == ["invalid_request"]


async def test_a_successful_callback_lands_on_the_configured_spa_uri(
    client: httpx.AsyncClient,
) -> None:
    """The redirect target is configuration, never taken from the request.

    There is no `redirect_uri` parameter on any endpoint here, so there is no
    open redirect to validate against an allow-list — the question never
    reaches the service.
    """
    challenge = pkce.challenge_for(pkce.new_verifier())
    started = await client.get("/api/v1/auth/login/dex", params={"codeChallenge": challenge})
    callback = await dexflow.authenticate(
        started.headers["location"], email=ADA, password=DEX_PASSWORD
    )

    resp = await client.get(
        "/api/v1/auth/callback/dex",
        params={key: values[0] for key, values in callback.items()},
    )

    location = urlparse(resp.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == SPA_REDIRECT
    assert parse_qs(location.query)["code"]


# --------------------------------------------------------------------------
# Spending the authorization code
# --------------------------------------------------------------------------


async def test_the_authorization_code_is_single_use(client: httpx.AsyncClient) -> None:
    attempt = await dexflow.begin(client, email=ADA, password=DEX_PASSWORD)
    await dexflow.finish(client, attempt)

    resp = await client.post(
        "/api/v1/auth/token",
        json={
            "grantType": "authorization_code",
            "code": attempt["code"],
            "codeVerifier": attempt["verifier"],
        },
    )

    assert resp.status_code == 401


async def test_a_code_without_its_verifier_is_worthless(client: httpx.AsyncClient) -> None:
    """The whole reason the code may travel in a redirect URL.

    Someone reading the code out of browser history, a referrer header or a
    proxy log has everything except the verifier, which never left the SPA.
    """
    attempt = await dexflow.begin(client, email=ADA, password=DEX_PASSWORD)

    resp = await client.post(
        "/api/v1/auth/token",
        json={
            "grantType": "authorization_code",
            "code": attempt["code"],
            "codeVerifier": pkce.new_verifier(),
        },
    )

    assert resp.status_code == 401


async def test_an_unknown_code_is_refused(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/token",
        json={
            "grantType": "authorization_code",
            "code": "never-issued",
            "codeVerifier": pkce.new_verifier(),
        },
    )

    assert resp.status_code == 401


async def test_an_unsupported_grant_type_is_refused(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/token",
        json={"grantType": "password", "code": "x", "codeVerifier": "y"},
    )

    assert resp.status_code == 400
    assert "grantType" in resp.json()["errors"]


async def test_a_snake_case_body_is_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/token",
        json={"grant_type": "authorization_code", "code": "x", "code_verifier": "y"},
    )

    assert resp.status_code == 400


# --------------------------------------------------------------------------
# dev-login is gone (register D5 settled)
# --------------------------------------------------------------------------


async def test_dev_login_no_longer_exists(client: httpx.AsyncClient) -> None:
    """It was deleted, not disabled — there is no flag to turn it back on."""
    resp = await client.post("/api/v1/auth/dev-login", json={"email": "anyone@example.com"})

    assert resp.status_code == 404
