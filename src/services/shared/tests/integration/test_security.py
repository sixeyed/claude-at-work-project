"""`require_user` / `require_service` — the platform's front door (Conventions §5).

These tests hold the line on the rules that a tenancy or privilege bug would
break: the signature, issuer and expiry must all check out; the audience is what
separates a user token from a service token, in both directions; and the
workspace comes from the `wsp` claim, never from the request.

Tokens come from the `tokens` fixture (`testkit.tokens`); the one minted with
a key the app does not trust uses a second `Tokens` over `other_key`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import jwt
import pytest
import redis.asyncio as aioredis
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI

from shared import (
    Denylist,
    ProblemException,
    SecurityConfig,
    SecurityContext,
    ServicePrincipal,
    UserPrincipal,
    install_problem_handlers,
    install_security,
    require_service,
    require_user,
    require_user_sensitive,
    verify_user_token,
)
from testkit.apps import asgi_client
from testkit.tokens import ISSUER, Tokens


@pytest.fixture(scope="module")
def other_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def build_app(tokens: Tokens, denylist: Denylist) -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)
    install_security(
        app,
        key_source=tokens.key_source(),
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
async def client(tokens: Tokens, redis_cache: aioredis.Redis):
    async with asgi_client(build_app(tokens, Denylist(redis_cache))) as c:
        yield c


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_a_valid_token_yields_the_principal(client, tokens) -> None:
    resp = await client.get("/me", headers=bearer(tokens.mint()))

    assert resp.status_code == 200
    assert resp.json() == {
        "userId": str(tokens.ADA),
        "workspaceId": str(tokens.WORKSPACE),
        "roles": ["member"],
        "email": "ada@collabhub.dev",
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
    resp = await client.get("/me", headers=bearer(Tokens(other_key).mint()))

    assert resp.status_code == 401


async def test_a_token_with_an_unknown_key_id_is_rejected(client, tokens) -> None:
    resp = await client.get("/me", headers=bearer(tokens.mint(kid="rotated-away")))

    assert resp.status_code == 401


async def test_an_expired_token_is_rejected(client, tokens) -> None:
    stale = tokens.mint(lifetime=timedelta(minutes=-1))

    resp = await client.get("/me", headers=bearer(stale))

    assert resp.status_code == 401


async def test_a_token_from_another_issuer_is_rejected(client, tokens) -> None:
    resp = await client.get("/me", headers=bearer(tokens.mint(iss="https://evil")))

    assert resp.status_code == 401


async def test_a_user_token_without_a_workspace_claim_is_rejected(client, tokens) -> None:
    """Every user token is scoped to exactly one workspace (Conventions §5.4)."""
    resp = await client.get("/me", headers=bearer(tokens.mint(wsp=None)))

    assert resp.status_code == 401


async def test_a_revoked_token_is_rejected(client, tokens, redis_cache) -> None:
    token = tokens.mint()
    jti = jwt.decode(token, options={"verify_signature": False})["jti"]
    await Denylist(redis_cache).revoke(jti, ttl_seconds=900)

    resp = await client.get("/me", headers=bearer(token))

    assert resp.status_code == 401


async def test_an_ordinary_request_proceeds_when_the_denylist_is_unreachable(tokens) -> None:
    """Fail open: short token lifetimes make this the right availability trade."""
    unreachable = aioredis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.05)

    async with asgi_client(build_app(tokens, Denylist(unreachable))) as c:
        resp = await c.get("/me", headers=bearer(tokens.mint()))

    await unreachable.aclose()
    assert resp.status_code == 200


async def test_a_sensitive_request_refuses_when_the_denylist_is_unreachable(tokens) -> None:
    """Fail closed: membership changes must not run on an uncheckable token."""
    unreachable = aioredis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.05)

    async with asgi_client(build_app(tokens, Denylist(unreachable))) as c:
        resp = await c.post("/members", headers=bearer(tokens.mint()))

    await unreachable.aclose()
    assert resp.status_code == 503
    assert resp.json()["type"] == "https://collabhub.dev/problems/service-unavailable"


async def test_a_service_token_satisfies_an_internal_endpoint(client, tokens) -> None:
    token = tokens.service("worker", scopes=["assets:write-variants"])

    resp = await client.post("/api/v1/internal/variants", headers=bearer(token))

    assert resp.status_code == 200
    assert resp.json() == {"service": "worker"}


async def test_a_service_token_without_the_scope_is_forbidden(client, tokens) -> None:
    token = tokens.service("worker", scopes=["notify:send"])

    resp = await client.post("/api/v1/internal/variants", headers=bearer(token))

    assert resp.status_code == 403


async def test_a_user_token_can_never_satisfy_an_internal_endpoint(client, tokens) -> None:
    resp = await client.post("/api/v1/internal/variants", headers=bearer(tokens.mint()))

    assert resp.status_code == 401


async def test_a_service_token_can_never_satisfy_a_user_endpoint(client, tokens) -> None:
    token = tokens.service("worker", scopes=["assets:write-variants"])

    resp = await client.get("/me", headers=bearer(token))

    assert resp.status_code == 401


# --- the request-free path -------------------------------------------------
#
# `verify_user_token` is the same verification core the dependency above uses,
# reachable with a token string and no `Request`. It exists because a Socket.IO
# handshake has exactly that — a token and no request — and a verification core
# only reachable through a FastAPI dependency would have to be reimplemented for
# it, which is how two front doors end up disagreeing.
#
# The tests above are deliberately untouched by the extraction; those are the
# evidence the behaviour did not move. These cover the string entry point on its
# own terms: it *raises* rather than returning a response, because the caller
# decides how to render a refusal.


def context(tokens: Tokens, denylist: Denylist) -> SecurityContext:
    return SecurityContext(
        key_source=tokens.key_source(),
        config=SecurityConfig(issuer=ISSUER),
        denylist=denylist,
    )


async def test_verify_user_token_yields_the_principal(tokens, redis_cache) -> None:
    principal = await verify_user_token(context(tokens, Denylist(redis_cache)), tokens.mint())

    assert principal.user_id == tokens.ADA
    # From the `wsp` claim, which is the only place a workspace ever comes from.
    assert principal.workspace_id == tokens.WORKSPACE
    assert principal.roles == ("member",)


async def test_verify_user_token_refuses_a_service_token(tokens, redis_cache) -> None:
    # A service token presented with the *user* audience: the missing `wsp` and
    # the `service:` subject still have to stop it.
    token = tokens.service("worker", aud="collabhub")

    with pytest.raises(ProblemException) as raised:
        await verify_user_token(context(tokens, Denylist(redis_cache)), token)

    assert raised.value.status == 401


@pytest.mark.parametrize(
    "token_for",
    [
        pytest.param(lambda t: t.mint(lifetime=timedelta(minutes=-5)), id="expired"),
        pytest.param(lambda t: "not-a-jwt", id="malformed"),
        pytest.param(lambda t: t.mint(iss="https://elsewhere.test"), id="issuer"),
    ],
)
async def test_verify_user_token_refuses_a_bad_token(tokens, redis_cache, token_for) -> None:
    with pytest.raises(ProblemException) as raised:
        await verify_user_token(context(tokens, Denylist(redis_cache)), token_for(tokens))

    assert raised.value.status == 401


async def test_verify_user_token_refuses_a_token_with_no_workspace(tokens, redis_cache):
    token = tokens.mint(wsp=None)

    with pytest.raises(ProblemException) as raised:
        await verify_user_token(context(tokens, Denylist(redis_cache)), token)

    assert raised.value.status == 401
    assert "workspace" in (raised.value.detail or "")


async def test_verify_user_token_refuses_a_revoked_token(tokens, redis_cache) -> None:
    token = tokens.mint()
    jti = jwt.decode(token, options={"verify_signature": False}, audience="collabhub")["jti"]
    await Denylist(redis_cache).revoke(jti, ttl_seconds=900)

    with pytest.raises(ProblemException) as raised:
        await verify_user_token(context(tokens, Denylist(redis_cache)), token)

    assert raised.value.status == 401


async def test_verify_user_token_fails_open_and_closed_on_an_unreachable_denylist(tokens):
    """The same split Conventions §5.2 makes for HTTP, and the handshake takes the open half.

    A socket connection is not in the fail-closed set — channel membership is
    not workspace membership — so it passes `sensitive=False` and a Redis
    outage does not stop people chatting.
    """
    unreachable = aioredis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.05)
    ctx = context(tokens, Denylist(unreachable))

    principal = await verify_user_token(ctx, tokens.mint(), sensitive=False)
    with pytest.raises(ProblemException) as raised:
        await verify_user_token(ctx, tokens.mint(), sensitive=True)

    await unreachable.aclose()
    assert principal.user_id == tokens.ADA
    assert raised.value.status == 503
