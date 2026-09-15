"""The shared health router behaves the same way for every service that mounts it."""

import httpx
import pytest
from fastapi import FastAPI

from shared import build_health_router


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _get(app: FastAPI, path: str) -> httpx.Response:
    async with _client(app) as client:
        return await client.get(path)


def _app(checks: dict) -> FastAPI:
    app = FastAPI()
    app.include_router(build_health_router(checks))
    return app


async def test_live_ignores_dependencies() -> None:
    async def broken() -> None:
        raise RuntimeError("postgres is down")

    resp = await _get(_app({"postgres": broken}), "/health/live")

    assert resp.status_code == 200
    assert resp.json() == {"status": "live"}


async def test_ready_is_200_when_every_check_passes() -> None:
    async def ok() -> None:
        return None

    resp = await _get(_app({"postgres": ok, "redis-cache": ok}), "/health/ready")

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ready",
        "checks": {"postgres": "ok", "redis-cache": "ok"},
    }


async def test_ready_is_503_and_names_the_failure() -> None:
    async def ok() -> None:
        return None

    async def broken() -> None:
        raise ConnectionError("connection refused")

    resp = await _get(_app({"postgres": ok, "redis-cache": broken}), "/health/ready")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["postgres"] == "ok"
    assert "connection refused" in body["checks"]["redis-cache"]


async def test_ready_times_out_rather_than_hanging_the_probe() -> None:
    import asyncio

    async def slow() -> None:
        await asyncio.sleep(10)

    app = FastAPI()
    app.include_router(build_health_router({"elasticsearch": slow}, timeout=0.01))

    resp = await _get(app, "/health/ready")

    assert resp.status_code == 503
    assert "timed out" in resp.json()["checks"]["elasticsearch"]


@pytest.mark.parametrize("path", ["/health/live", "/health/ready"])
async def test_no_checks_configured_is_still_healthy(path: str) -> None:
    resp = await _get(_app({}), path)

    assert resp.status_code == 200
