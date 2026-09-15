# Test Pyramid B — Integration framework — TDD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project rules override those skills.** **Never commit or stage** — leave the worktree dirty,
> move files with plain `mv`. Where a skill says "commit", this plan says "leave uncommitted".
> **Red first**: every framework change starts with a failing test, run and recorded here.
>
> **Run note (2026-09-15).** Elton handed this over with "get everything built and tested, make
> assumptions for any questions rather than stopping to ask". So the red runs are recorded below
> rather than stopped on, and every call the handoff marked "ask Elton" is made here, with its
> reasoning, in *This plan's own calls*. Review them in the final report.

**Goal:** One Postgres (a database per service), one Redis (a database index per role) and a
lazily started Elasticsearch, all through testcontainers and registered once from the `testkit`
plugin; the duplicated token, app, truncation and container helpers move into `testkit`; the
service conftests shrink to what is theirs; the Worker gets a consumer harness.

**Architecture:** `testkit.plugin` loads `testkit.containers` and `testkit.tokens` as plugins
(`pytest_plugins`), so each session fixture has **one** definition and therefore one container
per run. A unit test that so much as depends on a container fixture is refused at collection.
Pure helpers (`images`, `databases`, `apps`, `db`) are plain modules a conftest imports.

**Tech Stack:** Python 3.12, pytest 9.1 (`pytester`), testcontainers 4.15
(`testcontainers.community.{postgres,redis,elasticsearch}`), elasticsearch-py 9 async,
redis-py asyncio, SQLAlchemy 2 async + asyncpg, uvicorn, PyJWT.

**Spec:** [01-test-pyramid-design.md](01-test-pyramid-design.md) row **B**, Framework 2; the
handoff [03-test-pyramid-handoff-integration.md](03-test-pyramid-handoff-integration.md),
workstream 1. The backfill is [its own plan](05-test-pyramid-integration-backfill-implementation-plan.md).

**Worktree:** `/Users/elton/scm/manning/caw-test-pyramid-integration`, branch
`feature/test-pyramid-integration`, from `main` at `5c15626`.

**Baseline**, measured 2026-09-15 in this worktree: `-m unit` collects **123**, `-m integration`
collects **287**; no `pytest.mark.integration` left outside testkit; a full run starts two
`postgres:18` and three `redis:8` containers plus Dex.

---

## This plan's own calls (register D34)

1. **Container fixtures are registered once, from the plugin (option A).** `testkit.plugin`
   declares `pytest_plugins = ["testkit.containers", "testkit.tokens"]`. One fixture definition
   means one container per session; importing fixtures into each conftest (option B) would create
   a definition per service and a container per service.
2. **A unit test that depends on a container fixture stops the run at collection**, with a
   `pytest.UsageError`, rather than relying on Docker being unreachable. `DOCKER_HOST` alone is not
   a guarantee: testcontainers honours `~/.testcontainers.properties` and Docker contexts first, and
   a Unix-socket Docker slips past the socket guard. The check reads `item.fixturenames`, which is
   the transitive closure, so indirect dependencies are caught too.
3. **One Postgres, a database per service.** `service_database(server, name, upgrade)` runs
   `CREATE DATABASE <name>` and that service's `upgrade_to_head`. The service conftest keeps the
   `postgres_dsn` fixture name, so no test changes.
4. **One Redis, an index per role**: R1 cache `/0`, R2 realtime `/1`, R3 streams `/2`. Function
   fixtures `redis_cache` and `redis_streams` flush only their own index. **Pub/Sub is not scoped
   by database index**, so R2 separation is checked through the connection's `db=` in
   `CLIENT LIST`, never by channel. The old `redis_client` fixture is renamed `redis_cache` in the
   tests that used it, so every test names the role it writes through.
5. **Elasticsearch starts only when a test asks for it**, like Compose runs it: single-node,
   security off, 512 MB heap, plus `action.destructive_requires_name=false` so the per-test
   fixture can drop every index with one wildcard call.
