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
**Produces:** index jobs to `jobs:index` (R3) for Elasticsearch (consumed by Worker) — **not
built; see §5**.
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
| PATCH | `/channels/{id}` | see §3.1.1 | Rename / change topic. Takes `name`, `topic` and a required `version`; **never** `archivedAt`. |
| DELETE | `/channels/{id}` | see §3.1.1 | Archive. Unconditional, no body, **one-way** — see §3.1.1. Returns the archived channel. |
| GET | `/channels/{id}/members` | see §3.1.1 | List members. Ordered by `userId` and keyset-paginated on it. |
| POST | `/channels/{id}/members` | see §3.1.1 | Add **one** member, by id. Already a member → 409. |
| DELETE | `/channels/{id}/members/{userId}` | see §3.1.1 | Remove member. Not a member → 404; the channel's only admin → 409. |
| GET | `/channels/{id}/messages` | see §3.1.1 | History, cursor paginated, newest-first. Includes tombstones. |
| POST | `/channels/{id}/messages` | see §3.1.1 | Send message (REST fallback; prefer the Socket.IO event). |
| GET | `/messages/{id}` | see §3.1.1 | Single message. No thread root — threading is unbuilt (D8a). |
| PATCH | `/messages/{id}` | author only — see §3.1.4 | Edit message. Takes `body` and a required `version`. No time window. |
| DELETE | `/messages/{id}` | author or channel admin — see §3.1.4 | Tombstone the message. Returns **200 with the tombstoned `Message`**, not 204. |
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

**Added 2026-08-16, while building channel administration.** Visibility answers
who may *see* a channel; it did not answer who may *change* one. Two guards, in
this order, on `PATCH`/`DELETE /channels/{id}` and on every `/members` write:

| Caller | Result |
|---|---|
| the channel is not visible (other workspace, archived, private non-member, absent) | **404** `not-found` |
| visible, `myRole` is `null` or `member` | **403** `forbidden` |
| visible, `myRole == "admin"` | proceed |

The order matters more than either rule. Visibility decides the 404 and only
then does the role decide the 403, so a private channel is always "absent"
before it can be "not yours". The 403 that survives is safe on its own terms: it
is reachable only for a channel the caller can already read, where "you are not
an admin of it" discloses nothing new.

**Reading the member list is a visibility test, not a membership test.** This
table marked it "channel member", and applied literally that let Grace see
`#general` in her sidebar, read every word in it, and get a 403 for asking who
else was in it. It widens exactly one case — a public channel, where the
membership is not a secret from a workspace that can already read the
conversation.

**Archiving is one-way.** Every read in the service goes through the visibility
query, which filters `archived_at IS NULL`, so an archived channel is invisible
to everyone including its own admin: there is no `GET /channels?archived=true`,
no restore route, and archiving twice is a 404. Adding either would mean a read
path that sees archived rows. Two consequences worth stating rather than
discovering: the SPA confirms before archiving and navigates away afterwards,
and **the name is not released** — `ux_channels_public_name` covers archived
rows too, so `#general` cannot be created again once it has been archived.

**Nothing joins a channel by itself.** Both member writes require a channel
admin, including when the target is the caller: there is no self-join and no
self-leave in this scope.

**Added 2026-08-16, while building messages. Visibility gates reading *and*
writing; membership gates administration.** This table marked the message rows
"channel member", and read with the two facts above — a public channel is
visible to the whole workspace, and nobody can join a channel by themselves —
that recreates exactly the bug §3.1.1 was added to fix. Ada creates `#general`,
Grace sees it in her sidebar, and can never read a word in it.

| Request | Rule |
|---|---|
| `GET /channels/{id}/messages` | the caller can see the channel |
| `POST /channels/{id}/messages` | the same test. Posting in a public workspace channel needs no membership row |
| `GET /messages/{id}` | the same test, applied to the message's channel |
| a channel the caller cannot see | **404**, and the *message* 404 uses the same wording, so an id cannot be probed |
| an archived channel | unreachable by the same code path, deliberately |

