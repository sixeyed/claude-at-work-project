# Slice 6 — Socket write path, optimistic send, typing

## Context

[`02-messaging-core-delivery-plan.md`](./02-messaging-core-delivery-plan.md) restructures the
messaging build into seven vertical slices, and Slice 6 is the one it calls "the half where the
bugs live". This plan does two things, in that order: it **validates the delivery plan's Slice 6
paragraph against the design docs, the frozen slice contracts and the shipped code**, closing the
gaps it finds; then it **specifies the slice** in enough detail to build from.

Slice 6 turns the composer into a Socket.IO writer. Ada's message renders the instant she hits
enter and is confirmed silently against the server's acknowledgement; a rejected send rolls back
and shows why; Grace sees "Ada is typing…" appear and clear on its own.

The slice sits on top of Slice 5, which owns the socket server itself. Per
[`04-slice-contracts.md`](./04-slice-contracts.md) ruling 4, S5 owns `shared/security.py`'s
`verify_user_token` extraction and `build_asgi_app` — this plan **consumes both and respecifies
neither** — and ruling 5 puts S6's inbound handlers in `messaging/realtime_writes.py`, a module of
its own rather than a second slice editing `realtime.py`.

Validation found **ten gaps**. Four are corrections to `docs/design/02-messaging-service.md` §3.2
and `docs/design/06-frontend-spa.md`, which ruling 9 gives this slice to write back. Two raise
**Contract questions** rather than answering them.

---

## Gaps closed

### 1. The Socket.IO ack has no error shape — RFC 7807 stops at the HTTP boundary

Doc 02 §3.2 says `send_message` "returns the created `Message` via the Socket.IO acknowledgement
callback" and says nothing whatever about a *failed* write. Conventions §4.2 mandates
`application/problem+json` "on every non-2xx" — but an ack has no status code, no content type and
no response object. So the delivery plan's own demo, "a rejected send rolls back with an error",
has no wire format to carry the error in, and three handlers written blind would invent three.

Worse, `shared/problems.py` cannot help as it stands: `problem_response(request, problem)`
(`problems.py:124`) is `Request`-bound, exactly as `RequireUser.__call__` was before ruling 4 split
it. And a python-socketio handler that *raises* never sends its ack at all — the client's callback
simply never fires and the optimistic bubble hangs forever. **A handler on this path must never
raise.**

**The ack is a discriminated envelope, and its failure arm is the RFC 7807 body unchanged:**

```jsonc
// success
{ "ok": true,
  "data": { /* Message (send_message, edit_message) — see ruling 13 */ } }

// failure — byte-identical to what the REST route would have returned in its body
{ "ok": false,
  "problem": {
    "type": "https://collabhub.dev/problems/validation-error",
    "title": "One or more validation errors occurred.",
    "status": 400,
    "detail": "A message body must be 8000 characters or fewer.",
    "instance": "/messaging#send_message",   // the namespace and event, not a URL path
    "traceId": "…",
    "errors": { "body": ["A message body must be 8000 characters or fewer."] } } }
```

`ok` is the discriminant so no client has to infer failure from an absent key. The `problem`
object is the same document `install_problem_handlers` produces, so the SPA parses acks and REST
failures with one parser and `status` keeps meaning what it means everywhere else — 400 validation,
404 invisible channel, 409 version conflict, 401 expired token, 503 denylist unreachable.

**`delete_message`'s `data` is the tombstoned `Message`** — as is the `message_deleted` broadcast
S5 sends. This plan originally argued the opposite (`{messageId, channelId}`, matching doc 02
§3.2), on the reasoning that an ack should mirror its own broadcast payload. **Ruling 18 overturned
it, and the reasoning survives inverted:** the ack and the broadcast *are* the same shape — both
carry the `Message` — because ruling 1 keeps a deleted row in history with `body` redacted, and a
client cannot render that tombstone from an id alone. S3's `upsertMessage` then reconciles a delete
exactly as it reconciles an edit, through one code path.

Producing that body needs a request-free builder in `shared` — see the Contract question in gap 4's
sibling below and work package **C**.

**Write this back into `docs/design/02-messaging-service.md` §3.2**, as a paragraph under the
client→server table (ruling 9 gives S6 those rows).

