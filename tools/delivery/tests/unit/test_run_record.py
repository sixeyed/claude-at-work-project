"""What a run writes for people: `history.log`'s stats, `needs-human.md`, and what a stage
changed — each the bash `deliver.sh`'s format, so measured runs stay comparable."""

from __future__ import annotations

import json

from delivery.run.machine import HumanStop
from delivery.run.record import (
    needs_human_entry,
    ran_with,
    step_refusals,
    step_stats,
    touched_between,
)


def transcript(path, minutes=1.0, turns=3, cost=0.5):
    path.write_text(
        json.dumps({"duration_ms": minutes * 60000, "num_turns": turns, "total_cost_usd": cost})
    )
    return path


def test_a_steps_stats_add_up_every_run_it_took(tmp_path):
    files = [
        transcript(tmp_path / "01-plan-writer.out-of-turns.json"),
        transcript(tmp_path / "01-plan-writer.json"),
    ]

    assert step_stats(files) == "2m 6 turns $1"


def test_stats_round_as_jq_did(tmp_path):
    files = [transcript(tmp_path / "02-x.json", minutes=1.25, turns=7, cost=0.125)]

    assert step_stats(files) == "1.3m 7 turns $0.13"


def test_a_crash_that_left_nothing_counts_for_nothing(tmp_path):
    empty = tmp_path / "01-plan-writer.failed.json"
    empty.write_text("")

    assert step_stats([empty, transcript(tmp_path / "01-plan-writer.json")]) == "1m 3 turns $0.5"


def test_a_transcript_that_is_not_json_means_no_stats(tmp_path):
    bad = tmp_path / "01-x.json"
    bad.write_text("{oops")

    assert step_stats([bad]) == "no stats"


def refusing(path, *commands, tools=()):
    denials = [
        {"tool_name": "Bash", "tool_use_id": "t", "tool_input": {"command": c}} for c in commands
    ] + [{"tool_name": t, "tool_use_id": "t", "tool_input": {"file_path": "x.md"}} for t in tools]
    path.write_text(json.dumps({"num_turns": 3, "permission_denials": denials}))
    return path


def test_a_steps_refusals_are_every_one_in_every_run_it_took(tmp_path):
    files = [
        refusing(tmp_path / "08-test-reviewer.out-of-turns.json", 'npm test | grep -v "^$"'),
        refusing(tmp_path / "08-test-reviewer.json", "git log; echo $?", tools=("WebFetch",)),
    ]

    assert step_refusals(files) == ['npm test | grep -v "^$"', "git log; echo $?", "WebFetch x.md"]


def test_a_refused_command_is_kept_to_one_short_line(tmp_path):
    files = [refusing(tmp_path / "05-x.json", "cat >> a.md <<'EOF'\nbody\nEOF", "ls " + "a" * 300)]

    first, second = step_refusals(files)

    assert first == "cat >> a.md <<'EOF' …"
    assert len(second) <= 160
    assert second.endswith("…")


def test_the_preview_password_never_reaches_the_record(tmp_path):
    files = [refusing(tmp_path / "14-x.json", "curl -u ada:s3cret-pw https://p")]

    assert step_refusals(files, hide="s3cret-pw") == ["curl -u ada:*** https://p"]


def test_a_transcript_that_cannot_be_read_refused_nothing(tmp_path):
    bad = tmp_path / "01-x.json"
    bad.write_text("{oops")
    empty = tmp_path / "01-x.failed.json"
    empty.write_text("")

    assert step_refusals([bad, empty]) == []


def test_ran_with_names_the_agents_own_model_when_none_is_passed(tmp_path):
    agent = tmp_path / "plan-writer.md"
    agent.write_text("---\nname: plan-writer\nmodel: opus\n---\n")

    assert ran_with("", "", agent) == "opus · default"
    assert ran_with("haiku", "low", agent) == "haiku · low"
    assert ran_with("", "", tmp_path / "missing.md") == "default · default"


def test_the_first_stop_heads_the_questions_file():
    stop = HumanStop(stage="plan-writer", round=1, summary="stuck", questions=["Which?", "And?"])

    assert needs_human_entry("gh-3", stop, first=True) == (
        "# gh-3 — questions for a human\n"
        "\n## plan-writer stopped, round 1\n\nstuck\n\n"
        "1. Which?\n\n   **Answer:**\n\n"
        "2. And?\n\n   **Answer:**\n\n"
    )


def test_a_later_stop_is_appended_without_the_heading():
    stop = HumanStop(stage="code-writer", round=2, summary="again", questions=["Q?"])

    assert needs_human_entry("gh-3", stop, first=False).startswith(
        "\n## code-writer stopped, round 2"
    )


def test_touched_between_names_every_path_that_changed():
    before = {"a.py": "h1", "b.py": "h2", "gone.py": "h3"}
    after = {"a.py": "h1", "b.py": "h9", "new.py": "h4"}

    assert touched_between(before, after) == ["b.py", "gone.py", "new.py"]
