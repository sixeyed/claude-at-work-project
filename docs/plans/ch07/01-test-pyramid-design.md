# Test pyramid — design

Approved 2026-09-15. Decisions 1 and 6 were amended to say that testcontainers starts every
dependency. Elton decided the shape: **unit tests for all functionality, integration tests for
the service layer, BDD for end-to-end key user journeys**. This document plans the frameworks that
shape needs. The first implementation plan is
[02-test-pyramid-a-layout-and-testkit-implementation-plan.md](02-test-pyramid-a-layout-and-testkit-implementation-plan.md).

## Where it stands today

Collected on `main` at `fe345be`:

| Layer | Tests | Where |
|---|---|---|
| unit (`not integration and not bdd`) | **112** | shared 50, auth 43, messaging 12, health checks for the rest |
| integration (`integration`) | **287** | messaging 154, auth 105, shared 28 |
| bdd | **43** | 34 scenarios, with outlines expanded |

That is not a pyramid. There are two and a half integration tests for every unit test. The
specific causes are:

1. **The rules can only be reached through the database.** `validate_name` is a pure function,
   but its only tests go over HTTP against Postgres
   (`test_invalid_names_are_rejected_with_a_reason_per_rule`). The authorisation rules in
   `messages.edit` and `messages.delete` are pure decisions, but they sit inline in an async
   function *after* a database fetch, so no test can reach them without a session.
2. **The layer is chosen by a marker, and the default is unit.** A test that forgets
   `pytestmark = pytest.mark.integration` lands in the unit layer. Nothing stops a unit test from
   opening a socket or reaching Docker.
3. **Three conftests copy the same fixtures.** Containers, the truncation helper, token minting
   and the ASGI client are copied across auth, messaging and shared. They can't be shared by import,
   because every service has a `tests` package. Even the imports are spelled two ways:
   `testcontainers.postgres` in messaging, `testcontainers.community.postgres` in auth. A full run
   starts two Postgres containers and three Redis containers.
4. **There are no fixtures for Elasticsearch or Garage.** So the Worker (`consumer.py`, its
   handlers, `index.py`) and Messaging's `search.py` have **no tests at any layer** beyond health
   checks.
5. **The frontend has no tests.** It has 33 source files. Some of the logic is plainly unit-shaped:
   the TanStack cache updaters in `useMessages.ts`, `problemFrom` in `client.ts`, the session state
   machine in `session.ts`.
6. **About half of the BDD suite checks field rules.** Blank names, 80 characters, 8000
   characters, "cannot edit Grace's message": these belong lower down, and most of them are already
   covered there.
7. **`scripts/test.sh` doesn't run BDD.** The suite is a README step. CLAUDE.md treats that as a
   bug once the suite is a layer CI depends on.
8. **Conventions §11 describes four layers** (unit, integration, contract, acceptance), not three.

## The three layers

| | Unit | Integration | End-to-end |
|---|---|---|---|
| **Proves** | a rule, a mapping, a wire shape, an app's wiring | one service at its public boundary behaves correctly against the stores it owns | a key user journey works through a real browser and the whole stack |
| **Python** | pytest | pytest + testcontainers | pytest-bdd + Playwright (D27) |
| **Frontend** | Vitest + Testing Library + MSW | — | covered by the same journeys |
| **Runs against** | nothing: no Docker, no network (enforced) | real Postgres / Redis / Elasticsearch / Garage / Dex in containers; the service in-process | the throwaway Compose stack |
| **Substitutes allowed** | recorders for things we own at the edge (`RecordingServer`), typed MSW handlers | tokens minted with a local key instead of calling Auth; a static JWKS | none |
| **Never** | a fake database session, a fake Redis | mocks of the service's own stores | a scenario that only restates a field rule |
| **Command** | `scripts/test.sh unit` | `scripts/test.sh integration` | `scripts/test.sh e2e` |

**"The service layer" means a service's public boundary**, driven in-process against its real
stores:

