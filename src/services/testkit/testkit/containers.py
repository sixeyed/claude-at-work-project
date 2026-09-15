"""The stores integration tests run against — one container each per session (D34).

Registered by `testkit.plugin` through `pytest_plugins`, never imported into a
conftest. That is what makes "one container per session" true: pytest keeps one
value per *fixture definition*, and a conftest import would be a second
definition, and a second Postgres, for every service that did it.

- **Postgres:** one server; each service creates its own database on it with
  `testkit.databases.service_database`, mirroring "every service owns its own
  database".
- **Redis:** one server; each role is a database index — R1 cache `/0`, R2
  realtime `/1`, R3 streams `/2` — following the three `redis_*_url` settings.
- **Elasticsearch:** started the first time a test asks for it, and not before;
  it is the slowest container by far.

A unit test may not depend on any of these; the plugin stops the run at
collection if one does.

Heavy imports sit inside the fixtures, because this module loads into every
pytest run in the workspace, unit runs included.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

import pytest

from testkit import images
from testkit.databases import PostgresServer

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from elasticsearch import AsyncElasticsearch


class RedisRole(IntEnum):
    """Conventions §6/§7 — the three Redis instances, as database indexes here."""

    CACHE = 0  # R1 — cache and token denylist
    REALTIME = 1  # R2 — Socket.IO backplane
    STREAMS = 2  # R3 — job streams


@dataclass(frozen=True)
class RedisServer:
    """One Redis standing in for R1, R2 and R3.

    **Index separation is for keys only.** Redis Pub/Sub channels belong to the
    server, not to a database index, so a backplane message published through
    R2's URL is visible to a subscriber on any index. What this catches is a
    *key* written to the wrong role — a stream on the cache index, a denylist
    entry on the streams index. A Socket.IO backplane crossing roles would pass;
    to check that a connection uses R2, look at its `db=` in `CLIENT LIST`.
    """

    host: str
    port: int

    def url(self, role: RedisRole) -> str:
        return f"redis://{self.host}:{self.port}/{int(role)}"


@pytest.fixture(scope="session")
def postgres_server() -> Iterator[PostgresServer]:
    """One Postgres for the whole run. Services create their databases on it."""
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer(images.POSTGRES, driver="asyncpg") as container:
        yield PostgresServer(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(container.port)),
            user=container.username,
            password=container.password,
            admin_database=container.dbname,
        )


@pytest.fixture(scope="session")
def redis_server() -> Iterator[RedisServer]:
    """One Redis for the whole run; take a role's URL with `redis_server.url(role)`."""
    from testcontainers.community.redis import RedisContainer

    with RedisContainer(images.REDIS) as container:
        yield RedisServer(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(container.port)),
        )


async def _role_client(server: RedisServer, role: RedisRole) -> aioredis.Redis:
    import redis.asyncio as aioredis

    client = aioredis.from_url(server.url(role), decode_responses=True)
    # FLUSHDB, not FLUSHALL: a test holding the cache must not wipe the streams.
    await client.flushdb()
    return client


@pytest.fixture
async def redis_cache(redis_server: RedisServer) -> AsyncIterator[aioredis.Redis]:
    """A client on R1's index, flushed before the test."""
    client = await _role_client(redis_server, RedisRole.CACHE)
    yield client
    await client.aclose()


@pytest.fixture
async def redis_streams(redis_server: RedisServer) -> AsyncIterator[aioredis.Redis]:
    """A client on R3's index, flushed before the test."""
    client = await _role_client(redis_server, RedisRole.STREAMS)
    yield client
    await client.aclose()


@pytest.fixture(scope="session")
def elasticsearch_url() -> Iterator[str]:
    """Elasticsearch as Compose runs it: single node, no security, a 512 MB heap.

    `action.destructive_requires_name=false` is the one difference, and it is a
    test convenience: it lets the `elasticsearch` fixture drop every index with
    a wildcard before each test.
    """
    from testcontainers.community.elasticsearch import ElasticSearchContainer

    container = (
        ElasticSearchContainer(images.ELASTICSEARCH)
        .with_env("discovery.type", "single-node")
        .with_env("xpack.security.enabled", "false")
        .with_env("ES_JAVA_OPTS", "-Xms512m -Xmx512m")
        .with_env("action.destructive_requires_name", "false")
    )
    with container:
        host = container.get_container_host_ip()
        yield f"http://{host}:{container.get_exposed_port(container.port)}"


@pytest.fixture
async def elasticsearch(elasticsearch_url: str) -> AsyncIterator[AsyncElasticsearch]:
    """A client on a cluster with no indices in it."""
    from elasticsearch import AsyncElasticsearch

    client = AsyncElasticsearch(elasticsearch_url)
    await client.indices.delete(index="*", expand_wildcards="open,closed", ignore_unavailable=True)
    yield client
    await client.close()