### 2. `edit_message` carries no expected version — the socket would bypass a rule REST enforces

Doc 02 §3.2 gives `edit_message` the args `{ messageId, body }`. Contract ruling 3 is explicit that
**the expected version travels in the request body as `version` and is required** on
`PATCH /messages/{id}`. The delivery plan then asks the socket handlers to call "the same domain
functions the REST routers call" — which is impossible, because S4's `messages.edit` will take an
`expected_version` and the documented event has nowhere to put one. Built as documented, the socket
becomes the way to lose someone else's edit silently.

- **`edit_message` takes `{ messageId, body, version }`, and `version` is required.** Same field,
  same name, same requirement as the REST body (ruling 3) — one rule, two transports.
- A `VersionConflictError` from `messaging/channels.py` (ruling 3 defines it there; S4 imports it
  into `messages.py`) becomes an `ok: false` ack with `status: 409`, problem type `conflict`.
- **`delete_message` stays `{ messageId }` and unconditional**, because ruling 3 makes `DELETE`
  unconditional. It still bumps `version`; that is S4's code, not this slice's.

**Write the `version` argument into `docs/design/02-messaging-service.md` §3.2's `edit_message`
row.**

### 3. "A client may only act on a channel it has joined" is not the authorization rule

The delivery plan's Slice 6 paragraph says a client may only act on a channel it has joined, and
[`01-messaging-core-strategy-plan.md`](./01-messaging-core-strategy-plan.md) Phase 3 goes further:
*"`join_channel` is where membership is verified."* Both are wrong now, in two separate ways.

**It is the wrong test.** Ruling 12 settled that visibility gates reading *and* writing and that
membership gates administration only: `POST /channels/{id}/messages` is allowed to anyone
`channels.get_visible` returns the channel to. Authorizing the socket write on room membership
would make the socket stricter than the REST route it is replacing, and would resurrect exactly the
gap ruling 12 closed — Grace, who can see `#general` and has never been added to it, could post
over REST and not over the socket.

**It is not a durable fact.** A Socket.IO room is per-`sid` in-memory state. It is lost on every
reconnect, and the client re-joins from its `connect` handler — so a send queued across a reconnect
races its own `join_channel` and fails for a reason no user could act on.

**The call: every inbound write authorizes with `channels.get_visible(...)`, in the same
transaction as the write, exactly as the REST router does.** A channel the caller may not see is a
`not-found` ack — 404 in the problem body, never 403 (CLAUDE.md; doc 02 §3.1.1). For
`edit_message` / `delete_message` the message's own channel is the one tested, then S4's author /
channel-admin rule on top.

Room membership is dropped as a gate and keeps its real job: deciding who *receives* the broadcast.
A sender who has not joined the room still gets their ack, which is the only confirmation the
optimistic path needs. **This corrects the delivery plan and the strategy plan; doc 02 §3.2 never
claimed the room was an authorization boundary, so nothing there needs changing.**

### 4. A socket connection authenticates once and then writes forever

S5's handshake verifies the token in `connect` (ruling 5) and stores the `UserPrincipal` in the
Socket.IO session. Nothing verifies it again. A REST call re-checks signature, expiry and the
denylist on **every** request (Conventions §5.1, §5.2); a socket connection lives for hours on a
15-minute token. Until this slice that only meant a stale connection could keep *reading*. This
slice hands it a write path — so **moving the SPA onto the socket would be a security regression
unless the socket path is as strong as the REST path it replaces**, and neither the delivery plan
nor doc 02 §3.2 mentions it.

| Check | When | On failure |
|---|---|---|
| `principal.expires_at > now` | every inbound event, **including `typing`** | `unauthorized` ack, `status: 401` |
| `denylist.state(principal.token_id)` | the three write events only | `REVOKED` → 401 · `UNKNOWN` → **proceed** |

The denylist result **fails open** here, deliberately: doc 02 §3.1 puts channel writes outside the
fail-closed set of Conventions §5.2, and the shipped router says so in its own docstring
(`routers/channels.py:10`). `typing` skips the denylist because it persists nothing and one R1
round trip per throttle window is real load for no authority gained; the expiry check is free and
still applies.

