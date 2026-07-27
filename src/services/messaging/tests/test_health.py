"""Smoke test: the Messaging service builds and answers liveness."""

import httpx

from messaging.main import create_app
from messaging.settings import Settings


def _settings() -> Settings:
    return Settings(
        postgres_dsn="postgresql+asyncpg://collabhub:collabhub@postgres:5432/collabhub_messaging",
        redis_cache_url="redis://redis-cache:6379/0",
        redis_realtime_url="redis://redis-rt:6379/0",
        redis_streams_url="redis://redis-streams:6379/0",
        auth_issuer="http://localhost:8001",
        auth_jwks_url="http://auth:8000/.well-known/jwks.json",
    )


async def test_live() -> None:
    app = create_app(_settings())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/live")

    assert resp.status_code == 200
    assert resp.json() == {"status": "live"}


def test_declares_the_dependencies_it_owns() -> None:
    app = create_app(_settings())

    paths = set(app.openapi()["paths"])
    assert {"/health/live", "/health/ready"} <= paths
