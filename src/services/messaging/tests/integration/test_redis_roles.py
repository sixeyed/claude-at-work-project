"""Each Redis role Messaging uses lands on its own index (Conventions §6, §7; D34).

Messaging is the one service using all three: R1 for the denylist, R2 for the
Socket.IO backplane, R3 for index jobs. The tests give each role its own index
on one Redis, so a role wired to the wrong URL shows up as a key — or a
connection — on the wrong index.

**R2 is checked by connection, not by message.** Pub/Sub channels belong to the
server rather than to a database index, so a backplane publishing through R1's
URL would still reach every subscriber. What can be seen is the index the
backplane's own connection selected, in `CLIENT LIST`.
"""

from __future__ import annotations

import asyncio

import httpx
import jwt
import socketio

from contracts import JOBS_INDEX
from shared import Denylist


async def test_index_jobs_go_to_the_streams_index(realtime_url, tokens, redis_cache, redis_streams):
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as http:
        channel = (await http.post("/api/v1/channels", json={"name": "general"})).json()
        sent = await http.post(f"/api/v1/channels/{channel['id']}/messages", json={"body": "hello"})
    assert sent.status_code == 201, sent.text

    assert await redis_streams.exists(JOBS_INDEX) == 1
    assert await redis_cache.exists(JOBS_INDEX) == 0


async def test_the_denylist_messaging_reads_is_the_cache_index(client, tokens, redis_cache):
    token = tokens.mint()
    jti = jwt.decode(token, options={"verify_signature": False})["jti"]
    await Denylist(redis_cache).revoke(jti, ttl_seconds=900)

    response = await client.get("/api/v1/channels", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_the_backplane_connects_on_the_realtime_index(realtime_url, tokens, redis_cache):
    ada = socketio.AsyncSimpleClient()
    await ada.connect(
        realtime_url,
        namespace="/messaging",
        auth={"token": tokens.mint()},
        transports=["websocket"],
    )

    # The manager subscribes in a background task; give it a moment.
    subscribers = []
    for _ in range(100):
        clients = await redis_cache.client_list()
        subscribers = [c for c in clients if int(c.get("sub", 0)) > 0]
        if subscribers:
            break
        await asyncio.sleep(0.05)
    await ada.disconnect()

    assert subscribers, "the Socket.IO backplane never subscribed"
    assert {c["db"] for c in subscribers} == {"1"}
