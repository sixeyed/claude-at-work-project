# An accepted delivery opens its own PR, with its evidence in the branch's history

- **Status:** Accepted
- **Date:** 2026-10-19

## Context

Since ADR `261016-delivery-commits-its-own-branch`, a delivery ends at a pushed
`feature/<key>` whose last commit is `delivery(<key>): accepted`, with the acceptance-reviewer's
proof at `docs/plans/<key>/04-proof.md`. A person still had to open the pull request by hand
and copy the proof into it. Three things made that harder than copying text. The proof's
screenshots sit in `build/acceptance/`, which git ignores, so its links resolve only in the
worktree that ran it. Its *Try it* origin was a quick tunnel on the hosted runner, gone when
the job ended. And `caw-project/ch09` is public, so whatever the PR shows, anyone can see.

No agent calls `gh`, reads a URL or knows which backend its issue came from (handoff 05), and
only the runner commits. A PR that `deliver.yml` opens with its own `GITHUB_TOKEN` fires no
`pull_request` workflow — GitHub won't let a workflow's token start another workflow, except by
`workflow_dispatch`. And a hosted runner lives six hours at most.

## Decision

On GitHub, an accepted delivery ends in a pull request from `feature/<key>` into `main`,
opened by the runner after the `accepted` push. The acceptance-reviewer still writes only its
proof. The runner turns that into the PR's body without changing a word of it: it drops the
heading, folds `## The run` into `<details>`, and adds `Closes #N` and a note to squash. The
title is the issue's, with its key. The backend gains PR methods. `local` raises on every
one, so a forge PR is still opened by hand.

The screenshots the proof cites are committed under `docs/plans/<key>/proof/` and removed in
the very next commit, both pushed. The body links each at the commit that added it, raw, so it
shows inline. The PR's diff holds no image. `ch09` is squash-only with branches deleted on merge,
so the two commits never reach `main`'s history. GitHub keeps every PR's head at
`refs/pull/<n>/head`, which no clone fetches by default, so the links keep working after the
branch is gone.

After every change it makes to the PR, the runner dispatches `.github/workflows/preview.yml`.
That workflow deploys the PR's branch with `scripts/deploy.sh preview up` on a hosted runner,
keeps one comment on the PR with the origin, and holds until the PR is approved or closed, or
for about 5¾ hours. It previews only an open, non-draft PR whose head is a `feature/gh-N`
branch in this repo. A person's push to the branch starts it through `push` and replaces
the running preview.

Opening the PR can fail without failing the delivery. The branch is accepted and pushed, so
the run exits 0, says why, and records it in `build/delivery/publish.json` for the job
summary. A rerun of the accepted key does only what is owed: each step is found from git (the
screenshot commits, by subject, after the last `accepted`) and from the backend (the PR, by
its branch), so nothing about the PR is stored. A rerun updates the open PR and never opens a
second one. `--restart` turns it back into a draft until the next approval. `DELIVER_PR=0`
turns the step off.

## Consequences

The reviewer gets everything in one place: what was built, how it was proven, the screenshots
inline, a preview to try and the run, with no files in the diff that don't belong to the
feature. No new branch, store or cleanup job holds the evidence.

The squash-only setting is load-bearing: a merge commit or a rebase merge would put both
screenshot commits, and their blobs, in `main`'s history. It is a repo setting a person can
change, so the PR body says to squash as well. The images also live on GitHub for as long as
the PR does, deliberately.

A preview holds a hosted runner for as long as a review takes, up to six hours. It is free on a
public repo and billed on a private one. A review that takes longer finds its preview down and
re-dispatches it, or pushes. `preview.yml` runs the PR's own code, which is why it refuses
forks. It also needs *Allow GitHub Actions to create and approve pull requests*, which the
`caw-project` organisation has to allow before the repo can.

The proof's links still resolve in a worktree. Only the PR body is rewritten. The runner, not
the agent, owns every SHA and URL.

## Alternatives Considered

### The agent opens the PR

Give the acceptance-reviewer `gh pr create`. That is simpler on GitHub, but the agent would
need a token, would have to know the backend, and would need `tea` too for a forge delivery.
Every rule that keeps agents off the network would get an exception.

### A separate PR body file

Have the agent write a shorter `05-pr.md` that links the proof. That is two documents to keep
consistent, and the reviewer has to click through to the branch for the substance.

### An evidence branch or release assets

Push the screenshots to a long-lived `evidence` branch, or upload them somewhere. Either
outlives the PR and needs cleaning up. The commit pair needs neither.

### A GitHub App token instead of dispatch

Open the PR with an App's token, so `pull_request` fires as it does for a person. The events
would be cleaner, but it costs an App and a private key in the repo's secrets, for what one
`gh workflow run` does.

### A draft PR from the first checkpoint

Open a draft PR at the first stage, and have each stage update it. That shows progress on
GitHub, but every stage would need a PR body to keep up. The Slack thread
(`261019-delivery-reports-to-slack`) shows progress instead.
