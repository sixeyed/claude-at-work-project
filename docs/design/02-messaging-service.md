# CollabHub — Messaging Service

> Channels, threads, messages, reactions, read receipts, and real-time delivery.
> Read [Platform Conventions](./00-platform-conventions.md) first.

**Status:** Draft · **Runtime:** Python 3.12 / FastAPI + Socket.IO
**Owns:** channels, membership, messages, threads, reactions, read receipts
**Depends on:** PostgreSQL (own DB), Redis Real-time (R2), Redis Cache (R1), Redis Streams (R3)

---

## 1. Purpose & Responsibilities

The chat half of CollabHub. Provides Slack-like channels and threaded messaging with
sub-second real-time delivery.

**Owns:** channels and their membership/permissions, messages, threads, reactions,
read receipts, typing indicators.
**Produces:** index jobs to `jobs:index` (R3) for Elasticsearch (consumed by Worker).
**Does NOT own:** search querying (read path goes to Elasticsearch directly or via a thin
search endpoint — see §3), file attachments (Asset Service owns blobs; messages reference asset IDs).

---

## 2. Runtime & Dependencies
- FastAPI REST + a Socket.IO server on the `/messaging` namespace, with the R2 backplane
  (Conventions §6). The Socket.IO ASGI app is mounted alongside FastAPI on one Uvicorn process.
- SQLAlchemy 2.0 (async) + asyncpg; Alembic migrations.
- `redis-py` (`redis.asyncio`) for R1 (hot data), R2 (Socket.IO Redis manager / pub-sub),
  R3 (index jobs).

---

## 3. Public Interface

### 3.1 REST (`/api/v1`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/channels` | member | List channels visible to the user (cursor paginated, alphabetical). |
| POST | `/channels` | member | Create channel. Creator becomes its admin. |
| GET | `/channels/{id}` | see §3.1.1 | Channel detail. |
| PATCH | `/channels/{id}` | channel admin | Rename / change topic / archive. |
| DELETE | `/channels/{id}` | channel admin | Soft-delete (archive). |
| GET | `/channels/{id}/members` | channel member | List members. |
| POST | `/channels/{id}/members` | channel admin | Add member(s). |
| DELETE | `/channels/{id}/members/{userId}` | channel admin | Remove member. |
| GET | `/channels/{id}/messages` | channel member | History, cursor paginated, newest-first. |
| POST | `/channels/{id}/messages` | channel member | Send message (REST fallback; prefer the Socket.IO event). |
| GET | `/messages/{id}` | channel member | Single message (+ thread root). |
| PATCH | `/messages/{id}` | author | Edit message. |
| DELETE | `/messages/{id}` | author or channel admin | Delete message. |
| GET | `/messages/{id}/thread` | channel member | Replies in a thread (cursor paginated). |
| POST | `/messages/{id}/reactions` | channel member | Add reaction `{ "emoji": ":+1:" }`. |
| DELETE | `/messages/{id}/reactions/{emoji}` | channel member | Remove own reaction. |
| POST | `/channels/{id}/read` | channel member | Mark read up to `{ "messageId": "..." }`. |
| GET | `/search/messages?q=` | member | Thin proxy to Elasticsearch (optional). |

**Internal** (`/api/v1/internal/`, service token only — Conventions §5.5; never reachable
from the public ingress, and never carrying `require_user`):

| Method | Path | Scope | Purpose |
|--------|------|-------|---------|
| POST | `/internal/messages/sweep` | `messages:retention` | Delete messages past the retention window. The Worker calls this; it deletes nothing itself (register D25). |

**Every channel is scoped to the workspace in the token's `wsp` claim.** `channels.workspace_id`
comes from the claim and never from the request body or a query parameter — Conventions §5.4
is explicit that authorization must not accept a workspace identifier in place of the claim,
and substituting one here is a tenancy leak. A caller who wants another workspace switches
token first (`POST /auth/switch-workspace`).

Channel membership is *not* workspace membership, so these writes are **not** in the
fail-closed denylist set (Conventions §5.2) — that set names workspace membership changes,
role grants and asset deletion.

List endpoints use the cursor pagination in `collabhub-shared` (`?limit=`/`?cursor=`,
`{items, nextCursor}` — Conventions §4.1). Never `OFFSET`.

#### 3.1.1 Channel visibility

**Corrected 2026-08-15, while building the channels slice.** This table
originally marked channel detail "channel member", and never defined the list
rule at all. Together those made a public channel unopenable by anyone but its
creator — you could see `#general` in the sidebar and get a 403 clicking it,
until an admin added you. That is not what a public channel means.

| Request | Result |
|---|---|
| `GET /channels` | non-archived `public` channels in the token's `wsp`, **plus** any kind the caller is a member of |
| `GET /channels/{id}`, public, same workspace | 200 — membership is **not** required |
| `GET /channels/{id}`, private, member | 200 |
| `GET /channels/{id}`, private, non-member | **404** |
| `GET /channels/{id}`, any other workspace | **404** |

Membership gates the *messages* in a channel, not the knowledge that it exists.

