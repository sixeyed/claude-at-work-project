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
    # Not created until the features that need them (slice 3, and reactions
    # later still) — an empty table claims the service does something it cannot.
    assert "messages" not in names
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
