# Read state follows channel visibility, not membership

- **Status:** Accepted
- **Date:** 2026-09-15

## Context

Register entry **D31** — never previously given an ID — surfaced when read
markers and unread counts were built. The design doc said very little about
them: one REST row (`POST /channels/{id}/read`, "channel member"), one socket
event pair (`mark_read`, `read_receipt_updated`), a nullable `last_read_id`
column on `channel_members`, and one sentence — "unread counts are derived".
That column had already shipped, unused, in `0001_channels`, on the rule that a
column lands with its table because adding one later rewrites it.

The column's placement predates a correction that reshaped the whole service.
Doc 02 §3.1.1 settled that **visibility gates reading and writing, and
membership gates administration**: anyone in the workspace can see a public
channel, read its history and post in it, with no membership row. Two further
facts sit beside that rule. Nothing in this scope lets anyone join a channel
themselves — both member writes need a channel admin — and posting does not
create a membership row either. Put together, most of the people reading
`#general` on any given day have no `channel_members` row, and never will
unless an admin adds them one by one.

A read marker on the membership row therefore inherits the exact bug §3.1.1 was
written to remove. Grace sees `#general` in her sidebar, reads every message in
it, and gets no unread count and no way to mark it read, because she has no row
to hang one on. The design doc's "channel member" on the route is the same
literal reading that had already been corrected once for channel detail and
once for the message routes.

Three smaller questions had no answer at all: what "unread" means for your own
messages and for tombstones, what happens when two tabs mark the same channel
read out of order, and who a read receipt is broadcast to.

## Decision

We will keep read state in a table of its own, `channel_reads (channel_id,
user_id, last_read_id, updated_at)`, keyed on the channel and the person and
**gated on channel visibility** — the same `channels.get_visible` test as
reading history and posting. Migration `0003_channel_reads` creates it and drops
`channel_members.last_read_id`.

The marker **only moves forward**. Marking read is an upsert guarded by
`last_read_id < excluded.last_read_id`, so an older message arriving after a
newer one changes nothing, and `POST /channels/{id}/read` answers 204 either
way. UUID v7 ids sort by time in Postgres and in Python alike, which is what
makes the comparison mean "later". The message must be in the channel named by
the path; every miss — a channel the caller cannot see, a message from another
channel, an unknown id — is the same 404, so an id cannot be probed.

**Unread** is every message after the marker that someone else wrote and that
is not deleted; with no marker, every such message in the channel. It is
computed per request as a correlated count and returned as `unreadCount`, with
`lastReadId`, on every `Channel` the API returns. Only the reads that build that
DTO pay for the count; the visibility guard every write path authorizes through
does not.

A marker that moved is broadcast as `read_receipt_updated` to
`user:{workspaceId}:{userId}` — the reader's own connections in the current
workspace, which every connection joins on connect — skipping the connection it
arrived on when it came over the socket. It is never sent to the channel's room.

## Consequences

Everyone who can read a channel gets an unread count for it, which is the only
version of the feature that works with public channels as §3.1.1 defines them.
Read state and membership can no longer disagree, because they are no longer
the same row: removing someone from a private channel removes their access
through visibility, and their stale marker is simply never read again.

The table carries no `version` column, which is a deliberate departure from
Conventions §3's rule for updatable rows. The forward-only guard makes a lost
update impossible — the larger id always wins, whichever write lands last — so
there is nothing for optimistic concurrency to detect and nothing for a client
to send back. A future reader should not "fix" this by adding one.

There is no foreign key on `last_read_id`. A retention job (register D16) may
hard-delete the message a marker points at, and a marker must not block it; a
dangling id still compares correctly against newer ones.

The count is **exact and uncapped**, and that is the decision's main risk. A
public channel someone has never opened has no marker, so its count is every
message in it that they did not write, recomputed on every sidebar load. The
count walks `ix_messages_channel_time` from the marker forward and is cheap for
a channel you have read recently, but it is not cheap for years of history
nobody has opened. If the sidebar gets slow, cap it inside the query.

Receipts are private: nobody learns how far anyone else has read. Including the
workspace in the room name is a new pattern — Conventions §6 had only
`<entity>:<id>` rooms — and is recorded there, because one person can hold
connections in two workspaces and a connection must never carry another
workspace's traffic (§5.4).

What the unit tests written for this feature cannot reach — the count's four
rules, the forward-only guard and the 404s all need Postgres — is covered today
by a manual check and the existing integration suite's regression run, not by
tests of its own. That gap is recorded in the implementation plan.

## Alternatives Considered

### Use the `last_read_id` column already on `channel_members`

No schema change, and the column had shipped for exactly this. It lost because
it recreates the §3.1.1 bug: read state would exist only for members, and in a
scope where nobody can join a channel themselves, that means no unread count
for most people reading public channels. Upserting a membership row on first
read would fix the count by breaking something else — `myRole` would start
appearing for people who never joined, and "posting does not make you a member"
would become "reading does".

### Optimistic concurrency with a `version` column

The platform's default for updatable rows. It would turn two tabs marking the
same channel read into a 409 for one of them, which the client can do nothing
useful with — the right answer is always "keep the later marker", and the
guarded upsert gives that without a round trip.

### A capped count (`LIMIT 100`, shown as "99+")

Bounds the cost of a never-opened channel with a long history, and matches how
most chat clients display large counts. Deferred rather than rejected: the
exact count is simpler, and the cap can be added inside `_with_read_state`
without changing the API shape, since `unreadCount` stays an integer either way.

### Broadcast read receipts to the channel

Would let a UI show who has read what, as some messengers do. Nobody asked for
that, it is a privacy decision in its own right, and the design doc's own
description of `mark_read` — "broadcast to user's other sessions" — already
pointed at the reader's own connections only.
