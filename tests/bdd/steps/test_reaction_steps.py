"""Step definitions for reactions.feature.

Named `test_*` for the reason the other step modules give: `scenarios()`
generates its test functions into this module, and a module pytest does not
collect is a feature file that silently never runs. This is the only module that
calls `scenarios()` on `reactions.feature`.

`Given Grace is watching the "…" channel` is this feature's own phrasing and
stays here rather than in `steps/conftest.py`. It is more than "Grace opens the
channel": the server puts a connection in a room only once it has checked the
channel is visible, so a reaction sent before that acknowledgement reaches
nobody, and the scenario would fail for a reason that has nothing to do with
reactions.

No selectors. A step says what a person did; `pages/chat_page.py` knows what to
click.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then

from bdd.pages.chat_page import ChatPage

pytestmark = pytest.mark.bdd

scenarios("../features/reactions.feature")


# --- given ----------------------------------------------------------------


@given(parsers.parse('Grace is watching the "{name}" channel'))
def grace_is_watching(grace: ChatPage, name: str) -> None:
    grace.open()
    grace.open_channel(name)
    grace.wait_for_channel_joined()


# --- then -----------------------------------------------------------------
#
# `Ada reacts to …` and `Grace sees … reaction` are in `steps/conftest.py`, shared
# with message_actions.feature.


@then(parsers.parse('Ada sees "{body}" with {count:d} "{emoji}" reaction'))
def ada_sees_reaction(ada: ChatPage, body: str, count: int, emoji: str) -> None:
    assert ada.has_reaction_count(body, emoji, count)
