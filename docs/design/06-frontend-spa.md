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
    /settings     # the Settings page: display name, clock preference (register D28, D46)
  /stores          # Zustand — client state only (register D24)
  /components      # shared UI
  /types           # generated DTO types (register D23) — never hand-edited
```

**Corrected 2026-08-16.** There is no `/src/app`: the router and the providers
are `App.tsx` and `main.tsx` at the root of `/src`, which is small enough not to
need a folder of its own. `/features/canvas`, `/features/presence`,
`/features/assets` and `/lib/yjs` are the eventual shape and do not exist yet.
`/features/threads` exists as of 2026-10-02 (§5.2, *Threads*).

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

   The only things the SPA persists are two `sessionStorage` entries, for the seconds between
   redirecting to the provider and returning. The PKCE verifier is single-use, useless without
   the matching authorization code, and cleared before that code is spent. **The return path**
   (`collabhub.returnTo`, added 2026-10-21) is the route a signed-out visitor asked for: a path
   only, no secret. `Protected` passes it to `/sign-in`, `signIn(provider, returnTo)` stores it
   only if it is a safe same-origin path (not `//host`, `/\host`, `/sign-in` or `/auth/…`), and
   `/auth/callback` navigates to `takeReturnPath()` — the stored path once, else `/`. It applies
   to every protected route.
5. An Axios/fetch interceptor attaches `Authorization: Bearer`. Renewal is **ahead of expiry
   on a timer**, not reactive on a 401: waiting for a failure means every call site needs
   retry logic, whereas renewing early means they only ever see a valid token. Rotation makes
   a failed renewal non-retryable, so it signs the user out rather than looping.

   Rotation also means two requests carrying the same cookie look like theft, and the server
   revokes the session. So **within one tab, spending the cookie is single-flight**: callers
   that ask for a renewal while one is in flight share it, and a workspace switch waits for
   any renewal in flight to settle (a renewal that starts during a switch shares the switch).
   **Cross-tab coordination is not handled yet** — two tabs of the same session hold the same
   rotating cookie, and a renewal in each at once still spends it twice.
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

Cross-workspace views (an all-workspaces unread badge) cannot be served by a single token
and are out of scope until a dedicated aggregate endpoint exists. **Search is one
workspace — the token's — as of 2026-10-02** (§5.4); a *unified* search across workspaces
still needs an aggregate endpoint.

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
- Debounce `typing`.

**Read state — added 2026-10-02.** What the SPA does with the server's read marker
(register D31; the polling choice is in `docs/adr/261002-unread-state-polls-rather-than-pushes.md`):

- **When a channel counts as read.** The open channel's page is visible **and** the
  window is focused **and** its list is measured within 80px of the bottom
  (`STICK_THRESHOLD`, `<`, not `≤`). The bottom is measured — after a scroll and after
  any programmatic scroll — never assumed.
- **Target.** The newest non-pending loaded message, the user's own and tombstones
  included. A `temp:` send is never a target.
- **Throttle and timing.** `mark_read` over the socket, per channel, leading and trailing:
  the first read goes at once and opens a 1 s window; reads inside it are held, the latest
  kept, and sent when it ends, which opens the next. A window opens only when something
  was emitted. Leaving a channel (or unmounting) sends a held read at once; changing the
  socket or the workspace drops it. No queue and no retry: a read not sent is not sent
  later by itself, and the forward-only marker makes the next one cover it. Each emit has a
  5 s ack timeout.
- **Local write and hold.** As it emits, the SPA writes `lastReadId` and `unreadCount: 0`
  into the channel list and detail caches, never moving a marker back, and holds that
  write against any fetch that began earlier until the ack, an error ack, or the timeout. Leaving a channel does not release it; a
  socket change does, because the socket library answers each pending ack with an error.
- **Polling.** The channel list refetches every 30 s while the tab is visible, once on
  return to the tab or window, on every socket connect, and on every channel switch.
- **Receipts.** The user's own `read_receipt_updated` writes the caches when it covers the
  newest cached message, and refetches the list otherwise. Another user's is ignored.
- **The divider.** A "New messages" separator sits above the first message after the
  marker, by someone else, not deleted, among those that existed when the channel was
  opened. It is captured once per visit, after the channel detail and the history have both
  settled, then pinned for the visit. It waits for the older page that holds the marker.
