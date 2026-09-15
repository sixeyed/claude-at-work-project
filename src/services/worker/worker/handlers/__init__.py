"""Handlers by stream, then by job type.

A stream in `WORKER_STREAMS` with no entry here is a configuration error the
Worker refuses to start with — consuming a stream it cannot handle would
dead-letter every job on it.
"""

from __future__ import annotations

from elasticsearch import AsyncElasticsearch

from contracts import JOBS_INDEX
from worker.consumer import Handler
from worker.handlers.messages import build_message_handlers


def build_handlers(es: AsyncElasticsearch) -> dict[str, dict[str, Handler]]:
    return {JOBS_INDEX: build_message_handlers(es)}