- **REST:** the FastAPI app on `httpx.ASGITransport`.
- **Socket.IO:** uvicorn on an ephemeral port.
- **Worker:** `StreamConsumer` reading a real Redis stream and writing to a real Elasticsearch.

A test may call a domain function directly with a real session only for SQL behaviour the API
can't reach deterministically, such as two concurrent renames. See decision 1.

### Where a test goes

| Behaviour | Layer | Example today |
|---|---|---|
| Validation rule | unit | `validate_name`, `validate_body` |
| Authorisation *decision* (who may) | unit, on the extracted policy | edit: state before authorship |
| That a route *applies* the decision and maps it to 404/403/409 | integration, one test per route | `test_a_non_author_cannot_edit` |
| SQL: keyset cursor, partial unique index, forward-only upsert, unread count, tenancy filter | integration | `test_public_names_collide_regardless_of_case` |
| Problem Details shape, pagination encoding, ID generation | unit | `shared/tests/test_problems.py` |
| OpenAPI document and DTO shape (what D23 generates types from) | unit | `test_the_api_declares_a_route_to_mark_a_channel_read` |
| Job payload contract, producer ↔ Worker | unit, both sides against `contracts` models | *(none yet)* |
| Which room and payload a socket emit targets | unit, with `RecordingServer` | `test_read_markers.py` |
| Socket connect, auth handshake, fan-out across connections | integration | `test_realtime.py` |
| Worker handler writes and deletes an ES document; retry and dead-letter over Streams | integration | *(none yet)* |
| React component behaviour, hook cache updates | unit (Vitest) | *(none yet)* |
| CORS, `VITE_` values baked into the bundle, migration on container start, OIDC redirects through Dex, two browsers live | end-to-end | `channels.feature` sign-in |

### Making rules unit-testable: a functional core, not fake repositories

The edit rule today:

```python
message = await _visible(session, ...)          # SQL — visibility
if message is None: return None
if message.deleted_at is not None: raise AlreadyDeletedError(message_id)
if message.author_id != user_id:   raise NotAuthorError(message_id)
```

The pattern is to pull the decision out as a pure function over values that are already loaded,
and to leave the async function as the shell that fetches and writes:

```python
def check_editable(message: Message, *, user_id: uuid.UUID) -> None:
    """State, then authorship — that order is the security property."""
    if message.deleted_at is not None:
        raise AlreadyDeletedError(message.id)
    if message.author_id != user_id:
        raise NotAuthorError(message.id)
```

SQLAlchemy models construct without a session (`test_read_markers.py` already builds a
`Channel`), so the unit test needs nothing faked. Visibility stays a SQL predicate and is proven at
the integration layer.

The pattern is applied **when a slice touches a module**, not in a big-bang refactor. The first
worked example, message edit and delete, comes with the backfill: the framework plans add no
tests for existing behaviour.

## Framework 1 — Python unit

pytest 9.1.1 is already in place. Four things are added.

**Layout decides the layer.** Each service gets `tests/unit/` and `tests/integration/`. A
collection hook in the testkit plugin (framework 2) marks items by path, and a test file anywhere
else under a service's `tests/` is a **collection error**. The per-file `pytestmark` lines go, and
"forgot the marker" can't happen any more. Container fixtures live in
`tests/integration/conftest.py`, so a unit test can't even request one.

**The network is off in the unit layer.** pytest-socket 0.8.1 disables sockets for every item
marked `unit`, with `allow_unix_socket=True` because asyncio's self-pipe on macOS is an `AF_UNIX`
socketpair. The plugin also points `DOCKER_HOST` at `tcp://docker.invalid:1` for each unit test,
so a Docker client fails at once rather than finding the Unix socket. This lives in the plugin, not
in `test.sh`, so a bare `uv run pytest` behaves the same as the script. The whole current unit
layer already passes with sockets blocked: 112 tests in 6.5s.

