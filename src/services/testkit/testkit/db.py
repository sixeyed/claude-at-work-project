"""Emptying a service's tables between tests.

Truncating is much faster than re-running migrations, and the schema is what
the session fixture already proved. `RESTART IDENTITY CASCADE` so the order of
`tables` never matters and no sequence carries over.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

_TABLE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


async def truncate(engine: AsyncEngine, tables: Sequence[str]) -> None:
    bad = [table for table in tables if not _TABLE_NAME.match(table)]
    if bad or not tables:
        raise ValueError(f"not a list of table names: {list(tables)!r}")
    async with engine.begin() as connection:
        # conventions: ok — identifiers cannot be bind parameters, and every name
        # matched `_TABLE_NAME` above.
        await connection.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
