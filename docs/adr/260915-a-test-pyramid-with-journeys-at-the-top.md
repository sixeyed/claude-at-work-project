# A test pyramid, with journeys at the top

- **Status:** Accepted
- **Date:** 2026-09-15

## Context

Register entry **D32** — never previously given an ID — surfaced while reviewing
where CollabHub's tests actually live. Collected on `main` at `fe345be`: 112 unit
tests, 287 integration tests, 43 BDD scenarios. That is not a pyramid; it is two
and a half integration tests for every unit test, and the causes were structural
rather than incidental.

Rules were reachable only through the database. `validate_name` is a pure
function, but its only tests went over HTTP against Postgres
(`test_invalid_names_are_rejected_with_a_reason_per_rule`). The authorization
rules in `messages.edit` and `messages.delete` are pure decisions, but they sit
inline in an async function *after* a database fetch, so no test could reach them
without a session.

The layer was chosen by a pytest marker, and the default was unit. A test that
forgot `pytestmark = pytest.mark.integration` landed in the unit layer anyway,
with nothing stopping it from opening a socket or reaching Docker — a missing
marker silently made a test "unit" without making it fast or hermetic.

Three conftests — Auth, Messaging, Shared — copied the same fixtures: containers,
the truncation helper, token minting, the ASGI client. They could not be shared by
import, because every service's `tests` directory is the same namespace package
with no `__init__.py`; even the imports were spelled two ways
(`testcontainers.postgres` in Messaging, `testcontainers.community.postgres` in
Auth). A full run started two Postgres containers and three Redis containers to
do the same thing twice.

There were no fixtures for Elasticsearch or Garage, so the Worker
(`consumer.py`, its handlers, `index.py`) and Messaging's `search.py` had no
tests at any layer beyond health checks. The frontend SPA had no tests at all,
despite plainly unit-shaped logic — the TanStack cache updaters in
`useMessages.ts`, `problemFrom` in `client.ts`, the session state machine in
`session.ts`.

About half the BDD suite checked field rules — blank names, an 80-character
limit, an 8000-character limit, "cannot edit Grace's message" — that belong
lower down and, in most cases, were already covered there too. `scripts/test.sh`
did not run BDD at all; it was a README step, which CLAUDE.md already treats as a
bug once a suite is a layer CI depends on. And Conventions §11 described four
layers — unit, integration, contract, acceptance — with no rule for choosing
between them, so nothing in the docs would have stopped the inversion from
happening again.

## Decision

We will build a standard test pyramid: **unit tests for all functionality,
integration tests for each service's public boundary against dependencies
testcontainers starts, and BDD for key user journeys only.**

**The directory decides the layer**, not a marker. Every service's tests live in
`tests/unit/` or `tests/integration/`, and a test file anywhere else under a
service's `tests/` fails collection. This is enforced by a new dev-only workspace
member, `src/services/testkit` (distribution `collabhub-testkit`, module
`testkit`), registered through the `pytest11` entry point so every service gets
it with no conftest import. Its plugin marks each collected item by the directory
it lives in and refuses one that lives anywhere else.

**Unit tests get no network and no Docker.** pytest-socket disables sockets for
every item marked `unit` (Unix-domain sockets stay open, because asyncio's
self-pipe on macOS is an `AF_UNIX` socketpair), and `DOCKER_HOST` is pointed at an
address that cannot resolve, so a Docker client fails immediately rather than
quietly finding the local socket. The setup hook runs `tryfirst=True` so the
guard is up before a unit test's own fixtures run, and the teardown hook runs
`trylast=True` so `DOCKER_HOST` comes down only after a test's own fixtures and
monkeypatches have unwound outermost — pytest-socket's own socket guard has no
such ordering and re-enables sockets before fixture teardown runs, a known gap
tracked in the unit handoff's "Known gaps in the foundation". That ordering was not free: a review during
this slice found that without `trylast=True` the guard could leak `DOCKER_HOST`
past the test that had set it, and the fix was made test-first. The plugin now
carries 11 tests of its own (via pytest's `pytester` — a file outside `unit/` or
`integration/` fails collection, a unit test that opens a TCP socket fails, an
integration test may open one), and the service unit layer stands at 123 tests,
all green with sockets blocked.

**`from tests.…` imports are banned outright**, by ruff's `flake8-tidy-imports`
banned-api rule (TID251). Every service's `tests` directory is the same namespace
package with no `__init__.py`, so `from tests.conftest import …` silently binds
to whichever service happens to sort first — Auth's, when the whole suite runs.
Shared test helpers now live in `testkit`; a service's own stay as fixtures.

Dex's container and its three static accounts (`testkit/dex.py`), the
browser-driven OIDC sign-in flow (`testkit/dexflow.py`), and Auth's test
settings (`testkit/auth.py`) moved out of Auth's old conftest and `dexflow.py`
into `testkit`, unchanged in behavior — moving the tests forced the move, since
five Auth test files imported them from `tests`. `testkit` therefore depends on
`collabhub-auth`, which is new: no other dev-only package in the workspace
depends on a service.

**Coverage is reported, not gated.** pytest-cov runs on the unit layer with a
terminal report and `coverage.xml`; `scripts/test.sh unit` now runs fast, with no
network or Docker, and prints it. This slice measured a **TOTAL of 55%** on the
existing unit layer — a number to set a floor against later, once the backfill
has grown it, not a target guessed at now.

