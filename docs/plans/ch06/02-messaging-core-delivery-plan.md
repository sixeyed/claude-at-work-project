# Delivery plan: messaging core chat in seven reviewable slices

## Context

[`01-messaging-core-strategy-plan.md`](./01-messaging-core-strategy-plan.md) is a good
technical strategy but a poor delivery schedule. It is layered — all Gherkin, then `shared`, then REST, then Socket.IO, then the whole
React UI — so nothing is demonstrable until the second-to-last phase and each phase is a diff
too large to review honestly.

This plan restructures the same scope into **seven vertical slices**. Each slice starts by
writing its Gherkin scenarios, ends with those scenarios green against `docker compose up`,
and is roughly one branch's worth of work. The technical detail (file layout, reference points,
rules, idiom to copy) is **not repeated here** — it stays in the strategy plan, which each slice
references.

---

> **Amended 2026-08-15, after Slice 1 shipped.** Validating this plan against the design docs
> turned up gaps it did not carry, and building it corrected some of its own assumptions. The
> details are in [`03-slice-01-implementation-plan.md`](./03-slice-01-implementation-plan.md);
> what changes for the *remaining* slices is:
>
> - **The BDD harness does not cache `storage_state`.** Refresh tokens rotate and Auth
>   reuse-detects, so a saved cookie is single-use and replaying it revokes the whole chain.
>   Sign in once per user into a browser context that stays alive for the session; isolate
>   scenarios by truncating messaging tables only. Run against the Compose frontend, never
>   `npm run dev` — StrictMode fires the session restore twice.
> - **Both users must switch to the shared `CollabHub Demo` workspace.** Every account lands in
>   its own workspace on sign-in, and two people in two personal workspaces cannot see each
>   other's channels.
> - **The frontend feature folder is `features/channels/`**, per doc 06 §3 — not `features/chat/`.
> - **Typed clients are generated** from `src/frontend/openapi/messaging.json` (register D23),
>   not hand-written. Regenerate the JSON whenever a route or schema changes.
> - **ADRs land in the slice that makes the decision**, not in Slice 7. D24, Tailwind (D26) and
>   the BDD harness (D27) were recorded with Slice 1; Slice 7 keeps D8d and the docs sweep.
> - **`.env.example` needed no new variable** — `CORS_ALLOWED_ORIGINS` was already there and
>   simply not passed to the `messaging` container.
> - **Step modules must be named `test_*.py`**, or pytest does not collect them and the feature
>   file silently never runs.
> - **The suite runs against a throwaway stack**, brought up with
>   `-f docker-compose.yml -f docker-compose.test.yml` and running *alongside* the
>   development one. It truncates the messaging tables between scenarios, so pointed at the
>   development stack it would delete hand-made channels. The override moves the five ports
>   reached from the host (SPA 5183, Auth 8011, Messaging 8012, Dex 5566, Postgres 5442);
>   the harness addresses only those, so it cannot reach the wrong stack.

