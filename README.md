# CollabHub — sample project for *Claude at Work*

This repo is the running sample project for **Claude at Work** (Manning), by Elton Stoneman.

It's a deliberately realistic codebase: a greenfield product with real design documents,
real architectural decisions, and real recurring maintenance work — the kind of project you'd
get Claude Code to build.

> [Claude at Work - repo](https://github.com/sixeyed/claude-at-work)

**CollabHub** is the product being built: a team collaboration platform that pairs a
Slack-like chat experience with a Figma-like collaborative canvas in a single app.

## Current state

Scaffold-stage. Every component exists, builds and starts; none of them do anything yet.
Chapters of the book add code, configuration and automation to this repo as they go.

What a service currently is: a process that reads its configuration and answers
`/health/live` and `/health/ready`. There are no database models, no migrations, no API
routes, no Socket.IO namespaces, and no job handlers. `collabhub-shared` holds only the
health router — the Problem Details handlers, `require_user` / `require_service`, JWKS
caching, cursor pagination, the job envelope and the `ObjectStore` protocol are all still
to come. `collabhub-contracts` is empty.

Nothing in the scaffold resolves an open decision that was still 🔴 in the
[register](docs/design/07-open-decisions-register.md).

## What's here

```
docs/design/      Architecture and per-service design docs (start with 00-platform-conventions.md)
docs/adr/         Architecture Decision Records — one file per significant decision
docs/platform/    versions.md — tracked upstream versions for every platform component
src/services/     shared, contracts, and the five backend services (one uv workspace)
src/frontend/     React + TypeScript SPA (Vite)
docker/           One folder per component: its Dockerfile and any files it needs
charts/collabhub/ Helm chart covering every component
.claude/skills/   Project skills: adr-writer, stack-update-checker
```

Read [`docs/design/00-platform-conventions.md`](docs/design/00-platform-conventions.md) first —
it's the shared baseline every service doc builds on. The
[open decisions register](docs/design/07-open-decisions-register.md) lists what's still undecided.

## Planned architecture

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
storage (Garage) · Kubernetes · OpenTelemetry into the Grafana LGTM stack.

Python was chosen over .NET — see
[ADR 260708](docs/adr/260708-python-instead-of-dotnet.md) for the reasoning.

## Running it locally

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 24, Docker.

```bash
cp .env.example .env      # nothing in it is a real secret
uv sync --all-packages    # one workspace, one lockfile
uv run pytest             # unit tests
uv run ruff check . && uv run ruff format --check .
```

Bring up the full stack — Postgres, the three Redis instances, Garage, Elasticsearch, the
OTel collector, all five services and the SPA:

```bash
docker compose up --build
```

Then `curl localhost:8001/health/ready` (Auth), `:8002` Messaging, `:8003` Canvas,
`:8004` Asset, `:8005` Worker, and the SPA on <http://localhost:5173>.

For frontend work, the Vite dev server is faster than rebuilding the Nginx image:

```bash
cd src/frontend && npm install && npm run dev
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

## Working in this repo

Two project skills live in `.claude/skills/` and are used throughout the book:

- **adr-writer** — captures a decision and its rationale as an ADR in `docs/adr/`.
- **stack-update-checker** — compares each entry in `docs/platform/versions.md` against its
  upstream release feed, posts a digest of anything new to Slack, and writes the watermark
  back so the same release is never announced twice.

## License

MIT — see [LICENSE](LICENSE).
