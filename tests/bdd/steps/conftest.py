"""Steps shared by more than one feature file.

pytest-bdd resolves a step from the module that called `scenarios()` and from
`conftest.py` — **not** from a sibling `test_*.py`. So the moment a second
feature file needs `Given Ada is signed in`, the choice is to copy the
definition or to move it down here. Copying is how a suite ends up with four
subtly different versions of its most-used step.

What belongs here is the vocabulary every feature speaks: who is signed in,
which channels exist, what is in whose sidebar. What stays in a
`test_*_steps.py` is the phrasing that feature introduced — renaming a channel
belongs to `channels.feature`, being refused a control belongs to
`permissions.feature`.

No selectors here either. A step says what a person did; the page object
(`tests/bdd/pages/`) knows what to click.
"""

from __future__ import annotations

from pytest_bdd import given, parsers, then, when

from bdd.pages.chat_page import ChatPage

#: What Auth stores as these accounts' display names.
#:
#: Dex issues its `username` as the name claim and `provision_user` keeps it, so
#: the demo accounts are called "ada" and "grace" rather than "Ada Lovelace".
#: The member panel renders those, and a scenario that adds "Grace" has to pick
#: the option the UI actually shows.
ADA_NAME = "ada"
GRACE_NAME = "grace"


# --- given ----------------------------------------------------------------


@given("Ada is signed in")
def ada_is_signed_in(ada: ChatPage) -> None:
    # The context is signed in for the whole session; this loads the app fresh
    # so each scenario starts from the same place.
    ada.open()


@given(parsers.parse('Ada has created a public channel named "{name}"'))
def ada_has_created(ada: ChatPage, name: str) -> None:
    ada.create_channel_and_wait(name)


@given(parsers.parse('Ada has created a private channel named "{name}"'))
def ada_has_created_private(ada: ChatPage, name: str) -> None:
    ada.create_private_channel_and_wait(name)


# --- when -----------------------------------------------------------------


@when("Grace opens CollabHub")
def grace_opens(grace: ChatPage) -> None:
    grace.open()


@when(parsers.parse('Grace opens the "{name}" channel'))
def grace_opens_channel(grace: ChatPage, name: str) -> None:
    grace.open_channel(name)


# --- then -----------------------------------------------------------------


@then(parsers.parse('Ada is looking at the "{name}" channel'))
def ada_is_looking_at(ada: ChatPage, name: str) -> None:
    assert ada.open_channel_name() == name


@then(parsers.parse('Grace is looking at the "{name}" channel'))
def grace_is_looking_at(grace: ChatPage, name: str) -> None:
    assert grace.open_channel_name() == name


@then(parsers.parse('"{name}" is in Ada\'s channel list'))
def in_adas_list(ada: ChatPage, name: str) -> None:
    assert name in ada.channel_names()


@then(parsers.parse('"{name}" is not in Ada\'s channel list'))
def not_in_adas_list(ada: ChatPage, name: str) -> None:
    assert name not in ada.channel_names()


@then(parsers.parse('"{name}" is in Grace\'s channel list'))
def in_graces_list(grace: ChatPage, name: str) -> None:
    assert name in grace.channel_names()


@then(parsers.parse('"{name}" is not in Grace\'s channel list'))
def not_in_graces_list(grace: ChatPage, name: str) -> None:
    assert name not in grace.channel_names()


@given(parsers.parse('Ada has sent "{body}" in "{channel}"'))
def ada_has_sent(ada: ChatPage, body: str, channel: str) -> None:
    ada.open_channel(channel)
    ada.send_message_and_wait(body)


@when(parsers.parse('Ada opens the "{name}" channel'))
def ada_opens_channel(ada: ChatPage, name: str) -> None:
    ada.open_channel(name)


@when("Ada reloads CollabHub")
def ada_reloads(ada: ChatPage) -> None:
    ada.open()


#: `parsers.re` rather than `parsers.parse`, and the reason is not style.
#:
#: `parse`'s `{body}` will happily swallow a closing quote, so
#: `Ada sends "{body}"` also matches `Ada sends "x" in "general"` with a body of
#: `x" in "general` — and which of the two definitions wins then depends on
#: fixture resolution order. `[^"]*` cannot cross a quote, so the two phrases
#: are distinguishable by the pattern itself.
@when(parsers.re(r'Ada sends "(?P<body>[^"]*)"'))
def ada_sends(ada: ChatPage, body: str) -> None:
    ada.send_message_and_wait(body)


@when(parsers.re(r'Ada sends "(?P<body>[^"]*)" in "(?P<channel>[^"]*)"'))
def ada_sends_in(ada: ChatPage, body: str, channel: str) -> None:
    ada.open_channel(channel)
    ada.send_message_and_wait(body)


@when(parsers.parse("Ada tries to send a message of {count:d} characters"))
def ada_sends_too_long(ada: ChatPage, count: int) -> None:
    ada.send_message_expecting_failure("a" * count)


@then(parsers.parse('Ada sees "{body}" in the channel'))
def ada_sees(ada: ChatPage, body: str) -> None:
    assert ada.has_message(body), ada.message_bodies()


@then(parsers.parse('Grace sees "{body}" in the channel'))
def grace_sees(grace: ChatPage, body: str) -> None:
    assert grace.has_message(body), grace.message_bodies()


@then(parsers.parse('Ada does not see "{body}" in the channel'))
def ada_does_not_see(ada: ChatPage, body: str) -> None:
    assert not ada.has_message(body), ada.message_bodies()


@then("Ada sees no messages in the channel")
def ada_sees_nothing(ada: ChatPage) -> None:
    assert ada.message_bodies() == []


@then("Ada's message box is empty")
def adas_box_is_empty(ada: ChatPage) -> None:
    assert ada.draft() == ""


@then("Ada is told the message is too long")
def ada_told_too_long(ada: ChatPage) -> None:
    shown = ada.composer_error().lower()
    assert "or fewer" in shown, shown


@when(parsers.parse('Ada edits "{old}" to say "{new}"'))
def ada_edits(ada: ChatPage, old: str, new: str) -> None:
    ada.edit_message(old, new)


@when(parsers.parse('Ada deletes "{body}"'))
def ada_deletes(ada: ChatPage, body: str) -> None:
    ada.delete_message(body)
