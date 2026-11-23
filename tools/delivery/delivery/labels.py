"""The labels a delivery reads and writes on its issue.

`delivery` marks an issue written for delivery and starts nothing. A person adds
`delivery:ready` to start one, or `delivery:restart` to start it again from plan-writer;
`.github/workflows/deliver-on-label.yml` swaps either for `delivery:in-progress` and
dispatches `deliver.yml`. The runner sets `in-progress` too as it starts — a laptop run or a
hand dispatch reports the same way — and swaps it at the end for the one label that says how
the run ended. Adding `delivery:ready` again resumes it. Plan: docs/plans/ch09/
11-delivery-trigger-plan.md.

Every change removes only labels the issue carries: `gh issue edit --remove-label` refuses a
label the repo doesn't have.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

MARKER = "delivery"
READY = "delivery:ready"
RESTART = "delivery:restart"
IN_PROGRESS = "delivery:in-progress"
ACCEPTED = "delivery:accepted"
NEEDS_HUMAN = "delivery:needs-human"
OUT_OF_TIME = "delivery:out-of-time"
FAILED = "delivery:failed"
TRIGGERS = (READY, RESTART)
ENDS = (ACCEPTED, NEEDS_HUMAN, OUT_OF_TIME, FAILED)

#: name -> (description, colour): what `delivery ensure-labels` makes.
LABELS: dict[str, tuple[str, str]] = {
    MARKER: ("Written for the delivery team (scripts/deliver.sh)", "0e8a16"),
    READY: ("Add to start a delivery — or to resume one", "1d76db"),
    RESTART: ("Add to start a delivery again from plan-writer", "5319e7"),
    IN_PROGRESS: ("A delivery is running", "fbca04"),
    ACCEPTED: ("Delivered and accepted: the PR is open", "0e8a16"),
    NEEDS_HUMAN: ("Stopped for a human: answer needs-human.md, then add delivery:ready", "d93f0b"),
    OUT_OF_TIME: ("Ran out of time: add delivery:ready to continue", "c5def5"),
    FAILED: ("The delivery failed: read the run's log before adding delivery:ready", "b60205"),
}

#: The permissions that may start a run, as GitHub's collaborators endpoint names them:
#: maintain reads as write, triage as read.
CAN_START = frozenset({"admin", "write"})

END_FOR = {0: ACCEPTED, 2: NEEDS_HUMAN, 4: OUT_OF_TIME}


@dataclass(frozen=True)
class LabelChange:
    add: tuple[str, ...]
    remove: tuple[str, ...]

    def __bool__(self) -> bool:
        return bool(self.add or self.remove)


NO_CHANGE = LabelChange(add=(), remove=())


@dataclass(frozen=True)
class Trigger:
    """What `delivery trigger` does: start or not, and the labels it changes either way."""

    start: bool
    restart: bool
    #: One line for the job summary.
    reason: str
    labels: LabelChange


def end_label(status: int) -> str:
    """The label a run's exit status leaves: 0 accepted, 2 needs a human, 4 out of time,
    anything else — an error, a pause at an unbuilt stage, a kill — failed."""
    return END_FOR.get(status, FAILED)


def starting(labels: Sequence[str]) -> LabelChange:
    """The triggers and the last run's end come off; `in-progress` goes on."""
    remove = tuple(name for name in labels if name in TRIGGERS or name in ENDS)
    add = () if IN_PROGRESS in labels else (IN_PROGRESS,)
    return LabelChange(add=add, remove=remove)


def ending(labels: Sequence[str], status: int) -> LabelChange:
    """`in-progress` and any other end come off; this run's end goes on. A trigger added
    mid-run stays, for the run it starts."""
    end = end_label(status)
    remove = tuple(name for name in labels if name == IN_PROGRESS or (name in ENDS and name != end))
    add = () if end in labels else (end,)
    return LabelChange(add=add, remove=remove)


def decide_trigger(*, labels: Sequence[str], state: str, permission: str) -> Trigger:
    """Whether the issue's labels, as they are now, start a run.

    Read now, not from the event: two labels added together fire two events, and the first
    run takes both triggers off, so the second finds none and does nothing."""
    triggers = tuple(name for name in labels if name in TRIGGERS)
    if not triggers:
        return Trigger(False, False, "no trigger label — another run took it", NO_CHANGE)
    take_off = LabelChange(add=(), remove=triggers)
    if state.upper() != "OPEN":
        return Trigger(False, False, "the issue is closed — reopen it first", take_off)
    if permission.lower() not in CAN_START:
        return Trigger(
            False,
            False,
            f"only someone with write access can start a delivery — the sender has"
            f" {permission or 'none'}",
            take_off,
        )
    restart = RESTART in triggers
    reason = "started, from plan-writer again" if restart else "started"
    return Trigger(True, restart, reason, starting(labels))
