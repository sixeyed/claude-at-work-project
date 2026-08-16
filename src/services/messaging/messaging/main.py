"""Messaging service entry point.

`create_app` builds everything from a `Settings` object and hangs it on
`app.state`, so a test can point an app at a throwaway database without patching
module globals.

Unlike Auth, Messaging does not hold the signing key, so it verifies tokens
against Auth's published JWKS through `JwksClient` — the stateless path every
service but Auth uses (Conventions §5.1). There is no per-request call to Auth;
the client caches by `kid` and refetches on a miss.

The process serves two things on one port: FastAPI, and the Socket.IO
`/messaging` namespace from spec §3.2. `create_app` still returns a plain
`FastAPI` — every integration test drives that over `httpx.ASGITransport`, and
`python -m messaging.openapi` builds a document from it with nothing running —
and `build_asgi_app` wraps it for the server that actually listens.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import socketio
from fastapi import FastAPI

from messaging.db import build_engine, build_sessions
from messaging.realtime import RealtimeContext, build_server
from messaging.realtime_writes import register_write_handlers
from messaging.routers import channels as channel_routes
from messaging.routers import messages as message_routes
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
    # Replaced by `build_asgi_app` in a running process. `None` here is what
    # makes the publishers in the routers inert under `ASGITransport`, so the
    # tests exercise the real router code without a socket server behind it.
    app.state.realtime = None

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
    # Two routers from one module: history and sending hang off `/channels`, a
    # single message is addressable on its own.
    app.include_router(message_routes.channel_router)
    app.include_router(message_routes.router)

    return app


def build_asgi_app(settings: Settings, *, key_source: KeySource | None = None):
    """The app the server actually runs: Socket.IO wrapping FastAPI.

    **Constructed with `other_asgi_app` and nothing else, deliberately.**
    `socketio.ASGIApp` handles the `lifespan` scope itself and only delegates it
    down when it was given neither `on_startup` nor `on_shutdown`. Adding either
    — the obvious place to reach for if the socket server ever needs warm-up —
    would silently stop `create_app`'s lifespan running, leaking a connection
    pool and a Redis client per process with no error anywhere. Anything the
    socket layer needs at startup belongs in the FastAPI lifespan underneath.

    Everything that is not the engine.io path falls through to the FastAPI app,
    so `/health/live` still answers and the Compose healthcheck is unchanged.
    """
    app = create_app(settings, key_source=key_source)
    context = RealtimeContext(
        settings=settings,
        sessions=app.state.sessions,
        security=app.state.security,
    )
    sio = build_server(context)
    register_write_handlers(sio, context)
    app.state.realtime = sio
    return socketio.ASGIApp(sio, other_asgi_app=app)


def asgi_factory():
    """Uvicorn entry point: `uvicorn messaging.main:asgi_factory --factory`.

    One factory, not one live and one dead — `app_factory` is gone rather than
    left beside this, so nothing can start a process with no socket server in it.
    """
    return build_asgi_app(Settings())
