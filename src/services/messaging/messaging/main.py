"""Messaging service entry point.

`create_app` builds everything from a `Settings` object and hangs it on
`app.state`, so a test can point an app at a throwaway database without patching
module globals.

Unlike Auth, Messaging does not hold the signing key, so it verifies tokens
against Auth's published JWKS through `JwksClient` — the stateless path every
service but Auth uses (Conventions §5.1). There is no per-request call to Auth;
the client caches by `kid` and refetches on a miss.

The Socket.IO `/messaging` namespace described in spec §3.2 is not here yet. It
arrives with real-time delivery, at which point `create_app` keeps returning the
FastAPI app and a `build_asgi_app` wraps it — so the tests that drive this
through `ASGITransport` keep working.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI

from messaging.db import build_engine, build_sessions
from messaging.routers import channels as channel_routes
from messaging.settings import Settings
from shared import (
    Denylist,
    JwksClient,
    KeySource,
    SecurityConfig,
    build_health_router,
    install_cors,
    install_problem_handlers,
    install_security,
    postgres_check,
    redis_check,
)


def create_app(settings: Settings, *, key_source: KeySource | None = None) -> FastAPI:
    """Build the app. `key_source` defaults to Auth's published JWKS.

    Tests pass a `StaticKeySource` holding a key they mint with, which is what
    lets them exercise `require_user` for real without standing up Auth. Nothing
    else about the app changes, so what they exercise is the production path.
    """
    engine = build_engine(settings.postgres_dsn)
    sessions = build_sessions(engine)
    redis_client = aioredis.from_url(settings.redis_cache_url, decode_responses=True)

    keys = key_source or JwksClient(settings.auth_jwks_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        # Only close what this function opened; an injected source is the
        # caller's to dispose of.
        if key_source is None and isinstance(keys, JwksClient):
            await keys.aclose()
        await engine.dispose()
        await redis_client.aclose()

    app = FastAPI(title="CollabHub Messaging", version="0.1.0", lifespan=lifespan)

    app.state.settings = settings
    app.state.sessions = sessions
    app.state.denylist = Denylist(redis_client)

    install_cors(app, origins=settings.cors_allowed_origins)
    install_problem_handlers(app)
    install_security(
        app,
        key_source=keys,
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
                "redis-realtime": redis_check(settings.redis_realtime_url),
                "redis-streams": redis_check(settings.redis_streams_url),
            }
        )
    )
    app.include_router(channel_routes.router)

    return app


def app_factory() -> FastAPI:
    """Uvicorn entry point: `uvicorn messaging.main:app_factory --factory`."""
    return create_app(Settings())
