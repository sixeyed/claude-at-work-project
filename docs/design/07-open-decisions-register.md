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

**Settled 2026-07-27:** D1, D2, D9, D14 and D25 are now 🟢 and safe to build against.
**Settled 2026-07-28:** D5 and D22.
**Settled 2026-08-15:** D24, plus D26 and D27 — two choices the docs left open
without ever giving them an ID (SPA styling, and how acceptance criteria are
expressed). Both were forced by building the first messaging slice.
**Settled 2026-08-16:** D8d — message edit and delete semantics. See its row
under *Messaging* for the scope, which is narrower than the row's old title:
**retention values are still D16, and still 🔴.**

- 🟢 **Identity federation** [D5] — Auth is an OIDC *relying party*, never a provider. Dex is
  the upstream locally; a customer's own IdP elsewhere. `dev-login` is deleted.
  [ADR](../adr/260728-federate-to-an-upstream-oidc-provider.md)
- 🟢 **Refresh-token storage** [D22] — `HttpOnly; Secure; SameSite=Strict` cookie scoped to
  `/api/v1/auth`. Never in a request or response body. **Constrains deployment: the SPA and
  the API must be same-site.**
  [ADR](../adr/260728-refresh-token-in-an-httponly-cookie.md)
- 🟢 **Auth revocation model** [D1] — check-with-fail-open, except a named set of sensitive
  operations that fail closed. Conventions §5.2 updated.
- 🟢 **Multi-workspace tenancy** [D2] — many-to-many membership, one workspace per access
  token, switch via refresh exchange.
  [ADR](../adr/260727-single-active-workspace-per-token.md)
- 🟢 **Canvas state storage** [D9] — `bytea`, no derived JSONB.
- 🟢 **Worker result write-back** [D14] — internal endpoint plus service token.
  [ADR](../adr/260727-service-tokens-for-internal-calls.md)
- 🟢 **Worker data access** [D25] — job payloads carry what the producer already holds;
  anything else comes from the owning service's internal endpoint. The Worker connects to no
  service database. [ADR](../adr/260727-worker-never-reads-service-databases.md)
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
| D5 | Auth acts as full OIDC OP for first-party clients, or only federates to an upstream IdP? | 🟢 **Decided (2026-07-28):** federate only — Auth is an OIDC relying party and never a provider. Dex is the local upstream; a customer's own IdP elsewhere. Two independent PKCE exchanges (Auth↔IdP, SPA↔Auth). `dev-login` deleted, not disabled | See [ADR 260728](../adr/260728-federate-to-an-upstream-oidc-provider.md). Providers carry a public *and* an internal authority — an issuer is an identity, not an address | Auth |
| D6 | SAML federation in v1 or deferred? | 🔴 Open | Defer unless an enterprise customer needs it day one | Auth |
| D7 | Refresh tokens stored hashed in Postgres vs. in Redis (R1) | 🟡 Postgres (hashed) | Postgres for durability | Auth |

## Messaging

| ID | Decision | Default in docs | Recommendation | Scope |
|----|----------|-----------------|----------------|-------|
| D8a | Threading depth | 🟡 Single-level | Confirm against UX needs. **Built against it 2026-08-16:** `thread_root_id` ships as a column and serializes as `null`; there is no thread API and `ix_messages_thread` is not created | Messaging |
| D8b | DM modelling | 🟡 `kind='dm'` channels | **Built against it 2026-08-16:** `kind='dm'` is rejected by `CREATABLE_KINDS` in `messaging/models.py`, and nothing creates or lists a DM. The column accepts it; the API does not | Messaging |
| D8c | `/search/messages` lives in Messaging vs. a dedicated search gateway | 🟡 Thin proxy in Messaging | Revisit if search grows. **Built against it 2026-08-16:** neither exists — no `/search/messages`, and no `jobs:index` producer to feed one (doc 02 §5) | Messaging |
| D8d | Edit/delete semantics and tombstone retention | 🟢 **Decided 2026-08-16** — see below | [ADR](../adr/260816-message-edit-and-delete-semantics.md) | Messaging + Worker |

**D8d, in full.** No time window on either action. The author edits their own
message; the author or an admin of the channel deletes it — admins moderate by
deleting and no role may rewrite someone else's words. Deleted messages are
retained in history as tombstones (`body: ""`, `deletedAt` set), redacted
server-side, which is a documented exception to Conventions §3's "queries filter
`deleted_at IS NULL`".

