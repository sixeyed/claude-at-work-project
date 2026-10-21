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
**Settled 2026-09-14:** message search is built — the Worker writes a `messages`
index from `jobs:index`, and `GET /search/messages` treats it as a candidate list
hydrated from Postgres (D8c stays 🟡, now built against).
[ADR](../adr/260914-message-search-index-is-a-candidate-list.md). It opened
**D29, a reindex path, 🔴** — see *Worker*.
**Settled 2026-09-14:** D17 — the Worker runs as two KEDA-scaled pools split on
latency — and D30 — Socket.IO is WebSocket-only, which is what lets the Helm chart
carry no session affinity.
**Settled 2026-09-15:** D31 — read state follows channel *visibility*, not
membership, in a `channel_reads` table with a forward-only marker.
[ADR](../adr/260915-read-state-follows-channel-visibility.md).
**Settled 2026-09-15:** D32 — a test pyramid: unit tests for every rule, integration tests for
each service's boundary against testcontainers, BDD for key journeys only.
[ADR](../adr/260915-a-test-pyramid-with-journeys-at-the-top.md).
**Settled 2026-09-15:** D34 — integration tests share one container per store per
session, with a database per service and a Redis index per role.
[ADR](../adr/260915-integration-tests-share-one-container-per-store.md).
**Settled 2026-09-16:** D40 — CollabHub deploys to any environment from one set
of images, identified by `APP_ORIGIN` and `NAMESPACE`.
[ADR](../adr/260916-per-environment-values-and-an-opt-in-ingress.md).
**Settled 2026-09-16:** D41 — `charts/collabhub-deps` serves any environment, and
every credential it renders is required, with no default.
[ADR](../adr/260916-per-environment-values-and-an-opt-in-ingress.md).
**Settled 2026-09-16:** D42 — the lab's refresh cookie drops `Secure`, because the
lab is plain HTTP; nowhere else does.
[ADR](../adr/260916-per-environment-values-and-an-opt-in-ingress.md).
**Settled 2026-10-21:** D28 — per-user preferences are Auth's, one `user_preferences` row per user; and
D46 — display names are unique across CollabHub, deleted accounts included.
[ADR](../adr/261021-user-preferences-in-auth.md), [ADR](../adr/261021-display-names-unique-across-collabhub.md).
**Settled 2026-10-15:** D45 — preview environments: a k3d namespace per branch, public on
two cloudflared quick tunnels; Messaging's Socket.IO origin list is always set by the chart.
[ADR](../adr/261015-preview-environments-on-quick-tunnels.md).

**Settled 2026-10-02:** D15 — no virus scan; the content-type allow-list (no SVG) is the
mitigation — and D43 — attachment downloads follow message visibility, minted through
Messaging, and a send claims its files before the message exists.
[ADR](../adr/261002-attachment-downloads-follow-message-visibility.md).

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
| D36 | May a workspace `admin` grant or remove the `owner` role, or only an `owner`? (raised 2026-09-15 by the test-gaps review; doc 01 said only "Bearer (admin)") | 🟢 **Decided (2026-09-15):** yes — `owner` and `admin` both manage membership, including granting and removing `owner` | Matches what `MANAGING_ROLES` already allowed; the last-owner 409 still applies. A `guest` or `member` may not manage. Pinned by Auth's member integration tests ([plan 07](../plans/ch07/07-test-gaps-backfill-implementation-plan.md)) | Auth |
| D46 | Are display names unique, and across what? (raised 2026-10-21, issue gh-5) | 🟢 **Decided (2026-10-21):** yes — across all of CollabHub, ignoring case and Unicode form, **deleted accounts included**. Compared by `users.display_name_key` (`NFC(NFD(name).casefold())`, computed by the application in `auth.names`) under the unique index `uq_users_display_name_key`; a name is trimmed and NFC-normalised, 1–100 code points, with control, format, private-use, unassigned and default-ignorable characters refused. A first sign-in whose name is taken takes `X 2`, `X 3` …; migration `0002` renamed existing duplicates the same way, oldest keeps the name | A deliberate exception to the 404 rule (Conv §5.4): a taken name's 409 reveals that the name exists somewhere, in some workspace — and names nobody and no workspace. Confusables (Cyrillic `а` for `a`) are not handled. Full case folding is wider than SQL `lower()` (`ß` = `SS`). Wrote the key column rather than a `lower(display_name)` index so app and database compare one way. See [ADR 261021](../adr/261021-display-names-unique-across-collabhub.md) | Auth, Frontend |

