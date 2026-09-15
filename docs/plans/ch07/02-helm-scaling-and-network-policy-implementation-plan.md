# Helm chart: Worker autoscaling, WebSocket-only real-time, NetworkPolicy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete `charts/collabhub` with KEDA-scaled Worker pools and deny-by-default NetworkPolicy, and make Socket.IO WebSocket-only so the real-time services need no session affinity.

**Architecture:** The Worker becomes two Deployments (`notify`, `batch`) rendered from a `pools` map, each with a KEDA `ScaledObject` on Redis Streams `lagCount`. Every component gets its own NetworkPolicy declaring both directions, with external peers supplied per environment in values. Messaging's server and the SPA's client both restrict Socket.IO to the `websocket` transport, and all `sessionAffinity` config leaves the chart.

**Tech Stack:** Helm 3.19, Kubernetes 1.34 (`sixeyed`), KEDA 2.20.1, python-socketio, socket.io-client, TypeScript/Vite.

**Spec:** `docs/plans/ch07/01-helm-scaling-and-network-policy-design.md`

## Global Constraints

- **Write no tests** — no unit, integration or BDD tests, steps or page objects (CLAUDE.md). Each task ends in render/lint/dry-run verification instead. Running *existing* suites is fine.
- **Never commit.** Stage nothing, no `git commit`, no PR. The worktree stays dirty.
- All work in the worktree `/Users/elton/scm/manning/caw-helm-scaling`, branch `feature/helm-scaling-netpol`. Every path below is relative to it.
- Dedicated templates per component under `templates/<component>/` — never one template ranging over `.Values.components`.
- KEDA scaler metric is `lagCount`, never `pendingEntriesCount`. Consumer group `worker`.
- Pools: `notify` = `jobs:notify`, 1 → 5; `batch` = `jobs:index, jobs:thumbnail, jobs:export, jobs:retention`, 0 → 10. `lagCount: "5"`, `activationLagCount: "0"`, `pollingInterval: 30`, `cooldownPeriod: 300`, `fallback: {failureThreshold: 3, replicas: 1}`.
- KEDA gets `host:port` via `addressFromEnv: REDIS_STREAMS_ADDRESS`; password via TriggerAuthentication from key `REDIS_STREAMS_PASSWORD` of the `collabhub-worker` secret.
- `networkPolicy.enabled` defaults to `true`. Empty peer needed by an enabled component → `fail` naming the peer.
- ADR filenames are `docs/adr/260914-<title>.md` (today is 2026-09-14), written with the `adr-writer` skill.
- `.claude/hooks/lint.sh` runs after every edit and blocks on findings — fix what it reports even when outside this task's narrow scope.

---

### Task 1: Socket.IO is WebSocket-only; the chart loses session affinity (D30)