**The server does not disconnect the socket itself.** Returning the ack and then calling
`sio.disconnect` inside the same handler races the ack's own flush. The client tears the socket
down and reconnects when it sees `status: 401` — S5's frontend already rebuilds the connection on
token renewal (delivery plan, Slice 5), so this is the backstop for a renewal that did not happen.

**Write this into `docs/design/02-messaging-service.md` §3.2** as a note under the client→server
table: the handshake authenticates the connection, each inbound write re-checks expiry and
revocation.

### 5. Typing has no stop event, and no name to put in the sentence

The scenario is "A typing indicator appears for Grace and **clears when Ada stops**". Doc 02 §3.2
gives one client→server `typing` and one server→client `user_typing({channelId, userId})`. There is
no `typing_stopped` anywhere, so as documented the indicator appears and never leaves.

**Expiry is receiver-side, and the wire contract stays as doc 02 gives it.** No stop event is
added. A server that tracked who was typing would need that state shared across pods through R2
for something the design calls "ephemeral, never persisted" — and it would still have to invent a
timeout for the client that closed its laptop mid-word. The receiver already has to.

| Constant | Value | Why |
|---|---|---|
| `TYPING_EMIT_INTERVAL` | 2000 ms | **Leading-edge throttle, not a trailing debounce.** A trailing debounce delays the indicator by its own window, which is the opposite of the point. First keystroke emits immediately, then at most one emit per window while typing continues |
| `TYPING_TTL` | 4000 ms | Two missed windows. The receiver drops a user this long after their last `user_typing` |

The second half is the sentence itself. `user_typing` carries `{channelId, userId}` and the demo
says "Ada is typing…" — but Messaging does not read Auth's tables (Conventions §2), and ruling 13
already flags rendering an author's name from an id as an open question for S3.

This plan originally put a `displayName` on the `user_typing` payload, taken from the sender's own
`UserPrincipal.display_name`, on the grounds that an ephemeral event cannot go stale.
**Overturned in review, 2026-08-15: the name is resolved client-side through ruling 14's
`useWorkspaceMembers` hook, like every other name in the UI.** Two sources for one display name is
the drift that hook exists to prevent, and the typing user is by definition in the workspace the
hook has already fetched. It also leaves doc 02 §3.2's payload exactly as written — so this slice
changes that row's *shape* not at all, only documents it:

```jsonc
// user_typing  — server → client, unchanged from doc 02 §3.2
{ "channelId": "uuid", "userId": "uuid" }
```

Fan-out uses `skip_sid=sid` so the sender never sees their own indicator, **and** the client
discards any `user_typing` whose `userId` is its own — one line that also covers the user's second
tab, which `skip_sid` does not.

**Contract question: doc 02 §3.2's `user_typing` row.** Ruling 9 gives S5 the server→client event
table and S6 the `typing` client→server row, so this payload change straddles the seam.
**Recommendation: S6 writes the `user_typing` row as well.** S5 builds no typing path at all, and a
row S5 cannot exercise is a row S5 should not be editing.

> **Granted by ruling 19, 2026-08-15.** Ownership follows the emitter. Ruling 19 also gives this
> slice **doc 06 §8's client-side message-length pre-check**, the sentence gap 8 removes — the
> slice that changes the behaviour corrects the doc.

### 6. Optimistic send has a race the delivery plan does not mention

Doc 06 §5.2 says "render optimistically with a temp id, reconcile on the acknowledged `Message` /
`message_received`" — the slash is doing a lot of work. Socket.IO gives **no ordering guarantee
between a broadcast and an ack**, and the sender is in the room, so `message_received` for Ada's own
message can arrive *before* her ack does. Reconciling on the ack alone renders the message twice.

**The reconciliation rule, once:**