A caller who may not see a channel gets **404, never 403**. A 403 confirms the
channel exists and discloses its name to someone with no access to it; from that
token's point of view it does not exist, and the response says so.

Channels sort by `(name, id)`. The pair is the cursor: `name` alone is not
unique, because private channels and DMs may repeat one.

#### 3.1.2 Channel names

**Added 2026-08-15.** The docs previously gave no format at all, and one length
in a Conventions §4.2 *example* ("between 1 and 80 characters"). The rule:

- 3 to 80 characters, after trimming
- letters, numbers and hyphens only — ASCII `[A-Za-z0-9-]`
- must start with a letter
- unique among the **public** channels in a workspace, compared **without case**:
  `#General` collides with `#general`. The name is stored and displayed exactly
  as typed; only the index folds case
- a duplicate is `409 conflict`; a broken format rule is `400 validation-error`
  with the reason under `errors.name`, one message per rule so a form can show
  which part was wrong

This is a real narrowing: `#café` is not a valid channel name, and neither is
any name in a non-Latin script. Worth revisiting before a customer outside
English-speaking markets.

`kind` accepts `public` and `private` through the API. `dm` exists in the schema
(register D8b) but is not creatable this way — a DM has no name and no
creator-as-admin.

#### 3.1.3 DTOs

`Channel` DTO — **added 2026-08-15**; the doc previously specified only
`Message`:

```json
{
  "id": "uuid", "name": "general", "topic": "string|null",
  "kind": "public|private|dm", "createdBy": "uuid",
  "createdAt": "...", "updatedAt": "...", "archivedAt": "...|null",
  "version": 0,
  "myRole": "admin|member|null"
}
```

There is deliberately no `workspaceId`: a channel is always in the workspace
named by the caller's `wsp` claim, and echoing it invites a client to start
sending it. `myRole` is the caller's role in that channel, `null` if they are
not a member — it is what decides whether the UI offers the admin controls.

`Message` DTO:
```json
{
  "id": "uuid", "channelId": "uuid", "authorId": "uuid",
  "threadRootId": "uuid|null", "body": "markdown text",
  "attachments": ["assetId", "..."],
  "reactions": [{ "emoji": ":+1:", "count": 3, "mine": true }],
  "createdAt": "...", "editedAt": "...|null", "deletedAt": "...|null"
}
```

### 3.2 Socket.IO namespace — `/messaging`

Real-time runs on the Socket.IO `/messaging` namespace (Conventions §6). Client→server
events are verbs; server→client events are past-tense facts. `send_message` returns the
created `Message` via the Socket.IO acknowledgement callback.

**Client → Server**

| Event | Args | Effect |
|--------|------|--------|
| `join_channel` | channelId | Authorize + join room `channel:{id}`. |
| `leave_channel` | channelId | Leave room. |
| `send_message` | `{ channelId, body, threadRootId?, attachmentIds? }` | Persist + broadcast. Returns the created `Message` via ack. |
| `edit_message` | `{ messageId, body }` | Author-only edit + broadcast. |
| `delete_message` | `{ messageId }` | Author/admin delete + broadcast. |
| `add_reaction` / `remove_reaction` | `{ messageId, emoji }` | Broadcast reaction change. |
| `mark_read` | `{ channelId, messageId }` | Update read receipt; broadcast to user's other sessions. |
| `typing` | `{ channelId }` | Ephemeral; fan out `user_typing` (not persisted). |

**Server → Client (events)**

| Event | Payload |
|-------|---------|
| `message_received` | `Message` |
| `message_edited` | `Message` |
| `message_deleted` | `{ messageId, channelId }` |
| `reaction_changed` | `{ messageId, emoji, count, userId, added }` |
| `read_receipt_updated` | `{ channelId, userId, messageId }` |
| `user_typing` | `{ channelId, userId }` |

Rooms and naming follow Conventions §6. Presence (online/away) is published to R2 and
mirrored to the Canvas service's presence as needed (shared R2).

---

## 4. Data Model (PostgreSQL)

