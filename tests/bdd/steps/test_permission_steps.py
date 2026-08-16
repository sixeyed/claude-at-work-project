"""Step definitions for permissions.feature.

Named `test_*` for the reason `test_channel_steps.py` gives: `scenarios()`
generates its test functions into this module, and a module pytest does not
collect is a feature file that silently never runs.

The shared vocabulary — signing in, creating channels, reading a sidebar —
comes from `steps/conftest.py`. What is here is what this feature is about:
being offered a control, being refused a channel, and membership changing what
someone can see.

Two of these scenarios turn on an *absence*, which is the kind of assertion
worth being explicit about. "Grace is not offered the channel controls" checks
that the admin controls are not rendered — not that clicking one fails. The
server refuses a non-admin write with a 403 either way; that is covered in
`src/services/messaging/tests/test_channels.py`, because a control the SPA
deliberately does not draw is not something a browser can drive.
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


@then("Grace is not offered the channel controls")
def grace_has_no_controls(grace: ChatPage) -> None:
    assert not grace.has_channel_controls()


@then("Ada is offered the channel controls")
def ada_has_controls(ada: ChatPage) -> None:
    assert ada.has_channel_controls()


@then("Grace is told the channel does not exist")
def grace_is_told_not_found(grace: ChatPage) -> None:
    shown = grace.channel_error().lower()
    # "No such channel" — and deliberately not "you may not open this", which
    # would confirm there is something there to open.
    assert "no such channel" in shown or "not found" in shown, shown
