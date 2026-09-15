"""Real Postgres, Redis and Dex for the Auth service's integration tests.

One container of each per test session (Conventions §11 — testcontainers, not
mocks). Every test gets a clean database: rather than re-running migrations,
which is slow, the tables are truncated between tests.

**Dex is real too.** Sign-in is the one thing this service exists to do, and a
stubbed identity provider would test our idea of OIDC rather than OIDC. The
tests drive the actual redirect flow, through the actual login form, against the
image the compose stack runs. Dex's accounts and container live in
`testkit.dex`, and Auth's test settings in `testkit.auth`, so test modules can
import them by name.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from auth.main import create_app
from auth.migrations import upgrade_to_head
from auth.settings import Settings
from testkit.auth import AUTH_ISSUER, build_settings
from testkit.dex import start_dex

TABLES = "refresh_tokens, external_identities, workspace_members, workspaces, users"


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    with PostgresContainer("postgres:18", driver="asyncpg") as container:
        dsn = container.get_connection_url()
        asyncio.run(upgrade_to_head(dsn))
        yield dsn


@pytest.fixture(scope="session")
def dex_issuer(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """A real Dex, configured for three local accounts. Yields its issuer URL."""
    with start_dex(tmp_path_factory.mktemp("dex"), relying_party_issuer=AUTH_ISSUER) as issuer:
        yield issuer


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:8") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        yield f"redis://{host}:{port}/0"


@pytest.fixture
async def engine(postgres_dsn: str) -> AsyncIterator:
    engine = create_async_engine(postgres_dsn)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
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
    app = create_app(app_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncIterator[aioredis.Redis]:
    client = aioredis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()
