"""Step definitions for channels.feature.

Named `test_*` because this is the module pytest collects: `scenarios()` below
generates one test function per scenario *into this module*, so a file pytest
skips is a feature file that silently never runs.

No selectors here — every one belongs to a page object (`tests/bdd/pages/`).
A step says what a person did; the page object knows what to click.

The `complaint` phrases in the scenario outline are matched loosely on purpose.
The scenario's job is to say *which rule* was reported, not to pin the exact
wording of a message — copy should be editable without a test failing, while
"too short" being reported where "must start with a letter" was expected is
exactly the kind of mix-up worth catching.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage

pytestmark = pytest.mark.bdd

scenarios("../features/channels.feature")

#: Scenario phrase → words that must appear in what the user is shown.
_COMPLAINTS = {
    "is too short": ["at least"],
    "must start with a letter": ["start", "letter"],
    "can only use letters, numbers and hyphens": ["letters", "numbers", "hyphens"],
    "is too long": ["or fewer"],
}


def _assert_complaint(shown: str, phrase: str) -> None:
    expected = _COMPLAINTS[phrase]
    lowered = shown.lower()
    missing = [word for word in expected if word.lower() not in lowered]
    assert not missing, f"expected a complaint that the name {phrase!r}, got: {shown!r}"


# --- given ----------------------------------------------------------------


@given("Ada is signed in")
def ada_is_signed_in(ada: ChatPage) -> None:
    # The context is signed in for the whole session; this loads the app fresh
    # so each scenario starts from the same place.
    ada.open()


@given(parsers.parse('Ada has created a public channel named "{name}"'))
def ada_has_created(ada: ChatPage, name: str) -> None:
    ada.create_channel_and_wait(name)


# --- when -----------------------------------------------------------------


@when(parsers.parse('Ada creates a public channel named "{name}"'))
def ada_creates(ada: ChatPage, name: str) -> None:
    ada.create_channel_and_wait(name)


@when(parsers.parse('Ada tries to create a second public channel named "{name}"'))
def ada_tries_second(ada: ChatPage, name: str) -> None:
    ada.create_channel_expecting_failure(name)


@when(parsers.parse('Ada tries to create a public channel named "{name}"'))
def ada_tries(ada: ChatPage, name: str) -> None:
    ada.create_channel_expecting_failure(name)


@when("Ada tries to create a public channel with a blank name")
def ada_tries_blank(ada: ChatPage) -> None:
    ada.create_channel_expecting_failure("")


@when("Ada tries to create a public channel with an 81-character name")
def ada_tries_too_long(ada: ChatPage) -> None:
    # 81 valid characters: the only thing wrong with it is the length.
    ada.create_channel_expecting_failure("a" * 81)


@when("Grace opens CollabHub")
def grace_opens(grace: ChatPage) -> None:
    grace.open()


# --- then -----------------------------------------------------------------


@then(parsers.parse('Ada sees the "{name}" workspace'))
def ada_sees_workspace(ada: ChatPage, name: str) -> None:
    assert ada.workspace_name() == name


@then(parsers.parse('Ada is looking at the "{name}" channel'))
def ada_is_looking_at(ada: ChatPage, name: str) -> None:
    assert ada.open_channel_name() == name


@then(parsers.parse('"{name}" is in Ada\'s channel list'))
def in_adas_list(ada: ChatPage, name: str) -> None:
    assert name in ada.channel_names()


@then(parsers.parse('"{name}" is in Grace\'s channel list'))
def in_graces_list(grace: ChatPage, name: str) -> None:
    assert name in grace.channel_names()


@then(parsers.parse('"{name}" appears in Ada\'s channel list exactly once'))
def appears_once(ada: ChatPage, name: str) -> None:
    assert ada.channel_names().count(name) == 1


@then("Ada is told that channel name is already taken")
def told_taken(ada: ChatPage) -> None:
    shown = ada.error_message().lower()
    assert "already exists" in shown or "already taken" in shown, shown


@then("Ada is told a channel name is required")
def told_required(ada: ChatPage) -> None:
    assert "required" in ada.error_message().lower()


@then(parsers.parse("Ada is told the name {complaint}"))
def told_complaint(ada: ChatPage, complaint: str) -> None:
    _assert_complaint(ada.error_message(), complaint)


@then("Ada's channel list is empty")
def adas_list_is_empty(ada: ChatPage) -> None:
    assert ada.channel_names() == []
