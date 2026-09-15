# Build, deploy and test scripts — design

Approved 2026-09-14. The implementation plan is
[02-build-deploy-test-scripts-implementation-plan.md](02-build-deploy-test-scripts-implementation-plan.md).

## Problem

There are no scripts. Every command a developer runs lives in the README, written
out by hand, and a CI pipeline would have to copy them a second time. Build is
split two ways: Compose builds images under its own project names
(`collabhub-auth`, `collabhub-test-auth`) while the Helm chart expects
`collabhub/<component>:<appVersion>`, and nothing connects the two. There is no
Kubernetes environment the chart has ever been installed into.

## Decisions taken

| Question | Answer |
|---|---|
| What does "deploy" target? | Helm to a **local k3d cluster** |
| What form do the scripts take? | **Bash in `scripts/`** — the same files CI calls |
| What does `test.sh` cover? | lint, unit, integration. **No bdd** — it stays a manual README step |
| Where do the data stores come from in k3d? | A **local-only chart**, `charts/collabhub-local`, using the same pinned images as Compose |

Rejected: Make or a Python CLI for the scripts; upstream community charts
(Bitnami, ECK, dex/dex) for the dependencies, because they bring their own
images and versions that drift from `docs/platform/versions.md`; pointing k3d
workloads at the Compose data stores, which is not a self-contained cluster.

## 1. Script interface

```
scripts/
  lib/common.sh   repo root, log/die, require_cmd, component list, image naming + tag
  build.sh        [component...] [--push]
  deploy.sh       [up|cluster|infra|app|status|down]      default: up
  test.sh         [lint|unit|integration|all] [-- pytest args]   default: all
```

All three are `set -euo pipefail`, runnable from any directory, fail on the first
error, and check their required tools up front. CI calls exactly what a developer
calls.

**`build.sh`** builds `docker/<component>/Dockerfile` with the repo root as
context, for all six components or the ones named. Images are tagged
`${IMAGE_REGISTRY}/collabhub/<component>:${IMAGE_TAG}`.

- `IMAGE_REGISTRY` defaults to the k3d registry, `localhost:5500`; CI overrides it.
- `IMAGE_TAG` defaults to the short git SHA, suffixed `-dirty` when the worktree
  has uncommitted changes. Never `latest`. The tag is computed in `common.sh`, so
  `build.sh` and `deploy.sh` always agree.
- Pushes only with `--push`.
- The frontend's `VITE_*` build args come from the environment and default to the
  k3d origin, `http://localhost:8080`. The frontend image is therefore
  environment-specific, as `charts/collabhub/values.yaml` already records.

**`test.sh`** runs layers in order:

- `lint` — `ruff check`, `ruff format --check`, `conventions.py` over every tracked
  `.py`, `npm run lint`, `npm run typecheck`, `helm lint` on both charts.
- `unit` — `pytest -m "not integration and not bdd"`.
- `integration` — `pytest -m integration`, after checking Docker is reachable.

Arguments after `--` go to pytest (`--junitxml` in CI). It runs
`uv sync --locked` first, and `npm ci` when `node_modules` is missing or `CI` is
set. It adds no tests.

**`deploy.sh`** is idempotent — re-running upgrades in place.

- `cluster` — creates the `collabhub-registry` registry (port 5500) and the
  `collabhub` k3d cluster, from `scripts/k3d/cluster.yaml`. No-op if they exist.
- `infra` — `helm upgrade --install` of `charts/collabhub-local` into namespace
  `collabhub`, `--wait`.
- `app` — `helm upgrade --install` of `charts/collabhub` with
  `values-k3d.yaml`, the image registry and tag, `--wait`. It first checks the
  registry holds every image for the tag, so a missing image fails in seconds
  rather than at the Helm timeout. Afterwards it checks readiness through the
  Ingress (`/` and `/.well-known/jwks.json`). On a `-dirty` tag it restarts the
  rollouts, because the same tag may carry new content.
- `status` — Helm releases and pods. `down` — deletes cluster and registry.

Every `helm` and `kubectl` call passes `--kube-context k3d-collabhub` explicitly
and never uses the current context — a developer's default context may be a real
cluster. CI can override it with `KUBE_CONTEXT`.

Developer loop: `scripts/test.sh && scripts/build.sh --push && scripts/deploy.sh`.

## 2. The k3d environment and `charts/collabhub-local`

**Cluster.** `scripts/k3d/cluster.yaml` is a k3d config file: k3s pinned to
`rancher/k3s:v1.36.4-k3s1` (the `versions.md` Kubernetes track), load balancer
`8080→80`, the `collabhub-registry` registry, and a registry mirror so
`localhost:5500/collabhub/auth:<tag>` resolves both where it is pushed from the
host and where nodes pull it. Without the mirror the two need different
hostnames and `IMAGE_REGISTRY` would depend on who is using it.

**One origin, `http://localhost:8080`.** An Ingress in the local chart, on k3s's
built-in Traefik:

