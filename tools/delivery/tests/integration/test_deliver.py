"""A delivery from a GitHub issue, against a real git repo, a fake `gh` and a fake agent.

`.claude/delivery/loop-test.sh` proves the state machine through `scripts/deliver.sh` with the
local backend; this proves what only a remote backend does — the fetch, the issue copy,
`source.json` and every name taken from the key — and what only a real remote does: the
branch committed after every stage and pushed, brought level before a run, and never forced.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from delivery.errors import BackendError
from delivery.github import GitHubBackend
from delivery.resolve import BackendConfig
from delivery.run import deliver

URL = "https://github.com/caw-project/ch09"
REPO_ROOT = Path(__file__).resolve().parents[4]
BODY = "## Summary\n\nDisplay names are unique.\n"


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
    """A primary checkout with the two plan agents committed on main, and `origin` — a bare
    repo, as GitHub is to a runner — holding main."""
    root = tmp_path / "caw-project"
    agents = root / ".claude" / "agents"
    agents.mkdir(parents=True)
    for stage in ("plan-writer", "plan-reviewer"):
        (agents / f"{stage}.md").write_text(f"---\nname: {stage}\nmodel: opus\n---\n")
    (root / ".env.example").write_text("APP_ORIGIN=\n")
    # The repo's own ignore rules: what a checkpoint commits depends on them.
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
def person(repo, remote) -> Callable[[str, str], str]:
    """Someone else's clone: `person(path, text)` commits `path` with `text` on feature/gh-3
    and pushes it, as a person answering on GitHub does. Returns the commit."""

    def push(path: str, text: str) -> str:
        clone = repo.parent / "person"
        if not clone.exists():
            git(repo.parent, "clone", "-q", "-b", "feature/gh-3", str(remote), str(clone))
        git(clone, "pull", "-q", "--ff-only")
        (clone / path).parent.mkdir(parents=True, exist_ok=True)
        (clone / path).write_text(text)
        git(clone, "add", path)
        git(
            clone,
            "-c",
            "user.name=p",
            "-c",
            "user.email=p@example.com",
            "commit",
            "-qm",
            "an answer",
        )
        git(clone, "push", "-q", "origin", "feature/gh-3")
        return git(clone, "rev-parse", "HEAD").strip()

    return push


def subjects(cwd: Path, ref: str = "feature/gh-3") -> list[str]:
    """The commit subjects on a branch since main, newest first."""
    return git(cwd, "log", "--format=%s", f"main..{ref}").splitlines()


def committed(cwd: Path, ref: str = "feature/gh-3") -> set[str]:
    return set(git(cwd, "ls-tree", "-r", "--name-only", ref).splitlines())


class FakeAgent:
    """The plan-writer writes its plan; the plan-reviewer stops for a human, or returns
    `reviewer`. `during(stage, cwd)` runs inside a stage, as anything a person does while an
    agent works; `stray` makes the plan-writer write outside its scope."""

    def __init__(
        self,
        reviewer: str = "needs_human",
        during: Callable[[str, Path], None] | None = None,
        stray: bool = False,
    ) -> None:
        self.prompts: list[str] = []
        self.reviewer = reviewer
        self.during = during
        self.stray = stray

    def __call__(self, args: list[str], cwd: Path) -> str:
        prompt = args[args.index("-p") + 1]
        stage = args[args.index("--agent") + 1]
        self.prompts.append(prompt)
        lines = dict(line.split(": ", 1) for line in prompt.splitlines() if ": " in line)
        if self.during:
            self.during(stage, cwd)
        if stage == "plan-writer":
            (cwd / lines["Plan"]).write_text("# The plan\n")
            if self.stray:
                (cwd / "src").mkdir(exist_ok=True)
                (cwd / "src" / "stray.py").write_text("x = 1\n")
            out = {"status": "done", "summary": "planned", "files": [], "questions": []}
        elif self.reviewer == "approved":
            (cwd / lines["Write your review to"]).parent.mkdir(parents=True, exist_ok=True)
            (cwd / lines["Write your review to"]).write_text("Approved.\n")
            out = {"status": "approved", "summary": "looks right", "files": [], "questions": []}
        else:
            out = {
                "status": "needs_human",
                "summary": "a question",
                "files": [],
                "questions": ["Which?"],
            }
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


def run(repo, gh, agent, url=URL, *, env=None, restart=False, clock=None):
    return deliver(
        "gh-3",
        restart=restart,
        config=BackendConfig(kind="github", url=url),
        backend=GitHubBackend(url, run=gh),
        root=repo,
        env={"DELIVER_RETRY_WAIT": "0", **(env or {})},
        agent=agent,
        which=lambda cmd: f"/usr/bin/{cmd}",
        runs=lambda args: True,
        **({"clock": clock} if clock else {}),
    )


@pytest.fixture
def issue_3(gh, gh_issue):
    gh.answers["issue view"] = gh_issue(number=3, title="Display names", body=BODY)
    return gh


def test_a_github_issue_is_delivered_under_its_key(repo, issue_3):
    agent = FakeAgent()

    code = run(repo, issue_3, agent)

    worktree = repo.parent / "caw-gh-3"
    plans = worktree / "docs" / "plans" / "gh-3"
    assert code == 2
    assert git(worktree, "branch", "--show-current").strip() == "feature/gh-3"
    assert (plans / "00-issue.md").read_text() == f"# Display names\n\n{BODY}"
    assert json.loads((plans / "source.json").read_text()) == {
        "backend": "github",
        "url": URL,
        "number": 3,
    }
    assert (plans / "01-implementation-plan.md").exists()
    assert (plans / "needs-human.md").read_text().startswith("# gh-3 — questions for a human\n")
    assert agent.prompts[0].splitlines()[:3] == [
        "Issue: gh-3",
        "Issue file: docs/plans/gh-3/00-issue.md",
        "Plan dir: docs/plans/gh-3/",
    ]
    assert not any(URL in prompt for prompt in agent.prompts)
    history = (plans / "run" / "history.log").read_text().splitlines()
    assert [line.split(" [")[0] for line in history] == [
        "01 plan-writer done",
        "02 plan-reviewer needs_human",
    ]


def test_a_refused_command_is_counted_in_history_and_kept_beside_it(repo, remote, issue_3):
    # A public repo's transcripts aren't kept, so what a stage was refused is the one clue
    # to why it went without a tool: the count in history.log, the commands in refused.log.
    class Refused(FakeAgent):
        def __call__(self, args: list[str], cwd: Path) -> str:
            out = json.loads(super().__call__(args, cwd))
            if args[args.index("--agent") + 1] == "plan-writer":
                out["permission_denials"] = [
                    {"tool_name": "Bash", "tool_use_id": "a", "tool_input": {"command": c}}
                    for c in ("git log; echo $?", 'git diff | grep -v "^$"')
                ]
            return json.dumps(out)

    run(repo, issue_3, Refused())

    show = "feature/gh-3:docs/plans/gh-3/run/"
    history = git(remote, "show", f"{show}history.log").splitlines()
    assert history[0].startswith("01 plan-writer done [")
    assert "· 2 refused]" in history[0]
    assert "refused" not in history[1]
    assert git(remote, "show", f"{show}refused.log") == (
        '01 plan-writer: git log; echo $?\n01 plan-writer: git diff | grep -v "^$"\n'
    )


def test_a_rerun_resumes_where_it_stopped_with_the_issue_fetched_again(repo, issue_3, gh_issue):
    run(repo, issue_3, FakeAgent())
    issue_3.answers["issue view"] = gh_issue(
        number=3, title="Display names", body="## Summary\n\nEdited.\n"
    )
    agent = FakeAgent()

    run(repo, issue_3, agent)

    plans = repo.parent / "caw-gh-3" / "docs" / "plans" / "gh-3"
    assert "Edited." in (plans / "00-issue.md").read_text()
    assert agent.prompts[0].splitlines()[5] == "Stage: plan-reviewer, round 1 of 3"


def test_a_finished_delivery_is_left_as_it_was(repo, issue_3, gh_issue):
    run(repo, issue_3, FakeAgent())
    run_dir = repo.parent / "caw-gh-3" / "docs" / "plans" / "gh-3" / "run"
    (run_dir / "state.json").write_text(
        (run_dir / "state.json").read_text().replace('"needs_human"', '"done"')
    )
    copy = repo.parent / "caw-gh-3" / "docs" / "plans" / "gh-3" / "00-issue.md"
    before = copy.read_text()
    issue_3.answers["issue view"] = gh_issue(number=3, title="Renamed since", body=BODY)

    code = run(repo, issue_3, FakeAgent())

    assert code == 0
    assert copy.read_text() == before


def test_the_same_key_from_another_repo_is_refused(repo, issue_3, capsys):
    run(repo, issue_3, FakeAgent())
    other = "https://github.com/someone/else"

    code = run(repo, issue_3, FakeAgent(), url=other)

    assert code == 2
    assert "already holds" in capsys.readouterr().err


def test_an_issue_that_cannot_be_fetched_stops_before_any_worktree(repo, gh, capsys):
    gh.answers["issue view"] = BackendError("could not find issue 3")

    code = run(repo, gh, FakeAgent())

    assert code == 1
    assert "could not find issue 3" in capsys.readouterr().err
    assert not (repo.parent / "caw-gh-3").exists()


def test_a_missing_tool_stops_before_the_fetch(repo, gh, capsys):
    code = deliver(
        "gh-3",
        restart=False,
        config=BackendConfig(kind="github", url=URL),
        backend=GitHubBackend(URL, run=gh),
        root=repo,
        env={},
        agent=FakeAgent(),
        which=lambda cmd: None if cmd == "gh" else f"/usr/bin/{cmd}",
        runs=lambda args: True,
    )

    assert code == 1
    assert "'gh' is not on PATH" in capsys.readouterr().err
    assert gh.calls == []


# --- the branch: committed after every stage, pushed, brought level, never forced ------


def test_every_stage_leaves_a_checkpoint_on_the_remote(repo, remote, issue_3):
    code = run(repo, issue_3, FakeAgent(reviewer="approved"))

    # The test-writer has no agent in this repo, so the run pauses after the plan pair.
    assert code == 3
    assert subjects(remote) == [
        "delivery(gh-3): plan-reviewer approved, round 1",
        "delivery(gh-3): plan-writer done, round 1",
    ]
    assert git(remote, "log", "-1", "--format=%an|%b", "feature/gh-3").strip() == "t|looks right"
    files = committed(remote)
    assert {
        "docs/plans/gh-3/00-issue.md",
        "docs/plans/gh-3/source.json",
        "docs/plans/gh-3/01-implementation-plan.md",
        "docs/plans/gh-3/reviews/plan-reviewer-1.md",
        "docs/plans/gh-3/run/state.json",
        "docs/plans/gh-3/run/history.log",
    } <= files
    assert not any(f.startswith("build/") for f in files)
    assert ".env" not in files


def test_a_stop_for_a_human_is_committed_and_pushed(repo, remote, issue_3):
    code = run(repo, issue_3, FakeAgent())

    assert code == 2
    assert subjects(remote) == [
        "delivery(gh-3): needs a human at plan-reviewer, round 1",
        "delivery(gh-3): plan-writer done, round 1",
    ]
    assert "docs/plans/gh-3/needs-human.md" in committed(remote)
    state = json.loads(git(remote, "show", "feature/gh-3:docs/plans/gh-3/run/state.json"))
    assert (state["stage"], state["status"]) == ("plan-reviewer", "needs_human")


def test_a_stop_answered_on_the_remote_resumes_on_another_machine(repo, issue_3, person):
    run(repo, issue_3, FakeAgent())
    person("docs/plans/gh-3/needs-human.md", "# gh-3\n\n1. Which?\n\n   **Answer:** That one.\n")
    # A hosted runner starts with nothing but the remote.
    git(repo, "worktree", "remove", "--force", str(repo.parent / "caw-gh-3"))
    git(repo, "branch", "-D", "feature/gh-3")
    agent = FakeAgent()

    code = run(repo, issue_3, agent)

    worktree = repo.parent / "caw-gh-3"
    assert code == 2
    assert agent.prompts[0].splitlines()[5] == "Stage: plan-reviewer, round 1 of 3"
    assert "Human answers:" in agent.prompts[0]
    assert "That one." in (worktree / "docs/plans/gh-3/needs-human.md").read_text()
    assert (
        git(worktree, "rev-parse", "--abbrev-ref", "@{upstream}").strip() == "origin/feature/gh-3"
    )


def test_an_answer_pushed_to_the_branch_is_fast_forwarded_into_the_worktree(
    repo, remote, issue_3, person
):
    run(repo, issue_3, FakeAgent())
    answer = person("docs/plans/gh-3/needs-human.md", "**Answer:** That one.\n")
    agent = FakeAgent()

    run(repo, issue_3, agent)

    worktree = repo.parent / "caw-gh-3"
    assert git(worktree, "merge-base", "--is-ancestor", answer, "HEAD") == ""
    assert "Human answers:" in agent.prompts[0]
    assert subjects(remote)[0] == "delivery(gh-3): needs a human at plan-reviewer, round 1"
    assert git(worktree, "rev-list", "--merges", "main..HEAD") == ""


def test_a_branch_that_has_diverged_stops_before_any_stage(repo, issue_3, person, capsys):
    run(repo, issue_3, FakeAgent())
    worktree = repo.parent / "caw-gh-3"
    (worktree / "notes.md").write_text("mine\n")
    git(worktree, "add", "notes.md")
    git(worktree, "commit", "-qm", "a local commit")
    person("docs/plans/gh-3/needs-human.md", "theirs\n")
    capsys.readouterr()
    agent = FakeAgent()

    code = run(repo, issue_3, agent)

    assert code == 1
    assert "diverged" in capsys.readouterr().err
    assert agent.prompts == []


def test_uncommitted_work_with_the_remote_ahead_stops_before_any_stage(
    repo, issue_3, person, capsys
):
    run(repo, issue_3, FakeAgent())
    worktree = repo.parent / "caw-gh-3"
    (worktree / "docs/plans/gh-3/01-implementation-plan.md").write_text("# Edited here\n")
    person("docs/plans/gh-3/needs-human.md", "theirs\n")
    capsys.readouterr()
    agent = FakeAgent()

    code = run(repo, issue_3, agent)

    assert code == 1
    assert "uncommitted" in capsys.readouterr().err
    assert agent.prompts == []


def test_a_push_rejected_mid_run_stops_it_and_names_both_commits(
    repo, remote, issue_3, person, capsys
):
    run(repo, issue_3, FakeAgent())
    theirs: list[str] = []

    def answers_while_it_works(stage: str, cwd: Path) -> None:
        theirs.append(person("docs/plans/gh-3/elsewhere.md", "pushed meanwhile\n"))

    capsys.readouterr()

    code = run(repo, issue_3, FakeAgent(during=answers_while_it_works))

    worktree = repo.parent / "caw-gh-3"
    ours = git(worktree, "rev-parse", "HEAD").strip()
    err = capsys.readouterr().err
    assert code == 1
    assert ours[:7] in err
    assert theirs[0][:7] in err
    # Never forced: the remote still has the person's commit on top.
    assert git(remote, "rev-parse", "feature/gh-3").strip() == theirs[0]


def test_with_pushing_off_the_run_commits_and_touches_no_remote(repo, issue_3):
    git(repo, "remote", "remove", "origin")

    code = run(repo, issue_3, FakeAgent(), env={"DELIVER_PUSH": "0"})

    assert code == 2
    assert subjects(repo)[0] == "delivery(gh-3): needs a human at plan-reviewer, round 1"


def test_a_restart_starts_again_on_top_of_the_branch(repo, remote, issue_3):
    run(repo, issue_3, FakeAgent())
    agent = FakeAgent()

    code = run(repo, issue_3, agent, restart=True)

    assert code == 2
    assert agent.prompts[0].splitlines()[5] == "Stage: plan-writer, round 1 of 3"
    assert subjects(remote) == [
        "delivery(gh-3): needs a human at plan-reviewer, round 1",
        "delivery(gh-3): plan-writer done, round 1",
        "delivery(gh-3): needs a human at plan-reviewer, round 1",
        "delivery(gh-3): plan-writer done, round 1",
    ]


def test_out_of_time_ends_the_run_at_a_checkpoint(repo, remote, issue_3, capsys):
    start = 1_792_150_000
    now = [start]

    def ninety_minutes_a_stage(stage: str, cwd: Path) -> None:
        now[0] += 90 * 60

    agent = FakeAgent(reviewer="approved", during=ninety_minutes_a_stage)

    code = run(
        repo,
        issue_3,
        agent,
        env={"DELIVER_DEADLINE": str(start + 120 * 60)},
        clock=lambda: now[0],
    )

    assert code == 4
    assert len(agent.prompts) == 1
    assert subjects(remote) == ["delivery(gh-3): plan-writer done, round 1"]
    state = json.loads(git(remote, "show", "feature/gh-3:docs/plans/gh-3/run/state.json"))
    assert state["stage"] == "plan-reviewer"
    assert "run again" in capsys.readouterr().err


def test_a_stage_that_breaks_a_rule_is_committed_as_a_failure(repo, remote, issue_3, capsys):
    code = run(repo, issue_3, FakeAgent(stray=True))

    assert code == 1
    assert "wrote outside" in capsys.readouterr().err
    assert subjects(remote) == ["delivery(gh-3): failed at plan-writer, round 1"]
    assert git(remote, "log", "-1", "--format=%b", "feature/gh-3").startswith(
        "plan-writer wrote outside"
    )


def test_a_refused_write_is_set_aside_not_committed(repo, remote, issue_3, capsys):
    # The check stops the run; the commit after it must not keep what it refused, or the
    # rerun builds on it. The stage's own work is kept, and the refused file is kept aside.
    code = run(repo, issue_3, FakeAgent(stray=True))
    worktree = repo.parent / "caw-gh-3"

    assert code == 1
    assert "docs/plans/gh-3/01-implementation-plan.md" in git(
        remote, "show", "--name-only", "--format=", "feature/gh-3"
    )
    assert "src/stray.py" not in git(remote, "ls-tree", "-r", "--name-only", "feature/gh-3")
    assert not (worktree / "src" / "stray.py").exists()
    kept = worktree / "build" / "delivery" / "refused" / "01-plan-writer" / "src" / "stray.py"
    assert kept.read_text() == "x = 1\n"
    assert "build/delivery/refused/01-plan-writer" in capsys.readouterr().err


def test_a_sketch_never_outlives_its_stage(repo, issue_3):
    # A sketch proves the tests, written by the test pair and broken on purpose by the
    # code-reviewer. The next stage builds from the plan, never from someone else's probe.
    seen: dict[str, bool] = {}

    def sketches(stage: str, cwd: Path) -> None:
        seen[stage] = (cwd / "build" / "sketch").exists()
        if stage == "plan-writer":
            (cwd / "build" / "sketch" / "frontend" / "src").mkdir(parents=True)
            (cwd / "build" / "sketch" / "frontend" / "src" / "probe.ts").write_text("x\n")

    run(repo, issue_3, FakeAgent(during=sketches))

    assert seen == {"plan-writer": False, "plan-reviewer": False}
    assert not (repo.parent / "caw-gh-3" / "build" / "sketch").exists()


def test_an_approval_without_its_review_is_asked_for_it_once(repo, remote, issue_3):
    # A reviewer that approves and forgets the file is resumed in its session to write it,
    # not failed: the review is the record, and it costs a few turns, not a rerun.
    class Forgets(FakeAgent):
        def __call__(self, args: list[str], cwd: Path) -> str:
            stage = args[args.index("--agent") + 1]
            if stage == "plan-reviewer" and "--resume" not in args:
                self.prompts.append(args[args.index("-p") + 1])
                return json.dumps(
                    {
                        "subtype": "success",
                        "is_error": False,
                        "num_turns": 3,
                        "total_cost_usd": 0.5,
                        "duration_ms": 60000,
                        "session_id": "s-forgot",
                        "structured_output": {
                            "status": "approved",
                            "summary": "looks right",
                            "files": [],
                            "questions": [],
                        },
                    }
                )
            if "--resume" in args:
                # Asked for the file by name, in the session that forgot it.
                assert args[args.index("--resume") + 1] == "s-forgot"
                named = args[args.index("-p") + 1].split(": ", 1)[1].split(".md")[0] + ".md"
                (cwd / named).parent.mkdir(parents=True, exist_ok=True)
                (cwd / named).write_text("Approved.\n")
                return json.dumps({"subtype": "success", "is_error": False, "session_id": "s"})
            return super().__call__(args, cwd)

    code = run(repo, issue_3, Forgets(reviewer="approved"))

    assert code == 3  # paused at the test-writer, which has no agent here
    assert "docs/plans/gh-3/reviews/plan-reviewer-1.md" in committed(remote)
    assert subjects(remote)[0] == "delivery(gh-3): plan-reviewer approved, round 1"


def test_a_file_still_missing_after_asking_fails_the_run(repo, issue_3, capsys):
    class NeverWrites(FakeAgent):
        def __call__(self, args: list[str], cwd: Path) -> str:
            stage = args[args.index("--agent") + 1]
            if stage == "plan-reviewer":
                return json.dumps(
                    {
                        "subtype": "success",
                        "is_error": False,
                        "num_turns": 3,
                        "total_cost_usd": 0.5,
                        "duration_ms": 60000,
                        "session_id": "s-never",
                        "structured_output": {
                            "status": "approved",
                            "summary": "looks right",
                            "files": [],
                            "questions": [],
                        },
                    }
                )
            return super().__call__(args, cwd)

    code = run(repo, issue_3, NeverWrites(reviewer="approved"))

    assert code == 1
    assert "approved but wrote no docs/plans/gh-3/reviews/plan-reviewer-1.md" in (
        capsys.readouterr().err
    )


def test_a_refused_edit_to_a_tracked_file_is_put_back(repo, remote, issue_3):
    def edits_gitignore(stage: str, cwd: Path) -> None:
        if stage == "plan-writer":
            with (cwd / ".gitignore").open("a") as f:
                f.write("everything\n")

    code = run(repo, issue_3, FakeAgent(during=edits_gitignore))
    worktree = repo.parent / "caw-gh-3"

    assert code == 1
    assert git(remote, "show", "feature/gh-3:.gitignore") == git(repo, "show", "main:.gitignore")
    assert "everything" not in (worktree / ".gitignore").read_text()
    kept = worktree / "build" / "delivery" / "refused" / "01-plan-writer" / ".gitignore"
    assert kept.read_text().endswith("everything\n")


def test_an_agent_that_commits_still_stops_the_run(repo, issue_3, capsys):
    def commits(stage: str, cwd: Path) -> None:
        (cwd / "sneaky.md").write_text("x\n")
        git(cwd, "add", "sneaky.md")
        git(cwd, "commit", "-qm", "an agent's own commit")

    code = run(repo, issue_3, FakeAgent(during=commits))

    assert code == 1
    assert "plan-writer committed" in capsys.readouterr().err


def test_a_finished_delivery_leaves_no_new_commit(repo, remote, issue_3):
    run(repo, issue_3, FakeAgent())
    run_dir = repo.parent / "caw-gh-3" / "docs" / "plans" / "gh-3" / "run"
    state = json.loads((run_dir / "state.json").read_text())
    (run_dir / "state.json").write_text(json.dumps({**state, "status": "done", "stage": "done"}))
    before = git(repo.parent / "caw-gh-3", "rev-parse", "HEAD")

    assert run(repo, issue_3, FakeAgent()) == 0
    assert git(repo.parent / "caw-gh-3", "rev-parse", "HEAD") == before
