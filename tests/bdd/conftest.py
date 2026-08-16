"""Harness for the full-stack Gherkin suite.

These scenarios run against a Compose stack, not against containers they start
themselves. That is deliberate: it is the environment the feature is
demonstrated in, so "the scenarios pass" and "the demo works" are the same
fact, and iterating on a step does not cost a stack restart.

**But not the stack you demo on.** `reset_messaging` below truncates the
messaging tables between scenarios, because a scenario asserting "Ada's channel
list is empty" cannot pass with someone's real channels in the workspace. Run
against the ordinary stack that silently deletes hand-made data, which it did
once before this was fixed. So the suite requires the throwaway stack from
`docker-compose.test.yml`, which Compose gives its own volumes, and refuses to
run without it — see `stack_ready`.

**Sign-in happens once per user, into a context that stays alive.** The obvious
alternative — sign in once and reuse a saved Playwright `storage_state` — is
actively harmful here. The refresh token rotates on every use (Conventions
§5.1) and `App.tsx` spends it on every page load, and Auth *reuse-detects*: a
replayed token revokes the whole chain (`auth/sessions.py`). A cached
`storage_state` is therefore single-use, and the second scenario to load it
would sign the user out of every other context too. A live context rotates its
cookie in place and has no such problem.

Isolation between scenarios comes from truncating the messaging tables instead.
Auth's tables are left alone, because that is where the sessions live.

Everything here is synchronous. The root `pytest.ini` sets
`asyncio_mode = "auto"`, so an `async def` step would be collected as an
asyncio test and Playwright's sync API cannot be called from inside a running
event loop.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Coroutine, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import asyncpg
import pytest
from playwright.sync_api import Browser, BrowserContext

from bdd.pages.chat_page import ChatPage
from bdd.pages.sign_in_page import SignInPage

ADA = "ada@collabhub.dev"
GRACE = "grace@collabhub.dev"

#: The workspace both users work in. Each account also owns a personal one, and
#: two people in two personal workspaces cannot see each other's channels —
#: correct, and useless for a scenario about two people.
SHARED_WORKSPACE = os.environ.get("AUTH_DEMO_WORKSPACE_NAME", "CollabHub Demo")

#: Child table first — `channel_members` references `channels`.
MESSAGING_TABLES = "channel_members, channels"

#: Scenarios whose slice has not been built yet.
#:
#: The Gherkin for slices 2 to 6 was written and approved up front, all at once,
#: so the contract for a slice exists before anyone writes code against it. The
#: cost of that is a suite full of scenarios with no step definitions, which
#: would be red from the moment they landed and stay red for weeks — and a suite
#: that is expected to be red is one nobody reads. This tag is the answer: the
#: scenarios are merged, visible and skipped.
#:
#: **Each slice's first build step is to delete this tag from its own scenarios**
#: and watch them fail for the right reason. Nobody deletes it from anyone
#: else's — a slice that un-ignores the next slice's scenarios has only made the
#: suite red again, one slice earlier than before.
PENDING_TAG = "pending"


def pytest_bdd_apply_tag(tag: str, function: Callable[..., object]) -> object:
    """Turn `@pending` into a skip; leave every other tag to pytest-bdd.

    `pytest_bdd_apply_tag` is `firstresult=True`, so returning a value here
    short-circuits the default implementation — which applies a marker of the
    same name and lets the scenario run. Returning `None` for anything else
    hands `@bdd` and `@smoke` back to that default untouched.
    """
    if tag != PENDING_TAG:
        return None
    return pytest.mark.skip(
        reason=f"@{PENDING_TAG}: the slice that owns this scenario has not been built yet"
    )(function)


_UP = "    docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build\n"

_STACK_HINT = (
    "The CollabHub *test* stack is not answering at {url}.\n\n"
    "This suite truncates the messaging tables before every scenario, so it runs\n"
    "against a throwaway stack rather than your development one — which can stay\n"
    "up alongside it, on its usual ports:\n\n" + _UP
)

_WRONG_STACK_HINT = (
    "The services answered, but nothing is listening on Postgres port {port}.\n\n"
    "That port belongs to the *test* stack. Something is serving CollabHub on the\n"
    "test HTTP ports without it — most likely a half-started stack. Bring it up\n"
    "properly rather than letting this suite truncate a database it has not\n"
    "confirmed is disposable:\n\n" + _UP
)


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@pytest.fixture(scope="session")
def base_url() -> str:
    """Where the SPA is served.

    The test stack's frontend container, not `npm run dev`. In dev, React's
    StrictMode double-invokes the effect that restores the session, which fires
    two `/auth/refresh` calls with one rotating cookie and trips reuse
    detection. The built bundle behind Nginx does not.
    """
    return _env("COLLABHUB_BASE_URL", f"http://localhost:{_env('BDD_FRONTEND_PORT', '5183')}")


@pytest.fixture(scope="session")
def bdd_postgres_port() -> str:
    """The host port the *test* stack publishes Postgres on.

    Not 5432, and none of the ports below are the development stack's either.
    That is the interlock: nothing here can tell two stacks apart by looking at
    `/health/ready`, because they are the same images — so the suite only ever
    addresses ports that exist while the test stack is up. Aimed at a machine
    running only the development stack, it fails to connect rather than
    truncating a database someone is using.
    """
    return _env("BDD_POSTGRES_PORT", "5442")


@pytest.fixture(scope="session")
def messaging_dsn(bdd_postgres_port: str) -> str:
    """Messaging's database, reached from the host rather than the network.

    Compose publishes Postgres on the host, so the suite connects to
    `localhost` while the services connect to `postgres`.
    """
    user = _env("POSTGRES_USER", "collabhub")
    password = _env("POSTGRES_PASSWORD", "collabhub")
    return f"postgresql://{user}:{password}@localhost:{bdd_postgres_port}/collabhub_messaging"


def _reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.status < 500
    except (URLError, OSError):
        return False


@pytest.fixture(scope="session", autouse=True)
def stack_ready(base_url: str, messaging_dsn: str, bdd_postgres_port: str) -> None:
    """Fail with an instruction rather than a timeout when nothing is running.

    A readiness probe that times out tells you a browser could not reach a page.
    This tells you what to type.

    The database check is the important one, and it runs last on purpose: the
    services answering on their usual ports proves *a* stack is up, not that it
    is the disposable one. Postgres on the test port is what proves that, and
    failing here is what stops the suite truncating someone's demo data.
    """
    for url in (
        f"http://localhost:{_env('BDD_AUTH_PORT', '8011')}/health/ready",
        f"http://localhost:{_env('BDD_MESSAGING_PORT', '8012')}/health/ready",
        base_url,
    ):
        if not _reachable(url):
            pytest.fail(_STACK_HINT.format(url=url), pytrace=False)

    try:
        _run_off_loop(_ping, messaging_dsn)
    except OSError:
        pytest.fail(_WRONG_STACK_HINT.format(port=bdd_postgres_port), pytrace=False)


async def _ping(dsn: str) -> None:
    await (await asyncpg.connect(dsn)).close()


async def _truncate(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute(f"TRUNCATE {MESSAGING_TABLES} RESTART IDENTITY CASCADE")
    finally:
        await connection.close()


def _run_off_loop(work: Callable[[str], Coroutine[Any, Any, None]], dsn: str) -> None:
    """Run one coroutine on a thread of its own.

    `asyncio_mode = "auto"` means pytest-asyncio may already have a loop running
    on this thread, and `asyncio.run` refuses to nest. Rather than make the whole
    harness async — which Playwright's sync API cannot be driven from — the async
    work gets its own thread and its own loop.
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(lambda: asyncio.run(work(dsn))).result()


