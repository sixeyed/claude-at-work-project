# A label on the issue starts a delivery, and labels report how it went

- **Status:** Accepted
- **Date:** 2026-11-23

## Context

By ADR `261019-delivery-opens-its-pr`, a GitHub delivery runs on a hosted runner and ends in
a pull request with a preview held open for the review. Starting one still meant opening the
Actions tab and dispatching `deliver.yml` with the issue's key typed in. The people who decide
an issue is ready work on the issue, not in Actions, and after a run they had no way to see
from the issue whether it was running, waiting on them, or done.

The `issue-writer` skill already labels every issue it posts `delivery`, meaning "written for
delivery". That label can't also be the trigger: the skill adds it when it creates the issue,
and GitHub fires `issues: labeled` for labels set at creation too, so every new issue would
start a paid run before anyone had read it. Starting a run spends real money — the gh-3 runs
cost about $26 each — so who may start one matters, and anyone with triage access on the repo
can add a label.

GitHub has no trigger-level filter on a label's name. Every label added to any issue starts a
run of any workflow listening for `issues: labeled`, and a job-level `if` can only skip it,
which leaves a skipped run in that workflow's list. Events caused by `GITHUB_TOKEN` start no
workflow at all, except `workflow_dispatch`.

## Decision

We will start a delivery when a person adds `delivery:ready` to its issue, or
`delivery:restart` to start it again from plan-writer, and report the run back through
labels on the same issue. `delivery` stays the marker and starts nothing.

The trigger is its own workflow, `deliver-on-label.yml`. It runs `delivery trigger`, which
reads the issue's labels as they are now, not as the event had them. If a trigger is there,
the issue is open and the sender has write or admin access, it swaps the trigger labels for
`delivery:in-progress` and dispatches `deliver.yml` — the labels first, so that the second of
two events, queued behind the first in a per-issue concurrency group, finds no trigger and
stops. A refused trigger is taken off the issue, and the job summary says why. A label run
takes every default; the model and the stub stay on the dispatch form, except that a repo
variable, `DELIVER_STUB=1`, makes every label run a stub run while the trigger is being
proven.

The runner, not the workflow, sets the status labels, through the backend: `in-progress`
when it starts, and at the end exactly one of `delivery:accepted`, `delivery:needs-human`,
`delivery:out-of-time` or `delivery:failed`, from its exit status. A run started from a
laptop or by hand dispatch reports on the issue the same way, and the local backend, with no
labels, does nothing. A label that can't be set is logged and never fails a run.
`deliver.yml` keeps one fallback: an `always()` step that swaps an `in-progress` still on the
issue for `failed`, for a run that was cancelled or killed before it could say.

Each new run takes the last run's end label off, so adding `delivery:ready` again is how a
person resumes after answering `needs-human.md` or running out of time.

## Consequences

A delivery is started and followed from the issue. The issue list filtered by
`delivery:needs-human` is the queue of runs waiting on a person, and `delivery:accepted` the
ones with a PR to review.

Every label change on every issue shows up in `deliver-on-label`'s run list as a skipped run,
and a laptop run's own label changes — made with the person's `gh` login, not
`GITHUB_TOKEN` — add a few more that find no trigger and stop. Keeping the trigger out of
`deliver.yml` keeps that noise out of the list that matters.

The questions behind `delivery:needs-human` still live in `needs-human.md` on the branch, not
on the issue; the label says a person is needed, and Slack and the job summary say what for.
Taking `delivery:in-progress` off does not cancel a run. Both are left for later.

Eight labels must exist on the repo before the first run. `delivery ensure-labels` makes
them, the `issue-writer` skill runs it, the runner makes one it finds missing as it sets it,
and `delivery prereqs` reports any that aren't there.

## Alternatives Considered

### `delivery` as the trigger

What was first asked for. The skill would have had to stop labelling issues, or every issue it
posted would start a run on creation. A separate trigger keeps "written for delivery" and
"start it now" as two acts, the second a person's.

### The trigger in `deliver.yml`

One workflow, no dispatch hop. Every label added anywhere would leave a skipped run among the
real deliveries, in the list a person reads to find a run's log and summary.

### Labels set by workflow steps

`deliver.yml` could read the runner's exit code and set the end label itself. A delivery run
from a laptop, which the runner supports as fully as Actions, would then leave the issue
saying nothing, or still `in-progress` from an earlier run.

### A comment on the issue

A sticky comment linking the run and edited with its outcome, as the preview's comment is on
the PR. The labels say the same in less space, and can be filtered on.

### Option labels for the model or a stub

`delivery:stub`, `delivery:haiku` and the like would multiply the label states for runs a
person starts rarely, and from the dispatch form already.
