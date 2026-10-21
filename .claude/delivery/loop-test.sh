#!/usr/bin/env bash
# Proves scripts/deliver.sh's state machine with a fake `claude`: no model, no
# cost, a few seconds a scenario. Run it after any change to the script's
# rounds, send-backs, turn caps or context block.
#
#   .claude/delivery/loop-test.sh             every scenario
#   .claude/delivery/loop-test.sh sendback    the scenarios whose name matches
#
# Each scenario gives the fake a script — one verdict per stage run, in order —
# and then checks the exit status, the stages that ran, and what each was told in
# its context block. The verdicts: done, approved, changes_requested, send_back,
# needs_human, and two that aren't an agent's: max_turns (the turn cap) and
# crash (no result at all).
#
# It builds issue-999 — docs/issues/999.md, written for the run and removed after
# it — in ../caw-issue-999-loop on feature/issue-999-loop, from HEAD, and removes
# both after every scenario. The runner commits to that branch as it would to any
# delivery's, so the scenarios check those commits; DELIVER_PUSH=0, so nothing is
# fetched or pushed, and DELIVER_PR=0, so no PR is opened.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(mktemp -d)"
WORKTREE="$(dirname "$ROOT")/caw-issue-999-loop"
BRANCH=feature/issue-999-loop
ISSUE="$ROOT/docs/issues/999.md"
trap 'cleanup; rm -rf "$WORK" "$ISSUE"' EXIT

mkdir -p "$WORK/bin"
# The local backend reads issues from the checkout that runs the workflow.
printf 'Issue: 999\n\n# Issue 999 — the loop test\n\n## Summary\n\nA loop.\n' >"$ISSUE"

# The fake: .claude/delivery/stub-claude, which takes the next verdict from
# $FAKE_SCRIPT, records the prompt it was given under $FAKE_LOG, and writes the file
# the workflow expects that verdict to leave.
cp "$ROOT/.claude/delivery/stub-claude" "$WORK/bin/claude"

# The preview deploy deliver.sh runs before each acceptance pass. It fails its
# first $FAKE_DEPLOY_FAILS calls, then prints the origins as deploy.sh does.
cat >"$WORK/bin/deploy" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_LOG.deploys"
if [ "$(wc -l <"$FAKE_LOG.deploys")" -le "${FAKE_DEPLOY_FAILS:-0}" ]; then
    echo "fake deploy failed" >&2
    exit 1
fi
printf 'APP_ORIGIN=https://fake-preview.trycloudflare.com\nOBJECT_STORE_ORIGIN=https://fake-s3.trycloudflare.com\n'
FAKE
chmod +x "$WORK/bin/deploy"
export DELIVER_DEPLOY_SH="$WORK/bin/deploy"

cleanup() {
    git -C "$ROOT" worktree remove --force "$WORKTREE" >/dev/null 2>&1
    git -C "$ROOT" branch -D "$BRANCH" >/dev/null 2>&1
    return 0
}

failures=0
fail() {
    printf '    FAIL: %s\n' "$*"
    failures=$((failures + 1))
}

# scenario <name> <expected exit> <verdicts…>, then the checks below.
scenario() {
    NAME="$1" expected="$2"
    shift 2
    RAN=false
    case "$NAME" in *"$FILTER"*) ;; *) return 0 ;; esac
    RAN=true
    cleanup
    # deliver.sh pauses at a stage whose agent isn't in the worktree, and the
    # worktree is built from HEAD — so an agent not yet committed would pause every
    # scenario. Seed it from the working copy; deliver.sh reuses a worktree it finds.
    git -C "$ROOT" worktree add -q -b "$BRANCH" "$WORKTREE" HEAD >/dev/null 2>&1
    cp -R "$ROOT/.claude/agents" "$ROOT/.claude/delivery" "$WORKTREE/.claude/"
    export FAKE_SCRIPT="$WORK/$NAME.script" FAKE_LOG="$WORK/$NAME.log"
    rm -rf "$FAKE_LOG" "$FAKE_LOG.calls" "$FAKE_LOG.flags" "$FAKE_LOG.deploys" && mkdir -p "$FAKE_LOG"
    printf '%s\n' "$@" >"$FAKE_SCRIPT"
    printf '%s\n' "$NAME"
    BASE_SHA="$(git -C "$ROOT" rev-parse HEAD)"
    PATH="$WORK/bin:$PATH" DELIVER_RUN=loop DELIVER_BASE=HEAD DELIVER_RETRY_WAIT=0 DELIVER_PUSH=0 DELIVER_PR=0 \
        "$ROOT/scripts/deliver.sh" --backend local issue-999 >"$FAKE_LOG.out" 2>&1
    status=$?
    [ "$status" = "$expected" ] || fail "exit $status, expected $expected — $(tail -n 3 "$FAKE_LOG.out" | tr '\n' ' ')"
    [ ! -s "$FAKE_SCRIPT" ] || fail "verdicts left unused: $(tr '\n' ' ' <"$FAKE_SCRIPT")"
}

