"""Real Postgres, Redis and Dex for the Auth service's integration tests.

One container of each per test session (Conventions §11 — testcontainers, not
mocks). Every test gets a clean database: rather than re-running migrations,
which is slow, the tables are truncated between tests.

**Dex is real too.** Sign-in is the one thing this service exists to do, and a
stubbed identity provider would test our idea of OIDC rather than OIDC. The
tests drive the actual redirect flow, through the actual login form, against the
image the compose stack runs.

Dex is bound to a *fixed* host port rather than a random one, because an OIDC
issuer is baked into its configuration: the URL in `issuer` is what Dex puts in
`iss` and what the relying party checks against, so it cannot be discovered
after the container starts. The port is deliberately not 5556, so a running
`docker compose up` and a test run do not fight over it.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import redis.asyncio as aioredis
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer
from testcontainers.core.container import DockerContainer

from auth.main import create_app
from auth.migrations import upgrade_to_head
from auth.settings import Settings

TABLES = "refresh_tokens, external_identities, workspace_members, workspaces, users"

# Kept in step with docs/platform/versions.md.
DEX_IMAGE = "ghcr.io/dexidp/dex:v2.45.1"
DEX_PORT = 15556

# The issuer this service is configured with in tests, and the redirect URI Dex
# has registered — it has to match what the app builds from `auth_issuer`.
AUTH_ISSUER = "http://localhost:8001"
DEX_CLIENT_ID = "collabhub-auth"
DEX_CLIENT_SECRET = "test-client-secret"

# bcrypt of DEX_PASSWORD. Generated once and pinned rather than hashed at test
# setup, because bcrypt at cost 10 is deliberately slow and this is not what is
# being tested.
DEX_PASSWORD = "collabhub"
DEX_PASSWORD_HASH = "$2b$10$AjNda/ZYuDZgz2nQA9lAPOb3Y.uGW4xYCWXG8wTfnyb9KjviceU/S"

ADA = "ada@collabhub.dev"
GRACE = "grace@collabhub.dev"
ALAN = "alan@collabhub.dev"

# Dex sends `name` as the username, so this is the display name a first sign-in
# provisions the account with — and what its own workspace gets named after.
ADA_NAME = "ada"
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

DEX_CONFIG = """
issuer: http://localhost:{port}/dex
storage:
  type: memory
web:
  http: 0.0.0.0:5556
oauth2:
  responseTypes: ["code"]
  skipApprovalScreen: true
staticClients:
  - id: {client_id}
    name: CollabHub
    secret: {client_secret}
    redirectURIs:
      - {issuer}/api/v1/auth/callback/dex
enablePasswordDB: true
staticPasswords:
  - email: {ada}
    username: ada
    userID: 6f9619ff-8b86-d011-b42d-00c04fc964ff
    hashFromEnv: DEX_PASSWORD_HASH
  - email: {grace}
    username: grace
    userID: 7a9619ff-8b86-d011-b42d-00c04fc964ff
    hashFromEnv: DEX_PASSWORD_HASH
  - email: {alan}
    username: alan
    userID: 8b9619ff-8b86-d011-b42d-00c04fc964ff
    hashFromEnv: DEX_PASSWORD_HASH
"""


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    with PostgresContainer("postgres:18", driver="asyncpg") as container:
        dsn = container.get_connection_url()
        asyncio.run(upgrade_to_head(dsn))
        yield dsn


@pytest.fixture(scope="session")
def dex_issuer(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """A real Dex, configured for three local accounts. Yields its issuer URL.

    The config is generated here rather than reusing `docker/dex/config.yaml`
    so the tests do not depend on the compose stack's port being free, and so a
    change to local developer convenience cannot silently change what is tested.
    """
    config: Path = tmp_path_factory.mktemp("dex") / "config.yaml"
    config.write_text(
        DEX_CONFIG.format(
            port=DEX_PORT,
            issuer=AUTH_ISSUER,
            client_id=DEX_CLIENT_ID,
            client_secret=DEX_CLIENT_SECRET,
            ada=ADA,
            grace=GRACE,
            alan=ALAN,
        )
    )
    # Dex reads the config as the non-root user it runs as.
    config.chmod(0o644)

    container = (
        DockerContainer(DEX_IMAGE)
        .with_command("dex serve /etc/dex/config.yaml")
        .with_volume_mapping(str(config), "/etc/dex/config.yaml", "ro")
        .with_env("DEX_PASSWORD_HASH", DEX_PASSWORD_HASH)
        .with_bind_ports(5556, DEX_PORT)
    )

    with container:
        issuer = f"http://localhost:{DEX_PORT}/dex"
        _await_discovery(issuer, container)
        yield issuer


def _await_discovery(issuer: str, container: DockerContainer) -> None:
    """Block until Dex serves its discovery document.

    Polling the endpoint the tests actually use, rather than waiting on a log
    line, means readiness means "answers OIDC" and not "printed something".
    """
    deadline = 30
    for _ in range(deadline * 4):
        try:
            response = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=1.0)
            if response.status_code == httpx.codes.OK:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)

    raise RuntimeError(f"Dex did not become ready within {deadline}s:\n{container.get_logs()}")


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:8") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        yield f"redis://{host}:{port}/0"


@pytest.fixture
async def engine(postgres_dsn: str) -> AsyncIterator:
    engine = create_async_engine(postgres_dsn)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def sessions(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def app_settings(postgres_dsn: str, redis_url: str, dex_issuer: str) -> Settings:
    """The settings every integration test builds its app from.

    Public and internal authority are the same value here: the test process
    reaches Dex at the URL Dex calls itself, so there is nothing to translate.
    The split they exist for is unit-tested in test_oidc.py, which needs no
    container to prove a URL is rewritten.
    """
    return build_settings(postgres_dsn, redis_url, dex_issuer)


def build_settings(
    postgres_dsn: str, redis_url: str, dex_issuer: str, **overrides: Any
) -> Settings:
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


@pytest.fixture
async def client(app_settings: Settings, engine) -> AsyncIterator[httpx.AsyncClient]:
    """The Auth app on an ASGI transport, against the real containers."""
    app = create_app(app_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncIterator[aioredis.Redis]:
    client = aioredis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()
