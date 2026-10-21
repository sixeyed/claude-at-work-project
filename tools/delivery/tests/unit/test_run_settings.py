"""The `DELIVER_*` settings — the same names, defaults and refusals as the bash header."""

from __future__ import annotations

import pytest
from delivery.errors import ConfigError
from delivery.run.settings import Settings


def test_the_defaults_are_the_bash_ones():
    s = Settings.from_env({})

    assert (s.max_rounds, s.max_sendbacks, s.max_turns) == (3, 3, None)
    assert (s.rework_max_turns, s.final_max_turns, s.final_effort) == (100, 60, "medium")
    assert (s.base, s.run, s.permission_mode) == ("main", "", "dontAsk")
    assert (s.model, s.rework_model, s.effort, s.rework_effort) == ("", "", "", "")
    assert (s.retry_wait, s.deploy_sh) == (30.0, "scripts/deploy.sh")
    assert (s.remote, s.push, s.deadline, s.deadline_margin) == ("", True, None, 75)
    assert s.pr is True


def test_pushing_can_be_turned_off_and_the_remote_named():
    s = Settings.from_env({"DELIVER_PUSH": "0", "DELIVER_REMOTE": "upstream"})

    assert (s.push, s.remote) == (False, "upstream")


def test_the_pull_request_can_be_turned_off():
    assert Settings.from_env({"DELIVER_PR": "0"}).pr is False
    assert Settings.from_env({"DELIVER_PR": "1"}).pr is True
    assert Settings.from_env({"DELIVER_PR": ""}).pr is True


def test_a_deadline_is_epoch_seconds_and_its_margin_minutes():
    s = Settings.from_env({"DELIVER_DEADLINE": "1792150000", "DELIVER_DEADLINE_MARGIN": "30"})

    assert (s.deadline, s.deadline_margin) == (1792150000, 30)


def test_a_stages_own_setting_is_read_by_its_name():
    s = Settings.from_env(
        {"DELIVER_MODEL_TEST_WRITER": "opus", "DELIVER_EFFORT_CODE_REVIEWER": "high"}
    )

    assert s.stage_model("test-writer") == "opus"
    assert s.stage_effort("code-reviewer") == "high"
    assert s.stage_model("plan-writer") == ""


@pytest.mark.parametrize(
    ("env", "says"),
    [
        ({"DELIVER_MAX_ROUNDS": "0"}, "DELIVER_MAX_ROUNDS must be a positive number"),
        ({"DELIVER_MAX_SENDBACKS": "x"}, "DELIVER_MAX_SENDBACKS must be a positive number"),
        ({"DELIVER_REWORK_MAX_TURNS": ""}, "DELIVER_REWORK_MAX_TURNS must be a positive number"),
        ({"DELIVER_MAX_TURNS": "-3"}, "DELIVER_MAX_TURNS must be a positive number"),
        ({"DELIVER_PUSH": "no"}, "DELIVER_PUSH must be 0 or 1"),
        ({"DELIVER_PR": "yes"}, "DELIVER_PR must be 0 or 1"),
        ({"DELIVER_DEADLINE": "tomorrow"}, "DELIVER_DEADLINE must be a positive number"),
        ({"DELIVER_DEADLINE_MARGIN": "0"}, "DELIVER_DEADLINE_MARGIN must be a positive number"),
        ({"DELIVER_REMOTE": "a b"}, "DELIVER_REMOTE is not a remote name"),
        ({"DELIVER_RUN": "a b"}, "DELIVER_RUN may hold letters, digits, - and _ only"),
        (
            {"DELIVER_FINAL_EFFORT": "huge"},
            "DELIVER_FINAL_EFFORT must be low, medium, high, xhigh or max",
        ),
    ],
)
def test_a_bad_setting_is_refused(env, says):
    with pytest.raises(ConfigError, match=says):
        Settings.from_env(env)


def test_an_empty_max_turns_means_by_stage():
    assert Settings.from_env({"DELIVER_MAX_TURNS": ""}).max_turns is None
