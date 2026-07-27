"""Smoke test: the Asset service builds and answers liveness."""

import httpx

from asset.main import create_app
from asset.settings import Settings


def _settings() -> Settings:
    return Settings(
        postgres_dsn="postgresql+asyncpg://collabhub:collabhub@postgres:5432/collabhub_asset",
        redis_streams_url="redis://redis-streams:6379/0",
        auth_issuer="http://localhost:8001",
        auth_jwks_url="http://auth:8000/.well-known/jwks.json",
        object_store_endpoint="http://garage:3900",
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
