"""Fixtures for the Messaging integration tests.

Real Postgres and Redis in containers, not mocks (Conventions §11) — a keyset
cursor, a partial unique index and a case-folded collision are all things only a
real database can tell you the truth about.

Tokens are minted here rather than obtained from Auth. Messaging verifies
signatures against a JWKS it does not own, so the only thing a real Auth would
add to these tests is a second container and a slower suite; what matters is
that the token is a genuine RS256 JWT with the right claims, and a local key
gives that.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
import redis.asyncio as aioredis
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from messaging.main import create_app
from messaging.migrations import upgrade_to_head
from messaging.settings import Settings
from shared import StaticKeySource

AUTH_ISSUER = "https://auth.test"
AUDIENCE = "collabhub"
KEY_ID = "messaging-test-key"

#: Child tables first — `channel_members` references `channels`.
TABLES = "channel_members, channels"

ADA = uuid.uuid4()
GRACE = uuid.uuid4()
WORKSPACE = uuid.uuid4()
OTHER_WORKSPACE = uuid.uuid4()


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    with PostgresContainer("postgres:18", driver="asyncpg") as container:
        dsn = container.get_connection_url()
        asyncio.run(upgrade_to_head(dsn))
        yield dsn


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:8") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        yield f"redis://{host}:{port}/0"


@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
async def engine(postgres_dsn: str) -> AsyncIterator:
    engine = create_async_engine(postgres_dsn)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    yield engine
    await engine.dispose()


def build_settings(postgres_dsn: str, redis_url: str, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "local",
        "postgres_dsn": postgres_dsn,
        "redis_cache_url": redis_url,
        "redis_realtime_url": redis_url,
        "redis_streams_url": redis_url,
        "auth_issuer": AUTH_ISSUER,
        "auth_audience": AUDIENCE,
        "auth_jwks_url": "https://auth.test/.well-known/jwks.json",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
async def app_settings(postgres_dsn: str, redis_url: str) -> Settings:
    return build_settings(postgres_dsn, redis_url)


@pytest.fixture
async def client(
    app_settings: Settings, signing_key: rsa.RSAPrivateKey, engine
) -> AsyncIterator[httpx.AsyncClient]:
    """The Messaging app on an ASGI transport, against the real containers."""
    app = create_app(
        app_settings,
        key_source=StaticKeySource({KEY_ID: signing_key.public_key()}),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncIterator[aioredis.Redis]:
    client = aioredis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()


class Tokens:
    """Mints the access tokens these tests authenticate with.

    Reached through the `tokens` fixture rather than imported. Every service in
    this repo has a `tests` package, so `from tests.conftest import ...` binds
    to whichever one the importer found first — Auth's, when the whole suite
    runs. Fixtures have no such ambiguity.
    """

    ADA = ADA
    GRACE = GRACE
    WORKSPACE = WORKSPACE
    OTHER_WORKSPACE = OTHER_WORKSPACE

    def __init__(self, key: rsa.RSAPrivateKey) -> None:
        self._key = key

    def mint(
        self,
        *,
        user_id: uuid.UUID = ADA,
        workspace_id: uuid.UUID = WORKSPACE,
        name: str = "Ada Lovelace",
        email: str = "ada@collabhub.dev",
        roles: tuple[str, ...] = ("member",),
        lifetime: timedelta = timedelta(minutes=15),
        **overrides: Any,
    ) -> str:
        """A user access token as Auth would issue it (Conventions §5.1)."""
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "iss": AUTH_ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + lifetime,
            "jti": uuid.uuid4().hex,
            "sub": str(user_id),
            "name": name,
            "email": email,
            "wsp": str(workspace_id),
            "roles": list(roles),
        }
        payload.update(overrides)
        return jwt.encode(payload, self._key, algorithm="RS256", headers={"kid": KEY_ID})

    def header(self, **overrides: Any) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.mint(**overrides)}"}


@pytest.fixture
def tokens(signing_key: rsa.RSAPrivateKey) -> Tokens:
    return Tokens(signing_key)


@pytest.fixture
def ada(tokens: Tokens) -> dict[str, str]:
    return tokens.header()


@pytest.fixture
def grace(tokens: Tokens) -> dict[str, str]:
    return tokens.header(user_id=GRACE, name="Grace Hopper", email="grace@collabhub.dev")
