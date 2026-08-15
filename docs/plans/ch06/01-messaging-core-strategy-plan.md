# Messaging: core chat, end to end, driven by Gherkin

## Context

CollabHub has one finished service (Auth) and five skeletons. The Messaging service is a
24-line health-check app — no models, no migrations, no routers, no Socket.IO. The SPA is
598 lines of auth scaffold with three runtime dependencies and no test tooling at all.
There is no BDD anywhere in the repo.

This phase builds **core chat, end to end, demonstrable in a browser**: channels and
membership, send/edit/delete, history pagination, and real-time delivery — plus the React
UI to show it working. The specs are written first as Gherkin and drive the implementation
outside-in; the scenarios run full-stack through Playwright against the Docker Compose
stack, so "passing" and "demonstrable" are the same fact.

Threads, reactions, mentions, search, and read receipts are **out of scope** and deferred
to a later phase.

### Decisions settled in this phase

Four choices were made up front; each needs an ADR (`adr-writer` skill) and a status
update in `docs/design/07-open-decisions-register.md`.

| ID | Was | Now |
|---|---|---|
| **D24** | 🔴 Zustand vs RTK | **TanStack Query (server state) + Zustand (client state)** |
| **D8d** | 🔴 edit/delete windows | **No time window; author edits/deletes own, channel admin deletes any; soft-delete tombstones retained.** Retention (D16) stays open |
| doc 06 §2 | open | **Tailwind CSS v4** via `@tailwindcss/vite` |
| — | new | **pytest-bdd + Playwright Python** as the BDD harness |

D8a (single-level threading), D8b (`kind='dm'`), D8c (search proxy) stay 🟡 and untouched —
nothing in this scope depends on them.

---

## Reference points

Copy structure and idiom from these; do not invent new patterns.

- **Service layout / composition root** — `src/services/auth/auth/main.py`. Everything built
  from `Settings`, hung on `app.state`, `lifespan` disposes. Flat modules by concern, *not*
  `services/`+`repositories/`.
- **Domain layer** — `src/services/auth/auth/identities.py`. Plain async functions taking
  `AsyncSession` first, no FastAPI imports, raising domain exceptions the router translates.
- **Router idiom** — `src/services/auth/auth/routers/workspaces.py`. Private `_guard()`
  helpers at module top; signature order `page: PageParams`, `principal: ... = Depends(require_user)`,
  `session: ... = Depends(db_session)`; domain errors → `ProblemException` at the boundary.
- **Keyset pagination** — `identities.members_page` (`auth/identities.py:253`) +
  `shared/pagination.py` (`PageParams`, `page.fetch_limit`, `build_page`).
- **Schemas** — `auth/schemas.py`: `CamelModel` (responses) / `CamelRequest` (requests, no
  `populate_by_name`). `body.model_fields_set` for PATCH merge semantics (`routers/users.py:59`).
- **Migrations** — `auth/alembic.ini`, `auth/alembic/env.py`, `auth/migrations.py`,
  `auth/migrate.py`, hand-written `versions/0001_initial_schema.py`.
- **Test fixtures** — `src/services/auth/tests/conftest.py`: session-scoped
  `PostgresContainer("postgres:18", driver="asyncpg")` + `RedisContainer("redis:8")`,
  per-test `TRUNCATE ... RESTART IDENTITY CASCADE`, `build_settings(**overrides)`,
  `client` over `httpx.ASGITransport`.
- **Reuse, don't rebuild** — `shared.uuid7()`, `shared.install_problem_handlers`,
  `shared.install_cors`, `shared.install_security`, `shared.require_user`,
  `shared.JwksClient`, `shared.Denylist`, `shared.build_health_router`,
  `shared.postgres_check` / `redis_check`, `shared.pagination.*`.

---

## Phase 0 — Gherkin first

Write the specs before any implementation. These are the contract; everything after exists
to make them pass.

**Location:** `tests/bdd/` at repo root.
**Root `pyproject.toml`:** widen `testpaths = ["src/services"]` → `["src/services", "tests"]`;
add `bdd` to `markers`; add `pytest-bdd>=8.1` and `pytest-playwright>=0.7` to
`[dependency-groups] dev`.

```
tests/bdd/
  conftest.py            stack readiness probe, DB reset, Playwright contexts, sign-in
  features/
    channels.feature
    messages.feature
    realtime.feature
    permissions.feature
  steps/
    channel_steps.py
    message_steps.py
    realtime_steps.py
  pages/                 page objects wrapping data-testid selectors
    sign_in_page.py
    chat_page.py
```

### Scenario coverage to write