**How long a tombstone is kept before hard deletion is D16, still 🔴.** Nothing
in this scope deletes one: the stored `body` is left intact on delete, no
retention job exists, and `POST /api/v1/internal/messages/sweep` is not built.
D8d settles the semantics of edit and delete and not the retention half of its
original title — a distinction worth keeping, because it means message text
outlives a user pressing "delete" until D16 says otherwise.

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
| D16 | Retention policy values (message days, pending-asset hours, etc.) | 🔴 Open | Set concrete numbers. **No longer blocked on D8d** — that settled 2026-08-16 with no edit or delete window and tombstones retained in history, so retention and edit semantics are independent of each other. Nothing in the messaging core depends on a value: `POST /internal/messages/sweep` is not built and no retention job exists. **But a delete currently keeps the message text in the row**, redacting only on the way out — so this is the decision that governs when text is actually destroyed | Worker (+ Messaging) |
| D17 | Specialised worker pools vs. one deployment for all streams | 🟡 Single, split suggested | Split CPU-heavy (thumbnail/export) from IO-heavy (index/notify) | Worker |
| D18 | Notification channels in v1 | 🔴 Open | In-app first; push/email later | Worker |
| D19 | Canvas export rendering engine (headless renderer / server-side Yjs via `pycrdt` + skia) | 🔴 Open | Non-trivial; consider deferring | Worker |
| D25 | How the Worker gets the data its handlers need | 🟢 **Decided (2026-07-27):** producers put what they already hold into the job payload; anything else is fetched from the owning service's internal endpoint with a service token. No database connection, and retention inverts to a per-service internal sweep endpoint | Index jobs need a monotonic version for Elasticsearch external versioning; `messages` has no `version` column yet. See [ADR 260727](../adr/260727-worker-never-reads-service-databases.md) | Cross-cutting (Worker, Messaging, Canvas, Asset, Auth) |

## Frontend SPA

| ID | Decision | Default in docs | Recommendation | Scope |
|----|----------|-----------------|----------------|-------|
| D20 | React Native vs. PWA for mobile | 🔴 Open | Drives how much of `/lib` is platform-agnostic | Frontend |
| D21 | Canvas renderer: Konva vs. PixiJS/WebGL vs. custom | 🔴 Open | Driven by expected document complexity | Frontend |
| D22 | Refresh-token storage: HttpOnly cookie vs. in-app secure storage | 🟢 **Decided (2026-07-28):** `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` cookie. The token never appears in a body, so `/auth/refresh` takes no body at all. CORS now allows credentials | See [ADR 260728](../adr/260728-refresh-token-in-an-httponly-cookie.md). `SameSite=Strict` closes CSRF without a second token — at the cost of requiring the SPA and API to be **same-site**. Cross-site would need `SameSite=None` plus double-submit | Frontend (+ Auth) |
| D23 | Typed REST clients: generated from OpenAPI vs. hand-written | 🟡 Generated | Implemented for Messaging (2026-08-15): `python -m messaging.openapi` writes `src/frontend/openapi/messaging.json`, `npm run generate:api` turns it into types, `openapi-fetch` provides the client. Generating from a committed file rather than a live service keeps `npm run build` free of a running stack | Frontend |
| D24 | Client state manager: Zustand vs. Redux Toolkit | 🟢 **Decided (2026-08-15):** TanStack Query owns server state, Zustand owns client state. The register framed this as one question; it is two, and the split is the decision | Server state never goes in the Zustand store — query keys carry the workspace id so a switch cannot serve another workspace's cache. See [ADR 260815](../adr/260815-tanstack-query-and-zustand-for-spa-state.md) | Frontend |
| D26 | SPA styling: Tailwind vs. CSS Modules (doc 06 §2 left it as "team choice"; never had an ID) | 🟢 **Decided (2026-08-15):** Tailwind CSS v4 via `@tailwindcss/vite` | No config files — the theme is `@theme` tokens in `index.css`. See [ADR 260815](../adr/260815-tailwind-v4-for-spa-styling.md) | Frontend |
| D27 | How acceptance criteria are expressed and run (not previously registered) | 🟢 **Decided (2026-08-15):** Gherkin + pytest-bdd + Playwright (sync API), against `docker compose up` | Selectors are `data-testid` only and live in page objects. See [ADR 260815](../adr/260815-pytest-bdd-and-playwright-for-acceptance-tests.md) | Cross-cutting (Frontend, testing) |
| D28 | Where per-user preferences live — **no feature for them exists at all** (raised 2026-08-15) | 🔴 Open. `users` has display name, avatar and status and nothing else; `PATCH /users/me` updates two of those | Decide whether preferences are Auth's (a `preferences jsonb` column, exposed on `/users/me`, possibly cached in R1) or a separate service, before the first thing that needs one ships. Blocking a theme toggle now; i18n and notification channels (D18) need the same thing. **Built against it 2026-08-16:** six messaging slices shipped a light-only palette and stored no per-user choice anywhere — no theme, no locale, no notification setting — so the decision is still unforced | Cross-cutting (Auth, Frontend, Worker) |

---

## Notes
- "Default in docs" means the source doc already assumes this and built around it; changing it
  means editing that doc.
- Items marked 🟡 are safe to proceed on for early scaffolding; the 🔴 items mostly affect
  later-stage work (mobile path, exports, search breadth) and can be deferred without blocking
  a first build of the core services.
