"""Read state.

A table of its own rather than the `last_read_id` column `0001` shipped on
`channel_members`, and that column is dropped here. Membership is not what
gates reading a channel — visibility is (spec §3.1.1) — and nobody in this
scope can add themselves to a channel, so a pointer on the membership row would
give Grace no unread count in a public `#general` she reads every day.

Two columns the conventions would expect are absent on purpose:

* **No `version`.** The pointer only moves forward — the upsert is guarded by
  `last_read_id < excluded.last_read_id` — so there is no lost update for
  optimistic concurrency to catch, and nothing for a client to conflict on.
* **No foreign key on `last_read_id`.** A retention job may hard-delete messages
  (register D16), and a marker must not stop it. `user_id` carries none either:
  users are Auth's rows (Conventions §2).

No index beyond the primary key: every read of this table is one
`(channel_id, user_id)` pair, joined from the channel row.

Revision ID: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMPTZ = TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "channel_reads",
        sa.Column(
            "channel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("channels.id"),
            primary_key=True,
        ),
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("last_read_id", UUID(as_uuid=True), nullable=False),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )
    op.drop_column("channel_members", "last_read_id")


def downgrade() -> None:
    op.add_column("channel_members", sa.Column("last_read_id", UUID(as_uuid=True), nullable=True))
    op.drop_table("channel_reads")
