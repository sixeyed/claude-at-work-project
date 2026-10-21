# Delivery opens its PR — handoff after slice 3

Slice 3 (`08-delivery-actions-plan.md`, ADR `261016-delivery-commits-its-own-branch`) made the
runner commit and push `feature/<key>` after every stage, and added `.github/workflows/deliver.yml`,
which runs the same `scripts/deliver.sh` on a hosted runner. A delivery now ends at a pushed
branch whose last commit is `delivery(<key>): accepted`, with `docs/plans/<key>/04-proof.md`
on it, and a person still has to open the PR by hand, from the proof. The next slice has one
goal:

- **The acceptance-reviewer's approval ends in a pull request.** It writes the PR, with the
  proof attached and the run's evidence uploaded, so the person reviewing has everything in
  one place: what was built, how it was proven, screenshots, a link to try it, and the run.

Asked for by the user on 2026-10-18, after three real runs of `gh-3` on `caw-project/ch09`.
Read `08-…-plan.md` first: its *Found while building* and *Verified* sections say what the
runner and the workflow do now.

## Where things stand

- **Three accepted runs of gh-3.** `feature/gh-3-run1` (~99 min, one code-review send-back to
  the test pair), `feature/gh-3-run2` (107 min, no send-backs, $26.14) and `feature/gh-3`
  (`8f50f81`, ~96 min including a failed attempt and its resume; the code-reviewer approved first time).
  Any of them is a ready-made input for building the PR step: an accepted branch with a proof.
- **The proof is already shaped as a PR body** (`acceptance-reviewer.md`, *The proof*):
  summary, try it, the criteria table, the packs, screenshots, *For the human*, the run.
  Its screenshot links are relative (`../../../build/acceptance/…`) and resolve only in a
  worktree, and its *Screenshots* section already says "the PR uploads them".
- **`build/acceptance/` is uploaded as the `<key>-acceptance` artifact** (14 days), and the
  branch as a bundle. Transcripts are uploaded only from a private repo: `ch09` is public.
- **The preview dies with the job.** Run 3's proof links a quick tunnel that was gone when
  the job ended. Handoff 07's decision 11 accepted that for slice 3; decision 4 below replaces it.
- **No CI runs on a PR.** `deliver.yml` is the repo's only workflow; `docs/test-report.md`,
  committed by the code-writer's final verification, is the test evidence.
- **Backends:** `tools/delivery/delivery/model.py`'s `Backend` has `check`, `create`, `get`,
  `edit` and `ensure_label`, and nothing for PRs. `github.py` shells out to `gh`; `local.py`
  is files. Forge PRs have so far been opened by a person with `tea`.

## Decided

Decisions 1–4 were the user's going in; 5–27 were settled in a grilling session on 2026-10-19.

