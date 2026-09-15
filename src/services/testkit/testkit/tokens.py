"""Access tokens for integration tests, minted with a local key (Conventions §5).

A service verifies signatures against a JWKS it does not own, so the only thing
a real Auth would add to a test is a container and a slower suite. What matters
is that the token is a genuine RS256 JWT with the right claims, and a local key
gives that: the app under test is built with `tokens.key_source()`, which is the
same `StaticKeySource` path Auth itself uses.

Two kinds, split by audience, and neither satisfies the other's endpoints:

- **user tokens** — `aud=collabhub`, scoped to one workspace by `wsp`;
- **service tokens** — `aud=collabhub-internal`, `sub=service:<name>`, `scp`.

`signing_key` and `tokens` are fixtures registered by the testkit plugin, so
every service's tests share one key per session without a conftest import.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

if TYPE_CHECKING:
    from shared import StaticKeySource

ISSUER = "https://auth.test"
KEY_ID = "test-key"
USER_AUDIENCE = "collabhub"
INTERNAL_AUDIENCE = "collabhub-internal"

LIFETIME = timedelta(minutes=15)


class Tokens:
    """Mints user and service tokens signed by one key."""

    #: Stable for the session, so a test can name the people a token is for.
    ADA = uuid.uuid4()
    GRACE = uuid.uuid4()
    WORKSPACE = uuid.uuid4()
    OTHER_WORKSPACE = uuid.uuid4()

    def __init__(
        self, key: rsa.RSAPrivateKey, *, issuer: str = ISSUER, key_id: str = KEY_ID
    ) -> None:
        self._key = key
        self.issuer = issuer
        self.key_id = key_id

    def key_source(self) -> StaticKeySource:
        """What an app under test verifies these tokens with."""
        # Imported here, not at the top: this module loads with the plugin, before
        # pytest-cov starts, and an early `import shared` drops `shared` from the
        # unit coverage report ("previously imported, but not measured").
        from shared import StaticKeySource

        return StaticKeySource({self.key_id: self._key.public_key()})

    def encode(
        self,
        claims: dict[str, Any],
        *,
        kid: str | None = None,
        lifetime: timedelta = LIFETIME,
    ) -> str:
        """Sign `claims`, filling `iss`, `aud`, `iat`, `exp` and `jti` unless given.

        A claim whose value is `None` is left out, which is how a test builds a
        token that is *missing* something.
        """
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "iss": self.issuer,
            "aud": USER_AUDIENCE,
            "iat": now,
            "exp": now + lifetime,
            "jti": uuid.uuid4().hex,
        }
        payload.update(claims)
        payload = {name: value for name, value in payload.items() if value is not None}
        return jwt.encode(
            payload, self._key, algorithm="RS256", headers={"kid": kid or self.key_id}
        )

    def mint(
        self,
        *,
        user_id: uuid.UUID = ADA,
        workspace_id: uuid.UUID = WORKSPACE,
        name: str = "Ada Lovelace",
        email: str = "ada@collabhub.dev",
        roles: Iterable[str] = ("member",),
        lifetime: timedelta = LIFETIME,
        kid: str | None = None,
        **overrides: Any,
    ) -> str:
        """A user access token as Auth would issue it (Conventions §5.1)."""
        claims: dict[str, Any] = {
            "sub": str(user_id),
            "name": name,
            "email": email,
            "wsp": str(workspace_id),
            "roles": list(roles),
        }
        claims.update(overrides)
        return self.encode(claims, kid=kid, lifetime=lifetime)

    def service(
        self,
        name: str = "worker",
        *,
        scopes: Iterable[str] = ("assets:write-variants",),
        lifetime: timedelta = LIFETIME,
        **overrides: Any,
    ) -> str:
        """A service token for an internal endpoint (Conventions §5.5)."""
        claims: dict[str, Any] = {
            "aud": INTERNAL_AUDIENCE,
            "sub": f"service:{name}",
            "scp": list(scopes),
        }
        claims.update(overrides)
        return self.encode(claims, lifetime=lifetime)

    def header(self, **overrides: Any) -> dict[str, str]:
        """`Authorization` for a user token; takes `mint`'s arguments."""
        return {"Authorization": f"Bearer {self.mint(**overrides)}"}


@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    """One RSA key per session — keygen is slow enough to notice per test."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def tokens(signing_key: rsa.RSAPrivateKey) -> Tokens:
    return Tokens(signing_key)
