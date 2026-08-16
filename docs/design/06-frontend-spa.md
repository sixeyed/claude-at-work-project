# CollabHub — Frontend SPA

> React + TypeScript single-page app: chat, collaborative canvas, presence.
> Read [Platform Conventions](./00-platform-conventions.md) first.

**Status:** Draft · **Stack:** React + TypeScript (Vite) · React Native / PWA path for mobile
**Talks to:** Auth, Messaging, Canvas, Asset services (REST + Socket.IO), Garage (direct uploads)

---

## 1. Purpose & Responsibilities

The single client application. Combines a Slack-like chat experience and a Figma-like
collaborative canvas in one app. Communicates over **REST** for standard CRUD and **Socket.IO**
for all real-time interactions; runs the **Yjs CRDT** locally for the canvas (the backend is a
relay — Canvas doc §1).

**Owns:** all UI, client-side CRDT state, optimistic updates, presence rendering, the OIDC
login flow (PKCE), and direct-to-Garage uploads.
**Does NOT own:** merge conflict resolution beyond what Yjs provides; any persistence
(everything authoritative lives server-side).

---

## 2. Tech & Key Libraries

| Concern | Choice | Notes |
|---------|--------|-------|
| Framework | React 19 + TypeScript | |
| Build | Vite | Fast dev, PWA plugin for the mobile path. |
| Routing | React Router | |
| Server state / data fetching | **TanStack Query** | 🟢 Decided 2026-08-15 (D24). Owns *all* server state — no channel or message list is copied into the client store. Query keys carry the workspace id, so a workspace switch cannot serve the previous workspace's cache. [ADR](../adr/260815-tanstack-query-and-zustand-for-spa-state.md) |
| Client/UI state | **Zustand** | 🟢 Decided 2026-08-15 (D24). Client state only: active channel, connection status, per-channel drafts. |
| Real-time | `socket.io-client` | Two connections: messaging (`/messaging`) + canvas (`/canvas`). |
| CRDT | `yjs` + a Socket.IO provider (custom, see §5.3) | Canvas document state. |
| Canvas rendering | `react-konva` / `pixi.js` / custom WebGL | Pick per perf needs (Open Decision). |
| Auth | *(no library — hand-written)* | See below. |
| Forms / validation | React Hook Form + Zod | Zod schemas mirror `collabhub-contracts` (Pydantic models). |
| Styling | **Tailwind CSS v4** | 🟢 Decided 2026-08-15 (D26), via `@tailwindcss/vite`. No `tailwind.config.js` or PostCSS config — the theme is `@theme` tokens in `src/index.css`. **Light palette only** — there is no user-preferences feature to store a theme choice in (§9), so following the OS setting would mean maintaining two schemes for a setting nobody can override. Components use tokens (`text-ink-muted`), never literal colours; that is what keeps adding a dark palette cheap later. [ADR](../adr/260815-tailwind-v4-for-spa-styling.md) |
| Acceptance tests | **Gherkin + pytest-bdd + Playwright** | 🟢 Decided 2026-08-15 (D27). Run against `docker compose up`. Selectors are `data-testid` only and live in page objects — a step definition never holds one. [ADR](../adr/260815-pytest-bdd-and-playwright-for-acceptance-tests.md) |

**No OIDC library.** Earlier drafts named `oidc-client-ts`; it was not used, and the reason is
structural rather than a preference. That library assumes the *browser* is the OIDC client
talking directly to a provider — it manages tokens in web storage, performs silent renewal
through hidden iframes, and expects to own the whole authorization-code flow.

None of that is our shape. The SPA's counterparty is CollabHub's own Auth service, which is
itself the relying party (register D5); the code the SPA exchanges is a CollabHub code, not the
provider's. And since D22 the refresh token is an `HttpOnly` cookie the SPA cannot read, so a
library whose core job is storing and renewing tokens has nothing left to store. What remains
is a PKCE verifier, one redirect and one `fetch` — about sixty lines in `/lib/auth`, and
fewer moving parts than configuring a library out of doing the things it exists to do.

---

## 3. App Structure

