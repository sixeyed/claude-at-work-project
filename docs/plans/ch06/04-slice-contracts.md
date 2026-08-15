# Slice contracts: the seams between Slices 2 and 7

## Context

[`02-messaging-core-delivery-plan.md`](./02-messaging-core-delivery-plan.md) describes seven
slices in a paragraph each, and [`03-slice-01-implementation-plan.md`](./03-slice-01-implementation-plan.md)
showed what happens when one of those paragraphs is validated properly: nine gaps, two of them
corrections to the design docs themselves. Slices 2 to 7 are now being planned **in parallel**,
one agent per slice, and six agents working blind will close the same gap six different ways
wherever two slices touch the same file, table, DTO or doc section.

This document is the answer to that. It is not a summary of the delivery plan — it is a set of
**rulings**, each naming the one slice that owns the thing. Where the delivery plan already
recommends an answer it is confirmed or overturned here, once, and said which. Where nothing
does, the call is made here with the reason.

**Binding on every slice plan.** A plan that touches something ruled on below follows the ruling
and cites it; it does not re-decide it. Anything not ruled on, and which would constrain another
slice, is a **Contract question** in that plan — with a recommendation, never a silent answer.

Thirteen rulings: eleven seams identified before the fan-out, plus two more that freezing the
first eleven exposed.

---

> **Amended 2026-08-15, after the planners returned.** Six plans came back having found 55 gaps
> between them and having raised nine **Contract questions** — seams the thirteen rulings below
> did not reach. Two of those questions were asked by two slices each, with *different* answers,
> which is precisely the divergence this document exists to prevent. The rulings are 14 to 21, at
> the foot of this file. Nothing above is rewritten: where 14–21 change an earlier ruling they say
> so and the original stands as the record of what the planners were working from.
>
> - **14** — display names for a bare user id · **15** — the Socket.IO ack envelope · **16** —
>   `shared/problems.py` joins S5's `shared` extraction · **17** — amends ruling 7: the cache
>   helper upserts, it does not append · **18** — socket payloads carry `version` and the full
>   `Message` · **19** — ownership ruling 9 left unassigned · **20** — a member removed while
>   their socket is live · **21** — `messages.validate_body` is a named function.
>
> **Amended again after review.** Three reviewers — seams, fidelity, executability — read the six
> plans and this document. Their findings produced rulings **22–24** and corrected six factual
> errors in the rulings above, which have been fixed in place rather than annotated: a `pytest.ini`
> that does not exist (it is the root `pyproject.toml`), a `features/chat` claim about the delivery
> plan that was not true of any slice paragraph, `validate_body`'s missing `max_chars`, and three
> mis-attributions of which planner said what.

---

## 1. Tombstones and the messages index

Delivery plan **decision 1** proposes that history returns soft-deleted rows with `body` redacted
and `deletedAt` set, and that `ix_messages_channel_time` is therefore created **without** the
`WHERE deleted_at IS NULL` predicate that doc 02 §4 and the strategy plan both give it.

**Confirmed, as recommended.** A tombstone that a reload erases is not a tombstone, and the
Gherkin already says "a tombstone remains after reload". This is a documented, message-specific
exception to CLAUDE.md's blanket "queries filter `deleted_at IS NULL`" — the same shape of
exception `channels`/`archived_at` already carries (doc 02 §4).

The redaction is **server-side**, and the wire shape is fixed here so three slices cannot invent
three of them:

| Row state | `body` | `editedAt` | `deletedAt` |
|---|---|---|---|
| live | the text | `null`, or when last edited | `null` |
| deleted | **`""`** — empty string, never `null`, never the original text | unchanged | the delete time |

`body` stays a non-null string because the DTO types it that way and the generated TypeScript
client would otherwise force a null check at every render site. The client renders "This message
was deleted" from `deletedAt`, not from an empty body.

**Ownership.** The read path ships **complete in S3**: `history_page` and `get` do **not** filter
`deleted_at`, and the response mapper already redacts a deleted row — even though nothing in S3
can set `deleted_at` yet. That costs S3 four lines and means S4 changes no read path at all, only
adds the writes. **S4** owns the semantics (`PATCH`/`DELETE`), the D8d ADR and the register flip
(ruling 9). **S7** does not re-record it.

The index, in S3's migration:

```sql
-- No `WHERE deleted_at IS NULL`: history returns tombstones, so the read path
-- would not match a partial index (delivery plan decision 1).
CREATE INDEX ix_messages_channel_time ON messages (channel_id, id DESC);
```

**Doc 02 §4 currently gives the partial form and must be corrected — S3 owns that edit.**

---

## 2. Migration ownership

**Confirmed** from delivery plan decision 2, with two corrections.