6. **Garage is deferred** to the slice that introduces the `ObjectStore` protocol. Nothing uses
   object storage yet (Asset is a skeleton), and a fixture with no consumer is untested code.
   `images.py` pins no Garage tag until then; the drift test checks what is pinned.
7. **One signing key and one `Tokens` per session**, `kid = "test-key"`, issuer
   `https://auth.test`. Messaging's `KEY_ID` of `messaging-test-key` was only ever a label.
8. **`testkit` depends on `collabhub-worker` and `collabhub-messaging`** as well as Auth: Messaging's
   search tests build the `messages` index with the Worker's own mapping (see the backfill plan,
   call 4), and a dev-only package may depend on anything.

## What no test in this plan covers

- **"One Postgres for the whole run"** is proven by counting containers during a full run
  (Task 9), not by a test: pytest guarantees one value per session fixture definition, and
  collection proves there is one definition.
- **The deprecated-import rule** is proven by `grep`, not a test.

## Global Constraints

- Python `>=3.12,<3.13`; bash 3.2 for `scripts/`.
- `testcontainers[postgres,redis,elasticsearch]>=4.15`; imports only from
  `testcontainers.community.*` / `testcontainers.core.*`.
- Images: `postgres:18`, `redis:8`, `docker.elastic.co/elasticsearch/elasticsearch:9.4.3`,
  `ghcr.io/dexidp/dex:v2.45.1` — `docs/platform/versions.md` and `docker-compose.yml` win.
- `uv lock` then `uv sync --locked --all-packages` after any `pyproject.toml` change.
- `ruff check` / `ruff format` clean; the edit hook blocks.
- Never `git add`, `git mv`, `git commit`.
- `from tests… import` is banned (TID251).

## File map

| Path | Change | Responsibility |
|---|---|---|
| `pyproject.toml` | modify | `testcontainers[postgres,redis,elasticsearch]>=4.15` |
| `src/services/testkit/pyproject.toml` | modify | deps: worker, messaging, elasticsearch, redis, sqlalchemy, uvicorn, pyjwt |
| `src/services/testkit/testkit/images.py` | create | pinned image tags |
| `src/services/testkit/testkit/containers.py` | create | session fixtures `postgres_server`, `redis_server`, `elasticsearch_url`; function fixtures `redis_cache`, `redis_streams`, `elasticsearch` |
| `src/services/testkit/testkit/databases.py` | create | `PostgresServer`, `service_database()` |
| `src/services/testkit/testkit/tokens.py` | create | `Tokens`; fixtures `signing_key`, `tokens` |
| `src/services/testkit/testkit/apps.py` | create | `asgi_client()`, `serve()` |
| `src/services/testkit/testkit/db.py` | create | `truncate()` |
| `src/services/testkit/testkit/plugin.py` | modify | `pytest_plugins`; container fixtures refused in unit tests |
| `src/services/testkit/testkit/dex.py` | modify | `DEX_IMAGE` from `images` |
| `src/services/testkit/tests/unit/test_images.py` | create | drift guard against `docker-compose.yml` |
| `src/services/testkit/tests/unit/test_plugin.py` | modify | two tests for call 1 and call 2 |
| `src/services/testkit/tests/unit/test_tokens.py` | create | claims of both token kinds |
| `src/services/testkit/tests/integration/test_containers.py` | create | smoke test per fixture |
| `src/services/{auth,messaging,shared}/tests/integration/conftest.py` | rewrite | slimmed |
| `src/services/shared/tests/integration/test_security.py` | modify | `Tokens` replaces `mint`/`user_token`/`service_token` |
| `src/services/*/tests/integration/test_*.py` | modify | `redis_client` → `redis_cache` |
| `src/services/worker/tests/integration/conftest.py` | create | `run_consumer` harness |
| `CLAUDE.md`, `docs/design/00-platform-conventions.md` §11 | modify | fixtures and containers as built |
| `docs/design/07-open-decisions-register.md` | modify | D34 |
| `docs/adr/260915-integration-tests-share-one-container-per-store.md` | create | via `adr-writer` |

