"""Fixtures for the Messaging integration tests.

Real Postgres and Redis, not mocks (Conventions §11) — a keyset cursor, a
partial unique index and a case-folded collision are all things only a real
database can tell you the truth about. The servers are the session's shared
ones from `testkit.containers` (register D34): Messaging gets its own database,
`messaging`, and — as the one service that uses all three Redis roles — a
separate index for each.

Tokens come from `testkit.tokens` rather than from Auth. Messaging verifies
signatures against a JWKS it does not own, so the only thing a real Auth would
add is a second container and a slower suite; what matters is that the token is
a genuine RS256 JWT with the right claims, and a local key gives that.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from messaging.main import build_asgi_app, create_app
from messaging.migrations import upgrade_to_head
from messaging.settings import Settings
from testkit.apps import asgi_client, serve
from testkit.containers import RedisRole, RedisServer
from testkit.databases import PostgresServer, service_database
from testkit.db import truncate
from testkit.tokens import ISSUER, USER_AUDIENCE, Tokens

#: Child tables first — `messages` and `channel_members` both reference
#: `channels`. `CASCADE` would reach them anyway; being explicit is what stops
#: the next person wondering whether the order matters.
TABLES = ("messages", "channel_reads", "channel_members", "channels")


@pytest.fixture(scope="session")
def postgres_dsn(postgres_server: PostgresServer) -> str:
    return service_database(postgres_server, "messaging", upgrade_to_head)


@pytest.fixture
async def engine(postgres_dsn: str) -> AsyncIterator:
    engine = create_async_engine(postgres_dsn)
    await truncate(engine, TABLES)
    yield engine
    await engine.dispose()


def build_settings(postgres_dsn: str, redis: RedisServer, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "local",
        "postgres_dsn": postgres_dsn,
        "redis_cache_url": redis.url(RedisRole.CACHE),
        "redis_realtime_url": redis.url(RedisRole.REALTIME),
        "redis_streams_url": redis.url(RedisRole.STREAMS),
        # Unreachable unless a test asks for the real one: only the search tests
        # start Elasticsearch, and they pass `elasticsearch_url` to `client_for`.
        "elasticsearch_url": "http://elasticsearch.invalid:9200",
        "auth_issuer": ISSUER,
        "auth_audience": USER_AUDIENCE,
        "auth_jwks_url": "https://auth.test/.well-known/jwks.json",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
async def app_settings(postgres_dsn: str, redis_server: RedisServer) -> Settings:
    return build_settings(postgres_dsn, redis_server)


@pytest.fixture
async def client(
    app_settings: Settings, tokens: Tokens, engine
) -> AsyncIterator[httpx.AsyncClient]:
    """The Messaging app on an ASGI transport, against the real containers."""
    async with asgi_client(create_app(app_settings, key_source=tokens.key_source())) as c:
        yield c


@pytest.fixture
def client_for(
    postgres_dsn: str, redis_server: RedisServer, tokens: Tokens, engine
) -> Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]]:
    """A client against an app built with one or two settings changed.

    For the rules that *are* the configuration — the body limit — and for
    pointing one app at a real or an unreachable store: Elasticsearch for the
    search tests, a dead R3 for the fire-and-forget producer.

    A fixture rather than an import, deliberately. Every service in this repo
    has a `tests` package with no `__init__.py`, so `tests` is one namespace
    package spanning all of them; ruff bans `from tests.conftest import
    build_settings` outright (TID251) rather than let it bind to whichever
    service sorts first. Shared helpers go in `testkit`; a service's own go
    through fixtures like this one.
    """

    @asynccontextmanager
    async def build(**overrides: Any) -> AsyncIterator[httpx.AsyncClient]:
        settings = build_settings(postgres_dsn, redis_server, **overrides)
        async with asgi_client(create_app(settings, key_source=tokens.key_source())) as c:
            yield c

    return build


@pytest.fixture
async def realtime_url(app_settings: Settings, tokens: Tokens, engine) -> AsyncIterator[str]:
    """A real uvicorn serving the Socket.IO app — see `testkit.apps.serve` for why.

    In `conftest.py` rather than in a test module because the inbound-event
    tests need the same server, and neither test module owns the other's
    fixtures.
    """
    async with serve(build_asgi_app(app_settings, key_source=tokens.key_source())) as url:
        yield url


@pytest.fixture
def ada(tokens: Tokens) -> dict[str, str]:
    return tokens.header()


@pytest.fixture
def grace(tokens: Tokens) -> dict[str, str]:
    return tokens.header(user_id=tokens.GRACE, name="Grace Hopper", email="grace@collabhub.dev")
