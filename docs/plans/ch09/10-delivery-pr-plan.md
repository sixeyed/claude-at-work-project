# Delivery opens its PR — slice 4: the PR, its preview, and Slack

Slice 3 (`08-delivery-actions-plan.md`) left a delivery at a pushed `feature/<key>` ending in
`delivery(<key>): accepted`, with the proof on it and a person to open the PR. This slice ends
an accepted GitHub delivery at a pull request: the proof as its body, its screenshots inline,
a preview a reviewer can try held open on a hosted runner, and the run reported to Slack.

Settled in a grilling session on 2026-10-19: handoff 09's *Decided* table, 1–23, is the
spec. This plan says how, and records the two places it reads a decision more narrowly.

## Readings of the decisions

- **The proof keeps its `../../../build/acceptance/…` links** (decision 7). The runner reads
  the screenshots a proof cites from those links, copies each to `docs/plans/<key>/proof/`
  at the same path under it, and rewrites the link in the PR body only. The proof still
  renders in a worktree, and the acceptance-reviewer's instructions don't change for it.
- **The PR's title is `<issue title> (<key>)`**, not the proof's heading — `# gh-3 —
  acceptance proof: accepted` says nothing in a PR list. The body drops that heading.

## Shapes

```
tools/delivery/delivery/model.py         PullRequest; Backend gains the PR methods
tools/delivery/delivery/github.py        gh pr list|create|view|edit|ready|comment, gh workflow run
tools/delivery/delivery/local.py         opens no PR: opens_pull_requests = False
tools/delivery/delivery/run/publish.py   pure: cited screenshots, the PR title and body
tools/delivery/delivery/run/notify.py    Slack: the notifier, the message shapes
tools/delivery/delivery/cli.py           `delivery notify` — preview.yml posts through it
.github/workflows/preview.yml            the PR's preview, held for the review
scripts/lib/preview.sh                   preview_password_args — PREVIEW_PASSWORD to Dex's hash
tests/bdd/pages/sign_in_page.py          the password from SMOKE_PASSWORD, default collabhub
```

```python
@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str
    draft: bool

class Backend(Protocol):
    opens_pull_requests: bool
    def find_pull_request(self, head: str) -> PullRequest | None: ...   # open PRs only
    def open_pull_request(self, head: str, base: str, title: str, body: str) -> PullRequest: ...
    def update_pull_request(self, number: int, *, title: str | None = None,
                            body: str | None = None, draft: bool | None = None) -> PullRequest: ...
    def comment_on_pull_request(self, number: int, body: str) -> None: ...
    def start_preview(self, number: int) -> None: ...      # gh workflow run preview.yml -f pr=N
    def blob_url(self, sha: str, path: str) -> str: ...     # …/blob/<sha>/<path>?raw=true
```

```
DELIVER_PR        0 opens no PR. Default: 1 — a PR when the backend opens them and the branch is pushed
SLACK_BOT_TOKEN   with SLACK_CHANNEL: the run posts to Slack, and previews get a random password
SLACK_CHANNEL     the channel ID, C…
PREVIEW_PASSWORD  deploy.sh preview up: Dex's password for this preview. Default: the k3d values' collabhub
SMOKE_PASSWORD    the smoke packs' password. Default: collabhub
```

State gains `slack_thread: str = ""`. Nothing about the PR is stored: the screenshot commits
are found by subject after the last `accepted`, the PR by head branch, so each publish step
is idempotent and a rerun of a done delivery does only what is owed.

Commits after `accepted`, only when a PR will be opened and the proof cites a screenshot:

```
delivery(gh-3): proof screenshots            adds docs/plans/gh-3/proof/…
delivery(gh-3): proof screenshots removed    removes them — the PR's net diff has none
```

The PR body, from `04-proof.md`: its `# …` heading dropped; each cited screenshot's link →
`blob_url(<add commit>, docs/plans/<key>/proof/<path>)`; any other link into
`build/acceptance/` → the path as code, since nothing serves it; `## The run` to the next
`## ` wrapped in `<details><summary>The run</summary>`; then a rule, `Closes #<n>` and the
squash note. Longer than GitHub's 65536 characters fails the PR step.

`build/delivery/publish.json` — `{"url": …}` or `{"error": …}` — is what `deliver.yml`'s
summary reports; never committed.