**Posting does not create a membership row.** `myRole` stays `null` for someone
who has spoken in a public channel they never joined, and the admin controls
stay hidden. Whether posting *should* join you is a product question, not
something to settle by accident in a handler.

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

Membership DTOs — **added 2026-08-16**; `POST /channels/{id}/members` had no
request or response body specified at all:

```jsonc
// AddChannelMemberRequest
{ "userId": "uuid", "role": "member" }   // role optional, "member" | "admin", default "member"

// ChannelMember
{ "userId": "uuid", "role": "admin|member", "joinedAt": "..." }

// ChannelMemberListResponse
{ "items": [ /* ChannelMember */ ], "nextCursor": "…|null" }
```

Three things follow from Conventions §2 — **Messaging owns no user records and
must not read Auth's tables**:

- **By id, never by email.** Messaging cannot resolve an address, and it will
  not make a synchronous call to Auth on the path of a channel edit.
- **`userId` is not validated against anything.** A membership row for an id
  that is not a user in this workspace grants nothing — every read still filters
  on the caller's own `wsp` claim, so the row is inert.
- **There is no name here to give.** The SPA resolves ids to display names
  through Auth's own `GET /workspaces/{id}/members`, holding a token that
  already entitles it to both services. Copying a name onto Messaging's rows
  would put a fact Auth owns into Messaging's database, and would go stale the
  moment someone renamed themselves.

Nothing is revoked when a member is removed: channel membership is in no token,
which is the same fact that keeps these routes on plain `require_user`. Contrast
Auth's workspace removal, which must revoke sessions — there is no equivalent
here to write.

`UpdateChannelRequest` carries `version`, `name` and `topic`. An absent `topic`
leaves it alone; an explicit `null` clears it.

`Message` DTO — **replaced 2026-08-16.** The previous shape carried `reactions`
and no `version`, and neither was right for what the service actually is:

```jsonc
{
  "id": "uuid", "channelId": "uuid", "authorId": "uuid",
  "threadRootId": "uuid|null",     // always null in this scope (D8a 🟡)
  "body": "markdown text",         // "" when deletedAt is set — see §3.1.4
  "attachments": [],               // always empty; the Asset service is a skeleton
  "createdAt": "...", "editedAt": "...|null", "deletedAt": "...|null",
  "version": 0
}
```

- **No `reactions`.** The table is not created and no query makes it; a field
  that is always `[]` is a claim the service does not honour. `attachments`
  looks like the same case and is not — it is a real column read off a real row
  that happens to be empty.
- **No `workspaceId`**, for the reason the `Channel` DTO gives.
- **`version` is here**, because a `PATCH` sends it back for optimistic
  concurrency (§4).
- **`authorId` is a bare id.** There is no user expansion — Messaging does not
  read Auth's tables — and the browser resolves the name through Auth's own
  workspace directory.

```jsonc
// MessageListResponse — matches ChannelListResponse
{ "items": [ /* Message */ ], "nextCursor": "…|null" }

// SendMessageRequest — POST /channels/{id}/messages
{ "body": "markdown text" }
```