- `0002_messages` lands in **S3**. **No other slice adds a migration** — not S2, not S4, not S5,
  not S6. If a planner believes its slice needs a schema change, that is a **Contract question**,
  not a second revision file.
- Columns whose features arrive later ship with their table: `thread_root_id`, `attachments`,
  `edited_at`, `deleted_at`, `version`. A column is cheap now and an `ALTER` later; that is the
  churn this rule exists to avoid.
- **`last_read_id` already shipped**, in `0001_channels` on `channel_members`
  (`alembic/versions/0001_channels.py:87`). The delivery plan lists it as a later-feature column
  as though it were still to come. It is not.
- `reactions` is **not created**.
- **`ix_messages_thread` is not created either** — overturning doc 02 §4, which lists it. The line
  is the one `0001_channels` already drew and stated in its docstring: *columns* ship ahead of
  their feature because adding one later churns the table, but an *index* supporting a query no
  code makes is dead weight, and adding it later is a one-line migration with no table rewrite.
  Same reasoning that leaves `reactions` uncreated. S3 notes the omission in the migration
  docstring and leaves doc 02 §4's DDL as the eventual shape.

`messages.channel_id` keeps its foreign key to `channels.id` — same database, same service, and
`0001` set the precedent with `channel_members`. `author_id` carries none: it names a row in
Auth's database (Conventions §2).

---

## 3. Optimistic concurrency

**S2 defines the pattern. S4 applies it to messages by citation, not by restating it.** The shape,
once:

```python
result = await session.execute(
    update(Channel)
    .where(Channel.id == channel_id, Channel.version == expected_version)
    .values(name=name, version=Channel.version + 1, updated_at=func.now())
)
if result.rowcount == 0:
    raise VersionConflictError(channel_id)
```

- The domain exception is **`VersionConflictError`**, defined in `messaging/channels.py` by S2 and
  imported by `messaging/messages.py` in S4 — one exception, not two identically-named ones.
- The router translates it to `ProblemException.conflict(...)` → 409, problem type `conflict`
  (Conventions §4.2). The `IntegrityError` → 409 path that `channels.create` already uses for
  duplicate names is a *different* conflict with a different `detail`; both are 409 and that is
  correct.
- **The expected version travels in the request body as `version`**, on `PATCH /channels/{id}` and
  `PATCH /messages/{id}`, and it is **required** there. Not an `If-Match` header: nothing on this
  platform emits or parses an ETag, the `Channel` DTO already carries `version`
  (`schemas.py:58`), and the SPA holds the row it is editing in the TanStack cache, so it has the
  number. A header would be new machinery for the same guarantee.
- **`DELETE` is unconditional** — no body, no expected version. It still bumps `version`, because
  doc 02 §4 says `version` bumps on edit *and* delete and the Elasticsearch external version
  (D25 🟢) depends on it. Deleting a row someone else just edited is not a conflict worth
  surfacing; deleting it twice is idempotent.
- 409 is covered at **integration level, never in Gherkin** — the delivery plan already says this
  for S2 and it holds for S4 too. Two browsers racing a PATCH is not a scenario anyone can write
  honestly.

---

## 4. `shared/security.py` and the ASGI entry point

**S5 owns both. S6 consumes them and must not respecify them.**

**The extraction.** `RequireUser.__call__` (`shared/security.py:166`) does its work through
`Request`-bound helpers, so the Socket.IO handshake — which has a token and no `Request` — cannot
reuse it. S5 extracts two request-free functions and rewrites the existing ones to call them:

```python
async def decode_claims(context: SecurityContext, token: str, *, audience: str) -> dict[str, Any]
async def verify_user_token(context: SecurityContext, token: str, *, sensitive: bool = False) -> UserPrincipal
```

`_verified_claims(request, audience=...)` becomes `_context(request)` + `_bearer_token(request)` +
`decode_claims`. `RequireUser.__call__` becomes `_context(request)` + `_bearer_token(request)` +
`verify_user_token`. Behaviour is unchanged and the existing tests must stay green untouched —
that is the evidence the extraction was faithful.

**`SecurityContext` is not currently exported** from `shared/__init__.py` (its `__all__` lists
`SecurityConfig` but not `SecurityContext`). S5 adds both `SecurityContext` and
`verify_user_token` to `__all__`; the handshake needs the type to name what it holds.

**The entry point.** `messaging/main.py` today ships `create_app(settings, *, key_source=None)
-> FastAPI` and `app_factory()`, and `docker/messaging/Dockerfile` runs
`uvicorn messaging.main:app_factory --factory`. S5:

- keeps `create_app` returning a `FastAPI`, unchanged in signature, so every integration test
  keeps driving it over `httpx.ASGITransport` and `messaging/openapi.py` keeps working with no
  running stack;