# The context block the nth call was given.
block() { cat "$FAKE_LOG"/"$(printf '%02d' "$1")"-*.txt 2>/dev/null; }
# told <call> <text>, not_told <call> <text> — what a stage's context block held.
told() { ! $RAN || block "$1" | grep -qF -- "$2" || fail "call $1 was not told '$2': $(block "$1" | tr '\n' '|')"; }
not_told() { ! $RAN || ! block "$1" | grep -qF -- "$2" || fail "call $1 was told '$2'"; }
# ran <stages…> — the stages that ran, in order.
ran() { ! $RAN || [ "$(cut -d' ' -f1 "$FAKE_LOG.calls" | tr '\n' ' ')" = "$* " ] || fail "ran: $(cut -d' ' -f1 "$FAKE_LOG.calls" | tr '\n' ' ')"; }
# flags <call> <model> <effort> — the --model and --effort the nth call was run with;
# '' for one it was run without, which leaves the agent's own.
flags() { ! $RAN || [ "$(sed -n "$1p" "$FAKE_LOG.flags")" = "model=$2 effort=$3" ] || fail "call $1 ran with '$(sed -n "$1p" "$FAKE_LOG.flags")', expected 'model=$2 effort=$3'"; }
exists() { ! $RAN || [ -s "$WORKTREE/docs/plans/issue-999/$1" ] || fail "no $1"; }
# logged <text> — the workflow's own output said it; deploys <n> — preview deploys run.
logged() { ! $RAN || grep -qF -- "$1" "$FAKE_LOG.out" || fail "output has no '$1'"; }
deploys() { ! $RAN || [ "$(cat "$FAKE_LOG.deploys" 2>/dev/null | wc -l | tr -d ' ')" = "$1" ] || fail "deployed $(cat "$FAKE_LOG.deploys" 2>/dev/null | wc -l | tr -d ' ') times, expected $1"; }
history_has() { ! $RAN || grep -qE -- "$1" "$WORKTREE/docs/plans/issue-999/run/history.log" || fail "history.log has no '$1'"; }
# committed <subject> — the runner committed it on the branch; commits <n> — its commit count.
subjects() { git -C "$WORKTREE" log --format=%s "$BASE_SHA..HEAD" 2>/dev/null; }
# grep -q exits at its first match, and pipefail would then report git's SIGPIPE as a miss.
committed() { ! $RAN || subjects | grep -xF -- "$1" >/dev/null || fail "no commit '$1': $(subjects | tr '\n' '|')"; }
commits() { ! $RAN || [ "$(subjects | wc -l | tr -d ' ')" = "$1" ] || fail "$(subjects | wc -l | tr -d ' ') commits, expected $1"; }

FILTER="${1:-}"
REVIEWS=docs/plans/issue-999/reviews

