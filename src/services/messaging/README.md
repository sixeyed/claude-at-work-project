# CollabHub Messaging

Channels, messages and real-time delivery. Spec:
[docs/design/02-messaging-service.md](../../../docs/design/02-messaging-service.md),
on top of
[Platform Conventions](../../../docs/design/00-platform-conventions.md).

## What is built

**Channels.** `GET|POST /api/v1/channels`, `GET|PATCH|DELETE
/api/v1/channels/{id}` — create, list, read, rename and archive — plus
`GET|POST /api/v1/channels/{id}/members` and
`DELETE /api/v1/channels/{id}/members/{userId}`. Workspace-scoped, cursor
paginated, with optimistic concurrency on `version`.

**Messages.** `GET|POST /api/v1/channels/{id}/messages` and
`GET|PATCH|DELETE /api/v1/messages/{id}` — send, read history newest-first,
edit and delete.

**Real-time.** The Socket.IO `/messaging` namespace: an authenticated handshake,
`join_channel` / `leave_channel`, inbound `send_message` / `edit_message` /
`delete_message` / `typing`, and outbound `message_received` / `message_edited` /
`message_deleted` / `user_typing`.

Not built: threads, reactions, read receipts and search — see spec §3.1.5, which
lists every endpoint the design doc names and this service does not implement,
with the reason for each.

## Rules worth knowing before you change anything here

**The workspace comes from the token.** `channels.workspace_id` is
`principal.workspace_id`, the `wsp` claim, and never a value from a path, query
or body (Conventions §5.4). There is no workspace field in any request on this
surface — the shape makes the leak unrepresentable rather than the handler
refusing it. `tests/test_tenancy.py` holds the line.

**Plain `require_user`, not `require_user_sensitive`.** Channel membership is
not workspace membership, so channel writes are outside the fail-closed denylist
set (Conventions §5.2, spec §3.1). An unreachable R1 fails open here.

**A channel you may not see is a 404, never a 403.** 403 confirms that a private
channel exists and discloses its name. See spec §3.1.1.

**Visibility gates reading and writing; membership gates administration.** If
`channels.get_visible` returns a channel, the caller may read its history, post
in it, and join its Socket.IO room — no membership row needed. Membership is
what gates renaming, archiving and the member list writes. This corrected the
spec twice: it had marked channel detail *and* the message routes "channel
member", which — since nothing in this scope lets anyone join a channel
themselves — would have made a public channel unreadable by everyone but its
creator. So a guard here is `get_visible`, never `is_member`.

**Posting does not create a membership row.** `myRole` stays `null` for someone
who has spoken in a public channel they never joined.

**Channels archive, they do not soft-delete.** The column is `archived_at`, not
`deleted_at`, so Conventions §3's "filter `deleted_at IS NULL`" reads as
`archived_at IS NULL` for these tables. Archiving is **one-way**: every read
filters it out, so an archived channel is invisible to everyone including its
own admin, its messages are frozen, and its name is not released.

**Messages history returns tombstones, and filters no soft-delete column at
all.** The other exception to Conventions §3, and the opposite one: a deleted
message stays in history with `body` redacted to `""` server-side and
`deletedAt` set, because a tombstone a reload erases is not a tombstone.
`history_page` and `get` have no `deleted_at` clause, which is also why
`ix_messages_channel_time` is **not** the partial index the spec originally gave
(spec §3.1.4, register D8d).

**Admins delete, they do not edit.** Only an author may rewrite their own
message; an author or a channel admin may delete one. Deleting someone's words
is moderation; rewriting them under their name is forgery.

**The socket is not a second copy of the rules.** The inbound handlers call the
same `messages.create` / `edit` / `delete` the REST routes call, authorize on
the same `get_visible`, and commit before they publish. Room membership decides
who *receives* a broadcast and authorizes nothing — a room is per-`sid` state
that a reconnect destroys.

**Names are compared without case.** `ux_channels_public_name` indexes
`lower(name)`, so `#General` collides with `#general`; the stored name keeps the
case it was typed with. Uniqueness applies to public channels only — the index
is partial.

## Deliberately absent

**The `jobs:index` producer (R3).** Nothing consumes it: the Worker is unbuilt
and search is out of scope. The `version` column ships anyway because it earns
its place on optimistic concurrency alone (Conventions §3), so adding the
producer later is purely additive.

**`attachments` in the API.** The column arrives with `messages`; the Asset
service is still a skeleton.

**`POST /api/v1/internal/messages/sweep`.** Retention values are register D16,
still 🔴.

**The `reactions` table.** Not created until reactions are built — an empty
table is a claim about what the service does that is not yet true.

**`ix_messages_thread`.** The spec's §4 DDL lists it and `0002_messages` does
not create it. `thread_root_id` ships as a *column* because adding one later
rewrites the table; an index supporting a query no code makes is dead weight,
and adding it with the threading feature costs one line and no rewrite.

## Running it

The service is part of the Compose stack; see the [root README](../../../README.md).

```bash
# Tests — real Postgres and Redis via testcontainers, so Docker must be running
uv run pytest src/services/messaging

# Migrations, against this service's own database only
docker compose exec messaging python -m messaging.migrate
```

Migrations also run from `docker/messaging/entrypoint.sh` on container start
unless `RUN_MIGRATIONS=false`. In Kubernetes, set that and run
`python -m messaging.migrate` as a pre-upgrade Job instead — several replicas
rolling out at once must not each try to migrate.

The OpenAPI document is what the SPA generates its client from, and it can be
produced without a running stack:

```bash
uv run python -m messaging.openapi > src/frontend/openapi/messaging.json
```

## Configuration

Common variables per Conventions §8, plus `MESSAGING_MAX_BODY_CHARS` (8000) and
`MESSAGING_MAX_ATTACHMENTS` (10) from spec §6. `CORS_ALLOWED_ORIGINS` matters
locally: the SPA is a separate origin, and without it the browser will not call
this service at all. Empty installs no CORS middleware, which is the deployed
case behind a single ingress.

All three Redis instances are configured because they are not interchangeable:
**R1** cache and token denylist, **R2** the Socket.IO backplane, **R3** index
jobs. R1 and R2 are in use; R3 is not, because the `jobs:index` producer is not
built.

**R2 is addressed with an explicit pub/sub channel**, `channel="messaging"`, and
not `AsyncRedisManager`'s default. Canvas shares this Redis instance, and the
default is the same string in every service — two managers on one channel would
deliver each other's emits into each other's processes. Nothing visibly breaks
while the room names happen not to collide, which is what makes it worth being
explicit about.
