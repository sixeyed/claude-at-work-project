"""Run state in `build/delivery/` — saved after every step, so a stopped run resumes."""

from __future__ import annotations

import json

import pytest
from delivery.errors import ConfigError
from delivery.run.state import State


def test_a_fresh_run_starts_at_the_plan_writer_with_every_pair_in_round_one():
    state = State.fresh(max_rounds=3)

    assert (state.stage, state.status, state.step, state.review) == (
        "plan-writer",
        "running",
        0,
        "",
    )
    assert state.rounds == {"plan": 1, "test": 1, "code": 1, "acceptance": 1}
    assert state.final == {"plan": 3, "test": 3, "code": 3, "acceptance": 3}
    assert state.sendbacks == {"plan": 0, "test": 0, "code": 0}
    assert state.open_sendbacks == {}
    assert state.pending == {"test": "", "code": ""}


def test_no_saved_state_is_a_fresh_run(tmp_path):
    assert State.load(tmp_path, max_rounds=4) == State.fresh(max_rounds=4)


def test_state_survives_a_save_and_a_load(tmp_path):
    state = State.fresh(max_rounds=3)
    state.stage = "test-writer"
    state.step = 5
    state.rounds["plan"] = 2
    state.final["plan"] = 4
    state.sendbacks["plan"] = 1
    state.open_sendbacks["test-reviewer"] = "docs/plans/gh-3/reviews/test-reviewer-sendback-2.md"
    state.pending["test"] = "docs/plans/gh-3/reviews/test-reviewer-1.md"

    state.save(tmp_path)

    assert State.load(tmp_path, max_rounds=3) == state
    assert json.loads((tmp_path / "state.json").read_text())["stage"] == "test-writer"


def test_a_run_the_bash_workflow_left_unfinished_is_refused(tmp_path):
    (tmp_path / "state").write_text("STAGE=code-writer\nSTATUS=needs_human\nSTEP=5\n")

    with pytest.raises(ConfigError, match="started under the bash deliver"):
        State.load(tmp_path, max_rounds=3)


def test_a_run_the_bash_workflow_finished_is_done(tmp_path):
    (tmp_path / "state").write_text("STAGE=done\nSTATUS=done\nSTEP=7\n")

    assert State.load(tmp_path, max_rounds=3).status == "done"


def test_the_slack_thread_is_saved_and_loaded(tmp_path):
    state = State.fresh(max_rounds=3)
    state.slack_thread = "1700000000.000100"

    state.save(tmp_path)

    assert State.load(tmp_path, max_rounds=3).slack_thread == "1700000000.000100"


def test_a_state_saved_before_slack_loads_with_no_thread(tmp_path):
    saved = {k: v for k, v in State.fresh(max_rounds=3).__dict__.items() if k != "slack_thread"}
    (tmp_path / "state.json").write_text(json.dumps(saved))

    assert State.load(tmp_path, max_rounds=3).slack_thread == ""
