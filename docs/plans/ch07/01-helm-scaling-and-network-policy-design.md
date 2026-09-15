# Helm chart: Worker autoscaling, WebSocket-only real-time, NetworkPolicy

## Context

`charts/collabhub` deploys all six components and renders cleanly, but three things its own
comments promise are missing: a KEDA `ScaledObject` for the Worker, session affinity for the
real-time services, and any NetworkPolicy at all.

Looking into them changed two of the three:

- **The affinity that exists is ineffective.** Messaging and Canvas Services set
  `sessionAffinity: ClientIP`, but ingress-nginx routes to pod endpoints directly and never
  consults it. Were it consulted, the client IP would be the controller's, pinning every user
  to one pod. Working affinity would need a cookie at the ingress, and the chart has no
  Ingress by design.
- **Doc 05 §5.3's scaler cannot scale from zero.** `pendingEntriesCount` counts entries a
  consumer has already read and not acked. With no pods nothing is read, the count stays 0,
  and the Worker never starts. KEDA's docs name `lagCount` as the only Redis Streams metric
  that supports scale-to-zero; it needs Redis 7+ (pinned track is 8).
- **Doc 05 §5.3 also asks for two things one Deployment cannot do** — scale to zero, and keep
  a floor for `jobs:notify` (< 5 s p95).

Target cluster for verification is `sixeyed`: Kubernetes 1.34.3, KEDA 2.20.1, ingress-nginx
in namespace `ingress`. No policy-enforcing CNI is installed there, so NetworkPolicy objects
apply but block nothing.

### Decisions settled in this phase

Each needs an ADR (`adr-writer` skill) and a register update, made in this slice.

| ID | Was | Now |
|---|---|---|
| **D17** | 🟡 one deployment, CPU/IO split suggested | **Two Worker pools split on latency:** `notify` (floor 1) and `batch` (scales from 0) |
| **D30** | new | **Socket.IO is WebSocket-only.** No long-polling fallback, so no session affinity anywhere |

NetworkPolicy strictness (deny all, allow listed, ingress *and* egress) is a chart design
choice rather than a register entry.

## Reference points

- `docs/design/00-platform-conventions.md` §5.5 internal calls, §6 real-time, §9 observability
- `docs/design/02-messaging-service.md` §3.2 Socket.IO namespace
- `docs/design/03-canvas-service.md` — depends on Postgres, R1, R2; no R3
- `docs/design/04-asset-service.md` — Postgres, Garage, R3; R1 for the fail-closed delete
- `docs/design/05-worker-service.md` §5.1 consumer group `worker`, §5.3 scaling
- `src/services/worker/worker/settings.py` — `WORKER_STREAMS` already selects streams per deployment
- `src/services/messaging/messaging/realtime.py` — `build_server`
- `src/frontend/src/lib/realtime/socket.ts` — `transports: ['websocket', 'polling']` today
- KEDA 2.20 Redis Streams scaler and ScaledObject spec

## 1. Worker — two pools, KEDA-scaled

### Values

`components.worker` keeps image, env, secrets and security context, and gains:

```yaml
autoscaling:
  enabled: true          # false renders plain Deployments with replicaCount
  pollingInterval: 30
  cooldownPeriod: 300
  consumerGroup: worker  # doc 05 §5.1
  lagCount: "5"
pools:
  notify:
    streams: [jobs:notify]
    minReplicas: 1
    maxReplicas: 5
  batch:
    streams: [jobs:index, jobs:thumbnail, jobs:export, jobs:retention]
    minReplicas: 0
    maxReplicas: 10
```

Each pool's `WORKER_STREAMS` is derived from its `streams` list and set on that pool's
container, overriding the shared ConfigMap value. `replicaCount` remains the count used
when autoscaling is disabled.

### Templates — `templates/worker/`

| File | Renders |
|---|---|
| `configmap.yaml` | One shared ConfigMap, as today, plus `REDIS_STREAMS_ADDRESS` |
| `deployment.yaml` | One Deployment per pool: `<fullname>-worker-<pool>` |
| `scaledobject.yaml` | One ScaledObject per pool, when `autoscaling.enabled` |
| `triggerauthentication.yaml` | One TriggerAuthentication, when `autoscaling.enabled` |

- **Selector labels gain `collabhub.io/pool: <pool>`.** Both pools share
  `app.kubernetes.io/component: worker`; without the pool label each Deployment would select
  the other's pods. The `collabhub.selectorLabels` helper takes an optional `pool` key.
- **Deployments omit `spec.replicas` when autoscaling is enabled**, so `helm upgrade` does not
  reset what the HPA set.
- **One trigger per stream**, all `type: redis-streams` with `consumerGroup`, `lagCount` and
  `activationLagCount: "0"`. The HPA scales to whichever trigger asks for the most.
