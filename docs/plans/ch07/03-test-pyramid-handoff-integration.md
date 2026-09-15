# Test pyramid handoff — integration layer

Handoff, 2026-09-15. This is for an agent taking over the **integration layer** of CollabHub's
test pyramid, with no context from the session that designed it. Two sister handoffs cover the
other layers: [unit](03-test-pyramid-handoff-unit.md) and [end-to-end](03-test-pyramid-handoff-e2e.md).

You own two workstreams, in this order:

1. **Integration framework.** The design calls this "plan B", and no implementation plan exists for
   it yet. It covers shared containers through testcontainers, database-per-service, Redis-per-role,
   Elasticsearch, and consolidating the duplicated fixtures into `testkit`.
2. **Integration backfill.** The Worker and message search have no tests beyond health checks.
   You also confirm integration coverage for the BDD scenarios that are moving down a layer.

---

## Before you start

### Read these

| Document | Why |
|---|---|
| `CLAUDE.md` | The working rules. It wins over this handoff if they ever disagree. |
| `docs/design/00-platform-conventions.md` | The cross-service contract: tenancy, 404-not-403, jobs, auth, Redis roles. §11 describes the test layers once plan A lands. |
| `docs/plans/ch07/01-test-pyramid-design.md` | **The approved design, and your authority.** Read "The three layers", "Where a test goes" and "Framework 2". |
| `docs/plans/ch07/02-test-pyramid-a-layout-and-testkit-implementation-plan.md` | The foundation you build on: what exists and why. |
| `docs/design/02-messaging-service.md`, `docs/design/05-worker-service.md` | What search and the consumer are supposed to do. |
| `docs/design/07-open-decisions-register.md` D32, `docs/adr/260915-a-test-pyramid-with-journeys-at-the-top.md`, `docs/adr/260914-message-search-index-is-a-candidate-list.md`, `docs/adr/260914-worker-pools-split-on-latency.md` | Recorded decisions that bind your tests. |

Ignore `docs/project/`. It's book-production material.

### Check the foundation is there

```bash
uv run pytest --collect-only -q -m unit | tail -1            # 122 or more collected, no errors
uv run pytest --collect-only -q -m integration | tail -1     # 287 or more collected
grep -rn 'pytest.mark.integration' src/services --include='*.py' --exclude-dir=testkit   # prints nothing
ls src/services/testkit/testkit/                              # plugin.py dex.py dexflow.py auth.py …
```

Plan A is merged to `main`, so branch from `main`. If any of these fail, the foundation isn't
what this handoff expects. **Stop and ask Elton.**

### Working rules that bite

These come from CLAUDE.md and are repeated here because they are easy to get wrong:

- **Branch and worktree:** create a new git worktree on a new feature branch before your first
  edit, and tell Elton the branch name and path.
- **Never commit or stage.** No `git add`, `git commit` or `git stash`. Use plain `mv`, never
  `git mv`.
- **Write your plan into the repo.** Use superpowers:writing-plans to write it at
  `docs/plans/ch07/05-test-pyramid-integration-<topic>-implementation-plan.md` (prefix `05` is
  reserved for this handoff; unit has `04`, end-to-end `06`),
  and get Elton's approval before executing it.
- **Test first, and stop at red.** A framework change gets a failing test first, usually a
  `pytester` test in `src/services/testkit/tests/unit/` or a smoke test for a new fixture.
- **Backfill tests pass the moment they're written,** because the behaviour already exists. So
  prove each one can fail:
  1. Break the behaviour it pins, temporarily, with a one-line change.
  2. Run the test and watch it go red.
  3. Restore the code.
  4. Record the command and the output.

  Then stop for review.
- **Never mock a service's own stores.** testcontainers starts every dependency (design decisions 1
  and 6). An integration test never relies on the Compose stack or a hand-started container.
- **Hooks:**
  - An edit hook runs ruff and **blocks** on findings. Fix them.
  - `from tests… import` is a ruff error (TID251), because `tests` is one namespace package
    spanning every service. Shared helpers come from `testkit`, and a service's own go through
    fixtures.
- **Decisions:** a 🔴 decision in the register means stop and ask. New register IDs are reserved
  per handoff, so the three parallel branches don't collide: **D33** unit, **D34** integration,
  **D35** end-to-end. Record any decision you make in
  the same slice: register row, source design doc, and an ADR through `adr-writer` when it's
  significant.
- **Integration runs are slow.**
  - A single Bash tool call is capped at 10 minutes, so run per service:
    `scripts/test.sh integration -- src/services/<svc>`.
  - Docker Desktop on Elton's Mac is reached through a Docker *context*, not `DOCKER_HOST`.
    testcontainers handles that. docker-py's bare `from_env()` does not.

