"""Driving a service at its boundary, in-process.

Two ways, for two kinds of boundary:

- `asgi_client(app)` — REST over `httpx.ASGITransport`. No socket, no server,
  no lifespan: the fastest way to call a FastAPI app for real.
- `serve(app)` — a real uvicorn on an ephemeral port, for anything
  `ASGITransport` cannot carry. **It cannot carry a WebSocket**, so Socket.IO
  tests need a listening server; and once a test has one, its REST calls should
  go through it too, because an app built for the transport may be missing what
  the served one wires in (Messaging's `app.state.realtime` is `None` under
  `create_app`, so a REST write through that publishes nothing).

`serve` runs with `lifespan="on"` on purpose. `socketio.ASGIApp` handles the
lifespan scope itself and only delegates it down when it was built without
startup hooks, so serving with the lifespan on is also what proves the wrapped
app's own lifespan — engine and Redis disposal — still runs underneath.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

#: How long `serve` waits for uvicorn to bind: 500 polls of 20 ms.
_START_POLLS = 500
_START_POLL_SECONDS = 0.02


@asynccontextmanager
async def asgi_client(
    app: Any, *, base_url: str = "http://test"
) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        yield client


@asynccontextmanager
async def serve(app: Any) -> AsyncIterator[str]:
    """Serve `app` on 127.0.0.1 and an ephemeral port; yield its base URL."""
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.get_running_loop().create_task(server.serve())
    try:
        # `uvicorn.Server` exposes readiness as a plain bool it flips inside
        # `serve()`, with no event to await — so polling it is the only
        # handshake available. Bounded, so a server that never binds fails here
        # rather than hanging the suite.
        for _ in range(_START_POLLS):
            if server.started or task.done():
                break
            await asyncio.sleep(_START_POLL_SECONDS)
        if not server.started:
            raise AssertionError("the server did not start")
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task