**Coverage is reported, not gated.** pytest-cov 7.1.0 runs on the unit layer, with a terminal
report and `coverage.xml`. No threshold for now: a floor is set after the backfill has measured
one, not guessed first.

**Shared test helpers are imported from `testkit`, never from `tests`.** No service's `tests`
directory has an `__init__.py`, so `tests` is a single namespace package spanning all of them.
`from tests.conftest import …` binds to whichever service sorts first, which is Auth today. Ruff's
banned-api rule (TID251) makes that import a lint error.

## Framework 2 — Python integration: the `testkit` plugin

A new dev-only workspace member, `src/services/testkit` (distribution `collabhub-testkit`,
module `testkit`). It is registered as a pytest plugin through an entry point, so every service
gets it without a `conftest.py` import:

```toml
[project.entry-points.pytest11]
collabhub = "testkit.plugin"
```

It sits in the root `dev` dependency group, not in `dependencies`, and no service image installs
it.

```
src/services/testkit/testkit/
  plugin.py      layer-by-directory hook, unit socket and Docker guard                  (plan A)
  dex.py         Dex's image, accounts and config; start_dex()                         (plan A)
  dexflow.py     driving a real sign-in through Dex — moved from auth/tests            (plan A)
  auth.py        Auth's test configuration and build_settings — moved from its conftest (plan A)
  images.py      pinned image tags — unit-tested against docker-compose.yml so they can't drift
  containers.py  session fixtures: postgres_server, redis_server, elasticsearch_url, garage
  databases.py   service_database(name, upgrade) — CREATE DATABASE per service, run its migrations
  tokens.py      Tokens: user tokens (aud collabhub) and service tokens (aud collabhub-internal)
  apps.py        asgi_client(app), serve(app) — uvicorn on an ephemeral port, readiness-polled
  db.py          truncate(engine, tables)
  fakes.py       RecordingServer (unit layer)
```

Plan A moves Dex and Auth's helpers early because moving the tests forces it: five Auth test
files import them from `tests`. Everything else waits for plan B, which rewrites the conftests
for the shared containers anyway. Row factories wait for the backfill, which is when a second
test first needs one.

**One Postgres per session, a database per service.** This mirrors "every service owns its own
database", and a full run starts one container instead of two. **One Redis, a database index per
role** (R1 `/0`, R2 `/1`, R3 `/2`). Today all three roles share `/0`, so a key that crosses roles
passes unnoticed.

**testcontainers-python starts every dependency.** It uses the library's module where one exists
(`testcontainers.community.postgres`, `.redis` and `.elasticsearch`, not the deprecated
top-level paths Messaging imports today). Otherwise it uses `DockerContainer`. An integration test
never relies on the Compose stack or on a container someone started by hand.

| Fixture | Image | Built from |
|---|---|---|
| Elasticsearch | `docker.elastic.co/elasticsearch/elasticsearch:9.4.3` | `testcontainers[elasticsearch]`, single-node, security off, 512 MB heap, as Compose runs it |
| Garage | `dxflrs/garage:v2.3.0` | a generic `DockerContainer` with a generated `garage.toml`, then layout, key and bucket through the admin API |
| Dex | `ghcr.io/dexidp/dex:v2.45.1` | the existing fixture, moved out of auth's conftest unchanged |

After the move, a service's `tests/integration/conftest.py` shrinks to four things: which
database and tables it owns, `build_settings`, `create_app`, and its own seeded identities.

**The Worker gets a harness.** `run_consumer(handlers)` starts `StreamConsumer.run(stop)` as a
task against the Redis and Elasticsearch fixtures, and stops it cleanly. It lives in the Worker's
integration conftest.

**Contract tests fold into the unit layer.** The `contracts` package is the seam. The producer
side asserts that what Messaging enqueues validates as `MessageIndexPayload`. The consumer side
feeds a handler an envelope built from that same model. Conventions §11 goes from four layers to
three.

**The plugin tests itself** with pytest's `pytester`:

- a file outside `unit/` and `integration/` fails collection;
- a unit test that opens a TCP socket fails;
- an integration test may open one;
- `images.py` matches `docker-compose.yml`.

