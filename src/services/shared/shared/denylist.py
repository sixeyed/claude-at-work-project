"""Token revocation via Redis Cache R1 (Conventions §5.2).

RS256 verification is stateless and therefore cannot know about a logout. The
Auth service writes revoked `jti`s here with a TTL equal to the token's
remaining life, and every service checks the list on each request.

The lookup returns three states, not a boolean. `UNKNOWN` — R1 is unreachable —
is a real answer with real consequences, and collapsing it into "not revoked"
would bake the fail-open decision into this module. It is the caller's to make:
ordinary requests accept the token, while workspace membership changes, role
grants and asset deletion refuse (see `require_user_sensitive`).
"""

from __future__ import annotations

import logging
from enum import Enum

import redis.asyncio as aioredis
from redis.exceptions import RedisError

KEY_PREFIX = "auth:revoked:"

_log = logging.getLogger("collabhub.denylist")


class TokenState(Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    UNKNOWN = "unknown"


class Denylist:
    """Reads and writes the revoked-token set in R1."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def state(self, token_id: str) -> TokenState:
        try:
            revoked = await self._redis.exists(KEY_PREFIX + token_id)
        except RedisError as exc:
            _log.warning("denylist unavailable", extra={"error": str(exc)})
            return TokenState.UNKNOWN

        return TokenState.REVOKED if revoked else TokenState.ACTIVE

    async def revoke(self, token_id: str, *, ttl_seconds: int) -> None:
        """Revoke a token until it would have expired anyway.

        A non-positive TTL means the token is already expired, so there is
        nothing to revoke — and `SETEX` would reject it.
        """
        if ttl_seconds <= 0:
            return

        await self._redis.set(KEY_PREFIX + token_id, "1", ex=ttl_seconds)
