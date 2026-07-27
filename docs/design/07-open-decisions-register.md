# CollabHub — Open Decisions Register

> Consolidated list of every decision left open across the design docs, with the default
> currently baked into each doc and a recommendation where one exists. Use this as a living
> register — update **Status** as decisions are made and reflect them back into the source doc.

**Status legend:** 🔴 Open · 🟡 Leaning (default in docs) · 🟢 Decided
**Scope:** *Cross-cutting* = affects more than one component; resolve these first.

---

## Resolve First (cross-cutting)

These span service boundaries; deciding them keeps the individual docs consistent with each
other. Details in the tables below (IDs in brackets).

**Settled 2026-07-27:** D1, D2, D9 and D14 are now 🟢 and safe to build against.

- 🟢 **Auth revocation model** [D1] — check-with-fail-open, except a named set of sensitive
  operations that fail closed. Conventions §5.2 updated.
- 🟢 **Multi-workspace tenancy** [D2] — many-to-many membership, one workspace per access
  token, switch via refresh exchange.
  [ADR](../adr/260727-single-active-workspace-per-token.md)
- 🟢 **Canvas state storage** [D9] — `bytea`, no derived JSONB.
- 🟢 **Worker result write-back** [D14] — internal endpoint plus service token.
  [ADR](../adr/260727-service-tokens-for-internal-calls.md)
- 🔴 **Canvas search in Elasticsearch** [D12/D17] — still open. Requires Canvas to emit a text
  projection the Worker indexes. Touches Canvas + Worker.

---

## Platform / Auth

| ID | Decision | Default in docs | Recommendation | Scope |
|----|----------|-----------------|----------------|-------|
| D1 | Do all services consult the Redis denylist on every request, or rely only on short token lifetime? | 🟢 **Decided (2026-07-27):** check-with-fail-open for ordinary requests; a named set of sensitive operations fails **closed** (503) when R1 is unreachable | Sensitive set: workspace member changes, role grants, asset deletion. Conv §5.2 updated | Cross-cutting |
| D2 | Single active workspace per token, or multiple with a switch flow? | 🟢 **Decided (2026-07-27):** many-to-many membership; each access token scoped to one workspace via `wsp`; switch by exchanging the refresh token | See [ADR 260727](../adr/260727-single-active-workspace-per-token.md) | Cross-cutting (Conv, Auth) |
| D3 | Primary-key type | 🟡 UUID v7 | Keep unless there's a reason for bigint/ULID | Cross-cutting |
| D4 | Schema-per-service vs database-per-service in production | 🟡 Logically separate DBs | On-prem may co-locate; doesn't change app code | Cross-cutting |
| D5 | Auth acts as full OIDC OP for first-party clients, or only federates to an upstream IdP? | 🔴 Open | — | Auth |
| D6 | SAML federation in v1 or deferred? | 🔴 Open | Defer unless an enterprise customer needs it day one | Auth |
| D7 | Refresh tokens stored hashed in Postgres vs. in Redis (R1) | 🟡 Postgres (hashed) | Postgres for durability | Auth |

## Messaging

| ID | Decision | Default in docs | Recommendation | Scope |
|----|----------|-----------------|----------------|-------|
| D8a | Threading depth | 🟡 Single-level | Confirm against UX needs | Messaging |
| D8b | DM modelling | 🟡 `kind='dm'` channels | — | Messaging |
| D8c | `/search/messages` lives in Messaging vs. a dedicated search gateway | 🟡 Thin proxy in Messaging | Revisit if search grows | Messaging |
| D8d | Edit/delete windows and tombstone retention | 🔴 Open | Align with Worker retention (D16) | Messaging + Worker |

## Canvas

| ID | Decision | Default in docs | Recommendation | Scope |
|----|----------|-----------------|----------------|-------|
| D9 | Yjs state column type | 🟢 **Decided (2026-07-27):** `bytea`. The derived-JSONB option is dropped — Canvas is a relay and never interprets document structure | Any text projection for search (D12) is a separate derived artefact, not a column-type change | Cross-cutting (Canvas, Worker) |
| D10 | Storage strategy: snapshot-only vs. snapshot + append log | 🟡 Append log mentioned | Recommend snapshot + append log (durability between snapshots) | Canvas |
| D11 | Server-side Yjs (`pycrdt` y-crdt binding) vs. trust a debounced client full-state push | 🔴 Open | Server-side binding if crash-correctness matters | Canvas |
| D12 | Index canvas content in Elasticsearch? | 🔴 Open | Needs a Canvas → text projection; ties to D17 | Cross-cutting (Canvas, Worker) |

## Asset

| ID | Decision | Default in docs | Recommendation | Scope |
|----|----------|-----------------|----------------|-------|
| D13 | Avatars/exports in shared bucket vs. dedicated buckets | 🔴 Open | — | Asset |
| D14 | How Worker reports generated variants back | 🟢 **Decided (2026-07-27):** internal endpoint `POST /api/v1/internal/assets/{id}/variants`, authenticated with an Auth-issued service token | See [ADR 260727](../adr/260727-service-tokens-for-internal-calls.md) | Cross-cutting (Asset, Worker) |
| D15 | Virus/malware scan before marking `ready` | 🔴 Open | Add a scan hook if uploads are user-shared | Asset |
| D15b | Azure phase: direct Blob SDK vs. S3-compat layer | 🟡 S3-compat | Keep S3-compat behind the `ObjectStore` protocol | Asset |

## Worker

| ID | Decision | Default in docs | Recommendation | Scope |
|----|----------|-----------------|----------------|-------|
| D16 | Retention policy values (message days, pending-asset hours, etc.) | 🔴 Open | Set concrete numbers; coordinate with D8d | Worker (+ Messaging) |
| D17 | Specialised worker pools vs. one deployment for all streams | 🟡 Single, split suggested | Split CPU-heavy (thumbnail/export) from IO-heavy (index/notify) | Worker |
| D18 | Notification channels in v1 | 🔴 Open | In-app first; push/email later | Worker |
| D19 | Canvas export rendering engine (headless renderer / server-side Yjs via `pycrdt` + skia) | 🔴 Open | Non-trivial; consider deferring | Worker |

## Frontend SPA

| ID | Decision | Default in docs | Recommendation | Scope |
|----|----------|-----------------|----------------|-------|
| D20 | React Native vs. PWA for mobile | 🔴 Open | Drives how much of `/lib` is platform-agnostic | Frontend |
| D21 | Canvas renderer: Konva vs. PixiJS/WebGL vs. custom | 🔴 Open | Driven by expected document complexity | Frontend |
| D22 | Refresh-token storage: HttpOnly cookie vs. in-app secure storage | 🔴 Open | HttpOnly cookie if same-site allows; avoid localStorage | Frontend (+ Auth) |
| D23 | Typed REST clients: generated from OpenAPI vs. hand-written | 🟡 Generated suggested | Generate from each service's OpenAPI | Frontend |
| D24 | Client state manager: Zustand vs. Redux Toolkit | 🔴 Open | — | Frontend |

---

## Notes
- "Default in docs" means the source doc already assumes this and built around it; changing it
  means editing that doc.
- Items marked 🟡 are safe to proceed on for early scaffolding; the 🔴 items mostly affect
  later-stage work (mobile path, exports, search breadth) and can be deferred without blocking
  a first build of the core services.
