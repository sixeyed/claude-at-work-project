"""SQLAlchemy models for the Messaging service's own database (spec §4).

Only Messaging reads these tables; every other service learns about channels
through this service's API or an event (Conventions §2).

Two things differ from the DDL in docs/design/02-messaging-service.md §4, both
decided while planning slice 1 and reflected back into that doc:

* `ux_channels_public_name` folds case. `#General` and `#general` being two
  different channels is a support ticket, and people say channel names out loud
  where case does not exist. The name is stored exactly as typed — only the
  index is folded.
* Two indexes the spec omits. `channel_members` had only its composite primary
  key, which answers "who is in this channel?" but not "which channels is this
  user in?" — the query the sidebar runs on every page load.

Note also what is *not* here: `channels` has no `deleted_at`. Its soft-delete
column is `archived_at` (spec §4, and `DELETE /channels/{id}` is an archive), so
"filter `deleted_at IS NULL`" from Conventions §3 reads as `archived_at IS NULL`
for this table. `workspace_id`, `created_by` and `channel_members.user_id` carry
no foreign keys, because they name rows in other services' databases.

`messages` is the mirror image and the other documented exception to the same
Conventions §3 rule. It *does* have `deleted_at` — and the read path deliberately
does **not** filter it. A deleted message stays in history as a tombstone with
its body redacted server-side, because a tombstone a reload erases is not a
tombstone. That is why `ix_messages_channel_time` carries no
`WHERE deleted_at IS NULL` predicate: the query that would use it does not have
that clause. The rule is "filter the soft-delete column *unless the doc says
otherwise*", and this is one of the two places it says otherwise.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Every timestamp on the platform is UTC `timestamptz` (Conventions §3).
Timestamp = TIMESTAMP(timezone=True)

PUBLIC = "public"
PRIVATE = "private"
DM = "dm"

#: Kinds a client may create. `dm` exists in the schema (register D8b) but is
#: not creatable through this API — a DM has no name and no creator-as-admin.
CREATABLE_KINDS = (PUBLIC, PRIVATE)

ADMIN = "admin"
MEMBER = "member"


class Base(DeclarativeBase):
    pass


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (
        # A partial *index*, not a table constraint: PostgreSQL has no
        # `UNIQUE (...) WHERE ...` on a constraint. Names are unique among
        # public channels; private channels and DMs may repeat one.
        Index(
            "ux_channels_public_name",
            "workspace_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("kind = 'public'"),
        ),
        # Covers the sidebar query: one workspace, unarchived, name-ordered.
        Index(
            "ix_channels_workspace_name",
            "workspace_id",
            "name",
            "id",
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    topic: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String, nullable=False, server_default=PUBLIC)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class ChannelMember(Base):
    """Who is in a channel, and what they may do to it.

    Channel membership is *not* workspace membership (spec §3.1): these roles
    are `admin`/`member` within one channel and have nothing to do with the
    workspace roles in the token's `roles` claim.
    """

    __tablename__ = "channel_members"
    __table_args__ = (
        # "Which channels is this user in?" — the primary key leads with
        # channel_id and cannot answer it.
        Index("ix_channel_members_user", "user_id", "channel_id"),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(String, nullable=False, server_default=MEMBER)
    last_read_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )


class Message(Base):
    """Something somebody said in a channel (spec §4).

    Three columns ship ahead of their features, on the rule `0001_channels`
    already set: adding a column later churns the table, so `thread_root_id`
    (threading, register D8a), `attachments` (the Asset service is a skeleton)
    and `version` land now. `version` is not idle even so — it is the
    optimistic-concurrency guard for the edit in the next slice, and the
    external version an Elasticsearch index would use (register D25).

    `channel_id` carries a foreign key and `author_id` does not, and that is the
    Conventions §2 boundary drawn in DDL: a channel is this service's row, and a
    user is Auth's.
    """

    __tablename__ = "messages"
    __table_args__ = (
        # The history read: one channel, newest first. **No
        # `WHERE deleted_at IS NULL`** — history returns tombstones, so the read
        # path has no such clause and would not match a partial index.
        #
        # `ix_messages_thread` from spec §4 is deliberately absent: nothing
        # queries `thread_root_id` in this scope, and an index for a query no
        # code makes is dead weight. Adding it later is one line and no table
        # rewrite — unlike the column, which is why the column is here.
        Index("ix_messages_channel_time", "channel_id", text("id DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    thread_root_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attachments: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )
    edited_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
