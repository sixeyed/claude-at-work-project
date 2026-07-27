"""Asset service entry point.

Scaffold scope: the process starts, reads its config and answers health probes.
The presigned upload handshake in docs/design/04-asset-service.md §3, the
`ObjectStore` protocol and the internal variants endpoint are not implemented yet.

Readiness covers Postgres and R3 only. Object storage is not probed because the
`ObjectStore` abstraction it would go through does not exist yet — adding a
boto3 call here would prejudge that interface.
"""

from fastapi import FastAPI

from asset.settings import Settings
from shared import build_health_router, postgres_check, redis_check


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="CollabHub Asset", version="0.1.0")
    app.include_router(
        build_health_router(
            {
                "postgres": postgres_check(settings.postgres_dsn),
                "redis-streams": redis_check(settings.redis_streams_url),
            }
        )
    )
    return app


def app_factory() -> FastAPI:
    """Uvicorn entry point: `uvicorn asset.main:app_factory --factory`."""
    return create_app(Settings())
