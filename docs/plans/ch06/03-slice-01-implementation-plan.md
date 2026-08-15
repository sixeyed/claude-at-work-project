# Slice 1 — Channels: create and list

## Context

[`02-messaging-core-delivery-plan.md`](./02-messaging-core-delivery-plan.md) restructures the
messaging build into seven vertical slices. We are about to implement Slice 1, so this plan does two
things: it **validates the delivery plan against the design docs** and closes the gaps found, and it
**specifies Slice 1** in enough detail to build from.

Slice 1 is the fattest slice because it carries the BDD harness as well as the feature. It ends with
Ada signing in at <http://localhost:5173>, creating `#general`, and Grace seeing it.

Validation found **nine gaps**. Four were settled in conversation; the rest are recorded below with
the call made. Two are corrections to the *design docs*, not just the plan — Slice 1 writes them
back.

---

## Gaps closed

### 1. Public channels are workspace-readable (design-doc correction)

Doc 02 §3.1 marks `GET /channels/{id}` "channel member" and never defines the list-visibility rule
at all — so Slice 1's own demo (Grace sees Ada's new channel) is unsatisfiable as specified.

| Case | Result |
|---|---|
| `GET /channels` | non-archived `public` in the token's `wsp` ∪ any kind where I'm a member |
| `GET /channels/{id}` public, same workspace | 200 (membership not required) |
| `GET /channels/{id}` private, member | 200 |
| `GET /channels/{id}` private, non-member | **404** `not-found` — never 403; 403 leaks existence |
| `GET /channels/{id}` any other workspace | 404 `not-found` |

Membership gates *messages*, from Slice 3 on. There is no self-join in this slice — Slice 2's
admin-driven `POST /channels/{id}/members` is how Grace becomes a member.
**Write this back into `docs/design/02-messaging-service.md` §3.1.**

### 2. Channel DTO — does not exist in any design doc

Doc 02 §3.1 specifies a `Message` DTO and no `Channel` DTO. Defined here, consistent with the
Message DTO's style, and written back into doc 02 §3.1:

```jsonc
// Channel
{ "id": "uuid", "name": "general", "topic": "string|null",
  "kind": "public|private|dm", "createdBy": "uuid",
  "createdAt": "...", "updatedAt": "...", "archivedAt": "...|null",
  "version": 0,
  "myRole": "admin|member|null" }   // caller's channel role; null = not a member
```

`workspaceId` is deliberately absent — it is the token's `wsp` and nothing else. `version` and
`myRole` ship now, unused, so Slice 2's optimistic concurrency and admin-only controls do not churn
the contract. Create request is `{ name, topic?, kind? }`.

### 3. Name validation — only one number exists in the whole spec

Conventions §4.2's worked example says *"Channel name must be between 1 and 80 characters."* That is
the only rule anywhere. Adopted: **trim, then require 1–80 characters**; whitespace-only is blank. No
charset/slug rule — the design gives none, so do not invent one.

`kind` accepts `public` and `private` in this slice; **`dm` is rejected** (400) — D8b is 🟡 and DM
creation has different semantics (no name). Uniqueness is `(workspace_id, name)` among
`kind='public'` only, enforced by the partial unique index and caught as **409 `conflict`** from the
`IntegrityError` — not a pre-check `SELECT`, which races.

### 4. Creator becomes a channel admin — implied by three facts, stated by none

`POST /channels` inserts `channel_members(channel_id, user_id=principal.user_id, role='admin')` in
the same transaction. Without it the creator cannot read back a private channel, and Slice 2's
"channel admin renames a channel" has no admin.

### 5. Channels soft-delete via `archived_at`, not `deleted_at`

Doc 02's DDL gives `channels.archived_at` and no `deleted_at`, which contradicts CLAUDE.md's blanket
"queries filter `deleted_at IS NULL`". The DDL wins for this table: **every channel read filters
`archived_at IS NULL`.** Note it in the migration and in doc 02 §4. (This is separate from the
*messages* tombstone question, which stays in Slice 3/4.)