## Messaging

| ID | Decision | Default in docs | Recommendation | Scope |
|----|----------|-----------------|----------------|-------|
| D8a | Threading depth | 🟢 Single-level, built 2026-10-02 | A reply to a reply is filed under the root. Replies are kept out of channel history, unread and search; a root carries `replyCount`/`lastReplyAt`. See [ADR 261002](../adr/261002-single-level-threads.md) | Messaging |
| D8b | DM modelling | 🟢 `kind='dm'` channels, **built 2026-10-05** | A DM's `name` is the pair key `dm:{low}:{high}`, unique per workspace by the partial index `ux_channels_dm_pair`; `POST /channels/dm` get-or-creates it (200 either way); both people are `member`, nobody `admin`; `GET /channels` lists it once it has a top-level message; the first send emits `channel_added` to both members' personal rooms. `POST /channels` still refuses `kind='dm'`. See the [ADR](../adr/261005-direct-messages-are-dm-channels.md) and doc 02 §3.1 | Messaging |
| D8c | `/search/messages` lives in Messaging vs. a dedicated search gateway | 🟡 Thin proxy in Messaging | Revisit if search grows. **Built against it 2026-09-14:** `GET /api/v1/search/messages` is a thin proxy in Messaging over the `messages` index the Worker writes from `jobs:index`. Visibility is filtered per request and results are hydrated from Postgres, so the index is never the authority — see the [ADR](../adr/260914-message-search-index-is-a-candidate-list.md) and doc 02 §3.1.6. **Built against it 2026-10-02 (SPA):** the search box, `/search` and the jump consume `GET /api/v1/search/messages` unchanged; the jump pages history back on the client (doc 06 §5.4, [ADR](../adr/261002-jump-to-a-search-result-by-paging-back.md)). | Messaging |
| D8d | Edit/delete semantics and tombstone retention | 🟢 **Decided 2026-08-16** — see below | [ADR](../adr/260816-message-edit-and-delete-semantics.md) | Messaging + Worker |
| D31 | Read state: where the marker lives, what counts as unread, who is told (raised 2026-09-15; the docs gave a column and "counts are derived") | 🟢 **Decided (2026-09-15):** a `channel_reads` table gated on channel *visibility*, not membership; the marker only moves forward; unread = messages after it that someone else wrote and nobody deleted; `read_receipt_updated` goes only to the reader's own room `user:{workspaceId}:{userId}` | `channel_members.last_read_id` is dropped. The count is exact and uncapped — revisit if sidebar load gets slow. See [ADR 260915](../adr/260915-read-state-follows-channel-visibility.md) and doc 02 §3.1.7 | Messaging |
| D39 | Reactions: which emoji, how they are written, and how they reach a client (raised 2026-09-16 — the feature had **no register entry at all**: doc 02 named it in the endpoint table, the DTO and the DDL, and nothing implemented it) | 🟢 **Decided (2026-09-16):** a fixed server-owned allowlist of six shortcodes; written over REST only (`POST`/`DELETE /messages/{id}/reactions`), never the socket; aggregated onto the `Message` DTO as `{emoji, count, reacted}` by one grouped query per page; broadcast as `reaction_changed` carrying the authoritative count | Counts without user ids — a "who reacted" list needs its own privacy decision first. The composite key `(message_id, user_id, emoji)` is the concurrency control, so there is no `version` and no `deleted_at`. The DTO is now caller-dependent, which is why the event carries facts rather than a `Message`. See [ADR 260916](../adr/260916-message-reactions.md) and doc 02 §3.1.5 | Messaging |

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
outlives a user pressing "delete" until D16 says otherwise. **Attachments add to that
(2026-10-02):** unsent `pending` assets, a deleted message's `message_attachments` rows and
its blobs in Garage all accumulate, and nothing sweeps any of them.

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
| D13 | Avatars/exports in shared bucket vs. dedicated buckets | 🔴 Open | — **Built against it 2026-10-02:** attachments use the one bucket `collabhub-assets`; nothing here decides avatars or exports | Asset |
| D14 | How Worker reports generated variants back | 🟢 **Decided (2026-07-27):** internal endpoint `POST /api/v1/internal/assets/{id}/variants`, authenticated with an Auth-issued service token | See [ADR 260727](../adr/260727-service-tokens-for-internal-calls.md) | Cross-cutting (Asset, Worker) |
| D15 | Virus/malware scan before marking `ready` | 🟢 **Decided (2026-10-02):** no scan | The mitigation is the allow-list: PNG, JPEG, GIF, WebP and PDF only, **no SVG** (it runs script when opened), a constant in `asset/rules.py` and not a setting. A scan would add a state between `pending` and `ready`. See doc 04 §3 | Asset |
| D43 | Who authorizes an attachment download, and how a send gets its files (raised 2026-10-02 by issue 4) | 🟢 **Decided (2026-10-02):** Messaging, through `GET /messages/{id}/attachments/{assetId}/download-url`, for anyone who can see the message; Asset has no public download route. A send **claims** its assets from Asset (all or none) before inserting the message | Visibility has one implementation. A send with files depends on Asset and Auth being reachable (503 otherwise, nothing saved). See [ADR 261002](../adr/261002-attachment-downloads-follow-message-visibility.md), doc 02 §3.1.3–4 and doc 04 §3 | Cross-cutting (Messaging, Asset) |
| D15b | Azure phase: direct Blob SDK vs. S3-compat layer | 🟡 S3-compat | Keep S3-compat behind the `ObjectStore` protocol | Asset |

