# Slice 5 — Real-time delivery (broadcast only)

## Context

[`02-messaging-core-delivery-plan.md`](./02-messaging-core-delivery-plan.md) restructures the
messaging build into seven vertical slices. This plan covers Slice 5, and does two things: it
**validates the delivery plan against the design docs and the shipped code**, closing the gaps it
finds, and it **specifies the slice** in enough detail to build from.

Slice 5 is the socket layer and the read half of it. Writes still go over REST; the REST routers
publish to the room after commit. Nothing here is throwaway — doc 02 §3.1 keeps
`POST /channels/{id}/messages` as the permanent REST fallback, and the publishers are the same
ones Slice 6's inbound handlers will call.

**Demo:** two browser windows side by side — Ada sends, edits and deletes; Grace's window updates
without a reload.

The seams this slice shares with Slices 3, 4 and 6 are already frozen in
[`04-slice-contracts.md`](./04-slice-contracts.md), which is binding: rulings 4 and 5 give S5
`shared/security.py`, the ASGI entry point and `messaging/realtime.py`, ruling 6 gives it
`realtime.feature`, ruling 7 gives it `lib/realtime/*` and `connectionStatus`, and ruling 9 gives
it doc 02 §3.2's handshake/rooms/server→client rows and doc 06 §5.2's read half. Validation found
**eleven gaps** beyond those rulings, two of which are corrections to the design docs and two of
which are Contract questions this plan does not answer.

---

## Gaps closed

### 1. `build_server` is short by one argument — the handshake has no security context

Ruling 5 gives the signature `build_server(settings, sessions)`. That is not enough to authenticate
a handshake: `verify_user_token` takes a `SecurityContext`, and the only one in the process is
built inside `create_app` by `install_security` and hung on `app.state.security`
(`shared/security.py:87`). Ruling 4 half-notices this — it adds `SecurityContext` to
`shared/__init__.__all__` precisely because "the handshake needs the type to name what it holds" —
but the signature was not updated to carry it.

**The server is built from three things, gathered into one frozen dataclass in `realtime.py`:**

```python
@dataclass(frozen=True)
class RealtimeContext:
    settings: Settings
    sessions: async_sessionmaker[AsyncSession]
    security: SecurityContext


def build_server(context: RealtimeContext) -> socketio.AsyncServer: ...
```

`build_asgi_app` constructs the `RealtimeContext` from the FastAPI app it just built —
`app.state.settings`, `app.state.sessions`, `app.state.security` — so there is exactly one engine,
one session factory and one JWKS cache in the process, not a second set for the socket server.
This is also the object **S6's `register_write_handlers(sio, context)` takes**, so the one line
ruling 5 asks S6 to add to `build_asgi_app` has something to pass. That is a seam S6 should cite,
not a decision it needs to make.

### 2. The R2 backplane is shared with Canvas, and the default pub/sub channel is not

Doc 02 §4.1 and doc 03 §4.1 both put their Socket.IO backplane on **R2**, and Conventions §6 says
only `socketio.AsyncServer(client_manager=socketio.AsyncRedisManager(<R2 URL>))`. That constructor
defaults to `channel="socketio"`. Two services pointing two managers at one Redis with one channel
name means every Canvas emit is delivered into Messaging's server process and re-dispatched against
its rooms — `doc:{id}` will not match `channel:{id}` today, so nothing visibly breaks, which is the
worst kind of latent bug: it becomes a cross-service leak the first time either service names a
room the other could also name.

**Each service names its own channel.** Messaging constructs
`AsyncRedisManager(settings.redis_realtime_url, channel="messaging")`. R2 only — never R1
(cache and denylist), never R3 (job streams), per ruling 5.

**Write this into `docs/design/02-messaging-service.md` §3.2** as part of the namespace's
construction.

**Contract question: who fixes Conventions §6 and doc 03.** The same line belongs in Conventions §6
(which tells every service to construct the manager with a URL and nothing else) and in doc 03 §4.1
for Canvas, and ruling 9 assigns neither section to any slice — doc 02 §4.1 is unassigned too.
Recommendation: S5 writes the rule into doc 02 §3.2, which it owns, and **S7 carries the one-line
correction into Conventions §6 and doc 02 §4.1** as part of its sweep. Canvas is another chapter's
service and should be told, not edited from here.

> **Answered by ruling 19, 2026-08-15 — recommendation overturned.** **S5 owns Conventions §6 and
> doc 02 §4.1 for this correction**, not S7. CLAUDE.md records a decision in the slice that makes
> it, and this one is forced by this slice's code: two services silently sharing one pub/sub
> channel is too load-bearing to defer to a docs sweep, where it would arrive after both are
> running. Canvas's doc 03 §4.1 is still **told, not edited** — that half of the recommendation
> stands.

### 3. An empty `CORS_ALLOWED_ORIGINS` means the opposite thing to Socket.IO

