"""Messages.

Slice 3 of messaging. `0001` deliberately left this table out, and this is the
revision that adds it — one table, one index, and nothing speculative.

Columns whose features land later ship with the table, on the same rule `0001`
followed: `thread_root_id` (threading, register D8a), `attachments` (the Asset
service is a skeleton) and `version` (the edit's optimistic-concurrency guard,
one slice away). Adding a column later rewrites the table; adding an index later
does not — which is why the split below goes the way it does.

Two departures from the DDL in docs/design/02-messaging-service.md §4, both
recorded in that doc:

* **`ix_messages_channel_time` has no `WHERE deleted_at IS NULL`.** The spec
  gives the partial form. It is wrong for this service: a deleted message stays
  in history as a tombstone with its body redacted, so the history query has no
  `deleted_at` clause and would not match a partial index. This is the second of
  the two documented exceptions to Conventions §3's "queries filter
  `deleted_at IS NULL`" — the first being `channels`, which soft-deletes through
  `archived_at`.
* **`ix_messages_thread` is not created.** Nothing queries `thread_root_id` in
  this scope. An index supporting a query no code makes is dead weight, and
  adding it with the threading feature is one line and no table rewrite. Same
  reasoning that leaves `reactions` uncreated.

Revision ID: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP, UUID

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMPTZ = TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "channel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("channels.id"),
            nullable=False,
        ),
        # No foreign key: the user lives in the Auth service's database
        # (Conventions §2). The channel above is ours, so that one is real.
        sa.Column("author_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "thread_root_id",
            UUID(as_uuid=True),
            sa.ForeignKey("messages.id"),
            nullable=True,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "attachments",
            ARRAY(UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("edited_at", TIMESTAMPTZ, nullable=True),
        # Present, and deliberately *not* filtered by the read path — see the
        # module docstring.
        sa.Column("deleted_at", TIMESTAMPTZ, nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_index(
        "ix_messages_channel_time",
        "messages",
        ["channel_id", sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_table("messages")
