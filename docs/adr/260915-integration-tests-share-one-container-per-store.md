# Integration tests share one container per store

- **Status:** Accepted
- **Date:** 2026-09-15

## Context

The test pyramid (register D32, [ADR 260915](260915-a-test-pyramid-with-journeys-at-the-top.md))
puts every service's integration tests against real dependencies started by
testcontainers. Before this decision each service's `tests/integration/conftest.py`
started its own: a full run brought up two Postgres containers and three Redis
containers, with the fixtures that started them — and the token minting, the ASGI
client, the uvicorn helper and the truncation — copied between conftests. There were
no fixtures at all for Elasticsearch, so the Worker and Messaging's search had no
integration tests.

Three facts shaped what replaced that. **pytest keeps one value per fixture
definition**, not per fixture name: a session-scoped fixture imported into three
conftests is three definitions and three containers. **Every service owns its own
database and uses Redis in named roles** — R1 cache, R2 Socket.IO backplane, R3 job
streams — and in every test run until now all three roles pointed at the same
`/0`, so a key written through the wrong role passed unnoticed. And **Messaging reads
an index the Worker writes**, while Messaging's code must never import the Worker.

## Decision

We will start one container per store per test session, registered once from the
`testkit` pytest plugin. `testkit.plugin` declares
`pytest_plugins = ["testkit.containers", "testkit.tokens"]`, so `postgres_server`,
`redis_server`, `elasticsearch_url` and `tokens` each have a single definition that
every service's tests share without a conftest import.

On that shared infrastructure the tests mirror production's separation:

- **Postgres:** one server, a database per service. A service's conftest calls
  `testkit.databases.service_database(server, "<service>", upgrade_to_head)`.
- **Redis:** one server, a database index per role — R1 `/0`, R2 `/1`, R3 `/2` — and
  `redis_cache` / `redis_streams` fixtures that flush only their own index.
- **Elasticsearch:** started only when a test requests it, configured as Compose runs
  it; the per-test `elasticsearch` fixture drops every index first.

A unit test that depends on a container fixture, directly or through another
fixture, stops the run at collection. Garage has no fixture until the slice that
introduces the `ObjectStore` protocol, because nothing uses object storage yet.

Messaging's search tests build and fill the `messages` index **with the Worker's own
code**, reached through `testkit.search`: `ensure_messages_index` for the mapping and
alias, and the message handlers for the documents. `testkit` is dev-only and may
depend on both services; Messaging's code and its tests still import nothing from
`worker`.

## Consequences

A full integration run starts one Postgres, one Redis, one Dex and — only when the
Worker or search tests run — one Elasticsearch. Each service's conftest holds only its
database and tables, its settings, its app and its seeded identities; everything
shared lives once in `testkit`.

Role separation is now checked: a stream written on the cache index, or a denylist
entry on the streams index, shows up as a key on the wrong index. It is not complete.
**Redis Pub/Sub is server-wide, not per database index**, so a Socket.IO backplane
wired to the wrong URL would still deliver; the role test checks the backplane's
connection in `CLIENT LIST` instead, and the fixture's docstring says so rather than
claiming more isolation than there is.

Tests from different services now share servers, so they share state they did not
share before: a stream left on R3 by a Messaging test is visible to a Worker test that
does not flush it. The `redis_*` fixtures flush on entry, and tables are truncated by
each service's `engine` fixture, but a test that reads a store without requesting its
cleaning fixture can see another service's leftovers.

Search tests exercise the real mapping, so a Worker mapping change that breaks search
fails Messaging's tests. The price is that `testkit` depends on `collabhub-worker` and
`collabhub-messaging`, which is acceptable only because nothing ships `testkit`.

Session fixtures per process is also why pytest-xdist stays out: each worker process
would start its own set of containers.

## Alternatives Considered

### Import the container fixtures into each service's conftest

Keeps them invisible to unit tests with no plugin logic, but every import is a separate
fixture definition, so a full run would still start a Postgres per service — the thing
this decision exists to stop.

### A container per service, as before

The strongest isolation between services' tests, at the cost of five or more extra
containers per run and duplicated fixtures. The isolation it buys is already provided
by a database per service and an index per role, which is also what production
separation looks like.

### Seed the search index with a copy of the mapping in Messaging's tests

Would keep `testkit` free of a Worker dependency, but the copy would keep passing after
the real mapping changed — exactly when a test is needed. Seeding through a Worker-side
test instead would put Messaging's search route under the Worker's tests, which is the
wrong owner.

### Build the Garage fixture now

The design lists it, but with no `ObjectStore` protocol and nothing reading or writing
objects it would be untested code with no consumer. It lands with the slice that needs
it.