**`channels.feature`** — sign in as Ada and see the workspace; create a public channel and
land in it; created channel appears for another member; rename a channel as its admin;
non-admin rename is rejected; duplicate public channel name is rejected; archive a channel
and it leaves the list.

**`messages.feature`** — send a message and see it in the list; message shows author and
timestamp; a message over 8000 characters is rejected; scrolling up loads older messages
(cursor pagination, newest-first); edit own message and see the edited marker; cannot edit
someone else's message; delete own message and see the tombstone; channel admin deletes
another member's message.

**`realtime.feature`** — Ada sends, Grace sees it without reloading; Ada's edit and delete
propagate to Grace live; Grace only receives messages for channels she has joined; typing
indicator appears and clears; reconnect after a dropped connection recovers the stream.

**`permissions.feature`** — a non-member cannot open a private channel; a channel admin adds
a member and they see the channel; removing a member revokes their view; signing out and in
as a different user shows only that user's channels.

### Harness design

- **The Compose stack must already be running.** A session-scoped `stack_ready` fixture polls
  `/health/ready` on Auth and Messaging plus the SPA root, and fails with an explicit
  "run `docker compose up --build` first" message rather than a timeout. Cheaper and far
  faster to iterate on than spinning Compose up per run, and it is literally the demo
  environment.
- **Sign-in is the real Dex flow through Playwright** — navigate `/sign-in`, click, fill Dex's
  form (`ada@collabhub.dev` / `grace@collabhub.dev`, password `collabhub`), land back on `/`.
  This replaces the regex-based simulator in `auth/tests/dexflow.py` for browser tests.
  Cache Playwright `storage_state` per user for the session so sign-in runs once per user,
  not per scenario. *Verify during implementation that `session.ts` bootstraps from the
  HttpOnly refresh cookie on load; if it does not, fall back to a fresh sign-in per scenario.*
- **Isolation:** an autouse fixture truncates the messaging tables over a direct asyncpg
  connection to `localhost:${POSTGRES_PORT}` between scenarios. Auth data (users, workspace)
  is left intact so cached sign-in stays valid.
- **Two-user scenarios** use two Playwright browser contexts (Ada, Grace) in one browser.
- **Selectors are `data-testid` only.** Page objects own every selector; step definitions
  never contain a raw locator. This is what keeps browser BDD from being brittle — treat it
  as a hard rule when writing the React components in Phase 4.

---

## Phase 1 — `shared`: token verification off a raw string

`shared/security.py` verifies tokens through `Request`-bound helpers (`_bearer_token`,
`_verified_claims`, `_check_denylist`), so the Socket.IO handshake — which has a token but
no `Request` — cannot reuse `require_user`. This is the one genuine gap.

**Change:** extract the verification core into a request-free function:

```python
async def verify_user_token(context: SecurityContext, token: str) -> UserPrincipal: ...
```

Move the body of `RequireUser.__call__` (claims decode, `service:` subject rejection, `wsp`
parsing, denylist check, `UserPrincipal` construction) into it. `RequireUser.__call__`
becomes `_context(request)` + `_bearer_token(request)` + a call to the new function.
Export from `shared/__init__.py`. Behaviour is unchanged; add a test in
`src/services/shared/tests/test_security.py` covering the string-based path directly.

---

## Phase 2 — Messaging: data, domain, REST

**`src/services/messaging/pyproject.toml`** — add `python-socketio`, `alembic>=1.14`,
`httpx>=0.28`. `python-socketio` is not in `uv.lock` at all, so this needs a lock update.

**`messaging/settings.py`** — add `cors_allowed_origins: list[str] = []`. Add
`CORS_ALLOWED_ORIGINS` to the `messaging` service block in `docker-compose.yml` (only Auth
has it today) and confirm `.env.example` covers it.

**Files to create** (mirroring `src/services/auth/auth/`):

| File | Content |
|---|---|
| `db.py` | verbatim shape of `auth/db.py` — `build_engine`, `build_sessions`, `session` dependency |
| `models.py` | `Base`, `Channel`, `ChannelMember`, `Message` per the DDL in `docs/design/02-messaging-service.md` §4 |
| `schemas.py` | `CamelModel`/`CamelRequest` + channel and message DTOs |
| `channels.py` | domain: create, list, get, patch, archive, members add/remove, `is_member` / `is_admin` |
| `messages.py` | domain: create, edit, soft-delete, history page, `get` |
| `routers/channels.py` | the `/api/v1/channels` surface |
| `routers/messages.py` | `/api/v1/messages/{id}` GET/PATCH/DELETE |
| `migrations.py`, `migrate.py`, `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_initial_schema.py` | copies of Auth's, with a hand-written 0001 |
| `README.md`, `api.http` | as Auth ships |