> **Amended 2026-08-16, after Slices 2 to 6 shipped.** One block for all six, assembled from
> each slice plan's "Gaps closed". The slice paragraphs below are **not** rewritten — they are
> the record of what this plan said when it was written, and that is what makes an amendment
> worth reading. Only the corrections a future reader of *this* document would otherwise be
> misled by are here; the full findings stay in the per-slice plans.
>
> **Ownership moved.**
> - **The D8d ADR and register flip are Slice 4's, not Slice 7's.** Decision 1 below still says
>   "recorded in the D8d ADR in Slice 7". CLAUDE.md records a decision in the slice that makes
>   it, and a register reading 🔴 for three slices' worth of code built on the answer is the
>   drift Slice 7 exists to prevent. Slice 7 keeps the confirmation pass and the sweep.
> - **Conventions §6 and doc 02 §4.1 are Slice 5's**, for the same reason: Messaging and Canvas
>   would otherwise share `AsyncRedisManager`'s default pub/sub channel on one Redis, and that
>   is a decision Slice 5's code forces rather than something to defer to a sweep.
>
> **Facts that were already stale.**
> - **`last_read_id` shipped in `0001_channels`.** Decision 2 lists it among the columns whose
>   features arrive later, as though it were still to come.
> - **The frontend folder is `features/channels/`**, not `features/chat` — the Slice 5 and 6
>   paragraphs still imply the old path. Slice 1 moved it.
> - **Doc 06 §2 and the root README's BDD instructions shipped in Slice 1**, so the Slice 7
>   paragraph claims work that is already done.
> - **`.env.example` needed nothing across all six slices.** `x-service-common` sets
>   `env_file: .env`, so every variable reaches every service whether or not the explicit
>   `environment:` block names it — the explicit list is only for names that are renamed or
>   interpolated.
>
> **Rules the paragraphs get wrong, and which a builder following them would get wrong too.**
> - **Visibility gates reading *and* writing; membership gates administration.** Doc 02 §3.1
>   marked the message routes "channel member", and nothing in this scope lets anyone join a
>   channel themselves — so a membership guard would have made a public channel readable by
>   nobody but its creator. `messages.py` guards on `channels.get_visible`, never
>   `channels.is_member`, and **posting creates no membership row**.
> - **Slice 6's "a client may only act on a channel it has joined" is wrong twice.** It is the
>   wrong test, for the reason above; and a Socket.IO room is per-`sid` state that a reconnect
>   destroys, so a send across a reconnect would race its own `join_channel`. Every inbound
>   write authorizes on `get_visible`, in the same transaction as the write.
> - **`edit_message` carries `version`.** Doc 02 §3.2 omits it; without it the socket would be
>   the way around the optimistic-concurrency rule the REST route enforces.
> - **`message_deleted` carries the full redacted `Message`**, not `{messageId, channelId}` —
>   a client holding an id cannot render a tombstone.
> - **`DELETE /messages/{id}` returns 200 with the tombstone, not 204**, for the same reason.
> - **Slice 3's read path ships the tombstone redaction complete**, before anything can set
>   `deleted_at`; Slice 4 adds only the writes. The Slice 4 paragraph reads as though the
>   redaction were its work.
> - **`ix_messages_channel_time` is created without its `WHERE deleted_at IS NULL` predicate**
>   — decision 1 anticipated this — **and `ix_messages_thread` is not created at all**, which
>   decision 2 does not mention.
>
> **Two harness rules the plan does not carry.**
> - **`steps/conftest.py` holds every step more than one feature file uses.** pytest-bdd
>   resolves a step from the calling module and from `conftest.py` and **never** from a sibling
>   `test_*.py`, so the alternative is four copies of `Given Ada is signed in`.
> - **`go_offline()` is context-wide and the contexts are session-scoped**, so the `ada` and
>   `grace` fixtures restore the network on teardown. A scenario that failed while offline
>   would otherwise take every later scenario with it.

## Two decisions to settle before writing code

Both were surfaced while slicing and neither is answered by the strategy plan.

### 1. Tombstones vs. `deleted_at IS NULL` (affects Slice 3's migration)

The Gherkin says "delete own message and see the tombstone". CLAUDE.md says every read filters
`deleted_at IS NULL`. Those conflict: filtered out, a tombstone survives only until reload.

**Recommendation:** history returns soft-deleted rows with `body` redacted server-side and
`deletedAt` set; the client renders "This message was deleted". This is a documented,
message-specific exception to the blanket rule, recorded in the D8d ADR in Slice 7. It follows
that `ix_messages_channel_time` is created **without** the `WHERE deleted_at IS NULL` predicate
(the strategy plan assumes the partial form) — the read path no longer matches it. Decide this
in Slice 3, when migration `0002` is written, not in Slice 4 when the tombstone is rendered.

### 2. Migrations land per slice, not all in `0001`