### 6. Channel list ordering — unspecified

Alphabetical, keyset on **`(name, id)`** ascending. `name` alone is not unique (private channels may
repeat one), and `shared/pagination.py` is explicit that the sort key must be unique.

### 7. Two indexes the spec omits

The spec DDL gives `channel_members` only its composite PK `(channel_id, user_id)`, so "which
channels is this user in?" — the sidebar's query — has no supporting index. Migration `0001` adds
both, and doc 02 §4 gains them:

```sql
CREATE INDEX ix_channel_members_user ON channel_members (user_id, channel_id);
CREATE INDEX ix_channels_workspace_name ON channels (workspace_id, name, id)
    WHERE archived_at IS NULL;
```

### 8. `storage_state` caching is unsafe — the harness design changes

The strategy plan assumes Playwright `storage_state` cached per user. That breaks, and worse than
failing: `auth/sessions.py` rotates the refresh token *and* reuse-detects, revoking the whole chain
(`if row.rotated_to is not None: await _revoke_descendants(...)`). `App.tsx` calls
`session.restore()` on every page load, so a saved cookie is spent on first use and the second
scenario revokes the user's session.

**Sign in once per user per pytest session and keep the browser context alive** — the cookie rotates
in place. Isolation comes from truncating messaging tables between scenarios, not from fresh
sign-ins. Also: run BDD against the **Compose nginx frontend on :5173**, never `npm run dev` — React
`StrictMode` double-fires `restore()` in dev, firing two `/refresh` calls on one cookie.

### 9. Typed clients are generated from OpenAPI (D23 🟡 honoured)

Not hand-written. Messaging dumps its spec to a committed JSON file; `openapi-typescript` generates
the types; `openapi-fetch` provides the client. Keeps `npm run build` free of any Python dependency.

### Also corrected in the delivery plan

- **ADRs move from Slice 7 to Slice 1.** D24, Tailwind v4 and pytest-bdd+Playwright are *decided in
  Slice 1*; CLAUDE.md says record a decision when it is made, and D24 is 🔴 — leaving the register
  lying for six slices is exactly the drift Slice 7 exists to prevent. Slice 7 keeps D8d (decided in
  Slice 4) and the docs/README sweep.
- **`features/chat` → `features/channels`**, matching doc 06 §3.
- **`.env.example` needs no new variable.** `CORS_ALLOWED_ORIGINS=["http://localhost:5173"]` is
  already there; it is simply not passed to the `messaging` container. The delivery plan implies a
  new var.
- **Root `pyproject.toml` `testpaths = ["src/services"]`** means `tests/bdd` is invisible to
  `uv run pytest` until widened.

---

## How the slice runs

Unchanged from the delivery plan, and the gate is real:

1. Write `tests/bdd/features/channels.feature` — **scenarios only**, no steps, no page objects, no
   service code.
2. 🛑 **Stop and wait for explicit approval.** Expect rounds of revision.
3. Then build outside-in; watch the scenarios fail for the right reason first.
4. Never edit a scenario to fit the implementation.
5. `data-testid` selectors only, owned by page objects.
6. Branch `feature/messaging-s1-channels`. **Never commit** — leave the tree dirty.

**Scenarios** (per the delivery plan): Ada signs in and sees her workspace *(smoke)* · Ada creates a
public channel and lands in it · the new channel appears in Grace's channel list · a duplicate public
channel name is rejected · a blank channel name is rejected.

Tenancy isolation and the 409 race stay at integration level, not in Gherkin.

---

## Work

### A. BDD harness (review as its own commit)

- Root `pyproject.toml`: `testpaths = ["src/services", "tests"]`; add `bdd` marker; add
  `pytest-bdd>=8.1` and `pytest-playwright>=0.7` to `[dependency-groups] dev`.
