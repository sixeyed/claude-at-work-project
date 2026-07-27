"""Messaging service entry point.

Scaffold scope: the process starts, reads its config and answers health probes.
The REST endpoints and the Socket.IO `/messaging` namespace described in
docs/design/02-messaging-service.md §3 are not implemented yet.
"""

from fastapi import FastAPI

from messaging.settings import Settings
from shared import build_health_router, postgres_check, redis_check


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="CollabHub Messaging", version="0.1.0")
    app.include_router(
        build_health_router(
            {
                "postgres": postgres_check(settings.postgres_dsn),
                "redis-cache": redis_check(settings.redis_cache_url),
                "redis-realtime": redis_check(settings.redis_realtime_url),
                "redis-streams": redis_check(settings.redis_streams_url),
            }
        )
    )
    return app


def app_factory() -> FastAPI:
    """Uvicorn entry point: `uvicorn messaging.main:app_factory --factory`."""
    return create_app(Settings())
