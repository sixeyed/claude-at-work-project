"""Step definitions for permissions.feature.

Named `test_*` for the reason `test_channel_steps.py` gives: `scenarios()`
generates its test functions into this module, and a module pytest does not
collect is a feature file that silently never runs.

The shared vocabulary — signing in, creating channels, reading a sidebar —
comes from `steps/conftest.py`. What is here is what this feature is about:
being refused a channel, and membership changing what someone can see.

Whether a member is offered the channel controls is a rendering question, and
is proven by the Vitest `ChannelHeader` tests (register D32); the server's 403
for a non-admin write is in
`src/services/messaging/tests/integration/test_channels.py`.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, scenarios, then, when

from bdd.pages.chat_page import ChatPage
from bdd.steps.conftest import GRACE_NAME

pytestmark = pytest.mark.bdd

scenarios("../features/permissions.feature")


# --- given ----------------------------------------------------------------


@given("Ada has added Grace to the channel")
def ada_has_added_grace(ada: ChatPage) -> None:
    ada.add_member(GRACE_NAME)


@given("Ada has removed Grace from the channel")
def ada_has_removed_grace(ada: ChatPage) -> None:
    ada.remove_member(GRACE_NAME)


# --- when -----------------------------------------------------------------


@when("Grace opens the link to that channel")
def grace_opens_the_link(ada: ChatPage, grace: ChatPage) -> None:
    """Ada's URL, pasted into Grace's window.

    The id comes off Ada's address bar rather than out of the database: what is
    being tested is a person following a link they were sent, and that link is
    the one Ada is looking at.
    """
    grace.open_channel_by_id(ada.current_channel_id())


# --- then -----------------------------------------------------------------


@then("Grace is told the channel does not exist")
def grace_is_told_not_found(grace: ChatPage) -> None:
    shown = grace.channel_error().lower()
    # "No such channel" — and deliberately not "you may not open this", which
    # would confirm there is something there to open.
    assert "no such channel" in shown or "not found" in shown, shown