| # | Decision |
|---|---|
| 1 | **The approval opens the PR.** An `approved` acceptance pass ends with a PR from `feature/<key>` into `main`, opened in the same run, after the `accepted` commit is pushed. |
| 2 | **The acceptance-reviewer writes it.** The PR's title and body are the acceptance-reviewer's, built from its proof, with the proof's evidence attached and the run's artifacts linked. |
| 3 | **Screenshots live in the branch's history for as long as the PR does.** The runner commits the screenshots the proof cites under `docs/plans/<key>/proof/`, then deletes them in the very next commit, and pushes both. The PR body links each one at the commit that added it (`…/blob/<sha>/…?raw=true`), so they show inline. The PR's diff has no images. A squash merge brings none into `main`; a plain or rebase merge would put both commits in `main`'s history, so the repo is squash-only (decision 17). Deleting the branch doesn't delete the commits: GitHub keeps every PR's head at `refs/pull/<n>/head`, which no clone fetches by default, so the PR's links keep working after the branch is gone. No evidence branch, nothing to clean up. |
| 4 | **The preview a reviewer tries runs on a hosted runner, held open for the review.** A new `.github/workflows/preview.yml` deploys the PR's branch with `scripts/deploy.sh preview up`, posts the origin to the PR, and then waits. We assume a PR is reviewed well within a hosted runner's 6 hours. The job ends when the PR is approved or closed, or just before its time limit, whichever comes first. A push to the PR starts a new preview job and cancels the old one (one concurrency group per PR, `cancel-in-progress: true`), so a closed event stops the waiting job the same way. The proof's *Try it* section points at the PR's preview, not the acceptance run's tunnel, which dies with `deliver.yml`. |
| 5 | **The agent writes, the runner opens.** No agent calls `gh` or knows the backend. The runner opens or updates the PR through new `Backend` methods — find by head branch, open, update — after the push. `github.py` uses `gh pr`; `local.py` does nothing but say so. |
| 6 | **The proof is the PR body; there is no `05-pr.md`.** The runner builds the body from `04-proof.md` mechanically: screenshot links rewritten to the commit that holds them, `## The run` collapsed in `<details>`, `Closes #N` for the issue and a one-line "squash merge this PR" note appended. Every word of it is still the agent's. |
| 7 | **Screenshot links.** The agent never sees a SHA or a URL. The runner copies exactly the screenshots the proof cites into `docs/plans/<key>/proof/`, commits them, removes them in the next commit, and rewrites each link in the PR body to the raw URL at the commit that added them. A cited file that doesn't exist fails the PR step, never silently drops. The screenshot commits are made only when a PR will be opened. |
| 8 | **The delivery's PR starts its preview by dispatch.** A PR, push or edit made with `GITHUB_TOKEN` fires no `pull_request` workflow, so the runner runs `preview.yml` by `workflow_dispatch` (`-f pr=<n>`) after every change it makes to the PR. `preview.yml` takes both triggers and one concurrency group per PR, `preview-<n>`. No GitHub App. |
| 9 | **Only delivery PRs get a preview.** `preview.yml` deploys a PR only when its head is in this repo (never a fork) and its branch is `feature/gh-*`, and skips a draft. The public repo's forks can't spend our runners or put their code on a public tunnel. |
| 10 | **The preview password is random only when Slack can deliver it.** `ch09` is public, so its run logs, job summaries and artifacts are public too: a password printed there is no secret. With `SLACK_BOT_TOKEN` and `SLACK_CHANNEL` set, each preview gets a random password, posted to the delivery's Slack thread and nowhere else; without them — any laptop run, or Actions with no Slack secrets — it stays `collabhub`. A laptop run never generates one. The password reaches Dex as the deps chart's existing `dex.passwordHash` value, bcrypted by `deploy.sh preview up` from `PREVIEW_PASSWORD`. It is never written to disk, the state, the proof or the PR. |
| 11 | **Both previews use it.** The acceptance run's own preview gets the random password too; the agent's environment carries it as `SMOKE_PASSWORD`, which the smoke packs read (default `collabhub`), and the runner posts it to the run's thread with the origin. |
| 12 | **The PR opens only at `approved`, as a ready PR.** No draft from the first checkpoint. |
| 13 | **A rerun never opens a second PR.** It finds the open PR by head branch and updates its title and body. A `--restart` with a PR open turns it back into a draft and comments that a redelivery is running; the approval marks it ready again. `preview.yml` skips drafts, so a half-built branch is never previewed. |
| 14 | **A PR failure is not a failed delivery.** The push succeeded and the branch is accepted: the run exits 0, the job summary says ⚠️ with the error, and a rerun of the accepted key does only what the publish step still owes — the screenshot commits if missing, then the PR, then the dispatch. Each is idempotent, found from git and the backend rather than stored. `DELIVER_PR=0` turns the step off; `loop-test.sh` sets it. |
| 15 | **The preview ends** when `reviewDecision` is `APPROVED`, when the PR is closed or merged, or at about 5¾ hours, polled every 60 s. One sticky PR comment, found by a marker and edited in place, shows the origin while it is up and *preview down — approved / closed / timed out* after. |
| 16 | **Slack, in this slice.** The runner posts to one thread per delivery run with a bot token (`chat:write`, `chat.postMessage` and `chat.update`); the thread's `ts` is kept in `state.json`, so a resumed run, on any machine, replies in the same thread. The parent message is edited to the latest status. Each stage posts when it starts (stage, round, model) and ends (verdict, duration, cost, the agent's summary cut to ~300 characters, a link to its review file at the checkpoint); a stop, a failure, out of time and the PR opened post too, the PR one broadcast to the channel. A failed post is logged and never fails a run. The channel is a private `#deliveries`. |
| 17 | **`ch09` is squash-only, with `delete_branch_on_merge` on** — the condition decision 3 depends on. A person changes the setting. |
| 18 | **`preview.yml` posts in the delivery's thread**, the `ts` read from `docs/plans/<key>/run/state.json` on the PR's branch, broadcast to the channel; with no `ts`, a new top-level message. |
| 19 | **Reviewer findings by severity stay out of the result schema.** A stage's Slack message carries its summary; reviewers lead their summaries with the blocking findings. |
| 20 | **Forge stays manual.** GitHub only; the `local` backend opens no PR. |
| 21 | **Stage labels and `needs_human` on the issue stay out** — handoff 05's open items 1–2 carry over. |
| 22 | **The Node 24 action majors** (`checkout`, `setup-node`, `upload-artifact`, `setup-uv`) come in this slice; `preview.yml` starts on them. |
| 23 | **Two ADRs:** *Delivery opens its PR, with its evidence in the branch's history* (decisions 1–7, 12–14, 17, the `refs/pull` correction) and *Delivery reports to Slack, which carries the preview password* (10, 11, 16, 18). |

