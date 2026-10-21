"""One stage's agent: a headless `claude` run, rerun once after a crash and resumed once
after the turn cap, its result checked rather than trusted."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from delivery.errors import RunError

#: Runs `claude` with these arguments in this directory and returns what it printed. A
#: stage that runs out of turns exits non-zero with a JSON result, so the output decides
#: whether it failed, not the exit status.
AgentRunner = Callable[[list[str], Path], str]

# What every agent returns. The status a stage may use depends on its role, and is checked
# by the state machine, not here, so one schema serves all seven. --json-schema works
# through a StructuredOutput tool, and an agent's `tools:` line is an allowlist that drops
# it — so every agent in .claude/agents/ must list StructuredOutput, or it writes its JSON
# as text and the stage fails with "no structured result".
RESULT_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["done", "approved", "changes_requested", "send_back", "needs_human"],
            },
            "summary": {"type": "string"},
            "files": {"type": "array", "items": {"type": "string"}},
            "questions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["status", "summary", "files", "questions"],
        "additionalProperties": False,
    }
)

RESUME = (
    "You ran out of turns before you finished. Everything you wrote is in place, and this is"
    " the same session: don't start again, and don't reread what you have read. You have"
    " {more} more turns. Finish what is left, most important first, write your output file,"
    " and return your result through StructuredOutput. If it can't all be done in that, say"
    " in the output file what is done and what is not, and return anyway."
)


MISSING = (
    "You returned {status}, but these files your result needs are not there: {files}. This"
    " is the same session: don't redo the work. Write each one as your instructions say,"
    " from what you have already found, and return the same result through StructuredOutput."
)

#: Enough to write a file from what the session already holds, and no more.
MISSING_TURNS = 20


#: What no agent or script the runner starts is given.
RUNNER_ONLY = frozenset({"SLACK_BOT_TOKEN", "SLACK_CHANNEL"})


def agent_env(env: Mapping[str, str]) -> dict[str, str]:
    """The environment an agent or the deploy script runs in: the caller's, minus the
    virtualenv `uv run` started this runner in. That one is the primary checkout's — its
    editable installs are main's code, not the branch's — and the worktree has its own.
    Only an active virtualenv's own `bin` comes off PATH, never anything else. Slack stays
    with the runner, which does all the posting: a token an agent holds, a tool can print."""
    env = {k: v for k, v in env.items() if k not in RUNNER_ONLY}
    venv = env.get("VIRTUAL_ENV")
    if not venv:
        return dict(env)
    venv_bin = str(Path(venv) / "bin")
    cleaned = {k: v for k, v in env.items() if k != "VIRTUAL_ENV"}
    if "PATH" in cleaned:
        cleaned["PATH"] = os.pathsep.join(
            p for p in cleaned["PATH"].split(os.pathsep) if p != venv_bin
        )
    return cleaned


def run_claude(args: list[str], cwd: Path) -> str:
    try:
        done = subprocess.run(  # noqa: S603 — fixed program, argument list.
            ["claude", *args],  # noqa: S607 — claude from PATH; the loop test puts a fake first.
            cwd=cwd,
            env=agent_env(os.environ),
            stdout=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise RunError("claude is not on PATH") from e
    return done.stdout


@dataclass(frozen=True)
class Pass:
    """One stage's run: what it is told, and what it may use."""

    stage: str
    prompt: str
    turns: int
    tools: list[str]
    model: str
    effort: str
    permission_mode: str


def claude_args(
    p: Pass, *, prompt: str | None = None, turns: int | None = None, resume: str = ""
) -> list[str]:
    args = ["-p", p.prompt if prompt is None else prompt]
    if resume:
        args += ["--resume", resume]
    args += ["--agent", p.stage, "--max-turns", str(p.turns if turns is None else turns)]
    args += ["--allowedTools", *p.tools]
    if p.model:
        args += ["--model", p.model]
    if p.effort:
        args += ["--effort", p.effort]
    return [
        *args,
        "--output-format",
        "json",
        "--json-schema",
        RESULT_SCHEMA,
        "--permission-mode",
        p.permission_mode,
    ]


@dataclass(frozen=True)
class Ran:
    """How a pass ended: the result subtype, and the transcript's JSON."""

    subtype: str
    output: dict
    turns: int


