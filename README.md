# CollabHub — sample project for *Claude at Work*

This repo is the running sample project for **Claude at Work** (Manning), by Elton Stoneman.

It's a deliberately realistic codebase: a greenfield product with real design documents,
real architectural decisions, and real recurring maintenance work — the kind of project you'd
get Claude Code to build.

> [Claude at Work - repo](https://github.com/sixeyed/claude-at-work)

**CollabHub** is the product being built: a team collaboration platform that pairs a
Slack-like chat experience with a Figma-like collaborative canvas in a single app.

## Current state

Early-stage. **Auth is complete**, including federated sign-in through Dex.
**Messaging has its core**: channels with administration and membership,
messages with history, editing and deleting, and the Socket.IO `/messaging`
namespace carrying live delivery, the write path and typing indicators. Threads,
reactions, read receipts and search are not built — [doc 02
§3.1.5](docs/design/02-messaging-service.md) lists every endpoint the design
names and the service does not implement, with the reason for each. Canvas,
Asset and Worker are still scaffold — a process that reads its configuration and
answers `/health/live` and `/health/ready`, with no models, migrations, routes
or job handlers. **The SPA** has sign-in, a workspace switcher and the whole chat
shell. Chapters of the book add code, configuration and automation to this repo
as they go.

**[The open-decisions register](docs/design/07-open-decisions-register.md) is the
list of what is settled and what is not.** It is maintained as decisions are
made, and this README points at it rather than keeping a second copy that can
disagree with it — which is exactly what happened before. Every significant one
also has an ADR in [`docs/adr/`](docs/adr/).

Three are worth knowing before reading any code, because they constrain
deployment or the shape of everything above them. **D22** — the browser keeps its
refresh token in an `HttpOnly; Secure; SameSite=Strict` cookie, so the SPA stores
nothing at all and **the SPA and API must be deployed same-site**
([ADR](docs/adr/260728-refresh-token-in-an-httponly-cookie.md)). **D5** — Auth
federates to an upstream IdP and is never an OpenID Provider itself
([ADR](docs/adr/260728-federate-to-an-upstream-oidc-provider.md)). **D2** — an
access token is scoped to exactly one workspace, so switching is a token
exchange ([ADR](docs/adr/260727-single-active-workspace-per-token.md)).

Still open and worth knowing about: **D28** — there is no user-preferences
feature anywhere, which is why the SPA is light-only rather than following the
OS; and **D16** — retention values are unset, so nothing hard-deletes anything.

`collabhub-shared` carries the cross-cutting layer so the next service inherits it: RFC 7807
Problem Details, UUID v7, JWKS-backed verification, the token denylist, cursor pagination and
CORS. The job envelope and the `ObjectStore` protocol are still to come, and
`collabhub-contracts` is still empty.

## Where to read next

| | |
|---|---|
| [`docs/design/00-platform-conventions.md`](docs/design/00-platform-conventions.md) | **Start here.** The cross-service contract every service doc builds on. |
| [`docs/design/07-open-decisions-register.md`](docs/design/07-open-decisions-register.md) | What is still undecided, and what has been settled. |
| [`docs/adr/`](docs/adr/) | One file per significant decision, with the rejected options. |
| [`docs/platform/versions.md`](docs/platform/versions.md) | Tracked upstream versions for every platform component. |

Each component documents itself — how to run it, what it owns, and the rules that are easy
to get wrong:

| Component | Design doc | Service README |
|-----------|-----------|----------------|
| Auth | [01](docs/design/01-auth-service.md) | [src/services/auth](src/services/auth/README.md) |
| Messaging | [02](docs/design/02-messaging-service.md) | [src/services/messaging](src/services/messaging/README.md) |
| Canvas | [03](docs/design/03-canvas-service.md) | *scaffold* |
| Asset | [04](docs/design/04-asset-service.md) | *scaffold* |
| Worker | [05](docs/design/05-worker-service.md) | *scaffold* |
| Frontend SPA | [06](docs/design/06-frontend-spa.md) | [src/frontend](src/frontend/README.md) |

## Architecture

Five backend services, each independently deployable with its own database and its own
container image, plus a single-page frontend:

| Component | Role |
|-----------|------|
| Auth service | Identity, JWT issuance, workspace membership — the authorization source of truth |
| Messaging service | Channels, threads, messages, reactions; real-time delivery |
| Canvas service | Collaborative design documents — CRDT relay, presence, snapshot persistence |
| Asset service | File uploads and downloads via presigned object-storage URLs |
| Worker service | Headless background jobs: indexing, thumbnails, notifications, exports, retention |
| Frontend SPA | React + TypeScript client for both chat and canvas |

**Stack:** Python 3.12 · FastAPI / Uvicorn · SQLAlchemy + Alembic · Socket.IO · PostgreSQL ·
Redis (cache, real-time backplane, and job streams) · Elasticsearch · S3-compatible object
storage (Garage) · Dex · Kubernetes · OpenTelemetry into the Grafana LGTM stack.

Python was chosen over .NET — see
[ADR 260708](docs/adr/260708-python-instead-of-dotnet.md) for the reasoning.

```
docs/design/      Architecture and per-service design docs
docs/adr/         Architecture Decision Records
docs/platform/    versions.md — tracked upstream versions
docs/plans/       Strategy, delivery and per-slice implementation plans
src/services/     shared, contracts, and the five backend services (one uv workspace)
src/frontend/     React + TypeScript SPA (Vite)
tests/bdd/        The Gherkin acceptance suite — it spans every service, so it lives here
docker/           One folder per component: its Dockerfile and any files it needs
charts/collabhub/ Helm chart covering every component
.claude/skills/   Project skills: adr-writer, stack-update-checker
```

## Running it locally

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 24, Docker.

```bash
cp .env.example .env   # nothing in it is a real secret
uv sync                # one workspace, one lockfile
uv run pytest          # unit + integration tests (integration needs Docker)
uv run ruff check . && uv run ruff format --check .
```

Integration tests start real Postgres, Redis and Dex containers (Conventions §11). The `bdd`
suite is different again — it needs the whole Compose stack already running (see below). To
run only what needs no Docker at all:

```bash
uv run pytest -m "not integration and not bdd"
```

Bring up the full stack — Postgres, the three Redis instances, Dex, Garage, Elasticsearch,
the OTel collector, all five services and the SPA:

```bash
docker compose up --build
```

Then open <http://localhost:5173> and **sign in as `ada@collabhub.dev` with the password
`collabhub`** (or `grace@`, or `alan@`). Health checks are on `:8001` Auth, `:8002`
Messaging, `:8003` Canvas, `:8004` Asset, `:8005` Worker.

Every account owns a personal workspace *and* belongs to the shared **CollabHub
Demo** workspace. Two people only see each other's channels in the shared one, so
switch to it in the sidebar before trying anything with a second user.

Auth and Messaging have APIs — see their READMEs
([auth](src/services/auth/README.md), [messaging](src/services/messaging/README.md))
and their interactive docs at <http://localhost:8001/docs> and
<http://localhost:8002/docs>.

### Acceptance tests

The Gherkin suite in `tests/bdd/` drives a real browser through the whole stack.
**It truncates the messaging tables before every scenario** — scenarios like
"Ada's channel list is empty" cannot pass with real channels in the workspace —
so it runs against a throwaway stack, never the one you demo on.

`docker-compose.test.yml` is an override that gives that stack its own Compose
project name — and with it its own volumes — and moves the five ports anyone
reaches from the host. **It runs alongside your development stack**, so you can
leave that up and keep working:

```bash
uv run playwright install chromium        # once

docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build
uv run pytest tests/bdd -m bdd
uv run pytest tests/bdd -m bdd --headed   # watch it drive the browser
docker compose -f docker-compose.yml -f docker-compose.test.yml down
```

| | development | test |
|---|---|---|
| SPA | 5173 | **5183** |
| Auth | 8001 | **8011** |
| Messaging | 8002 | **8012** |
| Dex | 5556 | **5566** |
| Postgres | 5432 | **5442** |

Nothing else is published on the test stack — Canvas, Asset, Worker,
Elasticsearch, Garage and the OTel collector still run, they are just reached
over the Compose network by name. Both stacks running does mean two of
everything, Elasticsearch included; `--scale elasticsearch=0 --scale worker=0`
on the test stack trims it, since no scenario touches either yet.

Addressing only test-stack ports is also the safety interlock. The suite
truncates over 5442, so run against a machine with just the development stack up
it fails to connect rather than deleting your channels — it cannot tell the two
apart by looking, because they are the same images.

`down` without `-v` keeps both projects' volumes, so the test database is reused
between runs. To start it genuinely empty, add `-v`.

The suite runs against the test stack's frontend container, **not** `npm run
dev` — in dev, React's StrictMode fires the session restore twice, which spends
the rotating refresh token twice and signs the user out.

For frontend work where you are not running the acceptance tests, the Vite dev
server is faster than rebuilding the Nginx image:

```bash
cd src/frontend && npm install && npm run dev
```

The SPA's Messaging types are generated from that service's OpenAPI document
(register D23). After changing a Messaging route or schema:

```bash
uv run python -m messaging.openapi > src/frontend/openapi/messaging.json
cd src/frontend && npm run generate:api
```

### Object storage needs one manual step

Garage will not serve S3 traffic until a cluster layout is assigned, which is a one-off on
a fresh volume:

```bash
docker compose exec garage /garage status                     # note the node ID
docker compose exec garage /garage layout assign -z dc1 -c 1G <node-id>
docker compose exec garage /garage layout apply --version 1
docker compose exec garage /garage bucket create collabhub-assets
docker compose exec garage /garage key create collabhub-local
docker compose exec garage /garage bucket allow --read --write collabhub-assets --key collabhub-local
```

Put the key ID and secret it prints into `OBJECT_STORE_ACCESS_KEY` / `_SECRET_KEY` in `.env`.
Nothing reads them yet — the Asset service has no object-storage code.

### Deploying

```bash
helm lint charts/collabhub
helm template collabhub charts/collabhub
```

The chart deploys CollabHub's own workloads only. Postgres, Redis, Elasticsearch and Garage
are expected to exist already — they have their own lifecycle and backups, and bundling them
would make `helm uninstall` a data-loss command. There is no Ingress either: routing is
per-environment, and `/api/v1/internal/` must never be reachable from the public one.

Because routing is per-environment, **two constraints land on whoever writes it**:

- `/api/v1/internal/` must not be reachable from the public ingress (Conventions §5.5).
- The SPA and the API must be **same-site** — one registrable domain, or one origin. The
  refresh cookie is `SameSite=Strict` (register D22), so splitting them across genuinely
  different domains silently signs everyone out. See
  [`auth/cookies.py`](src/services/auth/auth/cookies.py).

## Working in this repo

Two project skills live in `.claude/skills/` and are used throughout the book:

- **adr-writer** — captures a decision and its rationale as an ADR in `docs/adr/`.
- **stack-update-checker** — compares each entry in `docs/platform/versions.md` against its
  upstream release feed, posts a digest of anything new to Slack, and writes the watermark
  back so the same release is never announced twice.

## License

MIT — see [LICENSE](LICENSE).
