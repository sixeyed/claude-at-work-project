"""Step definitions for realtime.feature.

Named `test_*` for the reason the other step modules give: `scenarios()`
generates its test functions into this module, and a module pytest does not
collect is a feature file that silently never runs. This is the only module that
calls `scenarios()` on `realtime.feature`.

The shared vocabulary — signing in, creating channels, sending, editing,
deleting — is in `steps/conftest.py`, and these scenarios reuse it rather than
spelling the same acts a second way. What is here is what "live" adds:
watching a channel, asserting on something that arrived without a reload, and
dropping the network.

**"Without reloading" is a property of the page object, not of a phrase.**
Nothing in these steps navigates or reloads, so a message appearing on Grace's
screen can only have got there over the socket. If a step here ever called
`open()`, the scenario would still pass and would stop testing anything.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage
from bdd.steps.conftest import ADA_NAME

pytestmark = pytest.mark.bdd

scenarios("../features/realtime.feature")


# --- given ----------------------------------------------------------------


@given(parsers.parse('Grace is looking at the "{name}" channel'))
def grace_is_watching(grace: ChatPage, name: str) -> None:
    """Grace opens the channel and waits until her socket is actually up.

    The wait is the point. Without it the scenario races its own arrangement:
    Ada sends, the broadcast goes to a room Grace has not joined yet, and the
    failure looks like "real-time does not work" rather than "the test was
    early".
    """
    grace.open()
    grace.open_channel(name)
    grace.wait_for_connection()


# --- when -----------------------------------------------------------------


@when("Grace's network drops")
def graces_network_drops(grace: ChatPage) -> None:
    grace.go_offline()


@when("Grace's network comes back")
def graces_network_returns(grace: ChatPage) -> None:
    grace.go_online()


# --- then -----------------------------------------------------------------


@then(parsers.parse('Grace sees "{body}" in the channel without reloading'))
def grace_sees_live(grace: ChatPage, body: str) -> None:
    grace.wait_for_message(body)


@then("Grace sees a deleted message in the channel without reloading")
def grace_sees_tombstone_live(grace: ChatPage) -> None:
    grace.wait_for_tombstone()


@then(parsers.parse('Grace sees "{body}" marked as edited'))
def grace_sees_edited_marker(grace: ChatPage, body: str) -> None:
    assert grace.has_edited_marker(body)


@then(parsers.parse('Grace does not see "{body}" in the channel'))
def grace_does_not_see(grace: ChatPage, body: str) -> None:
    assert grace.is_absent(body), grace.message_bodies()


@then(parsers.parse('"{body}" appears in Ada\'s channel exactly once'))
def appears_once_for_ada(ada: ChatPage, body: str) -> None:
    """The sender receives her own broadcast, and must not render it twice.

    There is no `sid` to skip it by — the write went over REST, which is not a
    socket — so the cache helper has to be idempotent on the message id. A blind
    append passes every other scenario in this file and fails this one.
    """
    assert ada.count_of(body) == 1


@then("Grace's connection is restored")
def graces_connection_restored(grace: ChatPage) -> None:
    grace.wait_for_connection()


# --- the socket write path (slice 6) ---------------------------------------


@when(parsers.parse('Ada types "{text}" into her message box without sending it'))
def ada_types(ada: ChatPage, text: str) -> None:
    """Typed a character at a time, because that is what the throttle sees.

    `fill` would set the value in one go and fire one change event — one
    keystroke's worth of signal for a whole sentence. The composer is disabled
    until the socket is up, and Playwright waits for an editable element, so
    this also absorbs the connection race.
    """
    ada.wait_for_connection()
    ada.type_into_composer(text)


@when("Ada stops typing")
def ada_stops_typing(ada: ChatPage) -> None:
    """Deliberately does nothing.

    There is no `typing_stopped` event and there is not meant to be one:
    stopping is the *absence* of an act. The indicator clears because the
    receiver expires it, which is the only design that also covers the person
    who closed their laptop mid-word.
    """


@then("Grace sees that Ada is typing")
def grace_sees_typing(grace: ChatPage) -> None:
    shown = grace.typing_indicator_text().lower()
    # The name is resolved from the workspace directory — the event carries only
    # a user id, because Messaging holds no names.
    assert ADA_NAME in shown, shown


@then("Grace no longer sees that Ada is typing")
def grace_stops_seeing_typing(grace: ChatPage) -> None:
    grace.expect_typing_indicator_gone()


@then(parsers.parse('Ada sees "{body}" in the channel before it is confirmed'))
def ada_sees_pending(ada: ChatPage, body: str) -> None:
    seen = ada.pending_seen()
    assert body in seen, seen


@then("Ada sees that message in the channel before it is confirmed")
def ada_sees_something_pending(ada: ChatPage) -> None:
    """The rejected send has to have been *shown* before it can be rolled back.

    That rollback is what makes this scenario different from the same rejection
    over REST: there, nothing ever appeared.
    """
    assert ada.pending_seen(), "nothing was rendered optimistically"


@then(parsers.parse('Ada sees "{body}" confirmed'))
def ada_sees_confirmed(ada: ChatPage, body: str) -> None:
    ada.wait_for_confirmed(body)


@then("Ada's message box still holds what she typed")
def adas_box_still_holds(ada: ChatPage) -> None:
    """Nothing typed is lost when the server says no.

    The draft is cleared on send — the message is already on screen — and put
    back if the send is refused.
    """
    assert ada.draft() != ""