- `tests/bdd/conftest.py`:
  - session `stack_ready` — poll `:8001/health/ready`, `:8002/health/ready` and
    `http://localhost:5173/` (the frontend has **no** Compose healthcheck), failing with "run
    `docker compose up --build` first", not a timeout.
  - session `ada_context` / `grace_context` — one Playwright context each, real Dex sign-in once.
  - autouse function-scoped truncate of `channel_members, channels` over asyncpg to
    `localhost:${POSTGRES_PORT}`. Auth tables are left alone so the sign-ins stay valid.
- **Keep every step definition synchronous.** Root pytest sets `asyncio_mode = "auto"`, so an
  `async def` step becomes an asyncio test and Playwright's sync API cannot run inside a live loop.
  Wrap the truncate in `asyncio.run(...)`.
- `tests/bdd/pages/{sign_in_page,chat_page}.py`, `tests/bdd/steps/channel_steps.py`. Reuse the Dex
  form knowledge in `src/services/auth/tests/dexflow.py` — its regex-parsed form action is the
  fragile part and is already solved.

### B. Backend — `src/services/messaging/`

- `pyproject.toml`: add `alembic>=1.14` → `uv lock` regen. (`python-socketio` waits for Slice 5.)
- `settings.py`: add `cors_allowed_origins: list[str] = []` and
  `auth_internal_audience: str = "collabhub-internal"`.
- `db.py` — copy `auth/db.py` verbatim in shape. Note routers commit **explicitly**; the dependency
  does not, despite its docstring.
- `models.py` — `Base`, `Channel`, `ChannelMember` per doc 02 §4 DDL. `Timestamp =
  TIMESTAMP(timezone=True)`; UUID PK with **no default** (`shared.uuid7()` in the app); `version`
  with `server_default="0"`; no FKs on `workspace_id`, `created_by`, `user_id`.
- `schemas.py` — `CamelModel`/`CamelRequest` copied from `auth/schemas.py` (note the deliberate
  asymmetry: requests are *not* `populate_by_name`), plus `ChannelResponse`, `ChannelListResponse`,
  `CreateChannelRequest`.
- `channels.py` — domain, no FastAPI imports, `session: AsyncSession` first: `create`, `list_page`,
  `get_visible`, `is_member`, `is_admin`. Model on `auth/identities.py`; `list_page` mirrors
  `members_page` (`identities.py:253`) using `PageRequest.fetch_limit` + `build_page`.
- `routers/channels.py` — `GET|POST /api/v1/channels`, `GET /api/v1/channels/{id}`. Private `_guard`
  helpers at module top; signature order `page: PageParams`, then
  `principal: UserPrincipal = Depends(require_user)`, then `session: ... = Depends(db_session)`.
  Plain **`require_user`** — channel writes are explicitly *not* in the fail-closed set (doc 02
  §3.1). `workspace_id` comes only from `principal.workspace_id`.
- `main.py` — currently 31 lines with a health router and nothing else. It needs `install_cors`,
  `install_problem_handlers` and `install_security` (all three absent today), a `lifespan` disposing
  engine/redis/JWKS, and `app.state`. Use **`JwksClient(settings.auth_jwks_url)`**, not Auth's
  `StaticKeySource`, and pass `denylist=Denylist(redis_client)` on R1.
- `migrations.py`, `migrate.py`, `alembic.ini` (at the *service* root), `alembic/env.py`,
  `alembic/versions/0001_channels.py` — copies of Auth's. Partial unique index as an index, not a
  constraint: `op.create_index("ux_channels_public_name", "channels", ["workspace_id", "name"],
  unique=True, postgresql_where=sa.text("kind = 'public'"))`, plus the two indexes from gap 7.
- `openapi.py` — `python -m messaging.openapi` dumps `create_app(...).openapi()` to stdout using
  placeholder settings, so generation needs no running stack.
- `docker/messaging/entrypoint.sh` mirroring `docker/auth/entrypoint.sh`, wired into
  `docker/messaging/Dockerfile` (`ENTRYPOINT` + keep the existing `CMD`) so `RUN_MIGRATIONS=true`
  works. Messaging has no entrypoint today.
- `docker-compose.yml`: add `CORS_ALLOWED_ORIGINS: ${CORS_ALLOWED_ORIGINS}` to the `messaging`
  environment block.
