"""Issuing, rotating and revoking sessions (spec §5.2, Conventions §5.1, §5.2).

A session is an access token the client uses and a refresh token it keeps.
Access tokens are never stored — they are verified by signature — so everything
persisted here is about the refresh token: one row per issue, hashed, linked to
the row it replaced.

Rotation is what makes a stolen refresh token detectable. Each refresh spends
the presented token and issues a new one, pointing the old row at the new
through `rotated_to`. If a token that has already been spent turns up again,
either the client or a thief is holding a copy, and there is no way to tell
which — so the whole chain is revoked and the user signs in again. Losing a
session is a smaller harm than serving an attacker.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.identities import Membership
from auth.models import RefreshToken, User
from auth.tokens import TokenIssuer, hash_refresh_token, new_refresh_token
from shared import Denylist, uuid7


class InvalidRefreshTokenError(Exception):
    """The presented refresh token is unknown, expired, revoked, or replayed."""


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


async def issue(
    session: AsyncSession,
    *,
    issuer: TokenIssuer,
    user: User,
    membership: Membership,
    refresh_token_days: int,
) -> TokenPair:
    """Mint an access token for one workspace, plus a refresh token to renew it."""
    access = issuer.access_token(
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        workspace_id=membership.workspace.id,
        roles=[membership.role],
    )

    refresh = new_refresh_token()
    session.add(
        RefreshToken(
            id=uuid7(),
            user_id=user.id,
            workspace_id=membership.workspace.id,
            token_hash=hash_refresh_token(refresh),
            expires_at=datetime.now(UTC) + timedelta(days=refresh_token_days),
        )
    )

    return TokenPair(access_token=access.value, refresh_token=refresh, expires_in=access.expires_in)


async def _find(session: AsyncSession, token: str) -> RefreshToken | None:
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token))
    )
    return result.scalar_one_or_none()


async def _revoke_descendants(session: AsyncSession, row: RefreshToken) -> None:
    """Revoke a spent token's whole rotation chain.

    Walking forward from the replayed row reaches every token issued after it,
    which is the live session — whoever holds it. The already-spent ancestors
    are revoked by definition.
    """
    now = datetime.now(UTC)
    current: RefreshToken | None = row
    seen: set[uuid.UUID] = set()

    while current is not None and current.id not in seen:
        seen.add(current.id)
        if current.revoked_at is None:
            current.revoked_at = now
        if current.rotated_to is None:
            break
        current = await session.get(RefreshToken, current.rotated_to)


async def spend(session: AsyncSession, token: str) -> RefreshToken:
    """Consume a refresh token, returning its row. Raises if it is not usable."""
    row = await _find(session, token)
    if row is None:
        raise InvalidRefreshTokenError("unknown refresh token")

    if row.rotated_to is not None:
        # Replay of a token that was already exchanged: assume compromise.
        await _revoke_descendants(session, row)
        raise InvalidRefreshTokenError("refresh token reuse detected")

    if row.revoked_at is not None:
        raise InvalidRefreshTokenError("refresh token revoked")

    if row.expires_at <= datetime.now(UTC):
        raise InvalidRefreshTokenError("refresh token expired")

    return row


async def rotate(
    session: AsyncSession,
    *,
    presented: RefreshToken,
    issuer: TokenIssuer,
    user: User,
    membership: Membership,
    refresh_token_days: int,
) -> TokenPair:
    """Issue the next pair in a family and retire the token that bought it."""
    pair = await issue(
        session,
        issuer=issuer,
        user=user,
        membership=membership,
        refresh_token_days=refresh_token_days,
    )
    await session.flush()

    successor = await _find(session, pair.refresh_token)
    if successor is None:  # pragma: no cover — just written in this transaction
        raise RuntimeError("the refresh token just issued could not be read back")
    presented.rotated_to = successor.id
    presented.revoked_at = datetime.now(UTC)

    return pair


async def revoke_access_token(denylist: Denylist, *, token_id: str, expires_at: datetime) -> None:
    """Add a `jti` to the R1 denylist for what remains of its lifetime."""
    remaining = int((expires_at - datetime.now(UTC)).total_seconds())
    await denylist.revoke(token_id, ttl_seconds=remaining)


async def revoke_refresh_token(session: AsyncSession, token: str) -> None:
    """Best-effort revocation on logout; an unknown token is already harmless."""
    row = await _find(session, token)
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
