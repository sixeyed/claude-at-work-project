"""Recorders for the things CollabHub owns at its edges — the unit layer only.

A recorder stands in for an object of ours whose only job in the code under test
is to be *told* something: a Socket.IO server that emits, a job queue that
enqueues. It records the whole call and does nothing else, so a test asserts on
exactly what was sent.

What never belongs here is a fake database session, a fake Redis or a fake
repository (register D32). Those would be a second implementation of every
query, and a test against one only tests the fake.
"""

from __future__ import annotations

from typing import Any


class RecordingServer:
    """Stands in for `socketio.AsyncServer` where only `emit` is called.

    Records the whole call — event, payload and every keyword — so an emit to
    the wrong room, namespace or sid fails the assertion rather than passing it.
    """

    def __init__(self) -> None:
        self.emits: list[tuple[str, Any, dict[str, Any]]] = []

    async def emit(self, event: str, data: Any = None, **kwargs: Any) -> None:
        self.emits.append((event, data, kwargs))


class RecordingJobQueue:
    """Stands in for `shared.JobQueue` where only `enqueue` is called.

    Records `(stream, job_type, payload)` with the payload model as given, so a
    contract test can validate what the producer built rather than what Redis
    would have stored. `fail_with` makes `enqueue` raise instead — how a test
    reaches the fire-and-forget path an unreachable R3 takes.
    """

    def __init__(self, *, fail_with: Exception | None = None) -> None:
        self.enqueued: list[tuple[str, str, Any]] = []
        self.fail_with = fail_with

    async def enqueue(self, stream: str, job_type: str, payload: Any) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.enqueued.append((stream, job_type, payload))
