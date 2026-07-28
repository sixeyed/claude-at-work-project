"""`require_user` / `require_service` — the platform's front door (Conventions §5).

These tests hold the line on the rules that a tenancy or privilege bug would
break: the signature, issuer and expiry must all check out; the audience is what
separates a user token from a service token, in both directions; and the
workspace comes from the `wsp` claim, never from the request.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
import redis.asyncio as aioredis
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI

from shared import (
    Denylist,
    SecurityConfig,
    ServicePrincipal,
    StaticKeySource,
    UserPrincipal,
    install_problem_handlers,
    install_security,
    require_service,
    require_user,
    require_user_sensitive,
)

pytestmark = pytest.mark.integration

ISSUER = "https://auth.test"
KEY_ID = "test-key"
USER_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def other_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def mint(
    key: rsa.RSAPrivateKey,
    *,
    kid: str = KEY_ID,
    issuer: str = ISSUER,
    audience: str = "collabhub",
    lifetime: timedelta = timedelta(minutes=15),
    **claims: Any,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + lifetime,
        "jti": uuid.uuid4().hex,
        **claims,
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


def user_token(key: rsa.RSAPrivateKey, **overrides: Any) -> str:
    claims: dict[str, Any] = {
        "sub": str(USER_ID),
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "wsp": str(WORKSPACE_ID),
        "roles": ["member"],
    }
    claims.update(overrides)
    return mint(key, **claims)


def service_token(key: rsa.RSAPrivateKey, **overrides: Any) -> str:
    claims: dict[str, Any] = {
        "sub": "service:worker",
        "scp": ["assets:write-variants"],
        "audience": "collabhub-internal",
    }
    claims.update(overrides)
    return mint(key, **claims)


def build_app(signing_key: rsa.RSAPrivateKey, denylist: Denylist) -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)
    install_security(
        app,
        key_source=StaticKeySource({KEY_ID: signing_key.public_key()}),
        config=SecurityConfig(issuer=ISSUER),
        denylist=denylist,
    )

    @app.get("/me")
    async def me(principal: UserPrincipal = Depends(require_user)) -> dict[str, Any]:
        return {
            "userId": str(principal.user_id),
            "workspaceId": str(principal.workspace_id),
            "roles": list(principal.roles),
            "email": principal.email,
        }

    @app.post("/members")
    async def members(principal: UserPrincipal = Depends(require_user_sensitive)) -> dict[str, str]:
        return {"userId": str(principal.user_id)}

    @app.post("/api/v1/internal/variants")
    async def variants(
        principal: ServicePrincipal = Depends(require_service("assets:write-variants")),
    ) -> dict[str, str]:
        return {"service": principal.name}

    return app


@pytest.fixture
async def client(signing_key: rsa.RSAPrivateKey, redis_client: aioredis.Redis):
    app = build_app(signing_key, Denylist(redis_client))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_a_valid_token_yields_the_principal(client, signing_key) -> None:
    resp = await client.get("/me", headers=bearer(user_token(signing_key)))

    assert resp.status_code == 200
    assert resp.json() == {
        "userId": str(USER_ID),
        "workspaceId": str(WORKSPACE_ID),
        "roles": ["member"],
        "email": "ada@example.com",
    }


async def test_a_missing_authorization_header_is_rejected(client) -> None:
    resp = await client.get("/me")

    assert resp.status_code == 401
    assert resp.json()["type"] == "https://collabhub.dev/problems/unauthorized"
    assert resp.headers["WWW-Authenticate"] == "Bearer"


async def test_a_non_bearer_authorization_header_is_rejected(client) -> None:
    resp = await client.get("/me", headers={"Authorization": "Basic ZGVtbzpkZW1v"})

    assert resp.status_code == 401


async def test_a_token_signed_by_another_key_is_rejected(client, other_key) -> None:
    resp = await client.get("/me", headers=bearer(user_token(other_key)))

    assert resp.status_code == 401


async def test_a_token_with_an_unknown_key_id_is_rejected(client, signing_key) -> None:
    resp = await client.get("/me", headers=bearer(user_token(signing_key, kid="rotated-away")))

    assert resp.status_code == 401


async def test_an_expired_token_is_rejected(client, signing_key) -> None:
    stale = user_token(signing_key, lifetime=timedelta(minutes=-1))

    resp = await client.get("/me", headers=bearer(stale))

    assert resp.status_code == 401


async def test_a_token_from_another_issuer_is_rejected(client, signing_key) -> None:
    resp = await client.get("/me", headers=bearer(user_token(signing_key, issuer="https://evil")))

    assert resp.status_code == 401


async def test_a_user_token_without_a_workspace_claim_is_rejected(client, signing_key) -> None:
    """Every user token is scoped to exactly one workspace (Conventions §5.4)."""
    resp = await client.get("/me", headers=bearer(user_token(signing_key, wsp=None)))

    assert resp.status_code == 401


async def test_a_revoked_token_is_rejected(client, signing_key, redis_client) -> None:
    token = user_token(signing_key)
    jti = jwt.decode(token, options={"verify_signature": False})["jti"]
    await Denylist(redis_client).revoke(jti, ttl_seconds=900)

    resp = await client.get("/me", headers=bearer(token))

    assert resp.status_code == 401


async def test_an_ordinary_request_proceeds_when_the_denylist_is_unreachable(
    signing_key,
) -> None:
    """Fail open: short token lifetimes make this the right availability trade."""
    unreachable = aioredis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.05)
    app = build_app(signing_key, Denylist(unreachable))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/me", headers=bearer(user_token(signing_key)))

    await unreachable.aclose()
    assert resp.status_code == 200


async def test_a_sensitive_request_refuses_when_the_denylist_is_unreachable(
    signing_key,
) -> None:
    """Fail closed: membership changes must not run on an uncheckable token."""
    unreachable = aioredis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.05)
    app = build_app(signing_key, Denylist(unreachable))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/members", headers=bearer(user_token(signing_key)))

    await unreachable.aclose()
    assert resp.status_code == 503
    assert resp.json()["type"] == "https://collabhub.dev/problems/service-unavailable"


async def test_a_service_token_satisfies_an_internal_endpoint(client, signing_key) -> None:
    token = mint(
        signing_key,
        audience="collabhub-internal",
        sub="service:worker",
        scp=["assets:write-variants"],
    )

    resp = await client.post("/api/v1/internal/variants", headers=bearer(token))

    assert resp.status_code == 200
    assert resp.json() == {"service": "worker"}


async def test_a_service_token_without_the_scope_is_forbidden(client, signing_key) -> None:
    token = mint(
        signing_key, audience="collabhub-internal", sub="service:worker", scp=["notify:send"]
    )

    resp = await client.post("/api/v1/internal/variants", headers=bearer(token))

    assert resp.status_code == 403


async def test_a_user_token_can_never_satisfy_an_internal_endpoint(client, signing_key) -> None:
    resp = await client.post("/api/v1/internal/variants", headers=bearer(user_token(signing_key)))

    assert resp.status_code == 401


async def test_a_service_token_can_never_satisfy_a_user_endpoint(client, signing_key) -> None:
    token = mint(
        signing_key,
        audience="collabhub-internal",
        sub="service:worker",
        scp=["assets:write-variants"],
    )

    resp = await client.get("/me", headers=bearer(token))

    assert resp.status_code == 401