- **Address from env, password from the secret.** KEDA takes `host:port`, not a `redis://`
  URL, so `addressFromEnv: REDIS_STREAMS_ADDRESS` reads the ConfigMap value, and the
  TriggerAuthentication maps `password` to key `REDIS_STREAMS_PASSWORD` of the
  `collabhub-worker` secret. Both variables are chart-only; the Worker process keeps using
  `REDIS_STREAMS_URL`. Both go into `.env.example`, marked as such.
- **`fallback: {failureThreshold: 3, replicas: 1}`.** See the known gap below.
- **Fail fast without KEDA.** With autoscaling enabled and `keda.sh/v1alpha1` absent from
  `.Capabilities.APIVersions`, the chart `fail`s with a message saying so. Offline rendering
  passes `--api-versions keda.sh/v1alpha1`.

### Known gap

**Corrected 2026-09-14** — the gap is not what the fallback comment first claimed. Checked
against KEDA v2.20.1's `redis_streams_scaler.go` (the `lagFactor` path, l.236-268): when the
stream does not exist yet, `XInfoGroups` returns `ERR no such key` and the scaler returns lag
`0` with **no error** (l.240-242); when the stream exists but the consumer group does not, it
falls through to `XLen` and returns the stream length as the lag, again with **no error**
(l.254-268). Neither case is a trigger error, so the fallback never engages for either of them.

Today this is silent: no service produces jobs yet, so every stream is missing, and `batch`
correctly sits at its floor of zero. The gap becomes live the moment a producer ships ahead of
the Worker creating its groups — the stream now exists, the group still doesn't, and KEDA reads
`XLEN` as the lag and scales the pool to `ceil(XLEN / lagCount)`, up to its max (10 for `batch`,
5 for `notify`). Nothing drains it, because no consumer is reading, so the pool pins at max
rather than at zero. The fallback (`fallback.replicas: 1`) still earns its place — it covers
Redis being unreachable or the trigger's auth failing — just not this case.

**Sequencing rule:** consumer groups are created before, or in the same slice as, the first
producer for their stream, from ID `0` — `XGROUP CREATE <stream> worker 0 MKSTREAM` — so the
lag KEDA measures matches the entries already sitting in the stream rather than skipping past
them. Creating the groups is Worker code and out of scope here.