## Worker

| ID | Decision | Default in docs | Recommendation | Scope |
|----|----------|-----------------|----------------|-------|
| D16 | Retention policy values (message days, pending-asset hours, etc.) | 🔴 Open | Set concrete numbers. **No longer blocked on D8d** — that settled 2026-08-16 with no edit or delete window and tombstones retained in history, so retention and edit semantics are independent of each other. Nothing in the messaging core depends on a value: `POST /internal/messages/sweep` is not built and no retention job exists. **But a delete currently keeps the message text in the row**, redacting only on the way out — so this is the decision that governs when text is actually destroyed | Worker (+ Messaging) |
| D17 | Specialised worker pools vs. one deployment for all streams | 🟢 **Decided (2026-09-14):** two pools split on latency — `notify` (`jobs:notify`, floor of 1, **off until its handler exists**) and `batch` (`jobs:index` today, other streams as their handlers ship; scales from 0) | One Deployment cannot both scale to zero and hold a notify floor. KEDA scales each pool on `lagCount`; the doc's `pendingEntriesCount` could never wake a pool from zero. A CPU/IO split inside `batch` remains possible. See [ADR 260914](../adr/260914-worker-pools-split-on-latency.md) | Worker |
| D18 | Notification channels in v1 | 🔴 Open | In-app first; push/email later | Worker |
| D19 | Canvas export rendering engine (headless renderer / server-side Yjs via `pycrdt` + skia) | 🔴 Open | Non-trivial; consider deferring | Worker |
| D25 | How the Worker gets the data its handlers need | 🟢 **Decided (2026-07-27):** producers put what they already hold into the job payload; anything else is fetched from the owning service's internal endpoint with a service token. No database connection, and retention inverts to a per-service internal sweep endpoint | Index jobs need a monotonic version for Elasticsearch external versioning; `messages.version` is it. **Built against it 2026-09-14:** the `jobs:index` producer (Messaging) and consumer (Worker) exist, and delete jobs carry `body: ""`. See [ADR 260727](../adr/260727-worker-never-reads-service-databases.md) | Cross-cutting (Worker, Messaging, Canvas, Asset, Auth) |
| D29 | Reindex / backfill path for search (raised 2026-09-14) | 🔴 Open | Needed before search can be trusted after an R3 outage: enqueue is fire-and-forget (Conventions §7), so a job lost between commit and `XADD` leaves the index wrong until something rebuilds it. Likely a Messaging internal endpoint that pages messages, plus a `reindex` job type into a fresh `messages-v2` behind the alias (doc 05 §4). Not a correctness risk for *visibility* — results are hydrated from Postgres — only for recall | Worker + Messaging |