- adds `build_asgi_app(settings, *, key_source=None)` returning
  `socketio.ASGIApp(sio, other_asgi_app=create_app(...))`;
- **replaces `app_factory` with `asgi_factory`** and changes the Dockerfile `CMD` in the same
  change. One factory, not one live and one dead. `/health/live` still resolves through the
  wrapper, so the Compose healthcheck is unchanged — S5 verifies that rather than assuming it.

**Wiring the server to the REST routers.** `create_app` sets `app.state.realtime = None`;
`build_asgi_app` constructs the `AsyncServer` and overwrites it. The publishers S5 adds to the
REST routers read `request.app.state.realtime` and **no-op when it is `None`**, so an
`ASGITransport` test exercises the same router code with no socket server behind it. S5 states
this once in `realtime.py`'s docstring.

---

## 5. The `realtime.py` split

Two modules, not one file two slices edit:

| Slice | File | Contents |
|---|---|---|
| **S5** | `messaging/realtime.py` | `build_server(settings, sessions)`; handshake auth in `connect` (token from the handshake `auth` payload, `access_token` query as fallback per Conventions §6) via `verify_user_token`; principal in the Socket.IO session; `disconnect`; `join_channel` / `leave_channel` authorizing against Postgres and joining room `channel:{id}`; the outbound publishers `publish_message_received` / `_edited` / `_deleted` that the REST routers call after commit |
| **S6** | `messaging/realtime_writes.py` | inbound `send_message` / `edit_message` / `delete_message` with acks; `typing` → `user_typing` fan-out |

S6's module exposes `register_write_handlers(sio, ...)` and S6 adds the one line calling it from
`build_asgi_app`. Editing one line of a file S5 created is fine — the slices are *built* in order;
only the planning is parallel.

Tests divide the same way: **S5 writes `tests/test_realtime.py`** (handshake accept/reject, join
and leave, and a REST write broadcasting to a joined client) and **S6 writes
`tests/test_realtime_writes.py`** (the inbound events, their acks, their rejections, and typing).
Neither slice edits the other's test module. Both use `socketio.AsyncSimpleClient` against uvicorn
on an ephemeral port with the real Postgres and Redis containers `tests/conftest.py` already
provides.

The Socket.IO server uses **R2 only** — `AsyncRedisManager(settings.redis_realtime_url)`. Never R1
(cache and denylist), never R3 (job streams).

---

## 6. BDD harness growth

`tests/bdd/conftest.py:60` currently truncates `MESSAGING_TABLES = "channel_members, channels"`.
**S3 changes it to `"messages, channel_members, channels"`** — child table first, because
`messages.channel_id` references `channels.id`. No other slice touches that constant.

| Slice | Feature file | Step module | Page object |
|---|---|---|---|
| S2 | extends `channels.feature` · new `permissions.feature` | extends `steps/test_channel_steps.py` · new `steps/test_permission_steps.py` | new methods on `pages/chat_page.py` |
| S3 | new `messages.feature` | new `steps/test_message_steps.py` | new methods on `pages/chat_page.py` |
| S4 | extends `messages.feature` | extends `steps/test_message_steps.py` | new methods on `pages/chat_page.py` |
| S5 | new `realtime.feature` | new `steps/test_realtime_steps.py` | new methods on `pages/chat_page.py` |
| S6 | extends `realtime.feature` | extends `steps/test_realtime_steps.py` | new methods on `pages/chat_page.py` |
| S7 | — | — | — |

Rules that hold throughout:

- **Step modules must be named `test_*.py`.** `scenarios()` generates one test function per
  scenario into the module that calls it; a module pytest does not collect is a feature file that
  silently never runs. This has already bitten once.
- **`scenarios("../features/X.feature")` is called in exactly one module.** Two modules pointing
  at one feature file run every scenario twice.
- **One page object for the chat shell.** Messages, the composer, the member panel and the typing
  indicator are all part of the same page — they get methods on `pages/chat_page.py`, not a
  second page object splitting the selectors for one screen across two files. A new page object is
  for a genuinely different page, as `sign_in_page.py` is.
- **Selectors are `data-testid` only, owned by page objects.** No raw locator in a step
  definition, ever.
- **Everything stays synchronous.** The root `pyproject.toml` sets `asyncio_mode = "auto"` under
  `[tool.pytest.ini_options]` — there is no `pytest.ini` in this repo — so an
  `async def` step is collected as an asyncio test and Playwright's sync API cannot run inside a
  live loop. Async work goes through the existing `_run_off_loop` helper.
