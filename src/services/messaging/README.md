# CollabHub Messaging

Channels, messages and real-time delivery. Spec:
[docs/design/02-messaging-service.md](../../../docs/design/02-messaging-service.md),
on top of
[Platform Conventions](../../../docs/design/00-platform-conventions.md).

## What is built

**Channels: create and list.** `GET|POST /api/v1/channels` and
`GET /api/v1/channels/{id}`, with membership, workspace scoping and cursor
pagination.

Not yet: messages, threads, reactions, read receipts, search, and the Socket.IO
`/messaging` namespace. Channel administration — rename, archive, add and remove
members — is the next slice, which is why `PATCH`/`DELETE /channels/{id}` and
the `/members` routes are absent.

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

**Public channels are readable by the whole workspace**, joined or not. Joining
gates the messages, from the next slice. This corrected the spec, which had
marked channel detail "channel member" and made a public channel unopenable by
anyone but its creator.

**Channels archive, they do not soft-delete.** The column is `archived_at`, not
`deleted_at`, so Conventions §3's "filter `deleted_at IS NULL`" reads as
`archived_at IS NULL` for these tables.

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

All three Redis instances are configured because the service will use all three
and they are not interchangeable (R1 cache and denylist, R2 the Socket.IO
backplane, R3 index jobs). Only R1 is used so far, for the token denylist.