---

## Task 1: Image pins and their drift guard

**Files:** create `testkit/images.py`, `tests/unit/test_images.py`; modify `testkit/dex.py`.

**Interfaces — produces:** `POSTGRES: str`, `REDIS: str`, `ELASTICSEARCH: str`, `DEX: str`.

- [ ] **Step 1: Write `test_images.py`.** It loads `docker-compose.yml` with `yaml.safe_load`
  (no network) and asserts `services.postgres.image == POSTGRES`, each of `redis-cache`,
  `redis-rt`, `redis-streams` equals `REDIS`, `elasticsearch` equals `ELASTICSEARCH`, `dex`
  equals `DEX`; and that `testkit.dex.DEX_IMAGE is DEX` so Dex has one pin.
- [ ] **Step 2: Run red.** `uv run pytest src/services/testkit/tests/unit/test_images.py`
  → collection error, `ModuleNotFoundError: No module named 'testkit.images'`.
- [ ] **Step 3: Create `images.py`; make `dex.py` import `DEX` as `DEX_IMAGE`.**
- [ ] **Step 4: Run green.** Same command → all pass.

## Task 2: Plugin registers container and token fixtures once; unit tests may not use containers

**Files:** modify `testkit/plugin.py`, `tests/unit/test_plugin.py`; create empty-bodied
`testkit/containers.py` and `testkit/tokens.py` first so the red is about behaviour.

**Interfaces — produces:** `CONTAINER_FIXTURES = frozenset({"postgres_server", "redis_server",
"elasticsearch_url"})`; `pytest.UsageError` text containing
`is a unit test but depends on a container fixture`.

- [ ] **Step 1: Add two pytester tests.**
  - `test_the_container_fixtures_come_from_testkit_without_a_conftest` — inner repo, run
    `--fixtures`; `stdout.fnmatch_lines(["*postgres_server*", "*redis_server*",
    "*elasticsearch_url*", "*tokens*"])`, and each fixture listed once.
  - `test_a_unit_test_that_depends_on_a_container_stops_the_run` — inner unit test with a local
    fixture that requests `redis_server`; `ret == USAGE_ERROR` and stderr names the file.
- [ ] **Step 2: Run red.** `uv run pytest src/services/testkit/tests/unit/test_plugin.py`
  → the two new tests fail (fixtures not listed; exit 0/1 rather than 4); 11 existing pass.
- [ ] **Step 3: Implement.** `pytest_plugins = ["testkit.containers", "testkit.tokens"]` in
  `plugin.py`; in `pytest_collection_modifyitems`, for a `unit` item, raise if
  `CONTAINER_FIXTURES & set(item.fixturenames)`. Fill in the fixtures (Tasks 3–5).
- [ ] **Step 4: Run green.** 13 pass.

## Task 3: Postgres — one server, a database per service

**Files:** create `testkit/databases.py`, `testkit/db.py`; fill `postgres_server` in
`containers.py`; smoke test in `testkit/tests/integration/test_containers.py`.

**Interfaces — produces:**
- `@dataclass(frozen=True) class PostgresServer: host: str; port: int; user: str; password: str;
  def dsn(self, database: str) -> str` (asyncpg URL).
- `service_database(server: PostgresServer, name: str, upgrade: Callable[[str], Awaitable[None]]) -> str`
  — validates `name` against `^[a-z][a-z0-9_]*$`, creates it (AUTOCOMMIT), runs `upgrade(dsn)`,
  returns the DSN.
- `async truncate(engine: AsyncEngine, tables: Sequence[str]) -> None` —
  `TRUNCATE … RESTART IDENTITY CASCADE`.
- session fixture `postgres_server -> PostgresServer`.