scenario straight-through 0 done approved done approved done approved approved
ran plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer acceptance-reviewer
told 7 'Stage: acceptance-reviewer, round 1 of 3'
told 7 'Turns: 200'
told 7 'Red report: docs/plans/issue-999/02-red-tests.md'
told 7 'Green report: docs/plans/issue-999/03-green-report.md'
told 7 'Proof: docs/plans/issue-999/04-proof.md'
told 7 'Evidence: build/acceptance/'
told 7 "Send-back file, if you send work back: $REVIEWS/acceptance-reviewer-sendback-2.md"
not_told 7 'Write your review to'
told 7 'Preview: up at https://fake-preview.trycloudflare.com — log: build/acceptance/preview-up.log'
deploys 1
flags 7 sonnet ''
history_has '^07 acceptance-reviewer approved \[1m 3 turns \$0.5 · sonnet · default\]'
exists 04-proof.md
told 1 'Stage: plan-writer, round 1 of 3'
told 1 'Turns: 150'
told 3 'Turns: 200'
told 5 'Turns: 250'
not_told 5 'Rework pass'
# The models a run uses when nothing is set: Sonnet for the test pair and the
# code-writer, the agent's own (Opus) for the plan pair and the code-reviewer.
flags 1 '' ''
flags 2 '' ''
flags 3 sonnet ''
flags 4 sonnet ''
flags 5 sonnet ''
flags 6 '' ''
history_has '^01 plan-writer done \[1m 3 turns \$0.5 · opus · default\]: fake'
history_has '^04 test-reviewer approved \[1m 3 turns \$0.5 · sonnet · default\]'
history_has '^06 code-reviewer approved \[1m 3 turns \$0.5 · opus · default\]'
# A checkpoint a stage, and the approval for the last.
commits 7
committed 'delivery(issue-999): plan-writer done, round 1'
committed 'delivery(issue-999): code-reviewer approved, round 1'
committed 'delivery(issue-999): accepted'

scenario three-rounds-then-a-human 2 done changes_requested done changes_requested done changes_requested
told 3 "Review to address: $REVIEWS/plan-reviewer-1.md"
told 3 'Rework pass: yes — 100 turns'
told 5 'Final round: yes — 60 turns'
told 6 'Final round: yes'
exists reviews/plan-reviewer-3.md
exists needs-human.md

scenario approved-in-round-two 0 done changes_requested done approved done approved done approved approved
told 4 'Stage: plan-reviewer, round 2 of 3'
told 4 'Rework pass'
told 5 'Stage: test-writer, round 1 of 3'
told 5 'Turns: 200'

# A reviewer sends back: its pair's round advances, its review survives, and its
# own writer gets that review when the flow comes forward.
scenario reviewer-sendback 0 done approved done send_back done approved done approved done approved approved
ran plan-writer plan-reviewer test-writer test-reviewer plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer acceptance-reviewer
told 4 "Send-back file, if you send work back: $REVIEWS/test-reviewer-sendback-2.md"
told 5 'Stage: plan-writer, round 2 of 3'
told 5 "Review to address: $REVIEWS/test-reviewer-sendback-2.md"
not_told 5 'After a send-back'
told 6 "After a send-back by test-reviewer: $REVIEWS/test-reviewer-sendback-2.md"
told 6 'Changed since the send-back by test-reviewer: docs/plans/issue-999/01-implementation-plan.md'
told 7 "Review to address: $REVIEWS/test-reviewer-1.md"
told 7 'After a send-back by test-reviewer'
told 7 'Stage: test-writer, round 2 of 3'
told 7 'Rework pass'
told 8 "Write your review to: $REVIEWS/test-reviewer-2.md"
told 8 'After a send-back by test-reviewer'
not_told 8 'Final round'
not_told 9 'After a send-back'
told 9 'Turns: 250'
exists reviews/test-reviewer-1.md
exists reviews/test-reviewer-2.md

# A writer sends back: no review of its own, its round stays, and it comes back
# to a first pass's turns.
scenario writer-sendback 0 done approved done approved send_back done approved done approved approved
ran plan-writer plan-reviewer test-writer test-reviewer code-writer test-writer test-reviewer code-writer code-reviewer acceptance-reviewer
told 6 "Review to address: $REVIEWS/code-writer-sendback-2.md"
told 6 'Stage: test-writer, round 2 of 3'
told 7 'After a send-back by code-writer'
told 8 'After a send-back by code-writer'
told 8 'Stage: code-writer, round 1 of 3'
told 8 'Turns: 250'
not_told 8 'Review to address'
not_told 9 'After a send-back'

