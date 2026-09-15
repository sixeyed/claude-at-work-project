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
charts/collabhub-local/  DEV ONLY: data stores, Dex, Secrets and Ingress for the local k3d cluster
scripts/          build.sh, test.sh, deploy.sh — the same entry points CI uses
.claude/skills/   Project skills: adr-writer, stack-update-checker
```

## Running it locally

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 24, Docker. Deploying to Kubernetes
also needs [k3d](https://k3d.io), Helm and kubectl.

```bash
cp .env.example .env   # nothing in it is a real secret
scripts/test.sh        # lint, unit, then integration (integration needs Docker)
```

`scripts/test.sh` is the one entry point for checks, and CI runs it too. Name layers to run
fewer — `lint` is ruff, the CollabHub convention checks, eslint, tsc and `helm lint`; `unit`
needs no Docker; `integration` starts real Postgres, Redis and Dex containers (Conventions
§11). Anything after `--` goes to pytest:

```bash
scripts/test.sh unit                 # fast, no Docker
scripts/test.sh lint unit -- -x      # stop at the first failure
scripts/test.sh e2e                  # the browser journeys, on a stack it starts and stops
scripts/test.sh all                  # every layer, e2e included — what CI runs
```

The no-argument run is `lint unit integration`. The `e2e` layer is slower — it builds and
starts a whole Compose stack — so it runs when named, or as part of `all` (see
[Acceptance tests](#acceptance-tests)).

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
leave that up and keep working.

`scripts/test.sh e2e` does the whole round trip: it brings the test stack up and
waits until it is healthy, installs Chromium for Playwright if it is missing, runs
the suite, and takes the stack down again whether the scenarios passed or not. It
exits with pytest's status. It needs Docker and a `.env` (`cp .env.example .env`).

```bash
scripts/test.sh e2e                           # up, run, down
scripts/test.sh e2e -- --headed -k channels   # watch it drive the browser
KEEP_STACK=1 scripts/test.sh e2e              # leave the stack up afterwards
```

`KEEP_STACK=1` is for iterating on steps: with the stack left up, rerun just the
suite with `uv run pytest tests/bdd -m bdd`, which skips the build. What the script
does, by hand:

```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build --wait \
    --scale elasticsearch=0 --scale worker=0
uv run playwright install chromium
uv run pytest tests/bdd -m bdd
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
over the Compose network by name. Both stacks running would mean two of
everything, Elasticsearch included, so the script runs the test stack with
`--scale elasticsearch=0 --scale worker=0` — no scenario touches either yet. The
first search journey removes that.

`--wait` only means something for containers with a healthcheck, which is why the
frontend has one: it probes `/`, the same path the Helm chart's probes use.

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
Nothing reads them yet — the Asset service has no object-storage code. The k3d deployment
below does all of this for you.

### Deploying to Kubernetes

`scripts/build.sh` and `scripts/deploy.sh` build the images and install the Helm chart into a
local [k3d](https://k3d.io) cluster — the same scripts CI will run:

```bash
scripts/test.sh && scripts/build.sh --push && scripts/deploy.sh
```

Then open <http://localhost:8080> and sign in as `ada@collabhub.dev` / `collabhub`, as above.
Everything is on that one origin: the SPA, every public API and Dex, behind the Traefik
Ingress k3s ships with.

| | |
|---|---|
| `scripts/build.sh [component...] [--push]` | Builds `localhost:5500/collabhub/<component>:<tag>`. The tag is the short commit SHA, plus `-dirty` for uncommitted changes |
| `scripts/deploy.sh cluster` | Creates the `collabhub` k3d cluster (k3s pinned to `versions.md`) and its registry on `localhost:5500` |
| `scripts/deploy.sh infra` | Installs KEDA (pinned to `versions.md`), then `charts/collabhub-local`: Postgres, three Redis, Elasticsearch, Garage (bootstrapped), Dex, the OTel collector, the Secrets and the Ingress |
| `scripts/deploy.sh app` | Installs `charts/collabhub` at the current tag. Migrations run as Helm hook Jobs before any pod rolls |
| `scripts/deploy.sh` | All three, in order. Idempotent — re-run it to upgrade |
| `scripts/deploy.sh status` / `down` | What is running / delete the cluster, its registry and **all its data** |

The scripts never use your current kubectl context. Every call names `k3d-collabhub`, creating
the cluster does not switch to it, and `cluster`, `infra` and `down` refuse to run against
anything else. `IMAGE_REGISTRY`, `IMAGE_TAG` and `KUBE_CONTEXT` override the defaults — see
`.env.example`.

k3d and the Compose development stack can run at the same time, but that is two of
everything, Elasticsearch included — give Docker the memory for it.

`charts/collabhub-local` is **development only**: its credentials are throwaway, its Dex is full
of demo accounts, and nothing in it is backed up. Never install it anywhere else.

### What the chart expects of an environment

Three things the chart now needs, all per environment:

- **KEDA**, installed in the cluster — the chart fails to render without the `keda.sh/v1alpha1`
  API, since the Worker's `ScaledObject`s depend on it. No KEDA and don't want it? Set
  `components.worker.autoscaling.enabled=false` and the Worker renders as plain Deployments
  instead.
- **`networkPolicy.peers` set in a values file for that environment** — `postgres`,
  `redisCache`, `redisRealtime`, `redisStreams`, `elasticsearch`, `objectStore`,
  `otelCollector`, `oidcProvider`. Where Postgres, Redis and the rest actually live varies per
  cluster, so the chart ships no defaults for them, and the render fails, naming whichever
  peer is missing, until every one an enabled component needs is set. Don't want NetworkPolicy
  objects at all? Set `networkPolicy.enabled=false`.
- **A `REDIS_STREAMS_PASSWORD` key in the `collabhub-worker` secret**, and
  `components.worker.env.REDIS_STREAMS_ADDRESS` pointed at R3's `host:port` — KEDA's
  `TriggerAuthentication` and its `redis-streams` trigger read these directly; they are not
  parsed out of `REDIS_STREAMS_URL`.

`ingressController` and `dns` are the exceptions: they ship non-empty defaults (ingress-nginx
in namespace `ingress-nginx`; CoreDNS via `k8s-app: kube-dns` in `kube-system`), so they pass
the empty-peer check even on a cluster where they're wrong. That's silent — nothing fails — so
check them by hand for your cluster. Under a CNI that enforces NetworkPolicy, a wrong
`ingressController` peer blocks all public ingress traffic to every component.

The k3d environment is a worked example of all three: `deploy.sh infra` installs KEDA,
`charts/collabhub/values-k3d.yaml` sets every peer (k3s's Traefik as the ingress controller,
and k3s does enforce NetworkPolicy), and `charts/collabhub-local` supplies the Secret keys.

```bash
helm lint charts/collabhub -f <env-values>.yaml --set components.worker.autoscaling.enabled=false
helm template collabhub charts/collabhub -f <env-values>.yaml --api-versions keda.sh/v1alpha1
```

`helm lint` has no `--api-versions` flag, so it can't see the KEDA API either way — the
`--set` above sidesteps that check the same way a KEDA-less cluster would. `helm template`
does take `--api-versions`, so pass it there instead once your peers are set.

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
