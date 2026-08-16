# Message edit and delete semantics

- **Status:** Accepted
- **Date:** 2026-08-16

## Context

Register entry **D8d** — "edit/delete windows and tombstone retention" — has been
open since the design docs were written, and the messaging build reached the
slice that cannot proceed without it. Doc 02 §3.1 lists `PATCH /messages/{id}` as
"author" and `DELETE /messages/{id}` as "author or channel admin" and says
nothing else: no time limit, no statement of what happens to a deleted row, and
no answer to what a refusal looks like.

Three forces met at this decision.

**Chat is a record people rely on.** A conversation is read by people who were
not there when it happened. If a deleted message simply vanishes, the replies
around it stop making sense — "yes, exactly this" answering nothing. Every
mainstream team chat product leaves a marker in place, and the acceptance
criteria written for this feature say the same thing in the user's words: "a
deleted one leaves a note in its place rather than a gap".

**A platform rule pointed the other way.** CLAUDE.md and Conventions §3 say
mutable resources carry `deleted_at` and *every query filters it*. Applied here,
a tombstone would survive until the next page load and then disappear — which is
not a tombstone, it is a rendering artefact.

**Time windows are a policy nobody had.** "You can edit for five minutes" is a
real product stance, but it needs a number, and a number needs someone to own the
consequence of a typo that is discovered at minute six. Nobody had picked one,
and the design doc's own §9 listed the window as undecided rather than assuming a
default.

Separately, **D16 — retention values** is still open. How long anything is kept
before hard deletion is a Worker concern with no numbers attached and no job
built. That boundary matters here because "tombstone retention" appears in D8d's
title, and answering half a question as though it were the whole one is how a
register starts lying.

## Decision

**No time window on either action.** The author may edit their own message at any
point in its life; the author, or an admin of the channel it is in, may delete it
at any point. An edit sets `edited_at`, which the UI renders as an "edited"
marker, so a late edit is visible rather than silent — that visibility is what a
window would otherwise have bought, at the cost of a number nobody could justify.

**Editing is the author's alone. Deleting is the author's or a channel admin's.**
The asymmetry is the point rather than an oversight: deleting someone's words is
moderation, and rewriting them under their name is forgery. No role on this
platform can edit a message it did not write.

**Deleted messages are retained in history as tombstones.** The row stays in
`GET /channels/{id}/messages` and in `GET /messages/{id}` with `body` redacted to
`""` — an empty string, never `null`, never the original text — and `deletedAt`
set. The redaction happens server-side, in the response mapper, so the text
cannot reach a client whatever the column holds. The client renders "This message
was deleted" from `deletedAt` and never from an empty body.

**This is a documented, message-specific exception to "queries filter
`deleted_at IS NULL`".** The `messages` read path does not filter that column,
and `ix_messages_channel_time` is therefore created *without* the
`WHERE deleted_at IS NULL` predicate the design doc originally gave it — a
partial index the query cannot match is worse than no index, because the failure
mode is a silent full scan. The service now carries two exceptions to one
Conventions §3 rule, and both are written into doc 02 §4: `channels` soft-deletes
through `archived_at` rather than `deleted_at`, and `messages` has `deleted_at`
and deliberately does not filter it.

**The stored `body` is never cleared.** Delete sets `deleted_at` and bumps
`version`, and touches nothing else.

**What this decision does *not* settle: how long a tombstone is kept.** That is
**D16, still open**. Nothing in this scope hard-deletes a message,
`POST /api/v1/internal/messages/sweep` is not built, and no retention job exists.
D8d is green for the *semantics* of edit and delete; the retention half of its
original title remains D16's to answer.

## Consequences

A conversation stays readable after a deletion, and stays readable after a
reload — which was the actual requirement and the thing a filtered query could
not deliver.

Two exceptions to a blanket platform rule now exist in one service. That is a
real cost: the next person to add a table to Messaging will read "queries filter
`deleted_at IS NULL`" in CLAUDE.md and find two counter-examples beside their
new code. The rule is therefore restated in doc 02 §4 as "filter the soft-delete
column unless this document says otherwise", with both exceptions named in one
place, and the model and migration docstrings repeat it where someone would
actually be reading.

**Message text survives deletion in the database.** Blanking the column would
look tidy, change nothing a client can see, and destroy data silently — and it
would pre-empt D16, which is the decision that should govern when text is
actually destroyed. The consequence to accept is that "delete" currently means
"hide, permanently, from every API" and not "erase". Anyone answering a data
subject request, or reasoning about what a database backup contains, needs to
know that. **This is the strongest argument for closing D16 sooner rather than
later**, and the register entry says so.

No time window means a message can be edited a year later and the only signal is
the "edited" marker. For a workspace chat tool that is the conventional trade,
but it does mean the record is not immutable and should not be treated as an
audit log.

An edit that changes nothing still bumps `version`. No dirty-check: `version` is
the Elasticsearch external version (D25), which wants to move forward
monotonically, and a no-op edit is not worth a special case.

Deleting twice is idempotent — the second call returns the existing tombstone
with the same timestamp and the same version, rather than bumping again for a row
that did not change.

One consequence discovered while building rather than while deciding:
**archiving a channel freezes its messages permanently.** Every message route
goes through the channel visibility query, which filters `archived_at IS NULL`,
so after an archive nobody can edit or delete anything in that channel — not the
author, not an admin — and there is no unarchive route in this scope. That is the
right default for an archive, and it is now stated in doc 02 §3.1.4 rather than
left to be discovered in a support ticket.

## Alternatives Considered

### A time window, e.g. five minutes to edit

The common alternative, and the one the register entry's title assumed. Rejected
because the window is a number nobody could justify, and because the problem it
solves — someone quietly rewriting history — is solved better by the `edited`
marker, which is visible for the life of the message rather than for five
minutes. A window also creates a support case with no good answer: the typo
found at minute six.

### Filter deleted messages out of history, per the blanket Conventions §3 rule

The rule-abiding option, and it was the starting assumption. It fails the actual
requirement: the tombstone would survive in a client's cache until the next load
and then disappear, which is worse than never showing one. It also leaves the
surrounding conversation incoherent, which is the reason products keep tombstones
at all.

### Hard-delete the row

Simplest to reason about and the strongest privacy position. Rejected because it
takes the message out of the middle of a conversation, and because it makes the
retention question moot in the wrong direction — it hard-deletes on the user's
click rather than under a policy, pre-empting D16 with an implicit "zero days".

### Clear the stored `body` on delete while keeping the row

A middle path: keep the tombstone, destroy the text. Genuinely tempting, and
rejected for one reason — it is irreversible data destruction performed as a side
effect of a UI affordance, before anyone has decided what the retention policy
is. The wire is already safe without it, since the mapper redacts every deleted
row on the way out. When D16 lands, a retention job can clear the column under a
policy that someone has actually chosen.

### Let channel admins edit as well as delete

Symmetrical, and briefly simpler to implement as one authority check. Rejected
outright: an edit under someone else's name with no signal that a third party
made it is forgery, and no product benefit justifies it. Admins moderate by
deleting.
