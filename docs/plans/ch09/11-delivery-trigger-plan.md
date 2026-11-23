# A label starts a delivery — slice 5: the trigger, and labels for its state

Slice 4 (`10-delivery-pr-plan.md`) ended an accepted GitHub delivery at a PR with a preview
held open, but a person still starts it from the Actions tab, by dispatching `deliver.yml`
with the issue's key. This slice starts it from the issue: a person adds `delivery:ready`,
and labels on the issue say how the run is going and how it ended.

Settled in a grilling session on 2026-11-23. Handoff 05's open item 1 (stage labels, a
trigger label apart from the `delivery` marker) is answered here; its item 2 (`needs_human`
as an issue comment) stays open — the label says a human is needed, the questions stay in
`needs-human.md` on the branch.

## Decided

| # | Decision |
|---|---|
| 1 | **`delivery` stays the marker** the `issue-writer` skill adds when it posts an issue. It starts nothing. |
| 2 | **`delivery:ready`, added by a person, starts a delivery.** `delivery:restart` starts one with `--restart`; on its own it is enough, and with `ready` it wins. No other option has a label: model and stub stay on the dispatch form, and a label run takes the defaults. |
| 3 | **Labels report the run.** `delivery:in-progress` while it runs; at the end exactly one of `delivery:accepted` (exit 0), `delivery:needs-human` (2), `delivery:out-of-time` (4) or `delivery:failed` (1, 3, or a run that never reported). No issue comment — the labels are the feedback. |
| 4 | **The labels come off as the next run starts**: the trigger labels and any status label, swapped for `in-progress`. Adding `delivery:ready` again is how a person resumes after answering `needs-human.md` or running out of time. |
| 5 | **The trigger is its own workflow, `deliver-on-label.yml`.** Every label added to any issue fires `issues: labeled`, and GitHub can't filter the trigger by label name, so most of its runs are skipped ones. In their own workflow they leave `deliver.yml`'s list holding only deliveries. It checks, swaps the labels and dispatches `deliver.yml`. |
| 6 | **Only a sender with write or admin access starts a run.** A run costs real money; triage can add labels. |
| 7 | **A closed issue starts nothing.** Refused — closed, or the sender can't — the trigger label is taken off and the reason goes in the job summary. An accepted issue is let through: a rerun of an accepted key does only what its publish step still owes (handoff 09, decision 14). |
| 8 | **Duplicate events dedupe on the issue's current labels.** `deliver-on-label` has one concurrency group per issue, queued, not cancelled. Each run reads the labels as they are now, not the event's: the first takes the trigger labels off before it dispatches, so the second finds none and stops. |
| 9 | **The runner sets the status labels**, through the backend, so a laptop run of `scripts/deliver.sh gh-N` and a hand dispatch report on the issue as a label run does. The local backend has no labels and does nothing. A label that can't be set is logged and never fails a run, as a Slack post isn't. |
| 10 | **`deliver.yml` keeps a fallback**: an `always()` step that swaps a `delivery:in-progress` still on the issue for `delivery:failed` — a cancel, a kill, a job timeout. |
| 11 | **Labels are made where they are needed.** The runner ensures a label it fails to add, then tries once more; `delivery ensure-labels` makes all eight, and the `issue-writer` skill runs it in place of `ensure-label delivery`; `delivery prereqs` reports any that are missing. |
| 12 | **Its proof is a stub run started by the label**, then one real run. A repo variable, `DELIVER_STUB=1`, makes `deliver-on-label` dispatch with `stub=true` — set for the proof, deleted after. (The grilling said a hidden `stub` input on a hand dispatch; a variable proves the real path, a person adding a label.) |

Events caused by `GITHUB_TOKEN` start no workflow, except `workflow_dispatch`: the labels a
run sets inside Actions fire nothing, and `deliver-on-label`'s dispatch of `deliver.yml`
works. A laptop run's labels are set with the person's own `gh`, so each fires a
`deliver-on-label` run that finds no trigger label and stops.

## Shapes

```
tools/delivery/delivery/labels.py      pure: the label set, the trigger decision, the end label
tools/delivery/delivery/model.py       Issue gains `state`; Backend gains set_labels,
                                       permission, start_delivery
tools/delivery/delivery/github.py      gh issue edit --add-label/--remove-label, gh api …/permission,
                                       gh workflow run deliver.yml
tools/delivery/delivery/local.py       no labels: set_labels does nothing; the other two refuse
tools/delivery/delivery/run/__init__.py  in-progress at the start, the end label at the end
tools/delivery/delivery/cli.py         `delivery trigger gh-N --sender LOGIN [--stub]`,
                                       `delivery ensure-labels`
tools/delivery/delivery/prereqs.py     the labels exist
.github/workflows/deliver-on-label.yml the trigger
.github/workflows/deliver.yml          issues: write; the in-progress → failed fallback
```

