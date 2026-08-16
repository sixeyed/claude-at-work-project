# Slice 3 — Messages: send and read history

## Context

[`02-messaging-core-delivery-plan.md`](./02-messaging-core-delivery-plan.md) describes this slice in
one paragraph. This plan does two things with it, in order: it **validates that paragraph against
the design docs and against the code Slice 1 shipped**, closing the gaps it finds, and it then
**specifies the slice** in enough detail to build from without re-deciding anything on the way.

Slice 3 is the first slice that writes a row a user typed. It ends with Ada typing into `#general`
and seeing her message, scrolling up to pull older ones, and Grace seeing it after a reload —
real-time is Slice 5 and the scenario says so out loud.

The cross-slice seams are already frozen in [`04-slice-contracts.md`](./04-slice-contracts.md), and
five of its thirteen rulings land in this slice: tombstones and the messages index (ruling 1),
migration ownership (ruling 2), the BDD truncate list (ruling 6), the message query keys and the
infinite-query cache helper (ruling 7), and the two rulings the freeze itself surfaced — who may
read and write messages (ruling 12) and the `Message` DTO (ruling 13). Those are followed and
cited, never re-decided.

Validation found **eight gaps**. Four are corrections to the *design docs* that this slice owns and
writes back; one is a **Contract question** that this slice may not answer; one is a knob in
`.env.example` that has never reached the container it configures.

---

## Gaps closed

### 1. Who may read and write messages — doc 02 §3.1 contradicts doc 02 §3.1.1

Doc 02 §3.1 marks `GET`/`POST /channels/{id}/messages` and `GET /messages/{id}` **"channel
member"**. Doc 02 §3.1.1 — added by Slice 1 — says a public channel is visible to the whole
workspace, and that *"membership gates the messages in a channel, not the knowledge that it
exists."* Nothing in scope lets a user join a channel themselves: there is no self-join endpoint,
and Slice 2's `POST /channels/{id}/members` is admin-driven. So this slice's own demo is
unsatisfiable as specified — Ada creates `#general`, Grace sees it in her sidebar, and can never
read a word in it.

Ruled in **contracts ruling 12**: *visibility gates reading and writing; membership gates
administration.* The rows this slice owns, restated only so the implementation has them in one
place:

| Request | Rule |
|---|---|
| `GET /channels/{id}/messages` | `channels.get_visible` returns the channel — public in the token's `wsp`, or a member of a private one |
| `POST /channels/{id}/messages` | the same test. Posting in a public workspace channel needs no membership row |
| `GET /messages/{id}` | the same test, applied to the message's channel |
| a channel the caller cannot see | **404 `not-found`**, never 403 |
| an archived channel | `get_visible` already filters `archived_at IS NULL`, so its messages are unreachable through the same code path — deliberate |

**`messages.py` guards on `channels.get_visible(...)`, never on `channels.is_member(...)`.**
`is_member` / `is_admin` (`channels.py:217`, `:221`) exist for administration and for Slice 4's
delete authority. **Posting does not create a membership row** — `myRole` stays `null` for someone
who has posted in a public channel they never joined, and the admin controls stay hidden.

**Write this back into `docs/design/02-messaging-service.md` §3.1 (the Auth column on the three
message rows) and §3.1.1** — ruling 9 gives S3 those rows and that rule; S4 writes back only
`PATCH`/`DELETE /messages/{id}`.

### 2. The `Message` DTO in doc 02 §3.1.3 describes a service this scope will not be

Doc 02 §3.1.3 gives a `Message` carrying `reactions` and no `version`. The `reactions` table is not
created (ruling 2) and `version` is what a `PATCH` sends back for optimistic concurrency (ruling
3). **Contracts ruling 13 defines the DTO once, here, and S4, S5 and S6 serialize it unchanged:**

```jsonc
// Message
{ "id": "uuid", "channelId": "uuid", "authorId": "uuid",
  "threadRootId": "uuid|null",          // always null in this scope (D8a 🟡)
  "body": "markdown text",              // "" when deletedAt is set (ruling 1)
  "attachments": [],                    // always empty; the Asset service is a skeleton
  "createdAt": "...", "editedAt": "...|null", "deletedAt": "...|null",
  "version": 0 }
```

No `reactions` key and no `workspaceId`, for the reasons ruling 13 gives. The asymmetry with
`attachments` — dropped as a field but kept as a key — is deliberate and worth one line in the
schema docstring: `attachments` is a real column read off a real row that simply has nothing in it
yet, whereas `reactions` would need a table that does not exist and a query nothing makes.

Two shapes ruling 13 implies but does not spell out, defined here:

```jsonc
// MessageListResponse — matches ChannelListResponse (schemas.py:62)
{ "items": [ /* Message */ ], "nextCursor": "…|null" }

// SendMessageRequest — POST /channels/{id}/messages
{ "body": "markdown text" }
```