Those are the failing tests the first plan stops on.

## Framework 3 — Frontend unit: Vitest

| Package | Version | Why |
|---|---|---|
| `vitest`, `@vitest/coverage-v8` | 5.0.1 | peer `vite ^6.4`, installed 6.4.3; shares the Vite config, so Tailwind and the React plugin just work |
| `jsdom` | **29.1.1** | 30.x needs Node ^24.15, and this machine has 24.10; 29 accepts `>=24.0.0` |
| `@testing-library/react` / `dom` / `user-event` / `jest-dom` | 16.3.3 / 10.4.2 / 14.6.7 / 7.0.1 | behaviour through the DOM, not component internals |
| `msw` | 2.15.0 | REST stubbed at the network edge, so `openapi-fetch` and TanStack Query run for real |

The pieces:

- **Config** goes in a `test` block in the existing `vite.config.ts`, not a second config file:
  `environment: 'jsdom'`, `setupFiles: ['src/test/setup.ts']`, `restoreMocks: true`.
- **Tests sit beside their source** as `Foo.test.tsx`.
- **npm scripts:** `"test": "vitest run"` and `"test:watch": "vitest"`.
- **`src/test/setup.ts`:**
  - jest-dom matchers;
  - an MSW server with `onUnhandledRequest: 'error'`, so an unstubbed call fails the test;
  - handler reset and DOM cleanup after each test;
  - a Zustand store reset.
- **`src/test/render.tsx`:** `renderWithProviders(ui, { route, session })`. It builds a **fresh
  QueryClient per test** (`retry: false`), a `MemoryRouter` and the fake socket. A shared client
  leaks cache between tests, which is the classic TanStack flake.
- **`src/test/api.ts`:** MSW handlers typed from the **generated** `src/types/messaging.ts`
  (D23). A stub response that doesn't match the API fails `tsc`, so the stubs can't drift from
  the OpenAPI document.
- **`src/test/socket.ts`:** an in-memory fake of the `socket.io-client` surface the app uses:
  `on`, `off`, and `emit` with an ack. `serverEmit(event, payload)` pushes server events, and
  `connect()` in `lib/realtime/socket.ts` is swapped for it with `vi.mock`.
- **`src/test/factories.ts`:** `aChannel()` and `aMessage()`, typed from the same generated
  schema.
- **ESLint** gets an override for `src/test/**` and `*.test.tsx`, because `react-refresh` warns on
  modules that export helpers.

The frontend has **no integration layer of its own**. The seam it would test, the SPA against a
real API, is covered from both sides: service integration tests prove the API, and journeys prove
the join.

## Framework 4 — End-to-end: key journeys only

The harness stays exactly as D27 built it. Two things change.

**`scripts/test.sh e2e`** becomes a layer. It brings up the test stack with
`docker compose … up -d --build --wait`, installs Chromium if Playwright lacks it, runs
`pytest -m bdd`, and tears the stack down on exit unless `KEEP_STACK=1` is set. It belongs to
`all` but not to the no-argument default, so the everyday run stays fast. CI runs `all`. This
replaces the "no bdd" line of ADR 260914.

**The suite is triaged to journeys.** A scenario is removed **only in the same change that adds
and passes its replacement** at the lower layer. So the triage runs after the backfill, not before
it.