---

## What the integration layer is (settled)

| | |
|---|---|
| **Proves** | one service at its public boundary behaves correctly against the stores it owns |
| **Where** | `src/services/<service>/tests/integration/`. The directory decides the layer (`testkit` plugin). |
| **Drives** | **REST:** the FastAPI app on `httpx.ASGITransport`. **Socket.IO:** uvicorn on an ephemeral port. **Worker:** `StreamConsumer` reading a real Redis stream and writing to a real Elasticsearch. |
| **Domain functions directly** | Only for SQL the API can't reach deterministically, such as two concurrent renames. |
| **Substitutes allowed** | Tokens minted with a local RSA key instead of calling Auth; a `StaticKeySource` JWKS. |
| **Never** | Mocks of the service's own Postgres, Redis or Elasticsearch. |
| **Run** | `scripts/test.sh integration [-- pytest args]` |

---

## Current state (measured 2026-09-15, after plan A's move)

- **Integration tests:** 287 (shared 28, auth 105, messaging 154). Canvas, Asset and Worker have
  none.
- **Containers per full run:** two Postgres (`postgres:18`), three Redis (`redis:8`) and one Dex.

| Where | What it starts | Notes |
|---|---|---|
| `src/services/auth/tests/integration/conftest.py` | Postgres, Redis, Dex | Dex comes from `testkit.dex.start_dex` and settings from `testkit.auth.build_settings`. It truncates `refresh_tokens, external_identities, workspace_members, workspaces, users`. |
| `src/services/messaging/tests/integration/conftest.py` | Postgres, Redis | **Uses deprecated imports:** `testcontainers.postgres` and `testcontainers.redis`, which should be `testcontainers.community.*`. It has a `Tokens` class (user tokens, aud `collabhub`), `build_settings`, `client`, `client_for`, `realtime_url` (uvicorn on port 0, `lifespan="on"`, bounded readiness poll) and `redis_client` (flushdb). It truncates `messages, channel_reads, channel_members, channels`. |
| `src/services/shared/tests/integration/conftest.py` | Redis | — |
| `src/services/shared/tests/integration/test_security.py` | — | Its own `mint`, `user_token` and `service_token` (aud `collabhub-internal`, `sub service:worker`, `scp`). |

In every service today, `redis_cache_url`, `redis_realtime_url` and `redis_streams_url` all point
at the same `/0`.

---

## Workstream 1 — Integration framework (plan B)

This builds `testkit` modules. You own `containers.py`, `databases.py`, `images.py`, `tokens.py`,
`apps.py` and `db.py`, plus the existing `dex.py` and `auth.py`.

1. **`images.py`:** the pinned image tags.
   - `postgres:18`
   - `redis:8`
   - `docker.elastic.co/elasticsearch/elasticsearch:9.4.3`
   - `ghcr.io/dexidp/dex:v2.45.1`, moved from `testkit.dex.DEX_IMAGE`
   - `dxflrs/garage:v2.3.0` if Garage lands; see item 5

   Add a **unit test** in `src/services/testkit/tests/unit/` asserting that each tag matches
   `docker-compose.yml`. It reads the file with no network, and it's the drift guard.
   `docs/platform/versions.md` is the source of truth for versions.
2. **One Postgres per test session, a database per service.**
   - A session fixture starts `postgres:18` with `testcontainers.community.postgres.PostgresContainer`
     (`driver="asyncpg"`).
   - `service_database(name, upgrade)` runs `CREATE DATABASE` for the service and then its
     migrations. Both `auth.migrations` and `messaging.migrations` expose
     `upgrade_to_head(dsn)`.
   - This mirrors "every service owns its own database".
3. **One Redis, a database index per role.**
   - R1 cache/denylist is `/0`, R2 Socket.IO backplane is `/1`, R3 job streams is `/2`, following
     the settings `redis_cache_url`, `redis_realtime_url` and `redis_streams_url`.
   - `redis_client` fixtures flush the index they use.
   - **Pub/Sub is not scoped by database index in Redis.** Channels are global to the server, so
     index separation catches a *key* written to the wrong role but not a Socket.IO backplane
     message crossing roles. Say so in the fixture's docstring. Don't claim more isolation than it
     gives.
4. **Elasticsearch:** `testcontainers.community.elasticsearch`, which was checked importable in
   testcontainers 4.15.
   - Run it the way Compose does: single-node, `xpack.security.enabled=false`,
     `ES_JAVA_OPTS=-Xms512m -Xmx512m`.
   - Add the `elasticsearch` extra to the root `pyproject.toml`
     (`testcontainers[postgres,redis,elasticsearch]`), then `uv lock` and
     `uv sync --locked --all-packages`.
   - Start it only for tests that request it; it's the slowest container.
