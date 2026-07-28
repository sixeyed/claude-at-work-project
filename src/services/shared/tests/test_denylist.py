"""The token denylist in Redis Cache R1 (Conventions §5.2).

Stateless verification cannot revoke a token before it expires, so logout writes
the token's `jti` here and every service checks it. The interesting case is the
one where R1 is *unreachable*: the denylist reports UNKNOWN rather than guessing,
because the fail-open/fail-closed choice belongs to the caller — ordinary
requests proceed, sensitive operations refuse.
"""

import pytest
import redis.asyncio as aioredis

from shared import Denylist, TokenState

pytestmark = pytest.mark.integration


async def test_an_untouched_token_is_active(redis_client: aioredis.Redis) -> None:
    denylist = Denylist(redis_client)

    assert await denylist.state("never-seen") is TokenState.ACTIVE


async def test_a_revoked_token_reports_revoked(redis_client: aioredis.Redis) -> None:
    denylist = Denylist(redis_client)

    await denylist.revoke("jti-1", ttl_seconds=60)

    assert await denylist.state("jti-1") is TokenState.REVOKED


async def test_revocation_expires_with_the_token(redis_client: aioredis.Redis) -> None:
    """The entry only has to outlive the token it revokes, or R1 grows forever."""
    denylist = Denylist(redis_client)

    await denylist.revoke("jti-1", ttl_seconds=42)

    assert 0 < await redis_client.ttl("auth:revoked:jti-1") <= 42


async def test_revoking_an_already_expired_token_is_a_no_op(redis_client: aioredis.Redis) -> None:
    denylist = Denylist(redis_client)

    await denylist.revoke("jti-1", ttl_seconds=0)

    assert await denylist.state("jti-1") is TokenState.ACTIVE


async def test_an_unreachable_redis_reports_unknown_rather_than_raising() -> None:
    unreachable = aioredis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.05)
    denylist = Denylist(unreachable)

    assert await denylist.state("jti-1") is TokenState.UNKNOWN

    await unreachable.aclose()