- The optimistic entry is a complete `Message`-shaped object built client-side, so `MessageItem`
  (S3's) renders it with no second component: `id` = `` `temp:${crypto.randomUUID()}` ``,
  `authorId` = `session.profile.id`, `createdAt` = now, `body` as typed, `threadRootId` `null`,
  `attachments` `[]`, `editedAt`/`deletedAt` `null`, `version` `0`.
- **The `temp:` prefix is the pending marker.** Nothing goes into Zustand: contract ruling 7 is that
  no slice puts anything server-shaped in `stores/chat.ts`, and a parallel map of in-flight sends
  keyed by temp id is a second copy of the message list wearing a hat. `id.startsWith('temp:')` is
  what greys the bubble.
- **Reconcile = remove the temp entry, then upsert the real one by `id`.** Upsert, not append —
  which makes the operation idempotent, so it does not matter whether the broadcast or the ack got
  there first, and it is the same idempotency a reconnect replay needs anyway.
- This is S3's exported infinite-query helper (ruling 7) doing the work; S6 calls it and does not
  write a second one. History is a `useInfiniteQuery`, so the cached value is `{ pages, pageParams }`
  and a handler that sets a bare array breaks the query silently.

No `clientMsgId` is added and **the `Message` DTO is not touched** — ruling 13 freezes it and gives
it to S3. Remove-then-upsert makes an echo field unnecessary, which is why it is the design chosen.

**Write this into `docs/design/06-frontend-spa.md` §5.2**, replacing the "reconcile on the
acknowledged `Message` / `message_received`" clause (ruling 9 gives S6 that half of §5.2).

### 7. A lost ack hangs the composer, and doc 06 §7's offline queue is not being built

`socket.emit(event, payload, callback)` with no connection does not fail — it buffers, and the
callback never fires. Doc 06 §7 says "queue outgoing chat sends while disconnected", which is what
the buffering half-implements: the message sits in a `temp:` bubble with no error and no way out.

**No queue in this scope, and the composer says so instead.** A queue that survived a reconnect
would need ordering, durable storage and dedupe against a `send_message` that is **not idempotent**
— nothing carries an idempotency key on this path, and Conventions §7's idempotency rule is about
Redis Stream jobs, not socket events. None of that machinery exists, and S5's "the stream recovers
after the connection drops" scenario already covers the case that matters.

- The composer is **disabled while `connectionStatus !== 'connected'`** (the field S5 adds to
  `stores/chat.ts`, ruling 7), with a visible reason rather than a dead input.
- Every emit is **`socket.timeout(5000).emit(...)`**, so a lost ack rolls back within five seconds
  instead of hanging.
- **A timed-out send is never retried automatically.** It rolls back, restores the text into
  `drafts[channelId]` — the store field that already exists for exactly this — and tells the user.
  Auto-retrying a non-idempotent write is how one message becomes two.

Doc 06 §7's queue line stays as an aspiration; S6 does not implement it and does not own §7, so it
records the deferral in **§5.2**, which it does own.

### 8. The client is told to pre-check the length that the rejected-send scenario depends on

The only rejection reachable from a browser with no fault injection is a body over
`MESSAGING_MAX_BODY_CHARS` (8000 — doc 02 §6, `settings.py:30`, and S3's own "a message over 8000
characters is rejected"). Doc 06 §8 says the SPA should "respect server limits (message length,
attachment count/size) client-side before sending". Do both and **"a rejected send is rolled back
and the error is shown" can never happen** — the send never leaves the browser, there is no
optimistic bubble, and there is nothing to roll back.

**The composer does not pre-validate the body length.** The server owns the rule; the client
renders what the server says. This is not a new principle — it is what the shipped
`CreateChannelDialog` already does, and says why in its own docstring: *"a regex here would be a
second copy to drift, and the one that matters is the one guarding the database"*
(`CreateChannelDialog.tsx:4`).

A `maxlength` attribute is likewise **not** set on the textarea, for the same reason and because it
would make the step unwritable.

### 9. `send_message`'s documented args include two fields nothing in scope can honour

Doc 02 §3.2 gives `send_message` the args `{ channelId, body, threadRootId?, attachmentIds? }`.
Both optional fields are out of scope and stay that way: D8a 🟡 keeps `thread_root_id` a column
with no API (ruling 10), and attachments are always `[]` because the Asset service is a skeleton
(ruling 13). Accepting a `threadRootId` that the handler drops on the floor is a claim the service
does not honour.

**`send_message` takes `{ channelId, body }`.** Inbound payloads are validated by Pydantic models
defined **in `realtime_writes.py`, not in `schemas.py`** — they are not REST bodies, they never
appear in the OpenAPI document, and keeping them beside their handlers avoids editing a file
ruling 13 gives to S3. A payload that fails validation is a `validation-error` ack, not a raised
exception (gap 1: a raise costs the client its callback).

**Write the narrowed argument list into `docs/design/02-messaging-service.md` §3.2**, with a note
that the two dropped fields return with threads and attachments.

### 10. The SPA moves its composer to the socket and nothing else

The delivery plan asks S6 for three inbound handlers. Contract ruling 7 gives S6 exactly one
frontend rewiring: *"the change of **send** from REST to socket emit inside `useMessages.ts`"*.
Edit and delete are S4's affordances and **stay on REST**. Read together those are consistent, but
only if it is said out loud — otherwise someone helpfully rewires `MessageEditor` and the diff
stops being reviewable.

- All three inbound handlers ship, because doc 02 §3.1 documents `POST /channels/{id}/messages` as
  the *fallback* and §3.2 as the real interface. A documented event with no implementation is worse
  than an unexercised one.
- `edit_message` and `delete_message` are covered by `tests/test_realtime_writes.py` only. Nothing
  in the browser emits them in this slice.
- **`POST /channels/{id}/messages` stays alive** with its tests untouched (ruling 7).

---

### Also corrected in the delivery plan

- **"each returning the `Message` via the Socket.IO ack"** is wrong for `delete_message` — gap 1.
- **"Extend `test_realtime.py`"** — ruling 5 supersedes it: S6 writes `tests/test_realtime_writes.py`
  and neither slice edits the other's test module.
- **`features/chat` → `features/channels`** (doc 06 §3), already noted in the delivery plan's
  amendment and in ruling 7; the Slice 6 paragraph still uses the old path implicitly.

---

## How the slice runs

Unchanged from the delivery plan. Six reminders:

1. **Gherkin first** — the scenarios below fleshed out into Given/When/Then, and nothing else.
2. 🛑 **Stop and wait for explicit approval.** Silence is not a go-ahead.
3. **Build outside-in**, and watch the scenarios fail for the right reason first.
4. **Never edit a scenario to fit the implementation** — reopen step 2 instead.
5. **`data-testid` only**, owned by page objects; no raw locator in a step definition.
6. **Branch `feature/messaging-s6-socket-write`. Never commit — leave the tree dirty.**

**Scenarios** — extending `tests/bdd/features/realtime.feature` (ruling 6): A typing indicator
appears for Grace and clears when Ada stops · A sent message appears immediately and is confirmed ·
A rejected send is rolled back and the error is shown.

Deliberately **integration-level, not Gherkin**: the `edit_message` and `delete_message` acks and
their rejections · the 409 on a stale `version` (ruling 3 keeps 409 out of Gherkin) · the expired
and revoked principal · a send into a channel the caller cannot see · the five-second ack timeout.
None of them is a scenario anyone could write honestly through a browser.

---

## Work

### A. BDD — `tests/bdd/`

- `features/realtime.feature` — **extend** the file S5 created; do not add a second one, and do not
  call `scenarios()` anywhere but S5's step module (ruling 6: two modules pointing at one feature
  run every scenario twice).
- `steps/test_realtime_steps.py` — **extend** S5's module with the new steps. Synchronous
  throughout; async work goes through the existing `_run_off_loop` helper (`tests/bdd/conftest.py:168`).
  No new fixture: `ada` and `grace` already give two long-lived signed-in contexts, and ruling 6
  forbids a slice adding a third signed-in user.
- `pages/chat_page.py` — new methods on the existing page object, never a second one (ruling 6):
  - `type_into_composer(text)` — fills without submitting, which is what makes `typing` fire.
  - `send_message(text)` and `message_bodies()` are **already on `ChatPage` from S3** — this slice
    reuses them and adds none of its own. Re-specifying a shipped method is how two slices end up
    with two spellings of one selector.
  - `pending_message_bodies()` — the subset carrying `data-pending="true"`, which is how a step
    distinguishes "appeared immediately" from "was confirmed".
  - `typing_indicator_text()` / `expect_typing_indicator_gone()` — the second waits on
    `state="hidden"` with an explicit timeout comfortably above `TYPING_TTL` (gap 5); Playwright's
    5-second default is too close to a 4-second expiry to trust.
  - `composer_error()` — **also S3's**, modelled there on `error_message()` (`chat_page.py:77`).
    Reused unchanged.
- The rejected send is a body over 8000 characters (gap 8). No fault injection, no mock, and it
  exercises the same domain rule S3 tested.

### B. Backend — `src/services/messaging/messaging/realtime_writes.py` (new)

Ruling 5 gives S6 this module and one line elsewhere. Model the file on `routers/channels.py`: the
`_guard`-style private helpers at the top, then the handlers, and the domain layer untouched below.

- `register_write_handlers(sio, context)` — the single export, taking **S5's `RealtimeContext`**
  (settings, sessions, security) unchanged; the denylist is reached through `context.security`,
  which already holds it (`shared/security.py:73`), not passed a second time. S6 adds the one line
  calling it from `build_asgi_app` in `main.py`, immediately after S5's `build_server(...)`.
  Editing one line of a file S5 created is expected: the slices are *built* in order, only the
  planning is parallel.
- Inbound payload models — `SendMessagePayload`, `EditMessagePayload`, `DeleteMessagePayload`,
  `TypingPayload` — as `CamelRequest` subclasses (`schemas.py:27`) but **defined here**, not in
  `schemas.py` (gap 9).
- The ack envelope is **imported, not built here**: `_ok`, `_problem` and `@_acked` come from
  `messaging/realtime.py` (rulings 15 and 16 — see package C). Handlers pass
  `instance=f"/messaging#{event}"`. **The trace id follows S5's rule** — carried from the connection
  if one was established at handshake, otherwise omitted; this slice does not generate one, because
  a trace id that correlates with nothing is worse than its absence.
- `_principal(sid)` — reads the `UserPrincipal` S5's handshake stored in the Socket.IO session,
  then applies gap 4's expiry check. `_check_revoked(principal)` applies the denylist half,
  fail-open on `TokenState.UNKNOWN`.
- `_authorize(session, principal, channel_id)` — `await channels.get_visible(session,
  workspace_id=principal.workspace_id, user_id=principal.user_id, channel_id=channel_id)`;
  `None` → a `not-found` problem (gap 3). `workspace_id` comes from the principal and from nothing
  in the payload — the payload has no workspace field to be tempted by, exactly as
  `routers/channels.py:5` describes for REST.
- The three write handlers each: validate the payload → `_principal` → `_check_revoked` → open a
  session from `sessions` → `_authorize` → call the S3/S4 domain function → **`await
  session.commit()`** → call S5's `publish_message_received` / `_edited` / `_deleted` → return the
  ack. Commit before publish, in that order, matching what S5 does from the REST routers (ruling 4).
  The routers commit explicitly and the session dependency does not (noted in
  `03-slice-01-implementation-plan.md`); nothing changes here.
- **Every handler is wrapped so nothing escapes it.** Domain exceptions map to their problems;
  a bare `Exception` is logged and returned as a 500-shaped `internal` problem carrying no internal
  message, mirroring `_unhandled` in `shared/problems.py:176`. A raise here costs the client its
  callback (gap 1) — this is the single most important line in the module.
- `typing` — `_principal` only, no denylist, no database, no persistence. Emits `user_typing`
  with `displayName` from the principal (gap 5) to `channel:{id}` with `skip_sid=sid`. It takes no
  ack: there is nothing to confirm.

### C. Backend — `shared` and the ack envelope, both consumed not built

This package builds nothing. It is here so an engineer reading `## Work` in order does not go
looking for the envelope's definition and write a second one:

- `from messaging.realtime import _ok, _problem, _acked` — S5's, per ruling 15.
- `from shared import problem_body` — S5's, per ruling 16.
- Neither is redefined, wrapped or renamed here. If either is missing when this slice starts, that
  is a defect against S5, not work to absorb.

**Contract question: does S6 own `shared/problems.py`?** Ruling 4 gives S5 `shared/security.py` and
nothing rules on `problems.py`. **Recommendation: yes, S6 owns it.** No other slice needs a
request-free problem body — S5's handshake rejects with `ConnectionRefusedError`, not a document —
and the alternative is `realtime_writes.py` hand-rolling a second problem body, which is precisely
what the module's own docstring says must not exist: *"the only route to a non-2xx body is through
here"*.

> **Answered by ruling 16, 2026-08-15 — recommendation overturned. S5 owns
> `src/services/shared/shared/problems.py`**, and this package builds nothing. The premise was
> wrong: S5 does need it, because `join_channel` refuses a channel the caller may not see and that
> refusal is an ack, not a handshake rejection. One slice touching `src/services/shared/` also
> means one review of the library every service depends on. **S6 imports
> `shared.problem_body`** and specifies no extraction of its own; S5's plan carries the signature,
> the export and the trace-id rule.
>
> Ruling 15 settles the envelope on the same terms: **S5 defines `_ok` / `_problem` / `@_acked` in
> `messaging/realtime.py` and S6 imports them.** The failure key is `problem` — this plan's
> spelling, which won over S5's `error`. Handlers here still never raise; that part is unchanged.

### D. Backend tests — `src/services/messaging/tests/test_realtime_writes.py` (new)

Ruling 5: S6 writes this module, S5 writes `test_realtime.py`, and neither edits the other's.
Drives **S5's `realtime_url` fixture** in `tests/conftest.py` — uvicorn on an ephemeral port with
the Postgres and Redis containers — which S5 puts there specifically so this slice reuses it rather
than standing up a second server. Tokens are minted through the existing `tokens` fixture
(`tests/conftest.py:171`), never imported from another service's `tests` package.

- `send_message` — happy path returns `ok: true` and a `Message`; the row is in Postgres; a joined
  second client receives `message_received`.
- `send_message` into a channel the caller cannot see — `ok: false`, `status: 404`, **not 403**,
  using the private-channel-and-not-a-member case `test_tenancy.py` already sets up.
- `send_message` from a *visible but unjoined* public channel — **succeeds** (ruling 12, gap 3), and
  writes no `channel_members` row.
- `send_message` over `messaging_max_body_chars` — `status: 400`, `errors.body` populated, nothing
  written.
- `edit_message` with a stale `version` — `status: 409` (gap 2). With the current version — 200-shaped
  ack and `message_edited` on the room.
- `delete_message` — ack `data` is the tombstoned `Message`, `body` redacted to `""` (gap 1,
  ruling 18), and the `message_deleted` broadcast carries the same.
- An expired principal and a revoked `jti` — `status: 401`; an unreachable denylist — the write
  **succeeds** (gap 4, fail-open).
- `typing` — the other client in the room receives `user_typing` with `channelId` and `userId`; the
  sender does not; nothing is written to `messages`.
- A handler given a malformed payload returns an ack rather than dropping the callback — the
  regression test for gap 1's failure mode.

### E. Frontend — `src/frontend/src/`

- `features/channels/useMessages.ts` — S3's file; S6 changes **send only** (ruling 7, gap 10).
  `useSendMessage` stops calling REST and emits `send_message` over S5's socket with
  `socket.timeout(5000)`. `onMutate` inserts the `temp:` entry through S3's exported infinite-query
  helper; the ack removes it and upserts the real message; a failed or timed-out ack removes it,
  restores `drafts[channelId]` and surfaces the `ProblemError` (gaps 6, 7). Query keys are S3's
  `messageKeys` unchanged — no second key.
- `features/channels/useTyping.ts` — **new, and S6's own file** rather than an edit to S5's
  `lib/realtime/useChannelSocket.ts`. Owns both halves: the leading-edge `typing` throttle and the
  `user_typing` subscription with per-user `TYPING_TTL` expiry, discarding its own `userId`
  (gap 5). Returns the list of names currently typing.
- `features/channels/TypingIndicator.tsx` — new (ruling 7). Renders `displayName`s from
  `useTyping`, `data-testid="typing-indicator"`, absent from the DOM when nobody is typing so the
  page object can wait on `hidden`. Tailwind tokens only, light palette, no stored preference
  (D28 🔴, doc 06 §2).
- `features/channels/MessageComposer.tsx` — S3's file; S6 adds the `typing` emit on change, the
  `connectionStatus`-driven disable with a visible reason (gap 7), and the rollback error slot.
  **No client-side length check and no `maxlength`** (gap 8). Same arrangement as the one-line edit
  to `main.py`: built in order, planned in parallel.
- `features/channels/MessageItem.tsx` — S3's/S4's file; S6 adds only `data-pending` derived from
  the `temp:` prefix, and the muted styling that goes with it.
- `lib/api/client.ts` — lift the private `problem(status, body)` helper out of
  `lib/api/messaging.ts:38` into this module as `problemFromBody(status, body)`, and point both
  `messaging.ts` and the new ack path at it. One `ProblemError` for REST failures and acks alike,
  which is the whole reason gap 1 chose the RFC 7807 body for the failure arm.
- **Nothing is added to `stores/chat.ts`** (ruling 7). `connectionStatus` is S5's and `drafts`
  already exists; the pending-send state lives in the temp id (gap 6).
- `src/types/messaging.ts` is generated output and is not edited (ruling 8).

### F. Decisions and design docs

- `docs/design/02-messaging-service.md` §3.2 — the client→server rows S6 owns (ruling 9): the ack
  envelope and its failure arm (gap 1), `version` on `edit_message` (gap 2), the narrowed
  `send_message` args (gap 9), and the per-event expiry/revocation note (gap 4). **Plus the
  `user_typing` server→client row** — ruling 19 granted it to this slice unconditionally, because
  ownership follows the emitter and S5 builds no typing path. That row's *payload* is unchanged
  from what doc 02 §3.2 already says (`{channelId, userId}`); what this slice documents is the
  throttle, the TTL and the `skip_sid` behaviour.
- `docs/design/06-frontend-spa.md` §5.2 — the optimistic-send half S6 owns (ruling 9): remove-then-
  upsert reconciliation (gap 6), the leading-edge `typing` throttle and receiver-side TTL (gap 5),
  and the deferral of §7's offline queue with its reason (gap 7).
- `docs/design/06-frontend-spa.md` §8 — **ruling 19 gives this slice the client-side
  message-length pre-check sentence**, which gap 8 removes. The slice that changes the behaviour
  corrects the doc that describes it.
- **No register change.** D8d flips in S4 (ruling 9), D16 and D28 stay 🔴 with nothing in this slice
  touching them, D8a/D8b/D8c stay 🟡. S7 confirms.
- **The ack-envelope ADR is not this slice's.** Rulings 15 and 16 put the envelope and
  `shared.problem_body` in S5, so if a cross-cutting wire contract warrants an ADR — and it
  probably does, since Canvas meets it next — it is written where the decision was made. This slice
  raises it if S5 did not, and does not absorb it.
- **No migration** (ruling 2), **no OpenAPI regeneration** — S6 adds no REST surface (ruling 8) —
  and **no new environment variable**, so `.env.example` is unchanged. If any of those three turns
  out to be false while building, it is a Contract question, not a local decision.

---

## Verification

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -m "not integration and not bdd"          # fast path, no Docker
uv run pytest src/services/messaging src/services/shared # shared/ matters: the problems.py extraction
cd src/frontend && npm run typecheck && npm run build

docker compose up -d --build                              # the demo stack: SPA :5173
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build   # the throwaway one
uv run pytest tests/bdd -m bdd
uv run pytest tests/bdd -m bdd --headed                 # watch the indicator appear and clear
```

Both stacks, and both need `--build`: the Gherkin runs against the throwaway one on :5183
because it truncates tables between scenarios, and the manual demo below is on the
development stack at :5173. They run side by side on different ports.

Nothing operational changes: no migration, no new variable, and `/health/live` still resolves
through S5's `socketio.ASGIApp` wrapper, so the Compose healthcheck is the one S5 already verified.

**Manual demo:** with the development stack up, sign in at <http://localhost:5173> as
`ada@collabhub.dev` / `collabhub` and open a second browser profile as `grace@collabhub.dev`, both
in the `CollabHub Demo` workspace. Ada types in `#general` — Grace sees "Ada is typing…" appear
within a keystroke and clear about four seconds after Ada stops. Ada hits enter: the message renders
instantly, greyed, and settles the moment the ack lands, while Grace's window gets it with no
reload. Ada then pastes more than 8000 characters and sends: her bubble disappears, the text comes
back in the composer, and the composer says why.

**Done:** the three new scenarios in `tests/bdd/features/realtime.feature` green headed against the
test stack, ruff clean, `src/services/messaging` and `src/services/shared` integration suites green
with S5's `test_realtime.py` and `shared`'s `test_problems.py` untouched and still passing — and the
working tree left dirty for you to commit.
