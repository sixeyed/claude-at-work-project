"""Step definitions for channels.feature.

Named `test_*` because this is the module pytest collects: `scenarios()` below
generates one test function per scenario *into this module*, so a file pytest
skips is a feature file that silently never runs.

Only the phrasing this feature introduces lives here. The steps two feature
files share — who is signed in, which channels exist, what is in whose sidebar
— moved to `steps/conftest.py` when `permissions.feature` arrived, because
pytest-bdd cannot see a step defined in a sibling `test_*.py`.

No selectors here — every one belongs to a page object (`tests/bdd/pages/`).
A step says what a person did; the page object knows what to click.

The naming rules, renaming and archiving are proven lower down (register D32):
unit `validate_name`, Messaging's integration tests, and the Vitest
`CreateChannelDialog`, `ChannelHeader` and `ChannelList` tests.
"""

from __future__ import annotations

import pytest
from pytest_bdd import parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage

pytestmark = pytest.mark.bdd

scenarios("../features/channels.feature")


# --- when -----------------------------------------------------------------


@when(parsers.parse('Ada creates a public channel named "{name}"'))
def ada_creates(ada: ChatPage, name: str) -> None:
    ada.create_channel_and_wait(name)


# --- then -----------------------------------------------------------------


@then(parsers.parse('Ada sees the "{name}" workspace'))
def ada_sees_workspace(ada: ChatPage, name: str) -> None:
    assert ada.workspace_name() == name