**Updated 2026-09-15**, after message search merged (PR #3): the Worker now creates its groups
from ID `0` at startup, which closes this gap for any pool whose pods start, and it exits on a
stream with no handler. Pools therefore list only handled streams: the chart ships `notify` with
`enabled: false` and `batch` on `jobs:index` alone, and fails the render for an enabled pool with
no streams.

### Upgrade note

The single `collabhub-worker` Deployment is replaced by two with different names and
selectors. Helm deletes the old one and creates the new ones; no manual step, but the Worker
is briefly absent during the rollout. Acceptable — producers never block on the Worker.

## 2. Real-time — WebSocket-only

- **SPA** — `socket.ts` uses `transports: ['websocket']`, with a comment pointing at D30.
- **Messaging** — `build_server` passes `transports=['websocket']` to `socketio.AsyncServer`,
  so a polling handshake is refused by the server rather than merely not attempted by this
  client.
- **Canvas** — has no Socket.IO server yet. Conventions §6 carries the rule for when it does.
- **Chart** — `service.sessionAffinity` is removed from every component in `values.yaml`, and
  the `sessionAffinity` block and its comment from the Service templates.

**Trade-off accepted:** a client behind a proxy that blocks WebSockets cannot connect at all.
ingress-nginx proxies WebSockets without annotations, and Socket.IO's 25 s ping keeps the
connection under its 60 s default read timeout.

## 3. NetworkPolicy — deny all, allow listed

One NetworkPolicy per component at `templates/<component>/networkpolicy.yaml`, selecting that
component's pods (both Worker pools share one). Every policy declares
`policyTypes: [Ingress, Egress]`, so anything not listed is denied. All are gated on
`networkPolicy.enabled` (default `true`).

### Allow matrix

Ingress is to the component's app port only.

| Pod | Ingress from | Egress to |
|---|---|---|
| frontend | ingress controller | — |
| auth | ingress controller, messaging, canvas, asset, worker | DNS, Postgres, R1, OIDC provider, OTel |
| messaging | ingress controller, worker | DNS, Postgres, R1, R2, R3, Elasticsearch, auth, OTel |
| canvas | ingress controller, worker | DNS, Postgres, R1, R2, auth, OTel |
| asset | ingress controller, worker | DNS, Postgres, R1, R3, object store, auth, OTel |
| worker | — | DNS, R3, Elasticsearch, object store, auth, messaging, canvas, asset, OTel |

In-release peers are selected by the chart's own labels (`instance` + `component`).

**Updated 2026-09-15:** Messaging gained Elasticsearch egress when message search merged
(PR #3, `GET /search/messages`); until then it was listed as deliberately not covered.

### External peers

```yaml
networkPolicy:
  enabled: true
  peers:
    ingressController:
      from:
        - namespaceSelector:
            matchLabels: {kubernetes.io/metadata.name: ingress-nginx}
          podSelector:
            matchLabels: {app.kubernetes.io/name: ingress-nginx}
    dns:
      to:
        - namespaceSelector:
            matchLabels: {kubernetes.io/metadata.name: kube-system}
          podSelector:
            matchLabels: {k8s-app: kube-dns}
      ports: [{port: 53, protocol: UDP}, {port: 53, protocol: TCP}]
    postgres:      {to: [], ports: [{port: 5432, protocol: TCP}]}
    redisCache:    {to: [], ports: [{port: 6379, protocol: TCP}]}
    redisRealtime: {to: [], ports: [{port: 6379, protocol: TCP}]}
    redisStreams:  {to: [], ports: [{port: 6379, protocol: TCP}]}
    elasticsearch: {to: [], ports: [{port: 9200, protocol: TCP}]}
    objectStore:   {to: [], ports: [{port: 3900, protocol: TCP}]}
    otelCollector: {to: [], ports: [{port: 4317, protocol: TCP}]}
    oidcProvider:  {to: [], ports: [{port: 443, protocol: TCP}]}
```

`to`/`from` are NetworkPolicyPeer lists — selectors or `ipBlock`s — so a store in the cluster
and one outside it are configured the same way.

- **Empty `to` fails the render** for any peer an enabled component needs, naming the peer.
  A chart that renders pods unable to reach their database is worse than one that refuses.
- **`sixeyed` differs from the defaults:** its Helm-installed controller is in namespace
  `ingress` with `app.kubernetes.io/name: ingressnginx`. That belongs in that environment's
  values file, not the chart defaults.

### Deliberately not covered

| Traffic | Why no rule |
|---|---|
| Kubelet probes | Originate on the node, which common CNIs admit regardless |
| KEDA operator → R3 | KEDA's pods, not this release's |
| Browser → Garage presigned uploads | Never passes through a CollabHub pod |
| Worker → notification providers | Channels undecided (D18 🔴) |
| Hiding `/api/v1/internal/` from the ingress controller | L7; NetworkPolicy is L3/L4. Remains an ingress routing rule (Conventions §5.5) |

## 4. Record the decisions

- `docs/design/07-open-decisions-register.md` — D17 → 🟢; add D30 🟢.
- ADRs via `adr-writer`: Worker pools split on latency (D17); WebSocket-only Socket.IO (D30).
- `docs/design/05-worker-service.md` §5.3 — `lagCount`, the two pools; §9 D17 bullet struck through.
- `docs/design/00-platform-conventions.md` §6 — transport bullet becomes WebSocket-only.
- `docs/design/02-messaging-service.md` §3.2 — server refuses polling.
- `docs/platform/versions.md` — add a KEDA entry (orchestration, track 2, 2.20.1 on the target cluster).
- `.env.example` — `REDIS_STREAMS_ADDRESS`, `REDIS_STREAMS_PASSWORD`, marked chart-only.
- `values.yaml` header comment and `worker/deployment.yaml` comment — no longer "when it lands".

## Out of scope

- The hard-coded `http://collabhub-auth:8000` URLs in values, which break for any release not
  named `collabhub`.
- The Worker creating its consumer groups.
- Tests of any kind — none until further notice (CLAUDE.md).

## Verification

No policy-enforcing CNI on `sixeyed`, so this proves the manifests are valid, not that the
rules hold.

`sixeyed-peers.yaml` is a scratch values file, not committed: `networkPolicy.peers` for that
cluster (controller in `ingress` labelled `ingressnginx`, Postgres in `data`, Elasticsearch in
`logging`, placeholder `ipBlock`s for the stores it does not run).

```bash
# Lint. `helm lint` has no --api-versions, and the chart refuses to render without
# KEDA's API or its peers, so lint runs with autoscaling off and the peers file.
helm lint charts/collabhub -f sixeyed-peers.yaml --set components.worker.autoscaling.enabled=false

# Render with KEDA's API declared
helm template t charts/collabhub --api-versions keda.sh/v1alpha1 -f sixeyed-peers.yaml

# Render must fail with a named peer when one is missing
helm template t charts/collabhub --api-versions keda.sh/v1alpha1

# Render must fail without KEDA when autoscaling is enabled
helm template t charts/collabhub -f sixeyed-peers.yaml

# Server-side schema validation, ScaledObject CRD included; creates nothing
helm template t charts/collabhub --api-versions keda.sh/v1alpha1 -f sixeyed-peers.yaml \
  | kubectl apply --dry-run=server -n default -f -

# Python and TypeScript changes
ruff check src/services/messaging && ruff format --check src/services/messaging
(cd src/frontend && npm run lint && npm run build)
```
