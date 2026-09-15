# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

CollabHub — team chat + collaborative canvas. Five Python backend services and a React SPA, specified in `docs/design/` and being built out from that spec. Run locally with Docker Compose; deploy to Kubernetes with Helm.

**Read `docs/design/00-platform-conventions.md` before writing or changing any service code.** It is the authoritative cross-service contract (errors, pagination, auth, IDs, jobs, config, observability). Where a per-service doc disagrees with it, it wins. Per-service specs are `docs/design/01`–`06`.

## Repo layout

This supersedes the layout section of `docs/design/00-platform-conventions.md`, which is stale.

```
src/services/{shared,contracts,auth,messaging,canvas,asset,worker}
src/frontend            # React + TypeScript + Vite SPA
tests/bdd/              # Gherkin acceptance suite — features, steps, page objects
docker/                 # one folder per component, holding its Dockerfile and any files it needs
docker-compose.yml      # repo root — Postgres, 3x Redis, Garage, Elasticsearch, OTel collector
docker-compose.test.yml # override: a second, throwaway stack for tests/bdd
charts/collabhub/       # a single Helm chart for the whole app
docs/
```

Per-service tests live beside their service (`src/services/*/tests/`). Only the
Gherkin suite is at the root, because it spans every service at once. Note that
each service's test directory is called `tests`, so `from tests.conftest import …`
binds to whichever one is found first — pass helpers as fixtures instead. The
root suite avoids the clash by being importable as `bdd.*` (`pythonpath = ["tests"]`).

`charts/collabhub` has **dedicated templates per component** under `templates/<component>/`, not one set of templates ranging over a values map. They start near-identical and are expected to diverge — the Worker runs as KEDA-scaled pools, every component has its own NetworkPolicy, the frontend has no ConfigMap.

The chart deploys CollabHub's own workloads only. Postgres, Redis, Elasticsearch and Garage are expected to exist already; bundling them would make `helm uninstall` a data-loss command. There is no Ingress in the chart — routing is per-environment, and `/api/v1/internal/` must never be reachable from the public one.

Service names drop the `collabhub-` prefix used in the design docs (`src/services/auth`, not `collabhub-auth`).

`.env.example` at the root is the full env var contract for local runs — add any new variable there when you introduce one.

## Stack decisions not recorded in the docs