`SendMessageRequest` carries **no** `channelId` (it is in the path), no
`authorId` (it is the token's `sub`), no `threadRootId` and no `attachmentIds`.
Accepting a field the service ignores is a claim it does not honour; both arrive
with the features that need them.

**Message body rules — added 2026-08-16.** §8 gave one number and no floor, no
layer and no error key:

- **Empty, or nothing but whitespace, is rejected** — 400 `validation-error`,
  `errors: {"body": ["A message cannot be empty."]}`. Emptiness is judged on the
  *stripped* string.
- **The body is stored verbatim and is not trimmed**, unlike a channel name.
  Markdown is whitespace-sensitive: an indented code block and a hard line break
  both mean something.
- **Length is `MESSAGING_MAX_BODY_CHARS` characters of the raw string**, checked
  in the domain so the message can name the limit —
  `errors: {"body": ["A message must be 8000 characters or fewer."]}`.
- The request model also carries a static `max_length` far above the configured
  limit. It exists only to keep an unbounded body out of the domain, and it must
  stay above the setting — otherwise raising `MESSAGING_MAX_BODY_CHARS` would
  silently start reporting a generic error from the wrong layer.

#### 3.1.4 Editing and deleting a message

**Added 2026-08-16.** Register **D8d** is settled — see the
[ADR](../adr/260816-message-edit-and-delete-semantics.md). The doc gave the Auth
column for these two routes and nothing else: no request body, no response, no
statement of what a refusal looks like, and no rule for a message that is
already deleted.

**No time window on either action.** An edit sets `edited_at`, which the UI shows
as an "edited" marker, so a late edit is visible rather than silent — that
visibility is what a window would otherwise have bought, at the cost of a number
nobody could justify.

**Editing is the author's alone; deleting is the author's or a channel admin's.**
The asymmetry is the point: deleting someone's words is moderation, rewriting
them under their name is forgery. No role on this platform can edit a message it
did not write.

##### Outcomes

| Case | Result |
|---|---|
| the message's channel is not visible | **404** `not-found` |
| the message id does not exist | **404** — the same body, deliberately, so an id cannot be probed |
| the channel is archived | **404** — see the freeze below |
| `PATCH`, caller is not the author | **403** `forbidden` |
| `PATCH`, caller is a channel admin but not the author | **403** — admins delete, they do not edit |
| `PATCH`, the message is already deleted | **409** `conflict`, "This message was deleted." |
| `PATCH`, the version does not match | **409** `conflict` |
| `DELETE`, caller is neither the author nor an admin of the channel | **403** `forbidden` |
| `DELETE`, caller is the author or a channel admin | **200** with the tombstone |

**The order is load-bearing.** Visibility, then existence, then state, then
authority. Checking authorship first would answer "you are not the author" for a
message in a private channel the caller has never been in, which tells them the
message is there. `detail` names the rule and never the author.

**403 here, and not the 404 the channel rules use.** A message the caller cannot
see never reaches the authority check; one they *can* see is already on their
screen, so refusing the edit discloses nothing and a 404 would be a lie about a
row they are looking at.

##### The request

```jsonc
// EditMessageRequest — both fields required
{ "body": "the new text",   // the replacement, not a patch of the old one
  "version": 3 }            // a precondition, never an assignment
```

**Not a JSON Merge Patch of `Message`**, despite Conventions §4 defining `PATCH`
that way — under RFC 7386 `{"version": 3}` would mean *assign 3 to version*,
which is the opposite of what it means here. Both fields are required: there is
exactly one editable field on a message, so "absent means leave it alone" has
nothing to express. The body is held to the same rules a send is (§3.1.3).

##### Tombstones in history

| Row state | `body` | `editedAt` | `deletedAt` |
|---|---|---|---|
| live | the text | `null`, or when last edited | `null` |
| deleted | **`""`** — empty string, never `null`, never the original text | unchanged | the delete time |

The redaction is **server-side**, in the response mapper, so the text cannot
reach a client whatever the column holds. The client renders "This message was
deleted" from `deletedAt`, not from an empty body — and shows **no** edited
marker on a deleted row even when `editedAt` is set, because "This message was
deleted (edited)" is not something anyone needs to read.

`DELETE` returns **200 with the tombstone rather than 204**, and that is a
deliberate deviation from the platform habit. A delete here does not remove a row
from the list, so the client has to draw something; with 204 it would have to
refetch a page it is already holding to learn what.

**Deleting twice is a no-op.** The second call returns the same tombstone — same
timestamp, same version. The first delete bumps `version`; a repeat does not,
because the Elasticsearch external version should not move for a document that
did not change.

**The stored `body` is never cleared.** The `UPDATE` sets `deleted_at` and
`version` and touches nothing else. Blanking the column looks tidy, changes
nothing a client can see, and destroys data silently — and hard deletion belongs
to a retention job whose window is **D16, still 🔴**. Nothing in this scope
deletes a tombstone.

##### Archiving a channel freezes its messages, permanently

Every message route goes through the channel visibility query, which filters
`archived_at IS NULL`. So once a channel is archived, **nobody can edit or delete
anything in it — not the author, not an admin — and the attempt returns 404.**

That is the right default for an archive, and there is no remedy in this scope:
archiving is one-way (§3.1.1), so there is no unarchive route to point anyone at.
Stated here rather than left to become a support ticket.

#### 3.1.5 Not built in this scope — added 2026-08-16

The table in §3.1 is the eventual surface. These rows have no implementation
after the messaging core slices, and are listed here so a reader consulting the
design doc — rather than a plan or a service README — knows which is which.

| Row | Why it is not built | Register |
|---|---|---|
| `GET /messages/{id}/thread` | threading is unbuilt; `thread_root_id` ships as a column and is always `null` | D8a 🟡 |
| `POST` / `DELETE /messages/{id}/reactions*` | the `reactions` table is not created — an empty table claims a capability the service does not have | — |
| `POST /channels/{id}/read` | `last_read_id` shipped with `channel_members` in `0001_channels`; nothing writes it | — |
| `GET /search/messages` | there is no Elasticsearch path at all, and no `jobs:index` producer to feed one (§5) | D8c 🟡 |
| `POST /internal/messages/sweep` | retention values are unset, and nothing hard-deletes a message | D16 🔴 |

Two things the *columns* do ship for, ahead of their features, because adding a
column later rewrites a table and adding an index or a route later does not:
`thread_root_id` and `attachments` on `messages`, and `last_read_id` on
`channel_members`.

### 3.2 Socket.IO namespace — `/messaging`

Real-time runs on the Socket.IO `/messaging` namespace (Conventions §6). Client→server
events are verbs; server→client events are past-tense facts. `send_message` returns the
created `Message` via the Socket.IO acknowledgement callback.

**Client → Server**

| Event | Args | Effect |
|--------|------|--------|
| `join_channel` | channelId | Authorize + join room `channel:{id}`. |
| `leave_channel` | channelId | Leave room. |
| `send_message` | `{ channelId, body }` — **narrowed 2026-08-16** | Persist + broadcast. Acks the created `Message`. |
| `edit_message` | `{ messageId, body, version }` — **`version` added 2026-08-16** | Author-only edit + broadcast. Acks the edited `Message`. |
| `delete_message` | `{ messageId }` | Author/channel-admin delete + broadcast. Acks the **tombstoned `Message`**. |
| `add_reaction` / `remove_reaction` | `{ messageId, emoji }` | Broadcast reaction change. |
| `mark_read` | `{ channelId, messageId }` | Update read receipt; broadcast to user's other sessions. |
| `typing` | `{ channelId }` | Ephemeral; fan out `user_typing` (not persisted). |

**Server → Client (events)**

| Event | Payload |
|-------|---------|
| `message_received` | `Message` |
| `message_edited` | `Message` |
| `message_deleted` | `Message`, redacted — **corrected 2026-08-16**, see below |
| `reaction_changed` | `{ messageId, emoji, count, userId, added }` |
| `read_receipt_updated` | `{ channelId, userId, messageId }` |
| `user_typing` | `{ channelId, userId }` — see §3.2.4 |

Rooms and naming follow Conventions §6. Presence (online/away) is published to R2 and
mirrored to the Canvas service's presence as needed (shared R2).

#### 3.2.1 How the namespace is built — added 2026-08-16

**The R2 backplane names its own channel: `AsyncRedisManager(url,
channel="messaging")`.** The constructor defaults to `channel="socketio"`, and
Canvas puts its backplane on the same R2 instance (doc 03 §4.1) — so two
services on the default would deliver every Canvas emit into this process to be
re-dispatched against these rooms. `doc:{id}` does not match `channel:{id}`
today, so nothing visibly breaks, which is exactly what makes it worth fixing
now: it becomes a cross-service leak the first time either service names a room
the other could name too. **Canvas needs the same change** and is told rather
than edited from here. The general rule is in Conventions §6.

**`cors_allowed_origins` is passed as `settings.cors_allowed_origins or None`.**
Conventions §5.6 makes an empty list mean "install no CORS at all" — a service
behind one ingress shares its SPA's origin. engine.io reads an empty list as an
allow-list containing nothing and refuses every browser handshake with a 400.
`None` is its spelling of "same origin only". The bug would only appear in the
deployment the convention was written for.

**The Socket.IO ASGI app wraps FastAPI and must be constructed with
`other_asgi_app` alone.** `ASGIApp` handles the `lifespan` scope itself and only
delegates it down when it was given neither `on_startup` nor `on_shutdown`, so
adding either would silently stop the FastAPI lifespan running and leak a
connection pool per process with no error anywhere. Everything that is not the
engine.io path falls through, so `/health/live` still answers through the
wrapper.

#### 3.2.2 The handshake — added 2026-08-16

The token comes from the handshake `auth` payload, falling back to an
`access_token` query parameter (Conventions §6); the fallback is second because
a query string ends up in access logs. It is verified with the same core
`require_user` uses, with **`sensitive=False`** — channel membership is not
workspace membership, so none of this surface is in Conventions §5.2's
fail-closed set, and an unreachable R1 accepts the connection exactly as it
accepts a `GET /channels`.

A refused handshake raises `ConnectionRefusedError`, which reaches the browser
as `connect_error`. **The SPA stops on `connect_error` rather than retrying:** a
handshake the server refused because a token is expired or denied will be
refused identically on every retry, and Socket.IO's backoff would hide that
behind a spinner forever. A dropped *transport* keeps the built-in backoff.

**The connection keeps the workspace of the token that opened it** (Conventions
§5.4). No handler reads a workspace from an event payload, for the same reason
no router reads one from a path.

**A connection is verified once, and mid-connection revocation is deliberately
not built.** An access token lives fifteen minutes and a connection can outlive
it, so a revoked user keeps receiving broadcasts until their client reconnects.
Closing that would need either a denylist round trip per emit — on the hot path,
per recipient — or an R2 fan-out of revocations, and the SPA re-establishes the
socket whenever the access token changes, which it does about a minute before
every expiry. The exposure is bounded by one token lifetime on a connection the
client re-opens on that cadence anyway.

**Known limitation: removing someone from a private channel does not evict their
live socket** from `channel:{id}`, so they keep receiving its broadcasts until
they next reconnect. Accepted rather than fixed: evicting a live connection needs
a registry of sids per user or a re-authorization on every publish, and the
exposure is one already-authorized session on one private channel. Public
channels are workspace-visible anyway, so there is nothing to revoke there. The
mitigation that already exists is that `join_channel` re-authorizes, so a
reconnect drops them.

#### 3.2.3 Rooms, acks and payloads — added 2026-08-16

**`join_channel` authorizes on channel *visibility*, not membership** — the room
mirrors the read rule in §3.1.1. A channel the caller cannot see acks a **404**
and never a 403. `leave_channel` needs no authorization: leaving a room you
should not be in is the correct outcome.

**The acknowledgement envelope**, which no document previously defined:

```jsonc
{ "ok": true,  "data": { /* the Message DTO, or absent */ } }
{ "ok": false, "problem": { /* the RFC 7807 body, verbatim */ } }
```

`problem` carries the same Problem Details document a REST call would have
returned (Conventions §4.2), so the platform has one error vocabulary rather
than one for HTTP and another for sockets — minus `instance` and `traceId`,
which a socket handler has nothing to derive from and must not invent.
**Handlers never raise:** a raising Socket.IO handler drops the client's
callback and the browser waits forever.

**Every message payload is `MessageResponse.model_dump(mode="json",
by_alias=True)`** — byte for byte the camelCase shape the REST route returns.
The SPA writes socket events and REST responses into the same cache entry and
reads both through one generated type, so two casings would be a render bug per
message rather than a caught error.

**`message_deleted` carries the full redacted `Message`, not
`{messageId, channelId}`.** A delete is a state transition of a row that stays
in the history (§3.1.4), so a client holding only an id could do nothing but
remove the row — the behaviour the tombstone exists to prevent — or refetch,
which defeats the point of the event.

**Reconnecting re-joins the room but replays nothing.** python-socketio has no
connection-state recovery, so everything broadcast while a client was away went
to a room it was not in and is gone. **Every connect therefore both re-joins the
active channel and refetches its history**; the refetch is the recovery and the
re-join only resumes the live stream from that point.

#### 3.2.4 The write path — added 2026-08-16

**`send_message` takes `{ channelId, body }` and nothing else.** The two
optional fields this table used to list are out of scope: `threadRootId` has a
column and no API (D8a), and `attachmentIds` would go to a service that is a
skeleton. Accepting a field the handler drops on the floor is a claim the
service does not honour; both return with the features that need them.

**`edit_message` carries `version`, which this table omitted.** The expected
version is required on `PATCH /messages/{id}` (§4), and an event without one
would make the socket the way to lose someone else's edit silently. One rule,
two transports. `delete_message` stays unconditional, matching `DELETE`.

**A write is authorized on channel *visibility*, not on room membership.** A
room is per-`sid` in-memory state that a reconnect destroys and the client
re-establishes, so a send across a reconnect would race its own `join_channel`
and fail for a reason no user could act on — and gating on membership would make
the socket stricter than the REST route it replaces, resurrecting the bug
§3.1.1 closed. A room decides who *receives* a broadcast and nothing else. The
sender gets their ack whether or not they are in the room.

**Every inbound write re-checks the token.** The handshake authenticates the
connection once, and a connection outlives its fifteen-minute token. That was
tolerable while the socket could only read:

| Check | When | On failure |
|---|---|---|
| the principal has not expired | every inbound event, **including `typing`** | `unauthorized` ack, 401 |
| the token is not on the denylist | the three write events only | revoked → 401 · unreachable R1 → **proceed** |

The denylist **fails open** here, matching §3.1: channel writes are outside
Conventions §5.2's fail-closed set. `typing` skips it because it persists
nothing and one Redis round trip per throttle window is real load for no
authority gained. **The server does not disconnect the socket itself** — acking
and then disconnecting in the same handler races the ack's own flush; the client
tears the connection down when it sees a 401 and reconnects with a fresh token.

**`typing` and `user_typing` — the payload is unchanged, the behaviour is
this.** There is no `typing_stopped` event and there is not meant to be one: a
server tracking who is typing would need that state shared across pods through
R2 for something this document calls ephemeral, and would still have to invent a
timeout for the client that closed its laptop mid-word. So:

- the client throttles `typing` on the **leading edge**, one emit per 2s window,
  because a trailing debounce would delay the indicator by its own window;
- the receiver drops a user 4s after their last `user_typing` — two missed
  windows;
- fan-out uses `skip_sid`, so a sender never sees their own indicator, **and**
  the client discards any `user_typing` carrying its own `userId`, which also
  covers that person's second tab;
- the payload carries **no display name**. Messaging holds none, and the browser
  already has the workspace directory it resolves every other name from. Two
  sources for one name is drift, even for an event that cannot go stale.

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

-- `version` and `updated_at`, added 2026-08-16 while building the writes.
--
-- `version` is optimistic concurrency, not a decoration. Every update is
-- guarded — `WHERE id = :id AND version = :expected`, zero rows affected → 409
-- `conflict` — and bumps the column. The expected version travels in the
-- request body as `version`, not in an `If-Match` header: nothing on this
-- platform emits or parses an ETag, and the DTO already carries the number the
-- client holds. `DELETE` is the exception and is unconditional; it still bumps,
-- because the Elasticsearch external version (register D25) depends on it.
--
-- **The version check is not the existence check.** A zero-row update means
-- either a stale version or a row that is not there, so the order is fixed:
-- visibility (404), then role (403), then the guarded update (409). Answering
-- 409 for a channel in another workspace would confirm it exists.
--
-- `updated_at` has a `server_default` and deliberately no `onupdate` — an
-- `onupdate` fires on any flush, including ones nobody asked for — so every
-- update in the service sets it explicitly. Miss it and the column reads as the
-- creation time forever.

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
-- Corrected 2026-08-16, when `0002_messages` was written. The predicate this
-- index used to carry — `WHERE deleted_at IS NULL` — is wrong for this service:
-- history returns tombstones, so the query has no such clause and would not
-- match a partial index. The failure mode is a full scan on a busy channel,
-- which no test that only checks results would catch.
CREATE INDEX ix_messages_channel_time ON messages (channel_id, id DESC);

-- Still the eventual shape, and deliberately **not created yet**: nothing
-- queries `thread_root_id` in this scope. A *column* ships ahead of its feature
-- because adding one later rewrites the table; an index does not, so it waits.
-- Same reasoning leaves `reactions` below uncreated.
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

**`messages` is the other exception, and it runs the opposite way.** The table
*has* `deleted_at`, and the read path deliberately does **not** filter it: a
deleted message stays in history as a tombstone with its `body` redacted to `""`
server-side, so the conversation around it still makes sense and a reload does
not bring the words back. Two exceptions to one Conventions §3 rule in one
service is worth stating plainly: the rule is "filter the soft-delete column
unless this document says otherwise", and both places it says otherwise are
here.

Threading is single-level: a reply sets `thread_root_id` to the top-level message; replies to
replies still point at the root. Read state is a per-member pointer (`last_read_id`); unread
counts are derived (messages with `id > last_read_id`).

### 4.1 Redis usage
- **R1:** cache channel membership sets and recent-message windows for fast event authorization.
- **R2:** Socket.IO Redis manager (backplane) + presence pub/sub. **On the pub/sub
  channel `messaging`, not the `AsyncRedisManager` default** — Canvas shares this
  Redis instance and would otherwise share the channel name too (§3.2.1,
  Conventions §6).
- **R3:** `jobs:index` — one job per created/edited/deleted message for ES sync. The payload
  carries the whole document (§5), so these entries contain user-authored message bodies —
  see the retention and trimming note in Worker doc §8. **The producer is not built; see §5.**

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

**Step 4 is not built — noted 2026-08-16.** The step stays above as the eventual
shape, in the same way §4 keeps `ix_messages_thread` in the DDL. Three reasons,
and the third is the one that makes the omission safe rather than merely
convenient:

- **Nothing consumes the stream.** The Worker is scaffold and search is out of
  scope, so a producer would fill R3 with entries no reader ever trims — which
  Worker doc §8 already warns about, for a stream that would contain
  user-authored message bodies.
- **A stream nobody reads is a claim the service does not honour.** Same
  reasoning that leaves `reactions` uncreated and `ix_messages_thread` unbuilt.
- **Adding it later is purely additive.** The `version` column it needs already
  ships, and earns its place on optimistic-concurrency merit alone (Conventions
  §3) — so this is one `XADD` in one place when the Worker exists, with no
  schema change and no migration.

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
- ~~Edit/delete windows and tombstone retention policy.~~ **Settled 2026-08-16
  (register D8d 🟢)** — no time window, author edits own, author or channel admin
  deletes, tombstones retained in history. See §3.1.4 and the
  [ADR](../adr/260816-message-edit-and-delete-semantics.md). **How long a
  tombstone is kept before hard deletion is still D16 🔴** and nothing here
  deletes one.