- **Fixtures.** `ada` / `grace` (`ChatPage` per user, separate long-lived signed-in contexts) and
  `reset_messaging` already exist and cover every slice. **No slice adds a session-scoped fixture
  that signs a third user in** — that is a Contract question, not a local decision. S5 needs to
  drop and restore the network for its reconnect scenario: that goes on `ChatPage` as
  `go_offline()` / `go_online()` wrapping `self.page.context.set_offline(...)`, keeping the
  Playwright API inside the page object like every selector.
- **Never truncate Auth's tables.** The sessions the browser contexts hold live there.

---

## 7. Frontend seams

- **Feature folder is `features/channels/`**, never `features/chat/` (doc 06 §3). Slice 1 already
  moved it. The delivery plan says `features/chat` once, in **Slice 1's** frontend bullet
  (`02-messaging-core-delivery-plan.md:156`), and its own amendment at line 31 already corrects it —
  no later slice paragraph repeats it, so nothing here is left to fix.
- **Message query keys are defined in S3**, in `src/frontend/src/features/channels/useMessages.ts`,
  mirroring `channelKeys` in `useChannels.ts:16`:

  ```ts
  export const messageKeys = {
    list: (workspaceId: string | null, channelId: string | undefined) =>
      ['messages', workspaceId, channelId] as const,
  }
  ```

  The workspace id leads every key for the reason `useChannels.ts` gives: a token is scoped to one
  workspace, so a switch reads a different cache entry rather than relying on a lifecycle hook
  somebody could forget.
- **S5's socket handlers write into that cache with `queryClient.setQueryData`** — they do not
  define a second key, and they do not invalidate-and-refetch on every inbound event. History is
  a `useInfiniteQuery`, so the cached value is `{ pages, pageParams }` and a handler that sets a
  bare array silently breaks the query. **S3 exports a helper from `useMessages.ts` that inserts,
  replaces or removes one message in the infinite-query shape**, and S5 calls it. This is the seam
  most likely to be got wrong twice.
- **There is never a second copy of the message list in Zustand** (D24 🟢). `stores/chat.ts` holds
  `activeChannelId` and `drafts` today; **S5 adds `connectionStatus`** and nothing else. No slice
  adds anything server-shaped to that store.
- Component ownership: **S3** `MessageList.tsx`, `MessageItem.tsx`, `MessageComposer.tsx`,
  `useMessages.ts` · **S4** the edit affordance and tombstone rendering *inside* `MessageItem.tsx`
  plus any new `MessageEditor.tsx` · **S5** `lib/realtime/socket.ts`,
  `lib/realtime/useChannelSocket.ts` · **S6** `TypingIndicator.tsx`, and the change of send from
  REST to socket emit inside `useMessages.ts`.
- **S6 keeps `POST /channels/{id}/messages` alive.** Doc 02 §3.1 documents it as the REST
  fallback; moving the SPA onto the socket does not delete the route or its tests.
- **Light palette only, no user preferences** (D28 🔴, doc 06 §2). No slice adds a theme toggle, a
  notification setting or any other stored per-user choice.

---

## 8. OpenAPI regeneration

Any slice that adds or changes a route, a request body or a response model regenerates the
committed document and the generated types (D23 🟡, honoured):

```bash
uv run python -m messaging.openapi > src/frontend/openapi/messaging.json
cd src/frontend && npm run generate:api        # → src/types/messaging.ts
```

That is **S2, S3 and S4**. S5 and S6 add no REST surface, so they regenerate nothing — if a
planner finds its slice changing a response model, it regenerates and says so. Both commands go
in each affected plan's Verification block; the reason for them stays here.

Types are never hand-written. `src/types/messaging.ts` is generated output — no slice edits it.

---

## 9. Design-doc writeback ownership

Exactly one slice owns each section, so two plans cannot both claim to rewrite it. Within doc 02
§3.1's endpoint table, ownership is **per row**.

| Section | Owner |
|---|---|
| 02 §3.1 table — `PATCH`/`DELETE /channels/{id}`, `/channels/{id}/members*` rows | S2 |
| 02 §3.1 table — `/channels/{id}/messages`, `GET /messages/{id}` rows | S3 |
| 02 §3.1 table — `PATCH`/`DELETE /messages/{id}` rows | S4 |
| 02 §3.1.1 channel visibility — private and archived rules | S2 |
| 02 §3.1.1 — the message read/write rule (ruling 12) | S3 |
| 02 §3.1.2 channel names | **nobody** — settled and written back in S1 |
| 02 §3.1.3 DTOs — `Channel` | **nobody** — settled in S1 |
| 02 §3.1.3 DTOs — `Message` (ruling 13) | S3 |
| new 02 §3.1.4 tombstones in history (ruling 1) | S4 |
| 02 §3.2 — handshake, rooms, server→client events | S5 |
| 02 §3.2 — client→server `send_message`/`edit_message`/`delete_message`/`typing` | S6 |
| 02 §4 — `messages` DDL and its indexes (rulings 1, 2) | S3 |
| 02 §4 — the `version` / optimistic-concurrency note (ruling 3) | S2 |
| 02 §5 — why the `jobs:index` producer is deliberately absent | S7 |
| 02 §9 — strike the edit/delete-window line | S4 |
| 06 §5.2 — history load, `join_channel`, inbound event handling | S5 |
| 06 §5.2 — optimistic send, `typing` debounce | S6 |
| 07 register — **D8d → 🟢** | S4 |
| 07 register — confirm D16 🔴, D28 🔴, D8a/D8b/D8c 🟡 unchanged | S7 |
| `docs/adr/` — the D8d ADR (`adr-writer` skill) | S4 |
| READMEs: root, `src/frontend`, `src/services/messaging` | S7 |
| `.env.example` | the slice that introduces a variable; none is expected |

