"""Messaging's own unit-test fixtures.

A row factory is a fixture here rather than a function in `testkit`: a
`Message` is Messaging's model, and `testkit` depending on Messaging would
couple the shared harness to one service (CLAUDE.md — a service's own helpers
go through fixtures).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from messaging.models import Message
from shared import uuid7

AT = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)


@pytest.fixture
def a_message() -> Callable[..., Message]:
    """Build a `Message` with no session — SQLAlchemy models construct without one.

    Every column is set, so nothing depends on a server default the unit layer
    never runs. Override whichever fields the test is about.
    """

    def build(**overrides: Any) -> Message:
        values: dict[str, Any] = {
            "id": uuid7(),
            "channel_id": uuid.uuid4(),
            "author_id": uuid.uuid4(),
            "thread_root_id": None,
            "body": "hello",
            "attachments": [],
            "created_at": AT,
            "edited_at": None,
            "deleted_at": None,
            "version": 0,
        }
        return Message(**(values | overrides))

    return build