`SendMessageRequest` carries **no** `channelId` (it is in the path), no `authorId` (it is the
token's `sub`), no `threadRootId` and no `attachmentIds` — accepting a field the service ignores is
a claim it does not honour, and both arrive with the features that need them.

**Write this into `docs/design/02-messaging-service.md` §3.1.3**, replacing the `Message` block
there.

### 3. Message body validation — the design gives one number, no floor, and no layer

Doc 02 §8 says *"Max message body 8000 chars"*; doc 02 §6 names `MESSAGING_MAX_BODY_CHARS`;
`settings.py:30` already carries the default. Nothing anywhere says whether an empty body is
allowed, whether the body is trimmed, which layer enforces the limit, or what key the `errors` map
uses — and the delivery plan's scenario list only covers the over-length case. The rules, mirroring
the shape Slice 1 settled for channel names (doc 02 §3.1.2):

- **A body that is empty or nothing but whitespace is rejected** — 400 `validation-error`,
  `errors: {"body": ["A message cannot be empty."]}`. This is the floor the design never gave.
- **The body is stored verbatim, not trimmed.** Markdown is whitespace-sensitive — an indented
  code block and a hard line break both mean something — so unlike a channel name, leading and
  trailing whitespace survives. Emptiness is judged on `body.strip()`; length is judged on the raw
  string.
- **Length is compared against `settings.messaging_max_body_chars`**, in characters, in the domain
  — one rule, one message, `errors: {"body": ["A message must be 8000 characters or fewer."]}`.
- **`SendMessageRequest.body` also carries a static outer bound**, `Field(max_length=64_000)`,
  exactly as `CreateChannelRequest.name` carries `max_length=200` for an 80-character rule. It
  exists only to stop an unbounded body reaching the domain at all. **It must stay well above the
  configured limit**, or raising `MESSAGING_MAX_BODY_CHARS` would silently start reporting the
  wrong error from the wrong layer — an integration test pins that the configured limit is the one
  that reports.
- One message per rule, so the composer can put it against the field rather than in a banner.

**Write this into `docs/design/02-messaging-service.md` §3.1.3**, alongside the DTO. **Do not
create a new §3.1.4 for it — ruling 9 gives that number to S4** for tombstones in history, and two
slices creating the same subsection is exactly what the contracts document exists to prevent.

### 4. The messages indexes — doc 02 §4 gives a predicate this slice must not use

Doc 02 §4 gives `ix_messages_channel_time ... WHERE deleted_at IS NULL` and
`ix_messages_thread`. Neither is right for this scope, and both are already ruled on:

- **Ruling 1** — history returns tombstones with `body` redacted and `deletedAt` set, so the read
  path filters no `deleted_at` and would not match a partial index. This is a documented,
  message-specific exception to CLAUDE.md's blanket "queries filter `deleted_at IS NULL`", the same
  shape of exception `channels`/`archived_at` already carries.
- **Ruling 2** — `ix_messages_thread` is *not* created. A column ships ahead of its feature because
  adding one later churns the table; an index supporting a query no code makes is dead weight, and
  adding it later is a one-line migration with no table rewrite. Same reasoning that leaves
  `reactions` uncreated.

```sql
-- No `WHERE deleted_at IS NULL`: history returns tombstones, so the read path
-- would not match a partial index (contracts ruling 1).
CREATE INDEX ix_messages_channel_time ON messages (channel_id, id DESC);

-- ix_messages_thread is deliberately NOT created (contracts ruling 2): nothing
-- queries thread_root_id in this scope.
```

The read path ships **complete** in this slice: `history_page` and `get` do not filter
`deleted_at`, and the response mapper already redacts a deleted row, even though nothing in S3 can
set `deleted_at`. That costs four lines here and means S4 changes no read path at all — it only
adds the writes.

**Write this back into `docs/design/02-messaging-service.md` §4** — ruling 9 gives S3 the `messages`
DDL and its indexes. Note the `ix_messages_thread` omission in the migration docstring and leave
doc 02 §4's DDL as the eventual shape, exactly as `0001_channels.py` did.

### 5. A message shows its author, and the DTO carries an id — **Contract question**

The delivery plan's scenario is *"A message shows its author and timestamp"*. Ruling 13 froze the
`Message` DTO with a bare `authorId` and no user expansion, because Messaging does not read Auth's
tables (Conventions §2) — and it explicitly leaves the rendering question to this slice **to raise,
not to answer**. The SPA today holds `Profile` for the *signed-in* user only
(`lib/auth/api.ts:27`), so Ada's window can render her own name and nothing else.

**Contract question: how does the SPA render another user's display name against a message?**

| Option | Cost | Consequence |
|---|---|---|
| **A — SPA reads Auth's workspace directory** *(recommended)* | one new query hook; no schema change, no new endpoint | `GET /api/v1/workspaces/{wsp}/members` already exists (`auth/routers/workspaces.py:108`), takes plain `require_user`, and requires the path id to equal the `wsp` claim. Map `authorId` → `displayName`, fall back to a shortened id for anyone no longer in the workspace |
| B — denormalize `author_name` onto `messages` | a column in `0002`, a field on the frozen DTO | Cheapest at render time, and the token already carries the `name` claim at write time. But a display name renamed in Auth never updates in history, and it puts a second service's data in Messaging's table |
| C — an Auth internal batch lookup | a new `/api/v1/internal/` route, a service token, a scope | New machinery for something an existing public route already answers |

**Recommendation: option A.** It changes no schema, no DTO and no service boundary, and it is the
same call the member panel in S2 will need.

**This has a deadline, and it is this slice.** Option B needs `author_name` in migration `0002`, and
**ruling 2 forbids any other slice adding a migration** — so if the answer is B it must be given
before `0002` is written, not after. Work package C specifies option A; if the answer is B, gaps 2
and 4 both change with it.

> **Answered by ruling 14 (`04-slice-contracts.md`), 2026-08-15.** Option A, as recommended —
> S2 raised the same question and reached the same answer. Three things this gap got wrong about
> the endpoint, corrected there and binding here: its item shape is
> **`{ user: { id, displayName, avatarAsset }, role, joinedAt }`** — the profile is nested under
> `user` (`auth/schemas.py:159`), not flat · it is cursor-paginated at 50, so the directory pages
> to exhaustion or loses every name after the fiftieth · **the hook is S2's, not this slice's.**
> S3 imports `useWorkspaceMembers` from `features/channels/useWorkspaceMembers.ts` and the key is
> `['workspace-members', workspaceId]`, not `['directory', …]`. `0002` carries no `author_name`.

### 6. Newest-first on the wire, oldest-first on screen — three layers and no ruling on who flips it

History is **newest-first, keyset on `id DESC`** (ruling 13, and the delivery plan). Chat is read
oldest-at-top. Doc 06 §5.2 says only *"load history via REST … and merge"*. Nobody says where the
reversal happens, and getting it wrong twice — once in `select`, once in the S5 cache helper — is
the seam ruling 7 already calls "the most likely to be got wrong twice".

| Layer | Order | Why |
|---|---|---|
| SQL / wire | newest first (`id DESC`) | matches `ix_messages_channel_time` and makes "the first page is what you see on open" one query |
| TanStack cache | `pages[0]` is the **newest** page; `items` within a page are newest-first | it is the raw server response; `useInfiniteQuery` appends each fetched page, so later pages are older |
| DOM | oldest first | how a chat log reads |

**The reversal happens once, in `useMessages`'s `select`**, and it copies before reversing —
`[...data.pages].reverse().flatMap(p => [...p.items].reverse())`. `Array.reverse` mutates, and the
array it would mutate is the cached server response.

It follows that **a newly arrived message belongs at the head of `pages[0].items`**, which is what
the helper ruling 7 requires this slice to export must do. The helper no-ops when the cache entry
is `undefined`, so an S5 socket event arriving before the first history load cannot fabricate a
page out of one message.

The corresponding edit to **doc 06 §5.2 belongs to S5** (ruling 9), so this slice does not make it.
The ordering contract is recorded here and in `useMessages.ts`'s docstring for S5 to reflect.

### 7. "Scrolling up loads older messages" cannot be arranged through the UI

The default page limit is 50 (`shared/pagination.py:37`), so the scenario needs 51 messages before
it can scroll to a second page. Sending 51 messages through the composer is 51 browser round trips
per run, and the harness has no API-level seeding — Slice 1 arranged everything by driving the UI,
which was right when the arrangement was one channel.

**Seed history directly into Postgres from the harness**, over the asyncpg connection
`tests/bdd/conftest.py` already opens to truncate with. The trade is honest: only the *arrangement*
bypasses the API, the read path and the cursor are exercised exactly as a user hits them, and the
write path has its own scenario two lines above. The seed:

- resolves the channel by name — `SELECT id FROM channels WHERE name = $1` — so no channel id has
  to be plumbed out of the browser and no new `data-testid` exists purely for a test;
- generates ids with `shared.uuid7()` in Python, sequentially, so the seeded rows sort older than
  anything sent afterwards and the keyset walks them in a defined order (CLAUDE.md: ids are
  generated in the application, never by the database);
- takes `author_id` from an existing message in that channel when there is one, so seeded rows look
  like the sender's, and a fresh uuid otherwise.

This is a helper next to `_truncate`, not a session-scoped fixture and not a third signed-in user —
ruling 6 makes that distinction, and this stays on the permitted side of it.

### 8. `MESSAGING_MAX_BODY_CHARS` is wired — make it explicit, do not "fix" it

**Withdrawn in review, 2026-08-15, and left here as a warning.** This gap originally claimed the
setting never reaches the container, because the `messaging` block in `docker-compose.yml` names
`POSTGRES_DSN`, the three Redis URLs and `CORS_ALLOWED_ORIGINS` and not this one. That is wrong:
`x-service-common` sets `env_file: .env` (`docker-compose.yml:16`) and `messaging` merges it
(`:180`), so **every variable in `.env` already reaches every service**. The knob works.

The reason it looked broken is worth keeping: the explicit `environment:` list reads like the whole
contract when it is only the part that is renamed or interpolated. `MESSAGING_POSTGRES_DSN → POSTGRES_DSN`
has to be listed because the names differ; `MESSAGING_MAX_BODY_CHARS` does not, because it does not.

**The call: change nothing.** Adding an explicit line would be harmless but would imply the others
are missing. **Do not "fix" this**, and do not read Slice 1's `CORS_ALLOWED_ORIGINS` finding as the
same shape — that one was genuinely absent from `.env` handling for a service that had no
`env_file` merge at the time.

### Also corrected in the delivery plan

Recorded here only — **ruling 9 gives S7 the sole right to amend the delivery plan**, in one dated
amendment covering all six slices.

- **The Slice 3 paragraph does not mention regenerating OpenAPI.** This slice adds three routes and
  three schemas, so ruling 8 applies: `messaging.json` and `src/types/messaging.ts` are both
  regenerated, and both commands are in Verification below.
- **It does not mention the BDD truncate list.** Ruling 6 makes this the slice that changes
  `MESSAGING_TABLES` (`tests/bdd/conftest.py:60`) to `"messages, channel_members, channels"`.
- **Decision 2 lists `last_read_id` as a later-feature column still to come.** It shipped in
  `0001_channels.py:87`. Ruling 2 already corrects this.
- **The paragraph's index note points at decision 1 for a predicate; ruling 1 also drops
  `ix_messages_thread`,** which decision 2 does not mention at all.
- **`test_schema.py:33` asserts `"messages" not in names`.** That assertion was correct for one
  slice and this is the slice that flips it — a passing test that must be rewritten, not a
  regression.

---

## How the slice runs

Unchanged from the delivery plan:

1. Gherkin first — write `tests/bdd/features/messages.feature` and nothing else.
2. 🛑 **Stop and wait for explicit approval.** Expect rounds of revision.
3. Build outside-in, and watch the scenarios fail for the right reason first.
4. Never edit a scenario to fit the implementation.
5. `data-testid` selectors only, owned by page objects — a step definition never holds one.
6. Branch `feature/messaging-s3-messages`. **Never commit** — leave the tree dirty.

**Scenarios.** Ada sends a message and sees it in the channel · A message shows its author and
timestamp · A blank message is not sent *(new — gap 3 created the rule, so the rule gets a
scenario)* · A message over 8000 characters is rejected · Scrolling up loads older messages ·
Grace sees Ada's message after reloading *(the placeholder for S5's live version, and it says so)*.