Slack, one thread per delivery: the parent `gh-3 · <issue title> — <status>` with the run's
link when on Actions, edited as the status changes; replies `▶ <stage> · round R · <model>`
and `<✔|↩|✋|✗> <stage> <status> · <minutes> · $<cost> — <summary, ≤300 chars>` with the
checkpoint's link to the stage's own file; the preview's origin and password; *out of time*;
the PR, broadcast. Every post goes through one wrapper that logs a failure and returns.

`preview.yml`: `workflow_dispatch` (`pr`) and `push` to `feature/gh-*` — `pull_request` until
the stub run, see *Found while building*; `concurrency: preview-<n>`, cancel in progress;
`permissions: contents: read, pull-requests: write`. A guard job reads the PR and goes on only
for an open, ready, same-repo `feature/gh-*` head — a `closed` event only marks the comment
down. Then: free disk, checkout the head, uv, k3d, cloudflared, htpasswd; a random
`PREVIEW_PASSWORD` when the Slack secrets are set; `BRANCH=<head> scripts/deploy.sh preview up`;
the sticky comment (`<!-- collabhub-preview -->`) with the origin; the password to the
delivery's thread with `delivery notify`; poll `gh pr view --json state,reviewDecision` every
60 s until approved, closed or 5¾ h; the comment edited to why it went down.

## Tasks

### RED

1. **`test_github.py`** — `find_pull_request` asks `gh pr list --head <branch> --state open`
   and returns the first, or `None`; `open_pull_request` sends title and body by `--body-file -`
   and reads the PR back; `update_pull_request` edits title and body, and `gh pr ready` /
   `--undo` for draft; `comment_on_pull_request`; `start_preview` runs `gh workflow run
   preview.yml -f pr=<n>`; `blob_url`; a body over the limit refused before `gh` is called.
2. **`test_local.py`** — `opens_pull_requests` is false, and every PR method raises a
   `BackendError` that names `tea pr create`.
3. **`test_run_publish.py`** — the screenshots a proof cites (image links into
   `build/acceptance/` only, each once, in order); the body: heading dropped, cited links
   rewritten, other `build/acceptance/` links made plain, `## The run` in `<details>` and
   nothing after it swallowed, `Closes #N` and the squash note; the title.
4. **`test_run_notify.py`** — no token or no channel is the null notifier; the Slack
   notifier's `chat.postMessage` (channel, text, `thread_ts`, `reply_broadcast`) and
   `chat.update` requests against a fake transport, the bearer token in the header, the `ts`
   it returns; a transport error or `ok: false` is logged, never raised; the stage messages'
   text, the summary cut at 300.
5. **`test_run_settings.py` / `test_run_state.py`** — `DELIVER_PR` 0, 1, bad value exits 2;
   `slack_thread` saved and loaded, an older `state.json` without it loads.
6. **`test_preview_script.py`** (testkit) — `preview_password_args` prints nothing without
   `PREVIEW_PASSWORD`; with it, `--set-string dex.passwordHash=<hash>` from `htpasswd`; with
   `htpasswd` missing, it fails saying so.
7. **testkit unit, `test_sign_in_password.py`** — `SignInPage`'s default password is
   `SMOKE_PASSWORD` when set, `collabhub` when not.
8. **Integration, `test_deliver.py`**, an accepting fake agent and a fake deploy script,
   against the bare repo:
   - an approved acceptance pass opens a PR from `feature/gh-3` into `main` with the issue's
     title, after `accepted`, `proof screenshots` and `proof screenshots removed` reach the
     remote; the net diff from `main` has no image; the add commit holds each screenshot at
     the SHA the body links; then `gh workflow run` for that PR.
   - a rerun of the done delivery with the PR open edits it, opens none, makes no new
     screenshot commits, and dispatches again.
   - a rerun after the PR failed opens it; one that crashed between the two screenshot
     commits makes only the removal.
   - `gh pr create` failing still exits 0, and `publish.json` holds the error.
   - `DELIVER_PR=0`, `DELIVER_PUSH=0`, and a proof with no screenshots: no screenshot commits;
     the first two call no `gh pr`.
   - `--restart` with a PR open makes it a draft and comments; the approval makes it ready.
   - with Slack set, against a fake transport: a parent message, a start and an end reply per
     stage, the thread `ts` in the committed state, and the deploy script's `PREVIEW_PASSWORD`
     the one posted; without Slack, the deploy script gets no `PREVIEW_PASSWORD`.
9. **`loop-test.sh`** sets `DELIVER_PR=0`, and still passes.

Stop at red for review.

### GREEN