## Frontend SPA

| ID | Decision | Default in docs | Recommendation | Scope |
|----|----------|-----------------|----------------|-------|
| D20 | React Native vs. PWA for mobile | 🔴 Open | Drives how much of `/lib` is platform-agnostic | Frontend |
| D21 | Canvas renderer: Konva vs. PixiJS/WebGL vs. custom | 🔴 Open | Driven by expected document complexity | Frontend |
| D22 | Refresh-token storage: HttpOnly cookie vs. in-app secure storage | 🟢 **Decided (2026-07-28):** `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` cookie. The token never appears in a body, so `/auth/refresh` takes no body at all. CORS now allows credentials | See [ADR 260728](../adr/260728-refresh-token-in-an-httponly-cookie.md). `SameSite=Strict` closes CSRF without a second token — at the cost of requiring the SPA and API to be **same-site**. Cross-site would need `SameSite=None` plus double-submit | Frontend (+ Auth) |
| D23 | Typed REST clients: generated from OpenAPI vs. hand-written | 🟡 Generated | Implemented for Messaging (2026-08-15): `python -m messaging.openapi` writes `src/frontend/openapi/messaging.json`, `npm run generate:api` turns it into types, `openapi-fetch` provides the client. Generating from a committed file rather than a live service keeps `npm run build` free of a running stack. Asset's types are generated the same way; **Auth has no `openapi` module and its types are hand-written** in `src/frontend/src/lib/auth/api.ts` (doc 06 §2) | Frontend |
| D24 | Client state manager: Zustand vs. Redux Toolkit | 🟢 **Decided (2026-08-15):** TanStack Query owns server state, Zustand owns client state. The register framed this as one question; it is two, and the split is the decision | Server state never goes in the Zustand store — query keys carry the workspace id so a switch cannot serve another workspace's cache. See [ADR 260815](../adr/260815-tanstack-query-and-zustand-for-spa-state.md) | Frontend |
| D26 | SPA styling: Tailwind vs. CSS Modules (doc 06 §2 left it as "team choice"; never had an ID) | 🟢 **Decided (2026-08-15):** Tailwind CSS v4 via `@tailwindcss/vite` | No config files — the theme is `@theme` tokens in `index.css`. See [ADR 260815](../adr/260815-tailwind-v4-for-spa-styling.md) | Frontend |
| D27 | How acceptance criteria are expressed and run (not previously registered) | 🟢 **Decided (2026-08-15):** Gherkin + pytest-bdd + Playwright (sync API), against `docker compose up` | Selectors are `data-testid` only and live in page objects. See [ADR 260815](../adr/260815-pytest-bdd-and-playwright-for-acceptance-tests.md) Narrowed by D32 (2026-09-15) to key user journeys. | Cross-cutting (Frontend, testing) |
| D28 | Where per-user preferences live — **no feature for them exists at all** (raised 2026-08-15) | 🟢 **Decided (2026-10-21, issue gh-5):** Auth owns them — a `user_preferences(user_id, prefs jsonb, version, updated_at)` row per user, created on first write, read and merged through `GET`/`PATCH /users/me/preferences` with server-validated keys. They are per user, not per workspace; the SPA holds them in TanStack Query only (D24); the display name stays on `users`. The first preference is `clock` (`12h`/`24h`, absent = the browser's locale) | Built 2026-10-21. The merge is one SQL statement, so two tabs' different keys both survive. Both PATCH routes use `require_user` and fail open when R1 is down (they are not in Conv §5.2's set). Still open and unbuilt: a theme (the palette is light-only), a locale, notification settings (D18) — each is one more validated key. See [ADR 261021](../adr/261021-user-preferences-in-auth.md). **Built against it before the decision (2026-08-16):** six messaging slices shipped a light-only palette and stored no per-user choice | Cross-cutting (Auth, Frontend, Worker) |
| D30 | Socket.IO transport: WebSocket with long-polling fallback vs. WebSocket only (raised 2026-09-14; never had an ID) | 🟢 **Decided (2026-09-14):** WebSocket only, refused by the server as well as not offered by the client | Long-polling needs every request of a session on one pod. `sessionAffinity: ClientIP` is bypassed by ingress-nginx, and would see only the controller's IP if it were not, so the chart carries no affinity at all. Cost: networks that block WebSockets cannot connect. See [ADR 260914](../adr/260914-websocket-only-socket-io.md) | Cross-cutting (Messaging, Canvas, Frontend, chart) |
| D40 | How CollabHub is deployed to more than one environment (raised 2026-09-16: only k3d could be deployed — the origin was a constant, `values-k3d.yaml` was hardwired, and the frontend image was built for one origin) | 🟢 **Decided (2026-09-16):** `APP_ORIGIN` and `NAMESPACE` identify an instance and are never written into values; `DEPLOY_ENV` selects `values-<env>.yaml`; the SPA is built same-origin, so one image serves every environment; `charts/collabhub` has an opt-in Ingress whose public-prefix allow-list is in the template | Several instances can share a cluster. `/api/v1/internal/` staying unrouted is now the chart's job, checked at lint time. See [ADR 260916](../adr/260916-per-environment-values-and-an-opt-in-ingress.md) | Cross-cutting (chart, scripts, Frontend) |
| D41 | Where an environment's data stores, IdP and Secrets come from when the cluster provides none (raised 2026-09-16: the lab has only an ingress controller, and `charts/collabhub-local` refused anything but k3d) | 🟢 **Decided (2026-09-16):** `charts/collabhub-local` becomes `charts/collabhub-deps`, for any environment. No credential has a default; each is a required scalar supplied by a values file or `--set-string`. Dev-only is a property of `values-k3d.yaml`, not the chart | Safer than before: the chart cannot render with throwaway credentials by accident. Still not production — no backups, Dex's password DB, Secrets rendered from values rather than a secret store. See [ADR 260916](../adr/260916-per-environment-values-and-an-opt-in-ingress.md) | Cross-cutting (charts, scripts) |
| D42 | Whether the refresh cookie may drop `Secure` in an environment served over plain HTTP (raised 2026-09-16: the lab is `http://` on a real hostname, where browsers discard a `Secure` cookie) | 🟢 **Decided (2026-09-16):** yes, in the lab only — `AUTH_COOKIE_SECURE: "false"` in `charts/collabhub/values-lab.yaml` | The refresh token — thirty days — then travels in clear. Acceptable on a trusted lab network and nowhere else; any environment reachable from outside one needs TLS. k3d instances on `*.localhost` keep `Secure`, which browsers accept there. Related: D22 | Auth (+ chart) |
| D45 | How a branch is shown to someone outside the developer's network (raised 2026-10-15, issue 6) | 🟢 **Decided (2026-10-15):** `scripts/deploy.sh preview up` deploys the branch into `preview-<slug>` on k3d, public on two cloudflared quick tunnels (app and object storage); the chart sets Messaging's `CORS_ALLOWED_ORIGINS` to `[APP_ORIGIN]` in every environment | New tunnels mean new URLs and a new issuer, so users sign in again; data is kept. A preview is https and keeps `Secure` (D42 untouched). Anyone with the URL can sign in as the demo users — accepted. Builds on D40, D41, D22. See [ADR 261015](../adr/261015-preview-environments-on-quick-tunnels.md) | Cross-cutting (scripts, charts) |
| D44 | Whether Messaging checks a `userId` against Auth when a member is added to a channel or a DM is opened (raised 2026-10-05, issue 5) | 🟡 **Not checked.** `channels.add_member` and `dms.open_dm` take the id as given; Messaging owns no user records and must not read Auth's tables | A membership row for an id that names no one is inert: every read filters on the caller's own `wsp` claim. A DM opened with such an id is a channel nobody else can see. Checking it is an Auth call from Messaging on a write path, which nobody has decided to add. See the [ADR](../adr/261005-direct-messages-are-dm-channels.md) | Messaging |
| D37 | What the SPA does when a REST call returns 401: a token revoked before it expires (raised 2026-09-15 by the test-gaps review; doc 06 says renewal is scheduled ahead of expiry and "not reactive on a 401", and nothing else) | 🔴 Open. Today the `ProblemError` is shown in a banner and the user stays "signed in" with a dead token | Recommendation: try one renewal, retry the call once, and sign out if that fails. Needs single-flight renewal, which landed with [plan 07](../plans/ch07/07-test-gaps-backfill-implementation-plan.md) | Frontend |
| D38 | Whether a renewal that fails with a network error (no response at all) signs the user out (raised 2026-09-15 by the test-gaps review) | 🔴 Open. `session.ts` signs out on every failure, including `restore()` at page load while Auth is down | Doc 06 §4.5 gives rotation as the reason to sign out, but a request that never reached Auth spent nothing — though a lost *response* may have. Tied to cross-tab renewal, which is also unsolved | Frontend (+ Auth) |
| D32 | Test strategy: what each layer is for (raised 2026-09-15; the docs listed four layers and no rule for choosing between them) | 🟢 **Decided (2026-09-15):** a test pyramid — unit tests for all functionality, integration tests for each service's public boundary against dependencies testcontainers starts, BDD for key user journeys only | The directory decides the layer (`tests/unit/`, `tests/integration/`), enforced by the `testkit` pytest plugin, which also cuts unit tests off from the network and Docker. Rules become pure functions; nothing fakes a repository. Contract tests fold into unit; the SPA gets Vitest. The BDD suite is the `e2e` layer of `scripts/test.sh` (in `all`, not the default), which brings the test stack up with `--wait`, runs it and tears it down; that needed a Compose healthcheck on `frontend`, probing `/` as the chart's probes do ([plan D](../plans/ch07/06-test-pyramid-e2e-script-and-triage-implementation-plan.md)). See [ADR 260915](../adr/260915-a-test-pyramid-with-journeys-at-the-top.md) and [the design](../plans/ch07/01-test-pyramid-design.md) | Cross-cutting (every service, Frontend, testing) |
| D34 | Integration test infrastructure: how many containers, where the fixtures live, how the stores are separated (raised 2026-09-15 by the integration handoff) | 🟢 **Decided (2026-09-15):** one container per store per test session, registered once from the `testkit` plugin; a database per service on one Postgres; a database index per Redis role (R1 `/0`, R2 `/1`, R3 `/2`); Elasticsearch started only on request | A unit test depending on a container fixture stops the run. Pub/Sub is not index-scoped, so R2 is checked by connection. Garage landed with attachments (2026-10-02): a `garage_server` fixture, bootstrapped by the real `garage-bootstrap.py`. Messaging's search tests seed the index with the Worker's own mapping and handlers through `testkit.search`. See [ADR 260915](../adr/260915-integration-tests-share-one-container-per-store.md) and [plan 05](../plans/ch07/05-test-pyramid-integration-framework-implementation-plan.md) | Cross-cutting (every service, testing) |

---

## Notes
- "Default in docs" means the source doc already assumes this and built around it; changing it
  means editing that doc.
- Items marked 🟡 are safe to proceed on for early scaffolding; the 🔴 items mostly affect
  later-stage work (mobile path, exports, search breadth) and can be deferred without blocking
  a first build of the core services.