**Files:**
- Modify: `src/services/messaging/messaging/realtime.py:143-154`
- Modify: `src/frontend/src/lib/realtime/socket.ts:26-29`
- Modify: `charts/collabhub/templates/{auth,messaging,canvas,asset,frontend}/service.yaml`
- Modify: `charts/collabhub/values.yaml` (every `sessionAffinity` line, Messaging's comment above it)
- Modify: `docs/design/00-platform-conventions.md:276-277`
- Modify: `docs/design/02-messaging-service.md` §3.2 opening paragraph
- Modify: `docs/design/07-open-decisions-register.md` (settled list, new D30 row)
- Create: `docs/adr/260914-websocket-only-socket-io.md` (via `adr-writer`)

**Interfaces:**
- Consumes: nothing.
- Produces: no `service.sessionAffinity` key in values — later tasks must not reintroduce it. Register has a `**Settled 2026-09-14:**` line that Task 2 extends.

- [ ] **Step 1: Messaging refuses polling**

In `build_server`, add `transports` after `cors_allowed_origins`:

```python
        cors_allowed_origins=context.settings.cors_allowed_origins or None,
        # WebSocket only (register D30). A long-polling session needs every
        # request to reach the same pod, and nothing in front of this service
        # promises that — so the server refuses polling rather than trusting
        # each client not to try it.
        transports=["websocket"],
    )
```

- [ ] **Step 2: The SPA stops offering polling**

In `socket.ts`:

```ts
  return io(`${MESSAGING_URL}/messaging`, {
    auth: { token: accessToken },
    // WebSocket only (register D30): the server refuses long-polling, so
    // offering it would only turn a blocked WebSocket into a confusing 400.
    transports: ['websocket'],
  })
```

- [ ] **Step 3: Remove affinity from the Service templates**

In each of `auth`, `messaging`, `canvas`, `asset`, `frontend` `service.yaml`, delete:

```yaml
  {{- with $component.service.sessionAffinity }}
  sessionAffinity: {{ . }}
  {{- end }}
```

Also delete the comment directly above it in `messaging/service.yaml`:

```yaml
  # Socket.IO falls back to HTTP long-polling, and a polling session's requests
  # must all reach the same pod. The R2 backplane lets any pod serve any room;
  # it does not rescue a handshake split across two of them.
```

and in `canvas/service.yaml`:

```yaml
  # Same long-polling constraint as Messaging.
```

Keep `asset/service.yaml`'s comment about `/api/v1/internal/` — it describes the Service, not affinity.

- [ ] **Step 4: Remove affinity from values**

In `values.yaml`, delete the `sessionAffinity:` line under every component's `service:` (six of them), and Messaging's four-line comment above its `sessionAffinity: ClientIP`:

```yaml
      # Socket.IO falls back to HTTP long-polling, and a polling session's
      # requests must all land on the same pod. The R2 backplane lets any pod
      # serve any room; it does not rescue a split polling handshake.
```

- [ ] **Step 5: Conventions §6**

Replace lines 276-277:

```markdown
- **Transport:** WebSockets preferred, automatic fallback to HTTP long-polling
  (Socket.IO default). The browser uses `socket.io-client`.
```

with:

```markdown
- **Transport:** WebSocket only — **decided 2026-09-14 (register D30).** Servers pass
  `transports=["websocket"]` and clients `transports: ['websocket']`; there is no HTTP
  long-polling fallback. A polling session needs every request on one pod, which neither a
  Service's `sessionAffinity` (bypassed by ingress-nginx) nor the R2 backplane provides, so
  refusing polling removes the need for affinity anywhere. Cost: a network that blocks
  WebSockets cannot connect. The browser uses `socket.io-client`.
```

- [ ] **Step 6: Doc 02 §3.2**

After the paragraph ending "`send_message` returns the created `Message` via the Socket.IO acknowledgement callback.", add:

```markdown

**WebSocket only — added 2026-09-14 (register D30).** `build_server` passes
`transports=["websocket"]`, so a long-polling handshake is refused rather than served, and
the chart sets no session affinity. See Conventions §6.
```

- [ ] **Step 7: Register**

After the `**Settled 2026-08-16:**` paragraph in *Resolve First*, add:

```markdown
**Settled 2026-09-14:** D30 — Socket.IO is WebSocket-only, which is what lets the
Helm chart carry no session affinity.
```

Append a row to the *Frontend SPA* table, after D28:

```markdown
| D30 | Socket.IO transport: WebSocket with long-polling fallback vs. WebSocket only (raised 2026-09-14; never had an ID) | 🟢 **Decided (2026-09-14):** WebSocket only, refused by the server as well as not offered by the client | Long-polling needs every request of a session on one pod. `sessionAffinity: ClientIP` is bypassed by ingress-nginx, and would see only the controller's IP if it were not, so the chart carries no affinity at all. Cost: networks that block WebSockets cannot connect. See [ADR 260914](../adr/260914-websocket-only-socket-io.md) | Cross-cutting (Messaging, Canvas, Frontend, chart) |
```

- [ ] **Step 8: ADR**

Invoke the `adr-writer` skill with: *"Socket.IO runs WebSocket-only — no long-polling fallback — enforced by the server (`transports=["websocket"]`) and the client. Because long-polling needs every request of a session to reach the same pod, and Service `sessionAffinity: ClientIP` is bypassed by ingress-nginx (which routes to endpoints) and would see only the controller's IP anyway. Alternatives: cookie affinity configured at the ingress (keeps polling, but lives outside the chart, which has no Ingress); ClientIP affinity in the chart only (ineffective behind an ingress). Consequence: clients on networks that block WebSockets cannot connect; Canvas must follow the same rule when its Socket.IO server is built."* Confirm the file lands at `docs/adr/260914-websocket-only-socket-io.md`; rename it if the skill chose a different slug, and fix the register link to match.

- [ ] **Step 9: Verify**

```bash
cd /Users/elton/scm/manning/caw-helm-scaling
uv run ruff check src/services/messaging && uv run ruff format --check src/services/messaging
uv run pytest src/services/messaging -m "not integration and not bdd" -q
# A new worktree has no node_modules
(cd src/frontend && npm ci && npm run lint && npm run build)
grep -rn "sessionAffinity" charts/ ; echo "exit=$? (expect 1: no matches)"
grep -n "long-polling" docs/design/00-platform-conventions.md
helm template t charts/collabhub > /dev/null && echo renders
```

Expected: ruff clean; existing unit tests pass; lint and build succeed; no `sessionAffinity` in `charts/`; the only Conventions hit is the new "no HTTP long-polling fallback" bullet; the chart still renders with default values (Tasks 2 and 3 have not added anything that needs KEDA or peers yet).

---

### Task 2: Worker pools scaled by KEDA (D17)

**Files:**
- Modify: `charts/collabhub/templates/_helpers.tpl` (`collabhub.selectorLabels`, new `collabhub.poolFullname`)
- Modify: `charts/collabhub/values.yaml` (`components.worker`)
- Modify: `charts/collabhub/templates/worker/deployment.yaml` (rewrite)
- Create: `charts/collabhub/templates/worker/scaledobject.yaml`
- Create: `charts/collabhub/templates/worker/triggerauthentication.yaml`
- Modify: `.env.example` (Worker section)
- Modify: `docs/design/05-worker-service.md` §5.3 and §9
- Modify: `docs/design/07-open-decisions-register.md` (D17 row, settled line)
- Modify: `docs/platform/versions.md` (new `keda` entry after `kubernetes`)
- Create: `docs/adr/260914-worker-pools-split-on-latency.md` (via `adr-writer`)

**Interfaces:**
- Consumes: Task 1's `**Settled 2026-09-14:**` register line.
- Produces:
  - `collabhub.selectorLabels` accepts an optional `pool` key in its dict and emits `collabhub.io/pool: <pool>` when present. Called without `pool` it renders exactly the three labels it does today — Task 3 relies on that to select *both* Worker pools with one policy.
  - `collabhub.poolFullname` takes `{root, name, pool}` → `<fullname>-<name>-<pool>`, truncated to 63.
  - Worker pods of every pool carry `app.kubernetes.io/component: worker`.

- [ ] **Step 1: Helpers**

Replace the `collabhub.selectorLabels` definition and its comment in `_helpers.tpl` with:

```
{{/*
app.kubernetes.io/component is what keeps one component's Deployment from
selecting another's pods — every component shares the name and instance labels.

collabhub.io/pool does the same job one level down: both Worker pools are
component "worker", and without it each pool's Deployment would select the
other's pods. Omit `pool` from the dict to select every pool of a component,
which is what a NetworkPolicy wants.
*/}}
{{- define "collabhub.selectorLabels" -}}
app.kubernetes.io/name: {{ include "collabhub.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .name }}
{{- with .pool }}
collabhub.io/pool: {{ . }}
{{- end }}
{{- end -}}
```

After `collabhub.componentFullname`, add:

```
{{/* Resource name for one pool of a component, e.g. collabhub-worker-notify. */}}
{{- define "collabhub.poolFullname" -}}
{{- printf "%s-%s" (include "collabhub.componentFullname" .) .pool | trunc 63 | trimSuffix "-" -}}
{{- end -}}
```

- [ ] **Step 2: Values**

Replace the whole `components.worker` block with:

```yaml
  worker:
    enabled: true
    # Only used with autoscaling disabled, when every pool runs this many. With
    # it enabled KEDA owns replicas and the Deployments omit the field.
    replicaCount: 1
    port: 8000
    image:
      repository: collabhub/worker
      tag: ""
    service:
      # No Service: the Worker serves no traffic. Its port carries health probes
      # only, and those are scraped from the pod (design doc 05 §2).
      create: false
      type: ClusterIP
    probes:
      live: /health/live
      ready: /health/ready
    env:
      APP_ENV: production
      LOG_LEVEL: info
      WORKER_MAX_ATTEMPTS: "5"
      WORKER_VISIBILITY_TIMEOUT_SECONDS: "60"
      WORKER_BATCH_SIZE: "16"
      OBJECT_STORE_BUCKET: collabhub-assets
      ASSET_INTERNAL_URL: http://collabhub-asset:8000/api/v1/internal
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4317
      # For KEDA, not the Worker process: the Redis Streams scaler takes
      # host:port and cannot parse the REDIS_STREAMS_URL the Worker uses.
      REDIS_STREAMS_ADDRESS: redis-streams:6379
    # Supplies REDIS_STREAMS_URL, REDIS_STREAMS_PASSWORD (read by KEDA),
    # ELASTICSEARCH_URL, OBJECT_STORE_*_KEY, SERVICE_TOKEN_URL and
    # WORKER_SERVICE_CLIENT_SECRET.
    envFromSecrets:
      - collabhub-worker
    autoscaling:
      # Requires KEDA (keda.sh/v1alpha1); the chart fails without it.
      enabled: true
      pollingInterval: 30
      cooldownPeriod: 300
      consumerGroup: worker # doc 05 §5.1
      lagCount: "5"
    # One Deployment and one ScaledObject per pool (register D17). Split on
    # latency: notify keeps a floor for its < 5 s p95 target, batch scales from
    # zero. A pool's streams become its WORKER_STREAMS.
    pools:
      notify:
        streams:
          - jobs:notify
        minReplicas: 1
        maxReplicas: 5
      batch:
        streams:
          - jobs:index
          - jobs:thumbnail
          - jobs:export
          - jobs:retention
        minReplicas: 0
        maxReplicas: 10
```

`WORKER_STREAMS` leaves the shared env on purpose: every pool sets its own, and a shared value would only mislead.

- [ ] **Step 3: Deployment per pool**

Replace `templates/worker/deployment.yaml` entirely with:

```yaml
{{- $component := .Values.components.worker }}
{{- if $component.enabled }}
{{- range $poolName, $pool := $component.pools }}
{{- $ctx := dict "root" $ "name" "worker" "pool" $poolName }}
---
# One Deployment per pool (register D17). Pools share image, ConfigMap and
# secret, and differ only in WORKER_STREAMS. With autoscaling enabled KEDA owns
# replicas through scaledobject.yaml, so spec.replicas is omitted — otherwise
# every `helm upgrade` would reset what the HPA had set.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "collabhub.poolFullname" $ctx }}
  labels:
    {{- include "collabhub.labels" $ctx | nindent 4 }}
spec:
  {{- if not $component.autoscaling.enabled }}
  replicas: {{ $component.replicaCount | default 1 }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "collabhub.selectorLabels" $ctx | nindent 6 }}
  template:
    metadata:
      annotations:
        # Roll this component's pods when its own config changes — scoped to the
        # component so an Auth config edit does not restart Messaging.
        checksum/config: {{ toYaml $component.env | sha256sum }}
      labels:
        {{- include "collabhub.selectorLabels" $ctx | nindent 8 }}
    spec:
      # Conventions §10: drain in-flight work before exiting.
      terminationGracePeriodSeconds: {{ $.Values.terminationGracePeriodSeconds }}
      securityContext:
        {{- toYaml ($component.podSecurityContext | default $.Values.defaults.podSecurityContext) | nindent 8 }}
      containers:
        - name: worker
          image: "{{ $component.image.repository }}:{{ $component.image.tag | default $.Chart.AppVersion }}"
          imagePullPolicy: {{ $.Values.imagePullPolicy }}
          securityContext:
            {{- toYaml ($component.containerSecurityContext | default $.Values.defaults.containerSecurityContext) | nindent 12 }}
          ports:
            - name: http
              containerPort: {{ $component.port }}
              protocol: TCP
          env:
            - name: WORKER_STREAMS
              value: {{ join "," $pool.streams | quote }}
          envFrom:
            - configMapRef:
                name: {{ include "collabhub.componentFullname" $ctx }}
            {{- range $component.envFromSecrets }}
            - secretRef:
                name: {{ . }}
            {{- end }}
          livenessProbe:
            httpGet:
              path: {{ $component.probes.live }}
              port: http
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: {{ $component.probes.ready }}
              port: http
            periodSeconds: 10
          resources:
            {{- toYaml ($component.resources | default $.Values.defaults.resources) | nindent 12 }}
{{- end }}
{{- end }}
```

`collabhub.componentFullname` ignores `pool`, so every pool references the one shared ConfigMap `<fullname>-worker`.

- [ ] **Step 4: ScaledObject per pool**

Create `templates/worker/scaledobject.yaml`:

```yaml
{{- $component := .Values.components.worker }}
{{- if and $component.enabled $component.autoscaling.enabled }}
{{- if not ($.Capabilities.APIVersions.Has "keda.sh/v1alpha1") }}
{{- fail "components.worker.autoscaling.enabled is true, but this cluster has no keda.sh/v1alpha1 API. Install KEDA, set components.worker.autoscaling.enabled=false, or render offline with --api-versions keda.sh/v1alpha1." }}
{{- end }}
{{- $scaling := $component.autoscaling }}
{{- range $poolName, $pool := $component.pools }}
{{- $ctx := dict "root" $ "name" "worker" "pool" $poolName }}
---
# lagCount, not pendingEntriesCount (doc 05 §5.3). Pending entries are ones a
# consumer has read and not acked: with zero pods nothing is read, the count
# stays 0, and a pool at zero never wakes. Lag is what the group has not read
# yet — the only Redis Streams metric KEDA can scale from zero on. Redis 7+.
# One trigger per stream; the HPA follows whichever asks for the most pods.
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: {{ include "collabhub.poolFullname" $ctx }}
  labels:
    {{- include "collabhub.labels" $ctx | nindent 4 }}
spec:
  scaleTargetRef:
    name: {{ include "collabhub.poolFullname" $ctx }}
    # addressFromEnv resolves against this container's env, ConfigMap included.
    envSourceContainerName: worker
  minReplicaCount: {{ $pool.minReplicas }}
  maxReplicaCount: {{ $pool.maxReplicas }}
  pollingInterval: {{ $scaling.pollingInterval }}
  cooldownPeriod: {{ $scaling.cooldownPeriod }}
  # Not for a missing consumer group — KEDA reads that as a real (if wrong)
  # lag, never an error, so this never engages there. It's for Redis being
  # unreachable or the trigger's auth failing (plan 01, "Known gap").
  fallback:
    failureThreshold: 3
    replicas: 1
  triggers:
    {{- range $pool.streams }}
    - type: redis-streams
      metadata:
        addressFromEnv: REDIS_STREAMS_ADDRESS
        stream: {{ . | quote }}
        consumerGroup: {{ $scaling.consumerGroup | quote }}
        lagCount: {{ $scaling.lagCount | quote }}
        activationLagCount: "0"
      authenticationRef:
        name: {{ include "collabhub.componentFullname" $ctx }}
    {{- end }}
{{- end }}
{{- end }}
```

- [ ] **Step 5: TriggerAuthentication**

Create `templates/worker/triggerauthentication.yaml`:

```yaml
{{- $component := .Values.components.worker }}
{{- if and $component.enabled $component.autoscaling.enabled }}
{{- $ctx := dict "root" $ "name" "worker" }}
# KEDA's credential for R3. The address comes from the Worker's own env
# (REDIS_STREAMS_ADDRESS) and the password from the Worker's own secret, so
# KEDA holds nothing the Worker does not — one credential to rotate, not two.
apiVersion: keda.sh/v1alpha1
kind: TriggerAuthentication
metadata:
  name: {{ include "collabhub.componentFullname" $ctx }}
  labels:
    {{- include "collabhub.labels" $ctx | nindent 4 }}
spec:
  secretTargetRef:
    - parameter: password
      name: {{ first $component.envFromSecrets }}
      key: REDIS_STREAMS_PASSWORD
{{- end }}
```

- [ ] **Step 6: `.env.example`**

In the Worker section, replace:

```
WORKER_STREAMS=jobs:index,jobs:thumbnail,jobs:notify,jobs:export,jobs:retention
```

with:

```
# Locally one Worker consumes everything. The Helm chart runs two pools instead,
# each with its own WORKER_STREAMS (register D17, doc 05 §5.3).
WORKER_STREAMS=jobs:index,jobs:thumbnail,jobs:notify,jobs:export,jobs:retention
```

and after `WORKER_BATCH_SIZE=16` add:

```

# Chart-only — read by KEDA to scale the Worker pools, never by the Worker process,
# which uses REDIS_STREAMS_URL. KEDA's Redis Streams scaler takes host:port and
# cannot parse a redis:// URL. Nothing in docker compose reads these.
REDIS_STREAMS_ADDRESS=redis-streams:6379
REDIS_STREAMS_PASSWORD=
```

- [ ] **Step 7: Doc 05**

Replace §5.3 (the heading and its two lines) with:

```markdown
### 5.3 Scaling (KEDA)
🟢 **Decided 2026-09-14 (register D17)** — two pools, split on latency. See the
[ADR](../adr/260914-worker-pools-split-on-latency.md).

| Pool | Streams | Replicas |
|------|---------|----------|
| `notify` | `jobs:notify` | 1 → N. The floor holds the < 5 s p95 target (§8) |
| `batch` | `jobs:index`, `jobs:thumbnail`, `jobs:export`, `jobs:retention` | 0 → N |

Each pool is its own Deployment with `WORKER_STREAMS` set to its streams, and its own
`ScaledObject` with one Redis Streams trigger per stream on **`lagCount`** for consumer group
`worker`. **Corrected 2026-09-14 — this section said `pendingEntriesCount`**, which counts
entries a consumer has read and not acked. With zero pods nothing is read, so the count never
leaves 0 and a pool at zero never wakes. Lag is what the group has not yet read; it is the only
Redis Streams metric KEDA can scale from zero on, and needs Redis 7+.

The split is on latency, not the CPU/IO axis this doc first suggested, because one Deployment
cannot both scale to zero and hold a notify floor. Splitting `batch` by CPU/IO later needs no
code change — only another pool.

**Consumer groups must exist before a producer writes to their stream.** The Worker does not
create them yet, and no service produces jobs yet either, so today this is silent: KEDA (v2.20.1)
reads a missing stream as lag `0` with no error, so `batch` correctly sits at zero. **Corrected
2026-09-14** — the earlier version of this paragraph said the triggers error and the fallback
holds each pool at one replica until the groups exist; that is not what the scaler does. A
missing *group* on a stream that already exists is also not an error — KEDA reads `XLEN` as the
lag instead, so if a producer ships before the Worker creates its groups, the affected pool scales
to its max and nothing drains it, because no consumer is reading. The fallback's real job is
covering Redis being unreachable or the trigger's auth failing, not a missing group. Consumer
groups must therefore be created before, or in the same slice as, the first producer for their
stream — from ID `0`, `XGROUP CREATE <stream> worker 0 MKSTREAM` — so the lag KEDA measures
matches what's already in the stream.
```

In §9, replace the **Specialised worker pools** bullet (three lines) with:

```markdown
- ~~**Specialised worker pools**~~ — 🟢 **Decided 2026-09-14 (register D17).** Two pools,
  `notify` and `batch`, split on latency. See §5.3 and the
  [ADR](../adr/260914-worker-pools-split-on-latency.md).
```

- [ ] **Step 8: Register**

Replace the D17 row with:

```markdown
| D17 | Specialised worker pools vs. one deployment for all streams | 🟢 **Decided (2026-09-14):** two pools split on latency — `notify` (`jobs:notify`, floor of 1) and `batch` (`jobs:index`, `jobs:thumbnail`, `jobs:export`, `jobs:retention`, scales from 0) | One Deployment cannot both scale to zero and hold a notify floor. KEDA scales each pool on `lagCount`; the doc's `pendingEntriesCount` could never wake a pool from zero. A CPU/IO split inside `batch` remains possible. See [ADR 260914](../adr/260914-worker-pools-split-on-latency.md) | Worker |
```

Change Task 1's settled line to:

```markdown
**Settled 2026-09-14:** D17 — the Worker runs as two KEDA-scaled pools split on
latency — and D30 — Socket.IO is WebSocket-only, which is what lets the Helm chart
carry no session affinity.
```

- [ ] **Step 9: `versions.md`**

Look up the newest KEDA release:

```bash
gh release view --repo kedacore/keda --json tagName,publishedAt
```

After the `kubernetes` entry, add (fill `current_stable`, `last_notified` and `released` from that output — `last_notified` equals `current_stable`, the tag without its leading `v`):

```yaml
- id: keda
  name: KEDA
  category: orchestration
  used_for: Autoscales the Worker pools on Redis Streams lag (doc 05 §5.3); a cluster add-on the Helm chart requires
  pinned_track: "2"
  current_stable: "<tag from gh>"
  last_notified: "<tag from gh>"   # watermark: last version announced to #stack-updates; skill only alerts when upstream > this
  released: "<publishedAt date from gh, YYYY-MM-DD>"
  base_image_hint: n/a           # cluster add-on, installed once per cluster, not an app base image
  check_url: https://github.com/kedacore/keda/releases
  eol_url: https://keda.sh/docs/latest/operate/cluster/
  notes: >
    Installed per cluster, not by the CollabHub chart, which fails to render without the
    keda.sh/v1alpha1 API. The redis-streams trigger's lagCount is the only metric that
    scales from zero and needs Redis 7+ (pinned track is 8). Check KEDA's Kubernetes
    compatibility table before a cluster upgrade. sixeyed runs 2.20.1 as of 2026-09-14.
```

- [ ] **Step 10: ADR**

Invoke `adr-writer` with: *"The Worker runs as two pools, split on latency: `notify` (jobs:notify, floor of one replica) and `batch` (jobs:index, jobs:thumbnail, jobs:export, jobs:retention, scales from zero), each a Deployment with its own KEDA ScaledObject on Redis Streams lagCount. Because design doc 05 wanted both scale-to-zero and a floor for the < 5 s p95 notify target, which one Deployment cannot do; and because pendingEntriesCount — what the doc named — cannot wake a pool from zero. Alternatives: one pool with a floor of 1 (no scale-to-zero); one pool scaling to zero (notify misses its target after idle); the CPU/IO split the register suggested (does not address the notify floor). Consequences: the chart requires KEDA; consumer groups must be created before, or in the same slice as, the first producer for their stream — KEDA v2.20.1 reads a missing stream as lag 0 with no error, but a missing group on a stream that already exists returns XLEN as the lag, also with no error, so a producer that ships first pins the affected pool at its max replica count rather than tripping the fallback."* Confirm the file is `docs/adr/260914-worker-pools-split-on-latency.md`; rename it and fix links in doc 05 and the register if not.

- [ ] **Step 11: Verify**

```bash
cd /Users/elton/scm/manning/caw-helm-scaling
# Renders with KEDA declared: 2 Deployments, 2 ScaledObjects, 1 TriggerAuthentication for the Worker
helm template t charts/collabhub --api-versions keda.sh/v1alpha1 \
  | grep -E "^kind:|^  name:" | paste - - | grep worker
# batch has no replicas field and minReplicaCount 0; notify has minReplicaCount 1
helm template t charts/collabhub --api-versions keda.sh/v1alpha1 -s templates/worker/scaledobject.yaml \
  | grep -E "name: t-collabhub-worker|minReplicaCount|stream:"
# Pools select only their own pods
helm template t charts/collabhub --api-versions keda.sh/v1alpha1 -s templates/worker/deployment.yaml \
  | grep -E "collabhub.io/pool|replicas:|WORKER_STREAMS" -A1
# Fails without KEDA
helm template t charts/collabhub 2>&1 | grep "no keda.sh/v1alpha1 API"
# Autoscaling off: plain Deployments with replicas, no KEDA objects
helm template t charts/collabhub --set components.worker.autoscaling.enabled=false \
  | grep -cE "kind: (ScaledObject|TriggerAuthentication)"
```

Expected: `Deployment`, `ScaledObject` for both `t-collabhub-worker-batch` and `-notify`, one `TriggerAuthentication t-collabhub-worker`; `minReplicaCount: 0` for batch with four `stream:` lines, `1` for notify with one; each Deployment's selector and pod labels carry its own `collabhub.io/pool`, no `replicas:` line, `WORKER_STREAMS` values match; the no-KEDA render prints the fail message; the last command prints `0`.

---

### Task 3: NetworkPolicy — deny all, allow listed

**Files:**
- Modify: `charts/collabhub/templates/_helpers.tpl` (four new helpers)
- Modify: `charts/collabhub/values.yaml` (header comment, new `networkPolicy` block)
- Create: `charts/collabhub/templates/{auth,messaging,canvas,asset,worker,frontend}/networkpolicy.yaml`
- Modify: `docs/design/00-platform-conventions.md:41-43`, `CLAUDE.md` (chart description sentence)

**Interfaces:**
- Consumes: `collabhub.selectorLabels` called with `{root, name}` and no `pool` (Task 2) — matches every pool of a component.
- Produces: `networkPolicy.enabled`, `networkPolicy.peers.<peer>.{to|from, ports}` values; helpers `collabhub.ingressFromController`, `collabhub.ingressFromComponents`, `collabhub.egressToPeer`, `collabhub.egressToComponent`.

- [ ] **Step 1: Helpers**

Append to `_helpers.tpl`:

```
{{/*
NetworkPolicy rules. Each renders one list item for a policy's ingress or
egress, so a policy reads as a list of includes.

External peers come from .Values.networkPolicy.peers and fail the render when
empty: a pod that cannot reach its database is worse than a chart that refuses.
In-release peers are matched on this chart's own labels, with no pool, so one
rule covers every Worker pool.

Ports: ingress names the pod's `http` port; egress to a component uses that
component's numeric port, because a NetworkPolicy is evaluated against the pod
behind a Service, not the Service.
*/}}

{{/* Usage: include "collabhub.ingressFromController" (dict "root" $ "name" "auth") */}}
{{- define "collabhub.ingressFromController" -}}
{{- $peer := .root.Values.networkPolicy.peers.ingressController -}}
{{- if not $peer.from -}}
{{- fail (printf "networkPolicy.peers.ingressController.from is empty, and %s needs it. Set it, or set networkPolicy.enabled=false." .name) -}}
{{- end -}}
- from:
    {{- toYaml $peer.from | nindent 4 }}
  ports:
    - port: http
      protocol: TCP
{{- end -}}

{{/* Usage: include "collabhub.ingressFromComponents" (dict "root" $ "from" (list "worker")) */}}
{{- define "collabhub.ingressFromComponents" -}}
- from:
    {{- range .from }}
    - podSelector:
        matchLabels:
          {{- include "collabhub.selectorLabels" (dict "root" $.root "name" .) | nindent 10 }}
    {{- end }}
  ports:
    - port: http
      protocol: TCP
{{- end -}}

{{/* Usage: include "collabhub.egressToPeer" (dict "root" $ "name" "auth" "peer" "postgres") */}}
{{- define "collabhub.egressToPeer" -}}
{{- $peer := index .root.Values.networkPolicy.peers .peer -}}
{{- if not $peer.to -}}
{{- fail (printf "networkPolicy.peers.%s.to is empty, and %s needs it. Set it, or set networkPolicy.enabled=false." .peer .name) -}}
{{- end -}}
- to:
    {{- toYaml $peer.to | nindent 4 }}
  ports:
    {{- toYaml $peer.ports | nindent 4 }}
{{- end -}}

{{/* Usage: include "collabhub.egressToComponent" (dict "root" $ "target" "auth") */}}
{{- define "collabhub.egressToComponent" -}}
{{- $target := index .root.Values.components .target -}}
- to:
    - podSelector:
        matchLabels:
          {{- include "collabhub.selectorLabels" (dict "root" .root "name" .target) | nindent 10 }}
  ports:
    - port: {{ $target.port }}
      protocol: TCP
{{- end -}}
```

- [ ] **Step 2: Values**

Append to the end of `values.yaml`:

```yaml

# NetworkPolicy — one per component, each declaring Ingress and Egress, so
# anything a policy does not list is denied in both directions.
#
# Traffic inside the release is matched on this chart's labels. Everything
# outside it is a peer below: a NetworkPolicyPeer list (selectors or ipBlock)
# plus ports, because where Postgres, Redis and the rest live is per
# environment. A peer an enabled component needs, left empty, fails the render.
#
# NetworkPolicy is L3/L4. It cannot keep /api/v1/internal/ away from the
# ingress controller, which reaches the same port as the public routes — that
# stays an ingress routing rule (Conventions §5.5). And it is only enforced by
# a CNI that implements it; elsewhere these objects apply and block nothing.
networkPolicy:
  enabled: true
  peers:
    ingressController:
      from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
          podSelector:
            matchLabels:
              app.kubernetes.io/name: ingress-nginx
    dns:
      to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
    postgres:
      to: []
      ports:
        - port: 5432
          protocol: TCP
    # R1 — cache and token denylist.
    redisCache:
      to: []
      ports:
        - port: 6379
          protocol: TCP
    # R2 — Socket.IO backplane.
    redisRealtime:
      to: []
      ports:
        - port: 6379
          protocol: TCP
    # R3 — job streams.
    redisStreams:
      to: []
      ports:
        - port: 6379
          protocol: TCP
    elasticsearch:
      to: []
      ports:
        - port: 9200
          protocol: TCP
    # Garage's S3 API, or whatever S3-compatible store replaces it.
    objectStore:
      to: []
      ports:
        - port: 3900
          protocol: TCP
    otelCollector:
      to: []
      ports:
        - port: 4317
          protocol: TCP
    # Auth's upstream IdP (register D5) — discovery, token exchange and JWKS.
    oidcProvider:
      to: []
      ports:
        - port: 443
          protocol: TCP
```

Replace the second paragraph of the header comment:

```yaml
# Each component has its own templates under templates/<component>/, rather than
# one set of templates ranging over this map. They start near-identical and are
# meant to diverge: the Worker gets a KEDA ScaledObject, the real-time services
# need session affinity, the frontend has no config at all.
```

with:

```yaml
# Each component has its own templates under templates/<component>/, rather than
# one set of templates ranging over this map. They start near-identical and are
# meant to diverge: the Worker runs as KEDA-scaled pools, each component has its
# own NetworkPolicy, the frontend has no config at all.
```

- [ ] **Step 3: Auth policy**

Create `templates/auth/networkpolicy.yaml`:

```yaml
{{- $component := .Values.components.auth }}
{{- if and $component.enabled .Values.networkPolicy.enabled }}
{{- $ctx := dict "root" $ "name" "auth" }}
# Auth — reached by the browser through the ingress, by every service for JWKS,
# and by the Worker for service tokens. Reaches its own Postgres, R1 for the
# denylist, and the upstream OIDC provider (register D5).
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "collabhub.componentFullname" $ctx }}
  labels:
    {{- include "collabhub.labels" $ctx | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "collabhub.selectorLabels" $ctx | nindent 6 }}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    {{- include "collabhub.ingressFromController" $ctx | nindent 4 }}
    {{- include "collabhub.ingressFromComponents" (dict "root" $ "from" (list "messaging" "canvas" "asset" "worker")) | nindent 4 }}
  egress:
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "auth" "peer" "dns") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "auth" "peer" "postgres") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "auth" "peer" "redisCache") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "auth" "peer" "oidcProvider") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "auth" "peer" "otelCollector") | nindent 4 }}
{{- end }}
```

- [ ] **Step 4: Messaging policy**

Create `templates/messaging/networkpolicy.yaml`:

```yaml
{{- $component := .Values.components.messaging }}
{{- if and $component.enabled .Values.networkPolicy.enabled }}
{{- $ctx := dict "root" $ "name" "messaging" }}
# Messaging — reached by the browser through the ingress (REST and the
# /messaging WebSocket) and by the Worker for its internal sweep endpoint.
# Reaches Postgres, all three Redis instances (R3 to enqueue jobs:index),
# Elasticsearch read-only for GET /search/messages (register D8c), and Auth
# for JWKS.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "collabhub.componentFullname" $ctx }}
  labels:
    {{- include "collabhub.labels" $ctx | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "collabhub.selectorLabels" $ctx | nindent 6 }}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    {{- include "collabhub.ingressFromController" $ctx | nindent 4 }}
    {{- include "collabhub.ingressFromComponents" (dict "root" $ "from" (list "worker")) | nindent 4 }}
  egress:
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "messaging" "peer" "dns") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "messaging" "peer" "postgres") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "messaging" "peer" "redisCache") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "messaging" "peer" "redisRealtime") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "messaging" "peer" "redisStreams") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "messaging" "peer" "elasticsearch") | nindent 4 }}
    {{- include "collabhub.egressToComponent" (dict "root" $ "target" "auth") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "messaging" "peer" "otelCollector") | nindent 4 }}
{{- end }}
```

- [ ] **Step 5: Canvas policy**

Create `templates/canvas/networkpolicy.yaml`:

```yaml
{{- $component := .Values.components.canvas }}
{{- if and $component.enabled .Values.networkPolicy.enabled }}
{{- $ctx := dict "root" $ "name" "canvas" }}
# Canvas — reached by the browser through the ingress (REST and the /canvas
# WebSocket) and by the Worker for document state and its sweep endpoint.
# Reaches Postgres, R1 for the hot-document cache, R2 for the relay, and Auth
# for JWKS. Canvas produces no jobs, so no R3 (doc 03).
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "collabhub.componentFullname" $ctx }}
  labels:
    {{- include "collabhub.labels" $ctx | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "collabhub.selectorLabels" $ctx | nindent 6 }}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    {{- include "collabhub.ingressFromController" $ctx | nindent 4 }}
    {{- include "collabhub.ingressFromComponents" (dict "root" $ "from" (list "worker")) | nindent 4 }}
  egress:
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "canvas" "peer" "dns") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "canvas" "peer" "postgres") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "canvas" "peer" "redisCache") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "canvas" "peer" "redisRealtime") | nindent 4 }}
    {{- include "collabhub.egressToComponent" (dict "root" $ "target" "auth") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "canvas" "peer" "otelCollector") | nindent 4 }}
{{- end }}
```

- [ ] **Step 6: Asset policy**

Create `templates/asset/networkpolicy.yaml`:

```yaml
{{- $component := .Values.components.asset }}
{{- if and $component.enabled .Values.networkPolicy.enabled }}
{{- $ctx := dict "root" $ "name" "asset" }}
# Asset — reached by the browser through the ingress and by the Worker for the
# variants write-back and sweep. Reaches Postgres, R1 (DELETE is in the
# fail-closed denylist set), R3 to enqueue thumbnails, the object store, and
# Auth for JWKS. Browser uploads go to the object store directly, never here.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "collabhub.componentFullname" $ctx }}
  labels:
    {{- include "collabhub.labels" $ctx | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "collabhub.selectorLabels" $ctx | nindent 6 }}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    {{- include "collabhub.ingressFromController" $ctx | nindent 4 }}
    {{- include "collabhub.ingressFromComponents" (dict "root" $ "from" (list "worker")) | nindent 4 }}
  egress:
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "asset" "peer" "dns") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "asset" "peer" "postgres") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "asset" "peer" "redisCache") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "asset" "peer" "redisStreams") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "asset" "peer" "objectStore") | nindent 4 }}
    {{- include "collabhub.egressToComponent" (dict "root" $ "target" "auth") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "asset" "peer" "otelCollector") | nindent 4 }}
{{- end }}
```

- [ ] **Step 7: Worker policy**

Create `templates/worker/networkpolicy.yaml`:

```yaml
{{- $component := .Values.components.worker }}
{{- if and $component.enabled .Values.networkPolicy.enabled }}
{{- $ctx := dict "root" $ "name" "worker" }}
# Worker — one policy for every pool: the selector carries no collabhub.io/pool.
# Nothing may reach it; its port answers kubelet probes only, which come from
# the node. Reaches R3, Elasticsearch, the object store, Auth for service
# tokens, and the internal endpoints of Messaging, Canvas and Asset.
# No notification providers yet: channels are undecided (register D18).
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "collabhub.componentFullname" $ctx }}
  labels:
    {{- include "collabhub.labels" $ctx | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "collabhub.selectorLabels" $ctx | nindent 6 }}
  policyTypes:
    - Ingress
    - Egress
  ingress: []
  egress:
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "worker" "peer" "dns") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "worker" "peer" "redisStreams") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "worker" "peer" "elasticsearch") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "worker" "peer" "objectStore") | nindent 4 }}
    {{- include "collabhub.egressToComponent" (dict "root" $ "target" "auth") | nindent 4 }}
    {{- include "collabhub.egressToComponent" (dict "root" $ "target" "messaging") | nindent 4 }}
    {{- include "collabhub.egressToComponent" (dict "root" $ "target" "canvas") | nindent 4 }}
    {{- include "collabhub.egressToComponent" (dict "root" $ "target" "asset") | nindent 4 }}
    {{- include "collabhub.egressToPeer" (dict "root" $ "name" "worker" "peer" "otelCollector") | nindent 4 }}
{{- end }}
```

- [ ] **Step 8: Frontend policy**

Create `templates/frontend/networkpolicy.yaml`:

```yaml
{{- $component := .Values.components.frontend }}
{{- if and $component.enabled .Values.networkPolicy.enabled }}
{{- $ctx := dict "root" $ "name" "frontend" }}
# Frontend — static files behind Nginx. Reached only through the ingress, and
# reaches nothing at all, not even DNS: the SPA talks to the APIs from the
# browser, never from this pod.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "collabhub.componentFullname" $ctx }}
  labels:
    {{- include "collabhub.labels" $ctx | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "collabhub.selectorLabels" $ctx | nindent 6 }}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    {{- include "collabhub.ingressFromController" $ctx | nindent 4 }}
  egress: []
{{- end }}
```

- [ ] **Step 9: Conventions and CLAUDE.md wording**

In `docs/design/00-platform-conventions.md` lines 41-43 and in `CLAUDE.md`'s repo-layout paragraph about `charts/collabhub`, replace the phrase:

```
the Worker needs a KEDA `ScaledObject`, the real-time services need session affinity, the frontend has no ConfigMap.
```

(line-wrapped differently in each file — match the words, not the breaks) with:

```
the Worker runs as KEDA-scaled pools, every component has its own NetworkPolicy, the frontend has no ConfigMap.
```

Re-wrap to the surrounding line length.

- [ ] **Step 10: Verify**

Write a scratch peers file **outside the repo** at `/private/tmp/claude-501/-Users-elton-scm-manning-caw-project/d9ccf961-7df5-4857-93d9-d1287b14d3d3/scratchpad/sixeyed-peers.yaml`:

```yaml
# sixeyed: controller in `ingress`, Postgres in `data`, Elasticsearch in
# `logging`, Dex in `dex`. The stores sixeyed does not run get TEST-NET
# placeholders — this file exists to render and validate, not to deploy.
networkPolicy:
  peers:
    ingressController:
      from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress
          podSelector:
            matchLabels:
              app.kubernetes.io/name: ingressnginx
    postgres:
      to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: data
    redisCache:
      to:
        - ipBlock:
            cidr: 192.0.2.11/32
    redisRealtime:
      to:
        - ipBlock:
            cidr: 192.0.2.12/32
    redisStreams:
      to:
        - ipBlock:
            cidr: 192.0.2.13/32
    elasticsearch:
      to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: logging
    objectStore:
      to:
        - ipBlock:
            cidr: 192.0.2.14/32
    otelCollector:
      to:
        - ipBlock:
            cidr: 192.0.2.15/32
    oidcProvider:
      to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: dex
      ports:
        - port: 5556
          protocol: TCP
```

Then:

```bash
cd /Users/elton/scm/manning/caw-helm-scaling
PEERS=/private/tmp/claude-501/-Users-elton-scm-manning-caw-project/d9ccf961-7df5-4857-93d9-d1287b14d3d3/scratchpad/sixeyed-peers.yaml
# Six policies
helm template t charts/collabhub -a keda.sh/v1alpha1 -f $PEERS | grep -A2 "^kind: NetworkPolicy" | grep "name:"
# Default values fail, naming a peer
helm template t charts/collabhub -a keda.sh/v1alpha1 2>&1 | grep "networkPolicy.peers"
# Disabled renders no policies and needs no peers
helm template t charts/collabhub -a keda.sh/v1alpha1 --set networkPolicy.enabled=false | grep -c "kind: NetworkPolicy"
# Worker policy selects without a pool label; frontend has empty egress
helm template t charts/collabhub -a keda.sh/v1alpha1 -f $PEERS -s templates/worker/networkpolicy.yaml -s templates/frontend/networkpolicy.yaml
```

Expected: six names `t-collabhub-{asset,auth,canvas,frontend,messaging,worker}`; the default render prints `networkPolicy.peers.… is empty, and … needs it`; disabled prints `0`; the Worker policy's `podSelector` has three labels and no `collabhub.io/pool`, `ingress: []`; the frontend policy has `egress: []`.

---

### Task 4: Whole-chart verification against `sixeyed`

**Files:** none changed — unless a check fails, in which case fix it in the task that owns the file.

**Interfaces:**
- Consumes: everything above, and the scratch `sixeyed-peers.yaml` from Task 3 Step 10.
- Produces: the evidence reported back to the user.

- [ ] **Step 1: Lint**

```bash
cd /Users/elton/scm/manning/caw-helm-scaling
PEERS=/private/tmp/claude-501/-Users-elton-scm-manning-caw-project/d9ccf961-7df5-4857-93d9-d1287b14d3d3/scratchpad/sixeyed-peers.yaml
helm lint charts/collabhub -f $PEERS --set components.worker.autoscaling.enabled=false
```

Expected: `1 chart(s) linted, 0 chart(s) failed`. (`helm lint` has no `--api-versions`, so autoscaling must be off for it to render.)

- [ ] **Step 2: Resource inventory**

```bash
helm template t charts/collabhub -a keda.sh/v1alpha1 -f $PEERS \
  | grep -E "^kind:|^  name:" | paste - - | sort | uniq -c
```

Expected: 5 ConfigMaps, 7 Deployments (`asset, auth, canvas, frontend, messaging, worker-batch, worker-notify`), 6 NetworkPolicies, 2 ScaledObjects, 5 Services, 1 TriggerAuthentication. No `sessionAffinity` anywhere.

- [ ] **Step 3: Server-side validation — creates nothing**

```bash
kubectl config current-context   # must print sixeyed
helm template t charts/collabhub -a keda.sh/v1alpha1 -f $PEERS \
  | kubectl apply --dry-run=server -n default -f -
```

Expected: every object reports `(server dry run)` — including the ScaledObjects against KEDA 2.20.1's CRD and the NetworkPolicies' named `http` ports.

A dry run creates nothing, so KEDA's admission webhook cannot find the Deployments a ScaledObject targets. If a ScaledObject is rejected **only** with a message that its scale target was not found, that is the dry run, not the chart: record the message and treat that object as unvalidated. Any other rejection — unknown field, wrong type, invalid value — is a real failure; fix it in the task that owns the template and rerun.

- [ ] **Step 4: Repo checks**

```bash
uv run ruff check src/services/messaging && uv run ruff format --check src/services/messaging
(cd src/frontend && { [ -d node_modules ] || npm ci; } && npm run lint && npm run build)
python3 .claude/hooks/checks/conventions.py
git status --short
```

Expected: clean ruff, lint and build; no convention findings; `git status` lists only the files named in Tasks 1–3 plus the two ADRs and the two `docs/plans/ch07/` files — nothing staged.

- [ ] **Step 5: Report**

Tell the user, without committing: what changed per task, the verification output, that `sixeyed` has no policy-enforcing CNI so the policies validate but do not block, and the two follow-ups the spec left out of scope — the Worker creating its consumer groups, and the hard-coded `http://collabhub-auth:8000` URLs in values.