5. **Garage — ask Elton before building it.**
   - The design lists a Garage fixture (`DockerContainer` with a generated `garage.toml`, then
     layout, key and bucket through the admin API on 3903).
   - But **nothing uses object storage yet**. The `ObjectStore` protocol doesn't exist:
     `src/services/asset/asset/main.py` and `src/services/shared/shared/__init__.py` both say so,
     and Asset is a skeleton.
   - Recommendation: defer it until the slice that introduces `ObjectStore`, and record that
     ruling. Compose's config is in `docker/garage/garage.toml`.
6. **Where the container fixtures are registered — decide and record.**
   - **Option A: register them once, from the plugin.** For example, `testkit.plugin` registers
     `testkit.containers` with `config.pluginmanager.register`. That gives one fixture definition
     and so **one container per session**. A unit test *could* request one, but the unit guard
     makes Docker unreachable, so it fails fast. Pin that with a pytester test.
   - **Option B: import them into each `tests/integration/conftest.py`.** This keeps them
     invisible to unit tests, **but each conftest import creates a separate fixture definition, so
     a session-scoped fixture can start one container per service**. That defeats item 2.
   - Recommendation: A. Prove "one Postgres for the whole run" with a check in your plan, for
     example counting containers with the `postgres:18` image during a full integration run.
7. **`tokens.py`:** one `Tokens` minting both kinds of token, replacing the Messaging conftest's
   class and `test_security.py`'s helpers.
   - **User tokens** (Conventions §5.1): `iss`, `aud=collabhub`, `iat`, `exp`, `jti`, `sub`,
     `name`, `email`, `wsp`, `roles`.
   - **Service tokens:** `aud=collabhub-internal`, `sub=service:<name>`, `scp`.
   - Expose it as a fixture that takes the signing key. Keep the Messaging tests' `ada` and `grace`
     header fixtures working.
8. **`apps.py`:**
   - `asgi_client(app)` is an async context manager over `httpx.ASGITransport`.
   - `serve(app)` is uvicorn on port 0 with `lifespan="on"` and a bounded `server.started` poll.
     Move the Messaging `realtime_url` fixture's docstring rationale with it: ASGITransport can't
     carry a WebSocket, and the socketio lifespan delegation.
9. **`db.py`:** `truncate(engine, tables)`, replacing the two copies.
10. **Slim the conftests.** Afterwards, a service's `tests/integration/conftest.py` holds only:
    - its database and table list
    - `build_settings`
    - `create_app`
    - its own seeded identities
11. **Worker harness:** create `src/services/worker/tests/integration/conftest.py` with
    `run_consumer(handlers)`.
    - It starts `StreamConsumer(client, stream, handlers, ConsumerConfig(...)).run(stop)` as a task
      against the R3 Redis index and Elasticsearch.
    - Use a small `block_ms`, for example 100, so tests don't wait on the 5000 default.
    - It stops cleanly by setting the `asyncio.Event` and awaiting the task.
    - `ConsumerConfig` fields: `consumer`, `batch_size`, `visibility_timeout_seconds`,
      `max_attempts`, `dead_letter_maxlen`, `block_ms=5000`, `group="worker"`.

**Framework done when:**
- a full `scripts/test.sh integration` passes, per service, on **one** Postgres and **one** Redis
- the image drift test is green
- no conftest duplicates a helper that's in `testkit`
- there are no deprecated testcontainers imports

---

## Workstream 2 — Integration backfill

Give each item its own plan slice and its own review.

1. **Worker consumer** (`src/services/worker/worker/consumer.py`) against a real Redis stream:
   - a handled job is acknowledged and leaves the pending list
   - a transient failure is retried and then succeeds
   - `PermanentJobError` goes to `dead_stream` at once, with its fixed reason; it never includes
     exception text
   - a job that fails `max_attempts` times is dead-lettered
   - a stale pending entry is reclaimed after `visibility_timeout_seconds`
   - an unknown job type: read the code for the intended behaviour
   - idempotency: the same `jobId` twice produces one effect (Conventions: handlers are idempotent)
2. **Worker handlers and index** (`handlers/messages.py`, `index.py`) against real Elasticsearch:
   - `ensure_messages_index` creates `messages-v1` behind the `messages` alias
   - upsert writes the document
   - delete removes it, or marks it deleted; read the code
   - **an older `version` arriving late is rejected**, because version is the ES external version
     (D25)