**D8d flips in S4, not S7** — CLAUDE.md says a decision is recorded in the slice that makes it,
and a register reading 🔴 for something three slices are already built on is exactly the drift S7
exists to prevent. **S7 keeps the sweep**, and re-recording a decision an earlier slice already
recorded is a mistake, not thoroughness.

**Only S7 amends [`02-messaging-core-delivery-plan.md`](./02-messaging-core-delivery-plan.md)**,
in one dated amendment blockquote covering all six slices. Every other slice records its
corrections in its own plan's "Gaps closed" and leaves the delivery plan alone.

---

## 10. Open decisions in play

| ID | Status | What it means for these slices |
|---|---|---|
| **D8d** edit/delete windows, tombstone retention | 🔴 → **S4 settles it** | No time window · author edits own · author or channel admin deletes · tombstones retained in history (ruling 1). ADR + register flip in S4 |
| **D16** retention values | 🔴 **stays open** | Nothing in scope depends on it. `POST /api/v1/internal/messages/sweep` is not built; no slice writes a retention job or picks a number |
| **D8b** DM modelling | 🟡 unchanged | `kind='dm'` remains **rejected** by `POST /channels` (`CREATABLE_KINDS`, `models.py:42`). No slice creates or lists DMs |
| **D8a** threading depth | 🟡 unchanged | `thread_root_id` ships as a column in S3 and is exposed on the `Message` DTO as `null`; no thread API, no `GET /messages/{id}/thread` |
| **D8c** search proxy | 🟡 unchanged | Out of scope. No `/search/messages`, no `jobs:index` producer |
| **D23** generated typed clients | 🟡, implemented | Ruling 8 |
| **D28** user preferences | 🔴 **stays open** | No stored per-user choice anywhere: no theme, no locale, no notification setting. Light palette only |

**The standing rule: a planner that hits a 🔴 records it as a bolded Contract question with a
recommendation, and repeats it in its return message. It does not pick an answer.** A 🔴 whose
answer would change something Slice 1 has already shipped goes to the user, not to the
coordinator.

---

## 11. Branch names

One branch per slice. Per CLAUDE.md: create the branch, leave the tree dirty, **never commit**.

| Slice | Branch |
|---|---|
| 2 — Channel administration and membership | `feature/messaging-s2-admin` |
| 3 — Messages: send and read history | `feature/messaging-s3-messages` |
| 4 — Messages: edit and delete | `feature/messaging-s4-edit-delete` |
| 5 — Real-time delivery (broadcast only) | `feature/messaging-s5-realtime` |
| 6 — Socket write path, optimistic send, typing | `feature/messaging-s6-socket-write` |
| 7 — Record the decisions | `feature/messaging-s7-decisions` |

---

## Rulings added while freezing the seams

The two below were not on the list. Freezing the first eleven surfaced them, and both would
otherwise have been answered differently by three slices each.

### 12. Who may read and write messages — doc 02 contradicts itself

Doc 02 §3.1 marks `GET`/`POST /channels/{id}/messages` **"channel member"**. Doc 02 §3.1.1, added
in S1, says a public channel is visible to the whole workspace and that *"membership gates the
messages in a channel, not the knowledge that it exists."* Read together with the fact that
**nothing in scope lets a user join a channel themselves** — there is no self-join endpoint, and
S2's `POST /channels/{id}/members` is admin-driven — those two rules recreate exactly the gap S1
closed. Ada creates `#general`; Grace can see it in her sidebar and can never read a word in it.
S3's own demo ("Grace sees Ada's message after reloading") and every S5 and S6 scenario are
unsatisfiable as specified.

**The ruling: visibility gates reading *and* writing; membership gates administration.**

