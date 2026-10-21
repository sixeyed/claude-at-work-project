"""An accepted GitHub delivery ends in a pull request (handoff 09): against a real git repo with
a bare one as `origin`, a fake `gh`, a fake deploy script, a fake Slack and an agent that
approves everything.

What only a real remote shows: the screenshot commits after `accepted` — added, then removed,
so the PR's diff holds no image but the commit its body links does — and every publish step
idempotent on a rerun, found from git and `gh` rather than stored.
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from delivery.errors import BackendError
from delivery.github import GitHubBackend
from delivery.resolve import BackendConfig
from delivery.run import deliver

URL = "https://github.com/caw-project/ch09"
REPO_ROOT = Path(__file__).resolve().parents[4]
STAGES = (
    "plan-writer",
    "plan-reviewer",
    "test-writer",
    "test-reviewer",
    "code-writer",
    "code-reviewer",
    "acceptance-reviewer",
)
PR_12 = json.dumps({"number": 12, "url": f"{URL}/pull/12", "isDraft": False})
SHOTS = ("feature/taken.png", "standard/signed-in.png")
#: Every acceptance pass writes a proof of its own, as the machine requires.
PASSES = itertools.count(1)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603 — fixed program, argument list.
        ["git", *args],  # noqa: S607 — git from PATH, as the runner finds it.
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path) -> Path:
    """A primary checkout with all seven agents on main, and `origin`, a bare repo, holding it."""
    root = tmp_path / "caw-project"
    agents = root / ".claude" / "agents"
    agents.mkdir(parents=True)
    for stage in STAGES:
        (agents / f"{stage}.md").write_text(f"---\nname: {stage}\nmodel: sonnet\n---\n")
    (root / ".env.example").write_text("APP_ORIGIN=\n")
    shutil.copy(REPO_ROOT / ".gitignore", root / ".gitignore")
    git(tmp_path, "init", "-q", "-b", "main", str(root))
    git(root, "config", "user.name", "t")
    git(root, "config", "user.email", "t@example.com")
    git(root, "add", ".")
    git(root, "commit", "-qm", "init")
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(tmp_path / "origin.git"))
    git(root, "remote", "add", "origin", str(tmp_path / "origin.git"))
    git(root, "push", "-q", "origin", "main")
    return root


@pytest.fixture
def remote(repo) -> Path:
    return repo.parent / "origin.git"


@pytest.fixture
def worktree(repo) -> Path:
    return repo.parent / "caw-gh-3"


@pytest.fixture
def deploy(tmp_path) -> tuple[Path, Path]:
    """A deploy script that records the PREVIEW_PASSWORD it was given, and its record."""
    seen = tmp_path / "deploy-saw"
    script = tmp_path / "deploy"
    script.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "${{PREVIEW_PASSWORD-<unset>}}" >>"{seen}"\n'
        "echo APP_ORIGIN=https://preview.example\n"
    )
    script.chmod(0o755)
    return script, seen


@pytest.fixture
def gh(gh, gh_issue):
    """No PR open yet; opening one gives #12."""
    gh.answers["issue view"] = gh_issue(number=3, title="Display names", body="## Summary\n\nx\n")
    gh.answers["pr list"] = "[]"
    gh.answers["pr create"] = f"{URL}/pull/12\n"
    gh.answers["pr view"] = PR_12
    return gh


