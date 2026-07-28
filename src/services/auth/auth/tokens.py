"""Minting tokens (spec §3.1, Conventions §5.1 and §5.5).

Pure and I/O-free on purpose: nothing here touches Postgres or Redis, so the
claim shape and the expiry arithmetic — the parts every other service depends on
— can be tested without a database in sight. Persisting the refresh token and
checking the denylist belong to `sessions.py`.

Two kinds of token come out of here and they are deliberately hard to confuse:

* **Access tokens** — `aud: collabhub`, a user `sub`, exactly one `wsp`.
* **Service tokens** — `aud: collabhub-internal`, `sub: service:{name}`, `scp`
  scopes, and no workspace at all.

Refresh tokens are neither: they are opaque random strings, not JWTs, because
nothing should be able to read a claim out of one, and only their SHA-256 hash
is ever stored.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from auth.keys import SigningKeys
from shared import uuid7

REFRESH_TOKEN_BYTES = 32


@dataclass(frozen=True)
class IssuedToken:
    """A signed JWT with the bits callers need for the response envelope."""

    value: str
    token_id: str
    expires_at: datetime

    @property
    def expires_in(self) -> int:
        """Seconds until expiry, as the `expires_in` field of the token response."""
        return max(0, round((self.expires_at - datetime.now(UTC)).total_seconds()))


def new_refresh_token() -> str:
    """A fresh opaque refresh token — 256 bits of entropy, URL-safe."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> bytes:
    """What goes in the database. The token itself never does.

    Plain SHA-256 rather than a password hash: these are full-entropy random
    strings, so there is no dictionary to attack and lookup has to be a single
    indexed read on every refresh.
    """
    return hashlib.sha256(token.encode()).digest()


class TokenIssuer:
    """Signs the tokens this service issues."""

    def __init__(
        self,
        *,
        keys: SigningKeys,
        issuer: str,
        audience: str,
        internal_audience: str,
        access_token_minutes: int,
        service_token_minutes: int,
    ) -> None:
        self._keys = keys
        self._issuer = issuer
        self._audience = audience
        self._internal_audience = internal_audience
        self._access_token_minutes = access_token_minutes
        self._service_token_minutes = service_token_minutes

    def _sign(self, claims: dict[str, Any], *, audience: str, lifetime: timedelta) -> IssuedToken:
        issued_at = datetime.now(UTC)
        expires_at = issued_at + lifetime
        token_id = str(uuid7())

        payload = {
            **claims,
            "iss": self._issuer,
            "aud": audience,
            "iat": issued_at,
            "exp": expires_at,
            "jti": token_id,
        }
        value = jwt.encode(
            payload,
            self._keys.private_key,
            algorithm="RS256",
            headers={"kid": self._keys.active_kid},
        )
        return IssuedToken(value=value, token_id=token_id, expires_at=expires_at)

    def access_token(
        self,
        *,
        user_id: uuid.UUID,
        display_name: str,
        email: str,
        workspace_id: uuid.UUID,
        roles: Sequence[str],
    ) -> IssuedToken:
        """A user token, scoped to exactly one workspace (Conventions §5.4)."""
        return self._sign(
            {
                "sub": str(user_id),
                "name": display_name,
                "email": email,
                "wsp": str(workspace_id),
                "roles": list(roles),
            },
            audience=self._audience,
            lifetime=timedelta(minutes=self._access_token_minutes),
        )

    def service_token(self, *, client_id: str, scopes: Sequence[str]) -> IssuedToken:
        """A client-credentials token for `/api/v1/internal/` calls."""
        return self._sign(
            {"sub": f"service:{client_id}", "scp": list(scopes)},
            audience=self._internal_audience,
            lifetime=timedelta(minutes=self._service_token_minutes),
        )