| Request | Rule |
|---|---|
| `GET /channels/{id}/messages` | the caller can see the channel — i.e. `channels.get_visible` returns it. Public in the token's `wsp`, or a member of a private one |
| `POST /channels/{id}/messages` | same test. Posting in a public workspace channel needs no membership row |
| `GET /messages/{id}` | same test, applied to the message's channel |
| `PATCH /messages/{id}` | author only (S4) |
| `DELETE /messages/{id}` | author, or an admin of the message's channel (S4) |
| `join_channel` over Socket.IO | same visibility test as `GET .../messages` — the room mirrors the read rule (S5) |
| A channel the caller cannot see | **404**, never 403 — for every one of the above |
| An archived channel | `get_visible` already filters `archived_at IS NULL`, so its messages are unreachable by the same code path. Correct, and deliberate |

**Posting does not create a membership row.** No implicit join in this scope: `myRole` stays
`null` for someone who has posted in a public channel they never joined, and the admin controls
stay hidden. Whether posting should join you is a product question for later, not a slice's to
settle.

The practical consequence for the planners: `messages.py` guards on
`channels.get_visible(...)`, not on `channels.is_member(...)`. `is_member` and `is_admin`
(`channels.py:217`, `:221`) exist and are for administration and for delete authority.

**S3 writes this back into `docs/design/02-messaging-service.md` §3.1 (the Auth column on the
message rows) and §3.1.1.** S4 writes back only its own two rows.

### 13. The `Message` DTO — S3 defines it, three slices serialize it

Doc 02 §3.1.3 gives a `Message` DTO carrying `reactions` and no `version`. Neither is right for
this scope: the `reactions` table is not created (ruling 2), and `version` is what a `PATCH`
sends back for optimistic concurrency (ruling 3). **S3 defines it once, in
`messaging/schemas.py`, and S4, S5 and S6 use it unchanged:**

```jsonc
// Message
{ "id": "uuid", "channelId": "uuid", "authorId": "uuid",
  "threadRootId": "uuid|null",          // always null in this scope (D8a 🟡)
  "body": "markdown text",              // "" when deletedAt is set (ruling 1)
  "attachments": [],                    // always empty; the Asset service is a skeleton
  "createdAt": "...", "editedAt": "...|null", "deletedAt": "...|null",
  "version": 0 }
```

No `reactions` key — a field that is always `[]` is a claim the service does not honour. No
`workspaceId`, for the reason the `Channel` DTO gives: it is the token's `wsp` and echoing it
invites a client to start sending it. `authorId` is a bare id; there is no user expansion, because
Messaging does not read Auth's tables (Conventions §2) — **rendering an author's name from an id
is a Contract question for S3 to raise, not to answer**, and the S3 Gherkin says "a message shows
its author".

The list envelope is `MessageListResponse` = `{items, nextCursor}` via `build_page`, matching
`ChannelListResponse` (`schemas.py:62`). History is **newest-first, keyset on `id DESC`** —
`messages.id` is UUID v7, so one descending key is unique and matches the index in ruling 1.
Never `OFFSET`.

**S3 writes this into `docs/design/02-messaging-service.md` §3.1.3**, replacing the DTO there.

---

## Rulings 14–21 — amended 2026-08-15, after the planners returned

The nine Contract questions the six plans raised, ruled on. Where a ruling changes one of 1–13 it
says which.

### 14. Display names for a bare user id — S2 owns it, S3 and S6 consume it

**Raised by S2 and S3 independently, with different answers — the clearest evidence the fan-out
needed reconciling.** Ruling 13 froze `authorId` as a bare uuid and said rendering a name from it
was a question, not an answer. S2 hits it first, in the member panel, before S3 hits it on a
message.

**Option A, as both planners recommended: the SPA reads Auth's existing endpoint.** Rejecting
option B (denormalising an `author_name` column onto `messages`) matters and is worth the sentence:
a copied display name goes stale the moment someone renames themselves, and it would put a fact
Auth owns into Messaging's database — the thing CLAUDE.md's "every service owns its own database"
rule exists to stop. Messaging's *server* still reads nothing of Auth's; the **browser** makes a
second call, holding a token that already entitles it to both.

`GET /api/v1/workspaces/{workspaceId}/members` exists and is built
(`auth/routers/workspaces.py:108`). Three corrections to what the planners assumed about it:

- Its item shape is **`{ user: { id, displayName, avatarAsset }, role, joinedAt }`** — the profile
  is nested under `user` (`auth/schemas.py:159` / `:115`), not flat. S3's plan described it flat
  and has been patched; S2's already said `user.displayName`.
- It is `_same_workspace`-guarded, so it is called with the token's own `wsp` and nothing else.
- It is **cursor-paginated, default limit 50** (Conventions §4.1). A directory that fetches one
  page and stops silently loses every name after the fiftieth. It pages to exhaustion, or it says
  in a comment why not.