scenario code-reviewer-sendback 0 done approved done approved done send_back done approved done approved approved
told 9 "Review to address: $REVIEWS/code-reviewer-1.md"
told 9 'After a send-back by code-reviewer'
told 9 'Stage: code-writer, round 2 of 3'
told 10 "Write your review to: $REVIEWS/code-reviewer-2.md"

# A send-back never lands in a final round: the plan pair has used its three,
# and still gets an ordinary review and a final one.
scenario sendback-after-three-rounds 0 done changes_requested done changes_requested done approved \
    done send_back done changes_requested done approved done approved done approved approved
told 9 'Stage: plan-writer, round 4 of 5'
not_told 9 'Final round'
told 11 'Stage: plan-writer, round 5 of 5'
told 11 'Final round: yes'

# Two send-backs open at once: the code-reviewer's, then the test-reviewer's.
scenario nested-sendbacks 0 done approved done approved done send_back \
    done send_back done approved done approved done approved approved
ran plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer \
    test-writer test-reviewer plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer \
    acceptance-reviewer
told 10 'After a send-back by test-reviewer'
told 10 'After a send-back by code-reviewer'
told 13 'After a send-back by code-reviewer'
not_told 13 'After a send-back by test-reviewer'
told 13 "Review to address: $REVIEWS/code-reviewer-1.md"

scenario too-many-sendbacks 2 done approved done send_back done approved done send_back \
    done approved done send_back done approved done send_back
exists needs-human.md

# Out of turns: resumed once in the same session; twice is a human's.
scenario out-of-turns-resumed 0 max_turns done approved done approved done approved approved
ran plan-writer plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer acceptance-reviewer
told 2 'You ran out of turns'
told 2 '75 more turns'
history_has '^01 plan-writer done \[2m 6 turns \$1 · opus · default\]'

scenario out-of-turns-twice 2 max_turns max_turns
exists needs-human.md

scenario crash-then-rerun 0 crash done approved done approved done approved approved
ran plan-writer plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer acceptance-reviewer
told 2 'Stage: plan-writer, round 1 of 3'

scenario crash-twice 1 crash crash
committed 'delivery(issue-999): failed at plan-writer, round 1'

scenario asks-a-human 2 done needs_human
exists needs-human.md
commits 2
committed 'delivery(issue-999): needs a human at plan-reviewer, round 1'

# The acceptance-reviewer approves only with its proof written. Without it, it is
# asked for the proof once, in its own session; still without it, the run stops.
scenario acceptance-approves-without-proof 1 done approved done approved done approved approved_bare approved_bare
ran plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer acceptance-reviewer \
    acceptance-reviewer
logged 'asking it for them'
logged 'approved but wrote no'

scenario acceptance-writes-its-proof-when-asked 0 done approved done approved done approved approved_bare approved
ran plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer acceptance-reviewer \
    acceptance-reviewer
committed 'delivery(issue-999): accepted'

# It has no writer to ask for changes: that is a stop, never a loop.
scenario acceptance-may-not-ask-for-changes 1 done approved done approved done approved changes_requested
logged 'has no writer to take changes'

# A proof from an earlier pass is not this pass's proof.
scenario acceptance-stale-proof 1 done approved done approved done approved send_back done approved approved_bare approved_bare
logged 'approved but did not rewrite'

# It sends back to the code-writer, and the flow comes forward through the
# code-reviewer to it again — a rework pass in a new round of its own.
scenario acceptance-sendback 0 done approved done approved done approved send_back done approved approved
ran plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer acceptance-reviewer \
    code-writer code-reviewer acceptance-reviewer
told 8 "Review to address: $REVIEWS/acceptance-reviewer-sendback-2.md"
told 8 'Stage: code-writer, round 2 of 3'
told 8 'Rework pass'
told 9 'After a send-back by acceptance-reviewer'
told 9 "Write your review to: $REVIEWS/code-reviewer-2.md"
told 10 'Stage: acceptance-reviewer, round 2 of 3'
told 10 'Rework pass'
told 10 'After a send-back by acceptance-reviewer'
not_told 10 'Write your review to'
deploys 2
exists reviews/acceptance-reviewer-sendback-2.md
exists 04-proof.md