```
/src
  App.tsx          # routes and the auth guard
  main.tsx         # bootstrap and providers
  /lib
    /api          # typed REST clients per service (generated from OpenAPI ideally)
    /realtime     # Socket.IO connection managers (messaging, canvas)
    /auth         # PKCE, the code exchange, the session store, refresh-ahead, auth guard
    /yjs          # Yjs doc factory + Socket.IO sync provider
  /features
    /channels     # channel list, channel view, composer
    /threads
    /canvas       # document view, toolbar, layers, cursors
    /presence     # online users, live cursors, awareness
    /assets       # upload widget, image/file rendering
  /stores          # Zustand — client state only (register D24)
  /components      # shared UI
  /types           # generated DTO types (register D23) — never hand-edited
```

**Corrected 2026-08-16.** There is no `/src/app`: the router and the providers
are `App.tsx` and `main.tsx` at the root of `/src`, which is small enough not to
need a folder of its own. `/features/threads`, `/features/canvas`,
`/features/presence`, `/features/assets` and `/lib/yjs` are the eventual shape
and do not exist yet.

---

## 4. Auth Flow (OIDC + PKCE)

1. Unauthenticated → redirect to Auth service `/auth/login/{provider}`.
2. After provider callback, the SPA receives an auth code at its redirect URI.
3. SPA exchanges code + PKCE verifier at `POST /auth/token` → an access token in the body,
   plus a refresh cookie the response sets.
4. **Token storage — decided 2026-07-28 (register D22),
   [ADR](../adr/260728-refresh-token-in-an-httponly-cookie.md).** The access token lives in
   memory and dies with the tab. The refresh token is an `HttpOnly; Secure; SameSite=Strict`
   cookie scoped to `/api/v1/auth`: the SPA cannot read it, does not store it, and never
   sends it explicitly — the browser does that.

   Three consequences for this application:

   - Every `fetch` to the Auth service must set `credentials: 'include'`, or the browser
     drops the cookie on a cross-origin call and every renewal fails as though the session
     had expired.
   - Nothing in the SPA may keep a refresh token anywhere. There is no "token store" to
     write; a signed-in page holds nothing in `localStorage` or `sessionStorage` at all.
   - **The SPA and the API must be deployed same-site** — one registrable domain, or one
     origin behind a single ingress. Under `SameSite=Strict` a genuinely cross-site split
     stops the cookie being sent, and the symptom is a silent sign-out rather than an error.

   The only thing the SPA persists is the PKCE verifier, in `sessionStorage`, for the seconds
   between redirecting to the provider and returning. It is single-use, useless without the
   matching authorization code, and cleared before that code is spent.
5. An Axios/fetch interceptor attaches `Authorization: Bearer`. Renewal is **ahead of expiry
   on a timer**, not reactive on a 401: waiting for a failure means every call site needs
   retry logic, whereas renewing early means they only ever see a valid token. Rotation makes
   a failed renewal non-retryable, so it signs the user out rather than looping.
6. Socket.IO connections pass the access token in the handshake `auth` payload (per Conventions
   §6) and re-acquire it on reconnect.

### Workspace switching

Access tokens are scoped to one workspace (Conventions §5.4,
[ADR](../adr/260727-single-active-workspace-per-token.md)), so switching is a real state
transition, not a UI filter. The SPA must:

1. `POST /auth/switch-workspace` with the target workspace ID — the session comes from the
   refresh cookie, which the browser attaches and the SPA never handles.
2. Cancel in-flight requests and **clear the TanStack Query cache** — cached data belongs to
   the old workspace.
3. **Tear down and re-establish both Socket.IO connections.** A connection authenticated for
   one workspace must never keep serving another; this is the most likely source of bugs
   here and is worth an explicit test.
4. Reset Yjs documents and awareness state for any open canvas.

Cross-workspace views (unified search, an all-workspaces unread badge) cannot be served by a
single token and are out of scope until a dedicated aggregate endpoint exists.

---

## 5. Real-Time Integration

