"""Driving the sign-in flow, all the way through the real identity provider.

Sign-in here is not simulated. The browser goes to the SPA, is redirected to
Auth, redirected on to Dex, fills in Dex's own form, and comes back — the same
two PKCE exchanges a real user causes (register D5). A faked token would prove
nothing about the part most likely to break.

The one fragile piece is Dex's login page: this clicks fields on a form
upstream owns, so a redesign there breaks these tests.
`src/services/testkit/testkit/dexflow.py` carries the same warning about
parsing that page server-side.
"""

from __future__ import annotations

import os

from playwright.sync_api import Page, expect

# Every seeded user's password. A delivery's preview on a public tunnel has its own, which the
# smoke packs are given as SMOKE_PASSWORD; the Compose stacks and k3d keep `collabhub`.
PASSWORD = os.environ.get("SMOKE_PASSWORD") or "collabhub"


class SignInPage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url

    def sign_in(self, email: str, password: str = PASSWORD) -> None:
        self.page.goto(f"{self.base_url}/sign-in")
        self.page.get_by_test_id("sign-in").click()

        # Now on Dex. Its field names are `login` and `password`; it renders
        # them without test ids, so this is the one place a raw selector is
        # unavoidable — and it is contained here rather than in a step.
        self.page.wait_for_url("**/dex/auth**")
        self.page.fill("input[name='login']", email)
        self.page.fill("input[name='password']", password)
        self.page.click("button[type='submit']")

        # Back on the SPA with a session. Waiting for the shell rather than the
        # URL means the assertion covers the token exchange too.
        expect(self.page.get_by_test_id("workspace-name")).to_be_visible()

    def use_workspace(self, name: str) -> None:
        """Switch to a named workspace, if not already in it.

        Every account lands in its *own* workspace on first sign-in and joins
        the shared demo workspace as a member (`auth/identities.py`
        `provision_user`). Two users therefore start out unable to see each
        other's channels, which is correct behaviour and useless for a
        two-person scenario — so the harness moves both into the shared one.

        This is a real token exchange, not a UI filter: the new token carries a
        different `wsp` claim (Conventions §5.4). The refresh cookie survives
        it, so later page loads stay in this workspace.
        """
        if self.page.get_by_test_id("workspace-name").inner_text() == name:
            return

        self.page.locator(f"[data-testid='workspace-option'][data-workspace-name='{name}']").click()

        expect(self.page.get_by_test_id("workspace-name")).to_have_text(name)

    def is_shown(self) -> bool:
        """Whether this browser is on the sign-in page with no session in it.

        Retrying, because getting here is a redirect that follows a failed
        session restore. The URL is checked as well as the button, so a signed-in
        shell that happened to render a sign-in control somewhere would not pass.
        """
        try:
            expect(self.page).to_have_url(f"{self.base_url}/sign-in")
            expect(self.page.get_by_test_id("sign-in")).to_be_visible()
            expect(self.page.get_by_test_id("workspace-name")).to_have_count(0)
        except AssertionError:
            return False
        return True

    def error(self) -> str:
        return self.page.get_by_test_id("sign-in-error").inner_text()