10. Backend methods; `publish.py`; `notify.py`; settings and state; the runner's publish step
    after `accepted`, on a done rerun and on `--restart`; Slack posts at each stage, stop,
    failure, out of time and PR; the password into the deploy's and the agent's environment.
11. `preview_password_args` in `scripts/lib/preview.sh`, used by `cmd_preview_up`'s infra
    install; `SignInPage` and `tests/smoke/fixtures.py` on `SMOKE_PASSWORD`.
12. `delivery notify --state <state.json> [--broadcast] <text>`.
13. `.claude/delivery/stub-claude`: the approving acceptance pass writes a screenshot under
    `build/acceptance/` and cites it, so a stub dispatch proves the screenshot commits.
14. The acceptance-reviewer's *Try it*: the PR's preview comment and the preview password.
15. `deliver.yml`: `pull-requests: write`, `actions: write`, the Slack secrets, `publish.json`
    in the summary, the Node 24 majors. `preview.yml` as in *Shapes*. actionlint clean.

### Record

16. CLAUDE.md's *Delivery workflow*: an accepted GitHub delivery ends in a PR, its preview held
    open by `preview.yml`, the run in Slack. The `delivery.run` docstring: the publish step,
    `DELIVER_PR`, the Slack variables. `.env.example`: the new variables, commented.
17. Two ADRs with `adr-writer` (decision 23).

### Verify

18. `scripts/test.sh lint unit`, the integration tests for `tools/delivery`,
    `.claude/delivery/loop-test.sh` — green.
19. On `caw-project/ch09`, once a person has set the Slack secrets, *Allow GitHub Actions to
    create and approve pull requests* and squash-only: a stub dispatch opens a PR with an inline
    screenshot; its preview comes up, comments its origin and posts its password to Slack; a
    second dispatch updates the PR; closing it takes the preview down. Then one real run.

## Red

What each failed with, on 2026-10-19:

- `test_github.py` — whole file, `ImportError: PullRequest` from `delivery.model`, which hides
  its existing tests until GREEN adds it; `test_run_notify.py`, `test_run_publish.py` —
  `ModuleNotFoundError`.
- `test_local.py`, seven — no `opens_pull_requests`, no PR methods.
- `test_run_settings.py`, three — no `pr`; `DELIVER_PR=yes` accepted.
  `test_run_state.py`, two — no `slack_thread`.
- `test_preview_script.py`, three — `preview_password_args: command not found`.
- `test_sign_in_password.py` — `SMOKE_PASSWORD` ignored; the two default cases pass, as
  guards that the change keeps `collabhub`.
- `test_publish.py`, eleven — no screenshot commits, no `gh pr` or `gh workflow run` call, no
  `publish.json`, `deliver()` takes no `slack_transport`. Three pass from the start, as
  regression guards: `DELIVER_PR=0` and `DELIVER_PUSH=0` open nothing, and without Slack the
  deploy gets no `PREVIEW_PASSWORD`.

## Found while building

- **The fake `gh` answers in sequence.** A restart finds its PR ready, and by the approval it
  is a draft; one fixed answer per subcommand can't say that. `FakeGh` takes a list as well,
  answered in turn, the last one for every call after.
- **The publish step stores nothing.** The screenshot commits are found by subject after the
  last `accepted`, the PR by its branch, so a crash between any two steps reruns cleanly. The
  integration test drops the removal commit and forces the branch back, and the rerun makes
  only the removal.
- **The Slack token stays with the runner.** `agent_env` hands an agent the whole
  environment, so it now drops `SLACK_BOT_TOKEN` and `SLACK_CHANNEL` (test first). `preview.yml`
  checks out `main` for its tooling and the PR's head in `pr/`: the token only meets `main`'s
  `delivery notify`, and the deploy runs with it unset.
- **`delivery notify` imports the notifier lazily**, as `deliver` imports the runner, so the
  issue-writer skill's commands don't load the runner's package.
- **The password reaches `htpasswd` on stdin** (`-niBC 10`), never in argv. Its `$2y$` hash
  is one Dex's Go bcrypt reads, and the deps chart's `checksum/config` covers `.Values.dex`,
  so Dex restarts with a new hash. `deliver.yml` and `preview.yml` install `apache2-utils` if
  the runner has no `htpasswd`.
- **The stub cites a screenshot.** With no `FAKE_SCRIPT`, an approving acceptance pass writes
  a 1×1 PNG to `build/acceptance/stub/` and links it, so a stub dispatch proves the screenshot
  commits and the PR's inline image. The loop test, which sets `FAKE_SCRIPT`, is unchanged.
