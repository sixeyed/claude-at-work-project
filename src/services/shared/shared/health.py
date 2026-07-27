"""Liveness and readiness endpoints (Conventions §10).

`/health/live` answers "is this process up" and checks nothing. `/health/ready`
checks the dependencies the service owns and returns 503 until they all answer,
which is what the Kubernetes readiness probe reads.

The router lives here rather than in each service because five copies of the
same two routes drift. Services supply their own checks — Auth does not care
whether the Socket.IO backplane is reachable, and Messaging does.

Note: readiness returns a plain JSON body rather than RFC 7807 Problem Details.
Probes read the status code, not the body, and a health endpoint that depends on
the error-handling stack is a health endpoint that lies when that stack breaks.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# A check raises to signal failure and returns None to signal health.
HealthCheck = Callable[[], Awaitable[None]]

DEFAULT_CHECK_TIMEOUT_SECONDS = 2.0


async def _run_check(check: HealthCheck, timeout: float) -> str | None:  # noqa: ASYNC109
    """Run one check, returning None when healthy or a short reason when not.

    ASYNC109 asks callers to own their timeouts rather than pass one in. Turning a
    timeout into a *value* is this function's whole job — a hung dependency has to
    read as "not ready", not propagate out and hang the probe — so the parameter
    stays.
    """
    try:
        await asyncio.wait_for(check(), timeout)
    except TimeoutError:
        return f"timed out after {timeout}s"
    except Exception as exc:
        # Any failure at all means not ready; the reason goes in the body.
        return f"{type(exc).__name__}: {exc}"
    return None


def build_health_router(
    checks: Mapping[str, HealthCheck] | None = None,
    *,
    timeout: float = DEFAULT_CHECK_TIMEOUT_SECONDS,
) -> APIRouter:
    """Build a router exposing `/health/live` and `/health/ready`.

    `checks` maps a dependency name (used in the response body and in probe
    logs) to a callable that raises when that dependency is unreachable.
    """
    checks = dict(checks or {})
    router = APIRouter(tags=["health"])

    @router.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @router.get("/health/ready")
    async def ready(response: Response) -> dict[str, object]:
        names = list(checks)
        results = await asyncio.gather(*(_run_check(checks[name], timeout) for name in names))
        detail = {name: (reason or "ok") for name, reason in zip(names, results, strict=True)}
        healthy = all(reason is None for reason in results)
        if not healthy:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "ready" if healthy else "not_ready", "checks": detail}

    return router


def postgres_check(dsn: str) -> HealthCheck:
    """Check the service's own PostgreSQL database with `SELECT 1`."""
    engine = create_async_engine(dsn, pool_size=1, max_overflow=0, pool_pre_ping=True)

    async def check() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    return check


def redis_check(url: str) -> HealthCheck:
    """Check one Redis instance. R1, R2 and R3 are separate and each needs its own."""
    client = aioredis.from_url(url)

    async def check() -> None:
        await client.ping()

    return check


def http_check(url: str) -> HealthCheck:
    """Check a plain HTTP dependency (Elasticsearch, object storage) by GET."""

    async def check() -> None:
        async with httpx.AsyncClient(timeout=DEFAULT_CHECK_TIMEOUT_SECONDS) as client:
            resp = await client.get(url)
            resp.raise_for_status()

    return check
