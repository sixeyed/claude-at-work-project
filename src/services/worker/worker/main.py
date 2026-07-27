"""Worker entry point.

The Worker is headless (design doc 05 §2): a long-running asyncio process with
no business HTTP, exposing only the health endpoints Kubernetes probes.

Scaffold scope: the process starts, reads its config, answers health probes and
shuts down cleanly on SIGTERM. No consumer groups are read and no handlers are
registered — `jobs:index`, `jobs:thumbnail`, `jobs:notify`, `jobs:export` and
`jobs:retention` are all unconsumed.
"""

import asyncio

import uvicorn
from fastapi import FastAPI

from shared import build_health_router, http_check, redis_check
from worker.settings import Settings

HEALTH_PORT = 8000


def create_health_app(settings: Settings) -> FastAPI:
    """The Worker's only HTTP surface."""
    app = FastAPI(title="CollabHub Worker (health)", version="0.1.0")
    app.include_router(
        build_health_router(
            {
                "redis-streams": redis_check(settings.redis_streams_url),
                "elasticsearch": http_check(settings.elasticsearch_url),
            }
        )
    )
    return app


async def run(settings: Settings) -> None:
    """Serve health until shut down.

    Consumer tasks join this gather once handlers exist; Uvicorn already installs
    the SIGTERM handler that drains and exits (Conventions §10).
    """
    config = uvicorn.Config(
        create_health_app(settings),
        # Binds all interfaces because the container is the boundary; what is
        # reachable is the pod's and the ingress's concern, not the process's.
        host="0.0.0.0",
        port=HEALTH_PORT,
        log_level=settings.log_level,
    )
    await uvicorn.Server(config).serve()


def main() -> None:
    asyncio.run(run(Settings()))