The strategy plan writes one `0001` covering every table. Split it: `0001` = `channels` +
`channel_members` (Slice 1), `0002` = `messages` (Slice 3). Columns whose *features* land later
still ship with their table (`last_read_id`, `thread_root_id`, `attachments`, `version`) so
there is no churn within a table. `reactions` is not created at all.

---

## How every slice runs

Identical protocol, so it isn't restated per slice:

1. **Gherkin first.** Write the `.feature` scenarios for the slice — the scenario titles listed
   below, fleshed out into Given/When/Then. Write nothing else: no step definitions, no page
   objects, no service code.
2. 🛑 **Stop and wait for approval.** Present the finished `.feature` files and **do not start
   building.** The scenarios are the contract for the slice, and they are the cheapest thing in
   it to change — so expect several rounds of "that's not the behaviour I want", "add the case
   where…", "drop that one". Rewrite and present again. Only an explicit go-ahead moves the
   slice to step 3; silence, a question, or a comment on one scenario is not a go-ahead for
   the rest.
3. **Build outside-in** until they pass — step definitions and page objects, then service and
   UI code. Backend integration tests (`pytestmark = pytest.mark.integration`, testcontainers)
   land with the code they cover. Run the scenarios first and watch them fail for the right
   reason (missing step, missing endpoint — not a broken harness).
4. **Never edit a scenario to fit the implementation.** Fix the implementation. If a scenario
   turns out to be genuinely wrong, that is a step-2 conversation to reopen, not a silent edit.
5. **Selectors are `data-testid` only**, owned by page objects. No raw locator in a step
   definition — this is the rule that keeps browser BDD from rotting.
6. **Exit criteria** for every slice: its scenarios green headed against
   `docker compose up --build`, `uv run ruff check . && uv run ruff format --check .` clean,
   `uv run pytest src/services/messaging src/services/shared` green,
   `cd src/frontend && npm run typecheck && npm run build` clean.
7. **Branch per slice** (`feature/messaging-s1-channels`, …). Per CLAUDE.md: create the branch,
   leave the tree dirty, **never commit** — that's the user's.

So each slice has **two review points, not one**: the scenarios before any code exists, and the
working slice at the end. The first is the one that saves the most time.

Rules enforced in every slice that touches the API, tested each time:
`workspace_id` comes from `principal.workspace_id` (the `wsp` claim), never from path, query or
body · cursor pagination only, `{items, nextCursor}` via `build_page` · plain `require_user`
(channel membership is not workspace membership, so not `require_user_sensitive`) · RFC 7807 on
every non-2xx · camelCase JSON, snake_case SQL · UUID v7 from `shared.uuid7()` in the app.

---

## Slice 1 — Channels: create and list

The fattest slice, because it carries the harness. Review it as two commits: **(a) BDD harness**,
**(b) the feature**.

**Demo:** sign in at <http://localhost:5173> as Ada, create `#general`, see it in the sidebar;
Grace signs in and sees it too.

**Gherkin** — `tests/bdd/features/channels.feature`
- Ada signs in and sees her workspace *(smoke — proves the harness end to end)*
- Ada creates a public channel and lands in it
- The new channel appears in Grace's channel list
- Creating a public channel with a name already in use is rejected
- A blank channel name is rejected

**Harness** (strategy plan Phase 0 verbatim)
- Root `pyproject.toml`: `testpaths = ["src/services", "tests"]`, `bdd` marker,
  `pytest-bdd>=8.1` + `pytest-playwright>=0.7` in `[dependency-groups] dev`.