def run_agent(
    p: Pass,
    *,
    cwd: Path,
    base: Path,
    run: AgentRunner,
    sleep: Callable[[float], None],
    retry_wait: float = 30.0,
    log: Callable[[str], None] = lambda _: None,
) -> Ran:
    """Runs a pass, writing its transcript to `<base>.json`, with `.failed.json` and
    `.out-of-turns.json` beside it for a crash and a turn cap."""
    out = base.with_name(base.name + ".json")

    def invoke(args: list[str]) -> dict | None:
        text = run(args, cwd)
        out.write_text(text)
        return parsed(text)

    found = invoke(claude_args(p))
    # No result at all, or an error that isn't the turn cap: the API or the network, not
    # the agent. Run it once more from the top — a writer finds its partial work in place
    # and a reviewer its partial review.
    if not subtype_of(found) or (
        subtype_of(found) != "error_max_turns" and found.get("is_error") is not False
    ):  # type: ignore[union-attr]
        log(
            f"{p.stage} failed without a result ({subtype_of(found) or 'no output'}) — running it once more"
        )
        out.rename(base.with_name(base.name + ".failed.json"))
        sleep(retry_wait)
        found = invoke(claude_args(p))
        if not subtype_of(found):
            raise RunError(f"{p.stage} failed twice — see {out}")

    # Out of turns is the cap working, not a crash. Resume the same session once, with half
    # as many turns again and told to finish: everything it has read is still in its
    # context, so this costs far less than a rerun.
    if subtype_of(found) == "error_max_turns":
        session = found.get("session_id") or ""  # type: ignore[union-attr]
        more = max(p.turns // 2, 30)
        if session:
            log(f"{p.stage} used all {p.turns} turns — resuming it with {more} more to finish")
            out.rename(base.with_name(base.name + ".out-of-turns.json"))
            found = invoke(
                claude_args(p, prompt=RESUME.format(more=more), turns=more, resume=session)
            )
            if not subtype_of(found):
                raise RunError(f"{p.stage} failed when resumed — see {out}")
    assert found is not None  # noqa: S101 — every path above has a result or raised.
    return Ran(subtype=subtype_of(found), output=found, turns=p.turns)


def finish_outputs(
    p: Pass,
    *,
    session: str,
    status: str,
    missing: list[str],
    cwd: Path,
    base: Path,
    run: AgentRunner,
) -> Ran:
    """Resumes a pass that returned its verdict without the files it owes, once, to write
    them — transcript in `<base>.missing.json`. Whether they are there now is the state
    machine's to check, as for any pass."""
    out = base.with_name(base.name + ".missing.json")
    text = run(
        claude_args(
            p,
            prompt=MISSING.format(status=status, files=", ".join(missing)),
            turns=MISSING_TURNS,
            resume=session,
        ),
        cwd,
    )
    out.write_text(text)
    found = parsed(text)
    if not subtype_of(found):
        raise RunError(f"{p.stage} failed when asked for {', '.join(missing)} — see {out}")
    assert found is not None  # noqa: S101 — a subtype means a parsed result.
    return Ran(subtype=subtype_of(found), output=found, turns=MISSING_TURNS)


def result_of(ran: Ran, *, stage: str, turns: int, round_: int, transcript: str) -> dict:
    """The stage's structured result — or, still out of turns after the resume, a stop for
    a human with its partial work left where it is."""
    if ran.subtype == "error_max_turns":
        return {
            "status": "needs_human",
            "summary": (
                f"{stage} used all {turns} turns in round {round_}, and the turns it was resumed"
                f" with, without finishing. Its transcript is in {transcript}; anything it wrote"
                " is left in place."
            ),
            "files": [],
            "questions": [
                (
                    f"{stage} ran out of turns twice. Rerun it as it is, rerun with a larger"
                    " DELIVER_MAX_TURNS, DELIVER_REWORK_MAX_TURNS or DELIVER_FINAL_MAX_TURNS,"
                    " or answer here what it was stuck on — which?"
                )
            ],
        }
    if ran.output.get("is_error") is not False:
        raise RunError(f"{stage} ended in error ({ran.subtype}) — see {transcript}")
    structured = ran.output.get("structured_output")
    if not isinstance(structured, dict) or not structured.get("status"):
        raise RunError(f"{stage} returned no structured result — see {transcript}")
    return structured


def parsed(text: str) -> dict | None:
    try:
        found = json.loads(text)
    except json.JSONDecodeError:
        return None
    return found if isinstance(found, dict) else None


def subtype_of(found: dict | None) -> str:
    return str(found.get("subtype") or "") if found else ""
