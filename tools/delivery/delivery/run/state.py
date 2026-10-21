"""Run state: where a delivery is, saved to `docs/plans/<key>/run/state.json` after every step
and committed with the checkpoint that follows it."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from delivery.errors import ConfigError

PAIRS = ("plan", "test", "code", "acceptance")
#: Pairs that can be sent back to — every pair with a writer.
SENT_BACK_TO = ("plan", "test", "code")
#: Reviewer pairs whose review can wait for their writer after a send-back.
PENDING = ("test", "code")
STATE = "state.json"
#: The bash workflow's state file: shell assignments, which this one doesn't resume.
BASH_STATE = "state"


@dataclass
class State:
    stage: str = "plan-writer"
    status: str = "running"
    step: int = 0
    #: The review or send-back file the next writer answers.
    review: str = ""
    rounds: dict[str, int] = field(default_factory=dict)
    #: Each pair's final round. A send-back moves it out, so it is state, not a setting.
    final: dict[str, int] = field(default_factory=dict)
    #: Send-backs each pair has taken.
    sendbacks: dict[str, int] = field(default_factory=dict)
    #: A send-back still open, by the stage that sent it: the file that says why. Open
    #: until that stage runs again; more than one can be open at once.
    open_sendbacks: dict[str, str] = field(default_factory=dict)
    #: A reviewer's review, written as it sent work back, waiting for its own writer.
    pending: dict[str, str] = field(default_factory=dict)
    #: The delivery's Slack thread — its parent message's `ts` — so a resumed run, on any
    #: machine, replies in it. Empty without Slack.
    slack_thread: str = ""

    @classmethod
    def fresh(cls, max_rounds: int) -> State:
        return cls(
            rounds=dict.fromkeys(PAIRS, 1),
            final=dict.fromkeys(PAIRS, max_rounds),
            sendbacks=dict.fromkeys(SENT_BACK_TO, 0),
            pending=dict.fromkeys(PENDING, ""),
        )

    @classmethod
    def load(cls, run_dir: Path, max_rounds: int) -> State:
        path = run_dir / STATE
        if path.is_file():
            return cls(**json.loads(path.read_text()))
        bash = run_dir / BASH_STATE
        if bash.is_file():
            if "STATUS=done" in bash.read_text().splitlines():
                return cls(**{**asdict(cls.fresh(max_rounds)), "stage": "done", "status": "done"})
            raise ConfigError(
                f"{bash} was started under the bash deliver.sh, which this one can't resume"
                " — finish it with the bash workflow, or start again with --restart"
            )
        return cls.fresh(max_rounds)

    def save(self, run_dir: Path) -> None:
        (run_dir / STATE).write_text(json.dumps(asdict(self), indent=2) + "\n")

    @staticmethod
    def forget(run_dir: Path) -> None:
        for name in (STATE, BASH_STATE):
            (run_dir / name).unlink(missing_ok=True)