**Contract tests fold into the unit layer.** The `contracts` package is the
seam: a producer's payload validates against the same Pydantic model a consumer's
handler is fed. Conventions §11 changes from four layers to three to match.

This slice — plan A of `docs/plans/ch07/02-test-pyramid-a-layout-and-testkit-implementation-plan.md`
— builds the layout and the `testkit` core only: the plugin, the directory
convention, the socket and Docker guard, `from tests` banned, all 399 existing
service tests moved into `unit/` or `integration/` with their collected counts
identical before and after, and the records this ADR is part of. It deliberately
does **not** extract message edit and delete into pure policy functions
(`check_editable` / `check_deletable`). That extraction was the design's worked
example of "pull the decision out as a pure function over values that are
already loaded, and leave the async function as the shell that fetches and
writes" — but it was deferred to the backfill by Elton, and does not exist in
code as of this slice. It is a pattern to apply later, not an example already
built.

The rest of the design — shared containers for Postgres/Redis/Elasticsearch/
Garage/Dex, the Vitest frontend layer, and the `e2e` layer in `scripts/test.sh`
with the BDD suite's triage down to roughly 16 journeys — is handed to other
agents through three handoff documents: `docs/plans/ch07/03-test-pyramid-handoff-unit.md`,
`docs/plans/ch07/03-test-pyramid-handoff-integration.md`, and
`docs/plans/ch07/03-test-pyramid-handoff-e2e.md`.

## Consequences

The directory decides the layer, and the `testkit` plugin enforces it — a test
can no longer land in the wrong layer by omission. Unit tests have no network or
Docker, so the unit suite stays fast and cannot drift into needing containers
without the move being visible in the diff (a file changing directory).

`from tests` is banned, and `testkit` now depends on `collabhub-auth` — a
dev-only package depending on a service is a new shape in this workspace, and
worth noticing if `testkit` grows further.

Rules become unit-testable by extraction into pure functions only when a slice
touches the module that holds them; nothing fakes a repository or a database
session to reach one early. Message edit and delete stay untested at the unit
layer until the backfill does that extraction — this ADR records the plan, not
the completed work.

Contract tests are now unit tests, checked on both sides against `contracts`
models, and Conventions §11 reads as three layers instead of four.

The frontend still has no tests, and the duplicated containers this slice left
in place — one Postgres and Redis fixture per service, rather than the shared,
database-per-service and index-per-role setup the design calls for — are not
fixed by this slice either. Both wait on the two remaining handoffs:
`docs/plans/ch07/03-test-pyramid-handoff-unit.md` owns the Vitest layer for the
SPA (and the Python unit backfill), and
`docs/plans/ch07/03-test-pyramid-handoff-integration.md` owns collapsing the
containers through testcontainers and the Worker/search backfill — the same way
the BDD triage below waits on the e2e handoff.

The BDD suite will shrink to about 16 journeys, once
`docs/plans/ch07/03-test-pyramid-handoff-e2e.md` carries out its triage; a
scenario is removed only in the same change that adds and passes its replacement
at a lower layer, never ahead of it. `scripts/test.sh` gains an `e2e` layer as
part of that same handoff — brought up, run, torn down — which **supersedes**
the "Gherkin suite is not included" line of
[ADR 260914](260914-scripts-as-the-build-test-deploy-entry-point.md): that ADR's
`test.sh` decision predates this one and is narrowed by it rather than
contradicted.

Coverage is reported and not gated. A number now exists (55% TOTAL) where none
did before, but nothing in CI enforces it yet, so a regression in coverage is
visible only to someone who reads the report.

## Alternatives Considered

### Repository protocols with in-memory fakes

Would let rules be tested without a real session by swapping in a fake
repository. Rejected: a fake is a second implementation of every query, and it
drifts from the real one the moment either changes — exactly the kind of test
that passes while the feature is broken. CLAUDE.md already rules out faking the
database, and this design does not create an exception to that.

### Keeping marker-selected layers

Leaving `pytestmark = pytest.mark.integration` (or its absence) as the source of
truth, and just writing more unit tests. Rejected: that is the silent-default
failure that produced the inversion in the first place — a missing marker still
runs, just in the wrong layer, with no signal that anything is wrong.

### Contract testing as a fourth layer (Pact-style)

A consumer-driven contract layer with its own broker and verification step.
Rejected: CollabHub is one repository with one shared `contracts` package, so
checking both sides against the same Pydantic models is already a unit-layer
concern. A Pact-style broker solves cross-repository drift, which does not exist
here.

### A frontend integration layer

Testing the SPA against a real running API, as a layer between Vitest and the
BDD suite. Rejected: the seam it would cover — the SPA talking to a real
service — is already proven from both sides, by each service's integration
tests and by the BDD journeys that drive a real browser through the whole
stack. A third layer in between would duplicate one side or the other without
adding a seam of its own.

### Playwright's own TypeScript test runner for end-to-end

Already rejected in [ADR 260815](260815-pytest-bdd-and-playwright-for-acceptance-tests.md),
which chose pytest-bdd driving Playwright's sync Python API so Gherkin scenarios
stay readable by non-engineers and the acceptance suite stays in the same
language as the rest of the backend. This decision narrows what that suite is
for; it does not reopen how it is built.
