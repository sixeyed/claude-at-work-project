"""Migration 0002: unique display names (gh-5, issue Req 4).

Each test gets a database of its own, migrated to `0001` — before names had to be
unique — seeded with the duplicates the issue describes, and then taken to head.
The migration is a one-way data change, so what it did to each row is what these
tests read back: the name, the comparison key, and whether `version` moved.

The database is made by a synchronous fixture because `service_database` runs the
migration with `asyncio.run`, which cannot be called from inside an `async def` test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from auth.migrations import upgrade_to
from testkit.databases import PostgresServer, service_database

ACUTE = chr(0x0301)
JOSE = "Jos\xe9"
JOSE_DECOMPOSED = "Jose" + ACUTE
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def db_at_0001(postgres_server: PostgresServer) -> str:
    """A fresh database at revision 0001, named for this test alone."""
    return service_database(
        postgres_server,
        f"auth_m_{uuid.uuid4().hex[:8]}",
        lambda dsn: upgrade_to(dsn, "0001"),
    )


async def seed(dsn: str, rows: list[tuple[str, int]], **options: Any) -> list[str]:
    """Insert users `(display_name, minutes after T0)`; return their emails, in order.

    `deleted` is a set of indexes to soft-delete; `version` the starting version.
    """
    deleted: set[int] = options.get("deleted", set())
    version: int = options.get("version", 0)
    engine = create_async_engine(dsn)
    emails = []
    try:
        async with engine.begin() as connection:
            for index, (name, age) in enumerate(rows):
                email = f"user{index}@example.com"
                emails.append(email)
                await connection.execute(
                    text(
                        "INSERT INTO users (id, email, display_name, created_at, deleted_at, "
                        "version) VALUES (:id, :email, :name, :created, :deleted, :version)"
                    ),
                    {
                        "id": uuid.UUID(int=index + 1),
                        "email": email,
                        "name": name,
                        "created": T0 + timedelta(minutes=age),
                        "deleted": T0 + timedelta(days=1) if index in deleted else None,
                        "version": version,
                    },
                )
    finally:
        await engine.dispose()
    return emails


async def read(dsn: str) -> dict[str, dict[str, Any]]:
    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT email, display_name, display_name_key, version FROM users")
            )
            return {row["email"]: dict(row) for row in result.mappings()}
    finally:
        await engine.dispose()


async def test_the_migration_normalises_names_and_renames_duplicates(db_at_0001: str) -> None:
    """The oldest holder keeps a name, a deleted account counts, and NFC comes first."""
    emails = await seed(
        db_at_0001,
        [("Sam", 0), (" sam", 1), ("SAM", 2), (JOSE_DECOMPOSED, 3), (JOSE, 4)],
        deleted={0},
    )

    await upgrade_to(db_at_0001, "head")

    users = await read(db_at_0001)
    assert [users[e]["display_name"] for e in emails] == [
        "Sam",
        "sam 2",
        "SAM 3",
        JOSE,
        JOSE + " 2",
    ]
    assert [users[e]["display_name_key"] for e in emails] == [
        "sam",
        "sam 2",
        "sam 3",
        "jos\xe9",
        "jos\xe9 2",
    ]


async def test_the_migration_leaves_a_newer_unique_name_alone(db_at_0001: str) -> None:
    """A name that was never a duplicate is not renamed to make room (Decision 17a)."""
    emails = await seed(db_at_0001, [("Sam", 0), ("sam", 1), ("Sam 2", 2)], version=4)

    await upgrade_to(db_at_0001, "head")

    users = await read(db_at_0001)
    assert [users[e]["display_name"] for e in emails] == ["Sam", "sam 3", "Sam 2"]
    assert users[emails[2]]["version"] == 4
    assert users[emails[0]]["version"] == 4
    assert users[emails[1]]["version"] == 5


async def test_only_renamed_rows_get_a_new_version(db_at_0001: str) -> None:
    emails = await seed(
        db_at_0001,
        [("Plain", 0), ("  Padded ", 1), ("Dup", 2), ("dup", 3), (JOSE_DECOMPOSED, 4)],
        version=7,
    )

    await upgrade_to(db_at_0001, "head")

    users = await read(db_at_0001)
    assert {e: users[e]["version"] for e in emails} == {
        emails[0]: 7,  # unchanged
        emails[1]: 8,  # trimmed
        emails[2]: 7,  # the oldest "Dup" keeps its name
        emails[3]: 8,  # renamed "dup 2"
        emails[4]: 8,  # recomposed
    }
    assert users[emails[1]]["display_name"] == "Padded"
    assert users[emails[3]]["display_name"] == "dup 2"
    assert users[emails[4]]["display_name"] == JOSE


async def test_after_the_migration_a_duplicate_is_refused(db_at_0001: str) -> None:
    """The index exists and compares on the key."""
    await seed(db_at_0001, [("Sam", 0)])
    await upgrade_to(db_at_0001, "head")

    engine = create_async_engine(db_at_0001)
    try:
        with pytest.raises(IntegrityError, match="uq_users_display_name_key"):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO users (id, email, display_name, display_name_key) "
                        "VALUES (:id, 'other@example.com', 'SAM', 'sam')"
                    ),
                    {"id": uuid.uuid4()},
                )
    finally:
        await engine.dispose()


async def test_the_migration_creates_the_preferences_table(db_at_0001: str) -> None:
    await upgrade_to(db_at_0001, "head")

    engine = create_async_engine(db_at_0001)
    try:
        async with engine.connect() as connection:
            columns = await connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'user_preferences'"
                )
            )
            assert {row[0] for row in columns} >= {"user_id", "prefs", "version", "updated_at"}
    finally:
        await engine.dispose()
