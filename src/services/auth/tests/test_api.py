"""The Auth service end to end, against real Postgres and Redis (spec §3).

Every test here goes through HTTP, because the contract other services and the
SPA build against is the HTTP one — the claims in the token, the shape of the
envelope, and the status code when something is wrong.

The through-line is the session lifecycle: sign in, use the token, refresh it,
switch workspace, sign out. The tests that matter most are the ones about
tokens that should *stop* working — a rotated refresh token, a replayed one, a
token whose `jti` is on the denylist.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from auth.main import create_app
from auth.settings import Settings

pytestmark = pytest.mark.integration

DEMO_WORKSPACE = "CollabHub Demo"
WORKER_SECRET = "worker-local-secret"

# A configured key for the one test that starts the app as if deployed, where
# generating a key is (correctly) refused.
_A_KEY = (
    rsa.generate_private_key(public_exponent=65537, key_size=2048)
    .private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    .decode()
)


def build_settings(postgres_dsn: str, redis_url: str, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "local",
        "postgres_dsn": postgres_dsn,
        "redis_cache_url": redis_url,
        "auth_issuer": "http://localhost:8001",
        "auth_service_clients": [
            {"client_id": "worker", "secret": WORKER_SECRET, "scopes": ["assets:write-variants"]}
        ],
        "auth_demo_workspace_name": DEMO_WORKSPACE,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
async def client(postgres_dsn: str, redis_url: str, engine) -> httpx.AsyncClient:
    app = create_app(build_settings(postgres_dsn, redis_url))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def sign_in(client: httpx.AsyncClient, email: str = "ada@example.com") -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/auth/dev-login", json={"email": email, "displayName": "Ada Lovelace"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


def claims(tokens: dict[str, Any]) -> dict[str, Any]:
    return jwt.decode(tokens["accessToken"], options={"verify_signature": False})


# --------------------------------------------------------------------------
# Signing in
# --------------------------------------------------------------------------


async def test_dev_login_issues_a_token_pair(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    assert tokens["tokenType"] == "Bearer"
    assert tokens["expiresIn"] == 900
    assert tokens["accessToken"]
    assert tokens["refreshToken"]


async def test_the_access_token_names_the_user_and_one_workspace(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    body = claims(tokens)

    assert body["email"] == "ada@example.com"
    assert body["name"] == "Ada Lovelace"
    assert uuid.UUID(body["sub"])
    assert uuid.UUID(body["wsp"])
    assert body["roles"] == ["owner"]


async def test_a_later_user_still_lands_in_their_own_workspace(client: httpx.AsyncClient) -> None:
    """The workspace a session starts in is chosen, not whichever row sorts first.

    Once the demo workspace already exists — which is the normal case, since the
    service creates it at startup — it is the *older* of the two a new user
    joins. Ordering by age alone would drop everybody into the shared workspace
    as a member.
    """
    await sign_in(client, "grace@example.com")

    tokens = await sign_in(client, "ada@example.com")

    assert claims(tokens)["roles"] == ["owner"]


async def test_signing_in_again_is_the_same_account(client: httpx.AsyncClient) -> None:
    first = claims(await sign_in(client, "ada@example.com"))
    second = claims(await sign_in(client, "ADA@EXAMPLE.COM"))

    assert first["sub"] == second["sub"]
    assert first["wsp"] == second["wsp"]


async def test_a_new_user_gets_their_own_workspace_and_the_demo_one(
    client: httpx.AsyncClient,
) -> None:
    tokens = await sign_in(client)

    resp = await client.get("/api/v1/workspaces", headers=bearer(tokens))

    workspaces = resp.json()["items"]
    assert {w["role"] for w in workspaces} == {"owner", "member"}
    assert DEMO_WORKSPACE in {w["name"] for w in workspaces}
    assert resp.json()["nextCursor"] is None


async def test_two_users_share_the_demo_workspace(client: httpx.AsyncClient) -> None:
    ada = await sign_in(client, "ada@example.com")
    grace = await sign_in(client, "grace@example.com")

    async def demo_id(tokens: dict[str, Any]) -> str:
        resp = await client.get("/api/v1/workspaces", headers=bearer(tokens))
        return next(w["id"] for w in resp.json()["items"] if w["name"] == DEMO_WORKSPACE)

    assert await demo_id(ada) == await demo_id(grace)


async def test_dev_login_does_not_exist_outside_local(
    postgres_dsn: str, redis_url: str, engine
) -> None:
    """The shortcut is a local convenience; deployed environments federate."""
    app = create_app(
        build_settings(postgres_dsn, redis_url, app_env="production", auth_signing_key=_A_KEY)
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/v1/auth/dev-login", json={"email": "ada@example.com"})

    assert resp.status_code == 404


async def test_a_malformed_sign_in_reports_the_field(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/dev-login", json={})

    assert resp.status_code == 400
    assert resp.headers["content-type"] == "application/problem+json"
    assert "email" in resp.json()["errors"]


# --------------------------------------------------------------------------
# Using the token
# --------------------------------------------------------------------------


async def test_the_profile_endpoint_returns_the_signed_in_user(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await client.get("/api/v1/users/me", headers=bearer(tokens))

    assert resp.status_code == 200
    assert resp.json()["email"] == "ada@example.com"
    assert resp.json()["displayName"] == "Ada Lovelace"
    assert resp.json()["id"] == claims(tokens)["sub"]


async def test_the_profile_endpoint_needs_a_token(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/users/me")

    assert resp.status_code == 401
    assert resp.headers["content-type"] == "application/problem+json"


async def test_userinfo_reports_the_current_token_claims(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await client.get("/api/v1/auth/userinfo", headers=bearer(tokens))

    assert resp.json()["sub"] == claims(tokens)["sub"]
    assert resp.json()["wsp"] == claims(tokens)["wsp"]
    assert resp.json()["roles"] == ["owner"]


# --------------------------------------------------------------------------
# JWKS — how the rest of the platform trusts these tokens
# --------------------------------------------------------------------------


async def test_jwks_publishes_the_active_key(client: httpx.AsyncClient) -> None:
    resp = await client.get("/.well-known/jwks.json")

    assert resp.status_code == 200
    assert resp.json()["keys"]
    assert "max-age" in resp.headers["cache-control"]


async def test_an_issued_token_verifies_against_the_published_jwks(
    client: httpx.AsyncClient,
) -> None:
    """The whole platform's trust model in one assertion."""
    tokens = await sign_in(client)
    document = (await client.get("/.well-known/jwks.json")).json()

    key = jwt.PyJWKSet.from_dict(document).keys[0]
    verified = jwt.decode(
        tokens["accessToken"],
        key.key,
        algorithms=["RS256"],
        issuer="http://localhost:8001",
        audience="collabhub",
    )

    assert verified["email"] == "ada@example.com"