| Path prefix | Backend |
|---|---|
| `/api/v1/auth`, `/api/v1/users`, `/api/v1/workspaces`, `/.well-known` | `collabhub-auth` |
| `/api/v1/channels`, `/api/v1/messages`, `/socket.io` | `collabhub-messaging` |
| `/dex` | `dex` |
| `/` | `collabhub-frontend` |

Nothing routes `/api/v1/internal` or `/health`; they fall through to the SPA's
`index.html` and never reach a service. Canvas and Asset have no APIs yet and get
routes when they do. Same origin satisfies D22 — `CORS_ALLOWED_ORIGINS` stays
empty and the `Secure` cookie works on `http://localhost`. The Ingress lives in
the local chart because the app chart deliberately has none: this is exactly the
per-environment routing it leaves out.

**Dependencies** — plain manifests, the same pinned images as `docker-compose.yml`:

- **Postgres 18** StatefulSet on k3s `local-path` storage. Init SQL is
  `docker/postgres/init.sql`, passed with `--set-file`, not copied.
- **Redis 8 ×3** named `redis-cache`, `redis-rt`, `redis-streams` — the Compose
  names, so the DSNs match `.env.example`. Only streams gets a volume.
- **Elasticsearch 9.4.3** single-node, security off, 512m heap.
- **Garage v2.3.0** StatefulSet, `garage.toml` via `--set-file`, plus an
  idempotent post-install/upgrade **bootstrap Job** doing the README's manual
  steps: layout assign and apply, bucket create, key import, bucket allow. The key
  is a fixed dev key, because Garage requires `GK…` key IDs.
- **OTel collector** with `docker/otel-collector/config.yaml` via `--set-file`.
- **Dex v2.45.1**, issuer `http://localhost:8080/dex`; Auth reaches it in-cluster
  at `http://dex:5556/dex`. Its config is necessarily a *template* in the chart —
  issuer and redirect URI differ and Dex cannot read them from env — so it is a
  third copy beside `config.yaml` and `config.test.yaml`, marked as such.

**Secrets.** The local chart creates `collabhub-auth`, `-messaging`, `-canvas`,
`-asset` and `-worker` — the names the app chart's `envFromSecrets` expects —
holding in-cluster DSNs, `OIDC_PROVIDERS`, `AUTH_SERVICE_CLIENTS`, the Dex
password hash and the object-store key. Auth's signing key is generated in-chart
with `genPrivateKey` and kept across upgrades with `lookup`, so there is no script
state and both Auth replicas sign with the same key. These dev values duplicate
`.env.example` on purpose: `.env` carries Compose hostnames and `$$` escaping and
cannot feed Kubernetes directly.

**Lifecycle.** `infra` before `app`, so Secrets exist before the app chart's
migration Jobs run. Volumes live inside the cluster, so `deploy.sh down` deletes
all data — intended for a local environment. Running the Compose dev stack and
k3d at once is two of everything, Elasticsearch included.

## 3. App chart changes, docs and decisions

**`charts/collabhub`** — k3d is the first real install of this chart.

- Top-level `image.registry` and `image.tag`. A `collabhub.image` helper builds
  `[registry/]repository:tag`, where the tag is the component's own, else
  `image.tag`, else `appVersion`. All six Deployments use it.
- `templates/auth/migrate-job.yaml` and `templates/messaging/migrate-job.yaml`:
  Helm `pre-install,pre-upgrade` hooks (`before-hook-creation,hook-succeeded`),
  the component's image, `python -m <service>.migrate`. Env is inline from the
  component's values plus `envFrom` its Secret, because the ConfigMap does not
  exist yet during a pre-install hook. `values.yaml` gains
  `RUN_MIGRATIONS: "false"` for Auth and Messaging, as the entrypoint comments
  prescribe for Kubernetes.
- `values-k3d.yaml`: `APP_ENV=local`, debug logging, `AUTH_ISSUER` and
  `SPA_REDIRECT_URI` on `http://localhost:8080`, in-cluster JWKS and OTel URLs,
  `imagePullPolicy: Always`. Auth and Messaging stay at 2 replicas, so the shared
  signing key and session affinity are exercised; the rest drop to 1.
- Gaps the install turns up are fixed in the chart, never worked around in the
  scripts.

**Docs.** README gains "Build, test and deploy" (loop, k3d prerequisites, sign-in
at `http://localhost:8080`, the memory note) replacing the `helm lint` lines under
Deploying; the Garage manual steps stay for Compose. CLAUDE.md's layout gains
`scripts/` and `charts/collabhub-local/` (dev-only, never installed elsewhere) and
Testing points at `scripts/test.sh`. `.env.example` gains `IMAGE_REGISTRY`,
`IMAGE_TAG`, `KUBE_CONTEXT`. `versions.md`'s Kubernetes entry notes that
`scripts/k3d/cluster.yaml` pins k3s to its track.

**Decisions.** Two ADRs via `adr-writer`: (1) the scripts are the single
build/test/deploy entry point shared by developers and CI; (2) local Kubernetes
on k3d with a dev-only dependency chart and a single-origin Ingress.

