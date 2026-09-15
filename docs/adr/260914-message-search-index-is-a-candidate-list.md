# The message search index is a candidate list, not a source of truth

- **Status:** Accepted
- **Date:** 2026-09-14

## Context

Message search arrived as two halves that run at different speeds. Messaging commits a
message, broadcasts it, and enqueues a `jobs:index` job onto Redis Streams; the Worker picks
the job up whenever it gets to it and writes an Elasticsearch document; `GET
/search/messages` reads that index. Register D25 had already settled that the job carries the
whole document and that `messages.version` is the Elasticsearch external version, so a stale
edit arriving late is refused rather than applied. What it had not settled was how much the
read side should *believe* the index.

Three facts made that question unavoidable.

**The index always lags the database.** By design — the enqueue is fire-and-forget
(Conventions §7) and the Worker scales on stream depth, not on request latency. For a few
hundred milliseconds normally, and for as long as an outage lasts otherwise, the index
describes a slightly older world than Postgres does. Deleted messages are the case that
matters: the product promise (register D8d) is that a deleted message's text is gone from
view, and a lagging index would break it.

**Hard deletes are not durable in Elasticsearch.** Doc 05 originally said `message.delete`
deletes the document. Elasticsearch keeps a deleted document's version only for
`index.gc_deletes`, 60 seconds by default. A stale `message.upsert` reclaimed after a Worker
crash — or simply delivered late — would find no version to lose to and recreate the
document, text and all. Retries and reclaims are normal operation for this pipeline, so this
is a when, not an if.

**Visibility changes constantly and lives in Messaging.** Who can see a message depends on
the channel's kind, the caller's membership and whether the channel is archived — all rows in
Messaging's database, all of which change without the message changing. Anything copied into
the index about who may see a document goes stale the moment someone is removed from a
private channel.

## Decision

We treat the `messages` index as a list of candidates for a query, and Postgres as the only
authority on what a caller sees. Three rules follow, and they are recorded together because
each depends on the others.

**Deletes write tombstones.** `message.delete` indexes a document at the bumped version with
the identifiers, `deleted: true` and no `body`. The text leaves the index as soon as the job
runs, and because the document still exists, its version survives indefinitely — a stale
upsert gets a 409 forever, not just for the first minute. The Worker treats that 409 as
success, which also makes duplicate delivery harmless. Hard removal from the index waits for
retention (D16).

**Authorization is a per-request filter, never data in the index.** For every search,
Messaging computes the caller's visible channel ids with the same query every other read uses,
and filters the Elasticsearch query to those ids, the `wsp` claim's workspace and
`deleted: false`. The index stores `workspaceId` and `channelId` only so they can be filtered
on.

**Results are hydrated from Postgres.** Elasticsearch returns ordered ids and nothing else.
Messaging loads those rows with `deleted_at IS NULL` and the visible-channel filter, keeps
Elasticsearch's order, and returns the ordinary `Message` DTO. A hit whose row has since been
deleted, or whose channel the caller can no longer see, is dropped.

## Consequences

A deleted message cannot be shown by search, however far behind the Worker is: the tombstone
removes it from the index eventually, and hydration removes it from results immediately.
Membership changes and archives take effect in search on the next request, with nothing to
reindex. Search returns exactly the DTO the SPA already renders — current body, `editedAt`,
`version` — so there is no second shape to keep in step.

Pages can be short. When hydration drops hits, a page holds fewer than `limit` items while
`nextCursor` is still set, because the cursor comes from the Elasticsearch hits so that
nothing is skipped. Clients must treat only `nextCursor: null` as the end. This is documented
on the route and in doc 02 §3.1.6, and it is the kind of detail a future client will get wrong
once.

Every search costs a visibility query and a primary-key lookup of up to 200 rows on top of the
Elasticsearch query. That is cheap at current scale; a workspace with very many channels also
approaches `index.max_terms_count` (65 536 by default) for the channel filter, far beyond any
realistic workspace but a limit worth knowing exists.

The index grows by one tombstone per deleted message until retention (D16) decides when those
are removed, and a reindex (D29) will need to carry tombstones across or rebuild from Postgres.

Recall, unlike visibility, still depends on the index. A job lost between commit and `XADD` is
a message search never finds until a reindex path exists — register D29, 🔴.

## Alternatives Considered

### Hard delete, as doc 05 first described

Simpler index and no `deleted` field. Rejected because Elasticsearch forgets the deleted
version after `index.gc_deletes`, so a late stale upsert — routine under retry and reclaim —
resurrects the message and its text in search.

### Visibility stored in the index

Indexing each document with the users or roles allowed to see it would let Elasticsearch
answer authorization alone. Rejected because visibility is a property of channel membership
and archive state, not of the message: every membership change or archive would need a
rewrite of every document in the channel, and the index would be a stale copy of Messaging's
authorization rules — a tenancy leak waiting for a missed update.

### Returning Elasticsearch documents directly

Skipping hydration saves a query. Rejected because it introduces a second message DTO that
drifts from the real one (no `editedAt`, no current `version`), and because index lag would
show a just-deleted message's text — exactly the promise D8d makes.

### Deleting the tombstone's text from Postgres on delete as well

Considered only to note it is out of scope: when message text is destroyed in the database is
retention (D16), and a delete path that blanked the row would pre-empt that decision
(ADR 260816).