- **One mount per channel.** `ChannelView` keys `MessageList` by channel, so each channel is
  a fresh mount: it starts at its newest message, takes its own divider and flushes its own
  pending read as it unmounts.

**Direct messages — added 2026-10-05** (register D8b, doc 02 §3.1.2):

- **The sidebar** has a *Direct messages* section under the channels (`DirectMessageList`).
  `ChannelList` shows `kind !== 'dm'` rows only and never reads the directory. DM rows are
  `NavLink`s named after the other person, in name order (`localeCompare`), with the channel
  list's count pill and bold name; the one being read shows no count.
- **Naming.** A DM is named after `dmPartnerId`, resolved through the workspace directory
  (`shortId` while unknown — the directory refetches once for an id it lacks; see *Names*) — never the stored pair key. `channelLabel` is the bare name
  (`general`, or the person's name) for `data-channel-name`, `data-dm-name` and the header;
  `channelTitle` adds the `#` for a channel only, for the composer's `Message …` and a search
  result. The header shows no `#`, topic or controls for a DM, and `ChannelView` no member panel.
- **The picker.** The **+** opens everyone in the workspace but the caller, by display name
  (sorted; an assumption, one line to change). Picking `POST`s `/channels/dm` and navigates to the
  channel it returns. The mutation records the workspace it started in and navigates only if that
  is still current, invalidating only that workspace's list key.
- **`channel_added { channelId }`** invalidates the channel list, which cancels a fetch in flight
  when the list has data. With no data yet, TanStack joins the first load rather than cancelling
  it, and that load may predate the message — so the handler invalidates again when it settles.
- **Badge.** A pill (`99+` above 99) and a bold name for a channel with unread messages,
  hidden on the open channel only while it is being read (`readingChannelId`, client state).

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
  **Since 2026-10-02 the refetch waits for an older-page fetch in flight** (`refetchHistory`),
  then refetches everything loaded: a refetch that cancelled the page fetch lost the page.
  **Corrected 2026-09-15: the refetch waits for the join's acknowledgement**, on a
  reconnect and on entering a channel alike. The server enters the room only after
  authorizing the join, so a refetch sent alongside it could finish first, and a
  message sent in between reached neither the history nor the room — seen as an
  intermittent failure in the live-delivery journeys. `join_channel` is emitted
  with an ack; on `ok` the store's `joinedChannelId` is set (rendered as
  `data-joined-channel`, which the acceptance suite waits on) and the channel is
  refetched. A disconnect or leaving the channel clears it.
  **And an event that arrives while that history is being fetched is applied again
  when the fetch lands.** A resolving fetch replaces the cached pages with what it
  read, which predates the event — so without the re-apply, a message broadcast
  during a load or refetch disappeared until a reload.
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
  puts the text back in `drafts[channelId]` and the files back among the chips (§6), and
  says why. `send_message` carries no idempotency key, so an automatic retry is how one
  message becomes two — and a send that *was* saved has claimed its files, so the retry
  is refused anyway. The timeout's wording is therefore "The server did not confirm that
  message — it may still arrive.", not "Nothing was sent."
- **Everything a send writes keys on the send's own channel** — `variables.channelId`,
  never the hook's `channelId` argument. TanStack takes the observer's new options when
  the component re-renders, so a closure over the channel the hook was rendered for cleans
  up the wrong cache once the user has moved to another channel mid-send. The restore is in
  the hook-level `onError` for the same family of reasons: Query keeps one `mutate`-level
  callback, the latest call's, so a per-call `onError` misses an earlier send when a later
  one is in flight.
- **A refusal is per channel** (`sendErrors[channelId]`): it shows in the composer it came
  from, not in another, comes back when the user returns, and is cleared when the next send
  *for that channel* starts.
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