# --------------------------------------------------------------------------
# Refresh and rotation
# --------------------------------------------------------------------------


async def test_refresh_returns_a_new_pair(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await client.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]})

    assert resp.status_code == 200
    assert resp.json()["refreshToken"] != tokens["refreshToken"]
    assert claims(resp.json())["sub"] == claims(tokens)["sub"]


async def test_a_spent_refresh_token_stops_working(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)
    await client.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]})

    resp = await client.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]})

    assert resp.status_code == 401


async def test_replaying_a_spent_refresh_token_kills_the_whole_family(
    client: httpx.AsyncClient,
) -> None:
    """Reuse means the token leaked; the safe assumption is that both copies are
    suspect, so every descendant is revoked and the user signs in again."""
    tokens = await sign_in(client)
    rotated = (
        await client.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    ).json()

    await client.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]})

    resp = await client.post("/api/v1/auth/refresh", json={"refreshToken": rotated["refreshToken"]})
    assert resp.status_code == 401


async def test_a_snake_case_request_body_is_rejected(client: httpx.AsyncClient) -> None:
    """camelCase is the contract, so the old OAuth spelling is a validation error.

    Quietly accepting both is worse than refusing one: it leaves two shapes in
    circulation that no document describes, and the day one of them stops
    working, nobody knows which clients were relying on it.
    """
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "def..."})

    assert resp.status_code == 400
    assert "refreshToken" in resp.json()["errors"]


async def test_an_unknown_refresh_token_is_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/refresh", json={"refreshToken": "not-a-token"})

    assert resp.status_code == 401


async def test_an_expired_refresh_token_is_rejected(
    postgres_dsn: str, redis_url: str, engine
) -> None:
    app = create_app(build_settings(postgres_dsn, redis_url, auth_refresh_token_days=0))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        tokens = await sign_in(c)
        resp = await c.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]})

    assert resp.status_code == 401


# --------------------------------------------------------------------------
# Switching workspace (Conventions §5.4)
# --------------------------------------------------------------------------


