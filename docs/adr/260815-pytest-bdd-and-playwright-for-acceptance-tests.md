# Drive acceptance tests with Gherkin, pytest-bdd and Playwright

- **Status:** Accepted
- **Date:** 2026-08-15

## Context

Conventions §11 names three test layers — unit, integration with testcontainers,
and contract — and there was no BDD anywhere in the repo. Those layers are good
at what they cover and they share a blind spot: every one of them stops at a
service boundary. Auth's suite proves Auth issues a correct token; Messaging's
proves a channel list is correctly paginated. Nothing proved that a person can
open a browser, sign in, and see a channel — which is the only claim anyone
outside the team cares about, and the one most likely to be quietly false. CORS
misconfigured on one service, a `VITE_` variable not reaching the bundle, or a
migration that never ran would leave every existing test green.

The chat slices also start from a spec written as behaviour rather than as
endpoints. Writing the scenarios first and getting them agreed before any code
exists is the cheapest review point in the slice — a scenario is a paragraph, a
built feature is a branch.

## Decision

We will write acceptance tests as **Gherkin feature files**, run by **pytest-bdd**,
driving a real browser through **Playwright's synchronous Python API**, against
the stack from `docker compose up`.

Feature files live at `tests/bdd/features/`, step definitions at
`tests/bdd/steps/`, and page objects at `tests/bdd/pages/`. Two rules make it
work:

**Selectors are `data-testid` only, and only page objects hold them.** No step
definition contains a locator. This is the rule that keeps browser tests from
rotting: restructuring a component changes one file rather than twenty, and
tests do not break because a designer changed a label.

**The stack must already be running; the suite does not start it.** A
session-scoped fixture probes Auth, Messaging and the SPA and fails with the
command to run rather than a timeout. This is the environment the feature is
demonstrated in, so "the scenarios pass" and "the demo works" become the same
fact — and iterating on a step does not cost a stack restart.

**But a throwaway stack, running alongside the development one.** Scenarios need
an empty workspace to assert against, so the suite truncates the messaging tables
between scenarios; run against the ordinary stack it silently deletes channels
made by hand, which it did once before this was caught.
`docker-compose.test.yml` sets a different Compose project name — enough on its
own to give the stack separate volumes, containers and network without a second
copy of the Compose definition — and republishes the five ports that are reached
from the host: the SPA, Auth, Messaging, Dex and Postgres. Everything else keeps
talking over the Compose network by service name and is not published at all,
so it cannot collide.

Addressing only test-stack ports doubles as the interlock. The suite truncates
over Postgres on 5442, so aimed at a machine running just the development stack
it fails to connect instead of destroying data — nothing can tell the two apart
by inspection, because they are the same images.

The cost is a second Dex configuration. Dex expands environment variables only
in its storage, signer and connector blocks, so the issuer and the client's
redirect URI cannot be parameterised, and an OIDC issuer has to name the port
the browser actually reaches it on — it is an identity, not an address. Three
lines differ between `docker/dex/config.yaml` and `config.test.yaml`, and they
have to be kept in step by hand.

Python rather than the more common Playwright-in-TypeScript, because it keeps
one test runner, one dependency group and one lockfile for the whole repo, and
lets a step reach the database directly to set up or assert state. The
**synchronous** API specifically: the root pytest config sets
`asyncio_mode = "auto"`, so an `async def` step would be collected as an asyncio
test, and Playwright's sync API cannot be driven from inside a running loop.

## Consequences

The scenarios are readable by someone who does not write Python, which is what
makes the "agree the scenarios before building" gate real rather than
ceremonial. And they exercise the parts no other layer touches: CORS, the built
bundle's environment variables, the migration running on container start, and
the real OIDC redirect chain through Dex.

They are also the slowest and least reliable tests in the repo. A browser
suite fails for reasons that have nothing to do with the feature — a slow
container, an animation, a race between a fetch and an assertion — and every one
of those costs someone an investigation. The page objects wait on explicit
conditions rather than sleeping, which helps, but this needs active maintenance
in a way the integration tests do not.

Running two stacks is two of everything, Elasticsearch included, which is real
memory on a laptop. No scenario touches Elasticsearch or the Worker yet, so
`--scale elasticsearch=0 --scale worker=0` trims the test stack until one does.

Two specific fragilities are worth naming. Sign-in parses **Dex's own login
page**, which upstream owns and can redesign; `auth/tests/dexflow.py` already
carries the same warning about the same page. And the suite requires Docker, a
built frontend image, and Playwright's browser binaries (`playwright install
chromium`), which is a heavier setup than `uv sync` for a new contributor.

The suite must run against the **Compose frontend**, not `npm run dev`. React's
StrictMode double-invokes the effect that restores the session, firing two
`/auth/refresh` calls with one rotating cookie and tripping Auth's reuse
detection. This is written into the `base_url` fixture, because the symptom —
random sign-outs — points nowhere near the cause.

## Alternatives Considered

### Playwright with its own TypeScript runner

The mainstream choice, with the better tooling: trace viewer, codegen, UI mode,
and parallel execution that actually works. Rejected because it splits the repo's
testing across two runners, two dependency managers and two CI invocations, and
because a step that needs to assert on database state would have to go through
the API to do it. If the browser suite grows large enough that execution time
becomes the constraint, this is the decision to revisit.

### pytest with Playwright, no Gherkin

Same browser automation, plain test functions, no feature files. Meaningfully
less machinery — no step registry, no parameter parsing, no indirection between
a scenario and the code that runs it. Rejected for what the feature files buy
outside the code: a spec the team agrees to *before* implementation, in language
that does not assume the reader knows what a fixture is. The indirection is the
cost of that, and on this project the review gate is worth it.

### Selenium

Mature and familiar, but Playwright's auto-waiting removes most of the explicit
sleeps and retries that make Selenium suites flaky, and its browser contexts
give cheap per-user isolation — which this suite needs, since two-person
scenarios run Ada and Grace side by side in one browser.
