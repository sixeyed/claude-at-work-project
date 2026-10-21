"""Unique display names, and per-user preferences (gh-5, register D46 and D28).

In order: add `users.display_name_key` as nullable; read every user — deleted
accounts included, because a deleted account's name stays taken (D46) — normalise
each name and rename the duplicates; set the key on every row; then make the key
not-null and unique; then create `user_preferences`.

This migration imports `auth.names` rather than copying it, because the issue
requires the rules that decide a rename and the rules that clean existing data to
be the same code. The cost: a later edit to `names.py` changes what a *fresh* run
of this migration does. A database already past 0002 is unaffected.

The renames are one-way. Downgrade drops the table, the index and the column and
leaves the names as they are now.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from auth import names

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMPTZ = TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name_key", sa.String(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, created_at, display_name, email FROM users")
    ).all()
    final = names.dedupe(
        [
            names.NameRow(
                id=row.id,
                created_at=row.created_at,
                display_name=row.display_name,
                email=row.email,
            )
            for row in rows
        ]
    )

    rename = sa.text(
        "UPDATE users SET display_name = :name, display_name_key = :key, "
        "version = version + 1, updated_at = now() WHERE id = :id"
    )
    keep = sa.text("UPDATE users SET display_name_key = :key WHERE id = :id")
    for row in rows:
        name = final[row.id]
        params = {"id": row.id, "key": names.name_key(name)}
        if name != row.display_name:
            connection.execute(rename, {**params, "name": name})
        else:
            connection.execute(keep, params)

    op.alter_column("users", "display_name_key", nullable=False)
    op.create_index("uq_users_display_name_key", "users", ["display_name_key"], unique=True)

    op.create_table(
        "user_preferences",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("prefs", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
    op.drop_index("uq_users_display_name_key", table_name="users")
    op.drop_column("users", "display_name_key")
