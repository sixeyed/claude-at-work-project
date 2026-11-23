"""The delivery labels: what starts a run, and what a run leaves on its issue."""

from __future__ import annotations

import pytest
from delivery.labels import (
    ACCEPTED,
    ENDS,
    FAILED,
    IN_PROGRESS,
    LABELS,
    MARKER,
    NEEDS_HUMAN,
    OUT_OF_TIME,
    READY,
    RESTART,
    TRIGGERS,
    LabelChange,
    decide_trigger,
    end_label,
    ending,
    starting,
)


def test_there_are_eight_labels_each_with_a_description_and_a_colour():
    assert set(LABELS) == {MARKER, *TRIGGERS, IN_PROGRESS, *ENDS}
    assert len(LABELS) == 8
    for description, colour in LABELS.values():
        assert description
        assert len(colour) == 6
        int(colour, 16)


def test_the_label_names():
    assert (MARKER, READY, RESTART, IN_PROGRESS) == (
        "delivery",
        "delivery:ready",
        "delivery:restart",
        "delivery:in-progress",
    )
    assert ENDS == (
        "delivery:accepted",
        "delivery:needs-human",
        "delivery:out-of-time",
        "delivery:failed",
    )


# --- end_label ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "label"),
    [
        (0, ACCEPTED),
        (2, NEEDS_HUMAN),
        (4, OUT_OF_TIME),
        (1, FAILED),
        # Paused at a stage with no agent: no longer a state a run should reach.
        (3, FAILED),
        (137, FAILED),
    ],
)
def test_each_exit_status_has_one_end_label(status, label):
    assert end_label(status) == label


# --- starting ----------------------------------------------------------------


def test_starting_swaps_the_triggers_for_in_progress():
    change = starting([MARKER, READY, "bug"])

    assert change == LabelChange(add=(IN_PROGRESS,), remove=(READY,))


def test_starting_takes_off_the_last_runs_end_and_both_triggers():
    change = starting([MARKER, NEEDS_HUMAN, READY, RESTART])

    assert change.add == (IN_PROGRESS,)
    assert set(change.remove) == {NEEDS_HUMAN, READY, RESTART}


def test_starting_removes_only_labels_the_issue_has():
    # gh refuses to remove a label the issue doesn't carry.
    assert starting([MARKER]) == LabelChange(add=(IN_PROGRESS,), remove=())


def test_starting_with_in_progress_already_on_adds_nothing():
    # The trigger workflow sets it, then the runner it dispatched sets it again.
    assert starting([MARKER, IN_PROGRESS]) == LabelChange(add=(), remove=())


# --- ending ------------------------------------------------------------------


@pytest.mark.parametrize(("status", "label"), [(0, ACCEPTED), (2, NEEDS_HUMAN), (1, FAILED)])
def test_ending_swaps_in_progress_for_the_end(status, label):
    assert ending([MARKER, IN_PROGRESS], status) == LabelChange(add=(label,), remove=(IN_PROGRESS,))


def test_ending_takes_off_any_other_end_and_keeps_the_rest():
    # A person added one mid-run, or a run before this one left it.
    change = ending([MARKER, IN_PROGRESS, FAILED, "bug"], 0)

    assert change.add == (ACCEPTED,)
    assert set(change.remove) == {IN_PROGRESS, FAILED}


def test_ending_leaves_a_trigger_added_mid_run_for_its_own_run():
    change = ending([IN_PROGRESS, READY], 4)

    assert READY not in change.remove


def test_ending_with_its_end_already_on_adds_nothing():
    assert ending([ACCEPTED], 0) == LabelChange(add=(), remove=())


# --- decide_trigger ----------------------------------------------------------


def test_ready_on_an_open_issue_from_a_writer_starts_a_run():
    trigger = decide_trigger(labels=[MARKER, READY], state="OPEN", permission="write")

    assert trigger.start
    assert not trigger.restart
    assert trigger.labels == LabelChange(add=(IN_PROGRESS,), remove=(READY,))
    assert trigger.reason


@pytest.mark.parametrize("labels", [[RESTART], [READY, RESTART], [RESTART, READY]])
def test_restart_starts_a_restarted_run_with_or_without_ready(labels):
    trigger = decide_trigger(labels=labels, state="OPEN", permission="admin")

    assert trigger.start
    assert trigger.restart
    assert set(trigger.labels.remove) == set(labels)


def test_an_issue_with_no_trigger_label_starts_nothing_and_changes_nothing():
    # The second of two events: the first run took the labels off already.
    trigger = decide_trigger(labels=[MARKER, IN_PROGRESS], state="OPEN", permission="admin")

    assert not trigger.start
    assert trigger.labels == LabelChange(add=(), remove=())
    assert "no trigger label" in trigger.reason


def test_a_closed_issue_is_refused_and_its_trigger_taken_off():
    trigger = decide_trigger(labels=[MARKER, READY], state="CLOSED", permission="admin")

    assert not trigger.start
    assert trigger.labels == LabelChange(add=(), remove=(READY,))
    assert "closed" in trigger.reason


@pytest.mark.parametrize("permission", ["read", "none", "triage", ""])
def test_a_sender_who_cannot_write_is_refused_and_the_trigger_taken_off(permission):
    trigger = decide_trigger(labels=[READY, RESTART], state="OPEN", permission=permission)

    assert not trigger.start
    assert set(trigger.labels.remove) == {READY, RESTART}
    assert trigger.labels.add == ()
    assert "write" in trigger.reason


def test_the_state_is_read_whatever_its_case():
    assert decide_trigger(labels=[READY], state="open", permission="write").start
    assert not decide_trigger(labels=[READY], state="closed", permission="write").start
