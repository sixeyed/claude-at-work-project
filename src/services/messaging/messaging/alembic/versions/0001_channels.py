"""Channels and channel membership.

Slice 1 of messaging: `channels` and `channel_members` only. `messages` arrives
in its own revision with the feature that needs it, and `reactions` is not
created until reactions are built — an empty table is a claim about what the
service does that is not yet true.

Columns whose features land later ship with their table (`last_read_id`,
`topic`, `version`) so no later revision has to alter one.

Two departures from the DDL in docs/design/02-messaging-service.md §4, both
recorded in that doc:

* `ux_channels_public_name` indexes `lower(name)`. Names are compared without
  case, so `#General` collides with `#general`; the stored name keeps whatever
  case it was typed with.
* `ix_channel_members_user` and `ix_channels_workspace_name` are additions. The
  spec gives `channel_members` only its composite primary key, which cannot
  answer "which channels is this user in?", and gives `channels` no index for
  the workspace-ordered sidebar read.

Revision ID: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMPTZ = TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # No foreign key: the workspace lives in the Auth service's database and
        # a constraint across that boundary would stop either side deploying
        # alone (Conventions §2).
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False, server_default="public"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        # A channel's soft delete is `archived_at`, not `deleted_at` — reads
        # filter on this column.
        sa.Column("archived_at", TIMESTAMPTZ, nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )

    # A partial unique *index*, not a constraint: PostgreSQL has no
    # `UNIQUE (...) WHERE ...` on a constraint, only on an index.
    op.create_index(
        "ux_channels_public_name",
        "channels",
        ["workspace_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("kind = 'public'"),
    )
    op.create_index(
        "ix_channels_workspace_name",
        "channels",
        ["workspace_id", "name", "id"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "channel_members",
        sa.Column(
            "channel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("channels.id"),
            primary_key=True,
        ),
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("role", sa.String(), nullable=False, server_default="member"),
        sa.Column("last_read_id", UUID(as_uuid=True), nullable=True),
        sa.Column("joined_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_channel_members_user", "channel_members", ["user_id", "channel_id"])


def downgrade() -> None:
    op.drop_table("channel_members")
    op.drop_table("channels")
