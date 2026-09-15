"""The layer rules `testkit.plugin` enforces (register D32).

Each test lays out a throwaway repo under pytester's temp directory and runs
pytest on it **in a subprocess**. In-process, the inner session's socket guard
would run inside this unit test's own, and the inner teardown would switch the
network back on under the outer test.
"""

from __future__ import annotations

import textwrap

import pytest

DEMO = "src/services/demo/tests"


@pytest.fixture
def repo(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
    """A repo root the plugin measures `src/services/...` from.

    The ini file pins pytest's rootdir to it. `DOCKER_HOST` is cleared because
    this outer test runs as a unit test too, and the subprocess inherits its
    environment: the dead address the outer plugin set would make the inner
    Docker test pass without the inner plugin doing anything.
    """
    pytester.makeini("[pytest]\naddopts = --import-mode=importlib\n")
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    return pytester


def write(pytester: pytest.Pytester, path: str, source: str) -> None:
    target = pytester.path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(source))


def run(pytester: pytest.Pytester, *args: str) -> pytest.RunResult:
    return pytester.runpytest_subprocess(*args, timeout=60)


PASSING = """
def test_it():
    pass
"""


# --- the directory decides the layer ---------------------------------------


def test_a_test_under_unit_is_selected_by_the_unit_marker(repo):
    """Breaks if the plugin does not mark `tests/unit/` as `unit`."""
    write(repo, f"{DEMO}/unit/test_a.py", PASSING)

    run(repo, "-m", "unit").assert_outcomes(passed=1)


def test_a_test_under_integration_is_selected_by_the_integration_marker(repo):
    """Breaks if the plugin does not mark `tests/integration/` as `integration`,
    or marks it `unit` as well."""
    write(repo, f"{DEMO}/integration/test_a.py", PASSING)

    run(repo, "-m", "integration and not unit").assert_outcomes(passed=1)


def test_a_test_outside_both_layers_stops_the_run(repo):
    """The old failure: a file that forgot its marker ran as a unit test.

    Breaks if a stray file is collected at all, or the message does not say
    which file and where it should go.
    """
    write(repo, f"{DEMO}/test_stray.py", PASSING)

    result = run(repo)

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(
        ["*src/services/demo/tests/test_stray.py is not under tests/unit/ or tests/integration/*"]
    )


def test_a_marker_that_contradicts_the_directory_stops_the_run(repo):
    """Breaks if an `integration` marker can smuggle a test into the unit
    directory — the file has to move instead."""
    write(
        repo,
        f"{DEMO}/unit/test_a.py",
        """
        import pytest

        pytestmark = pytest.mark.integration

        def test_it():
            pass
        """,
    )

    result = run(repo)

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*test_a.py is marked integration but lives under tests/unit/*"])


def test_tests_outside_src_services_are_left_alone(repo):
    """The Gherkin suite at `tests/bdd` belongs to neither layer.

    Breaks if the plugin errors on it or marks it. Passes before the plugin
    exists — it guards against an implementation that is too eager.
    """
    write(repo, "tests/bdd/test_journey.py", PASSING)

    run(repo, "-m", "not unit and not integration").assert_outcomes(passed=1)


# --- a unit test has no network and no Docker -------------------------------


def test_a_unit_test_cannot_open_a_network_socket(repo):
    """Breaks if a unit test can create an AF_INET socket."""
    write(
        repo,
        f"{DEMO}/unit/test_dial.py",
        """
        import socket

        def test_it():
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()
        """,
    )

    result = run(repo)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*SocketBlockedError*"])


def test_a_unit_test_can_still_run_an_event_loop(repo):
    """asyncio's self-pipe is an AF_UNIX socketpair.

    Breaks if the guard blocks Unix sockets, which would fail every async unit
    test. Passes before the plugin exists.
    """
    write(
        repo,
        f"{DEMO}/unit/test_loop.py",
        """
        import asyncio

        def test_it():
            asyncio.run(asyncio.sleep(0))
        """,
    )

    run(repo).assert_outcomes(passed=1)


def test_a_unit_test_points_docker_clients_at_an_unreachable_host(repo):
    """Docker's default transport is a Unix socket, which the socket guard allows.

    Pins `DOCKER_HOST` rather than attempting a ping. Docker clients read it
    before any default, and a ping is no proof on Docker Desktop: it is reached
    through a Docker context that docker-py's `from_env()` never reads, so the
    ping fails with or without this plugin.

    Breaks if a unit test runs with `DOCKER_HOST` unset or pointing anywhere
    else.
    """
    write(
        repo,
        f"{DEMO}/unit/test_docker.py",
        """
        import os

        def test_it():
            assert os.environ.get("DOCKER_HOST") == "tcp://docker.invalid:1"
        """,
    )

    run(repo).assert_outcomes(passed=1)


def test_an_integration_test_can_open_a_network_socket(repo):
    """Breaks if the guard leaks into the integration layer. Passes before the
    plugin exists."""
    write(
        repo,
        f"{DEMO}/integration/test_dial.py",
        """
        import socket

        def test_it():
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()
        """,
    )

    run(repo).assert_outcomes(passed=1)


def test_the_network_comes_back_after_a_unit_test(repo):
    """`demo` sorts before `zeta`, so the unit test runs first.

    Breaks if teardown leaves sockets blocked for the integration test after
    it. Passes before the plugin exists.
    """
    write(repo, f"{DEMO}/unit/test_a.py", PASSING)
    write(
        repo,
        "src/services/zeta/tests/integration/test_dial.py",
        """
        import socket

        def test_it():
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()
        """,
    )

    run(repo).assert_outcomes(passed=2)


def test_docker_host_comes_back_after_a_unit_test_that_patches_it(repo):
    """`demo` sorts before `zeta`, so the unit test runs first.

    Breaks if the plugin's own teardown runs before the test's `monkeypatch`
    fixture is torn down: the plugin would restore `DOCKER_HOST` to unset
    first, then the fixture's later teardown would restore its own recorded
    "previous" value — the dead address the plugin's setup had put there —
    clobbering the cleanup and leaking it into whatever runs next.
    """
    write(
        repo,
        f"{DEMO}/unit/test_a.py",
        """
        def test_it(monkeypatch):
            monkeypatch.delenv("DOCKER_HOST", raising=False)
        """,
    )
    write(
        repo,
        "src/services/zeta/tests/integration/test_b.py",
        """
        import os

        def test_it():
            assert os.environ.get("DOCKER_HOST") is None
        """,
    )

    run(repo).assert_outcomes(passed=2)