| Feature | Scenario | Verdict | Covered below by |
|---|---|---|---|
| channels | Ada signs in and sees her workspace | **keep** — OIDC, CORS, baked env | — |
| channels | Ada creates a public channel and lands in it | **keep one example** | outline rows → Vitest `CreateChannelDialog` |
| channels | A new public channel appears for another member | **keep** | — |
| channels | Name cannot be reused, whatever its case | demote | integration exists; Vitest shows the problem |
| channels | Name cannot be blank / has to be typeable / ≤ 80 | demote | unit `validate_name`; Vitest dialog |
| channels | A channel admin renames a channel | demote | integration exists; Vitest `ChannelHeader` |
| channels | A rename is visible to everyone | demote | integration `test_channels.py::test_a_rename_is_what_the_next_read_returns`. The scenario (`tests/bdd/features/channels.feature` ~line 84) has Grace *open* CollabHub after the rename, and Messaging emits no rename socket event (only message events, `read_receipt_updated` and `user_typing`), so the next read is the whole behaviour. |
| channels | An admin archives a channel and it leaves the list | demote | integration exists; Vitest `ChannelList` |
| channels | Ada creates a private channel and only she can see it | **keep** | — |
| messages | Ada sends a message and sees it | **keep** | — |
| messages | A message shows its author and timestamp | demote | Vitest `MessageItem` |
| messages | Blank not sent / over 8000 rejected | demote | unit `validate_body`; Vitest `MessageComposer` |
| messages | Scrolling up loads older messages | demote | integration pagination; Vitest `MessageList` (drives the observer callback, so no real scroll) |
| messages | Grace sees Ada's message after reloading | **keep** | — |
| messages | Ada edits her own message, edited marker | **keep** | — |
| messages | Ada cannot edit Grace's message | demote | unit `check_editable`; Vitest `MessageItem` |
| messages | Ada deletes her own message, tombstone after reload | **keep** | — |
| messages | Admin deletes another's / non-admin cannot | demote | unit `check_deletable`; integration exists |
| permissions | Non-admin not offered the channel controls | demote | Vitest `ChannelHeader` |
| permissions | Admin adds a member, they see it | **keep** | — |
| permissions | Removing a member revokes their view | **keep** | — |
| permissions | Non-member cannot open a private channel by URL | **keep** — the SPA's route to a 404 | — |
| realtime | Grace sees Ada's message without reloading | **keep** | — |
| realtime | Edit propagates live / delete propagates live | **keep** | — |
| realtime | Grace doesn't receive a channel she isn't viewing | demote | integration `test_realtime.py` rooms |
| realtime | The stream recovers after the connection drops | **keep** | — |
| realtime | Typing indicator appears and clears | demote | integration typing event; Vitest `TypingIndicator` |
| realtime | Sent message appears immediately and is confirmed | demote | Vitest `useSendMessage` |
| realtime | Rejected send is rolled back and the error shown | demote | Vitest `useSendMessage` |

The result is **about 16 scenarios, down from 34**. Merging the kept ones into longer
journey-shaped scenarios is a later, optional step. Search and unread counts have no journey yet.
Search needs the Worker and Elasticsearch on the test stack, which ADR 260815 currently scales to
zero.

## Commands when this is done

```bash
scripts/test.sh                    # lint, unit, integration — the everyday run
scripts/test.sh unit               # pytest (no network) + vitest
scripts/test.sh integration        # testcontainers
scripts/test.sh e2e                # brings the test stack up, runs journeys, tears it down
scripts/test.sh all                # all four — what CI runs
scripts/test.sh unit -- -k channels
(cd src/frontend && npm run test:watch)
```

## Records this work changes

- **CLAUDE.md:**
  - replace "unit tests only — for now" with "the failing test goes at the lowest layer that can
    prove the behaviour; stop at red";
  - drop "no frontend tests";
  - add `testkit` and `tests/{unit,integration}` to the layout;
  - rewrite the Testing section.
- **Conventions §11:** three layers, the "where a test goes" table, `testkit`.
- **Register:** new **D32 — test pyramid 🟢**. D27's note narrows to key journeys.
- **ADR:** `docs/adr/260915-a-test-pyramid-with-journeys-at-the-top.md`, written with
  `adr-writer`. It supersedes the "no bdd" consequence of 260914.
- **README:** the Acceptance tests section points at `scripts/test.sh e2e`.

These are recorded in the first implementation plan, the slice that makes the decision, not in a
sweep at the end.

## Delivery

Four implementation plans. Each runs as TDD and stops at red for review.

