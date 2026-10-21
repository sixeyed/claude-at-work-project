"""Step definitions for display_names.feature.

Named `test_*` for the reason the other step modules give: `scenarios()` generates
its test functions into this module, and a module pytest does not collect is a
feature file that silently never runs. This is the **only** module that calls
`scenarios()` on `display_names.feature`.

The shared vocabulary — `Ada is signed in`, creating a channel, `Grace opens
CollabHub` — is in `steps/conftest.py`. What is here is what this feature
introduced: Alan, who is used by no other scenario, so his new name needs no undoing
(Auth's tables survive between scenarios, and renaming to the name he already has is a
no-op, so a `KEEP_STACK` rerun still passes).

The rules themselves — trimming, normal form, the refused characters, the 409, the
suffix on a first sign-in, the migration, the clock — are proven lower down (register
D32): unit `test_names`, Auth's integration tests and the Vitest `SettingsPage` and
`App.settings` tests. This journey proves the one thing only a second browser can: a
rename made in one window is what another person's window shows.

`Grace sees "…" written by Alan Turing` is the vocabulary's bare form (doc 00,
section 15), its tail read as a display name. The `written by Ada` step in
`test_message_steps.py` binds in that module alone, so the two never meet. No
selectors: a step says what a person did, and `pages/chat_page.py` knows what to click.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage

pytestmark = pytest.mark.bdd

scenarios("../features/display_names.feature")


@given(parsers.re(r'Alan has sent "(?P<body>[^"]*)" in "(?P<channel>[^"]*)"'))
def alan_has_sent(alan: ChatPage, body: str, channel: str) -> None:
    alan.open()
    alan.open_channel(channel)
    alan.send_message_and_wait(body)


@when(parsers.re(r'Alan changes his display name to "(?P<name>[^"]*)" in Settings'))
def alan_changes_his_name(alan: ChatPage, name: str) -> None:
    alan.open_settings()
    alan.change_display_name(name)


@then(parsers.re(r'Alan sees "(?P<name>[^"]*)" as his name'))
def alan_sees_his_name(alan: ChatPage, name: str) -> None:
    """The sidebar names him at once, with no reload: the rename's own tab."""
    assert alan.has_current_user(name)


@then(parsers.re(r'Grace sees "(?P<body>[^"]*)" written by (?P<name>.+)'))
def grace_sees_author(grace: ChatPage, body: str, name: str) -> None:
    """Grace loaded the workspace directory after the rename, so it holds the new name."""
    assert grace.has_author(body, name), grace.author_of(body)