async def workspace_id(client: httpx.AsyncClient, tokens: dict[str, Any], name: str) -> str:
    resp = await client.get("/api/v1/workspaces", headers=bearer(tokens))
    return next(w["id"] for w in resp.json()["items"] if w["name"] == name)


async def test_switching_workspace_rescopes_the_token(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)
    demo = await workspace_id(client, tokens, DEMO_WORKSPACE)

    resp = await client.post(
        "/api/v1/auth/switch-workspace",
        json={"refreshToken": tokens["refreshToken"], "workspaceId": demo},
    )

    assert resp.status_code == 200
    assert claims(resp.json())["wsp"] == demo
    assert claims(resp.json())["roles"] == ["member"]


async def test_switching_workspace_rotates_the_refresh_token(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)
    demo = await workspace_id(client, tokens, DEMO_WORKSPACE)

    switched = await client.post(
        "/api/v1/auth/switch-workspace",
        json={"refreshToken": tokens["refreshToken"], "workspaceId": demo},
    )

    assert switched.json()["refreshToken"] != tokens["refreshToken"]
    replayed = await client.post(
        "/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]}
    )
    assert replayed.status_code == 401


async def test_switching_to_a_workspace_you_are_not_in_is_refused(
    client: httpx.AsyncClient,
) -> None:
    tokens = await sign_in(client)

    resp = await client.post(
        "/api/v1/auth/switch-workspace",
        json={"refreshToken": tokens["refreshToken"], "workspaceId": str(uuid.uuid4())},
    )

    assert resp.status_code == 403


async def test_switching_never_takes_the_workspace_from_the_access_token(
    client: httpx.AsyncClient,
) -> None:
    """Ada must not be able to switch Grace's session into Ada's workspace."""
    ada = await sign_in(client, "ada@example.com")
    grace = await sign_in(client, "grace@example.com")
    ada_own = await workspace_id(client, ada, "Ada Lovelace's Workspace")

    resp = await client.post(
        "/api/v1/auth/switch-workspace",
        json={"refreshToken": grace["refreshToken"], "workspaceId": ada_own},
    )

    assert resp.status_code == 403


# --------------------------------------------------------------------------
# Signing out
# --------------------------------------------------------------------------


async def test_logout_revokes_the_access_token(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    await client.post("/api/v1/auth/logout", headers=bearer(tokens), json={})

    resp = await client.get("/api/v1/users/me", headers=bearer(tokens))
    assert resp.status_code == 401


async def test_logout_revokes_the_refresh_token_it_is_given(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    await client.post(
        "/api/v1/auth/logout",
        headers=bearer(tokens),
        json={"refreshToken": tokens["refreshToken"]},
    )

    resp = await client.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert resp.status_code == 401


async def test_logout_needs_a_token(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/logout", json={})

    assert resp.status_code == 401


# --------------------------------------------------------------------------
# Service tokens (Conventions §5.5)
# --------------------------------------------------------------------------


async def test_a_client_credentials_grant_issues_an_internal_token(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.post(
        "/api/v1/auth/service-token",
        json={
            "grantType": "client_credentials",
            "clientId": "worker",
            "clientSecret": WORKER_SECRET,
        },
    )

    assert resp.status_code == 200
    body = jwt.decode(resp.json()["accessToken"], options={"verify_signature": False})
    assert body["aud"] == "collabhub-internal"
    assert body["sub"] == "service:worker"
    assert body["scp"] == ["assets:write-variants"]
    assert "wsp" not in body


async def test_a_service_token_is_refused_with_the_wrong_secret(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/service-token",
        json={"grantType": "client_credentials", "clientId": "worker", "clientSecret": "wrong"},
    )

    assert resp.status_code == 401


async def test_an_unknown_client_is_refused(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/service-token",
        json={"grantType": "client_credentials", "clientId": "ghost", "clientSecret": "x"},
    )

    assert resp.status_code == 401


async def test_an_unsupported_grant_type_is_refused(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/service-token",
        json={"grantType": "password", "clientId": "worker", "clientSecret": WORKER_SECRET},
    )

    assert resp.status_code == 400


async def test_a_service_token_cannot_be_used_as_a_user_token(client: httpx.AsyncClient) -> None:
    service = await client.post(
        "/api/v1/auth/service-token",
        json={
            "grantType": "client_credentials",
            "clientId": "worker",
            "clientSecret": WORKER_SECRET,
        },
    )

    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {service.json()['accessToken']}"},
    )

    assert resp.status_code == 401
