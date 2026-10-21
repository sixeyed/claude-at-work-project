"""Reading and merging a user's preferences (register D28).

One row per user in `user_preferences`, created by the first write. The API
decides which keys may be written; this module only stores them, and keeps keys it
does not know (a row may hold more than the API offers) when it merges.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Every SQL value is a bound parameter. Both `user_preferences.` qualifiers are
# needed: an unqualified `prefs` in the DO UPDATE clause is ambiguous with `excluded`.
_MERGE = text(
    """
    INSERT INTO user_preferences (user_id, prefs, version, updated_at)
    VALUES (:user_id, CAST(:set AS jsonb) - CAST(:removed AS text[]), 0, now())
    ON CONFLICT (user_id) DO UPDATE SET
        prefs = (user_preferences.prefs || CAST(:set AS jsonb)) - CAST(:removed AS text[]),
        version = user_preferences.version + 1,
        updated_at = now()
    RETURNING prefs
    """
)

_READ = text("SELECT prefs FROM user_preferences WHERE user_id = :user_id")


def _as_dict(prefs: Any) -> dict[str, Any]:
    return json.loads(prefs) if isinstance(prefs, str) else dict(prefs)


async def read(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    """The stored preferences; `{}` when the user has none. Never inserts."""
    result = await session.execute(_READ, {"user_id": user_id})
    prefs = result.scalar_one_or_none()
    return {} if prefs is None else _as_dict(prefs)


async def merge(
    session: AsyncSession, user_id: uuid.UUID, set_: dict[str, Any], removed: list[str]
) -> dict[str, Any]:
    """Apply `set_` and drop `removed` in one statement; return the stored result.

    A single upsert under the row lock: two tabs changing different keys both
    survive, and two first writes racing cannot turn one into a unique violation.
    """
    result = await session.execute(
        _MERGE, {"user_id": user_id, "set": json.dumps(set_), "removed": removed}
    )
    return _as_dict(result.scalar_one())