@pytest.fixture(autouse=True)
def reset_messaging(messaging_dsn: str, stack_ready: None) -> None:
    """Empty the messaging tables before each scenario.

    Only messaging's. Truncating Auth would invalidate the sessions the
    long-lived browser contexts are holding, and every scenario after the first
    would find itself signed out.

    This is why the suite insists on the test stack: `stack_ready` has already
    proved the database on the other end of this DSN is the disposable one.
    """
    _run_off_loop(_truncate, messaging_dsn)


def _signed_in_context(browser: Browser, base_url: str, email: str) -> Iterator[BrowserContext]:
    context = browser.new_context()
    page = context.new_page()

    sign_in = SignInPage(page, base_url)
    sign_in.sign_in(email)
    sign_in.use_workspace(SHARED_WORKSPACE)

    # Done once per user, not per scenario: the refresh cookie remembers the
    # workspace, so every later page load in this context comes back to it.
    page.close()
    yield context
    context.close()


@pytest.fixture(scope="session")
def ada_context(browser: Browser, base_url: str, stack_ready: None) -> Iterator[BrowserContext]:
    yield from _signed_in_context(browser, base_url, ADA)


@pytest.fixture(scope="session")
def grace_context(browser: Browser, base_url: str, stack_ready: None) -> Iterator[BrowserContext]:
    yield from _signed_in_context(browser, base_url, GRACE)


@pytest.fixture
def ada(ada_context: BrowserContext, base_url: str) -> Iterator[ChatPage]:
    page = ada_context.new_page()
    yield ChatPage(page, base_url)
    page.close()


@pytest.fixture
def grace(grace_context: BrowserContext, base_url: str) -> Iterator[ChatPage]:
    page = grace_context.new_page()
    yield ChatPage(page, base_url)
    page.close()