### 5.1 Connection management
Two long-lived Socket.IO connections — namespaces `/messaging` and `/canvas` — created lazily,
with automatic reconnect (Socket.IO's built-in exponential backoff). On reconnect, re-join the
rooms/documents the user was in and re-sync. A single shared "connection state" surfaces
offline/reconnecting UI.

### 5.2 Messaging
- On entering a channel: emit `join_channel`; load history via REST
  `GET /channels/{id}/messages` (cursor paginated, newest-first) and merge.
- Send via the `send_message` event; render **optimistically** with a temp id, reconcile on the
  acknowledged `Message` / `message_received`.
- Subscribe to `message_received`/`message_edited`/`message_deleted`, `reaction_changed`,
  `read_receipt_updated`, `user_typing` and update TanStack Query caches.
- Debounce `typing`; throttle `mark_read`.

**Added 2026-08-16, while building live delivery.** Four rules the bullets above
leave implicit, each of which is a bug that only shows up in a running app:

- **One socket for the shell, not one per channel view.** It is mounted where the
  layout is, so navigating between channels emits `join_channel` /
  `leave_channel` and never reconnects. A hook mounted in the channel view would
  cost a handshake, a token verification and a room join for something the user
  experiences as clicking a link.
- **Every connect re-joins *and* refetches.** Re-entering a room replays nothing
  — the server has no connection-state recovery — so everything broadcast while
  the client was away is gone. Invalidating that channel's message query is the
  recovery; the re-join only resumes the live stream from that point.
- **`connect_error` disconnects; a transport drop does not.** A handshake the
  server refused will be refused identically on every retry, so Socket.IO's
  backoff would loop forever against a service that has already said no.
  Recovery comes from the socket being re-created with a fresh token, which is
  the only thing that could change the answer — and that happens on its own,
  because the access token is the connection's dependency.
- **An inbound event for a channel with no cached history is dropped.** Writing
  into an empty infinite-query key stores whatever the updater returns, so a
  handler that built a page there would invent a one-message history with no
  cursor — and the real history would never load. Handlers key on the *event's*
  `channelId`, so a background channel that is cached still updates.

The three message events all carry the full `Message` — including
`message_deleted`, which carries the tombstone — and all three go through one
upsert helper keyed on the message id. **Idempotent, never appending:** the
sender receives its own broadcast and there is no id to skip it by, so an append
renders every message twice in its author's own window.

**Optimistic send — added 2026-08-16.** The bullet above says "reconcile on the
acknowledged `Message` / `message_received`", and the slash hides a race:
Socket.IO gives **no ordering guarantee between a broadcast and an ack**, and
the sender is in the room, so `message_received` for your own message can arrive
before your own acknowledgement does. Reconciling on the ack alone renders it
twice.

- The optimistic entry is a complete `Message`-shaped object with
  `id = "temp:<uuid>"`, so the ordinary message component renders it with no
  branch and no second component. **The `temp:` prefix is the pending marker**
  — nothing goes in the Zustand store, because a map of in-flight sends keyed by
  temp id is a second copy of the message list wearing a hat.
- **Reconciliation is remove-then-upsert**: drop the `temp:` row, then upsert
  the real message by id. Idempotent, so it does not matter which of the ack and
  the broadcast arrived first — and it is the same idempotency a reconnect
  refetch needs anyway.
- **Every emit carries a five-second ack timeout.** `emit` on a closed socket
  does not fail — it buffers, and the callback never fires — so without one the
  bubble would sit greyed forever with no error and no way out.
- **A timed-out or refused send is never retried automatically.** It rolls back,
  puts the text back in `drafts[channelId]`, and says why. `send_message`
  carries no idempotency key, so an automatic retry is how one message becomes
  two.
- **There is no offline send queue** (§7 lists one as an aspiration). It would
  need ordering, durable storage and dedupe against a write that cannot be
  deduped, and the composer is disabled with a visible reason while the socket
  is down instead. The reconnect-and-refetch path above already covers what
  matters: nothing said while you were away is lost.

**Typing** is a leading-edge throttle — one `typing` emit per 2s window, first
keystroke immediately, because a trailing debounce would delay the indicator by
its own window. There is no stop event: the receiver drops a name 4s after its
last `user_typing`. Names are resolved through the workspace directory like
every other name in the UI; the event carries only a user id.

### 5.3 Canvas (Yjs over Socket.IO)
- One `Y.Doc` per open document. A **custom Socket.IO provider** bridges Yjs ↔ the `/canvas`
  namespace:
  - On `join_document`, perform the sync handshake (`sync_step1`/`sync_step2`, Canvas doc §3.2),
    feeding the server's state into the local `Y.Doc`.
  - Local Yjs `update` events → emit `sync_update(documentId, update)`.
  - Incoming `update` → `Y.applyUpdate(doc, update)`.
  - Yjs **awareness** (cursor, selection, user color) → `awareness_update`; incoming awareness
    renders remote cursors; `peer_left` clears them.
- Initial load may also use REST `GET /documents/{id}/snapshot` to seed before the handshake
  on slow connections.
- The renderer subscribes to the `Y.Doc` and redraws on change; all editing mutates the
  `Y.Doc`, never local-only state.

---

## 6. Assets (direct upload)
1. `POST /assets/upload-url` → presigned PUT.
2. `PUT` the file bytes **directly to Garage** (show progress).
3. `POST /assets/{id}/confirm`.
4. Reference the returned `assetId` in a message (`attachments`) or canvas image node.
5. Render via `GET /assets/{id}/download-url` / `thumbnail-url` (short-lived URLs; refetch on
   expiry).

---

## 7. Cross-Cutting
- **Error handling:** parse RFC 7807 Problem Details (Conventions §4.2) into typed UI errors;
  show `errors` map on forms.
- **Offline / reconnect:** queue outgoing chat sends while disconnected; Yjs naturally
  reconciles canvas edits on reconnect.
  **Neither half is built — noted 2026-08-16.** There is no outgoing send queue:
  the composer is disabled while the socket is down, and a send that is refused
  or times out rolls back and surfaces its problem detail (§5.2). A queue would
  need ordering, durable storage and dedupe against a write with no idempotency
  key, and the reconnect-and-refetch path already covers what matters — nothing
  said while you were away is lost. Yjs reconciliation is Canvas's, and Canvas
  is scaffold.
- **Observability:** browser OTel SDK → collector; propagate `traceparent` on REST calls so
  traces stitch across SPA → service → worker.
- **Accessibility & i18n:** plan from the start (Open Decision on i18n lib).

## 8. Non-Functional & Limits
- First meaningful paint and channel-switch should feel instant (optimistic + cached).
- Canvas target 60 fps with N live cursors; throttle awareness broadcasts (~30–60 ms).
- ~~Respect server limits (message length, attachment count/size) client-side before sending.~~
  **Corrected 2026-08-16, for message length specifically.** The composer does
  **not** pre-check the body against `MESSAGING_MAX_BODY_CHARS`, and the
  textarea carries no `maxlength`. Two reasons, and the first is the one that
  generalises: a second copy of a server rule is a copy that drifts from the one
  guarding the database, which is the same call `CreateChannelDialog` makes for
  channel names. The second is that pre-validating would mean the over-long send
  never leaves the browser — no optimistic row, nothing to roll back, and the
  behaviour the rejected-send path exists to provide could not be exercised at
  all. Attachment count and size are untouched by this and stay as written.
- PWA/offline shell for the mobile path; service worker caches the app shell, not data.

## 9. Open Decisions
- **User preferences — there is no feature for them anywhere** (register D28). `users`
  carries a display name, an avatar reference and a status (doc 01 §4), and
  `PATCH /users/me` updates the first two. Nothing stores a per-user choice, so
  a theme toggle, a locale, a timezone or notification settings all need the
  same missing thing first: a place to put them, and a decision about whether
  they are Auth's (a column, in the token, cached in R1) or a separate concern.
  Currently blocking a dark mode; i18n and notification channels (Worker D18)
  will want it too.
- **React Native vs. PWA** for mobile — separate codebase vs. shared (the architecture lists
  both). Affects how much of `/lib` is platform-agnostic.
- **Canvas renderer:** Konva (DOM/2D, simpler) vs. PixiJS/WebGL (perf) vs. custom. Driven by
  expected document complexity.
- ~~**Styling:** Tailwind vs. CSS Modules.~~ — 🟢 **Decided 2026-08-15 (register D26).**
  Tailwind CSS v4. See §2 and the
  [ADR](../adr/260815-tailwind-v4-for-spa-styling.md).
- ~~**Refresh-token storage:** HttpOnly cookie vs. in-app secure storage.~~ — 🟢 **Decided
  2026-07-28 (register D22).** `HttpOnly; Secure; SameSite=Strict` cookie; the SPA stores no
  token at all. See §4 and the
  [ADR](../adr/260728-refresh-token-in-an-httponly-cookie.md).
- **Typed clients:** 🟡 generated, and now implemented for Messaging (2026-08-15).
  `python -m messaging.openapi` writes `src/frontend/openapi/messaging.json`,
  `npm run generate:api` turns it into `src/types/messaging.ts`, and
  `openapi-fetch` provides the client. Generating from a committed file rather
  than a live service keeps `npm run build` free of a running stack. The other
  services follow the same shape when they gain an API.
- ~~State manager choice (Zustand vs. Redux Toolkit).~~ — 🟢 **Decided 2026-08-15
  (register D24).** TanStack Query for server state, Zustand for client state.
  See §2 and the
  [ADR](../adr/260815-tanstack-query-and-zustand-for-spa-state.md).
