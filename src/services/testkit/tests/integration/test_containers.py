"""The shared container fixtures do what services rely on (register D34).

One smoke test per fixture: a database per service is really separate, a role's
Redis client is really on its own index, and Elasticsearch answers with the
pinned version and no indices left over from an earlier test.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from testkit import images
from testkit.containers import RedisRole
from testkit.databases import service_database


async def _create_marker_table(dsn: str) -> None:
    engine = create_async_engine(dsn)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE marker (id integer)"))
    await engine.dispose()


async def _no_migrations(dsn: str) -> None:
    return None


async def _tables(dsn: str) -> list[str]:
    engine = create_async_engine(dsn)
    async with engine.connect() as connection:
        rows = await connection.scalars(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")
        )
        names = list(rows)
    await engine.dispose()
    return names


def test_each_service_database_is_its_own(postgres_server):
    alpha = service_database(postgres_server, "smoke_alpha", _create_marker_table)
    beta = service_database(postgres_server, "smoke_beta", _no_migrations)

    assert asyncio.run(_tables(alpha)) == ["marker"]
    assert asyncio.run(_tables(beta)) == []


async def test_role_clients_sit_on_their_own_indexes(redis_server, redis_cache, redis_streams):
    await redis_cache.set("auth:revoked:some-jti", "1")

    assert redis_server.url(RedisRole.STREAMS).endswith("/2")
    assert await redis_streams.dbsize() == 0
    assert "db=0" in await redis_cache.execute_command("CLIENT", "INFO")
    assert "db=2" in await redis_streams.execute_command("CLIENT", "INFO")


async def test_elasticsearch_answers_with_the_pinned_version(elasticsearch):
    info = await elasticsearch.info()
    # Left behind on purpose: the next test proves the fixture clears it.
    await elasticsearch.indices.create(index="smoke-leftover")

    assert info["version"]["number"] == images.ELASTICSEARCH.rsplit(":", 1)[1]


async def test_every_test_starts_with_no_indices(elasticsearch):
    assert await elasticsearch.indices.get(index="*") == {}
