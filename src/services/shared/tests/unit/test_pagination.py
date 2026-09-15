"""Cursor pagination (Conventions §4.1).

The behaviour worth pinning down is the boundary: a cursor is built from the
last row *returned*, not the last row fetched, and the over-fetched extra row is
what tells us another page exists. Off by one here either drops a row between
pages or repeats one.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from shared import DEFAULT_LIMIT, MAX_LIMIT, PageRequest, build_page, decode_cursor, encode_cursor
from shared.problems import ProblemException


@dataclass(frozen=True)
class Row:
    at: str
    id: str


def rows(n: int) -> list[Row]:
    return [Row(at=f"2026-07-28T10:0{i}:00+00:00", id=f"id-{i}") for i in range(n)]


def key(row: Row) -> tuple[str, ...]:
    return (row.at, row.id)


def request(limit: int = 2, cursor: str | None = None) -> PageRequest:
    return PageRequest(limit=limit, cursor=decode_cursor(cursor) if cursor else None)


# --- the cursor itself -----------------------------------------------------


def test_a_cursor_round_trips() -> None:
    assert decode_cursor(encode_cursor("2026-07-28T10:00:00+00:00", "abc")) == (
        "2026-07-28T10:00:00+00:00",
        "abc",
    )


def test_a_cursor_is_opaque() -> None:
    """Not secret — just not something a client should learn to parse."""
    cursor = encode_cursor("2026-07-28T10:00:00+00:00", "abc")

    assert ":" not in cursor
    assert "=" not in cursor  # padding stripped, so it is URL-safe bare


def test_a_single_part_cursor_round_trips() -> None:
    assert decode_cursor(encode_cursor("only")) == ("only",)


def test_a_malformed_cursor_is_a_validation_error() -> None:
    with pytest.raises(ProblemException) as raised:
        decode_cursor("!!!not base64!!!")

    assert raised.value.status == 400
    assert "cursor" in (raised.value.errors or {})


# --- paging ----------------------------------------------------------------


def test_a_short_result_set_has_no_next_cursor() -> None:
    page = build_page(rows(2), request(limit=2), key=key)

    assert len(page.items) == 2
    assert page.next_cursor is None


def test_an_over_fetched_row_signals_another_page() -> None:
    """The query asks for `fetch_limit`; the extra row is dropped here."""
    page = build_page(rows(3), request(limit=2), key=key)

    assert len(page.items) == 2
    assert page.next_cursor is not None


def test_the_cursor_names_the_last_row_returned_not_the_one_dropped() -> None:
    """The off-by-one that repeats or skips a row.

    The over-fetched third row is the *first row of the next page*, so the
    cursor has to point at the second — the last one the caller actually saw.
    """
    page = build_page(rows(3), request(limit=2), key=key)

    assert decode_cursor(page.next_cursor) == key(rows(3)[1])


def test_an_empty_result_set_has_no_cursor() -> None:
    page = build_page([], request(limit=2), key=key)

    assert page.items == []
    assert page.next_cursor is None


def test_exactly_one_page_has_no_cursor() -> None:
    """A result set the same size as the limit is the last page, not a full one."""
    page = build_page(rows(2), request(limit=2), key=key)

    assert page.next_cursor is None


def test_fetch_limit_is_one_more_than_asked_for() -> None:
    assert request(limit=50).fetch_limit == 51


def test_the_conventional_limits_are_what_the_conventions_say() -> None:
    assert DEFAULT_LIMIT == 50
    assert MAX_LIMIT == 200
