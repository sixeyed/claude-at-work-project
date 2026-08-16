"""Cross-cutting helpers shared by every CollabHub backend service.

What lives here is the platform's shared contract, implemented once so five
services cannot drift: RFC 7807 Problem Details, UUID v7 keys, JWKS-backed token
verification with `require_user` / `require_service`, the Redis token denylist,
and the health router.

Still to arrive with the services that need them: the job envelope, the
`ObjectStore` protocol, and structlog + OpenTelemetry setup.
See docs/design/00-platform-conventions.md.
"""

from shared.cors import install_cors
from shared.denylist import Denylist, TokenState
from shared.health import HealthCheck, build_health_router, http_check, postgres_check, redis_check
from shared.ids import uuid7
from shared.keys import JwksClient, KeySource, StaticKeySource, UnknownKeyError, jwks_document
from shared.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    Page,
    PageParams,
    PageRequest,
    build_page,
    decode_cursor,
    encode_cursor,
    page_request,
)
from shared.problems import (
    PROBLEM_MEDIA_TYPE,
    ProblemException,
    install_problem_handlers,
    problem_body,
    problem_response,
    trace_id,
)
from shared.security import (
    SecurityConfig,
    SecurityContext,
    ServicePrincipal,
    UserPrincipal,
    install_security,
    require_service,
    require_user,
    require_user_sensitive,
    verify_user_token,
)

__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "PROBLEM_MEDIA_TYPE",
    "Denylist",
    "HealthCheck",
    "JwksClient",
    "KeySource",
    "Page",
    "PageParams",
    "PageRequest",
    "ProblemException",
    "SecurityConfig",
    "SecurityContext",
    "ServicePrincipal",
    "StaticKeySource",
    "TokenState",
    "UnknownKeyError",
    "UserPrincipal",
    "build_health_router",
    "build_page",
    "decode_cursor",
    "encode_cursor",
    "http_check",
    "install_cors",
    "install_problem_handlers",
    "install_security",
    "jwks_document",
    "page_request",
    "postgres_check",
    "problem_body",
    "problem_response",
    "redis_check",
    "require_service",
    "require_user",
    "require_user_sensitive",
    "trace_id",
    "uuid7",
    "verify_user_token",
]
