"""The migration produces the schema the models and the design doc describe.

Cheap to write and it catches the failure mode that hurts most: a model edited
without its migration, which passes every test that goes through SQLAlchemy and
then fails on a real deployment.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def _rows(engine, sql: str, **params) -> list[tuple]:
    async with engine.connect() as connection:
        result = await connection.execute(text(sql), params)
        return list(result.all())


async def test_the_expected_tables_exist(engine):
    rows = await _rows(
        engine,
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename",
    )
    names = [r[0] for r in rows]

    assert "channels" in names
    assert "channel_members" in names
    assert "messages" in names
    # Still not created. An empty table claims the service does something it
    # cannot, and nothing in this scope reads or writes a reaction.
    assert "reactions" not in names


async def test_timestamps_are_timestamptz(engine):
    rows = await _rows(
        engine,
        """
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_name = 'channels'
          AND column_name IN ('created_at', 'updated_at', 'archived_at')
        """,
    )

    assert dict(rows) == {
        "created_at": "timestamp with time zone",
        "updated_at": "timestamp with time zone",
        "archived_at": "timestamp with time zone",
    }


async def test_channels_soft_delete_with_archived_at_not_deleted_at(engine):
    rows = await _rows(
        engine,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'channels'",
    )
    names = {r[0] for r in rows}

    assert "archived_at" in names
    assert "deleted_at" not in names


async def test_the_public_name_index_is_partial_and_case_folded(engine):
    rows = await _rows(
        engine,
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'ux_channels_public_name'",
    )

    assert len(rows) == 1
    # Postgres re-renders the expression with its casts — `lower((name)::text)`
    # rather than `lower(name)` — so match the parts, not the spelling.
    definition = rows[0][0]
    assert "UNIQUE" in definition
    assert "lower(" in definition
    assert "WHERE" in definition
    assert "'public'" in definition


async def test_the_indexes_the_sidebar_needs_exist(engine):
    rows = await _rows(
        engine,
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'",
    )
    names = {r[0] for r in rows}

    assert "ix_channel_members_user" in names
    assert "ix_channels_workspace_name" in names


async def test_cross_service_ids_carry_no_foreign_keys(engine):
    """`workspace_id` and `created_by` name rows in another service's database."""
    rows = await _rows(
        engine,
        """
        SELECT conname, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE contype = 'f' AND conrelid::regclass::text IN ('channels', 'channel_members')
        """,
    )
    definitions = " ".join(d for _, d in rows)

    assert "workspace_id" not in definitions
    assert "created_by" not in definitions
    assert "user_id" not in definitions
    # The one foreign key that is allowed: both ends are ours.
    assert "REFERENCES channels(id)" in definitions


async def test_message_timestamps_are_timestamptz(engine):
    rows = await _rows(
        engine,
        """
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_name = 'messages'
          AND column_name IN ('created_at', 'edited_at', 'deleted_at')
        """,
    )

    assert dict(rows) == {
        "created_at": "timestamp with time zone",
        "edited_at": "timestamp with time zone",
        "deleted_at": "timestamp with time zone",
    }


async def test_the_history_index_is_not_partial(engine):
    """The read path returns tombstones, so it has no `deleted_at` clause.

    A partial index with `WHERE deleted_at IS NULL` would silently not be used
    by the query it was created for — the failure mode is a full scan on a busy
    channel, which no test that only checks results would ever catch.
    """
    rows = await _rows(
        engine,
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_messages_channel_time'",
    )

    assert len(rows) == 1
    definition = rows[0][0]
    assert "channel_id" in definition
    assert "DESC" in definition
    assert "WHERE" not in definition


async def test_the_thread_index_is_deliberately_absent(engine):
    """`ix_messages_thread` is in the design doc and is not built yet.

    Nothing queries `thread_root_id`. Unlike a column, an index can be added
    later with no table rewrite — so it waits for the feature.
    """
    rows = await _rows(engine, "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
    names = {r[0] for r in rows}

    assert "ix_messages_channel_time" in names
    assert "ix_messages_thread" not in names


async def test_a_message_references_its_channel_but_not_its_author(engine):
    """The Conventions §2 service boundary, drawn in DDL.

    A channel is this service's row and gets a real foreign key. An author is a
    row in Auth's database and gets none.
    """
    rows = await _rows(
        engine,
        """
        SELECT pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE contype = 'f' AND conrelid::regclass::text = 'messages'
        """,
    )
    definitions = " ".join(d for (d,) in rows)

    assert "REFERENCES channels(id)" in definitions
    assert "author_id" not in definitions
