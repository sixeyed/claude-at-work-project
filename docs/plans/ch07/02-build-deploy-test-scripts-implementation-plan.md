# Build, deploy and test scripts — implementation plan

> Executed inline in the session that wrote it, on branch
> `feature/build-deploy-test-scripts`. Steps use checkboxes for tracking.

**Goal:** `scripts/build.sh`, `scripts/test.sh` and `scripts/deploy.sh` — one
entry point each for building images, running the checks and deploying to a
local k3d cluster, called identically by developers and CI.

**Architecture:** Bash scripts share `scripts/lib/common.sh` for naming, tagging
and context. Deploy installs two Helm releases into k3d: `collabhub-local`
(dev-only data stores, Dex, Secrets, Ingress) and `collabhub` (the app chart,
extended with an image helper and migration Jobs).

**Tech stack:** bash 3.2-compatible, Docker/BuildKit, k3d 5.8 on k3s
`v1.36.4-k3s1`, Helm 3.19, kubectl, uv, npm.

**Spec:** [01-build-deploy-test-scripts-design.md](01-build-deploy-test-scripts-design.md)

## Global constraints

- **No tests are written** (CLAUDE.md, until further notice). Every task verifies
  by running a script and checking its output.
- **Nothing is committed.** The worktree is left dirty for the user.
- Images are `${IMAGE_REGISTRY}/collabhub/<component>:${IMAGE_TAG}`; registry
  default `localhost:5500`; tag default short SHA plus `-dirty`; never `latest`.
- Every `helm`/`kubectl` call names `--kube-context` (default `k3d-collabhub`).
  `cluster`, `infra` and `down` refuse any other context. The k3d config never
  switches the current context.
- Platform images are the ones pinned in `docs/platform/versions.md`.
- Release names `collabhub` and `collabhub-local`, namespace `collabhub`, one
  public origin `http://localhost:8080`.
- Any gap the first install finds in `charts/collabhub` is fixed in the chart,
  never worked around in a script.

---

### Task 1: Shared library and `build.sh`

**Files:** create `scripts/lib/common.sh`, `scripts/build.sh`, `.dockerignore`.

**Produces:** `REPO_ROOT`, `COMPONENTS`, `K3D_CLUSTER`, `K3D_ORIGIN`,
`NAMESPACE`, `IMAGE_REGISTRY`, `IMAGE_TAG`, `KUBE_CONTEXT`, `LOCAL_CHART_FILES`
(the `--set-file` args), `log`, `die`, `usage`, `require_cmd`, `is_component`,
`image_ref <component>`.

- [ ] Write `common.sh`. `IMAGE_TAG` is computed once at source time.
- [ ] Write `build.sh [component...] [--push]`. Frontend gets `VITE_*` build args
      defaulting to `K3D_ORIGIN`; every image gets an OCI revision label.
- [ ] Add a root `.dockerignore`. Without it `COPY src/frontend/` lays the host's
      macOS `node_modules` over the Linux install.
- [ ] Verify: `scripts/build.sh --help` prints usage; `scripts/build.sh nope`
      fails naming the valid components; `scripts/build.sh` builds all six tagged
      `localhost:5500/collabhub/<c>:<sha>-dirty`.

### Task 2: `test.sh`

**Files:** create `scripts/test.sh`.

- [ ] Layers `lint` (ruff check, ruff format --check, `conventions.py` over
      `git ls-files '*.py'`, `npm run lint`, `npm run typecheck`, `helm lint` on
      the app chart with and without `values-k3d.yaml` and on the local chart
      with `LOCAL_CHART_FILES`), `unit` (`-m "not integration and not bdd"`),
      `integration` (`-m "integration and not bdd"`, Docker checked first).
- [ ] `uv sync --locked` first; `npm ci` when `CI` is set or `node_modules` is
      missing; everything after `--` passed to pytest.
- [ ] Verify: `scripts/test.sh lint`, `scripts/test.sh unit` (102 passed at
      baseline), `scripts/test.sh integration`.

### Task 3: k3d cluster and `deploy.sh`

**Files:** create `scripts/k3d/cluster.yaml`, `scripts/deploy.sh`.

- [ ] `cluster.yaml`: k3s `v1.36.4-k3s1`, `127.0.0.1:8080:80` on the load
      balancer, registry `collabhub-registry` on `127.0.0.1:5500` created with
      the cluster, mirror `localhost:5500` → `http://k3d-collabhub-registry:5000`,
      `switchCurrentContext: false`.