**Schema for 0001** — full spec DDL for the three tables we need, including columns whose
features land later (`thread_root_id`, `attachments`, `last_read_id`) so there is no
migration churn. **Skip the `reactions` table** until reactions are built.

- Partial unique *index* `ux_channels_public_name ON channels(workspace_id, name) WHERE kind='public'`
- `ix_messages_channel_time ON messages(channel_id, id DESC) WHERE deleted_at IS NULL`
- `version int default 0` on `channels` and `messages` — optimistic concurrency
  (`WHERE id=:id AND version=:expected`, 0 rows → 409)
- UUID v7 PKs from `shared.uuid7()`, generated in the app. No FKs on cross-service IDs.

**Endpoints in scope** — `GET|POST /api/v1/channels`, `GET|PATCH|DELETE /api/v1/channels/{id}`,
`GET|POST /api/v1/channels/{id}/members`, `DELETE /api/v1/channels/{id}/members/{userId}`,
`GET|POST /api/v1/channels/{id}/messages`, `GET|PATCH|DELETE /api/v1/messages/{id}`.

**Rules that are easy to get wrong — enforce and test each:**
- `workspace_id` comes from `principal.workspace_id` (the `wsp` claim) and **never** from
  path, query, or body. Every query filters on it.
- Channel membership is not workspace membership → plain `require_user`, **not**
  `require_user_sensitive`. No route carries both `require_user` and `require_service`.
- Message history is cursor-paginated **newest-first**; `messages.id` is UUID v7 so a single
  descending keyset on `id` is already unique and matches the index. Never `OFFSET`.
- All lists return `{items, nextCursor}` via `build_page`.
- `deleted_at IS NULL` on every read.
- Body length checked against `settings.messaging_max_body_chars` → 400 `validation-error`.

**Deliberately deferred, with reasons:**
- **`jobs:index` producer (R3)** — nothing consumes it; the Worker is unbuilt and search is
  out of scope. The `version` column lands now anyway (it earns its place on optimistic
  concurrency alone), so adding the producer later is additive. Note this in the README.
- **`attachments` in the API** — column exists, not exposed; the Asset service is a skeleton.
- **`POST /api/v1/internal/messages/sweep`** — retention is D16 🔴.

