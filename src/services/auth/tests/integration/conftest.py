"""Postgres, Redis and Dex for the Auth service's integration tests.

The Postgres and Redis servers are the session's shared ones, started by
`testkit.containers` (register D34): Auth gets a database of its own, `auth`,
and R1's index on Redis — the only role it uses. Every test gets clean tables:
they are truncated, which is much faster than re-running migrations.

**Dex is real too.** Sign-in is the one thing this service exists to do, and a
stubbed identity provider would test our idea of OIDC rather than OIDC. The
tests drive the actual redirect flow, through the actual login form, against the
image the compose stack runs. Dex's accounts and container live in
`testkit.dex`, and Auth's test settings in `testkit.auth`, so test modules can
import them by name.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from auth.main import create_app
from auth.migrations import upgrade_to_head
from auth.settings import Settings
from testkit.apps import asgi_client
from testkit.auth import AUTH_ISSUER, build_settings
from testkit.containers import RedisRole, RedisServer
from testkit.databases import PostgresServer, service_database
from testkit.db import truncate
from testkit.dex import start_dex

TABLES = ("refresh_tokens", "external_identities", "workspace_members", "workspaces", "users")


@pytest.fixture(scope="session")
def postgres_dsn(postgres_server: PostgresServer) -> str:
    return service_database(postgres_server, "auth", upgrade_to_head)


@pytest.fixture(scope="session")
def redis_url(redis_server: RedisServer) -> str:
    """R1 — the cache and denylist. Auth uses no other Redis role."""
    return redis_server.url(RedisRole.CACHE)


@pytest.fixture(scope="session")
def dex_issuer(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """A real Dex, configured for three local accounts. Yields its issuer URL."""
    with start_dex(tmp_path_factory.mktemp("dex"), relying_party_issuer=AUTH_ISSUER) as issuer:
        yield issuer


@pytest.fixture
async def engine(postgres_dsn: str) -> AsyncIterator:
    engine = create_async_engine(postgres_dsn)
    await truncate(engine, TABLES)
    yield engine
    await engine.dispose()


@pytest.fixture
async def sessions(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def app_settings(postgres_dsn: str, redis_url: str, dex_issuer: str) -> Settings:
    """The settings every integration test builds its app from."""
    return build_settings(postgres_dsn, redis_url, dex_issuer)


@pytest.fixture
async def client(app_settings: Settings, engine) -> AsyncIterator[httpx.AsyncClient]:
    """The Auth app on an ASGI transport, against the real containers."""
    async with asgi_client(create_app(app_settings)) as c:
        yield c