- [ ] `deploy.sh up|cluster|infra|app|status|down`, as in the spec. `app` checks
      every image with `docker manifest inspect` before installing, restarts
      rollouts on an upgrade to a `-dirty` tag, then curls `/` and
      `/.well-known/jwks.json` through the Ingress.
- [ ] Verify: `scripts/deploy.sh cluster` creates the cluster;
      `kubectl config current-context` is unchanged; `docker ps` shows the
      registry; a second `cluster` is a no-op; `KUBE_CONTEXT=x scripts/deploy.sh infra`
      refuses.

### Task 4: `charts/collabhub-local`

**Files:** create `Chart.yaml`, `values.yaml`, `files/garage-bootstrap.py`,
`templates/{_helpers.tpl,postgres,redis,elasticsearch,garage,dex,otel-collector,app-secrets,ingress}.yaml`.

**Produces:** Services `postgres`, `redis-cache`, `redis-rt`, `redis-streams`,
`elasticsearch`, `garage`, `dex`, `otel-collector`; Secrets
`collabhub-{auth,messaging,canvas,asset,worker}` holding the keys each app
component's settings require; Ingress `collabhub`.

- [ ] Postgres StatefulSet with `init.sql` via `--set-file`; three Redis
      Deployments (streams with a PVC); single-node Elasticsearch; OTel collector
      with the Compose config via `--set-file`.
- [ ] Garage StatefulSet with `garage.toml` via `--set-file`, plus a
      post-install/upgrade Job running `garage-bootstrap.py` against the admin API
      v2 (`GetClusterStatus` → `GetClusterLayout` → `UpdateClusterLayout` +
      `ApplyClusterLayout` → `GetBucketInfo`/`CreateBucket` →
      `GetKeyInfo`/`ImportKey` → `AllowBucketKey`), retrying while the layout
      settles. Verified first against a throwaway `dxflrs/garage:v2.3.0`.
- [ ] Dex with its config templated from `origin` (the third copy, marked).
- [ ] Secrets with in-cluster DSNs; Auth's signing key from `genPrivateKey`,
      preserved across upgrades with `lookup`.
- [ ] Ingress on Traefik: Auth and Messaging public prefixes, `/dex`, `/` → SPA.
- [ ] Verify: `helm lint` passes; `scripts/deploy.sh infra` completes, the
      bootstrap Job succeeds, every pod is Ready; a second `infra` keeps the same
      `AUTH_SIGNING_KEY`.

### Task 5: `charts/collabhub` changes

**Files:** modify `templates/_helpers.tpl`, all six `templates/*/deployment.yaml`,
`values.yaml`; create `templates/{auth,messaging}/migrate-job.yaml`,
`values-k3d.yaml`.

- [ ] `collabhub.image` helper; top-level `image.registry` and `image.tag`.
- [ ] Migration Jobs as `pre-install,pre-upgrade` hooks with a distinct component
      label, env inline, `envFrom` the Secret. `RUN_MIGRATIONS: "false"` for Auth
      and Messaging in `values.yaml`.
- [ ] `values-k3d.yaml` as in the spec.
- [ ] Verify: `helm template` renders `localhost:5500/collabhub/auth:<tag>`
      images; `scripts/build.sh --push && scripts/deploy.sh app` installs, both
      migration Jobs succeed, every Deployment is Ready, the readiness curls pass.

### Task 6: End to end

- [ ] `scripts/test.sh`, `scripts/build.sh --push`, `scripts/deploy.sh`.
- [ ] Sign in as `ada@collabhub.dev` / `collabhub` at `http://localhost:8080`,
      reach the chat shell.
- [ ] `scripts/deploy.sh` again — completes without error.
- [ ] `scripts/deploy.sh down` removes the cluster and the registry.

### Task 7: Docs and decisions

**Files:** modify `README.md`, `CLAUDE.md`, `.env.example`,
`docs/platform/versions.md`; create two ADRs in `docs/adr/`.

- [ ] README "Build, test and deploy" section; Deploying section points at it.
- [ ] CLAUDE.md layout and Testing section.
- [ ] `.env.example`: `IMAGE_REGISTRY`, `IMAGE_TAG`, `KUBE_CONTEXT`.
- [ ] `versions.md` Kubernetes note about `scripts/k3d/cluster.yaml`.
- [ ] ADRs with `adr-writer`: scripts as the shared entry point; local k3d with a
      dev-only dependency chart.
