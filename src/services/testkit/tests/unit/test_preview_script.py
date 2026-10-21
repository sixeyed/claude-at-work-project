"""The preview functions in `scripts/lib` and the `preview` command of `deploy.sh`.

Each test runs the real bash under `/bin/bash` (3.2 on macOS) as a subprocess,
with an environment built from nothing and a fake `cloudflared` and `curl` on `PATH`,
so no developer's `APP_ORIGIN`, `BRANCH` or installed `cloudflared` reaches it. Neither
bash nor the fakes touch the network or Docker.

`scripts/lib/preview.sh` doesn't exist until the code is built, so the helper
sources it only if it is there: each test then fails on its own
`command not found` and the `common.sh` tests aren't hidden behind a load failure.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
BASH = "/bin/bash"
URL = re.compile(r"https://[a-z0-9]+(-[a-z0-9]+)+\.trycloudflare\.com")

# No `exec`: the process keeps "cloudflared tunnel" in its command line, as the
# real one does, or tunnel_alive couldn't be tested.
FAKE_CLOUDFLARED = """#!/bin/bash
echo $$ >>"$FAKE_CLOUDFLARED_PIDS"
printf '%s\\n' "$*" >>"$FAKE_CLOUDFLARED_ARGS"
echo "2026-10-15T10:00:00Z INF Requesting new quick Tunnel on trycloudflare.com..." >&2
[ "${FAKE_TUNNEL_SILENT:-}" = 1 ] ||
    echo "2026-10-15T10:00:01Z INF |  https://fake-$$-tunnel.trycloudflare.com  |" >&2
while :; do sleep 1; done
"""

# A quick tunnel can outlive its URL: when its connection drops for long enough — the
# laptop sleeps — Cloudflare deletes the tunnel, and the process retries for ever with
# "Tunnel not found". So liveness asks the URL too. This fake answers as curl would:
# the status from FAKE_CURL_CODES ("<url> <code>" lines; 200 when unlisted) on stdout
# for -w, exit 22 under -f/--fail for 400 and up, and "000" with exit 6 for 000 — no
# such host, which is what a deleted tunnel's name becomes. Every URL asked is logged.
FAKE_CURL = """#!/bin/bash
url="" fail=0 write=0
for arg in "$@"; do
    case "$arg" in
        --fail) fail=1 ;;
        --write-out | -w) write=1 ;;
        https://*) url="$arg" ;;
        --*) ;;
        -*f*) fail=1 ;;
    esac
