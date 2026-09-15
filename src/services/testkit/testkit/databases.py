"""A database per service on the one Postgres a test session starts (D34).

Every service owns its own database, so the tests do too: `service_database`
creates it and runs that service's migrations, and a service's conftest keeps
the DSN in a session fixture of its own.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_DATABASE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class PostgresServer:
    host: str
    port: int
    user: str
    password: str
    #: The database the container was created with — where `CREATE DATABASE` runs.
    admin_database: str

    def dsn(self, database: str) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{database}"
        )


def service_database(
    server: PostgresServer, name: str, upgrade: Callable[[str], Awaitable[None]]
) -> str:
    """Create database `name`, migrate it with `upgrade`, and return its DSN.

    Synchronous, for a session fixture: no event loop is running while one is
    set up, and `upgrade_to_head` is async.
    """
    if not _DATABASE_NAME.match(name):
        raise ValueError(f"not a database name: {name!r}")
    asyncio.run(_create(server, name))
    dsn = server.dsn(name)
    asyncio.run(upgrade(dsn))
    return dsn


async def _create(server: PostgresServer, name: str) -> None:
    # CREATE DATABASE cannot run inside a transaction.
    engine = create_async_engine(server.dsn(server.admin_database), isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            )
            if not exists:
                # conventions: ok — an identifier cannot be a bind parameter, and `name`
                # matched `_DATABASE_NAME` above.
                # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text — SQLAlchemy has no CREATE DATABASE construct, and the name is validated
                await connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await engine.dispose()