class Accepting:
    """Writers write their output, reviewers approve with a review, and the acceptance pass
    writes a proof citing `SHOTS` — each made under the evidence dir — unless `shots` is off."""

    def __init__(self, shots: bool = True) -> None:
        self.shots = shots
        self.stages: list[str] = []

    def __call__(self, args: list[str], cwd: Path) -> str:
        prompt = args[args.index("-p") + 1]
        stage = args[args.index("--agent") + 1]
        self.stages.append(stage)
        lines = dict(line.split(": ", 1) for line in prompt.splitlines() if ": " in line)
        status = "done" if stage.endswith("-writer") else "approved"
        if stage.endswith("-writer"):
            field = {"plan": "Plan", "test": "Red report", "code": "Green report"}
            out = lines[field[stage.split("-")[0]]]
            write(cwd / out, f"# {stage}\n")
        elif "Write your review to" in lines:
            write(cwd / lines["Write your review to"], "Approved.\n")
        else:
            cited = ""
            if self.shots:
                for shot in SHOTS:
                    write(cwd / "build" / "acceptance" / shot, f"PNG {shot}")
                cited = "".join(f"![{s}](../../../build/acceptance/{s})\n" for s in SHOTS)
            write(
                cwd / lines["Proof"],
                "# gh-3 — acceptance proof: accepted\n\n## Summary\n- Unique names.\n"
                f"- Pass {next(PASSES)}: a proof of its own.\n\n"
                f"## Screenshots\n{cited}\n## The run\n01 plan-writer done\n",
            )
        out = {"status": status, "summary": f"{stage} {status}", "files": [], "questions": []}
        return json.dumps(
            {
                "subtype": "success",
                "is_error": False,
                "num_turns": 3,
                "total_cost_usd": 0.5,
                "duration_ms": 60000,
                "session_id": "s",
                "structured_output": out,
            }
        )


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class FakeSlack:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict]] = []

    def __call__(self, url: str, headers: dict, payload: dict) -> dict:
        self.requests.append((url.rsplit("/", 1)[-1], payload))
        return {"ok": True, "ts": "1700000000.000100"}

    def texts(self) -> list[str]:
        return [p["text"] for _, p in self.requests]


def run(repo, gh, deploy, agent=None, *, env=None, restart=False, slack=None):
    script, _ = deploy
    return deliver(
        "gh-3",
        restart=restart,
        config=BackendConfig(kind="github", url=URL),
        backend=GitHubBackend(URL, run=gh),
        root=repo,
        env={"DELIVER_RETRY_WAIT": "0", "DELIVER_DEPLOY_SH": str(script), **(env or {})},
        agent=agent or Accepting(),
        which=lambda cmd: f"/usr/bin/{cmd}",
        runs=lambda args: True,
        **({"slack_transport": slack} if slack else {}),
    )


def subjects(cwd: Path, ref: str = "origin/feature/gh-3") -> list[str]:
    git(cwd, "fetch", "-q", "origin")
    return git(cwd, "log", "--format=%s", f"main..{ref}").splitlines()


def calls(gh, subcommand: str) -> list[tuple[list[str], str | None]]:
    return [c for c in gh.calls if " ".join(c[0][1:3]) == subcommand]


def publish_record(worktree: Path) -> dict:
    return json.loads((worktree / "build" / "delivery" / "publish.json").read_text())


# --- the PR ----------------------------------------------------------------


def test_an_accepted_delivery_opens_its_pr_after_the_screenshot_commits(
    repo, remote, worktree, gh, deploy
):
    code = run(repo, gh, deploy)

    assert code == 0
    assert subjects(repo)[:3] == [
        "delivery(gh-3): proof screenshots removed",
        "delivery(gh-3): proof screenshots",
        "delivery(gh-3): accepted",
    ]
    args, body = gh.call("pr create")
    assert args[args.index("--head") + 1] == "feature/gh-3"
    assert args[args.index("--base") + 1] == "main"
    assert args[args.index("--title") + 1] == "Display names (gh-3)"
    assert "Closes #3" in body
    assert publish_record(worktree) == {"url": f"{URL}/pull/12"}


def test_the_prs_diff_has_no_image_but_the_commit_its_body_links_holds_each(
    repo, remote, gh, deploy
):
    run(repo, gh, deploy)

    git(repo, "fetch", "-q", "origin")
    changed = git(repo, "diff", "--name-only", "main", "origin/feature/gh-3").splitlines()
    assert not [p for p in changed if "/proof/" in p]
    added = git(repo, "rev-parse", "origin/feature/gh-3~1").strip()
    _, body = gh.call("pr create")
    for shot in SHOTS:
        path = f"docs/plans/gh-3/proof/{shot}"
        assert f"{URL}/blob/{added}/{path}?raw=true" in body
        assert git(remote, "show", f"{added}:{path}") == f"PNG {shot}"