**Out of scope.** The CI workflow file, bdd, pushing to a real registry,
production Secrets, and the future `/socket.io` clash when Canvas gets real-time.

## Verification

No tests are written (CLAUDE.md). Verification is running the scripts end to end:
`test.sh`, `build.sh --push`, `deploy.sh`, sign in as `ada@collabhub.dev` through
`http://localhost:8080`, `deploy.sh` again to prove idempotency, `deploy.sh down`.

## Found during verification (2026-09-14)

The first real install surfaced problems the design did not anticipate. Each was
fixed where it belonged rather than worked around.

- **The frontend image could not run as the chart runs it.** The chart sets UID 101,
  but stock `nginx:1.30-alpine` expects a root master process and died on
  `mkdir /var/cache/nginx/client_temp`. `docker/frontend/Dockerfile` now hands the
  cache and `/run/nginx.pid` to `nginx` and runs as `USER 101` — in Compose too.
- **No `.dockerignore` existed.** Every build sent the whole checkout, and the
  frontend's `COPY src/frontend/` would lay macOS `node_modules` over the Linux
  install. Added at the root.
- **`uv sync --locked` drops member dev groups.** Messaging's dev group carries the
  Socket.IO async client and `aiohttp`; without it 26 real-time integration tests
  fail to connect. `test.sh` syncs with `--all-packages`. The README's old bare
  `uv sync` had the same gap, which a hand-installed venv had been hiding.
- **k3d names a config-created registry without the `k3d-` prefix**, so the mirror
  endpoint is `http://collabhub-registry:5000`.
- **`docker manifest inspect` reports "no such manifest"** against a plain-HTTP
  registry unless given `--insecure`. `deploy.sh` checks images with
  `docker buildx imagetools inspect`, which needs no special case.
- **`src/services/auth/scripts/sign-in.py` does not work on a single origin.** It
  stops following redirects when they leave the IdP's host, which cannot separate
  Dex from Auth when both are `localhost:8080`. Left unchanged; a copy that stops
  at Auth's callback path signed in successfully.

Results: `test.sh` lint passed, unit 102 passed, integration 287 passed.
`deploy.sh` installed both releases; both migration Jobs and the Garage bootstrap
succeeded; a CLI sign-in through Dex returned a token that Auth and Messaging both
accepted through the Ingress; a second `deploy.sh` upgraded cleanly and kept Auth's
signing key; `deploy.sh down` removed the cluster and its registry.

## Merged with main (2026-09-15)

PR #2 (KEDA worker pools, WebSocket-only Socket.IO, NetworkPolicy) and PR #3 (message
search) merged to `main` first. Only `README.md` and `charts/collabhub/values.yaml`
conflicted, and both kept both sides — but PR #2 changed what the app chart demands of
every environment, so a clean textual merge still left `deploy.sh` unable to install it.

- **KEDA is required.** The chart refuses to render without `keda.sh/v1alpha1`. Decision:
  install it rather than turn autoscaling off locally, so the ScaledObjects are exercised.
  `deploy.sh infra` installs the `kedacore/keda` chart pinned by `KEDA_VERSION` in
  `scripts/lib/common.sh`, matching the KEDA entry in `versions.md`.
- **NetworkPolicy peers are required, and k3s enforces them.** `values-k3d.yaml` sets every
  peer: Traefik in `kube-system` as the ingress controller, the local chart's pods by name
  label for the rest, and Dex on 5556 for `oidcProvider`.
- **New settings.** Messaging now needs `ELASTICSEARCH_URL`, and KEDA's
  TriggerAuthentication needs a `REDIS_STREAMS_PASSWORD` key in the Worker secret; the local
  chart supplies both.
- **A new public route.** Search is `/api/v1/search`, which the Ingress allow-list did not
  include.
- **`test.sh` lint** now lints the defaults with NetworkPolicy and autoscaling off, lints the
  k3d values with autoscaling off, and renders the k3d values with the KEDA API declared.
- **A bug in PR #2's default, found by the deploy.** `REDIS_STREAMS_ADDRESS` is resolved by
  KEDA's operator from its own namespace, so the bare `redis-streams:6379` failed with `no such
  host`. `values-k3d.yaml` uses the fully qualified Service name, and the `values.yaml` comment
  now says every environment must. After a fix like this on a live cluster, KEDA does not
  re-check an unchanged ScaledObject until its backoff expires; restarting the operator made it
  reconcile at once.
- The Traefik/session-affinity caveat is gone: Socket.IO is WebSocket-only (register D30).

Results on the merged branch: lint passed, unit 102 and integration 287 passed. `deploy.sh`
installed KEDA and upgraded both releases. All pods Ready under enforced policies — and the
frontend pod, whose policy allows no egress, could not even resolve a Service name. Sign-in
through Dex worked. A message posted through the Ingress was indexed and found by
`GET /api/v1/search/messages`; with the batch pool scaled to zero, a second message woke it
through KEDA, was indexed, and was found the same way. Auth's signing key survived both
upgrades.