**Names — added 2026-10-15.** The directory is one query per workspace, stale
after 5 minutes. An id it doesn't hold refetches it once, joining a fetch already
in flight (`cancelRefetch: false` — TanStack's default cancels and restarts it);
the short id shows meanwhile. An id seen before a fetch that lands without it is
*departed* and asks for nothing more until a fetch for another reason lands (a
mount, a window focus, a reconnect — a reconnect counts even when it joins the
tracker's own fetch; a stale mount or focus refetch that joins one does not).
Every socket connect refetches the directory. **Renames are not pushed to other people**: a
changed name shows at the next refetch after the 5 minutes are up (a mount, a
window focus, a reconnect, or an unknown id). Code: `features/channels/directoryRefresh.ts`.

**Names — the renamer's own tab updates at once (added 2026-10-21).** On a successful rename
(`features/settings/useProfile.ts`), `applyRename` writes the new name into the session profile,
the cached `['me', id]` and every cached workspace directory, so the sidebar and the user's own
messages agree immediately. It runs from the mutation's own `onSuccess`, so leaving Settings
mid-save still renames. In order and synchronously it cancels directory and profile reads in
flight (their answers are discarded), writes, then invalidates every cached directory so each is
re-read after the commit. A renewal or switch whose `GET /users/me` was answered before the
rename keeps the session's profile (`updateProfile` in `session.ts`); a read begun after it is
adopted as it is. The `name` claim in the access token stays stale for up to its life.

**Threads — added 2026-10-02** (register D8a, ADR 261002). Single-level; the code
is in `/features/threads`.

- **The panel** is `<aside aria-label="Thread">`, 20rem wide, in the channel's
  right column **in place of** the member panel. It shows the root, the replies
  oldest first, then a composer, and never touches the channel's read state.
- **The URL owns it**: `?thread=<rootId>`. Opening pushes (Back steps A → B → none);
  closing replaces and deletes only `thread`, so `?message=` survives and Back does
  not reopen it. Switching channel drops it; a channel that 404s renders no panel.
- **The cache**: one infinite query per root at
  `['messages', ws, channelId, 'thread', rootId]`, nested under the channel's
  history key. The join ack refetches history by its exact key (§5.4) and then
  invalidates `['messages', ws, channelId, 'thread']`, which refetches an open
  thread. Each page carries the root and its slice of replies.
- **Event routing** by `threadRootId`: a reply goes to its thread's cache and
  never into history; a top-level event goes to history and replaces the root in
  its own thread entry. History takes a **new** row only from `message_received`
  and its own sends — edits, deletes, summaries and the panel's results use
  `replaceMessage`, which adds nothing. `thread_summary_changed` *sets*
  `replyCount`/`lastReplyAt`, never adds, and — like every live event — is applied
  again when a history or thread fetch in flight resolves, since that fetch may have read
  the root before the reply; a reply's send makes no optimistic
  count bump.
- **Scroll**: older replies load at `scrollTop < 120` and hold position by the
  height added; a new reply sticks to the bottom when it is yours or when the
  reader was within 80px of it, measured before the render.
- **Drafts**: `threadDrafts[rootId]` in the store, apart from the channel's.
- **A thread that is not there** (no data and an error, or a root from another
  channel) shows "This thread isn't available."; a failed refetch over loaded data
  keeps showing the thread.

### 5.4 Search — added 2026-10-02

Over `GET /api/v1/search/messages` (doc 02, D8c), unchanged.

- **The box** is the first thing in the sidebar (`role="search"`). Enter submits the trimmed
  text (at most 200 characters) to `/search?q=…` from any route; blank submits nothing. It
  shows the query on `/search` and is empty elsewhere. Submitting the query already on screen
  refetches it and adds no history entry.
- **The results route** `/search` is protected and inside the shell. The cache key is
  `['search', workspaceId, q]`, so a workspace switch reads a different entry. Results are
  newest first as served, plain text, no match highlighting; "Load more" follows `nextCursor`
  (a short page with a cursor still has a next page). The list is a snapshot: focus and
  reconnect refetches are off, and a return to the page shows the cached list then refetches
  it. A failed first fetch shows the problem with Retry; a failed later page keeps the list.
  A blank `q` fetches nothing. Channel names come from the channel list, and from the channel
  detail (once per channel) for channels outside it, `#…` while unknown. A result in a direct
  message shows the other person's name, with no `#` (`channelTitle`, §5.2).
- **A result is a link** to `/c/<channelId>?message=<id>`. **The jump** lives in
  `MessageList` (`useMessageJump`): it decides only while history is idle, pages back with
  `fetchNextPage({ cancelRefetch: false })` up to **10 loaded pages in total**, centres the
  target and highlights it for 2 s (`data-highlighted="true"` on the `message-item`), then
  removes the parameter with `replace`. At the cap, or when history runs out, it shows the
  newest messages with "That message is too far back to show." A failed fetch ends it with
  the list's own error. Leaving the channel or navigating the parameter away abandons it; a
  different target restarts it (latest wins).
- **Exception to the read rule:** while a jump runs nothing is marked read and a new message
  does not pull the list to the bottom; a read held by the throttle when the jump starts is
  sent at once, and reading resumes when the highlight ends.
- **Page fetches never cancel a refetch, and a refetch never cancels a page fetch** (§5.2).

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
5. Render through a URL **Messaging** mints —
   `GET /messages/{id}/attachments/{assetId}/download-url` (register D43; Asset has no public
   download route). `thumbnail-url` is not built.

**Message attachments — built 2026-10 (issue 4).**

- **Attach by the paperclip, a drop or a paste.** Each file becomes a *chip* (client state,
  Zustand, keyed by channel) that uploads while the person keeps typing. The runner
  (`features/attachments/uploads.ts`) is plain async code **outside React**, so a channel
  switch cannot stop it and the finished upload lands in the chips of the channel it began in.
- **Rules are checked before anything is requested**, in the server's words: PNG, JPEG, GIF,
  WebP or PDF (no SVG), 1 byte to 50 MB, a name of 1–255 characters. A file that breaks one
  becomes a `failed` chip saying why, counts towards ten until removed, and is never uploaded.
- **All or none for a batch.** A batch that would take the message past ten adds nothing and
  says "At most 10 files per message — 3 attached, 8 added."
- **Paste.** A clipboard with text and a file (Excel, Word) pastes the text and attaches
  nothing; files and no text attach. Only the browser's generic `image.png` is renamed
  `Pasted image <yyyy-mm-dd hh.mm.ss>.png`, in local time.
- **Send waits for every chip to be `ready`**, and for there to be no more than ten; a message
  may be only files. The chips leave with the send and come back if it is refused, **in front
  of** anything attached since, even past ten — then Send is off and the composer says "At most
  10 files per message — remove 1." Nothing a person chose is dropped. Restored text goes in
  front of what was typed since, joined by one line break.
- **✕** on a chip cancels its upload (an `AbortController` per upload, checked before each of
  the three steps and passed to each request) and removes it. A workspace switch, or the shell
  unmounting on sign-out, cancels every upload and empties every channel's chips: a token is
  scoped to one workspace. The asset stays `pending` in Asset (register D16).
- **Showing a message's files.** Images inline, capped at 240 × 320 px; PDFs as a chip with
  the name, the size and a Download button. Name, type and size are the message's own, so a
  chip renders with no request and still does when Asset is down. A message still pending
  (`temp:` id) shows the chips' metadata and fetches no URL; a tombstone shows nothing.
- **A URL is stale at 780 s** (it lives 900 s), and staleness matters at three moments only: a
  **mount** that finds it stale refetches and shows no `src` until the new one lands; a
  **click** uses the cached URL only if it is fresh; an `<img>` that fails to load refetches
  **once**, then offers "Couldn't load — retry". A *mounted* image keeps its URL — the query
  refetches on no focus, no reconnect and no interval.
- **A click opens the window synchronously**, then sends it to the URL once a fresh one has
  arrived (`window.open` after an `await` loses its user activation in Safari and is
  blocked). A PDF navigates the page to a URL signed `Content-Disposition: attachment`, which
  downloads and leaves the page where it is.

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
  all. Attachment count and size are untouched by this and stay as written — and built as
  written (§6): a *file's* type, size and name are checked before an upload starts, because
  there the answer is not a send to roll back but a chip that says why.
- PWA/offline shell for the mobile path; service worker caches the app shell, not data.

## 9. Open Decisions
- **User preferences — decided 2026-10-21 (register D28), built for the clock.** They are
  Auth's: `user_preferences`, `GET`/`PATCH /users/me/preferences` (doc 01 §3–4), per user and
  not per workspace. The SPA holds them in TanStack Query only (`features/settings`);
  `ChatLayout` provides the clock to the three places a time is shown (`MessageItem`,
  `ThreadSummary`, `SearchResult`) through `ClockContext`, so a choice re-renders cached
  messages without refetching them. The Settings page (`/settings`, inside the chat shell,
  reached from your name in the sidebar) offers Automatic / 12-hour / 24-hour and reads the
  profile and preferences from the server on every visit. A theme toggle, a locale and
  notification settings (Worker D18) are each one more validated key — none is built, and the
  palette is still light-only.
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