## What it will need, roughly

1. **Backend, test first:** `find_pull_request(head)`, `open_pull_request`, `update_pull_request`
   (title, body, draft or ready), `comment_on_pull_request`, `start_preview(pr)` and `blob_url(sha, path)`
   on the `Backend` protocol; `github.py` through `gh pr …`, `gh workflow run` and the repo URL;
   `local.py` does nothing and says why. Unit tests against the fake `gh`, as the existing adaptor
   tests do.
2. **The publish step, pure first:** the screenshots a proof cites, the PR body from the proof, the
   title. Then the runner: after the `accepted` push, the screenshot commits, the PR, the dispatch;
   on a rerun of a done delivery, whatever of those is owed; on `--restart`, the draft.
3. **Slack:** a notifier with a fake transport under test, the message shapes as pure functions, the
   thread `ts` in the state, and a `delivery notify` command `preview.yml` posts through.
4. **The password:** `deploy.sh preview up` takes `PREVIEW_PASSWORD`; the smoke packs read
   `SMOKE_PASSWORD`; the runner makes one only when Slack is configured.
5. **The acceptance-reviewer:** *Try it* points at the PR's preview comment and the preview
   password; nothing about URLs or SHAs.
6. **Workflows:** `deliver.yml` gets `pull-requests: write`, `actions: write`, the Slack secrets, the
   PR's URL or error in its summary and the Node 24 majors; `preview.yml` as decisions 4, 8, 9, 15, 18.
7. **Record:** CLAUDE.md's *Delivery workflow* paragraph, the `delivery.run` docstring,
   `.env.example`, two ADRs.
8. **Proof:** a stub dispatch on `ch09` that opens a PR, whose preview comes up, posts its origin to
   the PR and its password to Slack; a second dispatch updates the PR; closing the PR takes the
   preview down. Then one real run.

**For a person:** the Slack app and its two secrets on `ch09`; *Allow GitHub Actions to create and
approve pull requests* on `ch09`; squash-only and `delete_branch_on_merge` on `ch09`.

The plan is `10-delivery-pr-plan.md`.

## Carried over

- **The turn caps don't bite as configured.** `--max-turns` counts something different from
  the result's `num_turns`: the test-writer reported 294 and 310 turns against a cap of 200.
  Worth measuring before any cap is relied on.
- **Agent sketching is the test-reviewer's alone again** (slice 3, after run 3): the
  test-writer's proving pass cost about ten minutes a run, and the test-reviewer found the gaps anyway.
- **Actions annotations from every run:** the v4 actions target Node 20 and are forced onto
  Node 24, and `ubuntu-latest` moves to Ubuntu 26 from 2026-10-19. Bump `checkout`,
  `setup-node`, `upload-artifact` and `setup-uv` to their Node 24 majors.
- **Housekeeping on `ch09`:** issue #4 and `feature/gh-4` from the stub runs, and the backup
  branches `feature/gh-3-run1` and `-run2`. Locally, the review worktree
  `../caw-gh-3-review`.
- **A delivery's branch never takes a later `main`** (slice 3, *Verified*). A long-open
  delivery PR can fall behind `main`; the PR shows that, and the runner still never merges.

## Not this slice

Merging, and any review agent acting on PR comments. A preview that outlives a hosted
runner's 6 hours (a self-hosted runner or a long-lived cluster). Forgejo and Azure DevOps adaptors
beyond what open item 7 settles. CI checks on the PR — a separate workflow, not the
delivery's.