Conventions §5.6 is explicit that empty is the default and **installs nothing** — a service behind
one ingress shares its SPA's origin and needs no CORS. `install_cors` honours that, and
`settings.cors_allowed_origins` defaults to `[]` (`messaging/settings.py:28`).

`socketio.AsyncServer(cors_allowed_origins=[])` means the opposite: engine.io reads an empty list
as *an allow-list containing nothing* and rejects every browser handshake with a 400. The value
that means "same origin only" is `None`.

**Pass `settings.cors_allowed_origins or None`**, with the reason in a comment. Locally the list is
populated (`docker-compose.yml` sets it on the `messaging` block, and `docker-compose.test.yml`
overrides it to the test stack's `:5183`), so the bug would only appear in the deployment the
convention was written for.

### 4. The ASGI wrapper owns the lifespan, and one keyword argument silently disables it

Ruling 4 fixes the entry point but not what happens to the FastAPI `lifespan` underneath it.
`messaging/main.py:56` disposes the engine, the Redis client and the `JwksClient` in that lifespan.
`socketio.ASGIApp` handles the `lifespan` scope itself, and only delegates it to `other_asgi_app`
when it was given **neither `on_startup` nor `on_shutdown`**.

**Construct the wrapper with `socketio.ASGIApp(sio, other_asgi_app=create_app(...))` and nothing
else.** Adding an `on_startup` there — the obvious place to reach for if the socket server ever
needs warm-up — would silently stop messaging's lifespan running, leaking a connection pool per
process with no error anywhere. Say so in the docstring, because the failure mode is invisible.

Two things the delivery plan asserts and this slice **verifies rather than assumes**:

- `/health/live` still resolves through the wrapper, so the Compose healthcheck
  (`docker-compose.yml`, `x-http-healthcheck`, which calls `urlopen('.../health/live')`) is
  unchanged. Anything that is not the engine.io path falls through to `other_asgi_app`.
- WebSocket transport actually works in the image: `messaging/pyproject.toml` already depends on
  `uvicorn[standard]`, which brings `websockets`. Without it Socket.IO silently degrades to HTTP
  long-polling, which passes every test and violates Conventions §6's "WebSockets preferred".

### 5. `message_deleted` cannot render a tombstone, and no event says how a payload is serialized

Doc 02 §3.2 gives `message_deleted` the payload `{ messageId, channelId }`. That predates ruling 1,
which makes a delete a **state transition of a row that stays in history**, with `body: ""`,
`deletedAt` set and `version` bumped. A client holding `{messageId, channelId}` cannot render "This
message was deleted" — it can only remove the row, which is exactly the behaviour ruling 1 exists
to prevent, or refetch, which defeats the point of the event.

**`message_deleted` carries the same redacted `Message` DTO that `message_edited` carries.** All
three server→client events take one payload type, and all three frontend handlers write through
the one `useMessages.ts` helper (ruling 7):

| Event | Payload | Cache effect |
|---|---|---|
| `message_received` | `Message` | upsert by `id` at the head of the newest page |
| `message_edited` | `Message` | replace by `id` |
| `message_deleted` | `Message`, redacted per ruling 1 | replace by `id` — never remove |

And the serialization, which no document states: **`MessageResponse.model_dump(mode="json",
by_alias=True)`** — the identical camelCase shape the REST route returns, `mode="json"` so
timestamps are ISO strings rather than `datetime` objects the JSON encoder would reject. The
frontend writes these straight into the TanStack cache alongside REST-loaded rows and reads them
through generated types (`components['schemas']['MessageResponse']`); two casings in one cache
entry would be a render bug per message, not a caught error.

**Write both into `docs/design/02-messaging-service.md` §3.2** — S5 owns the server→client event
table (ruling 9). S6 cites this rather than re-deciding it for its acks.

### 6. Nothing anywhere defines the ack envelope

Doc 02 §3.2 says `send_message` "returns the created `Message` via the acknowledgement callback"
and says nothing about what a *rejected* event returns, or what `join_channel` acks. Rulings 4 and
5 do not cover it. A socket handler cannot raise `ProblemException` and expect an answer — the
FastAPI exception handlers `install_problem_handlers` registers are HTTP middleware and never see
it — so every handler must catch and convert, and the shape it converts to is needed by S5
(`join_channel`, `leave_channel`) and S6 (`send_message`, `edit_message`, `delete_message`) alike.

**Contract question: the Socket.IO ack envelope.** Recommendation, which S5 builds and S6 cites
unless overturned — one envelope, defined once in `realtime.py`:

```jsonc
{ "ok": true,  "data": { /* Message, or omitted */ } }
{ "ok": false, "problem": { "type": "...", "title": "...", "status": 404, "detail": "..." } }
```

The problem object is the RFC 7807 body `ProblemException` already carries (Conventions §4.2), so
there is one error vocabulary on this platform rather than one for REST and another for sockets,
and the SPA's existing `ProblemError` can be constructed from either. `realtime.py` exports
`_ok(data=None)` and `_problem(exc: ProblemException)` and a `@_acked` decorator that wraps a
handler so a `ProblemException` becomes an error ack instead of an unhandled exception that
Socket.IO would swallow.

> **Answered by ruling 15, 2026-08-15 — accepted, with the key renamed.** S6 proposed the same
> envelope with the failure key spelled `problem`, and that spelling wins: the platform calls these
> Problem Details wherever it names them (`ProblemException`, `install_problem_handlers`,
> `problem_response`, the SPA's `ProblemError`), and reusing the word is what tells a reader the
> body is the same document a REST call would have returned. **S5 builds `_ok` / `_problem` /
> `@_acked`; S6 imports them.** Ruling 16 also moves `shared/problems.py` into this slice — see
> the note in work package B.

### 7. A handshake is verified once; the token behind it lives fifteen minutes

Conventions §5.1 gives access tokens a 15-minute life and §5.2 makes revocation a per-request
denylist check. A Socket.IO connection is checked in `connect` and then never again — doc 02 §3.2
and Conventions §6 say nothing about a connection that outlives its token, and §5.4 covers only the
workspace switch. Left alone, a revoked user keeps receiving messages until they close the tab.

**Verify at the handshake only, and bound the exposure from the client.** Specifically:

- `connect` calls `verify_user_token(context.security, token)` — **`sensitive=False`**, so an
  unreachable R1 fails open exactly as it does for `GET /channels`. Channel membership is not
  workspace membership, so none of this surface is in Conventions §5.2's fail-closed set, and doc
  02 §3.1 says so explicitly.
- The connection stores the `UserPrincipal` in the Socket.IO session and **keeps the workspace of
  the token that opened it** (Conventions §5.4). No handler re-reads a workspace from an event
  payload, for the same reason no router reads one from a path.
- The SPA tears the socket down and re-establishes it whenever the access token changes —
  `session.ts:96` renews about a minute before expiry, so in practice every connection
  re-authenticates roughly every fourteen minutes, and a workspace switch (which mints a new token)
  drops it immediately as doc 06 §4 requires.

**Mid-connection revocation is deliberately not built**, and doc 02 §3.2 should say so rather than
leave the reader to wonder: it would need either a per-emit denylist round trip on the hot path or
an R2 fan-out of revocations, and the exposure it closes is at most one token lifetime on a
connection the client re-opens on that same cadence anyway.

### 8. A rejected handshake retries forever

Doc 06 §5.1 asks for "automatic reconnect (Socket.IO's built-in exponential backoff)" and does not
distinguish a dropped transport from a **refused** one. They need opposite treatment: a dropped
WebSocket should reconnect, and a handshake the server refused because the token is expired, denied
or malformed will be refused identically on every retry — an infinite backoff loop against a
service that has already said no, and one that hides the real problem behind a spinner.

**`connect_error` stops the client.** `useChannelSocket` calls `socket.disconnect()` on
`connect_error` and sets `connectionStatus: 'disconnected'`; recovery comes from the effect
re-running with a fresh token, which is the only thing that could change the answer. Transport
drops keep Socket.IO's built-in backoff untouched.

### 9. Reconnect re-joins the room but not the history it missed

Doc 06 §5.1 says "on reconnect, re-join the rooms/documents the user was in and re-sync"; §5.2
describes the initial history load and the live events, and nothing bridges them. Every message
broadcast while the client was disconnected went to a room it was not in and is simply gone —
python-socketio has no equivalent of the Node server's connection-state recovery, so re-joining a
room replays nothing.

This is not a theoretical hole: **the slice's own scenario "the stream recovers after the
connection drops" cannot pass without closing it**, because the scenario drops Grace's network,
has Ada send, and expects Grace to see the message when the network returns.

**Every `connect` — first or subsequent — does both: re-emit `join_channel` for the active
channel, then invalidate that channel's message query.** The refetch is the recovery mechanism;
the re-join only resumes the live stream from that point. One line, and it is the difference
between a scenario that passes and one that passes only when the timing is lucky.

### 10. A socket handler can fabricate a history that was never loaded

Ruling 7 calls the infinite-query cache "the seam most likely to be got wrong twice", and there is a
second way to get it wrong that it does not name. `queryClient.setQueryData(key, updater)` on a key
with **no cached data** hands the updater `undefined` and then stores whatever it returns. A handler
that builds a fresh `{ pages: [[message]], pageParams: [null] }` there has invented a complete
history containing one message and no `nextCursor` — and the next time the user opens that channel,
TanStack Query serves that cache entry as fresh and the rest of the history never loads.

**Every inbound handler no-ops when there is no cached entry for the event's channel.** The handler
returns the previous value untouched when it is `undefined`; a channel the user has not opened has
nothing to update, and the history it eventually loads comes from REST with the message already in
it. Handlers key on **the event's `channelId`**, not the active one, so a background channel that
*is* cached stays correct.

**Contract question: the S3 helper must be an upsert, not an append.** Ruling 7 assigns
`useMessages.ts`'s insert/replace/remove helper to S3 and describes it as inserting. In this slice
the sender's own client posts over REST *and* receives its own `message_received` from the room —
the publisher has no `sid` to skip, because a REST request is not a socket — so a blind append
renders Ada's message twice in Ada's window. Recommendation: S3 exports `upsertMessage` (idempotent
on `id`) and `removeMessage`; S5 calls `upsertMessage` for all three events and asserts the
single-copy case in the Gherkin. If S3 ships an append, S5 makes it an upsert — one line, in S3's
file, and it is a bug either way.

> **Answered by ruling 17, 2026-08-15 — accepted, and ruling 7 amended to match.** S3's plan
> already replaces in place on a matching id and only inserts otherwise, so nothing in S3 changes;
> the ruling exists so a later reader cannot mistake the insert for a blind append. `upsertMessage`
> and `removeMessage` are the names.

### 11. The reconnect scenario would leave every later scenario offline

Ruling 6 puts the network drop on the page object as `go_offline()` / `go_online()` wrapping
`self.page.context.set_offline(...)`, which is right — the Playwright API belongs behind the page
object like every selector. But `set_offline` is **context-wide**, and the contexts are
session-scoped (`tests/bdd/conftest.py:209-216`): `grace_context` is signed in once and shared by
every scenario's `grace` fixture. A scenario that fails or errors between `go_offline()` and
`go_online()` leaves Grace's context offline for the rest of the session, and every subsequent
scenario fails somewhere unrelated with no clue why. This is the same class of harness bug as gap 8
in Slice 1's plan — an isolation mechanism that damages state it does not own.

**The `ada` and `grace` fixtures restore the network on teardown**, next to the `page.close()` they
already do:

```python
@pytest.fixture
def grace(grace_context: BrowserContext, base_url: str) -> Iterator[ChatPage]:
    page = grace_context.new_page()
    yield ChatPage(page, base_url)
    # go_offline() is context-wide and the context outlives the scenario, so a
    # scenario that fails while offline would take every later one with it.
    grace_context.set_offline(False)
    page.close()
```

Teardown rather than an autouse fixture, because an autouse fixture that requested both contexts
would sign both users in for every single-user scenario.

### Also corrected in the delivery plan

- **The scenario title "Grace does not receive messages for a channel she has not joined" now means
  two things.** After ruling 12, *joining* is an administrative act that grants nothing on the read
  path — Grace can read and post in a public channel with no membership row — while `join_channel`
  over the socket is a room subscription. The scenario is about the room. Reword it at the gate to
  say what it tests: **"Grace does not receive messages for a channel she is not looking at"**. The
  behaviour is unchanged; the title is the only thing that would mislead a reader.
- **`python-socketio` needs its client extra for the tests.** The delivery plan notes the dependency
  is absent from `uv.lock` but not that `socketio.AsyncSimpleClient` pulls a different dependency
  set: `python-socketio[asyncio_client]` brings `aiohttp`, which engine.io's async client uses for
  both polling and WebSocket transports. The server needs the plain package; the test client does
  not work without the extra.
- **The frontend dependency is missing from the delivery plan's Slice 5 paragraph.**
  `socket.io-client` is not in `src/frontend/package.json`; the strategy plan lists it and the
  delivery plan's frontend bullet assumes it. `socket.io-client` v4 is the protocol match for
  `python-socketio` 5.x.
- **The feature folder is `features/channels/`** (ruling 7, doc 06 §3). The delivery plan's Slice 5
  paragraph still says `features/chat`.
- **`.env.example` needs no new variable.** The socket reuses `VITE_MESSAGING_URL` and
  `REDIS_REALTIME_URL`, both already there and both already passed to the containers.

---

## How the slice runs

Unchanged from the delivery plan. Six reminders:

1. **Gherkin first** — `tests/bdd/features/realtime.feature`, scenarios only, no steps, no page
   objects, no service code.
2. 🛑 **Stop and wait for explicit approval.** Expect rounds of revision.
3. Build **outside-in** and watch the scenarios fail for the right reason first.
4. **Never edit a scenario to fit the implementation.**
5. **`data-testid` only**, owned by page objects — no raw locator in a step definition.
6. Branch `feature/messaging-s5-realtime`. **Never commit** — leave the tree dirty.

**Scenarios** (per the delivery plan, with the rewording above): Grace sees Ada's message without
reloading · Ada's edit propagates to Grace live · Ada's delete propagates to Grace live · Grace does
not receive messages for a channel she is not looking at · the stream recovers after the connection
drops.

Everything about the handshake itself stays at **integration level, never in Gherkin**: an absent,
expired, malformed or service-audience token being refused, the `access_token` query fallback, room
isolation between two connected sockets, and the publisher's no-op when `app.state.realtime` is
`None`. A browser cannot be made to present a malformed token without lying about what the app does.

---

## Work

### A. BDD — `tests/bdd/`

- `features/realtime.feature` — new file, the five scenarios above. Written and approved at the
  gate (step 1), not here. `scenarios("../features/realtime.feature")` is called from exactly one
  module (ruling 6).
- `steps/test_realtime_steps.py` — new. Named `test_*` or pytest never collects it and the feature
  silently never runs (ruling 6). Mirrors `steps/test_channel_steps.py` exactly: `pytestmark =
  pytest.mark.bdd`, `scenarios(...)` at module top, `given`/`when`/`then` grouped with the same
  comment banners, every assertion through a `ChatPage` method. **Synchronous throughout** — root
  `pytest.ini` sets `asyncio_mode = "auto"`, so an `async def` step is collected as an asyncio test
  and Playwright's sync API cannot run inside a live loop.
- `pages/chat_page.py` — new methods only; no second page object for the chat shell (ruling 6).
  `go_offline()` / `go_online()` wrapping `self.page.context.set_offline(...)` per ruling 6, and
  waits that are *events, not sleeps*: `expect(...).to_have_text(...)` on the message row keyed by
  id, so "without reloading" is proved by the assertion passing on a page nobody navigated. The
  message-row selectors themselves are S3's; S5 adds only what the live scenarios need.
- `conftest.py` — the two-line teardown from gap 11 in the `ada` and `grace` fixtures. **Nothing
  else in this file changes**: `MESSAGING_TABLES` is S3's (ruling 6), no slice adds a session-scoped
  fixture that signs a third user in, and Auth's tables are never truncated.

### B. `shared` — the request-free verification core, and the request-free problem body

**Ruling 16 (2026-08-15) adds `shared/problems.py` to this package.** S6 raised it and claimed it;
ownership came here instead, because this slice needs it first — `join_channel` has to refuse a
channel before S6 exists — and because one slice touching `src/services/shared/` means one review
of the one library every service depends on.

- `src/services/shared/shared/problems.py` — extract
  `problem_body(problem: ProblemException, *, instance: str | None = None, trace_id: str | None = None) -> dict[str, Any]`
  from `problem_response` (`problems.py:124`), and rewrite `problem_response` to call it and wrap
  the result in a `JSONResponse`. One problem-document builder, so a socket ack and a REST 404
  cannot describe the same refusal differently. Export it from `shared/__init__.py` — the import
  block **and** `__all__`, which is sorted.
  **The trace id has no `Request` to come from inside a socket handler.** Rule it explicitly rather
  than leaving a `None` to be discovered: carry the connection's trace id if one is established at
  handshake, otherwise omit the key — `traceId` is described by Conventions §4.2 as the W3C trace
  id, and inventing one that correlates with nothing is worse than its absence.
- `src/services/shared/tests/test_problems.py` — cover the request-free path directly: every
  problem class round-trips, `errors` survives on a validation error, and `problem_response` still
  produces the same body it did before the extraction. That last one is the evidence the refactor
  was faithful.
- `src/services/shared/shared/security.py` — extract exactly the two functions ruling 4 names, and
  rewrite the existing entry points to call them. Behaviour unchanged; the existing tests stay green
  **untouched**, and that is the evidence the extraction was faithful.

  ```python
  async def decode_claims(context: SecurityContext, token: str, *, audience: str) -> dict[str, Any]
  async def verify_user_token(context: SecurityContext, token: str, *,
                              sensitive: bool = False) -> UserPrincipal
  ```

  `decode_claims` takes the body of `_verified_claims` (`security.py:109`) from `kid` through
  `jwt.decode`, unchanged including the deliberate single failure message. `verify_user_token` takes
  the body of `RequireUser.__call__` (`security.py:166`) — service-subject rejection, `sub`/`wsp`
  parsing, denylist check, `UserPrincipal` construction. `_check_denylist` changes its first
  parameter from `request: Request` to `context: SecurityContext`; it never used the request for
  anything else. What is left:

  ```python
  async def _verified_claims(request: Request, *, audience: str) -> dict[str, Any]:
      return await decode_claims(_context(request), _bearer_token(request), audience=audience)

  class RequireUser:
      async def __call__(self, request: Request) -> UserPrincipal:
          return await verify_user_token(
              _context(request), _bearer_token(request), sensitive=self._sensitive
          )
  ```

  `RequireService` keeps calling `_verified_claims` with the internal audience — nothing about the
  service path moves, and `require_user` and `require_service` still never meet on one route.
- `src/services/shared/shared/__init__.py` — add **`SecurityContext`** and **`verify_user_token`**
  to the imports and to `__all__` (ruling 4). `SecurityContext` is currently built by
  `install_security` and exported by nothing (`__all__` lists `SecurityConfig` only); the handshake
  needs the type to annotate what it holds. `decode_claims` stays module-private to `shared` —
  nothing outside wants raw claims.
- `src/services/shared/tests/test_security.py` — add tests for the string path directly, alongside
  the existing HTTP ones. Build a `SecurityContext` from `StaticKeySource` and `Denylist` (the file
  already mints RS256 tokens with `mint`/`user_token` at `:53-83`) and cover: a valid token yields
  the principal with `workspace_id` from `wsp`; a service-audience token is refused; an expired
  token is refused; a revoked `jti` is refused; an unreachable denylist is accepted with
  `sensitive=False` and 503s with `sensitive=True`. `ProblemException` is what is raised — the
  caller decides how to render it, which is the whole point of the extraction.

### C. Backend — `src/services/messaging/`

- `pyproject.toml` — add `python-socketio>=5.12`; add `python-socketio[asyncio_client]` to the dev
  dependency group for the tests (gap: the extra brings `aiohttp`, which the async client needs).
  Neither is in `uv.lock`, so `uv lock` regenerates. `uvicorn[standard]` is already there and
  already brings `websockets`.
- `messaging/realtime.py` — **new, and S5 owns it** (ruling 5). Module docstring states the rule
  ruling 4 asks for once: *the publishers read `app.state.realtime` and no-op when it is `None`, so
  an `ASGITransport` test exercises the same router code with no socket server behind it.* Contents:
  - `NAMESPACE = "/messaging"` and `def room(channel_id) -> str: return f"channel:{channel_id}"`
    (Conventions §6 room naming).
  - `RealtimeContext` and `build_server(context)` per gap 1. The server is
    `AsyncServer(async_mode="asgi", client_manager=AsyncRedisManager(url, channel="messaging"),
    cors_allowed_origins=context.settings.cors_allowed_origins or None)` — gaps 2 and 3, with both
    reasons in comments.
  - `_ok` / `_problem` / `@_acked` — the ack envelope from gap 6.
  - `connect(sid, environ, auth)`: token from `auth["token"]`, falling back to the `access_token`
    query parameter parsed out of `environ["QUERY_STRING"]` (Conventions §6); `verify_user_token`
    with `sensitive=False`; `await sio.save_session(sid, {"principal": principal},
    namespace=NAMESPACE)`. A `ProblemException` becomes `raise ConnectionRefusedError(detail)`,
    which is the only way a Socket.IO `connect` handler can refuse — the message reaches the client
    as `connect_error`. **`namespace=NAMESPACE` on every `save_session`/`get_session`/`enter_room`
    call**; the default namespace is `/` and a session saved there is invisible to a `/messaging`
    handler.
  - `join_channel(sid, channel_id)` — authorizes on **`channels.get_visible(...)`, not
    `channels.is_member(...)`** (ruling 12: the room mirrors the read rule), with `workspace_id` and
    `user_id` from the session's principal and never from the event payload. `None` → an error ack
    carrying `ProblemException.not_found("No such channel.")`, 404 not 403. Success → `enter_room`
    and an `_ok()` ack. `leave_channel` is the mirror and needs no authorization — leaving a room
    you should not be in is the correct outcome.
  - `disconnect(sid)` — rooms are released by Socket.IO; the handler exists to log.
  - `publish_message_received` / `publish_message_edited` / `publish_message_deleted`, each
    `(sio: AsyncServer | None, message: MessageResponse) -> None`, returning immediately when `sio`
    is `None` and otherwise emitting `message.model_dump(mode="json", by_alias=True)` to
    `room(message.channel_id)` on `NAMESPACE` (gap 5).
  - `def server(request: Request) -> AsyncServer | None: return request.app.state.realtime` — a
    FastAPI dependency in the shape of `db.session`, so the routers keep the `Depends` idiom instead
    of reaching into `request.app.state` inline.
- `messaging/main.py` — per ruling 4, and no more than ruling 4:
  - `create_app` keeps its signature and gains one line, `app.state.realtime = None`, so every
    existing integration test drives the same router code with the publishers inert.
  - `build_asgi_app(settings, *, key_source=None)` builds the FastAPI app, constructs the
    `RealtimeContext` from its state, calls `build_server`, assigns `app.state.realtime = sio` and
    returns `socketio.ASGIApp(sio, other_asgi_app=app)` — **with no `on_startup`/`on_shutdown`**
    (gap 4), and the reason in the docstring.
  - **`app_factory` is replaced by `asgi_factory`**, not kept alongside it. One factory, not one
    live and one dead.
  - The module docstring's "not here yet" paragraph (`main.py:11-16`) is now wrong; rewrite it to
    describe what is there.
- `docker/messaging/Dockerfile` — `CMD` → `uvicorn messaging.main:asgi_factory --factory ...`, in
  the same change as the rename. `ENTRYPOINT` and the healthcheck are untouched; gap 4 verifies the
  latter rather than assuming it.
- `messaging/routers/messages.py` — S3's and S4's file; S5 adds the publish calls and nothing else.
  Each route gains `sio: AsyncServer | None = Depends(realtime.server)` after the existing
  dependencies, and publishes **after `await session.commit()` and before returning** — a broadcast
  for a row that then fails to commit is a message that exists only in other people's windows. The
  three call sites are `POST /channels/{id}/messages` (received), `PATCH /messages/{id}` (edited)
  and `DELETE /messages/{id}` (deleted, publishing the redacted DTO per ruling 1 and gap 5).
- `messaging/tests/conftest.py` — add one fixture, `realtime_url`, serving `build_asgi_app(...)`
  through `uvicorn.Server` on port 0 and yielding `http://127.0.0.1:{port}`: build the config with
  `lifespan="on"` (that is what gap 4 is checking), `asyncio.create_task(server.serve())`, poll
  `server.started`, read the port from `server.servers[0].sockets[0].getsockname()[1]`, and set
  `should_exit` on teardown. It goes in `conftest.py` rather than in a test module because **S6's
  `test_realtime_writes.py` needs the same server** and neither slice edits the other's test module
  (ruling 5). The existing `postgres_dsn`, `redis_url`, `signing_key`, `engine` and `tokens`
  fixtures are reused unchanged.
- `messaging/tests/test_realtime.py` — **new, S5's alone** (ruling 5). `pytestmark =
  [pytest.mark.integration]`, `socketio.AsyncSimpleClient` against `realtime_url` with the real
  Postgres and Redis containers. Covers: handshake accepted with a minted token in `auth`; accepted
  with the token in the `access_token` query string; refused with no token, an expired token, a
  malformed token and a service-audience token; `join_channel` on a visible public channel the
  caller has not joined succeeds (ruling 12); on a private channel the caller is not in, and on a
  channel in another workspace, both ack a 404 and never a 403; and **a REST write broadcasts to a
  joined client** — which must go over `httpx.AsyncClient(base_url=realtime_url)`, *not* the
  `client` fixture, because that one wraps `create_app` where `app.state.realtime` is `None` and
  nothing is published. Also assert a second client joined to a different channel receives nothing.

### D. Frontend — `src/frontend/`

- `package.json` — add `socket.io-client@^4`.
- `src/lib/realtime/socket.ts` — new (ruling 7). One function,
  `connect(accessToken: string): Socket`, returning
  `io(MESSAGING_URL + '/messaging', { auth: { token: accessToken } })`. The `/messaging` suffix is
  the **namespace**, which is what socket.io-client parses a trailing path as — it is not `path:`,
  and setting `path` instead points the client at a URL engine.io does not serve. `MESSAGING_URL`
  reads
  `import.meta.env.VITE_MESSAGING_URL` with the same fallback `lib/api/messaging.ts:23` uses.
  `withCredentials` stays off: the refresh cookie is scoped to `/api/v1/auth` (Conventions §5.1) and
  the handshake carries its own bearer token.
- `src/lib/realtime/useChannelSocket.ts` — new (ruling 7).
  `useChannelSocket(accessToken, workspaceId, channelId)`, two effects:
  - `[accessToken]` — create the socket, register `connect` / `disconnect` / `connect_error` /
    `message_received` / `message_edited` / `message_deleted`, and `socket.close()` on cleanup. The
    token is the dependency because it changes on renewal *and* on a workspace switch, so one key
    satisfies both Conventions §5.4 and doc 06 §4 without a second lifecycle hook to forget.
  - `[socket, channelId]` — `emit('join_channel', id)` and `emit('leave_channel', id)` on cleanup.
  - `connect` sets `connectionStatus: 'connected'`, re-emits `join_channel` for the channel held in
    a ref (gap 9 — a ref, because the handler registered on mount would otherwise close over the
    channel that was active then), and invalidates `messageKeys.list(workspaceId, channelId)`.
  - `connect_error` calls `socket.disconnect()` and sets `'disconnected'` (gap 8).
  - The three message handlers call S3's `upsertMessage` helper against
    `messageKeys.list(workspaceId, event.channelId)` and **no-op when that key holds no data**
    (gap 10). They never define a second query key and never invalidate-and-refetch per event
    (ruling 7).
- `src/lib/realtime/SocketProvider.tsx` — new, and **the seam S6 sends on.** `useChannelSocket`
  owns the socket's lifecycle but returns nothing, so a `useSocket()` accessor is the only way S6's
  composer can `emit`. A tiny React context holding the live socket instance (or `null` while
  disconnected), provided by `ChatLayout` where the hook is mounted and read by `useSocket()`.
  **Without this S6 has no socket to send on**, and putting the instance in the Zustand store is not
  the alternative — ruling 7 confines that store to `connectionStatus`, and a socket is not state.
- `src/stores/chat.ts` — **`connectionStatus` and nothing else** (ruling 7):
  `'connecting' | 'connected' | 'disconnected'`, plus its setter. No message, channel or membership
  data ever enters this store (D24 🟢) — the existing docstring says so and stays.
- `src/features/channels/ChatLayout.tsx` — mount `useChannelSocket` here, reading
  `activeChannelId` from `useChatStore`, which `ChannelView` already sets and clears
  (`ChannelView.tsx:27`). **One long-lived connection for the shell** (doc 06 §5.1), not one per
  channel view — mounting it in `ChannelView` would tear the socket down and rebuild it on every
  navigation. Render a small status indicator carrying `data-testid="connection-status"` so the
  reconnect scenario can assert on recovery rather than on a timeout.
- No new component, no theme, no notification setting, no stored per-user choice (D28 🔴, doc 06
  §2). `TypingIndicator.tsx` is S6's.
- **No OpenAPI regeneration.** S5 adds no route, no request body and no response model (ruling 8);
  `MessageResponse` is S3's and unchanged. The socket payloads are serializations of a model that
  is already in the committed document.

### E. Decisions and design docs

- `docs/design/02-messaging-service.md` §3.2 — S5 owns the handshake, rooms and server→client rows
  (ruling 9). Write back: the R2 channel name (gap 2), the CORS-empty distinction (gap 3), the
  `message_deleted` payload — **the full `Message`, overturning doc 02 §3.2's
  `{messageId, channelId}` per ruling 18** — and the camelCase `model_dump` serialization (gap 5),
  the ack envelope as **settled** by ruling 15 with its failure key `problem` (gap 6),
  handshake-only verification and why mid-connection revocation is not built (gap 7).
  **Plus ruling 20's limitation:** removing a member does not evict their live socket from
  `channel:{id}`, so they keep receiving a private channel's broadcasts until they reconnect —
  recorded here with the mitigation that already exists, that `join_channel` re-authorizes, so a
  reconnect drops them. S2 raised it; ruling 20 accepted it and assigned the write-up here. Leave the `add_reaction`,
  `remove_reaction`, `mark_read`, `reaction_changed` and `read_receipt_updated` rows alone — they
  are out of scope, not wrong.
- `docs/design/06-frontend-spa.md` §5.2 — S5 owns history load, `join_channel` and inbound event
  handling (ruling 9). Write back: re-join **and refetch** on every connect (gap 9), stop on
  `connect_error` (gap 8), handlers keyed on the event's channel and no-op on an uncached channel
  (gap 10). Optimistic send and the `typing` debounce are S6's rows — do not touch them.
- `docs/design/00-platform-conventions.md` §6 and `docs/design/02-messaging-service.md` §4.1 —
  **ruling 19 gives both to this slice**, overturning gap 2's recommendation that S7 sweep them.
  One line each: a Socket.IO server sharing R2 with another service must pass an explicit
  `channel=` to `AsyncRedisManager`, because the default (`"socketio"`) is the same string in every
  service and two namespaces would cross-deliver. Messaging uses `channel="messaging"`.
  **Canvas's doc 03 is told, not edited** — leave it alone and note the collision in the message.
- **No ADR and no register change.** Nothing 🔴 is settled here: D8d is S4's (ruling 9), D16 and D28
  stay open, and S7 confirms them. Re-recording a decision an earlier slice recorded is a mistake,
  not thoroughness.
- **The delivery plan is not amended.** Only S7 amends it (ruling 9); the corrections above live in
  this plan's "Gaps closed".

---

## Verification

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -m "not integration and not bdd"            # fast path, no Docker
uv run pytest src/services/shared                         # the extraction must not move behaviour
uv run pytest src/services/messaging                      # incl. test_realtime.py
cd src/frontend && npm run typecheck && npm run build

docker compose up -d --build                              # the demo stack: SPA :5173, messaging :8002
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build   # the throwaway one
uv run pytest tests/bdd -m bdd
uv run pytest tests/bdd -m bdd --headed                   # watch it drive the browser
```

Both stacks, and both need `--build`: the Gherkin runs against the throwaway one on :5183 because
it truncates tables between scenarios, and the manual demo below is on the development stack at
:5173. They run side by side on different ports.

Operationally: `uv lock` after the `pyproject.toml` change, and rebuild the messaging image — the
`CMD` moves to `asgi_factory` in the same change as the rename, so a stale image starts a factory
that no longer exists. Confirm `docker compose ps` still shows messaging **healthy**, which is the
check that `/health/live` resolves through the Socket.IO wrapper, and confirm the browser's network
panel shows a WebSocket upgrade rather than a long-polling loop.

**Manual demo:** sign in at <http://localhost:5173> as `ada@collabhub.dev` / `collabhub`, open a
second browser profile as `grace@collabhub.dev`, both in `CollabHub Demo`, and open the same
channel in each. Ada sends, edits and deletes — every change lands in Grace's window with no
reload, the deleted message stays as a tombstone, and Grace's window recovers on its own after her
network is dropped and restored.

**Done:** `tests/bdd/features/realtime.feature` green headed against the test stack, the shared
security tests green with no edit to the ones that existed, the messaging integration suite green
including `test_realtime.py`, ruff clean, frontend typecheck and build clean — and the working tree
left dirty for you to commit.