**Tests** — `src/services/messaging/tests/`, flat, one file per surface, `pytestmark =
pytest.mark.integration`: `conftest.py` (lifted from Auth's, minus Dex; token minting helper
that signs an RS256 user token with a `StaticKeySource`), `test_channels.py`,
`test_members.py`, `test_messages.py`, `test_pagination.py`, `test_tenancy.py` (a token for
workspace A must not see workspace B's channels), `test_schema.py`.

---

## Phase 3 — Messaging: Socket.IO `/messaging`

**New `messaging/realtime.py`.**

- `socketio.AsyncServer(async_mode="asgi", client_manager=socketio.AsyncRedisManager(settings.redis_realtime_url), cors_allowed_origins=settings.cors_allowed_origins)`.
  R2 only — never R1 or R3.
- `main.py` keeps `create_app(settings) -> FastAPI` (so tests can use `httpx.ASGITransport`)
  and gains `build_asgi_app(settings)` returning
  `socketio.ASGIApp(sio, other_asgi_app=fastapi_app)`. `docker/messaging/Dockerfile` CMD
  becomes `uvicorn messaging.main:asgi_factory --factory`. `/health/live` still resolves
  through the wrapper, so the Compose healthcheck is unchanged.
- Add `docker/messaging/entrypoint.sh` mirroring `docker/auth/entrypoint.sh` so
  `RUN_MIGRATIONS=true` works.

**Handshake auth** — read the token from the handshake `auth` payload (`access_token` query
param as fallback, per Conventions §6), call `verify_user_token` from Phase 1, and store the
`UserPrincipal` in the Socket.IO session. Reject the connection otherwise. A connection
inherits the workspace of the token that opened it and never serves another (§5.4).

**Events** — client→server verbs, server→client past-tense facts:

| In | Out |
|---|---|
| `join_channel(channelId)` → authorize against Postgres, join room `channel:{id}` | `message_received(Message)` |
| `leave_channel(channelId)` | `message_edited(Message)` |
| `send_message({channelId, body})` → persist, broadcast, **return the Message via the ack callback** | `message_deleted({messageId, channelId})` |
| `edit_message({messageId, body})` | `user_typing({channelId, userId})` |
| `delete_message({messageId})` | |
| `typing({channelId})` — ephemeral, never persisted | |

Authorization for `send_message`/`edit_message`/`delete_message` is the same domain check
the REST routers use — call into `channels.py`/`messages.py`, do not duplicate the rules.
A client may only act on a channel it has joined; `join_channel` is where membership is
verified.

**Tests** — `test_realtime.py`, using `socketio.AsyncSimpleClient` against a uvicorn server
started on an ephemeral port with real Postgres and Redis containers.

---

## Phase 4 — Frontend: the chat UI

**Dependencies** — `@tanstack/react-query`, `zustand`, `socket.io-client`; dev:
`tailwindcss@4`, `@tailwindcss/vite`. Wire the Tailwind plugin into `vite.config.ts` and
replace `src/index.css` with `@import "tailwindcss";` plus a short token layer.

**New structure** (existing `src/lib/auth/*` is untouched):

```
src/
  lib/api/client.ts          bearer token + RFC 7807 unwrap, factored out of lib/auth/api.ts
  lib/api/messaging.ts       typed calls against VITE_MESSAGING_URL
  lib/realtime/socket.ts     socket.io-client → `${VITE_MESSAGING_URL}/messaging`, auth:{token}
  lib/realtime/useChannelSocket.ts
  stores/chat.ts             zustand: activeChannelId, connectionStatus, drafts
  features/chat/ChatLayout.tsx | ChannelList.tsx | ChannelHeader.tsx
                 MessageList.tsx | MessageItem.tsx | MessageComposer.tsx
                 TypingIndicator.tsx | CreateChannelDialog.tsx
```

- `App.tsx` gains a `/c/:channelId` route behind a real auth guard; `main.tsx` wraps in
  `QueryClientProvider`.
- **TanStack Query owns server state**: `useQuery` for the channel list, `useInfiniteQuery`
  for message history (newest-first, `nextCursor` as the page param). Socket events write
  into the query cache via `queryClient.setQueryData` — no parallel copy of the message list.
- **Zustand owns client state only** — active channel, connection status, per-channel drafts.
- **Optimistic send**: render immediately with a temp id, reconcile on the Socket.IO ack,
  roll back and surface the problem detail on failure.
- **Reconnect on token renewal and on workspace switch** — `session.ts` already renews ahead
  of expiry; the socket must be torn down and re-established with the new token, and on a
  workspace switch it must drop and reconnect (Conventions §5.4).
- **`data-testid` on every element the Gherkin steps touch**: channel list items, message
  rows, author, body, edited marker, composer input, send button, typing indicator,
  create-channel controls, error banner.

`.env.example` already carries `VITE_MESSAGING_URL`; nothing new is needed there.

---

## Phase 5 — Light up the scenarios

Implement step definitions and page objects against the running stack, working through the
features in the order written: `channels` → `messages` → `permissions` → `realtime`. Fix
what the scenarios expose rather than adjusting the scenarios to fit the implementation.

---

## Phase 6 — Record the decisions

- ADRs via the `adr-writer` skill, in `docs/adr/`: D24 (TanStack Query + Zustand), D8d
  (edit/delete semantics), Tailwind v4, and pytest-bdd + Playwright as the BDD approach.
- Update `docs/design/07-open-decisions-register.md`: D24 → 🟢, D8d → 🟢. D16 stays 🔴.
- Reflect D8d back into `docs/design/02-messaging-service.md` §9 and D24/styling into
  `docs/design/06-frontend-spa.md` §2.
- Update `src/frontend/README` material and root `README.md` with how to run the BDD suite.
- Confirm CLAUDE.md's Conventions notes still hold; add any new env var to `.env.example`.

---

## Verification

```bash
# Lint and format — repo rules: line length 100, py312
uv run ruff check . && uv run ruff format --check .

# Backend unit + integration (needs Docker; testcontainers)
uv run pytest src/services/messaging src/services/shared
uv run pytest -m "not integration"          # fast path, no Docker

# Frontend typecheck and build
cd src/frontend && npm run typecheck && npm run build

# Bring the demo stack up, then run migrations
docker compose up --build
docker compose exec messaging python -m messaging.migrate

# Full-stack Gherkin against the running stack
uv run pytest tests/bdd -m bdd
uv run pytest tests/bdd -m bdd --headed      # watch it drive the browser
```

**Manual demo** — sign in at <http://localhost:5173> as `ada@collabhub.dev` / `collabhub`,
create `#general`, open a second browser profile as `grace@collabhub.dev`, and confirm
messages, edits, deletes, and the typing indicator cross between the two windows live.

**Definition of done:** every scenario in `tests/bdd/features/` passes headed against
`docker compose up`, `ruff` is clean, and the backend integration suite is green.

**Not committed** — per CLAUDE.md the working tree is left dirty for you to review and
commit yourself.
