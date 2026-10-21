# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

CollabHub — team chat + collaborative canvas. Five Python backend services and a React SPA, specified in `docs/design/` and being built out from that spec. Run locally with Docker Compose; deploy to Kubernetes with Helm — locally to k3d through `scripts/deploy.sh`.

**Read `docs/design/00-platform-conventions.md` before writing or changing any service code.** It is the authoritative cross-service contract (errors, pagination, auth, IDs, jobs, config, observability). Where a per-service doc disagrees with it, it wins. Per-service specs are `docs/design/01`–`06`.

## Repo layout

This supersedes the layout section of `docs/design/00-platform-conventions.md`, which is stale.

```
src/services/{shared,contracts,testkit,auth,messaging,canvas,asset,worker}
src/frontend            # React + TypeScript + Vite SPA
tools/delivery/         # the delivery backends — where issues live — and the `delivery` CLI; dev only
tests/bdd/              # Gherkin acceptance suite — features, steps, page objects
tests/smoke/            # smoke packs against a running deploy's origin — scripts/smoke.sh
docker/                 # one folder per component, holding its Dockerfile and any files it needs
docker-compose.yml      # repo root — Postgres, 3x Redis, Garage, Elasticsearch, Dex, OTel collector
docker-compose.test.yml # override: a second, throwaway stack for tests/bdd
charts/collabhub/       # a single Helm chart for the whole app
charts/collabhub-deps/  # data stores, Dex, Secrets, Dex's Ingress — any environment; credentials required (D41)
scripts/                # build.sh, test.sh, deploy.sh, smoke.sh — developers and CI call the same ones
docs/
```

**`scripts/` is the entry point for building, checking and deploying.** CI runs the
same scripts, so a step that only exists in a pipeline file, or only in the README,
is a bug. They are bash 3.2-compatible (macOS), share `scripts/lib/common.sh`, and
take their overridable settings — `IMAGE_REGISTRY`, `IMAGE_TAG`, `KUBE_CONTEXT`,
`DEPLOY_ENV`, `NAMESPACE`, `APP_ORIGIN` — from the environment.

Per-service tests live beside their service, in `src/services/*/tests/unit/` and
`tests/integration/` — and `tools/*/tests/` the same way. **The directory decides the layer**: `testkit`'s pytest
plugin marks each test by where it lives, stops the run for a test anywhere else,
and cuts unit tests off from the network and Docker. Only the Gherkin suite and
the smoke packs are at the root: the suite spans every service at once, and
`tests/smoke` proves a deploy rather than a rule (see Testing).

No service's `tests` directory has an `__init__.py`, so `tests` is one namespace
package spanning all of them and `from tests.… import` binds to whichever sorts
first — ruff bans it (TID251). Shared helpers live in `src/services/testkit`, a
dev-only workspace member no image installs; a service's own go through fixtures.
The root suite avoids the clash by being importable as `bdd.*` (`pythonpath = ["tests"]`).

`charts/collabhub` has **dedicated templates per component** under `templates/<component>/`, not one set of templates ranging over a values map. They start near-identical and are expected to diverge — the Worker runs as KEDA-scaled pools, every component has its own NetworkPolicy, the frontend has no ConfigMap.

The chart deploys CollabHub's own workloads only. Postgres, Redis, Elasticsearch and Garage are expected to exist already; bundling them would make `helm uninstall` a data-loss command. The chart's Ingress is opt-in (D40): its public-prefix allow-list lives in `templates/ingress.yaml`, so `/api/v1/internal/` is never routable; the host comes from `APP_ORIGIN` and never from a values file.

`charts/collabhub-deps` is an environment's answer to all of that — the data stores, Dex, the Secrets the app chart's `envFromSecrets` names, and Dex's Ingress on the instance's host. **No credential has a default** (D41): `values-k3d.yaml` carries throwaway ones and is development only; any other environment supplies them with `scripts/deploy.sh infra -- --set-string <path>=<value>`. `scripts/deploy.sh` refuses k3d values on any context but `k3d-collabhub`, and any other environment's values on it. Its Dex config is a third copy beside `docker/dex/config.yaml` and `config.test.yaml` — change all three together. Gaps a deploy finds in `charts/collabhub` get fixed in that chart, never worked around in the scripts or the dependency chart.

