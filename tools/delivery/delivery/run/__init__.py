"""Take one issue to a tested feature ready for review — on GitHub, a pull request — with the
delivery agents in .claude/agents/ doing the work. The runner commits the branch — never an
agent — and pushes it, so a delivery outlives the machine it ran on.

    scripts/deliver.sh issue-8                   start, or carry on from where it stopped
    scripts/deliver.sh issue-8 --restart         forget progress and start at plan-writer
    scripts/deliver.sh --backend github --url https://github.com/OWNER/REPO gh-3

The issue is named by its key — `issue-N` for docs/issues/NNN.md, `gh-N` for a GitHub
issue — and the backend comes from --backend/--url, else DELIVERY_BACKEND/DELIVERY_URL,
else local, as for every `delivery` command; a key for another backend is refused. Local
issues are read from the checkout that runs this, never the worktree. The issue is fetched
on every run, start or resume, and written for the agents to
docs/plans/<key>/00-issue.md — the title as a heading, then the body, whatever the
backend — so an issue edited to answer a question reaches them. docs/plans/<key>/
source.json records where it came from, and a run whose issue comes from anywhere else is
refused: keys are only unique within one backend. The work happens in the worktree
../caw-<key>, on branch feature/<key>, created from DELIVER_BASE if missing.
DELIVER_RUN=<name> builds the same issue again beside it, in ../caw-<key>-<name> on
feature/<key>-<name>.

The branch is the run's record. Every run fetches the remote first — DELIVER_REMOTE, else
`origin` for a gh- key and `forge` for an issue- key — and brings the branch level: a branch
only on the remote is tracked (another machine ran it), one the remote is ahead of is
fast-forwarded (a person pushed an answer). One that has diverged, or a worktree with
uncommitted changes while the remote is ahead, stops the run before any stage: nothing is
ever merged or forced. After every stage the runner commits everything outside build/ —
`delivery(<key>): <stage> <result>, round <R>` — and pushes it; a stop for a human commits
`needs a human at <stage>, round <R>`, a failure `failed at <stage>, round <R>` with the
error, and the approval `accepted`. A write the rules refuse is set aside first, into
build/delivery/refused/, and the path put back as the last checkpoint had it, so the
failure commit never keeps it. A verdict returned without the file it owes — a review, a
report, a send-back file, a proof of its own — is asked for it once in the same session,
with a few turns, before the state machine fails the run over it. A sketch in build/sketch/ is removed when its stage ends:
no stage builds from another's probe. A push the remote rejects stops the run with exit 1,
naming both commits. DELIVER_PUSH=0 commits without fetching or pushing.

An accepted delivery whose backend opens pull requests — GitHub — and whose branch is pushed
ends in one, from feature/<key> into DELIVER_BASE. Its title is the issue's, with the key;
its body is the proof, with `## The run` folded away and `Closes #N` added. The screenshots
the proof cites, from build/acceptance/, are committed under docs/plans/<key>/proof/ —
`proof screenshots` — and removed in the next commit — `proof screenshots removed` — so the
PR's diff has none, and the body links each at the commit that holds it, where it shows
inline. Then the PR's preview is dispatched (.github/workflows/preview.yml), which holds it
open for the review. A rerun finds the PR by its branch and updates it, never opening a
second; a rerun of an accepted delivery does only what this step still owes. A PR that
can't be opened doesn't fail the delivery: the run exits 0, says why, and records it in
build/delivery/publish.json. --restart turns an open PR back into a draft until the
approval. DELIVER_PR=0 opens none; a local issue never gets one.

With SLACK_BOT_TOKEN and SLACK_CHANNEL the run reports to Slack — one thread per delivery,
kept in the run's state, a reply as each stage starts and ends, at a stop, a failure, out of
time and the PR — and each preview gets a random password for Dex, posted there and nowhere
else; the acceptance stage gets it as SMOKE_PASSWORD, no agent the Slack token. Without them nothing is
posted and the password is the shared `collabhub`. A failed post never fails a run.

A run can have a deadline, DELIVER_DEADLINE: no stage starts with less than
DELIVER_DEADLINE_MARGIN minutes left, so a run on a hosted runner ends at a checkpoint
rather than mid-stage at the job's limit. It exits 4; run it again to continue, from the
branch, on any machine. The GitHub Actions workflow .github/workflows/deliver.yml runs this
command on a hosted runner and sets it.

Seven stages: a writer and a reviewer for each of plan, tests and code, then the
acceptance-reviewer, which deploys the branch's preview and proves it there. What every
agent needs to know about this workflow — the context block, rounds, the final round,
escalation — is in .claude/delivery/agent-context.md; keep it in step with this package.

  plan-writer -> plan-reviewer -> test-writer -> test-reviewer -> code-writer -> code-reviewer
    -> acceptance-reviewer -> done

  a writer returns    done               on to its reviewer
  a reviewer returns  approved           on to the next writer, or done
                      changes_requested  back to its writer, with the review
  a later stage       send_back          back to the writer of the pair before
    returns                                its own, with why in a send-back file
  any agent returns   needs_human        stop; questions in needs-human.md

The acceptance-reviewer has no writer: it approves (with its proof in
docs/plans/<key>/04-proof.md), sends back to the code-writer, or stops. Before each of its
passes the workflow deploys the branch's preview itself — a build and a deploy can outlast
any tool call an agent makes — retries a failure once, and tells the agent how it went.
The preview is left running for the human. Two deliveries at once are unsupported — both
`preview up`s upgrade KEDA.

A send-back is for work an earlier pair owns and a later stage finds wrong — a test the
code-writer can't pass because the test is broken, a plan the tests can't be written to.
The stage writes why to the send-back file its context block names, and stops. The earlier
pair takes a new round: its writer answers the file as it answers a review, its reviewer
gates the fix, and the workflow comes forward from there as usual. Every stage on the way
is told what changed since the send-back, and the stage that sent it back what it is
resuming after. Test stages send back to the plan-writer, code stages to the test-writer;
the plan pair can't send back. A reviewer that sends back has reviewed too: its pair's
round advances, so its next review is a new file, and its own writer gets the review to
answer when the flow comes forward to it.

A writer and its reviewer get DELIVER_MAX_ROUNDS reviews (default 3). The last is the
final round, and it is cut down so a disagreement cannot run on: both agents get fewer
turns and less effort, and are told so. The final reviewer may only approve — leaving
minor findings to the stages after it — or stop for a human over something critical or a
deadlock; `changes_requested` there stops for a human too. A send-back is not a
disagreement inside the pair, so it never lands in a final round: the pair it reaches, and
the pair of a reviewer that sent it, always have one ordinary review and a final one ahead.
What bounds it instead is DELIVER_MAX_SENDBACKS, the send-backs one pair will take.

A stage that runs out of turns is resumed once, in the same session, and told to finish;
one that dies without a result is run once more. Only when that fails too does the run
stop.

Answer the questions under each **Answer:** in docs/plans/<key>/needs-human.md, then run
the same command again: it resumes at the stage that stopped, and every agent reads the
answers. Rounds past the limit stay final rounds, so every one comes back through a human.

A stage whose agent is not written yet pauses the workflow the same way; run it again once
the agent exists.

  DELIVER_MAX_ROUNDS       reviews per writer/reviewer pair. Default: 3
  DELIVER_MAX_SENDBACKS    send-backs one pair takes before a human sees the next.
                           Default: 3
  DELIVER_MAX_TURNS        turns for a stage's first pass — a guard against a runaway,
                           not a budget. Default: by stage, 150 to 250 (first_pass_turns)
  DELIVER_REWORK_MAX_TURNS turns for a pass that answers a review or follows a send-back.
                           Default: 100
  DELIVER_FINAL_MAX_TURNS  turns for a stage in the final round. Default: 60
  DELIVER_FINAL_EFFORT     effort for a stage in the final round. Default: medium
  DELIVER_BASE             the branch a new worktree starts from. Default: main
  DELIVER_RUN              a name for a second build of the same issue (above)
  DELIVER_MODEL            one model for every stage, e.g. for a cheap dry run. Default:
                           by stage — Sonnet for the test pair, the code-writer and the
                           acceptance-reviewer, Opus for the plan pair and the
                           code-reviewer (rules.default_model)
  DELIVER_MODEL_<STAGE>    one stage's model, over DELIVER_MODEL and the default —
                           DELIVER_MODEL_TEST_WRITER=opus
  DELIVER_REWORK_MODEL     the model for a pass that answers a review or follows a
                           send-back, over both of those
  DELIVER_EFFORT           effort for every stage's first pass. Default: the model's own
  DELIVER_EFFORT_<STAGE>   one stage's effort, over DELIVER_EFFORT
  DELIVER_REWORK_EFFORT    effort for a rework pass, over both of those. The final round
                           keeps DELIVER_FINAL_EFFORT
  DELIVER_REMOTE           where the branch is pushed. Default: origin for gh-, forge for
                           issue- keys
  DELIVER_PUSH             0 commits without fetching or pushing — the loop test, or a
                           machine with no remote. Default: 1
  DELIVER_DEADLINE         epoch seconds: no stage starts after DELIVER_DEADLINE less the
                           margin. Default: none
  DELIVER_DEADLINE_MARGIN  minutes — the longest stage and a deploy. Default: 75
  DELIVER_PR               0 opens no PR at the approval. Default: 1
  SLACK_BOT_TOKEN          a Slack bot token (chat:write); with SLACK_CHANNEL, the run
                           reports to Slack and previews get their own password
  SLACK_CHANNEL            the channel's ID, C…
  DELIVER_PERMISSION_MODE  default: dontAsk — anything a stage is not allowed (rules.TOOLS)
                           is refused, never prompted for; each refusal is counted in its
                           history.log line and written out in run/refused.log

Exit status: 0 done · 1 error · 2 needs a human, or bad configuration · 3 paused at an
unbuilt stage · 4 out of time. Progress (state.json), history.log — each stage's verdict,
time, turns and cost — refused.log, and the send-back snapshots are in docs/plans/<key>/run/, committed
with the branch; every agent's full JSON result is in build/delivery/ in the worktree,
never committed. The proof is in docs/plans/<key>/04-proof.md, its evidence in build/acceptance/, and what
became of the PR in build/delivery/publish.json.
A run the bash deliver.sh started and didn't finish can't be resumed here.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from delivery.errors import BackendError, ConfigError, RunError
from delivery.model import Backend, Issue
from delivery.resolve import BackendConfig
from delivery.run import preflight as checks
from delivery.run.clock import out_of_time
from delivery.run.commit import (
    PushRejectedError,
    accepted_message,
    checkpoint_message,
    commit_all,
    failed_message,
    push,
    set_aside,
    stop_message,
)
from delivery.run.context import context_block
from delivery.run.invoke import (
    AgentRunner,
    Pass,
    finish_outputs,
    result_of,
    run_agent,
    run_claude,
)
from delivery.run.keys import (
    Paths,
    Source,
    branch_for,
    check_key,
    guard_source,
    paths_for,
    remote_for,
    render_issue,
    worktree_for,
)
from delivery.run.machine import (
    HumanStop,
    advance,
    has_writer,
    missing_outputs,
    pair_of,
    review_path,
    sendback_path,
    writer_output,
)
from delivery.run.notify import (
    NullNotifier,
    SlackNotifier,
    Transport,
    notifier_from,
    stage_ended,
    stage_started,
    thread_title,
)
from delivery.run.preview import deploy_preview
from delivery.run.publish import cited_screenshots, pr_body, pr_title
from delivery.run.record import (
    content_hash,
    load_snapshot,
    needs_human_entry,
    ran_with,
    save_snapshot,
    snapshot,
    step_refusals,
    step_stats,
    step_totals,
    touched_between,
)
from delivery.run.rules import (
    allowed_tools,
    effort_for,
    model_for,
    strays,
    turns_for,
    write_denied,
    write_scope,
)
from delivery.run.settings import Settings
from delivery.run.state import State
from delivery.run.sync import decide

__all__ = ["deliver"]

BOLD, RED, RESET = ("\033[1m", "\033[31m", "\033[0m") if sys.stderr.isatty() else ("", "", "")


def log(message: str) -> None:
    print(f"{BOLD}==> {message}{RESET}", file=sys.stderr, flush=True)  # noqa: T201


def error(message: str) -> None:
    print(f"{RED}error:{RESET} {message}", file=sys.stderr, flush=True)  # noqa: T201


def deliver(
    key: str,
    *,
    restart: bool,
    config: BackendConfig,
    backend: Backend,
    root: Path,
    env: Mapping[str, str] | None = None,
    agent: AgentRunner = run_claude,
    which: Callable[[str], str | None] = shutil.which,
    runs: Callable[[list[str]], bool] = checks.runs_quietly,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
    slack_transport: Transport | None = None,
) -> int:
    """Runs a delivery and returns its exit status. `root` is the checkout running it."""
    try:
        settings = Settings.from_env(os.environ if env is None else env)
        check_key(key, config.kind)
        problems = checks.problems(config.kind, root=root, which=which, runs=runs)
        if problems:
            log("Pre-flight failed — fix these, then run this again:")
            print("\n".join(f"  - {p}" for p in problems), file=sys.stderr)  # noqa: T201
            return 1
        issue = backend.get(key)
        run = Delivery.open(key, settings, root)
        run.issue = issue
        run.backend = backend
        run.slack = notifier_from(settings.env, transport=slack_transport, log=log)
        source = Source(config.kind, config.url, issue.number)
        return run.go(restart, render_issue(issue), source, agent=agent, sleep=sleep, clock=clock)
    except ConfigError as e:
        error(str(e))
        return 2
    except (BackendError, RunError) as e:
        error(str(e))
        return 1
    except (OSError, ValueError, TypeError, subprocess.CalledProcessError) as e:
        # A corrupt state file, a git that failed, a file that went missing: still one line.
        error(f"{type(e).__name__}: {e}")
        return 1


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True, check=False)  # noqa: S603, S607
    if done.returncode != 0:
        raise RunError(done.stderr.strip() or f"git {' '.join(args[:3])} failed")
    return done.stdout.strip()


def branch_exists(root: Path, branch: str) -> bool:
    try:
        git("-C", str(root), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")
    except RunError:
        return False
    return True


def ref_exists(root: Path, ref: str) -> bool:
    try:
        git("-C", str(root), "show-ref", "--verify", "--quiet", ref)
    except RunError:
        return False
    return True


@dataclass(frozen=True)
class Ran:
    """The stage that ran last, for the commit that follows it."""

    stage: str
    status: str
    round: int
    summary: str
    #: The file the stage left — its plan, report, review, send-back or proof — if any.
    file: str = ""
    minutes: float = 0.0
    cost: float = 0.0


@dataclass
class Delivery:
    """One issue's delivery, in its own worktree."""

    key: str
    settings: Settings
    paths: Paths
    worktree: Path
    branch: str
    #: The commit the branch left its base at: snapshots are taken against it.
    base: str
    #: Where checkpoints are pushed; empty when DELIVER_PUSH=0.
    remote: str = ""
    last: Ran | None = None
    issue: Issue | None = None
    backend: Backend | None = None
    slack: NullNotifier | SlackNotifier = dataclasses.field(default_factory=NullNotifier)
    #: Dex's password for this run's previews: random only when Slack can carry it to a
    #: person (handoff 09, decision 10). Never written anywhere.
    password: str = ""

    @property
    def run_dir(self) -> Path:
        """State, history and snapshots: committed with the plan."""
        return self.worktree / self.paths.run_dir

    @property
    def transcripts(self) -> Path:
        """Each stage's full JSON result: ignored, never committed."""
        return self.worktree / "build" / "delivery"

    @classmethod
    def open(
        cls,
        key: str,
        settings: Settings,
        root: Path,
    ) -> Delivery:
        """The worktree, made if missing, with its branch brought level with the remote's."""
        branch = branch_for(key, settings.run)
        worktree = worktree_for(root, key, settings.run)
        remote = remote_for(key, settings.remote) if settings.push else ""
        tracking = f"refs/remotes/{remote}/{branch}"
        if remote:
            log(f"Fetching {remote}")
            git("-C", str(root), "fetch", "-q", remote)
        sync = Delivery.sync(root, worktree, branch, tracking if remote else "")
        if sync.action == "stop":
            raise RunError(f"{branch}: {sync.reason}")
        if not worktree.is_dir():
            if sync.action == "track":
                log(f"Worktree {worktree} on {branch}, tracking {remote}'s")
                git(
                    "-C",
                    str(root),
                    "worktree",
                    "add",
                    "--track",
                    "-b",
                    branch,
                    str(worktree),
                    tracking,
                )
            elif sync.action == "new":
                log(f"Worktree {worktree} on a new {branch} from {settings.base}")
                git("-C", str(root), "worktree", "add", "-b", branch, str(worktree), settings.base)
            else:
                log(f"Worktree {worktree} on the existing {branch}")
                git("-C", str(root), "worktree", "add", str(worktree), branch)
        if git("-C", str(worktree), "branch", "--show-current") != branch:
            raise RunError(f"{worktree} is not on {branch} — move it or remove it")
        if sync.action == "fast-forward":
            log(f"Fast-forwarding {branch} to {remote}'s")
            git("-C", str(worktree), "merge", "-q", "--ff-only", tracking)
        base = git("-C", str(root), "rev-parse", f"{settings.base}^{{commit}}")
        run = cls(key, settings, paths_for(key), worktree, branch, base, remote)
        run.adopt_old_run_dir()
        run.run_dir.mkdir(parents=True, exist_ok=True)
        run.transcripts.mkdir(parents=True, exist_ok=True)
        (worktree / run.paths.plan_dir).mkdir(parents=True, exist_ok=True)
        # The e2e layer's Compose files read .env, which git ignores, so a new worktree has
        # none. The example is the full contract with local values.
        if not (worktree / ".env").exists():
            shutil.copy(worktree / ".env.example", worktree / ".env")
        return run

    @staticmethod
    def sync(root: Path, worktree: Path, branch: str, tracking: str):
        """What it takes to bring the branch level with the remote's; `tracking` is empty
        when there is no remote to bring it level with."""
        local = branch_exists(root, branch)
        remote = bool(tracking) and ref_exists(root, tracking)
        ahead = behind = 0
        if local and remote:
            counts = git(
                "-C", str(root), "rev-list", "--left-right", "--count", f"{branch}...{tracking}"
            )
            ahead, behind = (int(n) for n in counts.split())
        dirty = worktree.is_dir() and bool(git("-C", str(worktree), "status", "--porcelain"))
        return decide(local=local, remote=remote, ahead=ahead, behind=behind, dirty=dirty)

    def adopt_old_run_dir(self) -> None:
        """A run started before the state moved into the plan dir: carry it over."""
        old = self.transcripts
        if (old / "state.json").is_file() and not (self.run_dir / "state.json").exists():
            self.run_dir.mkdir(parents=True, exist_ok=True)
            for name in ("state.json", "history.log", *(p.name for p in old.glob("*.snapshot"))):
                if (old / name).exists():
                    shutil.move(old / name, self.run_dir / name)

    # --- the branch -----------------------------------------------------------------

    def commit(self, text: str) -> None:
        """Commits everything outside build/ and pushes it, unless pushing is off."""
        commit_all(self.worktree, text)
        if self.remote:
            push(self.worktree, self.remote, self.branch)

    @property
    def publishing(self) -> bool:
        """Whether the approval ends in a PR: the backend opens them, and the branch is pushed."""
        return bool(
            self.settings.pr
            and self.remote
            and self.backend is not None
            and self.backend.opens_pull_requests
        )

    def round_of(self, state: State, stage: str) -> int:
        return state.rounds[pair_of(stage)] if stage != "done" else 0

    # --- the loop -------------------------------------------------------------------

    def go(
        self,
        restart: bool,
        issue_text: str,
        source: Source,
        *,
        agent: AgentRunner,
        sleep: Callable[[float], None],
        clock: Callable[[], float],
    ) -> int:
        if restart:
            State.forget(self.run_dir)
            if self.publishing:
                self.back_to_draft()
        state = State.load(self.run_dir, self.settings.max_rounds)
        if state.status == "done":
            return self.already_done(state)
        guard_source(self.worktree / self.paths.source, source)
        # The issue travels with its plan, as a design doc does. Fetched every run, so an
        # issue edited to answer a question reaches the agents that read it.
        (self.worktree / self.paths.issue_copy).write_text(issue_text)
        if state.status == "needs_human":
            log(f"Resuming at {state.stage} with the answers in {self.paths.answers}")
        state.status = "running"
        self.open_thread(state, "running")
        state.save(self.run_dir)
        if self.slack.enabled:
            self.password = secrets.token_urlsafe(18)
        try:
            stopped = self.loop(state, agent, sleep, clock)
        except PushRejectedError as e:
            self.tell_failure(state, str(e))
            raise
        except RunError as e:
            # A stopped run's state and evidence must outlive the machine too.
            stage = state.stage
            self.commit(failed_message(self.key, stage, self.round_of(state, stage), str(e)))
            self.tell_failure(state, str(e))
            raise
        if stopped is not None:
            return stopped

        self.accept(state)
        where = f", pushed to {self.remote}" if self.remote else ""
        log(f"{self.key} is ready for review: {self.worktree}, branch {self.branch}{where}")
        log(
            f"Start with {self.paths.proof}. Its preview is still up: BRANCH={self.branch}"
            " scripts/deploy.sh preview url, and preview down when you're done"
        )
        # What the run took, a line a step.
        for line in (self.run_dir / "history.log").read_text().splitlines():
            print(re.sub(r"^([0-9]+ [a-z-]+ [a-z_]+ \[[^]]*\]).*", r"  \1", line), file=sys.stderr)  # noqa: T201
        return 0

    def already_done(self, state: State) -> int:
        log(f"{self.key} is already done — see {self.worktree}. --restart to plan it again")
        if self.publishing:
            # Whatever the approval's publish step didn't finish: each part is found from git
            # and the backend, so this does only what is owed.
            self.open_thread(state, "accepted")
            self.publish(state)
        return 0

    def accept(self, state: State) -> None:
        state.status = "done"
        state.save(self.run_dir)
        self.commit(accepted_message(self.key, self.last.summary if self.last else ""))
        self.report()
        self.retitle(state, "accepted")
        if self.publishing:
            self.publish(state)

    def loop(
        self,
        state: State,
        agent: AgentRunner,
        sleep: Callable[[float], None],
        clock: Callable[[], float],
    ) -> int | None:
        """Runs stages to the end; an exit status if the run stops before it."""
        while state.stage != "done":
            if out_of_time(clock(), self.settings.deadline, self.settings.deadline_margin):
                log(
                    f"Out of time — run again to continue: less than"
                    f" {self.settings.deadline_margin} minutes to the deadline, so"
                    f" {state.stage} doesn't start"
                )
                self.tell(f"⏸ out of time before {state.stage} — run again to continue")
                self.retitle(state, f"out of time before {state.stage}")
                return 4
            stopped = self.step(state, agent, sleep)
            if stopped is not None:
                return stopped
            state.save(self.run_dir)
            if state.stage != "done" and self.last:
                ran = self.last
                self.commit(
                    checkpoint_message(self.key, ran.stage, ran.status, ran.round, ran.summary)
                )
                self.report()
        return None

    def step(self, state: State, agent: AgentRunner, sleep: Callable[[float], None]) -> int | None:
        """Runs the current stage and moves the state on; an exit status if the run stops."""
        stage = state.stage
        if not (self.worktree / ".claude" / "agents" / f"{stage}.md").is_file():
            state.save(self.run_dir)
            log(f"Paused: {stage} has no agent in .claude/agents/ yet. Run this again once it has")
            return 3
        state.step += 1
        preview, proof_before = "", ""
        if not has_writer(stage):
            # The longest wait in a run: say so before it, not after.
            self.tell(f"⏳ {stage} · deploying the preview")
            preview = deploy_preview(
                self.worktree,
                evidence=self.paths.evidence,
                branch=self.branch,
                deploy_sh=self.settings.deploy_sh,
                retry_wait=self.settings.retry_wait,
                sleep=sleep,
                log=log,
                password=self.password,
            )
            if self.password and preview.startswith("up at "):
                origin = preview[len("up at ") :].split(" — ")[0]
                self.tell(
                    f"Preview of {self.branch} up at {origin} — sign in as ada@collabhub.dev"
                    f" with password `{self.password}`"
                )
            # The proof as it stood before this pass: an approval must leave its own.
            proof_before = content_hash(self.worktree / self.paths.proof)
        model = model_for(stage, state, self.settings)
        effort = effort_for(stage, state, self.settings)
        round_ = state.rounds[pair_of(stage)]
        self.tell(stage_started(stage, round_, self.ran_with(stage, model, effort)))
        # Only the stage with a preview signs in to it: every other stage's e2e signs in to
        # the Compose test stack, whose Dex keeps `collabhub`.
        with smoke_password("" if has_writer(stage) else self.password):
            result = self.run_stage(
                stage, state, model, effort, preview, agent, sleep, proof_before
            )
        status, summary = str(result["status"]), str(result.get("summary", ""))
        minutes, _, cost = step_totals(
            sorted(self.transcripts.glob(f"{state.step:02d}-*.json"))
        ) or (0.0, 0, 0.0)
        own = self.own_file(stage, status, state)
        self.last = Ran(stage, status, round_, summary, own, minutes, cost)
        stats = f"{self.stats(state.step)} · {self.ran_with(stage, model, effort)}"
        # What a stage was refused is the one clue to why it went without a tool: a public
        # repo's transcripts aren't kept.
        refused = step_refusals(
            sorted(self.transcripts.glob(f"{state.step:02d}-*.json")), hide=self.password
        )
        if refused:
            stats += f" · {len(refused)} refused"
            with (self.run_dir / "refused.log").open("a") as log_file:
                log_file.writelines(f"{state.step:02d} {stage}: {r}\n" for r in refused)
        with (self.run_dir / "history.log").open("a") as history:
            history.write(f"{state.step:02d} {stage} {status} [{stats}]: {summary}\n")
        log(f"{stage}: {status} [{stats}] — {summary}")

        moved = advance(
            state,
            stage,
            result,
            self.paths,
            self.settings,
            exists=self.holds,
            proof_rewritten=content_hash(self.worktree / self.paths.proof) != proof_before,
        )
        if moved.cleared:
            (self.run_dir / f"sendback-{stage}.snapshot").unlink(missing_ok=True)
        if moved.snapshot:
            save_snapshot(self.run_dir / f"sendback-{stage}.snapshot", self.snapshot())
        if moved.human:
            self.record_needs_human(moved.human)
        return self.stop_for_human(state) if moved.stop else None

    def run_stage(
        self,
        stage: str,
        state: State,
        model: str,
        effort: str,
        preview: str,
        agent: AgentRunner,
        sleep: Callable[[float], None],
        proof_before: str = "",
    ) -> dict:
        base = self.transcripts / f"{state.step:02d}-{stage}"
        transcript = f"{base.relative_to(self.worktree)}.json"
        before = self.snapshot()
        prompt = context_block(
            stage,
            state,
            self.settings,
            self.paths,
            worktree=self.worktree,
            branch=self.branch,
            preview=preview,
            has_reviews=self.has_reviews(),
            has_answers=self.holds(self.paths.answers),
            changed=self.changed_since_sendbacks(state, before),
        )
        turns = turns_for(stage, state, self.settings)
        p = Pass(
            stage=stage,
            prompt=prompt,
            turns=turns,
            tools=allowed_tools(stage),
            model=model,
            effort=effort,
            permission_mode=self.settings.permission_mode,
        )
        round_ = state.rounds[pair_of(stage)]
        log(
            f"{stage} — round {round_}, {turns} turns, {self.ran_with(stage, model, effort)} (log: {transcript})"
        )
        head = git("-C", str(self.worktree), "rev-parse", "HEAD")
        ran = run_agent(
            p,
            cwd=self.worktree,
            base=base,
            run=agent,
            sleep=sleep,
            retry_wait=self.settings.retry_wait,
            log=log,
        )
        # A sketch proves one stage's tests, and the next builds from the plan, never from
        # someone else's probe — gone whatever the stage returned, and if it forgot to clean.
        shutil.rmtree(self.worktree / "build" / "sketch", ignore_errors=True)
        # The rules no agent may break, checked rather than trusted — before anything else,
        # because a stage stopped mid-way may still have broken one.
        self.check_rules(stage, head, before, base)
        result = result_of(ran, stage=stage, turns=turns, round_=round_, transcript=transcript)
        # A verdict without the file it owes is asked for the file once, in its own session:
        # a few turns, where failing the run costs a person and a rerun. The machine checks
        # again, and fails as before if it is still missing.
        missing = missing_outputs(
            state,
            stage,
            result,
            self.paths,
            exists=self.holds,
            proof_rewritten=content_hash(self.worktree / self.paths.proof) != proof_before,
        )
        session = str(ran.output.get("session_id") or "")
        if missing and session:
            log(
                f"{stage} returned {result['status']} but wrote no {', '.join(missing)} — asking it for them"
            )
            finish_outputs(
                p,
                session=session,
                status=str(result["status"]),
                missing=missing,
                cwd=self.worktree,
                base=base,
                run=agent,
            )
            self.check_rules(stage, head, before, base)
        return result

    def check_rules(self, stage: str, head: str, before: dict[str, str], base: Path) -> None:
        """Stops the run on a commit or a write outside the stage's rules."""
        if git("-C", str(self.worktree), "rev-parse", "HEAD") != head:
            raise RunError(
                f"{stage} committed — the workflow never commits. Inspect {self.branch} before rerunning"
            )
        outside, refused = strays(stage, self.paths, touched_between(before, self.snapshot()))
        if outside or refused:
            # Out of the branch before the failure is committed, kept beside the transcript.
            kept = self.transcripts / "refused" / base.name
            set_aside(self.worktree, [*outside, *refused], kept)
            aside = (
                f"\nSet aside in {kept.relative_to(self.worktree)}; the branch has it as it was."
            )
            if outside:
                raise RunError(
                    f"{stage} wrote outside {write_scope(stage, self.paths)}:\n"
                    + "\n".join(outside)
                    + aside
                )
            raise RunError(
                f"{stage} wrote where it may not, {write_denied(stage, self.paths)}:\n"
                + "\n".join(refused)
                + aside
            )

    # --- helpers --------------------------------------------------------------------

    def snapshot(self) -> dict[str, str]:
        """What the branch holds since its base, outside build/ and the run's own state."""
        return snapshot(self.worktree, self.base, ignore=("build/", f"{self.paths.run_dir}/"))

    def holds(self, path: str) -> bool:
        """The worktree path exists and is not empty — the bash `[ -s ]`."""
        full = self.worktree / path
        return full.is_file() and full.stat().st_size > 0

    def has_reviews(self) -> bool:
        reviews = self.worktree / self.paths.reviews
        return reviews.is_dir() and any(reviews.iterdir())

    def changed_since_sendbacks(self, state: State, now: Mapping[str, str]) -> dict[str, list[str]]:
        changed = {}
        for sender in state.open_sendbacks:
            then = load_snapshot(self.run_dir / f"sendback-{sender}.snapshot")
            if then is not None:
                changed[sender] = touched_between(then, now)
        return changed

    def stats(self, step: int) -> str:
        return step_stats(sorted(self.transcripts.glob(f"{step:02d}-*.json")))

    def ran_with(self, stage: str, model: str, effort: str) -> str:
        return ran_with(model, effort, self.worktree / ".claude" / "agents" / f"{stage}.md")

    def record_needs_human(self, stop: HumanStop) -> None:
        first = not self.holds(self.paths.answers)
        with (self.worktree / self.paths.answers).open("a") as answers:
            answers.write(needs_human_entry(self.key, stop, first=first))

    def stop_for_human(self, state: State) -> int:
        state.status = "needs_human"
        state.save(self.run_dir)
        ran = self.last
        if ran:
            self.commit(stop_message(self.key, ran.stage, ran.round, ran.summary))
            self.report()
            self.retitle(state, f"needs a human at {ran.stage}")
        log(
            f"Needs a human: answer the questions in {self.worktree / self.paths.answers}, then run this again"
        )
        return 2

    # --- the PR (handoff 09) --------------------------------------------------------

    def publish(self, state: State) -> None:
        """Opens or updates the PR and starts its preview. A failure here leaves an accepted
        delivery accepted: it is reported, recorded for the job summary, and a rerun of the
        same key does what is owed."""
        record: dict[str, str]
        try:
            url = self.open_or_update_pr()
        except (BackendError, RunError, OSError) as e:
            if isinstance(e, PushRejectedError):
                raise
            error(f"{self.key} is accepted, but its PR could not be opened: {e}")
            self.tell(f"⚠️ accepted, but the PR could not be opened: {e}")
            record = {"error": str(e)}
        else:
            log(f"PR: {url}")
            self.tell(f"PR for {self.key}: {url}", broadcast=True)
            record = {"url": url}
        (self.transcripts / "publish.json").write_text(json.dumps(record) + "\n")

    def open_or_update_pr(self) -> str:
        assert self.backend is not None  # noqa: S101 — set by deliver().
        assert self.issue is not None  # noqa: S101
        proof_file = self.worktree / self.paths.proof
        if not proof_file.is_file():
            raise RunError(f"there is no {self.paths.proof} to open the PR from")
        proof = proof_file.read_text()
        shots = cited_screenshots(proof)
        added = self.screenshot_commits(shots)
        links = {s: self.backend.blob_url(added, f"{self.proof_dir}/{s}") for s in shots}
        body = pr_body(proof, issue_number=self.issue.number, links=links)
        title = pr_title(self.issue.title, self.key)
        pr = self.backend.find_pull_request(self.branch)
        if pr is None:
            pr = self.backend.open_pull_request(self.branch, self.settings.base, title, body)
        else:
            pr = self.backend.update_pull_request(pr.number, title=title, body=body)
            if pr.draft:
                pr = self.backend.update_pull_request(pr.number, draft=False)
        # A PR, push or edit made with GITHUB_TOKEN starts no workflow: start its preview.
        self.backend.start_preview(pr.number)
        return pr.url

    @property
    def proof_dir(self) -> str:
        return f"{self.paths.plan_dir}/proof"

    def screenshot_commits(self, shots: list[str]) -> str:
        """The commit that holds the screenshots the proof cites, made — then removed in the
        next commit — if this approval hasn't made it yet. "" when there are none."""
        if not shots:
            return ""
        added, removed = self.commits_since_accepted()
        if not added:
            missing = [s for s in shots if not (self.worktree / self.paths.evidence / s).is_file()]
            if missing:
                raise RunError(
                    "the proof cites screenshots that aren't there: "
                    + ", ".join(f"{self.paths.evidence}/{s}" for s in missing)
                )
            for shot in shots:
                target = self.worktree / self.proof_dir / shot
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.worktree / self.paths.evidence / shot, target)
            self.commit(f"delivery({self.key}): proof screenshots\n")
            added = git("-C", str(self.worktree), "rev-parse", "HEAD")
        if not removed:
            shutil.rmtree(self.worktree / self.proof_dir, ignore_errors=True)
            self.commit(f"delivery({self.key}): proof screenshots removed\n")
        return added

    def commits_since_accepted(self) -> tuple[str, str]:
        """The screenshot commits after the last `accepted`: (added, removed), "" if not made."""
        added = removed = ""
        log_ = git("-C", str(self.worktree), "log", "--format=%H %s", f"{self.base}..HEAD")
        for line in log_.splitlines():
            sha, _, subject = line.partition(" ")
            if subject == f"delivery({self.key}): accepted":
                break
            if subject == f"delivery({self.key}): proof screenshots removed":
                removed = removed or sha
            elif subject == f"delivery({self.key}): proof screenshots":
                added = added or sha
        return added, removed

    def back_to_draft(self) -> None:
        """A redelivery: its open PR goes back to a draft until the approval, so nothing
        half-built is previewed or merged."""
        assert self.backend is not None  # noqa: S101 — set by deliver().
        try:
            pr = self.backend.find_pull_request(self.branch)
            if pr is None:
                return
            if not pr.draft:
                self.backend.update_pull_request(pr.number, draft=True)
            self.backend.comment_on_pull_request(
                pr.number,
                f"A redelivery of {self.key} is running from the plan: this PR is a draft"
                " until it is accepted again.",
            )
        except BackendError as e:
            error(f"could not make {self.branch}'s PR a draft: {e}")

    # --- Slack (handoff 09) ----------------------------------------------------------

    def open_thread(self, state: State, status: str) -> None:
        """The delivery's thread: started on its first run, retitled on every other."""
        if not self.slack.enabled:
            return
        if state.slack_thread:
            self.retitle(state, status)
            return
        state.slack_thread = self.slack.post(self.title_text(status))
        state.save(self.run_dir)

    def retitle(self, state: State, status: str) -> None:
        if state.slack_thread:
            self.slack.edit(state.slack_thread, self.title_text(status))

    def title_text(self, status: str) -> str:
        env = self.settings.env
        run_url = ""
        if env.get("GITHUB_RUN_ID"):
            run_url = (
                f"{env.get('GITHUB_SERVER_URL', 'https://github.com')}/"
                f"{env.get('GITHUB_REPOSITORY', '')}/actions/runs/{env['GITHUB_RUN_ID']}"
            )
        title = self.issue.title if self.issue else ""
        return thread_title(self.key, title, status, run_url=run_url)

    def tell(self, text: str, *, broadcast: bool = False) -> None:
        """A reply in the delivery's thread; nothing without Slack."""
        if not self.slack.enabled:
            return
        state = State.load(self.run_dir, self.settings.max_rounds)
        self.slack.post(text, thread=state.slack_thread, broadcast=broadcast)

    def tell_failure(self, state: State, reason: str) -> None:
        self.tell(f"✗ failed at {state.stage}: {reason}")
        self.retitle(state, f"failed at {state.stage}")

    def report(self) -> None:
        """The stage that ran last, once its checkpoint holds its file."""
        ran = self.last
        if ran is None or not self.slack.enabled:
            return
        link = ""
        if ran.file and self.publishing and self.backend is not None:
            sha = git("-C", str(self.worktree), "rev-parse", "HEAD")
            # The file as GitHub renders it, not raw.
            link = self.backend.blob_url(sha, ran.file).removesuffix("?raw=true")
        self.tell(
            stage_ended(
                ran.stage,
                ran.status,
                minutes=ran.minutes,
                cost=ran.cost,
                summary=ran.summary,
                link=link,
            )
        )

    def own_file(self, stage: str, status: str, state: State) -> str:
        """The file a stage's verdict left — before the state moves on and its round with it."""
        if status == "done":
            return writer_output(stage, self.paths) or ""
        if status == "needs_human":
            return self.paths.answers
        if status == "send_back":
            return sendback_path(stage, state, self.paths)
        if has_writer(stage):
            return review_path(stage, state, self.paths)
        return self.paths.proof


@contextlib.contextmanager
def smoke_password(password: str):
    """The smoke packs' password, in the environment the acceptance stage's agent and its
    scripts inherit, for as long as that stage lasts — never on disk."""
    if not password:
        yield
        return
    before = os.environ.get("SMOKE_PASSWORD")
    os.environ["SMOKE_PASSWORD"] = password
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("SMOKE_PASSWORD", None)
        else:
            os.environ["SMOKE_PASSWORD"] = before
