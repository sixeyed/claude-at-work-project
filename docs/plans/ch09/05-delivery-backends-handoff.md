# Delivery backends — handoff after slice 1

Slice 1 put delivery issues behind a backend and moved the `issue-writer` skill onto it.
The next agent has three jobs:

- port `scripts/deliver.sh` to Python;
- extend the library so a delivery can run from a backend issue;
- make the agents backend-agnostic.

Read the slice's plan, `04-delivery-backends-plan.md`, its ADR,
`docs/adr/261016-pluggable-delivery-backends.md`, and the open list in
`03-acceptance-reviewer-handoff.md` (*Next: the workflow on GitHub*) first. Most of that list
lands on this work.

## Where it stands

- **The PR:** branch `feature/delivery-backends`, one commit (`a8da719`), in review as
  Forgejo PR #7. Start from `main` once it merges, or from the branch if it hasn't.
- **The library:** `tools/delivery/`, a dev-only uv workspace member (`collabhub-delivery`,
  module `delivery`, stdlib only). Its CLI is `uv run delivery`.
  - **Commands:** `check`, `issue create | get | edit | verify`, `ensure-label`.
  - **Two adaptors:** `local` (`docs/issues/NNN.md`, keys `issue-N`) and `github`
    (`gh`, keys `gh-N`).
  - **Tests:** 79 unit tests. Coverage is 86% on `github.py`; only the real `run_gh` is
    unexercised.
- **The skill:** `issue-writer` writes through the CLI. It runs `check` before grilling,
  confirms before a remote post, and reads the issue back with `issue verify`.
- **`deliver.sh` and the agents are unchanged.** `deliver.sh` still takes a local issue file
  and reads the number from an `Issue: N` line in its first 20 lines (`deliver.sh:210`).
- **Live trial repo:** https://github.com/caw-project/ch09, with issues enabled and the
  `delivery` label in place.
  - **#1:** a round-trip test. Close it.
  - **#2 and #3:** issues written with the skill. #3 (`gh-3`: display names, uniqueness, a
    clock preference) is the better candidate for the first GitHub delivery.

## How the library is built

- **`model.py`:** `Issue{key, number, title, body, url, labels}` and the `Backend`
  Protocol, which every adaptor implements in full. A new operation is a Protocol method,
  one implementation per adaptor, and a CLI subcommand in `cli.py`.
- **`resolve.py`:** turns arguments plus environment into a `BackendConfig`. The backend
  and URL come as a pair from one source: if either argument is given, the environment is
  ignored. `github.com` implies GitHub, `dev.azure.com` is refused as not built yet, and any
  other host needs `--backend`.
- **`github.py`:** every call goes through an injected `Runner`
  (`(args, stdin) -> stdout`). Unit tests drive it with the `gh` fixture (`FakeGh`) in
  `tests/conftest.py`, which records every command and returns canned output. Repos are
  named `HOST/OWNER/REPO`, bodies go on stdin with `--body-file -`, and a body over 65,536
  characters is refused before `gh` runs.
- **`local.py`:** resolves paths against the working directory (`root`), so run the CLI
  from the repo root, or from the worktree whose `docs/issues/` you mean.
- **Exit codes:** `ConfigError` exits 2, `BackendError` exits 1, and `verify` exits 1 on a
  difference.
- **Test layers:** testkit's directory-decides-the-layer rule covers `tools/<pkg>/tests/`,
  so tests under `tests/unit/` get the socket guard.
- **Importing helpers:** `from conftest import …` fails under importlib mode, so shared
  helpers are fixtures. Keep `conftest.py` free of `delivery` imports, so a broken module
  fails one test file, not collection.

## Job 1 — `deliver.sh` in Python

The script is 1,005 lines of bash 3.2. Its header is the reference for behaviour. Pieces to
carry over:

- **The state machine:** the seven stages; writer and reviewer rounds; the final round,
  with its turn and effort caps; send-backs and `DELIVER_MAX_SENDBACKS`; resume after the
  turn cap; one rerun after a crash; `needs_human` with the questions in `needs-human.md`;
  exit 3 for an unbuilt stage.
- **Per-stage settings:** the model and effort defaults (`default_model`, `model_for`,
  `effort_for`), and every `DELIVER_*` variable in the header.
- **Tool and write rules:** what each stage may run (`allowed_tools`, `read_only_bash`,
  `test_bash`, `check_bash`, `remove_bash`) and write (`write_scope`, `write_denied`).
  These are the safety boundary; port them exactly and test them as a table.
- **The context block** (`context_block`, `deliver.sh:652`). Every agent parses it, and
  `.claude/delivery/agent-context.md` documents it line by line, so a change to one is a
  change to the other.
- **The preview:** `deploy_preview` still calls `scripts/deploy.sh preview up`; Python
  wraps the call and doesn't reimplement it.
- **Run state:** `build/delivery/` in the worktree, `history.log` and resume state
  (`save_state`). A run started under bash should resume under Python, or the port should
  say plainly that it can't.

Suggestions; the user hasn't decided any of these yet:

- **Keep `scripts/deliver.sh` as the entry point.** CLAUDE.md makes `scripts/` the one
  place developers and CI start from, so it becomes a thin wrapper over
  `uv run delivery deliver …`.
- **Test the rules as pure functions:** `next_stage`, round and final-round logic,
  `model_for`, `allowed_tools`, `write_scope`, the context block. They become unit tests in
  `tools/delivery/tests/unit/`.
- **Keep `loop-test.sh` as the black-box oracle while porting.** It drives the script with
  a fake `claude` (19+ scenarios). Run it against bash first, then against the port. It
  hard-codes `Issue: 999` and `caw-issue-999-loop` (`loop-test.sh:15–27`), so it moves to
  keys along with everything else.

## Job 2 — the library, for a delivery

A delivery takes a **key**, not a file.

- **Fetching:** the runner fetches the issue through the backend and writes it to the
  worktree as `docs/plans/<key>/00-issue.md`. That file stays the agents' only view of the
  issue (ADR, decision 1).
- **Paths come from the key:** `feature/<key>`, `../caw-<key>`, `docs/plans/<key>/`. Local
  keys are `issue-N`, so every existing plan, branch and worktree keeps its name.
- **Collisions:** nothing yet stops two backends' keys landing on the same path, so add a
  guard. The ADR names this as a gap.
- **`DELIVER_RUN`'s suffix** carries over: `feature/<key>-<run>`.

Operations it will probably need, beyond what exists:

- **Labels:** set and remove one (`add_labels` / `remove_labels`), for the stage labels.
  Locally they are a no-op, or a line in `build/delivery/`.
- **Comments:** post one, and perhaps read them back, if `needs_human` questions, answers
  or the proof move onto the issue.
- **Finding work:** list issues with a label, if the GitHub Actions workflow finds its work
  that way rather than from the event payload.

## Job 3 — agents that don't know the backend

The agents already read only the issue-file copy. What ties them to local issues is
`issue-<N>` in their paths and the context block's `Issue: #N` line. Where it appears:

- **Agent descriptions:** five agents' `description:` lines (plan-writer, plan-reviewer,
  test-writer, code-writer, acceptance-reviewer), and `plan-writer.md:70`.
- **`.claude/delivery/agent-context.md`:** seven places — the team table (lines 16–22),
  line 96, the reviews path at 236, and `needs-human.md` at 379.
- **`CLAUDE.md:76`:** the delivery workflow paragraph, with three `issue-<N>` paths.
- **`docs/plans/exemplar-implementation-plan.md:65`:** the worktree line.
- **`deliver.sh`:** comments at lines 8–12, 31, 65 and 103, and `context_block`.

The likely shape: the context block names the key and every path outright (`Issue: gh-3`,
`Plan dir: docs/plans/gh-3/`), and every prompt says `docs/plans/<key>/` and takes its
paths from the block, never building one.

Three rules to keep:

- **No agent calls `delivery` or `gh`.**
- **No agent reads a URL.**
- **`loop-test.sh` stays backend-free.**

## Open — put these to the user

1. **Stage labels.** *Answered by `11-delivery-trigger-plan.md` and ADR
   `261123-a-label-starts-a-delivery`: a label per outcome, not per stage.* The names, which ones a run sets and clears, and what a failed or
   stopped run leaves. `delivery` marks an issue as written for delivery, and a separate
   trigger label, applied by a person, starts one.
2. **`needs_human` on GitHub.** Do the questions go to an issue comment, with the answers
   read from a reply, or stay in `needs-human.md` on a pushed branch? Either way it needs a
   label, so someone sees it.
3. **Who commits and pushes**, and the exception CLAUDE.md's *Never commit* rule gains.
   Handoff 03, item 1, recommends the workflow and not an agent.
4. **Preview, screenshots, the PR body, concurrency, and CI differences:** handoff 03,
   items 2–7. They come with the GitHub Actions workflow and may be a later slice than the
   port.
5. **The port's order.** I suggest porting `deliver.sh` to Python behind `loop-test.sh`
   first, with behaviour unchanged, then switching to keys and making the agents agnostic,
   then adding GitHub. The user may want it in one slice.
6. **A live GitHub test**, once a `GH_TOKEN` is in CI: the ADR leaves `gh --json` shape
   drift unguarded until then.

## Known gaps

- **`docs/test-report.md` on the branch** shows integration and end-to-end as "not run":
  slice 1 ran `lint unit` from a fresh worktree, which has no earlier results to keep. The
  next full `scripts/test.sh all` restores them.
- **Line breaks:** GitHub renders every newline in an issue body as a line break. The skill
  writes remote bodies one line per paragraph, and a ported `deliver.sh` that posts
  comments needs the same rule.
- **The `VIRTUAL_ENV` warning:** `uv run` from a worktree warns that `VIRTUAL_ENV` points at
  the primary checkout's `.venv`. Harmless: uv uses the worktree's own.
- **Issue #3's tenancy decision:** it decides D46 (display names unique across workspaces,
  which knowingly reveals that a name exists elsewhere). It doesn't record that exception
  under CLAUDE.md's *Conventions that are easy to get wrong*, so a code-reviewer may flag
  the 409 as a leak. Fix the issue before delivering it.