done
printf '%s\\n' "$url" >>"$FAKE_CURL_ASKED"
code="$(awk -v u="$url" '$1 == u { print $2 }' "$FAKE_CURL_CODES" | tail -n 1)"
code="${code:-200}"
[ "$write" = 1 ] && printf '%s' "$code"
[ "$code" = 000 ] && exit 6
[ "$fail" = 1 ] && [ "$code" -ge 400 ] && exit 22
exit 0
"""

TUNNEL_ARGS = ["tunnel", "--no-autoupdate", "--url", "http://localhost:8080"]
APP_URL = "https://quiet-fox-runs.trycloudflare.com"
S3_URL = "https://bold-owl-sings.trycloudflare.com"

# Branch names around the 63-character limit. "preview-" is 8 characters.
B55 = "feature/" + "a" * 47  # slug 55 → namespace exactly 63
B56 = "feature/" + "a" * 48  # 64 before the cut
B56U = "feature_" + "a" * 48  # the same slug as B56
BDASH = "feature/" + "b" * 39 + "/" + "c" * 20  # the 56th character of the name is "-"


def _sha6(branch: str) -> str:
    """First 6 hex of sha1(branch) — what `printf %s <branch> | shasum -a 1` gives."""
    return hashlib.sha1(branch.encode(), usedforsecurity=False).hexdigest()[:6]


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def _wait_until(condition: Callable[[], bool], seconds: float = 8.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


class Sandbox:
    """A temp dir, a fake `cloudflared`, an env built from nothing, and cleanup."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.bin = root / "bin"
        self.bin.mkdir()
        self.fake = self.bin / "cloudflared"
        self.fake.write_text(FAKE_CLOUDFLARED)
        self.fake.chmod(0o755)
        self.curl = self.bin / "curl"
        self.curl.write_text(FAKE_CURL)
        self.curl.chmod(0o755)
        self.curl_codes = root / "fake-curl-codes"
        self.curl_asked = root / "fake-curl-asked"
        self.curl_codes.touch()
        self.curl_asked.touch()
        self.pids = root / "fake-pids"
        self.args = root / "fake-args"
        self.pids.touch()
        self.args.touch()
        self.state = root / "state"
        self.procs: list[subprocess.Popen[str]] = []

    def env(self, **extra: str) -> dict[str, str]:
        path = [str(self.bin), "/usr/bin", "/bin"]
        git = shutil.which("git")
        if git and str(Path(git).parent) not in path:
            path.append(str(Path(git).parent))
        env = {
            "PATH": ":".join(path),
            "HOME": str(self.root),
            "IMAGE_TAG": "t",
            "PREVIEW_STATE_ROOT": str(self.state),
            "FAKE_CLOUDFLARED_ARGS": str(self.args),
            "FAKE_CLOUDFLARED_PIDS": str(self.pids),
            "FAKE_CURL_CODES": str(self.curl_codes),
            "FAKE_CURL_ASKED": str(self.curl_asked),
        }
        env.update(extra)
        return env

    def run(
        self, argv: list[str], env: dict[str, str], cwd: Path = REPO
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 — argv is the test's own: /bin/bash and literals
            argv, env=env, cwd=cwd, text=True, capture_output=True, timeout=30, check=False
        )

    def fn(self, snippet: str, **extra: str) -> subprocess.CompletedProcess[str]:
        script = (
            "set -u; . scripts/lib/common.sh; "
            "[ ! -f scripts/lib/preview.sh ] || . scripts/lib/preview.sh; " + snippet
        )
        done = self.run([BASH, "-c", script], self.env(**extra))
        # 127 is a function or script that isn't there — the red this file is waiting on.
        # Say so here, rather than let each test fail on an empty stdout.
        assert done.returncode != 127, f"missing: {done.stderr.strip()}"
        return done

    def deploy(self, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return self.run([BASH, "scripts/deploy.sh", *args], self.env(**extra))

    def spawn(self, argv: list[str]) -> subprocess.Popen[str]:
        proc = subprocess.Popen(  # noqa: S603 — argv is the test's own: /bin/bash, the fake, literals
            argv,
            env=self.env(),
            cwd=REPO,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.procs.append(proc)
        return proc

    def spawn_fake(self) -> subprocess.Popen[str]:
        proc = self.spawn([BASH, str(self.fake), *TUNNEL_ARGS])
        # The fake has written its own pid once it is running its script.
        assert _wait_until(lambda: str(proc.pid) in self.pids.read_text().split()), "fake not up"
        return proc

    def fake_pids(self) -> list[int]:
        return [int(p) for p in self.pids.read_text().split()]

    def kill_and_wait(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        for proc in self.procs:
            if proc.pid == pid:
                proc.wait(timeout=5)
        assert _wait_until(lambda: _gone(pid)), f"pid {pid} would not die"

    def close(self) -> None:
        for pid in self.fake_pids():
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        for proc in self.procs:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)

    def running_preview(self, namespace: str = "preview-t") -> Path:
        """Two live fakes and decision 9's state files, written by hand."""
        directory = self.state / namespace
        directory.mkdir(parents=True)
        app, s3 = self.spawn_fake(), self.spawn_fake()
        (directory / "app.pid").write_text(f"{app.pid}\n")
        (directory / "s3.pid").write_text(f"{s3.pid}\n")
        (directory / "app.url").write_text(APP_URL + "\n")
        (directory / "s3.url").write_text(S3_URL + "\n")
        return directory


@pytest.fixture
def sb(tmp_path: Path) -> Iterator[Sandbox]:
    sandbox = Sandbox(tmp_path)
    yield sandbox
    sandbox.close()


def _namespace(sb: Sandbox, branch: str) -> subprocess.CompletedProcess[str]:
    return sb.fn(f"preview_namespace {shlex.quote(branch)}")


def _repo_on(sb: Sandbox, branch: str) -> Path:
    repo = sb.root / "repo"
    repo.mkdir()
    env = sb.env()
    git = ["/usr/bin/git", "-C", str(repo)]
    for argv in (
        [*git, "init", "-q"],
        [*git, "symbolic-ref", "HEAD", f"refs/heads/{branch}"],
        [
            *git,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "one",
        ],
    ):
        done = sb.run(argv, env)
        assert done.returncode == 0, done.stderr
    return repo


# --- R1: the namespace ------------------------------------------------------


def test_a_branch_is_lowercased_and_separators_become_dashes(sb: Sandbox) -> None:
    """A wrong slug deploys to a namespace the next `up` and `down` can't find."""
    done = _namespace(sb, "Feature/ISSUE_6")

    assert done.stdout.strip() == "preview-feature-issue-6"
    assert done.returncode == 0


def test_runs_of_dashes_collapse_and_the_ends_are_trimmed(sb: Sandbox) -> None:
    """Namespaces can't hold `--` runs or start and end with a dash."""
    assert _namespace(sb, "--Feature//a__b--").stdout.strip() == "preview-feature-a-b"


def test_bytes_outside_a_to_z_and_digits_become_dashes(sb: Sandbox) -> None:
    """Every byte, so macOS and Linux agree whatever the locale (decision 21)."""
    assert _namespace(sb, "fé/x").stdout.strip() == "preview-f-x"


def test_main_is_allowed(sb: Sandbox) -> None:
    """`main` is a branch like any other."""
    assert _namespace(sb, "main").stdout.strip() == "preview-main"


def test_a_name_of_exactly_63_is_not_cut(sb: Sandbox) -> None:
    """63 is within the limit: no suffix, or two namespaces of one branch would exist."""
    name = _namespace(sb, B55).stdout.strip()

    assert name == "preview-feature-" + "a" * 47
    assert len(name) == 63


def test_a_name_of_64_is_cut_and_suffixed_within_63(sb: Sandbox) -> None:
    """One character over the limit is cut to 56 and suffixed with the branch's hash."""
    name = _namespace(sb, B56).stdout.strip()

    assert name == "preview-feature-" + "a" * 40 + "-" + _sha6(B56)
    assert len(name) == 63


def test_the_suffix_hashes_the_branch_not_the_slug(sb: Sandbox) -> None:
    """Two long branches with one slug still get different namespaces."""
    first = _namespace(sb, B56).stdout.strip()
    second = _namespace(sb, B56U).stdout.strip()

    assert first[:56] == second[:56]
    assert first != second
    assert second.endswith("-" + _sha6(B56U))
    assert _sha6(B56) != _sha6(B56U)


def test_a_cut_ending_in_a_dash_is_trimmed_before_the_suffix(sb: Sandbox) -> None:
    """The join must not leave `--`: R1's runs stay collapsed across it."""
    name = _namespace(sb, BDASH).stdout.strip()

    assert name == "preview-feature-" + "b" * 39 + "-" + _sha6(BDASH)
    assert len(name) == 62
    assert "--" not in name


def test_a_branch_with_no_letters_or_digits_is_refused(sb: Sandbox) -> None:
    """`preview-` alone is no namespace (decision 20)."""
    done = _namespace(sb, "___")

    assert done.returncode != 0
    assert "has no letters or digits to name a preview after" in done.stderr
    assert done.stdout.strip() == ""


def test_branches_differing_only_in_separators_share_a_preview(sb: Sandbox) -> None:
    """Decision 7: accepted, and the same namespace is what makes it documented."""
    one = _namespace(sb, "feature/a_b").stdout.strip()
    other = _namespace(sb, "feature/a-b").stdout.strip()

    assert one == other == "preview-feature-a-b"


# --- R1: the branch ---------------------------------------------------------


def test_the_checked_out_branch_names_the_preview(sb: Sandbox) -> None:
    """With no BRANCH, the checkout's branch is the preview's."""
    repo = _repo_on(sb, "topic/x")

    done = sb.fn(f"preview_branch {shlex.quote(str(repo))}")

    assert done.stdout.strip() == "topic/x"
    assert done.returncode == 0


def test_BRANCH_overrides_the_checkout(sb: Sandbox) -> None:  # noqa: N802
    """BRANCH wins over what is checked out, or CI can't name a preview."""
    repo = _repo_on(sb, "topic/x")

    done = sb.fn(f"preview_branch {shlex.quote(str(repo))}", BRANCH="other")

    assert done.stdout.strip() == "other"


def test_a_detached_head_needs_BRANCH(sb: Sandbox) -> None:  # noqa: N802
    """A detached HEAD has no name to give a preview, unless BRANCH supplies one."""
    repo = _repo_on(sb, "topic/x")
    detached = sb.run(["/usr/bin/git", "-C", str(repo), "checkout", "-q", "--detach"], sb.env())
    assert detached.returncode == 0, detached.stderr
    quoted = shlex.quote(str(repo))

    refused = sb.fn(f"preview_branch {quoted}")
    named = sb.fn(f"preview_branch {quoted}", BRANCH="x")

    assert refused.returncode != 0
    assert "HEAD is detached — set BRANCH to name the preview" in refused.stderr
    assert named.stdout.strip() == "x"
    assert named.returncode == 0


def test_the_state_directory_is_under_the_root_or_the_git_common_dir(sb: Sandbox) -> None:
    """Decision 9: shared by every worktree, so `down` works from any checkout."""
    overridden = sb.fn("preview_state_dir preview-x")
    default_env = sb.env()
    del default_env["PREVIEW_STATE_ROOT"]
    default = sb.run(
        [
            BASH,
            "-c",
            ". scripts/lib/common.sh; . scripts/lib/preview.sh; preview_state_dir preview-x",
        ],
        default_env,
    )
    common = sb.run(["/usr/bin/git", "rev-parse", "--git-common-dir"], sb.env())

    assert overridden.stdout.strip() == f"{sb.state}/preview-x"
    expected = os.path.realpath(REPO / common.stdout.strip())
    got = default.stdout.strip()
    assert os.path.isabs(got)
    assert os.path.realpath(os.path.dirname(got)) == os.path.join(expected, "collabhub-previews")
    assert os.path.basename(got) == "preview-x"


# --- the image tag a preview deploys ----------------------------------------
#
# Every worktree branched from one commit is dirty at that commit, so every one
# tags `<sha>-dirty`. Previews left up side by side would share images: a pod
# restarted in one would pull the branch pushed last.


def test_a_dirty_tag_is_kept_apart_by_namespace(sb: Sandbox) -> None:
    seven = sb.fn("preview_image_tag abc123def456-dirty preview-feature-issue-7")
    eight = sb.fn("preview_image_tag abc123def456-dirty preview-feature-issue-8")

    assert seven.stdout == "abc123def456-preview-feature-issue-7-dirty"
    assert eight.stdout == "abc123def456-preview-feature-issue-8-dirty"


def test_a_dirty_tag_still_ends_dirty(sb: Sandbox) -> None:
    """`cmd_app` restarts the pods of a `*-dirty` tag, or a rebuild would never roll out."""
    done = sb.fn("preview_image_tag abc123def456-dirty preview-x")

    assert done.stdout.endswith("-dirty")


def test_a_clean_tag_is_shared(sb: Sandbox) -> None:
    """One commit is one build of the code: two previews of it may share the images."""
    done = sb.fn("preview_image_tag abc123def456 preview-feature-issue-7")

    assert done.stdout == "abc123def456"


# --- R4: the object store's endpoint ---------------------------------------


def test_the_object_store_endpoint_defaults_to_s3_of_the_app_origin(sb: Sandbox) -> None:
    """Plain k3d and the lab keep `s3.<host>` (R4)."""
    local = sb.fn("object_store_endpoint http://localhost:8080")
    named = sb.fn("object_store_endpoint https://a.example")

    assert local.stdout == "http://s3.localhost:8080"
    assert named.stdout == "https://s3.a.example"


def test_an_object_store_origin_is_the_endpoint_as_given(sb: Sandbox) -> None:
    """A presigned URL's host is signed: the endpoint must be the tunnel's, whole."""
    done = sb.fn(f"object_store_endpoint https://a.example {S3_URL}")

    assert done.stdout == S3_URL


def test_normalize_origin_trims_a_slash_and_refuses_a_path_or_scheme(sb: Sandbox) -> None:
    """The checks `resolve_origin` made for APP_ORIGIN, now for either origin."""
    trimmed = sb.fn("normalize_origin OBJECT_STORE_ORIGIN https://b.example/")
    with_path = sb.fn("normalize_origin OBJECT_STORE_ORIGIN https://b.example/x")
    no_scheme = sb.fn("normalize_origin OBJECT_STORE_ORIGIN b.example")

    assert trimmed.stdout == "https://b.example"
    assert trimmed.returncode == 0
    assert with_path.returncode != 0
    assert "OBJECT_STORE_ORIGIN is an origin, with no path" in with_path.stderr
    assert no_scheme.returncode != 0
    assert "OBJECT_STORE_ORIGIN must start with http:// or https://" in no_scheme.stderr


# --- R2: reading a tunnel's URL --------------------------------------------

REQUESTING = "2026-10-15T10:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...\n"
DECOY = "2026-10-15T10:00:00Z ERR Cannot reach https://api.trycloudflare.com/tunnel\n"
BANNER = "2026-10-15T10:00:01Z INF |  https://calm-otter-hums.trycloudflare.com  |\n"


def test_the_tunnel_url_is_read_past_a_decoy(sb: Sandbox) -> None:
    """The error line names api.trycloudflare.com; only the banner is a tunnel."""
    log = sb.root / "t.log"
    log.write_text(REQUESTING + DECOY + BANNER)

    done = sb.fn(f"tunnel_url_from_log {shlex.quote(str(log))}")

    assert done.stdout.strip() == "https://calm-otter-hums.trycloudflare.com"
    assert done.returncode == 0


def test_a_log_with_no_tunnel_url_gives_nothing(sb: Sandbox) -> None:
    """The decoy alone must not be mistaken for a URL."""
    log = sb.root / "t.log"
    log.write_text(REQUESTING + DECOY)

    done = sb.fn(f"tunnel_url_from_log {shlex.quote(str(log))}")

    assert done.stdout.strip() == ""
    assert done.returncode == 1


def test_waiting_returns_the_url_once_it_appears(sb: Sandbox) -> None:
    """The banner arrives after the wait begins; the wait is for it, not a fixed sleep."""
    late = sb.root / "late.log"
    late.write_text(REQUESTING)
    sb.spawn([BASH, "-c", f"sleep 1; printf '%s' {shlex.quote(BANNER)} >>{shlex.quote(str(late))}"])
    empty = sb.root / "empty.log"
    empty.write_text("")

    found = sb.fn(f"preview_wait_for_url {shlex.quote(str(late))} 5")
    missed = sb.fn(f"preview_wait_for_url {shlex.quote(str(empty))} 1")

    assert found.stdout.strip() == "https://calm-otter-hums.trycloudflare.com"
    assert found.returncode == 0
    assert missed.returncode == 1
    assert missed.stdout.strip() == ""


# --- R6: live or dead ------------------------------------------------------


def test_a_live_tunnel_is_a_running_cloudflared(sb: Sandbox) -> None:
    """`kill -0` alone is fooled by a pid a reboot handed to something else."""
    fake = sb.spawn_fake()
    reused = sb.spawn(["/bin/sleep", "30"])
    finished = sb.spawn(["/usr/bin/true"])
    finished.wait(timeout=5)

    def alive(pid: int | None) -> int:
        pidfile = sb.root / "x.pid"
        if pid is None:
            pidfile.unlink(missing_ok=True)
        else:
            pidfile.write_text(f"{pid}\n")
        return sb.fn(f"tunnel_alive {shlex.quote(str(pidfile))}").returncode

    assert alive(fake.pid) == 0
    assert alive(reused.pid) == 1
    assert alive(finished.pid) == 1
    assert alive(None) == 1


def test_starting_gives_two_tunnels_to_the_k3d_load_balancer(sb: Sandbox) -> None:
    """Two processes, two different URLs, both to localhost:8080, and the pair reads as live."""
    directory = sb.state / "preview-t"

    done = sb.fn(
        f'D={shlex.quote(str(directory))}; preview_start_tunnels "$D" 10; echo "start=$?"; '
        'preview_tunnels_live "$D"; echo "live=$?"'
    )

    assert "start=0" in done.stdout, done.stderr
    assert "live=0" in done.stdout
    pids = sb.fake_pids()
    assert len(pids) == 2
    assert not any(_gone(pid) for pid in pids)
    app_url = (directory / "app.url").read_text().strip()
    s3_url = (directory / "s3.url").read_text().strip()
    assert URL.fullmatch(app_url)
    assert URL.fullmatch(s3_url)
    assert app_url != s3_url
    assert sb.args.read_text().splitlines() == [" ".join(TUNNEL_ARGS)] * 2


def test_one_dead_tunnel_makes_the_preview_not_live(sb: Sandbox) -> None:
    """R6: either tunnel dead means new URLs for both."""
    directory = sb.state / "preview-t"
    quoted = shlex.quote(str(directory))
    sb.fn(f"preview_start_tunnels {quoted} 10")
    assert sb.fn(f"preview_tunnels_live {quoted}").returncode == 0

    sb.kill_and_wait(int((directory / "s3.pid").read_text()))

    assert sb.fn(f"preview_tunnels_live {quoted}").returncode == 1


@pytest.mark.parametrize(
    ("dead", "code"),
    [("app", "000"), ("s3", "000"), ("app", "530"), ("s3", "530")],
)
def test_a_running_tunnel_whose_url_is_gone_makes_the_preview_not_live(
    sb: Sandbox, dead: str, code: str
) -> None:
    """R6 after a sleep: both processes still run, but Cloudflare has deleted one tunnel.

    Its hostname no longer resolves (000), or Cloudflare answers 530 for a tunnel with
    no connection. Either way the URL is dead, and reusing it would print a preview
    nobody can open.
    """
    directory = sb.running_preview()
    url = {"app": APP_URL, "s3": S3_URL}[dead]
    sb.curl_codes.write_text(f"{url} {code}\n")

    assert sb.fn(f"preview_tunnels_live {shlex.quote(str(directory))}").returncode == 1


def test_a_url_that_answers_with_any_other_status_is_live(sb: Sandbox) -> None:
    """Garage answers its root with 403 and the app may be mid-rollout with a 502:
    the tunnel is there either way. Both URLs are asked."""
    directory = sb.running_preview()
    sb.curl_codes.write_text(f"{APP_URL} 502\n{S3_URL} 403\n")

    assert sb.fn(f"preview_tunnels_live {shlex.quote(str(directory))}").returncode == 0
    assert set(sb.curl_asked.read_text().split()) >= {APP_URL, S3_URL}


def test_a_dead_process_is_not_live_without_asking_its_url(sb: Sandbox) -> None:
    """The process check comes first: a killed tunnel costs no network round trip."""
    directory = sb.running_preview()
    sb.kill_and_wait(int((directory / "app.pid").read_text()))

    assert sb.fn(f"preview_tunnels_live {shlex.quote(str(directory))}").returncode == 1
    assert APP_URL not in sb.curl_asked.read_text().split()


def test_a_tunnel_with_no_url_stops_both_and_fails(sb: Sandbox) -> None:
    """Nothing is deployed on one URL: a miss stops both and names the role and its log."""
    directory = sb.state / "preview-t"

    done = sb.fn(f"preview_start_tunnels {shlex.quote(str(directory))} 2", FAKE_TUNNEL_SILENT="1")

    assert done.returncode == 1
    assert "app" in done.stderr
    assert "app.log" in done.stderr
    pids = sb.fake_pids()
    assert len(pids) == 2, "both fakes should have been started before one was missed"
    assert _wait_until(lambda: all(_gone(pid) for pid in pids))
    assert not (directory / "app.pid").exists()
    assert not (directory / "s3.pid").exists()


def test_stopping_stops_cloudflared_and_nothing_else(sb: Sandbox) -> None:
    """A pid file can outlive its process; the pid may now be someone's editor."""
    directory = sb.state / "preview-t"
    quoted = shlex.quote(str(directory))
    sb.fn(f"preview_start_tunnels {quoted} 10")
    app_pid = int((directory / "app.pid").read_text())
    sb.kill_and_wait(int((directory / "s3.pid").read_text()))
    bystander = sb.spawn(["/bin/sleep", "60"])
    (directory / "s3.pid").write_text(f"{bystander.pid}\n")
    assert not _gone(app_pid)

    first = sb.fn(f"preview_stop_tunnels {quoted}")
    second = sb.fn(f"preview_stop_tunnels {quoted}")

    assert first.returncode == 0, first.stderr
    assert _wait_until(lambda: _gone(app_pid))
    assert bystander.poll() is None, "a process that is not cloudflared was signalled"
    for name in ("app.pid", "s3.pid", "app.url", "s3.url"):
        assert not (directory / name).exists(), name
    assert (directory / "app.log").exists()
    assert second.returncode == 0


# --- deploy.sh preview -----------------------------------------------------


def test_preview_up_refuses_without_cloudflared(sb: Sandbox) -> None:
    """Refused before anything is built or started, and for cloudflared first (t-3)."""
    minbin = sb.root / "minbin"
    minbin.mkdir()
    for tool in [
        "bash",
        "dirname",
        "git",
        "tr",
        "sed",
        "cat",
        "ps",
        "sleep",
        "mkdir",
        "rm",
        "shasum",
        "sha1sum",
    ]:
        found = shutil.which(tool)
        if found:
            (minbin / tool).symlink_to(found)
    env = sb.env(PATH=str(minbin), BRANCH="t")

    without = sb.run([BASH, "scripts/deploy.sh", "preview", "up"], env)
    (minbin / "cloudflared").symlink_to(sb.fake)
    with_fake = sb.run([BASH, "scripts/deploy.sh", "preview", "up"], env)

    assert without.returncode == 1
    assert "'cloudflared' is required" in without.stderr
    assert with_fake.returncode == 1
    assert "'k3d' is required" in with_fake.stderr
    assert "cloudflared" not in with_fake.stderr


def test_preview_url_prints_both_origins(sb: Sandbox) -> None:
    """The two lines can be eval'd or pasted into a later command."""
    sb.running_preview()

    done = sb.deploy("preview", "url", BRANCH="t")

    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [
        f"APP_ORIGIN={APP_URL}",
        f"OBJECT_STORE_ORIGIN={S3_URL}",
    ]


def test_preview_url_says_when_the_tunnels_are_down(sb: Sandbox) -> None:
    """No state, or one dead tunnel, is not live — and a script can tell by the status."""
    nothing = sb.deploy("preview", "url", BRANCH="t")
    directory = sb.running_preview()
    sb.kill_and_wait(int((directory / "s3.pid").read_text()))
    one_dead = sb.deploy("preview", "url", BRANCH="t")

    assert nothing.returncode == 1
    assert "tunnels are not running" in nothing.stderr
    assert one_dead.returncode == 1
    assert "tunnels are not running" in one_dead.stderr
    assert one_dead.stdout == ""


def test_preview_refuses_what_it_owns(sb: Sandbox) -> None:
    """Each override would be silently overwritten or contradict decision 3 (decision 22)."""
    sb.running_preview()
    refusals = [
        (["preview", "url"], {"APP_ORIGIN": "http://x"}, "APP_ORIGIN"),
        (["preview", "url"], {"OBJECT_STORE_ORIGIN": "http://x"}, "OBJECT_STORE_ORIGIN"),
        (["preview", "url"], {"DEPLOY_ENV": "lab"}, "DEPLOY_ENV"),
        (["preview", "url"], {"NAMESPACE": "other"}, "NAMESPACE"),
        (["preview", "url", "--", "--set", "x=y"], {}, "Helm arguments"),
    ]

    for argv, extra, named in refusals:
        done = sb.deploy(*argv, BRANCH="t", **extra)
        assert done.returncode == 1, (argv, extra, done.stderr)
        assert named in done.stderr, (argv, extra, done.stderr)

    # The positive: with none of them set, the same command succeeds.
    clean = sb.deploy("preview", "url", BRANCH="t")
    assert clean.returncode == 0, clean.stderr
    assert f"APP_ORIGIN={APP_URL}" in clean.stdout


# --- the preview's password (handoff 09, decision 10) -----------------------

# Prints as `htpasswd -niBC 10 ""` does — a colon, the hash, a blank line — with a hash made
# from the password it read on stdin, so a test can see which one reached it. Its args and
# stdin are logged, one line each.
FAKE_HTPASSWD = """#!/bin/bash
read -r password
printf '%s\\n' "$*" >>"$FAKE_HTPASSWD_LOG"
printf '%s\\n' "$password" >>"$FAKE_HTPASSWD_LOG"
printf ':$2y$10$fake.%s\\n\\n' "$password"
"""


def _fake_htpasswd(sb: Sandbox) -> Path:
    fake = sb.bin / "htpasswd"
    fake.write_text(FAKE_HTPASSWD)
    fake.chmod(0o755)
    log = sb.root / "fake-htpasswd"
    log.touch()
    return log


def test_without_a_preview_password_dex_keeps_the_k3d_values_hash(sb: Sandbox) -> None:
    log = _fake_htpasswd(sb)

    done = sb.fn("preview_password_args", FAKE_HTPASSWD_LOG=str(log))

    assert done.returncode == 0, done.stderr
    assert done.stdout == ""
    assert log.read_text() == ""


def test_a_preview_password_reaches_dex_as_its_bcrypt_hash(sb: Sandbox) -> None:
    log = _fake_htpasswd(sb)

    done = sb.fn("preview_password_args", PREVIEW_PASSWORD="s3cret-Pw", FAKE_HTPASSWD_LOG=str(log))

    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["--set-string", "dex.passwordHash=$2y$10$fake.s3cret-Pw"]
    # On stdin, never in argv, where `ps` would show it.
    args, stdin = log.read_text().splitlines()
    assert "s3cret-Pw" not in args
    assert args.split() == ["-niBC", "10", ""] or args.split() == ["-niBC", "10"]
    assert stdin == "s3cret-Pw"


def test_a_preview_password_without_htpasswd_is_refused(sb: Sandbox) -> None:
    minbin = sb.root / "minbin"
    minbin.mkdir()
    for tool in ["bash", "dirname", "git", "tr", "sed", "cat"]:
        found = shutil.which(tool)
        if found:
            (minbin / tool).symlink_to(found)

    done = sb.fn("preview_password_args", PATH=str(minbin), PREVIEW_PASSWORD="s3cret-Pw")

    assert done.returncode != 0
    assert "'htpasswd' is required" in done.stderr