**One implementation, named here so two slices cannot build two.** `src/frontend/src/lib/auth/api.ts`
gains `workspaceMembers(accessToken, workspaceId)` alongside the existing `workspaces()`
(`api.ts:101`); **S2** adds `src/frontend/src/features/channels/useWorkspaceMembers.ts` holding the
hook and the key:

```ts
export const directoryKeys = {
  members: (workspaceId: string | null) => ['workspace-members', workspaceId] as const,
}
```

S2's `['workspace-members', workspaceId]` wins over S3's `['directory', …]` — it names the endpoint
it caches. **S3 and S6 import this hook and define neither a second key nor a second fetch.** A
user id with no matching member renders as a shortened id, never as a blank or a crash.

### 15. The Socket.IO ack envelope — S5 defines it, S6 cites it

**Raised by S5 and S6, who invented two envelopes that differ in one key.** No design doc defines
an error shape for a socket ack; Conventions §4.2 stops at HTTP. The envelope:

```jsonc
{ "ok": true,  "data": { /* the Message DTO */ } }
{ "ok": false, "problem": { /* the RFC 7807 body, verbatim */ } }
```

**`problem`, not S5's `error`.** The platform calls these Problem Details everywhere it names them
— `ProblemException`, `install_problem_handlers`, `problem_response`, the SPA's `ProblemError` —
and reusing the word is what tells a reader the body is the same document a REST call would have
returned.

**S5 owns it**: `_ok()`, `_problem()` and the `@_acked` decorator live in `messaging/realtime.py`,
because `join_channel` needs to refuse a channel before S6 exists. **S6 imports them.** Both
slices' handlers **never raise** — a raising handler drops the client's callback and the browser
waits forever.

### 16. `shared/problems.py` — the request-free body joins S5's `shared` extraction

**Raised by S6, which claimed it.** Overturned on ownership only: `problem_response` is
`Request`-bound (`shared/problems.py:124`) and so is `trace_id` (`:108`), so ruling 15's envelope
needs a request-free `problem_body(problem, *, trace_id=None) -> dict` — and **S5 needs it before
S6 does**, for the same `join_channel` refusal.

**S5 owns it**, extending ruling 4: one slice touches `src/services/shared/`, reviewed once, for
both the security extraction and this one. `problem_response` is rewritten to call it so there is
one problem-document builder, and `shared/tests/test_problems.py` covers the request-free path.
S6 imports and does not respecify. The trace id has no `Request` to come from inside a socket
handler; S5 rules whether it is omitted or carried on the connection, and says which.

### 17. The message cache helper upserts — this amends ruling 7

**Raised by S5.** Ruling 7 said S3 exports a helper that "inserts, replaces or removes one
message", which is vague enough to be built as a blind append. S5 found why that would be wrong:
**the REST sender receives its own `message_received` broadcast.** There is no `sid` to skip it by,
so Ada's own message would arrive twice and render twice.

S3's plan already specifies the right thing — replace in place on a matching id, insert otherwise.
This ruling names that behaviour so it cannot be built any other way; **it is not a correction to
S3, and S3 changes nothing.**

**The helper is `upsertMessage(queryClient, key, message)` — keyed on `message.id`, replacing in
place when the id is already cached on any page, and otherwise inserting at the head of the newest
page — plus `removeMessage(...)`.** Never a blind append. Head-of-newest-page *is* id order here:
history is newest-first and `messages.id` is UUID v7, so a new message sorts above every cached
one. S3 defines both; S5 and S6 call them. S6's optimistic send
composes on top: drop the `temp:` row, then upsert the real one, in that order, so a broadcast that
beats the ack is absorbed rather than duplicated.

S5's related finding stands and binds S3: a handler that fires for a channel with **no cached
history** must no-op, not seed a one-message page with a null `nextCursor` — that fabricates a
history the user can never scroll past.

### 18. Socket payloads — `version` on edit, the full `Message` on delete

Three questions from S4, S5 and S6. The first two are confirmations; **the third overturns S6**,
which argued the opposite in its plan and has been patched:

- **`edit_message` carries `{ messageId, body, version }`.** Doc 02 §3.2 omits `version`, which
  would let the socket path bypass the concurrency rule ruling 3 makes mandatory on `PATCH`. The
  socket is not a way around the contract. **S6** writes the corrected row.
- **`delete_message`'s ack returns the tombstoned `Message`**, not an id — the row stays in the
  list and the client has to render it (ruling 1).
- **`message_deleted` carries the full `Message` too**, overturning doc 02 §3.2's
  `{messageId, channelId}`. Same reason. **S5** writes that row, since it owns the server→client
  half.

### 19. Ownership ruling 9 left unassigned