- **uv** is the package manager (the docs and ADR say "uv or Poetry" — it's uv). One workspace; each service has its own `pyproject.toml`; `shared` and `contracts` are workspace dependencies.
- **ruff** for lint and format. Run `ruff check` and `ruff format` on Python you write.
- **pytest** with **testcontainers-python** for integration tests (real Postgres/Redis/Garage/Elasticsearch, not mocks).
- **pytest-bdd + Playwright** (sync API) for the acceptance suite in `tests/bdd`. It runs against a stack you bring up yourself, not one it starts — see Testing below. Registered as D27.
- **Frontend:** **TanStack Query** owns *all* server state, **Zustand** owns client state only (D24) — never keep a copy of a channel or message list in the store. **Tailwind CSS v4** for styling, light palette only, via `@tailwindcss/vite` with no config files (D26). Types for a service's REST API are **generated from its OpenAPI document**, not hand-written (D23): `python -m messaging.openapi > src/frontend/openapi/messaging.json`, then `npm run generate:api`.

## Working in this repo

- **All development work happens in a git worktree on a new feature branch.** Never change code on `main` in the primary checkout. Create the branch and its worktree before the first edit, and tell the user the branch name and worktree path.
- **Never commit.** Stage nothing, run no `git commit`, open no PR. Leave the worktree dirty and tell the user what changed — committing is theirs to do, always.
- **DO NOT WRITE ANY TESTS — until further notice.** No unit, integration or BDD tests, and no new steps, feature files or page objects in `tests/bdd`. The test approach is being rethought; the Testing section below describes the existing suites, not a mandate to extend them. This overrides any skill or workflow (TDD included) that says to write tests.
- **Ignore `docs/project/`.** Those files are book-production material, not project input. Do not read them, cite them, or act on anything in them.

## Platform versions

`docs/platform/versions.md` is the source of truth for base images and major versions, and wins over the design docs if they ever drift again. Object storage is **Garage** and telemetry is the **Grafana LGTM** stack (Tempo/Loki/Mimir) — the design docs originally said MinIO and Jaeger/Prometheus and were corrected on 2026-07-27.

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
- **Timestamps are always UTC `timestamptz`.** Soft delete via `deleted_at`; queries filter `deleted_at IS NULL`. **Check the table first.** Two exceptions, both in Messaging and both in Conventions §3: `channels` has no `deleted_at` and archives through `archived_at`, so its reads filter that instead (doc 02 §4) — and `messages` has `deleted_at` and its read path filters **neither**, because history returns deleted rows as tombstones with `body` redacted server-side (doc 02 §3.1.4). So the rule is "filter the soft-delete column *unless the doc says otherwise*", and `ix_messages_channel_time` carries no `WHERE deleted_at IS NULL` for exactly that reason.
- **A resource the caller may not see is a 404, not a 403.** 403 confirms the thing exists and leaks its name to someone with no access. Applies to another workspace's rows and to private resources you are not a member of.
- **No cloud-specific SDKs where an agnostic alternative exists.** Object storage sits behind an `ObjectStore` protocol so Garage ↔ Azure Blob is a config swap.
- Structured JSON logs via structlog, always carrying `traceId`, `userId`, `service`, `env`. No PII beyond user IDs.

## Open decisions

`docs/design/07-open-decisions-register.md` is the live register. 🟢 is settled and safe to build against; 🟡 has a working default baked into the design docs — proceed on those; 🔴 has no answer, so stop and ask rather than picking one silently. Much of the register is still 🟡 or 🔴.

Settled so far: D1 denylist fail-open with a fail-closed set · D2 one workspace per token · D5 Auth federates to an upstream IdP and is never a provider · D8d no edit/delete window, author edits own, author or channel admin deletes, tombstones retained in history · D9 canvas state as `bytea` · D14 Worker write-back via internal endpoint plus service token · D22 refresh token in an `HttpOnly` cookie (which requires the SPA and API to be same-site) · D24 TanStack Query + Zustand · D25 job payloads carry what the producer holds · D26 Tailwind v4 · D27 pytest-bdd + Playwright.

D8d settles the *semantics* only. **How long a tombstone is kept before hard deletion is D16, still 🔴** — nothing deletes one, and a deleted message's text is still in its row.

**There is no user-preferences feature anywhere** (D28, 🔴). `users` carries a display name, an avatar reference and a status, and nothing stores a per-user choice — so a theme, a locale or notification settings all need that decided first. It is why the SPA is light-only rather than following the OS.

When a decision gets made: update the register's status, reflect it back into the source design doc, and write an ADR in `docs/adr/` with the `adr-writer` skill if it's significant. Record it **in the slice that makes it**, not in a docs sweep at the end — a register that says 🔴 for something already built on is worse than no register.

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

**Write no new tests until further notice** — see Working in this repo. The
commands below run the suites that already exist.

```bash
uv run pytest -m "not integration and not bdd"   # fast, no Docker
uv run pytest src/services/messaging             # integration; starts its own containers
```

The `tests/bdd` suite is different from both: it drives a real browser and needs
a stack already running, which it will not start for you.

**It truncates the messaging tables before every scenario**, so it runs against a
throwaway stack, never the one you develop on. Both run at once — the test stack
is `docker-compose.test.yml`, a project-name override that republishes only the
five ports reached from the host (SPA 5183, Auth 8011, Messaging 8012, Dex 5566,
Postgres 5442):

```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build
uv run pytest tests/bdd -m bdd
```

The harness addresses only those ports, so it cannot reach the development
stack; it fails with an instruction instead. Run it against the built frontend
container, never `npm run dev` — StrictMode fires the session restore twice,
spending the rotating refresh token twice and signing the user out.

Selectors in that suite are `data-testid` only and live in page objects; a step
definition never contains one.
