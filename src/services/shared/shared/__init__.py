"""Cross-cutting helpers shared by every CollabHub backend service.

Scaffold scope: health endpoints only. The rest of what this package is meant to
own — RFC 7807 Problem Details handlers, `require_user` / `require_service`,
JWKS caching, the token denylist, cursor pagination, UUID v7, the job envelope,
the `ObjectStore` protocol, structlog + OpenTelemetry setup — is deliberately
not here yet. See docs/design/00-platform-conventions.md.
"""

from shared.health import HealthCheck, build_health_router, http_check, postgres_check, redis_check

__all__ = [
    "HealthCheck",
    "build_health_router",
    "http_check",
    "postgres_check",
    "redis_check",
]