- [ ] **Step 1: Smoke test** `test_each_service_database_is_its_own` — create `alpha` and `beta`
  with an upgrade that creates a table only in `alpha`; assert `beta` does not have it, and both
  DSNs share host and port.
- [ ] **Step 2: Run red** → `fixture 'postgres_server' not found` / `ImportError`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run green.** `uv run pytest src/services/testkit/tests/integration -k database`.

## Task 4: Redis — one server, an index per role

**Interfaces — produces:**
- `class RedisRole(IntEnum): CACHE = 0; REALTIME = 1; STREAMS = 2`
- `@dataclass(frozen=True) class RedisServer: host: str; port: int; def url(self, role: RedisRole) -> str`
- session fixture `redis_server -> RedisServer`; function fixtures `redis_cache`,
  `redis_streams -> redis.asyncio.Redis` (decode_responses, flushed index on entry).

- [ ] **Step 1: Smoke test** `test_role_clients_sit_on_their_own_indexes` — a key written
  through `redis_cache` leaves `DBSIZE` 0 on `redis_streams`; `CLIENT INFO` reports `db=0` and
  `db=2` for the two clients; `redis_server.url(RedisRole.STREAMS)` ends `/2`.
- [ ] **Step 2–4:** red (fixture missing), implement, green.

## Task 5: Elasticsearch, started on demand

**Interfaces — produces:** session fixture `elasticsearch_url -> str`; function fixture
`elasticsearch -> AsyncElasticsearch` that deletes every open/closed index before the test and
closes the client after.

- [ ] **Step 1: Smoke test** `test_elasticsearch_answers_and_starts_clean` — create an index,
  and in a second test assert it is gone.
- [ ] **Step 2–4:** red, implement (`ElasticSearchContainer(ELASTICSEARCH)` with
  `discovery.type=single-node`, `ES_JAVA_OPTS=-Xms512m -Xmx512m`,
  `action.destructive_requires_name=false`), green. Root `pyproject.toml` gets the
  `elasticsearch` extra; `uv lock && uv sync --locked --all-packages`.

## Task 6: `Tokens`, `asgi_client`, `serve`

**Interfaces — produces:**
- `testkit.tokens`: constants `ISSUER = "https://auth.test"`, `KEY_ID = "test-key"`,
  `USER_AUDIENCE = "collabhub"`, `INTERNAL_AUDIENCE = "collabhub-internal"`; `class Tokens` with
  class attributes `ADA`, `GRACE`, `WORKSPACE`, `OTHER_WORKSPACE` (uuid), and
  `__init__(key, *, issuer=ISSUER, key_id=KEY_ID)`, `key_source() -> StaticKeySource`,
  `encode(claims: dict, *, kid: str | None = None, lifetime=15 min) -> str` (adds `iss`, `aud`
  default user, `iat`, `exp`, `jti` unless given; a claim of `None` is dropped),
  `mint(*, user_id=ADA, workspace_id=WORKSPACE, name="Ada Lovelace", email="ada@collabhub.dev",
  roles=("member",), lifetime=15 min, kid=None, **overrides) -> str`,
  `service(name="worker", scopes=("assets:write-variants",), **overrides) -> str`,
  `header(**overrides) -> dict[str, str]`; fixtures `signing_key` (session) and `tokens`.
- `testkit.apps`: `asgi_client(app, *, base_url="http://test") -> AbstractAsyncContextManager[httpx.AsyncClient]`;
  `serve(app) -> AbstractAsyncContextManager[str]` yielding `http://127.0.0.1:<port>`.

- [ ] **Step 1: Unit test `test_tokens.py`** — decode without verification: a user token carries
  exactly `iss aud iat exp jti sub name email wsp roles` with `aud == "collabhub"`; a service token
  has `aud == "collabhub-internal"`, `sub == "service:worker"`, `scp`; an override of `None` removes
  the claim; `kid` header is `test-key`.
