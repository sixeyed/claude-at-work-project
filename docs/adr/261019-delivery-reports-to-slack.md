# A delivery reports to Slack, which also carries the preview password

- **Status:** Accepted
- **Date:** 2026-10-19

## Context

A delivery on a hosted runner takes around 100 minutes and seven agents. The only window on it
was the Actions log and, at the end, `history.log` in the job summary. Nothing told a person
that a stage had sent work back, that a run had stopped for them, or that a PR was waiting.

A delivery's previews also need a password. Dex in a preview comes from `values-k3d.yaml`,
whose seeded users all sign in with `collabhub`. The preview is on a public quick tunnel, and
its origin goes in a comment on a public PR, held open for hours
(`261019-delivery-opens-its-pr`). On a public repo, Actions' run logs, job summaries and
artifacts are public too. So a password printed anywhere the workflow can write is no secret,
and a password nobody can read is no use.

## Decision

The runner reports to Slack through a bot token (`chat:write`), in one thread per delivery. The
parent message names the issue and its status, and is edited as the status changes. A reply
goes out as each stage starts and ends, with its verdict, time, cost, summary and a link to its
file at the checkpoint. A stop, a failure, running out of time and the PR each post too, and the
PR is also sent to the channel. The thread's `ts` is kept in the run's committed `state.json`, so
a resumed run on any machine replies in the same thread, and so does `preview.yml`, through
`delivery notify`. A post that fails is logged, and the run carries on.

With `SLACK_BOT_TOKEN` and `SLACK_CHANNEL` set, each preview gets a random password. It is
bcrypted into the deps chart's existing `dex.passwordHash` value by `deploy.sh preview up`,
from `PREVIEW_PASSWORD`. It is posted in the delivery's thread and nowhere else: never on disk,
in the state, the proof, the PR or a log. The acceptance-reviewer gets it as `SMOKE_PASSWORD`,
which the smoke packs sign in with, and is told it is a credential. No other stage does: their
e2e runs sign in to the Compose test stack, whose Dex keeps `collabhub`. Without Slack — every laptop run, or a repo
without the secrets — nothing is posted and previews keep `collabhub`. The Slack token stays
with the runner and `main`'s code: agents' environments drop it, and `preview.yml` gives it only
to the step that runs `main`'s `delivery notify`, never to the PR's deploy.

## Consequences

A person can follow a run from their phone, see a send-back as it happens, and find the
preview's password where the people who should have it already are. The channel's membership
is the access list, so `#deliveries` is private.

A public preview with Slack configured can no longer be signed into by anyone who reads the PR.
Without Slack it still can, and that is accepted: the data is throwaway and the runner
ephemeral. The password lives in Slack's history, which is outside the repo's control. A
preview's password changes with every deploy, so an old message's password stops working once
a newer preview replaces it.

There is a new secret pair to manage. Slack becomes a dependency of the experience, though not
of the run. Severity counts aren't in the stage messages: reviewers lead their summaries with
blocking findings, and the result schema stays as it is.

## Alternatives Considered

### Print a generated password in the job summary

It is simple, and it would be private on a private repo. On `ch09`, summaries and logs are
public, so it would protect nothing.

### A repo secret holding one fixed preview password

It is private and needs nothing new, but the password never rotates. It also has to be shared by
hand with each reviewer, and it leaks to everyone who ever had it.

### Encrypt the password to the owner's key in the summary

Only the key's holder could read it, and there would be no new service. But every review would
start with a decrypt step, and there would be nowhere to report progress.

### A Slack incoming webhook

That is one secret and no app scopes. But a webhook can neither thread nor edit, so a run would
be ten to twenty top-level messages.

### Make the repo private

The summary would then be members-only, and a generated password could go there. But `ch09`
is public on purpose: it is what readers of the book follow.