- Tests (`pytestmark = pytest.mark.integration`): `conftest.py` lifted from `auth/tests/conftest.py`
  minus Dex, with RSA key + `StaticKeySource` token minting copied from
  `src/services/shared/tests/test_security.py:43-94`; `test_channels.py`, `test_tenancy.py` (a
  workspace-A token must not see workspace-B channels), `test_schema.py`.

### C. Frontend — `src/frontend/`

- Deps: `@tanstack/react-query`, `zustand`, `openapi-fetch`; dev `tailwindcss@4`,
  `@tailwindcss/vite`, `openapi-typescript`. Wire the Tailwind plugin in `vite.config.ts`;
  `src/index.css` → `@import "tailwindcss";` plus a short token layer.
- `openapi/messaging.json` (committed) + `npm run generate:api` → `src/types/messaging.ts`.
- `lib/api/client.ts` — bearer + RFC 7807 unwrap, factored out of `lib/auth/api.ts`. **The current
  `ProblemError` drops the `errors` map**; it must carry `status`, `detail`, `title` *and* `errors`,
  because doc 06 §7 requires the errors map to render on forms and the blank-name scenario asserts
  on it. Refactor `lib/auth/api.ts` onto it.
- `lib/api/messaging.ts` — `openapi-fetch` client against `VITE_MESSAGING_URL` (declared in
  Compose/`.env.example` but read nowhere today).
- `stores/chat.ts` (Zustand: `activeChannelId`),
  `features/channels/{ChatLayout,ChannelList,CreateChannelDialog}.tsx`.
- `App.tsx` gains `/c/:channelId` behind a real auth guard extracted from the inline check in
  `Home`; `main.tsx` wraps in `QueryClientProvider`. Note `SignIn` currently ignores
  `status === 'loading'`, so it flashes before redirecting — fix it, it is a Playwright race.
- `tsconfig.json` is strict with `verbatimModuleSyntax` (use `import type`) and
  `allowImportingTsExtensions` (existing imports carry `.tsx`).
- **`data-testid` on every element the steps touch** — there are currently zero in the repo.

### D. Decisions recorded (moved up from Slice 7)

- ADRs via the `adr-writer` skill in `docs/adr/`: **D24** TanStack Query + Zustand · **Tailwind v4** ·
  **pytest-bdd + Playwright** as the BDD harness.
- `docs/design/07-open-decisions-register.md`: D24 → 🟢. Add a note against D23 that types are
  generated per its default.
- `docs/design/02-messaging-service.md`: §3.1 gains the Channel DTO and the visibility rule (gaps
  1–2); §4 gains the two indexes and the `archived_at` note (gaps 5, 7).
- `docs/design/06-frontend-spa.md` §2: styling = Tailwind v4; state = TanStack Query + Zustand.
- Amend [`02-messaging-core-delivery-plan.md`](./02-messaging-core-delivery-plan.md) for the
  corrections above (harness sign-in, `features/channels`, generated clients, ADR timing,
  `.env.example` already covered).

---

## Verification

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -m "not integration"                      # fast path, no Docker
uv run pytest src/services/messaging src/services/shared
cd src/frontend && npm run typecheck && npm run build

docker compose up --build                               # frontend on :5173, messaging on :8002
uv run pytest tests/bdd -m bdd
uv run pytest tests/bdd -m bdd --headed                 # watch it drive the browser
```

Migrations run from `docker/messaging/entrypoint.sh` on `up`; `docker compose exec messaging python
-m messaging.migrate` re-runs them by hand.

**Manual demo:** sign in at <http://localhost:5173> as `ada@collabhub.dev` / `collabhub`, create
`#general`, open a second browser profile as `grace@collabhub.dev`, and confirm `#general` is in her
sidebar. Both accounts join the `CollabHub Demo` workspace on first sign-in, so they share a `wsp`.

**Done:** every scenario in `tests/bdd/features/channels.feature` green headed against
`docker compose up`, ruff clean, messaging integration suite green — and the tree left dirty.
