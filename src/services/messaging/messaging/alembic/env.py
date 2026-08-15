"""Alembic environment for the Messaging service.

Runs against Messaging's database and no other (Conventions §2). Two entry
paths:

* embedded — `messaging.migrations.upgrade_to_head` passes an open connection in
  `config.attributes`, which is how the service and the tests migrate;
* CLI — `alembic upgrade head` with no connection, where this module builds its
  own async engine from `POSTGRES_DSN`.
"""

from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from messaging.models import Base

config = context.config
target_metadata = Base.metadata


def _dsn() -> str:
    return os.environ.get("POSTGRES_DSN") or config.get_main_option("sqlalchemy.url", "")


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(_dsn())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run)
            await connection.commit()
    finally:
        await engine.dispose()


def run_offline() -> None:
    context.configure(url=_dsn(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_offline()
elif (connection := config.attributes.get("connection")) is not None:
    _run(connection)
else:
    asyncio.run(_run_async())