- [ ] **Step 2: Run red** → `ImportError: cannot import name 'Tokens'`.
- [ ] **Step 3: Implement** both modules; move the `realtime_url` docstring rationale into `serve`.
- [ ] **Step 4: Green.**

## Task 7: Slim the conftests onto the shared fixtures

- [ ] **Shared:** conftest deleted — `redis_cache` comes from testkit. `test_security.py` uses
  `tokens` (its `mint`, `user_token`, `service_token`, `ISSUER`, `KEY_ID`, `USER_ID`,
  `WORKSPACE_ID` go); `other_key` stays local as `Tokens(other_key)`.
- [ ] **Auth:** `postgres_dsn` = `service_database(postgres_server, "auth", upgrade_to_head)`;
  `redis_url` = `redis_server.url(RedisRole.CACHE)`; `engine` truncates through `testkit.db`;
  `client` through `asgi_client`. Dex fixture unchanged.
- [ ] **Messaging:** `postgres_dsn` on database `messaging`; `build_settings` takes a
  `RedisServer` and sets the three role URLs; `client`, `client_for`, `realtime_url` use `apps`;
  `Tokens`, `signing_key`, `tokens` come from testkit; `ada`/`grace` stay.
- [ ] **Rename** `redis_client` → `redis_cache` in every test using it.
- [ ] **Run** `scripts/test.sh integration -- src/services/shared`, `… auth`, `… messaging`:
  28, 105, 154 pass.

## Task 8: Worker harness

**Files:** create `src/services/worker/tests/integration/conftest.py` and a smoke test
`test_harness.py`.

**Interfaces — produces:** fixture `run_consumer` —
`run_consumer(handlers: Mapping[str, Handler], *, stream: str = JOBS_INDEX, **config) -> AbstractAsyncContextManager[StreamConsumer]`,
defaults `consumer="test"`, `batch_size=16`, `visibility_timeout_seconds=1`, `max_attempts=3`,
`dead_letter_maxlen=100`, `block_ms=100`; starts `run(stop)` as a task on R3 and on exit sets
`stop` and awaits it (bounded). Fixture `jobs` — helper over `redis_streams`:
`enqueue(job_type, payload | dict) -> JobEnvelope`, `enqueue_raw(data: str)`,
`await drained(timeout=10)` (stream empty and no pending), `dead_letters() -> list[dict]`.

- [ ] Smoke test: a handler recording envelopes receives an enqueued job and the stream drains.
- [ ] Red (fixture missing), implement, green.

## Task 9: Prove it and record it

- [ ] `uv run pytest -m unit -q` — all pass.
- [ ] Per service `scripts/test.sh integration -- src/services/<svc>` for testkit, shared, auth,
  messaging, worker — all pass.
- [ ] Full `scripts/test.sh integration` in the background while sampling
  `docker ps --filter ancestor=postgres:18 -q | wc -l` and the same for `redis:8`: max 1 each.
- [ ] `grep -rn "testcontainers\.\(postgres\|redis\|elasticsearch\)" src` prints nothing.
- [ ] Records: register D34, CLAUDE.md Testing, Conventions §11, ADR.

---

## After merging `main` (2026-09-15)

The unit handoff landed first ([plan 04](04-test-pyramid-unit-framework-and-backfill-implementation-plan.md)).
`main` at `bd712b1` was merged in as a fast-forward of the branch pointer — the branch had no
commits of its own — with this branch's uncommitted edits to `CLAUDE.md` and Conventions §11
re-applied by three-way `git merge-file`, both clean. Nothing was staged or committed.

| | Before the merge (this plan) | After |
|---|---|---|
| Unit (pytest) | 136 | **209** — plan 04's 196 plus this plan's 13 |
| Integration, existing | 287 | **278** — plan 04 trimmed nine parametrize rows that duplicated unit tests |
| Integration, total | 326 | **317** on first run after the merge, **315** after the backfill's own trims (see the backfill plan) |

