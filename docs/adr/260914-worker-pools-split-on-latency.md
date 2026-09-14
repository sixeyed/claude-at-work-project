# The Worker runs as two KEDA-scaled pools, split on latency

- **Status:** Accepted
- **Date:** 2026-09-14

## Context

Register entry **D17** has sat open since the Worker's design doc was first
written: whether the Worker should be one Deployment consuming every job
stream, or several specialised pools that scale independently. The doc's
working default leaned toward splitting CPU-heavy streams (`jobs:thumbnail`,
`jobs:export`) from IO-heavy ones (`jobs:index`, `jobs:notify`), but never
settled it, and `docs/design/05-worker-service.md` §5.3 described the intended
scaling mechanism — a `ScaledObject` per Deployment, scaling 0→N on depth, with
"a floor for latency-sensitive `jobs:notify`" — as if a single Deployment could
carry both a scale-to-zero policy and a nonzero floor at the same time. It
cannot: `minReplicaCount` and `maxReplicaCount` are properties of one
`ScaledObject` bound to one `scaleTargetRef`, so whatever floor is set applies
to every stream that Deployment consumes. A Worker that scales `jobs:index` to
zero overnight necessarily scales `jobs:notify` to zero with it, and
`jobs:notify` carries the Worker's only user-facing latency contract — under 5
seconds p95 (doc 05 §8) — which a cold start from zero replicas cannot meet.

Building the chart's KEDA integration (this task) forced the question, because
the `ScaledObject` template needed a concrete shape before it could be written.
It also surfaced a second, independent error in the same section: doc 05
named `pendingEntriesCount` as the metric to scale on. That metric counts
entries a consumer has *read* and not yet acknowledged. With zero running
pods, nothing is reading, so `pendingEntriesCount` never leaves zero — a pool
scaled to zero on that metric can never wake itself back up. `lagCount`, which
counts entries the consumer group has not yet read at all, is the only Redis
Streams metric KEDA's `redis-streams` scaler can use to scale from zero, and
it requires Redis 7+ (the platform is pinned to Redis 8, so this is not a
constraint in practice).

## Decision

**The Worker runs as two pools, split on latency, not on the CPU/IO axis the
design doc first suggested.** `notify` consumes only `jobs:notify` and keeps a
floor of one replica, so it is never woken from a cold start when a
notification job arrives. `batch` consumes the remaining four streams
(`jobs:index`, `jobs:thumbnail`, `jobs:export`, `jobs:retention`) and scales
from zero, since none of them carry a user-facing latency contract and idle
cost matters more than warm-start latency for those.

Each pool is its own `Deployment` and its own `ScaledObject`, sharing the same
container image, ConfigMap and Secret — only `WORKER_STREAMS` and the scaling
bounds differ per pool. Each `ScaledObject` carries one `redis-streams`
trigger per stream in its pool, scaling on **`lagCount`** rather than
`pendingEntriesCount`, correcting the error in doc 05 §5.3 at the same time
this ADR settles D17. A shared `TriggerAuthentication` supplies the R3
credential from the Worker's own secret, so KEDA holds no credential the
Worker doesn't already have.

The split is deliberately on latency rather than resource shape. A CPU/IO
split (thumbnail/export vs. index/notify) does not address the actual
constraint, which is that `jobs:notify` cannot tolerate scaling to zero while
its neighbors can. Nothing prevents `batch` from being split further along a
CPU/IO axis later — doing so needs only another pool definition, not a code
change, since pools are already a `range` over `values.yaml`.

## Consequences

The chart now has a hard dependency on KEDA: `templates/worker/scaledobject.yaml`
fails the render with an explicit error if the cluster has no
`keda.sh/v1alpha1` API, rather than silently deploying a Worker that never
scales. Operators who don't want to run KEDA can set
`components.worker.autoscaling.enabled=false`, which reverts every pool to a
plain `Deployment` with `replicaCount` replicas and renders no KEDA objects at
all — but then no pool scales with load, including to zero, so that path is
an escape hatch for a KEDA-less cluster rather than encouraged either way.

`lagCount` only means anything relative to a consumer group's read position,
and **the Worker does not create its consumer groups yet.** That is a silent
gap today, not an erroring one: checked against KEDA v2.20.1's
`redis_streams_scaler.go` (the `lagFactor` path), a missing stream returns lag
`0` with no error, and a missing group on an existing stream returns `XLEN` as
the lag, also with no error. `fallback.replicas: 1` never engages for either
case — its real job is covering Redis being unreachable or the trigger's auth
failing. The actual risk is sequencing: if a producer starts writing to a
stream before the Worker creates that stream's consumer group, KEDA reads the
growing `XLEN` as lag and scales the pool to its max, and nothing drains it
because no consumer is reading — a `batch` pool pinned at 10 replicas, not
held gracefully at one. Whoever adds consumer-group creation to the Worker
must create each stream's group (`XGROUP CREATE <stream> worker 0 MKSTREAM`,
from ID `0`) before, or in the same slice as, the first producer for that
stream — never after.

Two pools sharing one image means two rollouts on every deploy instead of one,
and two sets of pod logs/metrics to correlate instead of one — a small
operational cost against the alternative of a `notify` target that silently
regresses after any idle period.

## Alternatives Considered

### One pool, floor of one replica, no scale-to-zero

Keeps a single Deployment and a single `ScaledObject`, with `minReplicaCount:
1` protecting the notify latency target. Rejected because it pays the idle
cost of at least one running pod for the entire Worker fleet at all times,
even though four of the five streams (`index`, `thumbnail`, `export`,
`retention`) have no latency contract and would benefit from scaling to zero
during quiet periods. It also does nothing to fix the `pendingEntriesCount`
error, since a floor of one sidesteps the wake-from-zero problem rather than
solving it.

### One pool, scales to zero

Lets every stream scale to zero, minimizing idle cost. Rejected outright: it
lets `jobs:notify` scale to zero along with everything else, so a
notification arriving after an idle period pays a cold-start Deployment
scale-up before the first message is even read, which cannot meet the < 5s
p95 target in doc 05 §8. This is the failure mode the whole decision exists
to avoid.

### CPU/IO split (thumbnail/export vs. index/notify) as doc 05 first suggested

Splits pools by resource profile instead of latency sensitivity. Rejected
because it doesn't address the actual constraint: `jobs:notify` would still
share a pool and a scaling floor with `jobs:index`, so the pool carrying
`notify` would still need to choose between a floor (defeating scale-to-zero
for `index`) or scaling to zero (missing the notify target). The latency
split solves the real problem directly; a CPU/IO split remains available as a
follow-up inside `batch`, where it doesn't conflict with any latency
requirement.
