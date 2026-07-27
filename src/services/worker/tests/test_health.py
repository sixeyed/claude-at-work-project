"""Smoke test: the Worker's health app builds, and it parses its stream list."""

import httpx

from worker.main import create_health_app
from worker.settings import Settings


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "redis_streams_url": "redis://redis-streams:6379/0",
        "elasticsearch_url": "http://elasticsearch:9200",
        "object_store_endpoint": "http://garage:3900",
    }
    values.update(overrides)
    return Settings(**values)


async def test_live() -> None:
    app = create_health_app(_settings())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/live")

    assert resp.status_code == 200
    assert resp.json() == {"status": "live"}


def test_exposes_no_business_http() -> None:
    app = create_health_app(_settings())

    paths = set(app.openapi()["paths"])
    assert paths == {"/health/live", "/health/ready"}


def test_streams_are_parsed_from_the_comma_separated_var() -> None:
    settings = _settings(worker_streams="jobs:thumbnail, jobs:export ,")

    assert settings.streams == ["jobs:thumbnail", "jobs:export"]
