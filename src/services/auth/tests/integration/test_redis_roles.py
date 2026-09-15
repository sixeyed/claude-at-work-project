"""Auth's Redis keys land on R1's index (Conventions §6; D34).

Auth uses one role, R1 — the cache, holding the denylist and the short-lived
login-flow keys. The tests give each role its own index on one Redis, so a key
written through the wrong URL would show up on the wrong index.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from auth import pkce
from testkit.containers import RedisRole


async def test_a_login_in_progress_is_kept_on_the_cache_index(client, redis_server, redis_cache):
    started = await client.get(
        "/api/v1/auth/login/dex", params={"codeChallenge": pkce.challenge_for(pkce.new_verifier())}
    )
    assert started.status_code == 302, started.text

    assert await redis_cache.keys("auth:login:*")
    for role in (RedisRole.REALTIME, RedisRole.STREAMS):
        other = aioredis.from_url(redis_server.url(role), decode_responses=True)
        try:
            assert await other.keys("auth:*") == [], role
        finally:
            await other.aclose()