| Section | Owner | Why |
|---|---|---|
| 02 §3.2 — the `user_typing` server→client row | **S6** | ruling 9 gave the server→client half to S5, but only S6 emits it; ownership follows the emitter |
| 06 §8 — the client-side message-length pre-check | **S6** | S6 removes it (gap 8); the slice that changes the behaviour corrects the doc |
| Conventions §6 + 02 §4.1 — the R2 backplane channel name | **S5** | *overturns S5's own recommendation that S7 carry it.* CLAUDE.md records a decision in the slice that makes it, and this one is forced by S5's code: Canvas and Messaging would otherwise share `AsyncRedisManager`'s default `channel="socketio"` on one R2. Too load-bearing to defer to a sweep. Canvas's doc 03 is **told, not edited** — S5 notes the collision and leaves the other service's doc alone |
| Conventions §3 — the soft-delete bullet and its two exceptions | **S7** | as S7 recommended |
| `CLAUDE.md` — the soft-delete bullet, "Settled so far" | **S7** | as S7 recommended |
| 02 new §3.1.5 — the rows this scope never builds | **S7** | additive; edits no row another slice owns. Distinct from S4's new §3.1.4 (ruling 9) |
| 06 §3 and §7 | **S7** | as S7 recommended |

**If S7 finds D8d still 🔴 because S4 slipped, S7 fixes the register row and escalates rather than
authoring the ADR.** S7 proposed this itself and it is right: a sweep that quietly writes another
slice's ADR hides that the slice did not finish.

### 20. A member removed while their socket is live — accepted, and written down

**Raised by S2.** Once S5 ships, removing someone from a private channel does not evict their
live socket from room `channel:{id}`, so they keep receiving broadcasts until they reconnect.

**Accepted as a limitation, not fixed in this scope.** Evicting a live connection means either a
cross-request registry of sids per user or a re-authorization on every publish, and the exposure
is one already-authorized session on one private channel until its next reconnect. It only affects
private channels — ruling 12 makes public ones workspace-visible anyway, so there is nothing to
revoke.

**S5 documents it in its doc 02 §3.2 writeback**, including the mitigation that already exists:
`join_channel` re-authorizes, so a reconnect drops them. Not a Gherkin scenario — it asserts an
absence over an unbounded wait.

### 21. `messages.validate_body` is a named function

**Raised by S4 as a dependency on S3.** Granted, and binding on S3: body validation is
`messages.validate_body(raw: str, *, max_chars: int) -> str` — the limit is configuration
(`settings.messaging_max_body_chars`, `settings.py:30`), so it is a parameter, not a constant in
the module. A named domain function beside
`channels.validate_name` (`channels.py:81`), not logic inline in `create`. Send and edit then
cannot drift on the maximum length, and S4 adds no extraction of its own.

Same shape as `validate_name`: one exception per broken rule so the router can put a specific
message under `errors.body`.


---

## Rulings 22–24 — amended 2026-08-15, after the reviewers returned

### 22. Doc 02 §3.1.3 splits per DTO block, not per section

Ruling 9 subdivided §3.1.3 for `Channel` (nobody) and `Message` (S3) and forgot that S2 has three
membership DTOs to put somewhere. Both plans now claim the section.

**Ownership within §3.1.3 is per DTO block, exactly as §3.1's is per row:** `Channel` — nobody, it
shipped in S1 · `Message`, `MessageListResponse`, `SendMessageRequest` — **S3** · the membership
DTOs (`AddChannelMemberRequest`, the member response and its list envelope) — **S2** ·
`EditMessageRequest` — **S4**, which puts it in its own new §3.1.4 rather than here. No slice
rewrites the section; each appends its own block.

### 23. S5 exposes the live socket — S6 has nothing to emit on otherwise

Ruling 7 confines `stores/chat.ts` to `connectionStatus`, and S5's `useChannelSocket` owns the
socket's lifecycle but returns nothing. S6's composer then has no way to reach the connection.

**S5 adds `lib/realtime/SocketProvider.tsx` — a React context holding the live socket, provided by
`ChatLayout` where the hook is already mounted, read through a `useSocket()` accessor.** S6 imports
it. The socket does not go in the Zustand store: ruling 7 is about server state, and a live
connection is neither server state nor client state — it is a resource, and a context is what React
has for those.

### 24. One display name source — the typing payload does not carry its own

S6 put a `displayName` on `user_typing`, taken from the sender's own token claim, arguing an
ephemeral event cannot go stale. True, but it makes two sources for one name.

**The name is resolved client-side through ruling 14's `useWorkspaceMembers`, like every other name
in the UI.** The typing user is by definition in the workspace that hook has already fetched. This
also leaves doc 02 §3.2's `user_typing` payload exactly as written — `{channelId, userId}` — so S6
documents the throttle, the TTL and the `skip_sid` behaviour rather than changing a shape.