| Plan | Builds | Red is | Proven by |
|---|---|---|---|
| **A — layout and testkit core** | `testkit` package and plugin, layer-by-directory, socket and Docker guard; Dex and Auth's helpers moved into `testkit`; `from tests` banned; existing tests moved into `unit/` and `integration/`; coverage; all the records above | `pytester` tests for the plugin | collected counts identical before and after the move (112 / 287 / 43), then every suite green |
| **B — containers** | shared Postgres with database-per-service, Redis index per role, Elasticsearch, Garage, all through testcontainers; `Tokens` / `apps` / `db` / `RecordingServer` into `testkit` and the conftests slimmed; `images.py` checked against Compose; Worker `run_consumer` | the `images.py` drift test; one smoke test per new fixture | integration suite green on one Postgres and one Redis |
| **C — Vitest** | dependencies, config, setup, `renderWithProviders`, typed MSW, fake socket, factories, ESLint override, `npm test` in `test.sh unit` | one pilot test per helper, e.g. `upsertMessage`, `problemFrom`, a `MessageItem` render | `scripts/test.sh lint unit` green |
| **D — e2e layer** | `test.sh e2e` with the stack lifecycle; README and ADR note | — (script-only, verified by running it) | 43 bdd tests pass through the script |

Order: **A, then B and C in parallel, then D.** The backfill and the triage come after that. The
backfill covers the Worker, search, frontend components, the demoted rules and the first
pure-policy example (message edit and delete). It is per-module feature work, not framework: the
framework plans add no tests for existing behaviour.

## Not in this design

- **Writing the missing tests.** That is the backfill above.
- **pytest-xdist.** Session containers per worker would multiply the containers. Revisit when the
  integration run hurts.
- **Coverage thresholds.** Set after the backfill measures one.
- **Other kinds of testing:** mutation, load, visual regression, Playwright's TypeScript runner
  (rejected in ADR 260815).
- **A CI pipeline file.** None is in the repo, and the scripts are the contract.
- **Canvas and Asset tests beyond health.** They have no behaviour yet.

## Decisions — approved 2026-09-15

1. **Integration tests drive a service's public boundary** (REST, Socket.IO, stream consumer)
   in-process, against real dependencies **started by testcontainers**. Domain functions are
   called with a real session only for SQL the API can't reach deterministically.
2. **Rules become unit-testable by extracting pure policy functions.** No repository protocols
   with in-memory fakes. The fakes would be a second implementation of every query that drifts
   from the first, and CLAUDE.md already rules out faking the database. It is applied when a slice
   touches a module; the first example, message edit and delete, comes with the backfill.
3. **The directory decides the layer.** `tests/unit/` and `tests/integration/` per service, and a
   test anywhere else is a collection error. This moves all 399 existing service tests once, in
   plan A.
4. **The unit layer has no network,** enforced with pytest-socket, and no Docker, enforced with
   `DOCKER_HOST`.
5. **A `testkit` workspace package**, loaded as a pytest11 plugin, holds shared fixtures and
   helpers. It adds a member to the repo layout.
6. **One Postgres per test session with a database per service. One Redis with a database index
   per role.** Both are testcontainers session fixtures.
7. **Contract tests are unit tests** against `contracts` models on both sides, and Conventions §11
   goes to three layers.
8. **The frontend unit stack is Vitest 5, Testing Library, typed MSW and a fake socket.** Tests
   sit beside their source, jsdom is pinned at 29, and there is no frontend integration layer.
9. **The BDD suite is trimmed to about 16 journey scenarios** per the table. Each demotion happens
   only with its replacement in the same change, and the "rename visible to everyone" row is
   checked before it's decided. Checked 2026-09-15 during plan A: demote — see the table.
10. **`scripts/test.sh e2e` is a new layer,** part of `all` but not the default. It supersedes
    ADR 260914's "no bdd".
11. **Coverage is reported with no gate** until the backfill.
12. **These plans live in `docs/plans/ch07/`.**
