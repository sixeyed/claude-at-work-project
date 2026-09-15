"""Message body rules (doc 02 §3.1.3) — every rule, with no database.

`tests/integration/test_messages.py` keeps one example per rule per route, and
the test that the *configured* limit reaches the route. The rule itself is here.
"""

from __future__ import annotations

import pytest

from messaging.messages import BodyRequiredError, BodyTooLongError, validate_body

LIMIT = 8000


@pytest.mark.parametrize("raw", ["", " ", "   ", "\n\t  \n"])
def test_an_empty_or_whitespace_only_body_is_refused(raw):
    """Breaks if emptiness is judged on the raw string rather than the stripped one."""
    with pytest.raises(BodyRequiredError):
        validate_body(raw, max_chars=LIMIT)


def test_a_body_over_the_limit_is_refused():
    with pytest.raises(BodyTooLongError):
        validate_body("a" * (LIMIT + 1), max_chars=LIMIT)


def test_a_body_of_exactly_the_limit_is_accepted():
    """Breaks if the limit is off by one."""
    assert validate_body("a" * LIMIT, max_chars=LIMIT) == "a" * LIMIT


def test_the_body_is_returned_verbatim():
    """Markdown is whitespace-sensitive: breaks if the body is trimmed like a channel name."""
    raw = "    indented code\ntrailing  "
    assert validate_body(raw, max_chars=LIMIT) == raw


def test_length_is_judged_on_the_raw_body():
    """Breaks if surrounding whitespace is stripped before the length check."""
    with pytest.raises(BodyTooLongError):
        validate_body(" " + "a" * 10, max_chars=10)


def test_the_configured_limit_is_the_one_applied():
    """`MESSAGING_MAX_BODY_CHARS` is configuration: breaks if a constant replaces it."""
    assert validate_body("a" * 10, max_chars=10) == "a" * 10
    with pytest.raises(BodyTooLongError):
        validate_body("a" * 11, max_chars=10)
