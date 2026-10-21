"""The `DELIVER_*` settings, read once from the environment and checked before anything runs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from delivery.errors import ConfigError

EFFORTS = ("low", "medium", "high", "xhigh", "max")
RUN_NAME = re.compile(r"[a-zA-Z0-9_-]*")
REMOTE = re.compile(r"[a-zA-Z0-9._-]*")


@dataclass(frozen=True)
class Settings:
    max_rounds: int = 3
    max_sendbacks: int = 3
    #: A first pass's turns for every stage; None for each stage's own (`first_pass_turns`).
    max_turns: int | None = None
    rework_max_turns: int = 100
    final_max_turns: int = 60
    final_effort: str = "medium"
    base: str = "main"
    run: str = ""
    model: str = ""
    rework_model: str = ""
    effort: str = ""
    rework_effort: str = ""
    permission_mode: str = "dontAsk"
    #: Seconds before a retry — a crashed stage, a failed preview. The loop test sets 0.
    retry_wait: float = 30.0
    #: The preview's deploy script, relative to the worktree. The loop test's fake sets it.
    deploy_sh: str = "scripts/deploy.sh"
    #: Where the branch is pushed; empty for the backend's own (`keys.remote_for`).
    remote: str = ""
    #: False commits without fetching or pushing — the loop test, or a machine with no remote.
    push: bool = True
    #: False opens no PR at the approval; one opens only where the backend opens them and
    #: the branch is pushed.
    pr: bool = True
    #: Epoch seconds: no stage starts with less than `deadline_margin` minutes left.
    deadline: int | None = None
    deadline_margin: int = 75
    env: Mapping[str, str] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        final_effort = env.get("DELIVER_FINAL_EFFORT", "medium") or "medium"
        if final_effort not in EFFORTS:
            raise ConfigError("DELIVER_FINAL_EFFORT must be low, medium, high, xhigh or max")
        run = env.get("DELIVER_RUN", "")
        if not RUN_NAME.fullmatch(run):
            raise ConfigError("DELIVER_RUN may hold letters, digits, - and _ only")
        max_turns = env.get("DELIVER_MAX_TURNS", "")
        remote = env.get("DELIVER_REMOTE", "")
        if not REMOTE.fullmatch(remote):
            raise ConfigError("DELIVER_REMOTE is not a remote name")
        push = env.get("DELIVER_PUSH", "") or "1"
        if push not in ("0", "1"):
            raise ConfigError("DELIVER_PUSH must be 0 or 1")
        pr = env.get("DELIVER_PR", "") or "1"
        if pr not in ("0", "1"):
            raise ConfigError("DELIVER_PR must be 0 or 1")
        deadline = env.get("DELIVER_DEADLINE", "")
        return cls(
            max_rounds=positive(env, "DELIVER_MAX_ROUNDS", "3"),
            max_sendbacks=positive(env, "DELIVER_MAX_SENDBACKS", "3"),
            max_turns=positive(env, "DELIVER_MAX_TURNS", max_turns) if max_turns else None,
            rework_max_turns=positive(env, "DELIVER_REWORK_MAX_TURNS", "100"),
            final_max_turns=positive(env, "DELIVER_FINAL_MAX_TURNS", "60"),
            final_effort=final_effort,
            base=env.get("DELIVER_BASE", "") or "main",
            run=run,
            model=env.get("DELIVER_MODEL", ""),
            rework_model=env.get("DELIVER_REWORK_MODEL", ""),
            effort=env.get("DELIVER_EFFORT", ""),
            rework_effort=env.get("DELIVER_REWORK_EFFORT", ""),
            permission_mode=env.get("DELIVER_PERMISSION_MODE", "") or "dontAsk",
            retry_wait=float(env.get("DELIVER_RETRY_WAIT", "") or 30),
            deploy_sh=env.get("DELIVER_DEPLOY_SH", "") or "scripts/deploy.sh",
            remote=remote,
            push=push == "1",
            pr=pr == "1",
            deadline=positive(env, "DELIVER_DEADLINE", deadline) if deadline else None,
            deadline_margin=positive(env, "DELIVER_DEADLINE_MARGIN", "75"),
            env=dict(env),
        )

    def stage_model(self, stage: str) -> str:
        """`DELIVER_MODEL_<STAGE>`: test-writer -> DELIVER_MODEL_TEST_WRITER."""
        return self.env.get(f"DELIVER_MODEL_{upper(stage)}", "")

    def stage_effort(self, stage: str) -> str:
        return self.env.get(f"DELIVER_EFFORT_{upper(stage)}", "")


def upper(stage: str) -> str:
    return stage.upper().replace("-", "_")


def positive(env: Mapping[str, str], name: str, default: str) -> int:
    # Set but empty is refused, as the bash `case` did; only DELIVER_MAX_TURNS may be empty.
    value = env.get(name, default)
    if not value.isdigit() or int(value) == 0:
        raise ConfigError(f"{name} must be a positive number")
    return int(value)
