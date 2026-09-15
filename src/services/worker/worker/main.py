"""Worker entry point.

The Worker is headless (design doc 05 §2): a long-running asyncio process with
no business HTTP. It serves the health endpoints Kubernetes probes and, beside
them, one consumer task per stream in `WORKER_STREAMS`. `jobs:index` is the only
stream with handlers; `jobs:thumbnail`, `jobs:notify`, `jobs:export` and
`jobs:retention` are still unconsumed.

**Startup order.** Health first, so a probe can see *why* the Worker is not
ready; then the `messages` index is ensured, retrying until Elasticsearch
answers; then the consumers start. A job read before the index exists would
fail and be retried anyway, but waiting keeps the logs about the real cause.

**Shutdown drains.** SIGTERM stops Uvicorn, which sets `stop`; each consumer
finishes the entry in hand and returns. Anything unfinished is still pending in
Redis and is reclaimed by the next consumer (Conventions §10).

**A consumer that dies takes the process with it.** If the consume task raises,
the health server is told to exit — a Worker answering `/health/live` while
consuming nothing is the failure nobody notices.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import socket

import redis.asyncio as aioredis
import uvicorn
from elasticsearch import AsyncElasticsearch
from elasticsearch import ConnectionError as EsConnectionError
from fastapi import FastAPI

from shared import build_health_router, http_check, redis_check
from worker.consumer import ConsumerConfig, StreamConsumer
from worker.handlers import build_handlers
from worker.index import ensure_messages_index
from worker.settings import Settings

HEALTH_PORT = 8000
_INDEX_RETRY_SECONDS = 5.0
#: Comfortably above the consumer's 5 s block, so an idle stream is not an error.
_REDIS_SOCKET_TIMEOUT_SECONDS = 15.0

_log = logging.getLogger("collabhub.worker")


def create_health_app(settings: Settings) -> FastAPI:
    """The Worker's only HTTP surface."""
    app = FastAPI(title="CollabHub Worker (health)", version="0.1.0")
    app.include_router(
        build_health_router(
            {
                "redis-streams": redis_check(settings.redis_streams_url),
                "elasticsearch": http_check(settings.elasticsearch_url),
            }
        )
    )
    return app


async def _wait_for_index(es: AsyncElasticsearch, stop: asyncio.Event) -> bool:
    """Ensure the `messages` index, retrying until Elasticsearch answers or we stop."""
    while not stop.is_set():
        try:
            await ensure_messages_index(es)
        except EsConnectionError as exc:
            _log.warning(
                "elasticsearch not ready (%s); retrying in %ss",
                type(exc).__name__,
                _INDEX_RETRY_SECONDS,
            )
            await asyncio.sleep(_INDEX_RETRY_SECONDS)
        else:
            return True
    return False


async def run(settings: Settings) -> None:
    es = AsyncElasticsearch(settings.elasticsearch_url)
    # The socket timeout must outlast `XREADGROUP BLOCK` (`ConsumerConfig.block_ms`),
    # or every idle read ends in a TimeoutError instead of an empty reply.
    redis_client = aioredis.from_url(
        settings.redis_streams_url,
        decode_responses=True,
        socket_timeout=_REDIS_SOCKET_TIMEOUT_SECONDS,
    )
    registry = build_handlers(es)

    missing = [stream for stream in settings.streams if stream not in registry]
    if missing:
        await es.close()
        await redis_client.aclose()
        raise SystemExit(
            f"No handlers for WORKER_STREAMS entries: {', '.join(missing)}. "
            f"Built streams: {', '.join(sorted(registry))}."
        )

    config = ConsumerConfig(
        consumer=socket.gethostname(),
        batch_size=settings.worker_batch_size,
        visibility_timeout_seconds=settings.worker_visibility_timeout_seconds,
        max_attempts=settings.worker_max_attempts,
        dead_letter_maxlen=settings.worker_dead_letter_maxlen,
    )
    consumers = [
        StreamConsumer(redis_client, stream, registry[stream], config)
        for stream in settings.streams
    ]

    server = uvicorn.Server(
        uvicorn.Config(
            create_health_app(settings),
            # Binds all interfaces because the container is the boundary; what is
            # reachable is the pod's and the ingress's concern, not the process's.
            host="0.0.0.0",  # noqa: S104
            port=HEALTH_PORT,
            log_level=settings.log_level,
        )
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    # Uvicorn captures SIGTERM while serving and re-raises it after `serve()`
    # returns. With the default handler that re-raise would kill the process
    # before the drain below; with this one it only sets `stop`, again.
    def _on_signal(*_: object) -> None:
        loop.call_soon_threadsafe(stop.set)

    signal.signal(signal.SIGTERM, _on_signal)

    async def consume() -> None:
        if await _wait_for_index(es, stop):
            await asyncio.gather(*(consumer.run(stop) for consumer in consumers))

    consume_task = asyncio.create_task(consume())

    def _on_consume_done(task: asyncio.Task[None]) -> None:
        if not task.cancelled() and task.exception() is not None:
            _log.error("consumer task failed: %s", type(task.exception()).__name__)
            server.should_exit = True

    consume_task.add_done_callback(_on_consume_done)

    try:
        await server.serve()
    finally:
        stop.set()
        try:
            await consume_task
        finally:
            await es.close()
            await redis_client.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(Settings()))
