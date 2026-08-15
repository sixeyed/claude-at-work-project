"""`python -m messaging.openapi` — print this service's OpenAPI document.

The SPA generates its types and its REST client from this (register D23), so the
schema has to be obtainable without a database, a Redis or a running container:
a developer regenerating types should not need `docker compose up` first, and
neither should CI.

That is why it builds the app from placeholder settings. `create_app` only
*describes* its dependencies at import time — the engine is lazy and nothing
connects until a request arrives — so a document produced this way is identical
to one served from a live process.
"""

from __future__ import annotations

import json

from messaging.main import create_app
from messaging.settings import Settings

#: Syntactically valid and deliberately unreachable. Nothing dials them.
_PLACEHOLDERS = {
    "postgres_dsn": "postgresql+asyncpg://openapi/openapi",
    "redis_cache_url": "redis://openapi/0",
    "redis_realtime_url": "redis://openapi/0",
    "redis_streams_url": "redis://openapi/0",
    "auth_issuer": "https://auth.invalid",
    "auth_jwks_url": "https://auth.invalid/.well-known/jwks.json",
}


def document() -> dict:
    return create_app(Settings(**_PLACEHOLDERS)).openapi()


def main() -> None:
    print(json.dumps(document(), indent=2, sort_keys=True))  # noqa: T201 — this is the output


if __name__ == "__main__":
    main()
