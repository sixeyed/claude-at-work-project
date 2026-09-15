"""Auth's test configuration — the values its integration tests build the app with.

Here rather than in Auth's conftest because test modules import these by name,
and a conftest cannot be imported unambiguously: every service's `tests`
directory is the same namespace package.
"""

from __future__ import annotations

from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from auth.settings import Settings
from testkit.dex import DEX_CLIENT_ID, DEX_CLIENT_SECRET

# The issuer this service is configured with in tests, and the redirect URI Dex
# has registered — it has to match what the app builds from `auth_issuer`.
AUTH_ISSUER = "http://localhost:8001"

DEMO_WORKSPACE = "CollabHub Demo"
SPA_REDIRECT = "http://localhost:5173/auth/callback"
WORKER_SECRET = "worker-local-secret"

# Outside `local` the service refuses to invent a signing key, so any test that
# builds an app as if deployed has to supply one. Generated once per session —
# RSA keygen is slow enough to notice if every test did it.
A_SIGNING_KEY = (
    rsa.generate_private_key(public_exponent=65537, key_size=2048)
    .private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    .decode()
)


def build_settings(
    postgres_dsn: str, redis_url: str, dex_issuer: str, **overrides: Any
) -> Settings:
    """Public and internal authority are the same value here: the test process
    reaches Dex at the URL Dex calls itself, so there is nothing to translate.
    The split they exist for is unit-tested in test_oidc.py, which needs no
    container to prove a URL is rewritten.
    """
    values: dict[str, Any] = {
        "app_env": "local",
        "postgres_dsn": postgres_dsn,
        "redis_cache_url": redis_url,
        "auth_issuer": AUTH_ISSUER,
        "spa_redirect_uri": SPA_REDIRECT,
        "auth_demo_workspace_name": DEMO_WORKSPACE,
        "auth_service_clients": [
            {"client_id": "worker", "secret": WORKER_SECRET, "scopes": ["assets:write-variants"]}
        ],
        "oidc_providers": [
            {
                "name": "dex",
                "authority": dex_issuer,
                "internalAuthority": dex_issuer,
                "clientId": DEX_CLIENT_ID,
                "clientSecret": DEX_CLIENT_SECRET,
            }
        ],
    }
    values.update(overrides)
    return Settings(**values)
