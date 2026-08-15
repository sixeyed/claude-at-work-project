"""Database access for the Messaging service — its own database and no other.

The engine is built once per app and handed to routes as a session factory, so
tests can point an app at a throwaway container without patching anything.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_engine(dsn: str) -> AsyncEngine:
    return create_async_engine(dsn, pool_pre_ping=True)


def build_sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # `expire_on_commit=False` so a committed row can still be read for the
    # response without a second round trip.
    return async_sessionmaker(engine, expire_on_commit=False)


async def session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session; routes commit explicitly."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.sessions
    async with factory() as db_session:
        yield db_session
