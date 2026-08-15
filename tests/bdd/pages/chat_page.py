"""The chat shell, as the scenarios talk about it.

Every selector in the suite lives in a page object; no step definition contains
one. That is the rule that keeps browser tests from rotting — when a component
is restructured, one file changes rather than twenty.

Selectors are `data-testid` only. Text and CSS classes are things a designer
should be free to change without breaking a test about channels.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


class ChatPage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url

    # --- navigation -------------------------------------------------------

    def open(self) -> None:
        """Load the app fresh, as someone arriving would.

        `networkidle` matters here: the session restores from the refresh cookie
        and *then* fetches channels, so a test that looked immediately after
        load would race the list it is about to assert on.
        """
        self.page.goto(self.base_url)
        self.page.wait_for_load_state("networkidle")

    # --- reading ----------------------------------------------------------

    def workspace_name(self) -> str:
        return self.page.get_by_test_id("workspace-name").inner_text()

    def channel_names(self) -> list[str]:
        """Every channel in the sidebar, in the order it is displayed."""
        self._settle()
        items = self.page.get_by_test_id("channel-list-item")
        return [
            (items.nth(i).get_attribute("data-channel-name") or "").strip()
            for i in range(items.count())
        ]

    def open_channel_name(self) -> str:
        return self.page.get_by_test_id("channel-header-name").inner_text().lstrip("# ").strip()

    def _settle(self) -> None:
        """Wait for the channel list to finish its first load.

        The sidebar renders a loading state before either a list or an empty
        message, and reading through it would return an empty list that looks
        exactly like "no channels".
        """
        self.page.get_by_test_id("channel-list-loading").wait_for(state="detached", timeout=10_000)

    # --- creating ---------------------------------------------------------

    def create_channel(self, name: str) -> None:
        self.page.get_by_test_id("create-channel-name").fill(name)
        self.page.get_by_test_id("create-channel-submit").click()

    def create_channel_and_wait(self, name: str) -> None:
        """Create a channel and wait until the app has navigated into it."""
        self.create_channel(name)
        expect(self.page.get_by_test_id("channel-view")).to_be_visible()

    def create_channel_expecting_failure(self, name: str) -> None:
        self.create_channel(name)
        # Either an error appears or the app navigates away; waiting for the
        # error explicitly turns "it silently succeeded" into a clear failure
        # rather than a later, more confusing one.
        self.error_message()

    def error_message(self) -> str:
        """Whatever the create form is complaining about.

        Field-level problems (the naming rules) render against the input;
        anything without a field, such as a duplicate name, renders in the
        banner. A scenario only cares that the user was told.
        """
        field = self.page.get_by_test_id("create-channel-name-error")
        banner = self.page.get_by_test_id("create-channel-error")
        field.or_(banner).first.wait_for(state="visible", timeout=10_000)
        return field.inner_text() if field.count() else banner.inner_text()