`testkit` gained `fakes.py` from plan 04 — the unit layer's module; nothing here uses it. The
edit hook's worktree fix (`.claude/hooks/lint.sh`) came with the merge.

## Red and green log

### Red

| Task | Command | Result | Why |
|---|---|---|---|
| 1 | `uv run pytest src/services/testkit/tests/unit` | collection error | `ImportError: cannot import name 'images' from 'testkit'` |
| 6 | same run | collection error | `ModuleNotFoundError: No module named 'testkit.tokens'` |
| 2 | `uv run pytest src/services/testkit/tests/unit/test_plugin.py` | **2 failed, 11 passed** | `--fixtures` listed no `postgres_server` (`assert 0 == 1`); the unit test depending on `redis_server` exited `TESTS_FAILED` (1) with `fixture 'redis_server' not found`, not `USAGE_ERROR` (4). The 11 existing plugin tests stayed green |

**Deviation, stated plainly:** Tasks 3–5's fixtures were written in the same step as Task 2's
green, so their smoke tests passed on first run (`4 passed in 26.08s`). The red that stands for
them is Task 2's "fixture not found".

### Green

| Run | Result |
|---|---|
| `uv run pytest -m unit` | **136 passed** (123 before + 13 new: 2 plugin, 7 images, 4 tokens) |
| `uv run pytest -m integration src/services/testkit` | 4 passed |
| `uv run pytest -m integration src/services/shared` | 28 passed |
| `uv run pytest -m integration src/services/auth` | 105 passed in 35.88s |
| `uv run pytest -m integration src/services/messaging` | 154 passed in 35.91s |

### Task 9 — proof

| Check | Result |
|---|---|
| `scripts/test.sh integration` (every service, one session), sampling `docker ps --filter ancestor=<image>` every 2 s | **326 passed in 88.10s**; peak containers **postgres:18 = 1, redis:8 = 1, elasticsearch:9.4.3 = 1** (Dex 1, as before). Before: 2 Postgres, 3 Redis |
| `scripts/test.sh lint unit` | ruff, conventions, eslint, tsc, helm all pass; **136 passed** |
| `grep -rn "testcontainers\.\(postgres\|redis\|elasticsearch\)" src` | no output |
| Conftests | Auth: database, tables, settings, Dex, app. Messaging: database, tables, `build_settings`, apps, `ada`/`grace`. Shared: none. Worker: `run_consumer`, `jobs` |

326 = 287 existing + testkit 4 + Worker 15 + Messaging 19 + Auth 1.

**After merging `main`**, same checks: `scripts/test.sh integration` **315 passed in 93.14s**,
peak containers postgres:18 = 1, redis:8 = 1, elasticsearch = 1; `scripts/test.sh lint unit`
passes with pytest **209** and Vitest **97**. 315 = 278 existing + testkit 4 + Worker 13 +
Messaging 19 + Auth 1. (The worktree's `src/frontend/node_modules` predated the merge and `tsc`
could not find Vitest's types until `npm ci`; `test.sh` only installs when the folder is
missing.)

### Found on the way

- **The plugin's early `import shared` cost coverage.** `testkit.tokens` imported `shared` at
  plugin load, before pytest-cov starts, and the unit report dropped `shared`'s import-time lines
  (`CoverageWarning: Module shared was previously imported, but not measured`; TOTAL 48%). The
  import moved inside `Tokens.key_source`; the warning is gone and TOTAL is back to 55%.

- **`testkit.containers` escaped assert rewriting** (`PytestAssertRewriteWarning: Module already
  imported`), because `plugin.py` imported `CONTAINER_FIXTURES` from it before pytest registered
  it as a plugin. The constant moved into `plugin.py`.
- **`Tokens.mint(roles=None)` crashed** on `list(None)` — a mistake in the rewritten
  `test_security.py`, which passed `roles=None` it never needed. The argument was removed.
- **`redis_client` is gone.** Every test that used it now names its role: `redis_cache`.
