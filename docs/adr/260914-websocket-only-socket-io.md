# Socket.IO runs WebSocket-only, with no long-polling fallback

- **Status:** Accepted
- **Date:** 2026-09-14

## Context

Register entry **D30** — never previously given an ID — surfaced while shaping
the Helm chart's scaling and network-policy work (`docs/plans/ch07/01-helm-scaling-and-network-policy-design.md`).
The chart's Messaging and Canvas Services carried `sessionAffinity: ClientIP`,
justified in both `values.yaml` and their `service.yaml` templates by the same
comment: Socket.IO falls back to HTTP long-polling by default, and a polling
session's requests must all land on the same pod for the handshake to survive.
The Redis real-time backplane (R2) lets any pod serve any room once a
connection exists, but it does not rescue a polling session split across two
pods mid-handshake — hence the affinity.

That affinity does not do what the comment says it does. This chart deploys no
Ingress (`docs/design/00-platform-conventions.md`, repo layout); routing is a
per-environment decision, and every realistic environment for this app fronts
the cluster with an L7 proxy that routes straight to pod endpoints — an
ingress controller (`ingress-nginx` is the example used throughout this ADR)
or a Gateway API implementation. `ClusterIP` `Service.spec.sessionAffinity` is
a kube-proxy feature: it pins a *client IP* to a *backend pod* at the iptables/
IPVS layer that kube-proxy programs. None of these proxies route through
kube-proxy's Service VIP at all — each discovers pod IPs from `EndpointSlices`
and load-balances directly to them, so `sessionAffinity` on the Service is
simply never consulted for their traffic. Even in the
hypothetical where something upstream did honor it, every request would be
attributed to the ingress controller's own pod IP rather than the browser's,
so every client would collapse onto whichever single backend pod the
controller happened to send its first request to. The field was, in short,
decoration: present in the chart, doing nothing for the traffic it exists to
protect.

Two real fixes exist for a service that actually needs polling to work behind
an ingress. Cookie-based affinity configured on the ingress
(`nginx.ingress.kubernetes.io/affinity: cookie`) works because it operates at
the layer that actually proxies the traffic. Removing the need for affinity by
refusing polling altogether also works, and is simpler: it deletes both the
Service-level lie and the ingress-level machinery an operator would otherwise
need to remember to configure correctly, in every environment, forever.

## Decision

**Socket.IO connections are WebSocket-only.** The Messaging server's
`build_server` passes `transports=["websocket"]` to `socketio.AsyncServer`, so
a long-polling handshake is refused by the server rather than served. The SPA's
`connect()` in `src/frontend/src/lib/realtime/socket.ts` passes
`transports: ['websocket']` to `socket.io-client`, so the browser never offers
polling as an option in the first place — the client-side change exists
because without it, a browser blocked from upgrading to WebSocket would retry
against a server that has already said no, turning a clean refusal into a
confusing sequence of 400s.

Because no client ever depends on polling, no pod-affinity requirement exists
for it to protect, so the chart's Services carry no `sessionAffinity` at all —
not `ClientIP`, not a cookie-based scheme at the ingress. Doc
`00-platform-conventions.md` §6 and doc `02-messaging-service.md` §3.2 record
the rule at the point a server is built; this ADR is the cross-cutting record,
and **Canvas must apply the same `transports=["websocket"]` constraint when its
own Socket.IO server is built**, since it was named in the same affinity
comment for the same reason.

## Consequences

The chart is simpler and no longer makes a promise it cannot keep: no
`sessionAffinity` field anywhere in `values.yaml` or the Service templates,
and no ingress-annotation dependency for realtime traffic to behave correctly.
A later task adding NetworkPolicy or KEDA scaling to these components does not
need to reason about pod stickiness for Messaging or Canvas at all.

**Clients on networks that block or fail to upgrade WebSocket connections
cannot connect.** Some corporate proxies and older intermediaries interfere
with the WebSocket upgrade handshake; Socket.IO's long-polling fallback existed
specifically to serve that minority of clients. Accepting this decision means
accepting that those clients get a hard failure rather than a degraded-but-working
connection. Nothing in this decision affects REST traffic, which never used
Socket.IO transports and was never protected by the affinity in the first
place.

Canvas's Socket.IO server does not exist yet at the time of this decision; the
constraint is written into the register and the conventions doc so the
service is built WebSocket-only from its first commit rather than needing a
follow-up correction once it ships with the old default.

## Alternatives Considered

### Cookie affinity configured at the ingress

`nginx.ingress.kubernetes.io/affinity: cookie` genuinely works, unlike
Service-level `ClientIP` affinity, because it operates in the component that
actually proxies the traffic. It was rejected because it lives entirely
outside this chart — the chart deploys no Ingress by design (routing is
per-environment) — so the fix would be an annotation an operator must
remember to add correctly in every environment, forever, with no chart-level
enforcement and no test that could catch its absence. It also does nothing to
fix the misleading `sessionAffinity: ClientIP` already sitting in the chart,
which would keep implying a protection it does not provide.

### `ClientIP` affinity in the chart only, left as-is

The status quo. Rejected because it is actively misleading: it looks like a
safeguard, costs nothing to leave in place, and protects nothing once traffic
arrives through `ingress-nginx` rather than being sent straight to the
Service's `ClusterIP`. A comment explaining a mechanism that does not work is
worse than no comment, because it survives review as if it were doing its
job.

### Keep long-polling but require the environment to route Socket.IO paths outside the ingress

Sending realtime traffic to the Service directly — bypassing the ingress —
would let `ClientIP` affinity work as documented. Rejected as a much larger
change than the problem justifies: it requires a second, non-standard traffic
path per environment, for every realtime service, purely to keep a fallback
transport that WebSocket-capable clients never use anyway.