def test_the_preview_is_dispatched_for_the_pr_it_opened(repo, gh, deploy):
    run(repo, gh, deploy)

    args, _ = gh.call("workflow run")
    assert args[-2:] == ["-f", "pr=12"]
    order = [" ".join(c[0][1:3]) for c in gh.calls]
    assert order.index("pr create") < order.index("workflow run")


def test_a_rerun_with_the_pr_open_updates_it_and_opens_none(repo, gh, deploy):
    run(repo, gh, deploy)
    before = subjects(repo)
    gh.answers["pr list"] = json.dumps([json.loads(PR_12)])
    gh.calls.clear()

    code = run(repo, gh, deploy)

    assert code == 0
    assert calls(gh, "pr create") == []
    args, body = gh.call("pr edit")
    assert args[3] == "12"
    assert "Closes #3" in body
    assert len(calls(gh, "workflow run")) == 1
    assert subjects(repo) == before


def test_a_pr_that_could_not_be_opened_is_reported_and_the_delivery_still_accepted(
    repo, worktree, gh, deploy, capsys
):
    gh.answers["pr create"] = BackendError(
        "GitHub Actions is not permitted to create pull requests"
    )

    code = run(repo, gh, deploy)

    assert code == 0
    assert "not permitted" in publish_record(worktree)["error"]
    assert "not permitted" in capsys.readouterr().err
    assert calls(gh, "workflow run") == []


def test_a_rerun_after_the_pr_failed_opens_it(repo, gh, deploy):
    gh.answers["pr create"] = BackendError("not permitted")
    run(repo, gh, deploy)
    before = subjects(repo)
    gh.answers["pr create"] = f"{URL}/pull/12\n"

    code = run(repo, gh, deploy)

    assert code == 0
    assert len(calls(gh, "pr create")) == 2
    assert subjects(repo) == before


def test_a_rerun_after_a_crash_between_the_screenshot_commits_makes_only_the_removal(
    repo, worktree, gh, deploy
):
    run(repo, gh, deploy)
    git(worktree, "reset", "-q", "--hard", "HEAD~1")
    git(worktree, "push", "-q", "--force", "origin", "feature/gh-3")

    run(repo, gh, deploy)

    assert subjects(repo)[:3] == [
        "delivery(gh-3): proof screenshots removed",
        "delivery(gh-3): proof screenshots",
        "delivery(gh-3): accepted",
    ]


@pytest.mark.parametrize("env", [{"DELIVER_PR": "0"}, {"DELIVER_PUSH": "0"}])
def test_no_pr_no_screenshot_commits_when_the_pr_is_off_or_nothing_is_pushed(
    repo, worktree, gh, deploy, env
):
    code = run(repo, gh, deploy, env=env)

    assert code == 0
    log = git(worktree, "log", "--format=%s", "main..HEAD").splitlines()
    assert log[0] == "delivery(gh-3): accepted"
    assert [c for c in gh.calls if c[0][1] in ("pr", "workflow")] == []


def test_a_proof_with_no_screenshots_opens_its_pr_with_no_screenshot_commits(repo, gh, deploy):
    code = run(repo, gh, deploy, Accepting(shots=False))

    assert code == 0
    assert subjects(repo)[0] == "delivery(gh-3): accepted"
    assert len(calls(gh, "pr create")) == 1


def test_a_restart_with_the_pr_open_makes_it_a_draft_until_the_approval(repo, gh, deploy):
    run(repo, gh, deploy)
    # Ready when the restart finds it; a draft, as the restart left it, at the approval.
    draft = json.dumps({**json.loads(PR_12), "isDraft": True})
    gh.answers["pr list"] = [json.dumps([json.loads(PR_12)]), f"[{draft}]"]
    gh.answers["pr view"] = [draft, draft, PR_12]
    gh.calls.clear()

    code = run(repo, gh, deploy, restart=True)

    assert code == 0
    ready = [c[0] for c in calls(gh, "pr ready")]
    assert ready == [
        ["gh", "pr", "ready", "12", "--repo", "github.com/caw-project/ch09", "--undo"],
        ["gh", "pr", "ready", "12", "--repo", "github.com/caw-project/ch09"],
    ]
    comment = calls(gh, "pr comment")[0]
    assert "redelivery" in comment[1].lower()
    order = [" ".join(c[0][1:3]) for c in gh.calls if c[0][1] == "pr"]
    assert order.index("pr comment") < order.index("pr edit")


