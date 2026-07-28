"""Auth service entry point.

`create_app` builds everything the service needs from a `Settings` object and
holds it on `app.state`, so a test can point an app at a throwaway database
without patching module globals.

Auth verifies its own tokens through the same `require_user` every other service
uses, but with a `StaticKeySource` rather than a `JwksClient` — it holds the
signing key, and fetching its own JWKS over HTTP would be a round trip through
its own ingress to learn something it already knows.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI

from auth.db import build_engine, build_sessions
from auth.identities import ensure_demo_workspace
from auth.keys import SigningKeys
from auth.loginflow import LoginFlowStore
from auth.oidc import build_clients
from auth.routers import auth as auth_routes
from auth.routers import federation as federation_routes
from auth.routers import users as user_routes
from auth.routers import wellknown as wellknown_routes
from auth.routers import workspaces as workspace_routes
from auth.settings import Settings
from auth.tokens import TokenIssuer
from shared import (
    Denylist,
    SecurityConfig,
    StaticKeySource,
    build_health_router,
    install_cors,
    install_problem_handlers,
    install_security,
    postgres_check,
    redis_check,
)

_log = logging.getLogger("collabhub.auth")


def create_app(settings: Settings) -> FastAPI:
    keys = SigningKeys.load(
        signing_key_pem=settings.auth_signing_key,
        previous_keys_pem=settings.auth_previous_keys,
        app_env=settings.app_env,
    )
    engine = build_engine(settings.postgres_dsn)
    sessions = build_sessions(engine)
    redis_client = aioredis.from_url(settings.redis_cache_url, decode_responses=True)

    oidc_clients = build_clients(settings.oidc_providers)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.is_local:
            # Create the shared local workspace up front, so the first sign-in
            # is not racing a second one to create it.
            async with sessions.begin() as session:
                await ensure_demo_workspace(session, settings.auth_demo_workspace_name)
        yield
        for client in oidc_clients.values():
            await client.aclose()
        await engine.dispose()
        await redis_client.aclose()

    app = FastAPI(title="CollabHub Auth", version="0.1.0", lifespan=lifespan)

    app.state.settings = settings
    app.state.signing_keys = keys
    app.state.sessions = sessions
    app.state.denylist = Denylist(redis_client)
    app.state.oidc_clients = oidc_clients
    app.state.login_flow = LoginFlowStore(
        redis_client,
        state_ttl_seconds=settings.auth_login_state_ttl_seconds,
        code_ttl_seconds=settings.auth_code_ttl_seconds,
    )
    app.state.token_issuer = TokenIssuer(
        keys=keys,
        issuer=settings.auth_issuer,
        audience=settings.auth_audience,
        internal_audience=settings.auth_internal_audience,
        access_token_minutes=settings.auth_access_token_minutes,
        service_token_minutes=settings.auth_service_token_minutes,
    )

    install_cors(app, origins=settings.cors_allowed_origins)
    install_problem_handlers(app)
    install_security(
        app,
        key_source=StaticKeySource(keys.public_keys()),
        config=SecurityConfig(
            issuer=settings.auth_issuer,
            audience=settings.auth_audience,
            internal_audience=settings.auth_internal_audience,
        ),
        denylist=app.state.denylist,
    )

    app.include_router(
        build_health_router(
            {
                "postgres": postgres_check(settings.postgres_dsn),
                "redis-cache": redis_check(settings.redis_cache_url),
            }
        )
    )
    app.include_router(wellknown_routes.router)
    app.include_router(federation_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(user_routes.router)
    app.include_router(workspace_routes.router)

    if not oidc_clients:
        # Not fatal: JWKS, refresh, and service tokens all still work, and a
        # deployment may be brought up before its IdP is configured. But no one
        # can sign in, which is worth saying once at startup rather than leaving
        # to be discovered as a 404 on /auth/login.
        _log.warning("no OIDC providers are configured — interactive sign-in is unavailable")

    return app


def app_factory() -> FastAPI:
    """Uvicorn entry point: `uvicorn auth.main:app_factory --factory`.

    Config is read here rather than at import time so tests can build an app
    without the environment being set up.
    """
    return create_app(Settings())