- `tests/bdd/conftest.py` — `stack_ready` probe (fails with "run `docker compose up --build`
  first", not a timeout), per-scenario truncate of messaging tables over asyncpg to
  `localhost:${POSTGRES_PORT}`, two Playwright contexts, real Dex sign-in with `storage_state`
  cached per user. Verify `session.ts` bootstraps from the HttpOnly refresh cookie on load;
  if not, fall back to a fresh sign-in per scenario.
- `tests/bdd/pages/{sign_in_page,chat_page}.py`, `tests/bdd/steps/channel_steps.py`.

**Backend**
- `messaging/pyproject.toml`: `alembic>=1.14`, `httpx>=0.28` (`python-socketio` waits for S5).
- `db.py`, `models.py` (`Channel`, `ChannelMember`), `schemas.py`, `channels.py` (create,
  `list_page`, get, `is_member`, `is_admin`), `routers/channels.py`
  (`GET|POST /api/v1/channels`, `GET /api/v1/channels/{id}`).
- `main.py` composition root per `auth/main.py`; `migrations.py`, `migrate.py`, `alembic.ini`,
  `alembic/env.py`, `alembic/versions/0001_channels.py` (incl. partial unique index
  `ux_channels_public_name`, `version` column).
- `settings.cors_allowed_origins`; `CORS_ALLOWED_ORIGINS` on the `messaging` block in
  `docker-compose.yml`; confirm `.env.example`.
- `docker/messaging/entrypoint.sh` mirroring `docker/auth/entrypoint.sh` so `RUN_MIGRATIONS=true`
  works, wired into `docker/messaging/Dockerfile`.
- Tests: `conftest.py` (lifted from Auth's, minus Dex; RS256 token minting via `StaticKeySource`),
  `test_channels.py`, `test_tenancy.py`, `test_schema.py`.

**Frontend**
- Deps: `@tanstack/react-query`, `zustand`; dev `tailwindcss@4`, `@tailwindcss/vite`. Wire the
  Tailwind plugin in `vite.config.ts`; `src/index.css` → `@import "tailwindcss";` + token layer.
- `lib/api/client.ts` — bearer + RFC 7807 unwrap, factored out of `lib/auth/api.ts`.
- `lib/api/messaging.ts` (`listChannels`, `createChannel`), `stores/chat.ts` (`activeChannelId`),
  `features/chat/{ChatLayout,ChannelList,CreateChannelDialog}.tsx`.
- `App.tsx` gains `/c/:channelId` behind a real auth guard; `main.tsx` wraps in
  `QueryClientProvider`.

---

## Slice 2 — Channel administration and membership

**Demo:** Ada renames and archives a channel, adds Grace to a private one, removes her again —
Grace's sidebar changes to match.

**Gherkin** — extend `channels.feature`; add `tests/bdd/features/permissions.feature`
- A channel admin renames a channel
- A non-admin cannot rename a channel
- An admin archives a channel and it leaves the list
- An admin adds a member and they see the channel
- Removing a member revokes their view of the channel
- A non-member cannot open a private channel
- Signing in as a different user shows only that user's channels

**Backend** — `PATCH|DELETE /channels/{id}`, `GET|POST /channels/{id}/members`,
`DELETE /channels/{id}/members/{userId}`; domain rename/archive/add/remove; private-channel
visibility in the list query; optimistic concurrency on `version`
(`WHERE id=:id AND version=:expected`, 0 rows → 409). Tests: `test_members.py`, extend
`test_channels.py` and `test_tenancy.py`; 409 covered at integration level, not in Gherkin.

**Frontend** — `ChannelHeader` (rename, archive), member panel, error banner rendering the
problem `title`/`detail`, archived channels dropped from the list.

---

## Slice 3 — Messages: send and read history

**Demo:** Ada types into `#general` and her messages appear; scrolling up pulls older ones.
Grace sees them **after a reload** — real-time is Slice 5, and the scenario says so out loud.

**Gherkin** — `tests/bdd/features/messages.feature`
- Ada sends a message and sees it in the channel
- A message shows its author and timestamp
- A message over 8000 characters is rejected
- Scrolling up loads older messages
- Grace sees Ada's message after reloading *(placeholder for the Slice 5 live version)*

**Backend** — migration `0002_messages` (see decision 2 above; index predicate per decision 1);
`Message` model; `messages.py` domain (create, `history_page`, get); `POST|GET
/channels/{id}/messages`, `GET /messages/{id}`. History is **newest-first keyset on `id DESC`** —
`messages.id` is UUID v7 so a single descending key is unique and matches the index. Never
`OFFSET`. Body length against `settings.messaging_max_body_chars` → 400 `validation-error`.
Tests: `test_messages.py`, `test_pagination.py`.

**Frontend** — `useInfiniteQuery` over `nextCursor`; `MessageList`, `MessageItem`,
`MessageComposer`; scroll-to-top loads the next page and holds scroll position.

---

## Slice 4 — Messages: edit and delete (settles D8d)

**Demo:** Ada edits a message and it shows "edited"; she deletes another and a tombstone stays;
as channel admin she deletes one of Grace's.

**Gherkin** — extend `messages.feature`
- Ada edits her own message and it shows an edited marker
- Ada cannot edit Grace's message
- Ada deletes her own message and a tombstone remains after reload
- A channel admin deletes another member's message
- A member cannot delete someone else's message

**Backend** — `PATCH|DELETE /messages/{id}`; author-only edit, author-or-channel-admin delete,
**no time window** (D8d); `edited_at`/`deleted_at` set, `version` bumped; deleted rows returned
with `body` redacted server-side. Extend `test_messages.py`.

**Frontend** — inline edit affordance on own messages, edited marker, tombstone rendering,
admin delete control.

---

## Slice 5 — Real-time delivery (broadcast only)

The socket infrastructure and the read path. Writes still go over REST; the routers publish to
the room after commit. That is not throwaway work — the publisher and the REST write path are
both permanent (doc 02 §3.1 keeps `POST /channels/{id}/messages` as the REST fallback), and it
means a failing scenario here can only be the socket layer.

**Demo:** two browser windows side by side. Ada sends, edits, deletes — Grace's window updates
without a reload.

**Gherkin** — `tests/bdd/features/realtime.feature`
- Grace sees Ada's message without reloading
- Ada's edit propagates to Grace live
- Ada's delete propagates to Grace live
- Grace does not receive messages for a channel she has not joined
- The stream recovers after the connection drops

**Backend**
- `shared/security.py`: extract `async def verify_user_token(context, token) -> UserPrincipal`
  from `RequireUser.__call__`; `__call__` becomes `_context` + `_bearer_token` + the new
  function. Export it; test the string path in `src/services/shared/tests/test_security.py`.
  Behaviour unchanged.
- `python-socketio` dependency (**not currently in `uv.lock`** — needs a lock update).
- `messaging/realtime.py`: `AsyncServer(async_mode="asgi",
  client_manager=AsyncRedisManager(settings.redis_realtime_url), cors_allowed_origins=...)` —
  **R2 only**. Handshake auth from the `auth` payload (`access_token` query fallback per
  Conventions §6) via `verify_user_token`; principal stored in the Socket.IO session; a
  connection keeps the workspace of the token that opened it (§5.4). `join_channel` authorizes
  against Postgres and joins `channel:{id}`; `leave_channel` leaves. `publish_message_received`
  / `_edited` / `_deleted` helpers.
- REST routers call the publishers after commit.
- `main.py` keeps `create_app(settings) -> FastAPI` (so tests keep using `ASGITransport`) and
  gains `build_asgi_app` returning `socketio.ASGIApp(sio, other_asgi_app=app)`;
  `docker/messaging/Dockerfile` CMD → `uvicorn messaging.main:asgi_factory --factory`.
  `/health/live` still resolves through the wrapper, so the Compose healthcheck is unchanged.
- Tests: `test_realtime.py` using `socketio.AsyncSimpleClient` against uvicorn on an ephemeral
  port with real Postgres and Redis containers.

**Frontend** — `lib/realtime/socket.ts` (→ `${VITE_MESSAGING_URL}/messaging`, `auth: {token}`),
`lib/realtime/useChannelSocket.ts`; connection status in `stores/chat.ts`; socket events write
into the TanStack cache with `queryClient.setQueryData` — **no parallel copy of the message
list**; socket torn down and re-established on token renewal and on workspace switch (§5.4).

---

## Slice 6 — Socket write path, optimistic send, typing

The half where the bugs live, reviewed on its own.

**Demo:** Ada's message renders the instant she hits enter and is confirmed silently; a rejected
send rolls back with an error; Grace sees "Ada is typing…" appear and clear.

**Gherkin** — extend `realtime.feature`
- A typing indicator appears for Grace and clears when Ada stops
- A sent message appears immediately and is confirmed
- A rejected send is rolled back and the error is shown

**Backend** — inbound `send_message` / `edit_message` / `delete_message` calling **the same
domain functions the REST routers call** (no duplicated rules), each returning the `Message` via
the Socket.IO ack; `typing` → `user_typing` fan-out, ephemeral, never persisted. A client may
only act on a channel it has joined. Extend `test_realtime.py`.

**Frontend** — composer emits over the socket, renders optimistically with a temp id, reconciles
on ack, rolls back and surfaces the problem detail on failure; `TypingIndicator`; typing emits
debounced.

---

## Slice 7 — Record the decisions

Docs only — a fast review, but it is the slice that stops the register drifting.

**Reduced 2026-08-15.** D24, Tailwind (D26) and the BDD harness (D27) were decided *and
recorded* in Slice 1, because CLAUDE.md says a decision gets written down when it is made
and leaving the register 🔴 for six slices while building on the answer is the drift this
slice exists to prevent. What is left here:

- ADR via the `adr-writer` skill in `docs/adr/`: **D8d** edit/delete semantics, no time
  window, tombstones retained in history (incl. the `deleted_at IS NULL` exception from
  decision 1) — decided in Slice 4, so recorded there if that slice gets there first.
- `docs/design/07-open-decisions-register.md`: D8d → 🟢. D16 stays 🔴.
  D8a/D8b/D8c untouched at 🟡.
- Reflect D8d into `docs/design/02-messaging-service.md` §9 and D24 + styling into
  `docs/design/06-frontend-spa.md` §2.
- README updates: root, `src/frontend`, `src/services/messaging` — how to run the BDD suite;
  note why the `jobs:index` producer is deliberately absent.
- Confirm `.env.example` carries every variable introduced (`CORS_ALLOWED_ORIGINS` for messaging).

---

## Out of scope throughout

Threads, reactions, mentions, search, read receipts · the `jobs:index` producer on R3 (nothing
consumes it; the Worker is unbuilt — the `version` column lands anyway on optimistic-concurrency
merit, so adding the producer later is additive) · `attachments` in the API (column exists, Asset
is a skeleton) · `POST /api/v1/internal/messages/sweep` (retention is D16 🔴) · the `reactions`
table.

---

## Verification

Per slice, the exit criteria above. End to end, after Slice 7:

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -m "not integration and not bdd"        # fast path, no Docker
uv run pytest src/services/messaging src/services/shared
cd src/frontend && npm run typecheck && npm run build

docker compose up --build
docker compose exec messaging python -m messaging.migrate

uv run pytest tests/bdd -m bdd
uv run pytest tests/bdd -m bdd --headed               # watch it drive the browser
```

**Manual demo:** sign in at <http://localhost:5173> as `ada@collabhub.dev` / `collabhub`, create
`#general`, open a second browser profile as `grace@collabhub.dev`, and confirm messages, edits,
deletes and the typing indicator cross between the windows live.

**Done:** every scenario in `tests/bdd/features/` green headed against `docker compose up`, ruff
clean, backend integration suite green — and the working tree left dirty for you to commit.