Staying at integration level and deliberately out of Gherkin: tenancy isolation (a workspace-A
token reading a workspace-B channel's messages), 404-not-403 for a private channel the caller is
not in, **the positive private-channel case — a member of a private channel `GET`s and `POST`s its
messages successfully** — the exact `errors` map and problem `type` of each rejection, cursor
mechanics and `nextCursor` going null on the last page, and the tombstone read path — which no
endpoint can even produce until S4, so it is arranged with raw SQL.

**Why the private-channel read/write pair is here and not in Gherkin.** Ruling 12 makes
`messages.py` guard on `channels.get_visible(...)` rather than `channels.is_member(...)`, and that
is the mistake worth defending against — doc 02 §3.1 says "channel member", so a builder following
it recreates the gap S1 closed. A **private channel with a member** cannot catch that mistake:
`get_visible` and `is_member` both return true for them, so the scenario passes under either guard.
The case that discriminates is **public plus non-member**, and the Gherkin already carries it twice
— Grace reads `general` without joining it ("Grace sees Ada's message after reloading"), and S4
arranges two messages by having Grace *post* to it. `get_visible` is `_visible_query` plus an id
filter (`channels.py:199`), so there is no second visibility path a browser test could reach that
these do not. What is left is worth a pair of integration cases and not a browser scenario:
membership-gated visibility composing with the message routes.

---

## Work

### A. Gherkin and harness — `tests/bdd/`

**The Gherkin is already written, reviewed and merged**, for this slice and for slices 2, 4, 5 and 6
together, against [`gherkin/00-scenario-vocabulary.md`](./gherkin/00-scenario-vocabulary.md). Step 1
of this slice is "turn this slice's scenarios on", not "write them".

- **First build step: delete `@pending` from this slice's six scenarios in
  `tests/bdd/features/messages.feature`** — they are tagged `@pending @s3`. Keep `@s3` for now (see
  the last bullet). **Leave S4's five `@pending @s4` scenarios in the same file alone**: this slice
  calls `scenarios()` on the whole file, so un-ignoring them would run five scenarios for behaviour
  this slice does not build and keep the suite red throughout. Then watch the six fail for the right
  reason before writing code.
- `tests/bdd/features/messages.feature` — **do not rewrite it.** It holds the approved contract for
  this slice and for S4, with one narrative paragraph and one `Background`, both this slice's. Never
  edit a scenario to fit the implementation (delivery-plan step 4).
- **`steps/conftest.py` already exists** — S2 created it and moved the shared steps into it, because
  pytest-bdd resolves a step from the calling module and `conftest.py`, never from a sibling
  `test_*.py`. Put steps this slice's feature file introduces in `test_message_steps.py`, and any
  step S4, S5 or S6 will also need in `steps/conftest.py`. **Do not re-register a step that is
  already there** — a second spelling of one act is the defect the shared module exists to prevent.
- **Last build step, once delivered and green: delete `@s3` from those six scenarios.**
- `tests/bdd/steps/test_message_steps.py` — new. **Named `test_*`** (ruling 6): `scenarios()`
  generates one test function per scenario into the calling module, and a module pytest does not
  collect is a feature file that silently never runs. `pytestmark = pytest.mark.bdd`,
  `scenarios("../features/messages.feature")` called **here and nowhere else**. Structure mirrors
  `steps/test_channel_steps.py` — given/when/then blocks, `parsers.parse`, loose phrase matching on
  complaints so copy stays editable. Reuses the existing `ada` / `grace` fixtures; adds none.
- `tests/bdd/pages/chat_page.py` — extended, not replaced (ruling 6: one page object for the chat
  shell). New methods, every selector staying inside this file:
  - `open_channel(name)` — **S2 adds this first**; S3 reuses it and adds nothing. Slice 1's
    scenarios always navigated by creating, so the method is genuinely new to the suite — but it is
    new in S2, which needs it to open a channel as a non-admin. If S2 has not landed, S3 adds it to
    the same file with the same name and S2 finds it there.
  - `send_message(text)`, `send_message_and_wait(text)` — fill `message-composer-input`, click
    `message-composer-send`, wait for the body to appear; mirrors `create_channel_and_wait`.
  - `message_bodies()`, `author_of(body)`, `timestamp_of(body)` — read from `message-item` rows and
    their `message-author` / `message-body` / `message-time` children. `timestamp_of` reads the
    `datetime` attribute, not the rendered text, so the assertion does not depend on a locale.
  - `scroll_history_to_top()` — scroll the `message-list` container to 0 and wait for the count to
    grow; the Playwright call lives here for the reason `go_offline()` will in S5.
  - `composer_error()` — mirrors `error_message()`, reading `message-composer-error`.
  - `_settle_messages()` — waits for `message-list-loading` to detach, the same trick `_settle()`
    already uses for the sidebar; reading through the loading state returns an empty list that
    looks exactly like "no messages".
- `tests/bdd/conftest.py`:
  - `MESSAGING_TABLES = "messages, channel_members, channels"` — child table first (ruling 6).
  - `async def _seed_history(dsn, channel_name, count, prefix)` next to `_truncate`, per gap 7:
    one `SELECT id FROM channels WHERE name = $1`, one `SELECT author_id FROM messages WHERE
    channel_id = $1 LIMIT 1`, then an `executemany` insert of `count` rows with sequential
    `shared.uuid7()` ids. `shared` is a root workspace dependency, so it imports without ceremony.
  - `_run_off_loop` currently takes `Callable[[str], Coroutine]` and one dsn argument. Widen it to
    take a zero-argument coroutine factory and pass `partial(_truncate, dsn)` /
    `partial(_seed_history, dsn, …)`; the existing call sites change by one word. Everything stays
    synchronous — `asyncio_mode = "auto"` means an `async def` step would be collected as an
    asyncio test and Playwright's sync API cannot run inside a live loop.
  - Expose the seed as a function-scoped `seed_history` fixture returning a callable, so a step
    definition never touches a DSN.

### B. Backend — `src/services/messaging/`

- `messaging/models.py` — add `Message`, in the shape `Channel` already has: `Timestamp` for every
  datetime, UUID PK with **no default** (`shared.uuid7()` in the application), `version` with
  `server_default="0"`, `attachments` as `ARRAY(UUID(as_uuid=True))` with `server_default=text("'{}'")`.
  `channel_id` carries `ForeignKey("channels.id")` — same database, same service, and `0001` set
  the precedent with `channel_members`; `author_id` carries **none**, because it names a row in
  Auth's database (ruling 2, Conventions §2). `thread_root_id` is a self-referencing nullable FK,
  as doc 02 §4 has it. `__table_args__` gets `Index("ix_messages_channel_time", "channel_id",
  Message.id.desc())` and **no** `ix_messages_thread`. The module docstring already explains
  `channels`/`archived_at`; extend it with the mirror-image note for `messages` — this table *has*
  `deleted_at` and deliberately does not filter it (ruling 1).
- `messaging/alembic/versions/0002_messages.py` — new revision, `down_revision = "0001"`. Copy the
  shape and the docstring habit of `0001_channels.py`: what ships, what deliberately does not
  (`ix_messages_thread`, `reactions`), and why. **The only migration any slice from 2 to 7 adds**
  (ruling 2) — a planner who believes otherwise raises a Contract question, not a second revision.
- `messaging/schemas.py` — add `MessageResponse`, `MessageListResponse`, `SendMessageRequest` per
  gap 2, using the existing `CamelModel` / `CamelRequest` split (responses are `populate_by_name`,
  requests deliberately are not). `MessageListResponse` mirrors `ChannelListResponse:62` exactly.
- `messaging/messages.py` — **new domain module**, modelled on `channels.py`: plain async functions,
  `AsyncSession` first, no FastAPI imports, one exception per broken rule so the router can build a
  useful `errors` map.
  - `BodyRequiredError`, `BodyTooLongError`, and `validate_body(raw, *, max_chars)` returning the
    body unchanged — the mirror of `validate_name` (`channels.py:81`) except that it does not trim.
  - `create(session, *, channel_id, author_id, body, max_chars) -> Message` — validates, builds with
    `uuid7()`, `session.add`, `await session.flush()`. No `IntegrityError` branch: the only
    constraint that could fire is the channel FK, and the caller has already proved the channel is
    visible.
  - `history_page(session, *, channel_id, page: PageRequest) -> Page[Message]` — mirrors
    `channels.list_page` (`channels.py:178`), itself mirroring `members_page`
    (`auth/identities.py:253`). `order_by(Message.id.desc())`, `where(Message.id < cursor_id)` when
    a cursor is present, `limit(page.fetch_limit)`, `build_page(rows, page, key=lambda m:
    (str(m.id),))`. **One key part, because `messages.id` is UUID v7 and already unique and
    time-ordered** (`shared/pagination.py`'s "the sort key must be unique"). Never `OFFSET`. **No
    `deleted_at` filter** — ruling 1, and the reason is in the docstring.
  - `get(session, *, message_id) -> Message | None` — workspace-blind on purpose; it is never
    called without the channel guard behind it, and the guard is what turns invisibility into 404.
    S4 imports both this and the guard.
- `messaging/routers/messages.py` — **new router module**, not additions to `routers/channels.py`:
  S2 is rewriting that file in parallel, and the message routes belong to a different pair of doc
  rows. Two `APIRouter`s in the one module, because the surface spans two prefixes:
  `channel_router = APIRouter(prefix="/api/v1/channels", tags=["messages"])` carrying
  `GET|POST /{channel_id}/messages`, and `router = APIRouter(prefix="/api/v1/messages",
  tags=["messages"])` carrying `GET /{message_id}` — with `PATCH`/`DELETE` arriving on the same
  router in S4. Module-top private helpers, exactly the idiom `routers/channels.py` and
  `auth/routers/workspaces.py` use:
  - `_settings(request) -> Settings` returning `request.app.state.settings` — copied verbatim from
    `auth/routers/auth.py:43`, and the only way the configured body limit reaches a route.
  - `_visible_channel(session, principal, channel_id)` — `channels.get_visible(...)` or
    `ProblemException.not_found("No such channel.")`. **Ruling 12: `get_visible`, never
    `is_member`.**
  - `_visible_message(session, principal, message_id)` — `messages.get(...)`, then
    `_visible_channel(...)` on its `channel_id`. Both misses raise the same 404 wording, so a caller
    cannot tell "no such message" from "not your channel".
  - `_as_message(row) -> MessageResponse` — `model_validate(..., from_attributes=True)`, then
    `model_copy(update={"body": ""})` when `row.deleted_at` is set. Four lines, shipped now,
    unreachable until S4 (ruling 1). `""`, never `None` — the DTO types `body` as a non-null
    string and the generated TypeScript would otherwise force a null check at every render site.
  - Signature order everywhere: `page: PageParams`, then `principal: UserPrincipal =
    Depends(require_user)`, then `session: AsyncSession = Depends(db_session)`. **Plain
    `require_user`** — messages are not in the fail-closed set (doc 02 §3.1, Conventions §5.2).
    `POST` returns **201** with the created `Message`, matching `POST /channels`; the router
    commits explicitly, because `db.session` does not.
- `messaging/main.py` — include both routers next to `channel_routes.router`. Nothing else changes:
  `create_app(settings, *, key_source=None) -> FastAPI` keeps its signature, which is what S5's
  `build_asgi_app` will wrap (ruling 4).
- `docker-compose.yml` — `MESSAGING_MAX_BODY_CHARS: ${MESSAGING_MAX_BODY_CHARS}` on the `messaging`
  environment block (gap 8). Nothing new in `.env.example`.
- Tests, all `pytestmark = pytest.mark.integration`, against the real containers
  `tests/conftest.py` already provides:
  - `tests/conftest.py` — `TABLES = "messages, channel_members, channels"` (line 42), child first.
    `TRUNCATE ... CASCADE` would reach `messages` anyway through the FK; being explicit is what
    stops the next person wondering.
  - `tests/test_messages.py` — new. Send and read back; author and timestamps; the two validation
    rejections with their `errors` keys and 400 `validation-error` type; the configured limit
    reporting before the static `Field` bound; `GET /messages/{id}`; a **public channel the caller
    has never joined accepts a post and returns history** (ruling 12, and the fact Grace's scenario
    depends on); a private channel the caller is not in gives **404 with
    `application/problem+json`**, not 403; **a private channel the caller *is* a member of accepts a
    post and returns history** — the positive half of the same rule, and the only place it is
    proved, since no Gherkin scenario puts messages in a private channel and the
    "How the slice runs" note explains why; an archived channel's messages are unreachable; and
    `test_a_deleted_row_reads_back_redacted`, which sets `deleted_at` with raw SQL because no
    endpoint can yet, then asserts `body == ""` and `deletedAt` present.
  - `tests/test_pagination.py` — new. 120 messages, `?limit=50`, walk `nextCursor` to exhaustion:
    newest-first order, no row seen twice, no row missed, `nextCursor` null on the last page, and a
    malformed cursor rejected as 400 by `decode_cursor`.
  - `tests/test_tenancy.py` — extend: a workspace-A token gets 404 on a workspace-B channel's
    messages and on a workspace-B message id, and posting into one writes nothing.
  - `tests/test_schema.py` — flip line 33 to assert `messages` **is** present and `reactions` still
    is not; add the messages timestamptz check, `ix_messages_channel_time` present without a
    `WHERE` clause, `ix_messages_thread` absent, and `author_id` carrying no foreign key while
    `channel_id` does.

### C. Frontend — `src/frontend/`

- `openapi/messaging.json` + `src/types/messaging.ts` — regenerated, never hand-edited (ruling 8,
  D23 🟡). Both commands are in Verification.
- `src/lib/api/messaging.ts` — add `listMessages(accessToken, channelId, cursor?)`,
  `sendMessage(accessToken, channelId, body)` and `getMessage(accessToken, messageId)`, each in the
  shape `listChannels`/`createChannel` already have: `openapi-fetch` call, `if (error !== undefined)
  throw problem(response.status, error)`, so nothing downstream sees the two-shaped result. Export
  `type Message = components['schemas']['MessageResponse']` and `MessagePage`.
- `src/features/channels/useMessages.ts` — **new, and the file ruling 7 names**:
  - `messageKeys.list(workspaceId, channelId)` exactly as ruling 7 gives it, mirroring
    `channelKeys` (`useChannels.ts:16`). The workspace id leads the key for the reason
    `useChannels.ts` documents.
  - `useMessages(...)` — `useInfiniteQuery`, `getNextPageParam: (last) => last.nextCursor ??
    undefined`, `initialPageParam: undefined`, `enabled: Boolean(channelId)`, and the `select` from
    gap 6 that copies before reversing.
  - `useSendMessage(...)` — mutation over `sendMessage`; on success calls the cache helper below
    rather than `invalidateQueries`, because invalidating an infinite query refetches **every**
    loaded page — a scroll-back of five pages would refetch five pages to add one message.
  - `upsertMessage(queryClient, key, message)` and `removeMessage(queryClient, key, messageId)` —
    the exported helpers ruling 7 requires, operating on the `{ pages, pageParams }` shape:
    replace in place when the id is already present on any page, otherwise unshift onto
    `pages[0].items`; no-op when the cache entry is `undefined`. **S5 calls these; it does not
    define a second key and does not invalidate-and-refetch per event.**
- `src/features/channels/MessageList.tsx` — new. The scroll container
  (`data-testid="message-list"`, `overflow-y-auto`), `message-list-loading` /
  `message-list-empty` / `message-list-error` states mirroring `ChannelList.tsx:21-43`. Near the
  top of the scroll and `hasNextPage && !isFetchingNextPage` → `fetchNextPage()`. **Scroll
  anchoring both ways**, which the delivery plan asks for and no doc specifies: record
  `scrollHeight` before a prepend and restore `scrollTop += scrollHeight - previous` in a
  `useLayoutEffect`, or the view jumps a page every time older messages arrive; and stick to the
  bottom on a new message only when the user was already at the bottom.
- `src/features/channels/MessageItem.tsx` — new. `data-testid="message-item"` with
  `data-message-id`, and `message-author` / `message-body` / `message-time` children. The timestamp
  renders through `<time dateTime={createdAt}>` with the browser's own locale formatting — **not a
  stored preference**: D28 is 🔴 and there is nowhere to keep a locale, exactly as there is nowhere
  to keep a theme (doc 06 §9). The `dateTime` attribute is what the harness asserts on. S4 adds the
  edit affordance and tombstone rendering **inside this file** (ruling 7); nothing here forecloses
  that.
- `src/features/channels/MessageComposer.tsx` — new. `message-composer-input` (textarea, Enter
  sends, Shift+Enter newlines), `message-composer-send`, `message-composer-error` rendering
  `ProblemError.fieldError('body')` against the field and `message` in the banner — the split
  `CreateChannelDialog.tsx:26-30` already makes. **The composer is the first consumer of
  `stores/chat.ts`'s `drafts`**, which shipped in Slice 1 with nothing writing them: `setDraft` on
  change, `clearDraft` on a confirmed send. No server state enters that store (D24 🟢, ruling 7).
- `src/features/channels/ChannelView.tsx` — replace the `channel-empty` placeholder (`:71`) with
  `<MessageList/>` over `<MessageComposer/>`. The composer is enabled for any channel this view can
  render, because ruling 12 makes visibility the write test too.
- `src/features/channels/useWorkspaceMembers.ts` — **S2 builds this, per ruling 14; S3 imports it
  and adds nothing.** `MessageItem` calls the hook, maps `authorId` → `user.displayName` (the
  profile is nested under `user`), and falls back to a shortened id for anyone no longer in the
  workspace. If S2 has not landed when this slice starts, S3 builds the hook to ruling 14's
  spelling — same file, same `['workspace-members', workspaceId]` key — and S2 finds it already
  there. Auth is already an origin the SPA calls, so nothing changes in CORS or the client.

### D. Decisions and design-doc writeback

- `docs/design/02-messaging-service.md`:
  - §3.1 — the Auth column on `GET|POST /channels/{id}/messages` and `GET /messages/{id}`
    (gap 1). Those three rows only; S2 and S4 own the others (ruling 9).
  - §3.1.1 — the message read/write rule and its 404 (gap 1).
  - §3.1.3 — the `Message` DTO replaced (gap 2), plus the body rules (gap 3). **No new §3.1.4** —
    that number is S4's.
  - §4 — the `messages` DDL, `ix_messages_channel_time` without its predicate, and a line saying
    `ix_messages_thread` and `reactions` are deliberately not created yet (gap 4).
- `docs/design/07-open-decisions-register.md` — **nothing flips in this slice.** D8a stays 🟡 with
  `thread_root_id` shipping as a column and `threadRootId` exposed as `null`; D8d is S4's to settle;
  D16 and D28 stay 🔴 and nothing here depends on them. Re-recording a decision another slice makes
  is the mistake ruling 9 warns about.
- No ADR. This slice makes no decision that is its own to make — the one open question, gap 5, goes
  back to the coordinator.
- No amendment to the delivery plan (ruling 9 reserves that for S7); no edit to doc 06 §5.2
  (ruling 9 gives it to S5); no README changes (S7).

---

## Verification

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -m "not integration and not bdd"          # fast path, no Docker
uv run pytest src/services/messaging                    # integration; starts its own containers

uv run python -m messaging.openapi > src/frontend/openapi/messaging.json   # ruling 8
cd src/frontend && npm run generate:api                 # → src/types/messaging.ts, never hand-edited
npm run typecheck && npm run build

docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build
uv run pytest tests/bdd -m bdd
uv run pytest tests/bdd -m bdd --headed                 # watch it drive the browser
```

`0002_messages` runs from `docker/messaging/entrypoint.sh` on `up` with `RUN_MIGRATIONS=true`;
`docker compose exec messaging python -m messaging.migrate` re-runs it by hand. Both stacks need
`--build` after this slice — the development one for the demo, the test one for the suite, and a
test stack still on `0001` fails every scenario at the first insert.

**Manual demo:** with the development stack up, sign in at <http://localhost:5173> as
`ada@collabhub.dev` / `collabhub`, open `#general`, type a few messages and watch them appear;
scroll up in a channel with more than fifty and watch older ones load without the view jumping;
open a second browser profile as `grace@collabhub.dev`, reload, and see Ada's messages — Grace has
never joined `#general` and does not need to (ruling 12). Real-time is Slice 5, so the reload is
the point, not a workaround.

**Done:** every scenario in `tests/bdd/features/messages.feature` green headed against the test
stack, `channels.feature` still green, ruff clean, the messaging integration suite green, the SPA
typechecking and building — and the working tree left dirty for you to commit.
