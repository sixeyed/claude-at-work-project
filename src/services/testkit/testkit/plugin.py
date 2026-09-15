"""CollabHub's pytest plugin: the directory decides a test's layer (register D32).

Registered through the `pytest11` entry point in testkit's pyproject, so every
pytest run in the workspace loads it without a conftest import.

Under `src/services/<service>/tests/`, a test in `unit/` is marked `unit` and
one in `integration/` is marked `integration`. A test anywhere else there stops
the run. Before this the layer was a `pytestmark` line, and a file that forgot
it ran in the unit layer, reaching for containers it had no business with.

A unit test gets no network and no Docker. Sockets other than Unix-domain ones
are refused — asyncio's self-pipe is an AF_UNIX socketpair, so an event loop
still works — and `DOCKER_HOST` points at an address that cannot resolve,
because the Docker SDK's default is a Unix socket the guard would let through.

Paths outside `src/services` — the Gherkin suite in `tests/bdd` — are left alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_socket import disable_socket, enable_socket

#: Loaded through this plugin rather than imported into conftests, so each
#: fixture has exactly one definition — and a session fixture one container —
#: however many services' tests request it (register D34). Nothing here imports
#: them: a module imported before pytest registers it escapes assert rewriting.
pytest_plugins = ["testkit.containers", "testkit.tokens"]

#: The fixtures in `testkit.containers` that start a container. A unit test
#: depending on any of them, directly or through another fixture, stops the run.
CONTAINER_FIXTURES = frozenset({"postgres_server", "redis_server", "elasticsearch_url"})

UNIT = "unit"
INTEGRATION = "integration"
LAYERS = (UNIT, INTEGRATION)
UNREACHABLE_DOCKER = "tcp://docker.invalid:1"

_environment = pytest.StashKey[pytest.MonkeyPatch]()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "unit: no network, no Docker — set by living in a service's tests/unit/"
    )
    config.addinivalue_line(
        "markers",
        "integration: real dependencies started by testcontainers — set by living in tests/integration/",
    )


def layer_of(path: Path, root: Path) -> str | None:
    """`unit` or `integration` for a test in a service's tests, None outside them.

    Raises `pytest.UsageError` for a test file in a service's `tests/` that is
    in neither layer's directory.
    """
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return None
    if len(parts) < 5 or parts[:2] != ("src", "services") or parts[3] != "tests":
        return None
    if len(parts) > 5 and parts[4] in LAYERS:
        return parts[4]
    raise pytest.UsageError(
        f"{Path(*parts)} is not under tests/unit/ or tests/integration/"
        " — the directory decides a test's layer."
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        layer = layer_of(item.path, config.rootpath)
        if layer is None:
            continue
        for other in LAYERS:
            if other != layer and item.get_closest_marker(other):
                raise pytest.UsageError(
                    f"{item.path.relative_to(config.rootpath)} is marked {other} but lives"
                    f" under tests/{layer}/ — move the file rather than marking it."
                )
        if layer == UNIT:
            # `fixturenames` is the closure, so a container reached through
            # another fixture is caught too.
            containers = sorted(CONTAINER_FIXTURES.intersection(item.fixturenames))
            if containers:
                raise pytest.UsageError(
                    f"{item.path.relative_to(config.rootpath)} is a unit test but depends on a"
                    f" container fixture: {', '.join(containers)} — move it to tests/integration/."
                )
        item.add_marker(layer)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    # tryfirst, so the guard is up before the item's fixtures are set up — a
    # unit fixture that dials out fails as surely as the test would.
    if item.get_closest_marker(UNIT) is None:
        return
    environment = pytest.MonkeyPatch()
    environment.setenv("DOCKER_HOST", UNREACHABLE_DOCKER)
    item.stash[_environment] = environment
    disable_socket(allow_unix_socket=True)


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: pytest.Item) -> None:
    # trylast, so it runs after fixture teardown and undoes the guard
    # outermost, after a test's own monkeypatch has undone its changes.
    environment = item.stash.get(_environment, None)
    if environment is None:
        return
    enable_socket()
    environment.undo()
