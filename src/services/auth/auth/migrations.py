"""Running Auth's Alembic migrations (Conventions §11).

The migration scripts live *inside* the `auth` package rather than beside it, so
they are part of the wheel. The service image installs with `--no-editable` and
drops the source tree, and migrations that are not packaged are migrations that
cannot run in the container that needs them.

Alembic's `command.upgrade` is synchronous while the service speaks asyncpg, so
`upgrade_to_head` opens the async connection and hands it to Alembic through
`run_sync`. `env.py` uses that connection when it is given one and creates its
own when invoked from the CLI.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

SCRIPT_LOCATION = Path(__file__).parent / "alembic"


def alembic_config(dsn: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    config.set_main_option("sqlalchemy.url", dsn)
    return config


def _upgrade(connection: Connection, dsn: str) -> None:
    config = alembic_config(dsn)
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


async def upgrade_to_head(dsn: str) -> None:
    """Bring the database at `dsn` up to the latest revision."""
    engine = create_async_engine(dsn)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_upgrade, dsn)
    finally:
        await engine.dispose()