```sql
CREATE TABLE channels (
    id           uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    name         text NOT NULL,
    topic        text NULL,
    kind         text NOT NULL DEFAULT 'public',  -- public | private | dm
    created_by   uuid NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    archived_at  timestamptz NULL,
    version      integer NOT NULL DEFAULT 0
);

-- A partial index, not a table constraint: PostgreSQL has no
-- `UNIQUE (...) WHERE ...` on a constraint, only on an index. Names are unique
-- among public channels; private channels and DMs may repeat one.
--
-- Indexes `lower(name)`, not `name` (corrected 2026-08-15): #General and
-- #general are the same channel. The stored name keeps the case it was typed
-- with — only the comparison folds.
CREATE UNIQUE INDEX ux_channels_public_name
    ON channels (workspace_id, lower(name)) WHERE kind = 'public';

-- Added 2026-08-15. The sidebar reads one workspace's unarchived channels in
-- name order on every page load, and nothing above covers that.
CREATE INDEX ix_channels_workspace_name
    ON channels (workspace_id, name, id) WHERE archived_at IS NULL;

CREATE TABLE channel_members (
    channel_id   uuid NOT NULL REFERENCES channels(id),
    user_id      uuid NOT NULL,
    role         text NOT NULL DEFAULT 'member',  -- admin | member
    last_read_id uuid NULL,                        -- read receipt pointer
    joined_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (channel_id, user_id)
);

-- Added 2026-08-15. The primary key leads with channel_id, so it answers "who
-- is in this channel?" but not "which channels is this user in?" — which is the
-- query the sidebar runs for every signed-in user.
CREATE INDEX ix_channel_members_user ON channel_members (user_id, channel_id);

CREATE TABLE messages (
    id             uuid PRIMARY KEY,                -- UUID v7 → time-ordered
    channel_id     uuid NOT NULL REFERENCES channels(id),
    author_id      uuid NOT NULL,
    thread_root_id uuid NULL REFERENCES messages(id), -- NULL = top-level
    body           text NOT NULL,
    attachments    uuid[] NOT NULL DEFAULT '{}',     -- Asset service IDs
    created_at     timestamptz NOT NULL DEFAULT now(),
    edited_at      timestamptz NULL,
    deleted_at     timestamptz NULL,
    version        integer NOT NULL DEFAULT 0   -- bumped on edit/delete
);
CREATE INDEX ix_messages_channel_time ON messages (channel_id, id DESC) WHERE deleted_at IS NULL;
CREATE INDEX ix_messages_thread ON messages (thread_root_id, id) WHERE thread_root_id IS NOT NULL;

CREATE TABLE reactions (
    message_id   uuid NOT NULL REFERENCES messages(id),
    user_id      uuid NOT NULL,
    emoji        text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (message_id, user_id, emoji)
);
```

`version` serves double duty. It is the optimistic-concurrency column Conventions §3 requires
of any updatable row, and it is what `jobs:index` carries as the Elasticsearch external
version (register D25) — so a late-arriving older document is rejected rather than applied.
Bump it on every edit and on delete.

**`channels` soft-deletes through `archived_at`, not `deleted_at`.** Conventions
§3 says mutable resources carry `deleted_at` and every query filters it; for
this table the equivalent column is `archived_at`, and `DELETE /channels/{id}`
sets it. Reads filter `archived_at IS NULL`. Called out because the blanket rule
sends people looking for a column that is not there.

Threading is single-level: a reply sets `thread_root_id` to the top-level message; replies to
replies still point at the root. Read state is a per-member pointer (`last_read_id`); unread
counts are derived (messages with `id > last_read_id`).

### 4.1 Redis usage
- **R1:** cache channel membership sets and recent-message windows for fast event authorization.
- **R2:** Socket.IO Redis manager (backplane) + presence pub/sub.
- **R3:** `jobs:index` — one job per created/edited/deleted message for ES sync. The payload
  carries the whole document (§5), so these entries contain user-authored message bodies —
  see the retention and trimming note in Worker doc §8.

---

## 5. Internal Design — Send Message
Mirrors the architecture's sequence diagram:
1. Client emits the `send_message` event on the `/messaging` namespace.
2. Persist to `messages` (PostgreSQL).
3. Broadcast `message_received` to room `channel:{id}` via the R2 backplane.
4. `XADD jobs:index` with the **full indexable document**, not just an identifier:
   `{ messageId, channelId, workspaceId, authorId, body, createdAt, version, op: "upsert" }`.
   🟢 Register D25 — the Worker holds no database connection, and Messaging already has the
   message in hand here, so a read-back would add load to this exact path for nothing.
   `version` is the row's version, used as the Elasticsearch external version so two rapid
   edits cannot be indexed out of order. See the
   [ADR](../adr/260727-worker-never-reads-service-databases.md).
5. Worker consumes and indexes into Elasticsearch (Worker doc owns the mapping).

Edits/deletes follow the same persist → broadcast → enqueue(`op: upsert|delete`) pattern.

---

## 6. Configuration
Common vars (Conventions §8): owns `POSTGRES_DSN`, uses `REDIS_CACHE_URL`,
`REDIS_REALTIME_URL`, `REDIS_STREAMS_URL`. Plus `MESSAGING_MAX_BODY_CHARS` (default 8000),
`MESSAGING_MAX_ATTACHMENTS` (default 10).

## 7. Cross-Cutting
Auth, errors, pagination, observability, health per Conventions. Metrics:
`messages_sent_total`, `messages_edited_total`, `reactions_total`, Socket.IO connection gauge.

## 8. Non-Functional & Limits
- Real-time delivery p99 < 500 ms end-to-end.
- Max message body 8000 chars; max 10 attachments; emoji from an allow-list.
- History reads served from Postgres; full-text from Elasticsearch.

## 9. Open Decisions
- Threading depth: single-level (assumed) vs. nested.
- DM modelling: as `kind='dm'` channels (assumed) vs. separate table.
- Whether `/search/messages` lives here (thin proxy) or clients query a dedicated search gateway.
- Edit/delete windows and tombstone retention policy (coordinate with Worker retention jobs).
