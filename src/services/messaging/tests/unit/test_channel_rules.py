"""Channel name and kind rules (doc 02 §3.1) — every rule, with no database.

These used to be reachable only over HTTP against Postgres. What stays in
`tests/integration/test_channels.py` is one example per rule per route: proof
that the route maps each exception to its problem, not a second copy of the
rules.
"""

from __future__ import annotations

import pytest

from messaging.channels import (
    MAX_NAME_LENGTH,
    MIN_NAME_LENGTH,
    NameCharactersError,
    NameMustStartWithLetterError,
    NameRequiredError,
    NameTooLongError,
    NameTooShortError,
    UnknownKindError,
    validate_kind,
    validate_name,
)


@pytest.mark.parametrize("raw", ["", "   ", "\t\n"])
def test_a_name_is_required(raw):
    """Breaks if emptiness is judged before trimming, or not at all."""
    with pytest.raises(NameRequiredError):
        validate_name(raw)


def test_a_name_shorter_than_three_characters_is_refused():
    """Breaks if the minimum moves."""
    assert MIN_NAME_LENGTH == 3
    with pytest.raises(NameTooShortError):
        validate_name("ab")


def test_a_name_of_exactly_three_characters_is_accepted():
    """Breaks if the minimum is off by one."""
    assert validate_name("abc") == "abc"


def test_a_name_longer_than_eighty_characters_is_refused():
    """Breaks if the maximum moves."""
    assert MAX_NAME_LENGTH == 80
    with pytest.raises(NameTooLongError):
        validate_name("a" * 81)


def test_a_name_of_exactly_eighty_characters_is_accepted():
    """Breaks if the maximum is off by one."""
    assert validate_name("a" * 80) == "a" * 80


@pytest.mark.parametrize("raw", ["1password", "-general"])
def test_a_name_must_start_with_a_letter(raw):
    """Breaks if a leading digit or hyphen falls through to the character rule."""
    with pytest.raises(NameMustStartWithLetterError):
        validate_name(raw)


@pytest.mark.parametrize("raw", ["dev team", "dev_team", "général", "dev.team"])
def test_a_name_uses_only_letters_numbers_and_hyphens(raw):
    """ASCII only: breaks if the pattern admits a space, underscore or accent."""
    with pytest.raises(NameCharactersError):
        validate_name(raw)


@pytest.mark.parametrize("raw", ["general", "team-42", "Design-Review", "a1b"])
def test_a_typeable_name_is_accepted_as_typed(raw):
    """Breaks if a valid name is refused, or its case is changed."""
    assert validate_name(raw) == raw


def test_a_name_is_trimmed():
    """The stored name is the trimmed one."""
    assert validate_name("  general  ") == "general"


def test_the_length_rules_apply_to_the_trimmed_name():
    """Breaks if the length is measured before trimming — `"  ab  "` is six characters."""
    with pytest.raises(NameTooShortError):
        validate_name("  ab  ")


@pytest.mark.parametrize("kind", ["public", "private"])
def test_public_and_private_channels_can_be_created(kind):
    assert validate_kind(kind) == kind


@pytest.mark.parametrize("kind", ["dm", "bogus", ""])
def test_any_other_kind_is_refused(kind):
    """`dm` exists in the schema (D8b) and is still refused: a DM has no name to give."""
    with pytest.raises(UnknownKindError):
        validate_kind(kind)
