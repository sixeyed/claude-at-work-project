"""The display-name rules, in one place (gh-5, register D46).

Used by `PATCH /users/me`, by `provision_user` and by migration 0002, so that what
a rename accepts, what a first sign-in repairs and what the migration does to
existing rows are one set of rules and cannot drift apart. Nothing here touches a
database or HTTP.

Uniqueness is decided on `name_key`, a canonical caseless form the application
computes and stores in `users.display_name_key` under a unique index. Postgres's
`lower()` would compare with rules that depend on the database's `LC_CTYPE` and
that are not case folding, while the application would need a second copy of the
comparison; one function and one stored key keeps both sides identical.
"""

from __future__ import annotations

import unicodedata
import uuid
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import count

MAX_LENGTH = 100

REQUIRED = "A display name is required."
TOO_LONG = f"A display name can be at most {MAX_LENGTH} characters."
INVISIBLE = "A display name can't contain invisible or control characters."

# General categories no name may contain: control, format, surrogate, private use,
# unassigned, and the line and paragraph separators.
_REFUSED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

# The Unicode `Default_Ignorable_Code_Point` property, which Python's `unicodedata`
# does not expose. These are the ranges for Unicode 15.0, the version of Python
# 3.12's `unicodedata.unidata_version`; they render as nothing, so a name made of
# them would look like another person's. ZWJ and ZWNJ are included (Decided 5).
# U+2800 (braille blank) is a visible symbol and is deliberately not here.
_DEFAULT_IGNORABLE = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)


class InvalidNameError(ValueError):
    """A display name the rules refuse; `str(exc)` is the message the user sees."""


def _refused(char: str) -> bool:
    if unicodedata.category(char) in _REFUSED_CATEGORIES:
        return True
    point = ord(char)
    return any(first <= point <= last for first, last in _DEFAULT_IGNORABLE)


def normalise(raw: str) -> str:
    """Trim, then compose to NFC — the form a name is stored in."""
    return unicodedata.normalize("NFC", raw.strip())


def check(name: str) -> None:
    """Raise `InvalidNameError` unless an already-normalised name is acceptable.

    Length is counted in code points of the stored form (Decision 14).
    """
    if not name:
        raise InvalidNameError(REQUIRED)
    if any(_refused(char) for char in name):
        raise InvalidNameError(INVISIBLE)
    if len(name) > MAX_LENGTH:
        raise InvalidNameError(TOO_LONG)


def clean(raw: str) -> str:
    """Normalise and check; returns the form to store."""
    name = normalise(raw)
    check(name)
    return name


def name_key(name: str) -> str:
    """The comparison key: full case folding on the decomposed form, recomposed."""
    return unicodedata.normalize("NFC", unicodedata.normalize("NFD", name).casefold())


def candidates(base: str) -> Iterator[str]:
    """`base`, `base 2`, `base 3` …, the base cut so each fits the limit (Decision 16)."""
    yield base
    for n in count(2):
        suffix = f" {n}"
        yield base[: MAX_LENGTH - len(suffix)] + suffix


def first_free(base: str, taken: Collection[str]) -> str:
    """The first candidate whose key is not in `taken` (a collection of keys)."""
    return next(c for c in candidates(base) if name_key(c) not in taken)


def _repair(raw: str) -> str:
    """Normalise, drop refused characters, cut to the limit; may return ''."""
    kept = "".join(char for char in normalise(raw) if not _refused(char))
    return normalise(normalise(kept)[:MAX_LENGTH])


def provisional(raw: str, fallback: str) -> str:
    """A name that passes `check`, made from one that may not (Decision 15).

    `raw` repaired; failing that `fallback` (the email's local part) repaired;
    failing that `"user"`. Sign-in never refuses over a name.
    """
    return _repair(raw) or _repair(fallback) or "user"


@dataclass(frozen=True)
class NameRow:
    id: uuid.UUID
    created_at: datetime
    display_name: str
    email: str


def dedupe(rows: Sequence[NameRow]) -> dict[uuid.UUID, str]:
    """Every row's final name, so that no two share a key (Req 4).

    Each name is normalised first (and repaired if `check` refuses it — Decision
    17). The oldest holder of a name keeps it. Before any newer holder is given a
    suffix, the key of every name that is no duplicate, and of the oldest holder
    of every duplicate group, is reserved (Decision 17a): a newer `Sam 2` that was
    never a duplicate is not renamed to make room for a `sam` that was.
    """
    ordered = sorted(rows, key=lambda r: (r.created_at, r.id))
    names: dict[uuid.UUID, str] = {}
    for row in ordered:
        name = normalise(row.display_name)
        try:
            check(name)
        except InvalidNameError:
            name = provisional(name, row.email.split("@")[0])
        names[row.id] = name

    reserved: set[str] = set()
    duplicates: list[uuid.UUID] = []
    for row in ordered:
        key = name_key(names[row.id])
        if key in reserved:
            duplicates.append(row.id)
        else:
            reserved.add(key)

    for row_id in duplicates:
        names[row_id] = first_free(names[row_id], reserved)
        reserved.add(name_key(names[row_id]))
    return names
