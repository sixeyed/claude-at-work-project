# CollabHub — sample project for *Claude at Work*

This repo is the running sample project for **Claude at Work** (Manning), by Elton Stoneman.
It's a deliberately realistic codebase: a greenfield product with real design documents,
real architectural decisions, and real recurring maintenance work — the kind of project you'd
actually point Claude Code at.

> [Claude at Work - repo](https://github.com/sixeyed/claude-at-work)

**CollabHub** is the product being built: a team collaboration platform that pairs a
Slack-like chat experience with a Figma-like collaborative canvas in a single app.

## Current state

Design-stage. The design docs and decision records are written; the services aren't built yet.
Chapters of the book add code, configuration and automation to this repo as they go.

## What's here

```
docs/design/      Architecture and per-service design docs (start with 00-platform-conventions.md)
docs/adr/         Architecture Decision Records — one file per significant decision
docs/platform/    versions.md — tracked upstream versions for every platform component
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

## Working in this repo

Two project skills live in `.claude/skills/` and are used throughout the book:

- **adr-writer** — captures a decision and its rationale as an ADR in `docs/adr/`.
- **stack-update-checker** — compares each entry in `docs/platform/versions.md` against its
  upstream release feed, posts a digest of anything new to Slack, and writes the watermark
  back so the same release is never announced twice.

## License

MIT — see [LICENSE](LICENSE).
