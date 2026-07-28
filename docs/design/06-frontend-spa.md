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
| Server state / data fetching | TanStack Query | Caching, mutations, optimistic updates over REST. |
| Client/UI state | Zustand (or Redux Toolkit) | Lightweight global state (current user, presence). |
| Real-time | `socket.io-client` | Two connections: messaging (`/messaging`) + canvas (`/canvas`). |
| CRDT | `yjs` + a Socket.IO provider (custom, see §5.3) | Canvas document state. |
| Canvas rendering | `react-konva` / `pixi.js` / custom WebGL | Pick per perf needs (Open Decision). |
| Auth | *(no library — hand-written)* | See below. |
| Forms / validation | React Hook Form + Zod | Zod schemas mirror `collabhub-contracts` (Pydantic models). |
| Styling | (team choice) Tailwind / CSS Modules | |

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
  /app            # bootstrap, providers, router
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
  /components      # shared UI
  /types           # shared DTO types (mirrors collabhub-contracts)
```

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
- **Observability:** browser OTel SDK → collector; propagate `traceparent` on REST calls so
  traces stitch across SPA → service → worker.
- **Accessibility & i18n:** plan from the start (Open Decision on i18n lib).

## 8. Non-Functional & Limits
- First meaningful paint and channel-switch should feel instant (optimistic + cached).
- Canvas target 60 fps with N live cursors; throttle awareness broadcasts (~30–60 ms).
- Respect server limits (message length, attachment count/size) client-side before sending.
- PWA/offline shell for the mobile path; service worker caches the app shell, not data.

## 9. Open Decisions
- **React Native vs. PWA** for mobile — separate codebase vs. shared (the architecture lists
  both). Affects how much of `/lib` is platform-agnostic.
- **Canvas renderer:** Konva (DOM/2D, simpler) vs. PixiJS/WebGL (perf) vs. custom. Driven by
  expected document complexity.
- ~~**Refresh-token storage:** HttpOnly cookie vs. in-app secure storage.~~ — 🟢 **Decided
  2026-07-28 (register D22).** `HttpOnly; Secure; SameSite=Strict` cookie; the SPA stores no
  token at all. See §4 and the
  [ADR](../adr/260728-refresh-token-in-an-httponly-cookie.md).
- **Typed clients:** generate REST clients + types from each service's OpenAPI doc vs.
  hand-write against `collabhub-contracts`. Recommend generated.
- State manager choice (Zustand vs. Redux Toolkit).