```python
# labels.py
MARKER = "delivery"
READY, RESTART = "delivery:ready", "delivery:restart"
IN_PROGRESS = "delivery:in-progress"
ACCEPTED, NEEDS_HUMAN = "delivery:accepted", "delivery:needs-human"
OUT_OF_TIME, FAILED = "delivery:out-of-time", "delivery:failed"
TRIGGERS = (READY, RESTART)
ENDS = (ACCEPTED, NEEDS_HUMAN, OUT_OF_TIME, FAILED)
LABELS: dict[str, tuple[str, str]]          # name -> (description, colour), all eight


@dataclass(frozen=True)
class LabelChange:
    add: tuple[str, ...]
    remove: tuple[str, ...]                  # only labels the issue has — gh refuses others


@dataclass(frozen=True)
class Trigger:
    start: bool
    restart: bool
    reason: str                              # one line, for the job summary
    labels: LabelChange                      # what to do to the issue, started or refused


def decide_trigger(*, labels: Sequence[str], state: str, permission: str) -> Trigger: ...
def starting(labels: Sequence[str]) -> LabelChange: ...       # triggers and ends off, in-progress on
def ending(labels: Sequence[str], status: int) -> LabelChange: ...  # in-progress off, the end on
def end_label(status: int) -> str: ...      # 0 accepted · 2 needs-human · 4 out-of-time · else failed
```

`decide_trigger`, in order: no trigger label → don't start, change nothing ("no trigger
label — another run took it"); closed → refuse, take the triggers off; permission not
`admin` or `write` → refuse, take the triggers off; otherwise start, `restart` if
`delivery:restart` was there, with `starting(labels)`.

```python
# Backend
def set_labels(self, key: str, add: Sequence[str], remove: Sequence[str]) -> None: ...
def permission(self, login: str) -> str:    # admin | write | read | none
def start_delivery(self, key: str, *, restart: bool, stub: bool) -> None: ...
```

`gh api repos/O/R/collaborators/LOGIN/permission --jq .permission` gives `admin`, `write`,
`read` or `none`: maintain reads as write, triage as read. A login that isn't a collaborator
is a 404, read as `none`.

`delivery trigger gh-N --sender LOGIN [--stub]` reads the issue and the sender's permission,
decides, applies the label change, dispatches `deliver.yml` if it starts, and prints the
reason. Exit 0 whether it started or refused — a refusal is the workflow doing its job; 1 on
a backend error.

In the runner, after `backend.get(key)` and the worktree is open: `starting(issue.labels)`.
Around `run.go(...)`: whatever status it returns, or 1 if it raises, `ending(...)` on the
labels as they are then (`backend.get` again — a person may have changed them mid-run).
A run that fails before the worktree opens — a bad key, pre-flight, a diverged branch —
sets no label: it never started.

## Tasks

### RED

1. `tests/unit/test_labels.py` — `end_label` for 0, 1, 2, 3, 4 and 137; `starting` takes
   off both triggers and every end label the issue has, leaves `delivery` and `bug`, adds
   `in-progress`, and removes nothing the issue doesn't have; `ending` takes off
   `in-progress` and adds one end; `decide_trigger` for each row above, `restart` with and
   without `ready`, maintain-as-write and triage-as-read already folded by the backend.
2. `tests/unit/test_github.py` — `set_labels` is one `gh issue edit` with `--add-label` and
   `--remove-label` per label, and none when both are empty; on a failure it ensures each
   added label and tries once more; `permission` asks the collaborators endpoint and reads
   a 404 as `none`; `start_delivery` is `gh workflow run deliver.yml -f key=… -f restart=…
   -f stub=…`; `get` reads `state`.
3. `tests/unit/test_local.py` — `set_labels` does nothing; `permission` and `start_delivery`
   raise, saying why.
4. `tests/unit/test_cli.py` — `delivery trigger` dispatches and swaps on a ready issue, with
   `restart` from the label and `stub` from the flag; refuses a closed issue and a read-only
   sender, taking the label off and dispatching nothing; with no trigger label does nothing
   at all. `delivery ensure-labels` ensures all eight.