3. **Messaging producer.** A message send, edit or delete over REST enqueues onto `jobs:index` in
   the real R3 Redis, with a `MessageIndexPayload`. Grep the existing `test_messages.py` first; it
   may already partly cover this.
   - Redis being unreachable must not fail the write, because it's fire-and-forget.
   - The unit handoff covers the payload's shape; you cover the real stream.
4. **Message search** (`GET /search/messages`, `messaging/search.py`, `routers/search.py`) with
   real Elasticsearch and Postgres (ADR 260914: the index is a *candidate list* hydrated from
   Postgres):
   - results come from the candidates, hydrated
   - a private channel you're not in is excluded, and so is another workspace (404-not-403 rules
     and tenancy)
   - deleted messages are handled per doc 02
   - ES unavailable maps to `SearchUnavailableError`'s response; read the router for the status
   - the `MAX_QUERY_CHARS` (200) boundary
   - **Seeding ES is a decision to record.** Messaging must not import the Worker. Either write
     documents directly through Messaging's ES client against the `messages` alias, or seed through
     the Worker handler in a Worker-side test. Pick one and write down why.
5. **Redis role separation.** Once item 3 of workstream 1 lands, add one test per service that
   writes through each role and asserts the key lands in the right index.
6. **Confirm lower-layer coverage for the demoted BDD scenarios.** For each row, confirm the named
   test exists and really covers the behaviour, or write it:

   | BDD scenario | Existing integration test to confirm |
   |---|---|
   | channels: "A public channel name cannot be reused, whatever its case" | `test_channels.py::test_public_names_collide_regardless_of_case` |
   | channels: "A channel admin renames a channel" | `test_channels.py::test_an_admin_renames_a_channel` |
   | channels: "A rename is visible to everyone in the workspace" | `test_channels.py::test_a_rename_is_what_the_next_read_returns`. The scenario has Grace *open* CollabHub after the rename, and Messaging emits no rename socket event, so the next read is the whole behaviour. |
   | channels: "An admin archives a channel and it leaves the list" | `test_channels.py::test_an_admin_archives_a_channel_and_it_leaves_the_list` |
   | messages: "Scrolling up loads older messages" | `test_pagination.py` (cursor paging) |
   | messages: "A channel admin deletes another user's message" / "A non-admin cannot delete someone else's message" | `test_messages.py::test_a_channel_admin_deletes_another_users_message`, `::test_a_non_admin_cannot_delete_someone_elses_message` |
   | realtime: "Grace does not receive messages for a channel she is not looking at" | `test_realtime.py`, room membership; find the test |
   | realtime: "A typing indicator appears for Grace and clears when Ada stops" | `test_realtime_writes.py::test_typing_reaches_the_room_but_not_the_sender` |

   Deliver this table, with the confirmed test names, in a `## BDD replacements` section of your
   `05-test-pyramid-integration-…` plan. The end-to-end agent reads it from `main`; a final report
   is invisible to it. The
   end-to-end handoff deletes a scenario only when both its unit and integration replacements are
   confirmed.

---

## Done when

- The framework "done when" above holds.
- Worker consumer, handlers, index and message search have integration tests at their public
  boundary.
- The BDD confirmation table is delivered.
- CLAUDE.md "Testing" and Conventions §11 match what exists: fixtures, one container per store,
  Redis index per role.

## Not yours

- **The unit handoff owns these:** pure rules and extractions, Vitest, and `testkit/fakes.py` and
  `factories.py`.
- **The end-to-end handoff owns these:** `scripts/test.sh e2e`, deleting BDD scenarios, and new
  journeys.
- **Out of scope:**
  - pytest-xdist (session containers per worker would multiply containers)
  - Canvas and Asset tests beyond health, since they have no behaviour
  - load testing

## Coordinating with the other two handoffs

- **`pyproject.toml` and `uv.lock`:** you add the ES extra. If another branch also changed
  `uv.lock`, resolve the conflict by re-running `uv lock`.
- **`testkit/plugin.py`:** it's shared. There's a known gap in the unit guard (pytest-socket's
  `enable_socket` marker bypasses it), described in the unit handoff. Option A in workstream 1, item 6 changes it, so write a
  failing pytester test first and get Elton's review. The unit layer's guard must keep passing its
  11 tests.
- **CLAUDE.md "Testing" and `docs/design/00-platform-conventions.md` §11:** all three handoffs may
  edit these. Re-read both sections from `main` before editing, and expect to merge text.
- **The e2e handoff's test stack** is Compose, not testcontainers. Nothing you build is used there.
