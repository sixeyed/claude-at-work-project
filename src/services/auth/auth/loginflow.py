"""The two short-lived, single-use keys a login turns on, held in R1.

A federated sign-in is two round trips through the browser, and each leg needs
something remembered across it:

* **`auth:login:{state}`** — written when we send the user to the provider, read
  when they come back. Carries the nonce and our own PKCE verifier (so the
  callback can finish the exchange) and the SPA's code challenge (so it can be
  handed to the code that gets issued).
* **`auth:code:{code}`** — written when identity is established, read when the
  SPA exchanges it for tokens. Carries the user, the workspace, and the SPA's
  challenge.

Both are **single-use**: read is `GETDEL`, so the second read of a key finds
nothing. That is what makes a replayed `state` or a captured authorization code
worthless rather than a second session. Doing it in one command rather than
`GET` then `DEL` matters — two commands leave a window in which two concurrent
redemptions both succeed.

Both **fail closed**. This is the deliberate opposite of the token denylist,
which fails open when R1 is unreachable (Conventions §5.2). The reasoning
there — short-lived tokens make availability worth more than certainty — does
not transfer: failing open here would mean issuing a session for an
authorization code nobody can show was ever issued. A login that errors is a
login the user retries.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import asdict, dataclass
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from auth import pkce

LOGIN_KEY_PREFIX = "auth:login:"
CODE_KEY_PREFIX = "auth:code:"
HANDLE_BYTES = 32


class LoginStoreUnavailableError(Exception):
    """R1 could not be reached, so this login cannot be trusted either way."""


@dataclass(frozen=True)
class PendingLogin:
    """What the outbound leg of a login has to remember about itself."""

    provider: str
    nonce: str
    verifier: str  # ours, for the exchange with the provider
    code_challenge: str  # the SPA's, to carry onto the authorization code


@dataclass(frozen=True)
class AuthorizationCode:
    """An established identity, waiting for the SPA to collect it."""

    user_id: str
    workspace_id: str
    code_challenge: str


def _handle() -> str:
    """An opaque, unguessable value for a `state` or a code."""
    return secrets.token_urlsafe(HANDLE_BYTES)


class LoginFlowStore:
    """R1-backed storage for both halves of a login."""

    def __init__(
        self, redis_client: aioredis.Redis, *, state_ttl_seconds: int, code_ttl_seconds: int
    ) -> None:
        self._redis = redis_client
        self._state_ttl = state_ttl_seconds
        self._code_ttl = code_ttl_seconds

    async def _put(self, key: str, value: dict[str, Any], ttl: int) -> None:
        try:
            await self._redis.set(key, json.dumps(value), ex=ttl)
        except RedisError as exc:
            raise LoginStoreUnavailableError(str(exc)) from exc

    async def _take(self, key: str) -> dict[str, Any] | None:
        """Read and delete in one command — the read *is* the consumption."""
        try:
            raw = await self._redis.getdel(key)
        except RedisError as exc:
            raise LoginStoreUnavailableError(str(exc)) from exc

        if raw is None:
            return None
        try:
            return json.loads(raw)
        except ValueError:  # pragma: no cover — only we ever write these
            return None

    async def begin_login(self, *, provider: str, code_challenge: str) -> tuple[str, PendingLogin]:
        """Open a login, returning the `state` to send and what it stands for."""
        pending = PendingLogin(
            provider=provider,
            nonce=_handle(),
            verifier=pkce.new_verifier(),
            code_challenge=code_challenge,
        )
        state = _handle()
        await self._put(LOGIN_KEY_PREFIX + state, asdict(pending), self._state_ttl)
        return state, pending

    async def claim_login(self, state: str) -> PendingLogin | None:
        """Consume a `state`. A second attempt with the same one gets None."""
        stored = await self._take(LOGIN_KEY_PREFIX + state)
        return PendingLogin(**stored) if stored else None

    async def issue_code(
        self, *, user_id: uuid.UUID, workspace_id: uuid.UUID, code_challenge: str
    ) -> str:
        """Mint the authorization code the SPA will exchange for tokens."""
        code = _handle()
        await self._put(
            CODE_KEY_PREFIX + code,
            asdict(
                AuthorizationCode(
                    user_id=str(user_id),
                    workspace_id=str(workspace_id),
                    code_challenge=code_challenge,
                )
            ),
            self._code_ttl,
        )
        return code

    async def claim_code(self, code: str) -> AuthorizationCode | None:
        """Consume an authorization code. Replays get None."""
        stored = await self._take(CODE_KEY_PREFIX + code)
        return AuthorizationCode(**stored) if stored else None