5. `tests/integration/test_deliver.py` (the runner against real git, a fake `gh`) — a gh run sets
   `in-progress` at the start and `accepted` / `needs-human` / `out-of-time` / `failed` at
   the end; a label call that fails is logged and the exit status is unchanged; a run
   refused at pre-flight sets none.
6. `tests/unit/test_prereqs.py` — the labels are reported missing by name, and ok when all
   eight exist.

### GREEN

7. `labels.py`, the `Issue.state` field, the backend methods, the CLI commands, the runner's
   two calls, the prereqs check.
8. `.github/workflows/deliver-on-label.yml`: `on: issues: types: [labeled]`; job `if` the
   label is `delivery:ready` or `delivery:restart`; concurrency `deliver-on-label-<n>`,
   queued; `permissions: contents: read, issues: write, actions: write`; checkout, setup-uv,
   `uv run delivery trigger gh-<n> --sender <sender> ${{ vars.DELIVER_STUB == '1' && '--stub' }}`,
   its output in the job summary.
9. `deliver.yml`: `issues: write`; a final `always()` step — if the issue still has
   `delivery:in-progress`, swap it for `delivery:failed`.

### Record

10. ADR `261123-a-label-starts-a-delivery.md` (decisions 1–11). CLAUDE.md's *Delivery
    workflow* paragraph; the `delivery.run` docstring; the `issue-writer` skill (`ensure-labels`,
    and the closing hand-off says to add `delivery:ready`); `docs/delivery/prerequisites.md`
    (the labels, `DELIVER_STUB`); handoff 05's item 1 marked answered.

### Verify

11. `uv run pytest tools/delivery`, `ruff`, `.claude/delivery/loop-test.sh`.
12. On `ch09`, `DELIVER_STUB=1`: a test issue labelled `delivery:ready` gets `in-progress`
    within a minute and `accepted` at the end, with its stub PR; adding `delivery:ready` and
    `delivery:restart` together starts one run, restarted; a label on a closed issue is taken
    off; `bug` added to an issue shows a skipped `deliver-on-label` run and nothing else.
    `DELIVER_STUB` deleted. Then one real run of a small issue, started by the label.

## Red

`uv run pytest tools/delivery`: 61 failed, 936 passed. `labels.py` holds the names and
signatures only, so every failure is an assertion or a `NotImplementedError` /
`AttributeError`, never an import error that would hide a module's other tests.

- `test_labels.py` — 28 of 30 fail with `NotImplementedError`; the two on names pass.
- `test_github.py` — 12: `set_labels`, `permission`, `start_delivery` missing; `get` asks
  without `state`.
- `test_local.py` — 4: the same methods missing, `Issue.state` missing.
- `test_cli.py` — 8: no `trigger` or `ensure-labels` command (argparse exits 2), and
  `issue create`'s JSON has no `state`.
- `test_prereqs.py` — 4: no labels check, no `deliver-on-label.yml` among the workflows.
- `integration/test_deliver.py` — 5: the runner makes no `gh issue edit`.
  `test_a_run_that_never_starts_sets_no_label` passes, and must keep passing: it is the
  guard that a diverged branch labels nothing.

## Found while building

- **A dispatch that fails leaves `in-progress` with no run behind it.** `delivery trigger`
  swaps the labels before it dispatches (decision 8), so a refused `gh workflow run` would
  leave the issue saying a run is going. It now labels the issue `failed` and exits 1; a test
  in `test_cli.py` holds it.
- **The trigger runs only the delivery package**: `uv run --frozen --package
  collabhub-delivery`, so a trigger job doesn't install the services' dependencies.
- **The fallback in `deliver.yml` runs only after a valid key** (`steps.inputs.outcome ==
  'success'`), and warns rather than fails when it can't read or set a label.
- **A test helper sliced one argument too far** (`[7:]` for `[6:]`) and was fixed at green;
  the assertions it feeds were unchanged.

## Verified

- `uv run pytest tools/delivery`: 997 passed. `ruff check` and `ruff format --check` clean.
  `.claude/delivery/loop-test.sh`: every scenario passed.
- Not yet on GitHub: `issues` workflows run only from the default branch, so task 12 waits
  for this branch to reach `main`.

## Not this slice

`needs_human` questions and answers on the issue (handoff 05, item 2). Stage-by-stage labels.
Labels on a local or Forgejo issue. Cancelling a run by taking its label off.