Service names drop the `collabhub-` prefix used in the design docs (`src/services/auth`, not `collabhub-auth`).

`.env.example` at the root is the full env var contract for local runs — add any new variable there when you introduce one.

## Stack choices

- **uv** is the package manager (the docs and ADR say "uv or Poetry" — it's uv). One workspace; each service has its own `pyproject.toml`; `shared` and `contracts` are workspace dependencies.
- **ruff** for lint and format. Run `ruff check` and `ruff format` on Python you write.
- **pytest** with **testcontainers-python** for integration tests — every dependency (Postgres, Redis, Elasticsearch, Garage, Dex) is started by testcontainers, never the Compose stack. Unit tests have no network and no Docker (pytest-socket, applied by `testkit`). **pytest-cov** reports unit coverage; nothing gates on it yet. The layers are register D32.
- **pytest-bdd + Playwright** (sync API) for the acceptance suite in `tests/bdd`. It runs against a throwaway Compose stack that `scripts/test.sh e2e` brings up and tears down — see Testing below. Registered as D27.
- **Frontend:** **TanStack Query** owns *all* server state, **Zustand** owns client state only (D24) — never keep a copy of a channel or message list in the store. **Tailwind CSS v4** via `@tailwindcss/vite` with no config files (D26). A service's REST types are **generated from its OpenAPI document** where it has an `openapi` module (D23): `python -m <service>.openapi > src/frontend/openapi/<service>.json`, then `npm run generate:api`. A service without one is hand-typed under `src/frontend/src/lib/` (doc 06 §2 says which) — work that changes its responses either generates its types first or updates the hand-typed ones and says why.

## Working in this repo

- **All development work happens in a git worktree on a new feature branch.** Never change code on `main` in the primary checkout. In an interactive session, create the branch and its worktree before the first edit, and tell the user the branch name and worktree path; under `scripts/deliver.sh` the workflow creates them and the agent works where its context block says.
- **Never commit.** Stage nothing, run no `git commit`, open no PR. Leave the worktree dirty and tell the user what changed — committing is theirs to do, always. **One exception:** the delivery workflow's runner — never an agent, never a person's session — commits and pushes its own `feature/<key>` branch after every stage, at a stop and at the approval (ADR `261016-delivery-commits-its-own-branch`).
- **New behaviour is test-driven, at the lowest layer that can prove it** (register D32). Write the failing test first — a unit test for a rule, a mapping or a wire shape; an integration test for SQL, a socket or a stream, against dependencies testcontainers starts; a `tests/bdd` scenario only for a key user journey — run it, and — in an interactive session — **stop at red** so the tests can be reviewed before any production code is written. The stop is for interactive sessions only. A headless session (`claude -p`) has nobody to review at red, so it runs the failing tests, records what each failed with, and carries on to green; under `scripts/deliver.sh` the test-reviewer agent's approval is that review, and the workflow carries on to the code-writer without stopping (see Delivery workflow). Frontend unit tests are Vitest, beside their source (see Testing). Never fake a database to reach SQL behaviour from a unit test.
- **Ignore `docs/project/`.** Those files are book-production material, not project input. Do not read them, cite them, or act on anything in them.

## Delivery workflow

`scripts/deliver.sh <key>` takes one issue to a tested feature ready for review — for a `gh-` key, a pull request — headless, through seven agents in `.claude/agents/`: plan-writer → plan-reviewer → test-writer → test-reviewer → code-writer → code-reviewer → acceptance-reviewer. A reviewer can send work back to its writer, and a later stage can send it back to the pair before its own — acceptance to the code-writer, code to the test-writer, tests to the plan-writer — with its reasons in a send-back file under `reviews/`; the workflow deploys the branch's preview before each acceptance pass, and the acceptance-reviewer runs `scripts/smoke.sh` against it and writes `docs/plans/<key>/04-proof.md` — the record a person accepts from — leaving the preview up; any agent can stop the run with `needs_human`, and its questions go into `docs/plans/<key>/needs-human.md` for a person to answer before rerunning — a last resort: a run is meant to finish without a person, so an agent settles what the issue leaves open by the best-fitting reading and records it as an **assumed** decision for the human to read at the end. It works in `../caw-<key>` on `feature/<key>`. No agent commits; the runner commits the branch after every stage — `delivery(<key>): <stage> <result>, round <R>` — and at a stop, a failure and the approval, and pushes it to `origin` for a `gh-` key or `forge` for an `issue-` key (`DELIVER_REMOTE` overrides, `DELIVER_PUSH=0` turns fetching and pushing off). Its state and `history.log` are in `docs/plans/<key>/run/`, committed, so a run resumes on any machine with the branch; every run fetches first and fast-forwards, and a branch that has diverged stops it — nothing is merged or forced. `DELIVER_DEADLINE` ends a run at a checkpoint with exit 4 before a job limit can kill it mid-stage. **`.github/workflows/deliver.yml`** runs the same `scripts/deliver.sh` on a hosted runner from a manual trigger — `key`, `restart`, `model`, `stub` (`.claude/delivery/stub-claude`, no model) — and is rerun with the same key to resume. An accepted GitHub delivery ends in a PR into `main` whose body is the proof, with the screenshots it cites committed and removed again right after `accepted` so they show inline but never reach `main` — the repo is squash-only for it — and the runner dispatches **`.github/workflows/preview.yml`**, which deploys the PR's branch on a hosted runner and holds it until the PR is approved or closed. With the `SLACK_BOT_TOKEN` and `SLACK_CHANNEL` secrets a run reports to Slack, one thread per delivery, and each preview gets a random password posted only there; without them, nothing is posted and previews keep `collabhub`. `DELIVER_PR=0` opens no PR; a local issue never gets one. The plan pair and the code-reviewer run on Opus, the test pair, the code-writer and the acceptance-reviewer on Sonnet — hard-coded in `default_model` in `tools/delivery/delivery/run/rules.py` and each agent's `model:` line, which change together; `docs/plans/ch08/05-model-effort-handoff.md` has the runs behind it. The script is a wrapper: the workflow is the Python package `delivery.run` in `tools/delivery/`, and its docstring is the reference. Its tool and write rules are held to `tools/delivery/tests/unit/fixtures/deliver-rules.json`, captured from the bash script it replaced — change the fixture and the rule together, on purpose. `.claude/delivery/loop-test.sh` proves its state machine through the wrapper with a fake `claude`, and is run after any change to it. What a run needs — tools, `gh` signed in, the repo's secrets and settings, Slack — is `docs/delivery/prerequisites.md`, and `uv run delivery [--backend github --url URL] prereqs` checks it.

**Where this file and an agent's instructions differ in kind, the delivery rules win for the agent.** This file is written for a person's session: "tell the user", "stop and ask" and the Testing commands below assume someone is there. A delivery agent has nobody — it stops through `needs_human`, runs tests as `.claude/delivery/agent-context.md` *Running tests* says (never `scripts/test.sh`, except the code-writer's final verification), and settles what is open as *Decide, record, carry on* says. Every fact and convention here still binds it.

What every agent shares — the team, how a run works, what an agent may touch, rounds and the final round, severity, deadlocks, escalation, the `StructuredOutput` result — lives once in `.claude/delivery/agent-context.md`, and each agent reads it first. An agent's own file holds only its role; put anything that applies to more than one agent in the shared file, not in two prompts. It sits outside `.claude/agents/` because every file there is loaded as an agent.

An issue for it is written with the `issue-writer` skill, which grills the user against `docs/issues/exemplar-issue.md` — where the rules meet, the paths each must hold on, the assumptions it leans on, and a timeline for anything timed. Update the exemplar issue when a delivery's plan has to decide something its issue should have.

**Where an issue lives is a delivery backend** (ADRs `261016-pluggable-delivery-backends`, `261016-delivery-runner-in-python-by-key`): `tools/delivery/` holds one adaptor per backend — `local` (`docs/issues/NNN.md`) and `github` (through `gh`) — behind the `delivery` CLI, chosen by `--backend`/`--url`, else `DELIVERY_BACKEND`/`DELIVERY_URL`, else local. Only the edges call it — the `issue-writer` skill, `deliver.sh` and the GitHub Actions workflow that runs it — and the agents read only the issue-file copy and take every path from their context block, so no agent knows the backend. An issue is named by a **key**: `issue-N` locally, `gh-N` on GitHub (`fj-N`, `ado-N` reserved), because GitHub's numbers collide with the local ones. `deliver.sh` takes a key and fetches the issue through the backend on every run, into `docs/plans/<key>/00-issue.md`; `docs/plans/<key>/source.json` records where it came from and refuses another backend's issue under the same key. The plans are `docs/plans/ch09/04-delivery-backends-plan.md`, `06-delivery-runner-plan.md` and `08-delivery-actions-plan.md`.

The plan-writer models its plans on `docs/plans/exemplar-implementation-plan.md`, which records what past plans got right and what their builds found missing — update it when a build teaches something new.

## Platform versions

`docs/platform/versions.md` is the source of truth for base images, major versions and which product fills each role (object storage, telemetry), and wins over the design docs if they ever drift.

Library versions (FastAPI, SQLAlchemy, React) are out of that file's scope — pin those per service.

## Conventions that are easy to get wrong

- **Every service owns its own database.** Services must not share a schema or read another service's tables — go through its API or an event. Cross-service ID columns carry no foreign keys.
- **UUID v7 primary keys, generated by the application, not the database** — IDs must be known before insert.
- **Errors are RFC 7807 Problem Details** (`application/problem+json`) on every non-2xx, implemented once in `shared` as FastAPI exception handlers. Never put stack traces or internal messages in `detail`.
- **Pagination is cursor-based only** (`?limit=`, default 50 / max 200, `?cursor=`; response `{items, nextCursor}`). Never `OFFSET` for user-facing lists.
- **JSON is camelCase; SQL columns are snake_case.**
- **Three logically separate Redis instances**, and they are not interchangeable: R1 cache/token denylist, R2 Socket.IO backplane, R3 job streams.
- **Auth is stateless.** Services verify RS256 JWTs against cached JWKS — there is no per-request call to the Auth service. Use the shared `Depends(require_user)`.
- **A token is scoped to one workspace** (`wsp` claim). Authorization reads the claim and never takes a workspace ID from the request path or body in its place — that substitution is a tenancy leak.
- **Internal endpoints are different.** Anything under `/api/v1/internal/` is called by another service, guarded by `Depends(require_service("scope"))`, and uses audience `collabhub-internal` rather than `collabhub`. Never put `require_user` and `require_service` on the same route. See Conventions §5.5.
- **The token denylist fails open, except where it doesn't.** Ordinary requests accept the token when R1 is unreachable; workspace membership changes, role grants and asset deletion return 503 instead. See Conventions §5.2.
- **Socket.IO event naming:** client→server are verbs (`send_message`); server→client are past-tense facts (`message_received`). Canvas is the documented exception — it follows the Yjs sync protocol names.
- **Jobs are fire-and-forget onto Redis Streams and handlers must be idempotent** (`jobId` is the idempotency key). Producers never block on the Worker; the Worker never writes to another service's tables.
- **All config comes from environment variables**, loaded with pydantic-settings. Nothing baked into images. `SCREAMING_SNAKE_CASE`.
- **Timestamps are always UTC `timestamptz`.** Soft delete via `deleted_at`; queries filter the soft-delete column **unless the design doc says otherwise. Check the table first** — not every table has `deleted_at`, and not every read path filters it (Conventions §3 lists the exceptions).
- **A resource the caller may not see is a 404, not a 403.** 403 confirms the thing exists and leaks its name to someone with no access. Applies to another workspace's rows and to private resources you are not a member of.
- **No cloud-specific SDKs where an agnostic alternative exists.** Object storage sits behind an `ObjectStore` protocol so Garage ↔ Azure Blob is a config swap.
- Structured JSON logs via structlog, always carrying `traceId`, `userId`, `service`, `env`. No PII beyond user IDs.

A decision can make a deliberate exception to one of these. It is recorded in the register, the conventions doc and the design doc it touches — never here — and code that follows a recorded exception is right, not a finding. Look before you call one a breach.

## Open decisions

`docs/design/07-open-decisions-register.md` is the live register. 🟢 is settled and safe to build against; 🟡 has a working default baked into the design docs — proceed on those; 🔴 has no answer, so stop and ask rather than picking one silently (a delivery agent stops through `needs_human`). Much of the register is still 🟡 or 🔴.

**Read a decision's status in the register, never from memory or from this file.** This file states how to work, not what has been decided: it names no decision's status and restates none of its consequences, because every copy of a decision falls behind the register. Read the entries a change touches, including what each says has been *built against it* — a 🔴 can already have code leaning on it.

When a decision gets made: update the register's status, reflect it back into the source design doc, and write an ADR in `docs/adr/` with the `adr-writer` skill if it's significant. Record it **in the slice that makes it**, not in a docs sweep at the end — a register that says 🔴 for something already built on is worse than no register. A slice never edits this file to record a decision; if this file contradicts the register, the register wins and the contradiction is a person's to fix.

## Code quality

Two Claude Code hooks, wired in `.claude/settings.json`:

- **After every `Write`, `Edit` or `Bash`** — `.claude/hooks/lint.sh` formats and
  lints the files that changed (`ruff` for Python, `eslint` for `.ts`/`.tsx`),
  autofixing what it can. It **blocks** on anything left, because lint findings
  are mechanical and always fixable. Roughly 0.3s for Python, 1.1s for
  TypeScript. `Bash` is in the matcher because a heredoc or `sed -i` changes a
  file just as surely as `Edit` does — those arrive in
  `tool_response.bashEditDiff.changedFiles`, and a Bash command that touched no
  file exits in ~0.1s.
- **At the end of a turn** — `.claude/hooks/security.sh` runs `ruff --select S`
  (flake8-bandit), the convention checks below, `gitleaks` over the working tree,
  and `semgrep` with `p/python` + `p/secrets`. About 4s. It is **advisory**: it
  reports and lets the turn end, because a false positive must never strand a
  session.

`.claude/hooks/checks/conventions.py` is the part no off-the-shelf tool can do —
CH001 tenancy id taken from the request rather than the `wsp` claim · CH002
`require_user` and `require_service` on one route · CH003 an `/internal/` route
with no `require_service` · CH004 a 403 answering a lookup that came back empty
· CH005 `OFFSET` · CH006 SQL built by interpolation · CH007 exception text in a
Problem Details `detail` · CH008 PII in a log call · CH009 `select()` on a
soft-delete table with no `deleted_at` filter. It runs over everything changed
since HEAD; run it by hand with `python3 .claude/hooks/checks/conventions.py
[files...]`.

Waive a finding on its own line or in the comment block above it, always with a
reason:

```python
# conventions: ok — the caller's own account state, not someone else's row.
raise ProblemException.forbidden("This account belongs to no workspace.")
```

The rule sets are tuned so the tree is **clean today**: a new finding means new
code, not a backlog. `ruff.toml` records which rule families were left out and
what each would have cost.

## Migrations

Alembic per service, against that service's own database only (`alembic upgrade head`).

## Testing

**A test pyramid** (D32), and the failing test goes at the lowest layer that can
prove the behaviour — see Working in this repo.

- **Unit** — every rule, mapping and wire shape. No network, no Docker. A rule
  that sits behind a database fetch is made testable by pulling the decision into
  a pure function over the loaded row, never by faking a repository or a session.
- **Integration** — each service at its public boundary (REST, Socket.IO, a
  stream consumer), in-process, against dependencies testcontainers starts. SQL
  behaviour is proven here.
- **End-to-end** — `tests/bdd`, key user journeys only. A field rule belongs lower down.

**Integration fixtures come from `testkit`, registered by its plugin — never import
them into a conftest** (D34). One container per store per session:
`postgres_server` (a service creates its own database on it with
`testkit.databases.service_database`), `redis_server` with `redis_cache` and
`redis_streams` (one Redis, an index per role: R1 `/0`, R2 `/1`, R3 `/2` — Pub/Sub
is server-wide, so that separates keys, not backplane messages), and
`elasticsearch_url` / `elasticsearch`, started only when a test asks. `tokens` mints
user and service tokens; `testkit.apps` has `asgi_client` and `serve`,
`testkit.db` has `truncate`, `testkit.search` seeds the `messages` index with the
Worker's own code. A unit test that depends on a container fixture stops the run.
`garage_server` starts Garage with a bucket and a key, for object storage. The
Worker's `tests/integration/conftest.py` has `run_consumer` and `jobs`.

```bash
scripts/test.sh                  # lint, unit, integration — the everyday run
scripts/test.sh unit             # pytest then Vitest, no network or Docker; prints coverage
scripts/test.sh integration -- src/services/messaging   # starts its own containers
scripts/test.sh e2e              # tests/bdd: brings the test stack up, runs, tears down
scripts/test.sh e2e -- --headed -k channels
scripts/test.sh all              # all four layers — what CI runs
scripts/smoke.sh --origin http://localhost:8080   # smoke packs against a running deploy
scripts/smoke.sh                 # …against this branch's preview
(cd src/frontend && npm test)    # Vitest only; `npm run test:watch` while working
```

**Every `scripts/test.sh` run rewrites `docs/test-report.md`**, after each layer and
whether it passed or not — it is committed, and it is the feedback until CI exists.
Each tool writes JUnit and coverage XML into `build/test-results/` and
`testkit.report` merges them; a layer not run this time keeps its last result there.
The report leaves out timestamps and durations so its diff shows only changed
results — keep it that way. Never edit it by hand. `testkit.plugin` labels each
Gherkin scenario with its feature, name, line and tags in the JUnit file, because
pytest-bdd's Cucumber JSON drops a scenario that fails in setup.

**The SPA's unit tests are Vitest**, beside their source as `Foo.test.tsx`, with the
helpers in `src/frontend/src/test/`:
- `renderWithProviders` / `renderHookWithProviders` give a fresh `QueryClient` per test.
- `api.ts` holds MSW stubs typed from the generated OpenAPI types, so a stub that
  doesn't match the API fails `tsc`, and any unstubbed request fails the test.
- `socket.ts` is a fake socket. `connect()` is mocked to it for every test, so no
  test opens a real one.
- `factories.ts` holds `aChannel()`, `aMessage()` and friends.

Query by role, label or text: `data-testid` belongs to the BDD suite, and a Vitest
test neither adds nor reads one.

The `tests/bdd` suite is different from both: it drives a real browser against a
whole Compose stack, which `scripts/test.sh e2e` starts with `up --build --wait`
and takes down afterwards, pass or fail. `KEEP_STACK=1` leaves it up, so you can
rerun `uv run pytest tests/bdd -m bdd` without the rebuild.

**It truncates the messaging tables before every scenario**, so it runs against a
throwaway stack, never the one you develop on. Both run at once — the test stack
is `docker-compose.test.yml`, a project-name override that republishes only the
seven ports reached from the host (SPA 5183, Auth 8011, Messaging 8012, Asset 8014,
Dex 5566, Garage 3910, Postgres 5442). The whole stack runs there, the Worker and
Elasticsearch included.

The harness addresses only those ports, so it cannot reach the development
stack; it fails with an instruction instead. Run it against the built frontend
container, never `npm run dev` — StrictMode fires the session restore twice,
spending the rotating refresh token twice and signing the user out.

Selectors in that suite are `data-testid` only and live in page objects; a step
definition never contains one.

**`tests/smoke` is not a test layer.** It proves a deploy, not a rule: non-destructive,
through the origin only, and never collected by `scripts/test.sh` or a plain
`uv run pytest`. A feature's own pack is written by the acceptance-reviewer under
`build/acceptance/` and thrown away.