# The code pair takes three of its send-backs; a human sees the fourth.
scenario acceptance-sendbacks-bounded 2 done approved done approved done approved send_back \
    done approved send_back done approved send_back done approved send_back
exists needs-human.md

scenario acceptance-needs-human 2 done approved done approved done approved needs_human
exists needs-human.md

# It writes its proof and its send-back file on the branch, and nothing else.
scenario acceptance-stray-write 1 done approved done approved done approved stray
logged 'wrote outside'

# The workflow deploys the preview, not the agent — a build can outlast any tool
# call. A failure is retried once, then handed to the agent to judge.
export FAKE_DEPLOY_FAILS=1
scenario acceptance-preview-retried 0 done approved done approved done approved approved
told 7 'Preview: up at https://fake-preview.trycloudflare.com'
deploys 2
export FAKE_DEPLOY_FAILS=2
scenario acceptance-preview-fails 2 done approved done approved done approved needs_human
told 7 'Preview: failed twice — log: build/acceptance/preview-up.log'
deploys 2
unset FAKE_DEPLOY_FAILS

# A stage's model and effort come from its own setting; a rework pass takes the
# rework effort whatever the stage's own, and history.log says what each ran with.
export DELIVER_MODEL_TEST_WRITER=opus DELIVER_EFFORT_TEST_WRITER=medium DELIVER_REWORK_EFFORT=high
scenario model-and-effort-by-stage 0 done approved done changes_requested done approved done approved approved
flags 1 '' ''
flags 3 opus medium
flags 4 sonnet ''
flags 5 opus high
flags 6 sonnet high
flags 7 sonnet ''
flags 8 '' ''
history_has '^01 plan-writer done \[1m 3 turns \$0.5 · opus · default\]'
history_has '^03 test-writer done \[1m 3 turns \$0.5 · opus · medium\]'
history_has '^05 test-writer done \[1m 3 turns \$0.5 · opus · high\]'
history_has '^06 test-reviewer approved \[1m 3 turns \$0.5 · sonnet · high\]'
unset DELIVER_MODEL_TEST_WRITER DELIVER_EFFORT_TEST_WRITER DELIVER_REWORK_EFFORT

# The final round is cut down to bound a disagreement, so its effort wins over
# the rework effort.
export DELIVER_REWORK_EFFORT=high
scenario final-round-effort-over-rework 2 done changes_requested done changes_requested done changes_requested
flags 3 '' high
flags 4 '' high
flags 5 '' medium
flags 6 '' medium

# DELIVER_MODEL still overrides every stage, the defaults included.
export DELIVER_MODEL=haiku
scenario one-model-for-every-stage 0 done approved done approved done approved approved
flags 1 haiku ''
flags 3 haiku ''
flags 6 haiku ''
flags 7 haiku ''
unset DELIVER_MODEL
unset DELIVER_REWORK_EFFORT

# A stage's own model wins over DELIVER_MODEL, and the rework model over both.
export DELIVER_MODEL=haiku DELIVER_MODEL_CODE_WRITER=sonnet DELIVER_REWORK_MODEL=opus DELIVER_EFFORT=low
scenario rework-model 0 done approved done approved done changes_requested done approved approved
flags 1 haiku low
flags 5 sonnet low
flags 6 haiku low
flags 7 opus low
flags 8 opus low
history_has '^07 code-writer done \[1m 3 turns \$0.5 · opus · low\]'
unset DELIVER_MODEL DELIVER_MODEL_CODE_WRITER DELIVER_REWORK_MODEL DELIVER_EFFORT

# A resume is the same pass: same model, same effort.
export DELIVER_MODEL_PLAN_WRITER=sonnet DELIVER_EFFORT_PLAN_WRITER=high
scenario out-of-turns-keeps-its-flags 0 max_turns done approved done approved done approved approved
flags 1 sonnet high
flags 2 sonnet high
unset DELIVER_MODEL_PLAN_WRITER DELIVER_EFFORT_PLAN_WRITER

echo
if [ "$failures" -gt 0 ]; then
    echo "$failures check(s) failed. Each scenario's output: $WORK/<name>.log.out"
    trap 'cleanup; rm -f "$ISSUE"' EXIT
    exit 1
fi
echo "Every scenario passed."
