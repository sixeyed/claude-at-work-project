"""Auth service entry point.

Scaffold scope: the process starts, reads its config and answers health probes.
The endpoints in docs/design/01-auth-service.md §3 — JWKS, the token and refresh
endpoints, workspace membership — are not implemented yet.
"""

from fastapi import FastAPI

from auth.settings import Settings
from shared import build_health_router, postgres_check, redis_check


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="CollabHub Auth", version="0.1.0")
    app.include_router(
        build_health_router(
            {
                "postgres": postgres_check(settings.postgres_dsn),
                "redis-cache": redis_check(settings.redis_cache_url),
            }
        )
    )
    return app


def app_factory() -> FastAPI:
    """Uvicorn entry point: `uvicorn auth.main:app_factory --factory`.

    Config is read here rather than at import time so tests can build an app
    without the environment being set up.
    """
    return create_app(Settings())