- **Action pins:** `checkout@v7`, `setup-node@v7` and `upload-artifact@v7`, all Node 24.
  `astral-sh/setup-uv` publishes no major tag, and v10.3.0 was ten days old, so it is
  `@v10.2.0`.
- **`caw-project` forbids Actions-created PRs at the organisation level**, so the repo's
  checkbox is greyed out. An org owner allows it first. `ch09` is now squash-only with
  `delete_branch_on_merge` (set by `gh api`, at the user's word), and has `SLACK_BOT_TOKEN` and
  `SLACK_CHANNEL`.

- **A bot-opened PR's `pull_request` run waits for approval.** The stub run's PR #6 showed
  "1 check awaiting approval": GitHub made a `pull_request` run for the PR the Actions bot
  opened and held it for a maintainer. Approving it would have replaced the working preview
  and its password. `preview.yml` triggers on `push` to `feature/gh-*` instead and finds the
  branch's open PR; the runner's own pushes start nothing. Concurrency moved onto the job,
  keyed by the PR the guard found, and the `closed` job went: the holding preview sees a
  close within a minute.
- **A dispatched run isn't among a PR's checks.** The preview was up and the PR showed no sign
  of it until the comment landed. `preview.yml` sets a `preview` commit status on the head:
  deploying, up at the origin, down, or failed (`statuses: write`).
- **The deploy was silent in Slack.** The runner deployed before posting the stage's start, so
  the thread went quiet for the longest wait. It posts `⏳ acceptance-reviewer · deploying the
  preview` first.
- **The stub's 1×1 screenshot was invisible in the PR.** It copies
  `.claude/delivery/stub-screenshot.png`, 800×220, instead.

- **The preview's password broke every e2e run.** The first real gh-3 run stopped at the
  code-writer: every scenario failed at Dex's login. The runner had put `SMOKE_PASSWORD` in the
  environment for the whole run, and `SignInPage` reads it, so the e2e layer signed in to the
  Compose test stack with the preview's password. Only the acceptance stage gets it now.
- **Stage links unfurled in Slack.** Each stage's file link became a GitHub card, burying the
  thread. Every post sends `unfurl_links` and `unfurl_media` false.
- **Screenshots as links.** gh-3's proof linked its screenshots from the criteria table, so
  the PR showed none. The template now shows each under *Screenshots*, and the runner shows
  any the proof only links to there, captioned with its link's label.
- **A reviewer approved without running anything.** gh-3's round-2 test-reviewer read a
  refusal as "Bash was denied" and approved by reading. The guide said a pipe into `grep`
  was fine; in dontAsk mode a `$` anywhere (`grep -v "^$"`, `echo $?`) or a `;` is refused,
  while a plain pipe into `tail`, `head`, `grep` or `sed -n` runs. The guide says so now,
  and to rerun bare and stop for a human rather than approve on reading. A public repo's
  transcripts aren't kept, so each stage's refusals are counted in `history.log` and
  written to the committed `run/refused.log`, the preview password masked.

## Verified

- On the last commit, on 2026-10-21: `scripts/test.sh lint unit` is green (1368 pytest,
  503 Vitest, and the workflows lint is clean). `scripts/test.sh integration --
  tools/delivery`: 48 passed. `.claude/delivery/loop-test.sh`: every scenario passed.
- Task 19, on `caw-project/ch09` with this branch as its `main`:
  - **Stub, gh-4.** Dispatches `39239817408` and `39242990863` opened PRs #6 and #7 with the
    stub's screenshot inline. #6 is what found the held `pull_request` run; #7's preview
    (`39245060826`) came up, commented its origin, posted its password to Slack, and went
    down within a minute of the PR's close.
  - **Real, gh-3.** `39255821740` stopped at the code-writer on the preview password in the
    e2e environment, and `39266919141` resumed it to PR #8. #8's proof only linked its
    screenshots, and #8 was closed by hand for the fix. `39491422045` restarted it to PR #9:
    five screenshots under *Screenshots*, the criteria table linking each at its commit. Its
    preview (`39504742197`) set the `preview` status deploying, up and, after 5h53m, down
    — timed out, the hold limit working as meant.
  - **Not seen live:** a second dispatch updating an open PR. Each PR here came from a run
    after the last one was closed. Only the fake `gh` has shown it:
    `test_a_rerun_with_the_pr_open_updates_it_and_opens_none`.
