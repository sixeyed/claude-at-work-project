"""Real backing services for the shared library's integration tests.

Conventions §11 calls for testcontainers rather than mocks: a fake Redis that
never drops a connection cannot tell us whether the denylist fails open, and
that behaviour is the whole point of the module.
"""

from collections.abc import Iterator

import pytest
import redis.asyncio as aioredis
from testcontainers.community.redis import RedisContainer


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:8") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        yield f"redis://{host}:{port}/0"


@pytest.fixture
async def redis_client(redis_url: str) -> Iterator[aioredis.Redis]:
    client = aioredis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()