# --- Slack, and the password it carries --------------------------------------

SLACK = {"SLACK_BOT_TOKEN": "xoxb-1", "SLACK_CHANNEL": "C0DELIVER"}


def test_with_slack_each_stage_starts_and_ends_in_one_thread(repo, worktree, gh, deploy):
    slack = FakeSlack()

    run(repo, gh, deploy, env=SLACK, slack=slack)

    method, parent = slack.requests[0]
    assert (method, "thread_ts" in parent) == ("chat.postMessage", False)
    assert parent["text"].startswith("gh-3 · Display names")
    replies = [p for m, p in slack.requests[1:] if m == "chat.postMessage"]
    assert all(p["thread_ts"] == "1700000000.000100" for p in replies)
    texts = slack.texts()
    for stage in STAGES:
        assert any(t.startswith(f"▶ {stage} · round 1") for t in texts), stage
        assert any(t.startswith(f"✔ {stage} ") for t in texts), stage
    pr = next(p for _, p in slack.requests if f"{URL}/pull/12" in p["text"])
    assert pr.get("reply_broadcast") is True
    assert ("chat.update", "accepted") in [
        (m, p["text"].split(" — ")[1].split(" ·")[0])
        for m, p in slack.requests
        if m == "chat.update"
    ]
    state = json.loads(git(repo, "show", "origin/feature/gh-3:docs/plans/gh-3/run/state.json"))
    assert state["slack_thread"] == "1700000000.000100"


def test_with_slack_the_preview_gets_a_random_password_posted_only_to_slack(
    repo, worktree, gh, deploy
):
    slack = FakeSlack()
    _, seen = deploy

    run(repo, gh, deploy, env=SLACK, slack=slack)

    password = seen.read_text().splitlines()[0]
    assert password not in ("", "<unset>", "collabhub")
    assert len(password) >= 16
    assert any(password in t and "https://preview.example" in t for t in slack.texts())
    git(repo, "fetch", "-q", "origin")
    assert password not in git(repo, "log", "-p", "main..origin/feature/gh-3")
    assert password not in calls(gh, "pr create")[0][1]


def test_with_slack_the_preview_deploy_is_announced_before_it_starts(repo, gh, deploy):
    """The deploy is the longest wait in a stub run and a long one in any: never silent."""
    slack = FakeSlack()

    run(repo, gh, deploy, env=SLACK, slack=slack)

    texts = slack.texts()
    deploying = texts.index("⏳ acceptance-reviewer · deploying the preview")
    up = next(i for i, t in enumerate(texts) if "https://preview.example" in t)
    started = next(i for i, t in enumerate(texts) if t.startswith("▶ acceptance-reviewer"))
    assert deploying < up < started


class SeesPassword(Accepting):
    """Records, for each stage, the SMOKE_PASSWORD its agent would inherit."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: dict[str, str | None] = {}

    def __call__(self, args: list[str], cwd: Path) -> str:
        self.seen[args[args.index("--agent") + 1]] = os.environ.get("SMOKE_PASSWORD")
        return super().__call__(args, cwd)


def test_only_the_acceptance_stage_is_given_the_preview_password(repo, gh, deploy):
    """The code-writer's e2e signs in to the Compose test stack, whose Dex keeps `collabhub`:
    the preview's password there fails every scenario at the login (gh-3, first real run)."""
    agent = SeesPassword()

    run(repo, gh, deploy, agent, env=SLACK, slack=FakeSlack())

    assert agent.seen.pop("acceptance-reviewer")
    assert agent.seen == dict.fromkeys(STAGES[:-1], None)


def test_without_slack_the_preview_keeps_the_shared_password(repo, gh, deploy):
    _, seen = deploy

    run(repo, gh, deploy)

    assert seen.read_text().splitlines() == ["<unset>"]
