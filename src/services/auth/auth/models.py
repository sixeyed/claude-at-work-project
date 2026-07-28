"""SQLAlchemy models for the Auth service's own database (spec §4).

They map one-to-one to the tables in docs/design/01-auth-service.md; Alembic
owns the migration history. Only Auth reads these tables — every other service
learns about users through a token claim or this service's API (Conventions §2).

Note what is *not* here: `users.avatar_asset` holds an Asset service id with no
foreign key, because a cross-service reference that the database enforces is a
cross-service coupling that stops either side deploying alone.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Every timestamp on the platform is UTC `timestamptz` (Conventions §3).
Timestamp = TIMESTAMP(timezone=True)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    avatar_asset: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class ExternalIdentity(Base):
    """A user's identity at an upstream IdP — `oidc:acme`, `saml:corp`.

    Empty until federation lands (register D5): the MVP's dev-login is a local
    shortcut, not an identity provider. The table ships now because its
    successor writes here and nothing else changes when it does.
    """

    __tablename__ = "external_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_external_identity"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )


class WorkspaceMember(Base):
    """Many-to-many membership; the `wsp` claim names one of these at a time."""

    __tablename__ = "workspace_members"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )


class RefreshToken(Base):
    """One row per issued refresh token — access tokens are never stored.

    Rotation writes a new row and points the old one at it through `rotated_to`,
    which is what makes replay of a spent token detectable (spec §5.2).

    `workspace_id` is an addition to the table in spec §4. Refresh tokens are
    not workspace-*scoped* — the holder may switch at any time (Conventions
    §5.4) — but the row has to remember which workspace the session was last
    using, or every refresh would silently drop the user back into their first
    workspace and a switch would survive only fifteen minutes.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_user", "user_id", postgresql_where=text("revoked_at IS NULL")),
        Index("ix_refresh_token_hash", "token_hash", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(Timestamp, nullable=False)
    rotated_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_tokens.id"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
