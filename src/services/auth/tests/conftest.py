"""Real Postgres and Redis for the Auth service's integration tests.

One container of each per test session (Conventions §11 — testcontainers, not
mocks). Every test gets a clean database: rather than re-running migrations,
which is slow, the tables are truncated between tests.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from auth.migrations import upgrade_to_head

TABLES = "refresh_tokens, external_identities, workspace_members, workspaces, users"


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    with PostgresContainer("postgres:18", driver="asyncpg") as container:
        dsn = container.get_connection_url()
        asyncio.run(upgrade_to_head(dsn))
        yield dsn


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
async def redis_client(redis_url: str) -> AsyncIterator[aioredis.Redis]:
    client = aioredis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()
