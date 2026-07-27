"""Smoke test: the Auth service builds and answers liveness."""

import httpx

from auth.main import create_app
from auth.settings import Settings


def _settings() -> Settings:
    return Settings(
        postgres_dsn="postgresql+asyncpg://collabhub:collabhub@postgres:5432/collabhub_auth",
        redis_cache_url="redis://redis-cache:6379/0",
        auth_issuer="http://localhost:8001",
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
