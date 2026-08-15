# Slice 4 — Messages: edit and delete

## Context

[`02-messaging-core-delivery-plan.md`](./02-messaging-core-delivery-plan.md) restructures the
messaging build into seven vertical slices, and this is the plan for the fourth. It does two
things, in this order: it **validates the delivery plan's Slice 4 paragraph against the design
docs and the shipped code**, closing the gaps that turns up, and it then **specifies the slice**
in enough detail to build from.

Slice 4 is narrow in surface and wide in rules. Two routes — `PATCH /messages/{id}` and
`DELETE /messages/{id}` — settle who may change a message after it is sent, and it is the slice
that flips **D8d** from 🔴 to 🟢.

**Demo:** Ada edits a message and it shows "edited"; she deletes another and a tombstone stays
through a reload; as the channel's admin she deletes one of Grace's.

Everything cross-slice is already frozen in [`04-slice-contracts.md`](./04-slice-contracts.md) —
the tombstone wire shape (ruling 1), the optimistic-concurrency pattern (ruling 3), who may read
and write messages (ruling 12), the `Message` DTO (ruling 13). Those are cited here and not
re-decided. Validating what is *left* found **nine gaps**, plus two **Contract questions** that
belong to Slice 6 and are recorded rather than answered.

---

## Gaps closed

### 1. Authorization outcomes — the design says who may act, never what a refusal looks like

Doc 02 §3.1 marks `PATCH /messages/{id}` "author" and `DELETE /messages/{id}` "author or channel
admin", and contract ruling 12 repeats both. Neither says what the *other* case returns. The
platform rule everyone will reach for is CLAUDE.md's "a resource the caller may not see is a 404,
not a 403" — and it does not apply here. Grace's message in a public channel **is** visible to
Ada; ruling 12 made it so. Refusing the edit discloses nothing that the message list did not
already show, so a 404 would be a lie about a row the caller is looking at.

**Two different failures, two different codes, and the visibility test runs first.**

| Case | Result |
|---|---|
| Message's channel not visible (`channels.get_visible` → `None`) | **404** `not-found` |
| Message id does not exist | **404** `not-found` — same body, deliberately |
| Channel archived | **404** — `get_visible` filters `archived_at IS NULL` (gap 7) |
| `PATCH`, caller is not the author | **403** `forbidden` |
| `PATCH`, caller is a channel admin but not the author | **403** — admins delete, they do not edit |
| `DELETE`, caller is neither the author nor an admin of the channel | **403** `forbidden` |
| `DELETE`, caller is a channel admin | **200** |

**Order is load-bearing.** Visibility, then existence, then authority. Checking authorship first
would answer "not the author" for a message in a private channel the caller has never been in,
which tells them the message exists. `detail` names the rule, never the author
("Only the author can edit a message.").

Admins deleting but not editing is not an oversight in doc 02 §3.1 — it is the point. Deleting
someone's words is moderation; rewriting them under their name is forgery.

**Write this into `docs/design/02-messaging-service.md` — the Auth column of the two
`/messages/{id}` rows in §3.1, and this table in the new §3.1.4 (ruling 9 gives S4 both).**

### 2. The edit request body exists in no design doc, and `version` in it fights Conventions §4

Doc 02 §3.1 lists the route and its Auth column and stops; there is no request DTO for any
endpoint in the doc. Meanwhile Conventions §4 defines `PATCH` as "partial update, **JSON Merge
Patch RFC 7386**". Under RFC 7386, `{"body": "…", "version": 3}` means *assign 3 to version* —
which is precisely the opposite of what ruling 3 requires it to mean.

**`PATCH /messages/{id}` takes a typed request model, not a merge patch of `Message`, and
`version` in it is a precondition rather than a field:**

```jsonc
// EditMessageRequest — both fields required
{ "body": "the new text",   // the replacement, not a patch of the old one
  "version": 3 }            // the version the caller last saw; a precondition, never an assignment
```

- Both required. There is exactly one editable field on a message, so "field omitted means leave
  it alone" has nothing to express — the `body.model_fields_set` merge idiom from
  `auth/routers/users.py:59` is deliberately **not** used here, and the plan says so rather than
  leaving the next reader to wonder whether it was forgotten.
- `version` travels in the body and is required, per **ruling 3** — not an `If-Match` header.
  Cited, not re-decided.
- The response is the full `Message` (ruling 13) at **200**.
- The outer length bound is a `Field(max_length=…)` mirroring `CreateChannelRequest.name`
  (`schemas.py:78`), so an unbounded string never reaches the domain; the real limit is
  `settings.messaging_max_body_chars` checked in the domain, exactly as S3's send path does.
  **Use whatever constant S3 chose for its send request** — send and edit disagreeing on the
  maximum length of a message body is a bug with a very long half-life.

**Write the DTO into `docs/design/02-messaging-service.md` §3.1.4.** The `Message` response DTO
is S3's (ruling 9) and is not touched.

### 3. Editing or deleting something already deleted — ruling 3 makes two claims that need reconciling

Ruling 3 says `DELETE` "still bumps `version`" *and* that "deleting it twice is idempotent", and
doc 02 §4 says `version` is "bumped on edit/delete". Taken literally, the second delete of the
same row bumps the version again, which is not idempotent and — once the `jobs:index` producer
exists — emits a second Elasticsearch external version for a document that did not change.

**The first delete bumps; a repeat delete is a no-op that returns the existing tombstone.**

- `DELETE` on a live row: sets `deleted_at = now()`, `version = version + 1`, returns 200 with the
  redacted `Message`.
- `DELETE` on a row that already has `deleted_at`: returns **200 with the same tombstone**,
  untouched — no second timestamp, no second version. That is what "idempotent" has to mean, and
  it keeps ruling 3's "no expected version on delete" honest.
- `PATCH` on a row that already has `deleted_at`: **409 `conflict`**, detail "This message was
  deleted." Not 404 — the tombstone is visible in history, and saying "no such message" about a
  row the caller can see is the same lie gap 1 rejects. Not 400 either: the request is
  well-formed, the resource's state refuses it, which is what 409 is for (Conventions §4.2).

**The already-deleted check is a separate check, not an extra `WHERE` clause.** Folding
`deleted_at IS NULL` into the conditional update would make a deleted row and a stale version
both surface as `rowcount == 0`, and the client would be told "someone else edited this" about a
message that no longer exists. Check the loaded row first, then run the version-conditional
update, so `rowcount == 0` means one thing only.

### 4. `DELETE /messages/{id}` has no specified response, and the client needs the row back

Doc 02 §3.1 gives the route, the Auth column and a one-line purpose. The delivery plan's Slice 4
paragraph says "deleted rows returned with `body` redacted server-side" about *history*, and says
nothing about the delete call itself. 204 is the reflex.

**204 is wrong here. `DELETE` returns 200 with the tombstoned `Message`.** A delete on this
platform does not remove a row from the list — ruling 1 keeps it there with `body: ""` and
`deletedAt` set, and the SPA has to render it. With 204 the client would have to refetch the page
it is already holding to learn what to draw; with the row in hand it replaces one entry in the
infinite-query cache through S3's helper (ruling 7) and re-renders. Same argument as returning the
created row from `POST` — the caller already paid for the round trip.

This is a genuine deviation from "DELETE returns 204", so it is written down rather than left as
a surprise in the OpenAPI document.

**Write the `200 → Message` response into `docs/design/02-messaging-service.md` §3.1.4.**

### 5. Delete redacts on the way out — it never clears the stored row

Ruling 1 fixes the wire shape and says the redaction is server-side, and gives the mapper to S3.
What no document says is whether `DELETE` should *also* blank the `body` column. It should not,
and the reason is worth stating because blanking it looks tidy, changes nothing visible, and
destroys data silently:

- The wire is already safe — the mapper substitutes `""` for any row with `deleted_at` set, so
  the text cannot reach a client whatever the column holds.
- Hard deletion belongs to a retention job, and its window is **D16, still 🔴** (ruling 10). No
  slice in this scope writes one, and `POST /api/v1/internal/messages/sweep` is not built. A
  delete path that erases the text now would pre-empt a decision nobody has made.
- Nothing else holds a copy: the `jobs:index` producer is out of scope throughout (delivery plan,
  "Out of scope"), so there is no Elasticsearch document to purge either.

**The `UPDATE` sets `deleted_at` and `version`, and touches no other column.** Also: `edited_at`
is left exactly as ruling 1's table says — *unchanged* — which means a message that was edited and
then deleted carries both timestamps. **The client renders the tombstone from `deletedAt` alone
and never shows the edited marker on a deleted row**; "This message was deleted (edited)" is not a
thing anyone needs to read.

### 6. Three of the five scenario titles say "member", and membership is not the rule any more

The delivery plan's Slice 4 Gherkin list names "A channel **admin** deletes another **member's**
message" and "A **member** cannot delete someone else's message". Contract ruling 12 removed
membership from the read and write path entirely — visibility gates reading and writing, and
**posting does not create a membership row**. So the actor in scenario five is not a member, the
victim in scenario four is not a member, and a scenario written to the plan's wording would need a
membership step that only S2's admin-driven `POST /channels/{id}/members` can perform — making
this slice's acceptance suite depend on Slice 2's UI for no behavioural reason.

**The scenarios run in a public channel with no membership step at all.** Ada creates
`#general`, so she is its admin (`channels.create`, `channels.py:141`). Grace posts in it without
joining, per ruling 12. That is the whole setup, and it exercises the interesting case — an admin
moderating someone who is not in the channel — rather than the easy one.

Retitled:

- A channel admin deletes another **user's** message
- A **non-admin** cannot delete someone else's message

Both remain the delivery plan's scenarios; only the noun that ruling 12 invalidated changes.

### 7. Archiving a channel freezes its messages, and nobody has written that down

Ruling 12's last row notes that `get_visible` filters `archived_at IS NULL`, so an archived
channel's messages are unreachable "by the same code path. Correct, and deliberate." Following it
forward: **once S2 archives a channel, nobody can edit or delete anything in it — not the author,
not an admin — and the attempt returns 404.**

That is the right default (an archive is a frozen record) but it is a support ticket waiting to
happen, and it is a consequence of a ruling rather than anything doc 02 §3.1.1 states. **State it
in `docs/design/02-messaging-service.md` §3.1.4**, where the edit and delete rules live, and test
it at integration level. **There is no remedy in this scope: S2 rules archiving one-way** — its
`PATCH /channels/{id}` carries `name`, `topic` and `version` only, and accepts `archivedAt`
nowhere — so §3.1.4 must say the freeze is permanent rather than pointing at an unarchive route
that does not exist.

### 8. The version the caller holds next — the stale-row trap, twice over

Ruling 3's pattern is written against `Channel` and ends `.values(name=name, version=Channel.version + 1, updated_at=func.now())`. Copied to messages verbatim it will not run: **`messages` has no
`updated_at` column** (doc 02 §4 DDL — `created_at`, `edited_at`, `deleted_at`, `version`). The
edit timestamp *is* `edited_at`, and it is also what the UI's marker reads, so it is set on every
successful edit and never cleared.

The second half of the trap is on both sides of the wire, and both halves produce the same
symptom — a second edit failing with 409 for no reason a user can see:

- **Server:** a Core `update()` leaves the ORM object the router loaded holding the *old*
  `version`. Serialising that object returns a version the row no longer has.
  **`await session.refresh(message)` after the update, before building the response.**
- **Client:** the mutation writes the returned `Message` back into the infinite-query cache
  through S3's replace helper (ruling 7). It does **not** `invalidateQueries` the way
  `useCreateChannel` does (`useChannels.ts:39`) — invalidating a `useInfiniteQuery` refetches
  every loaded page and throws away the scroll position S3 worked to hold.

An edit that leaves the text unchanged still bumps `version`. No dirty-check: the column feeds the
Elasticsearch external version (doc 02 §4, register D25 🟢), which wants monotonic, and a
no-op edit is not worth a special case.

### 9. D8d flips, but half of what its title names belongs to D16

The register's D8d reads **"Edit/delete windows and tombstone retention"** (line 65), and its
"Depends on" column says "Align with Worker retention (D16)". D16 — retention values — **stays
🔴** (ruling 10). Flipping D8d to 🟢 as titled would claim that tombstone retention is settled
when nothing in this scope picks a number, keeps a sweep endpoint, or writes a retention job.

**D8d flips to 🟢 with its scope stated in the entry, not just its status changed:**

> 🟢 Decided 2026-08-15. No time window on either action. The author edits their own message;
> the author or an admin of the channel deletes it. Deleted messages are retained in history as
> tombstones (`body: ""`, `deletedAt` set), redacted server-side. **How long a tombstone is kept
> before hard deletion is D16, still 🔴** — nothing in this scope deletes one.

The ADR (`adr-writer` skill, `docs/adr/`) carries the same boundary, and says why the tombstone
exception to CLAUDE.md's "queries filter `deleted_at IS NULL`" exists at all: a tombstone a reload
erases is not a tombstone. Ruling 9 puts D8d in **S4, not S7**; S7 must not re-record it.

### Also corrected in the delivery plan

- **The read-path redaction is S3's, not S4's.** The Slice 4 paragraph says "deleted rows returned
  with `body` redacted server-side" as though this slice adds it. Ruling 1 ships `history_page`,
  `get` and the redacting mapper complete in S3, before anything can set `deleted_at`. **S4 changes
  no read path** — it adds the two writes and nothing else on the query side.
- **The D8d ADR moves from Slice 7 to Slice 4** (ruling 9, and CLAUDE.md's "record it in the slice
  that makes it"). The delivery plan's Slice 7 section already hedges with "recorded there if that
  slice gets there first"; the ruling removes the hedge.
- **No migration.** Ruling 2 puts `edited_at`, `deleted_at` and `version` in S3's
  `0002_messages` and forbids a second revision file in any other slice. S4 adds no Alembic
  version, no index and no column. If building it turns up a schema need, that is a Contract
  question, not a `0003`.

S7 carries all three into the delivery plan's amendment blockquote — **ruling 9 says only S7
amends that file**, so this plan records them here and leaves it alone.

---

## How the slice runs

Unchanged from the delivery plan:

1. Gherkin first — extend `tests/bdd/features/messages.feature` and write nothing else.
2. 🛑 **Stop and wait for explicit approval.** Expect rounds of revision.
3. Build outside-in; watch the scenarios fail for the right reason before writing code.
4. Never edit a scenario to fit the implementation.
5. `data-testid` selectors only, owned by page objects.
6. Branch `feature/messaging-s4-edit-delete` (ruling 11). **Never commit** — leave the tree dirty.

**Scenarios** — Ada edits her own message and it shows an edited marker · Ada cannot edit Grace's
message · Ada deletes her own message and a tombstone remains after reload · A channel admin
deletes another user's message · A non-admin cannot delete someone else's message. (Two retitled
per gap 6; the delivery plan's five, unchanged in substance.)

Deliberately **not** in Gherkin, at integration level instead: the 409 version conflict (ruling 3
— two browsers racing a `PATCH` is not a scenario anyone can write honestly), the 403-vs-404 split
from gap 1, the idempotent second delete, `PATCH` on a tombstone, the archived-channel freeze from
gap 7, and cross-workspace tenancy.

---

## Work

### A. Acceptance — `tests/bdd/`

- `tests/bdd/features/messages.feature` — **extend**, do not create (ruling 6: S3 owns the file,
  S4 extends it). Five scenarios, in a public channel with no membership step (gap 6). The
  tombstone scenario reloads through `ChatPage.open()` before asserting, because "a tombstone
  remains after reload" is the whole point of ruling 1.
- `tests/bdd/steps/test_message_steps.py` — **extend**. Already named `test_*` and already calls
  `scenarios("../features/messages.feature")`; **do not call `scenarios()` a second time** — two
  calls run every scenario twice (ruling 6). Mirror the shape of
  `steps/test_channel_steps.py:47-139`: `@given`/`@when`/`@then` taking the `ada` / `grace`
  fixtures, no locator anywhere in the module.
- `tests/bdd/pages/chat_page.py` — **new methods on the existing page object**, never a second
  page object for the same screen (ruling 6). Needed: `edit_message(old, new)`,
  `message_body(text)`, `has_edited_marker(text)`, `delete_message(text)`, `tombstone_visible()`,
  `can_edit(text)` / `can_delete(text)` for the two refusal scenarios. Each waits explicitly the
  way `create_channel_and_wait` does (`chat_page.py:65`) rather than relying on an implicit
  timeout. New `data-testid`s go here and nowhere else in the suite.
- `tests/bdd/conftest.py` — **untouched.** `MESSAGING_TABLES` is S3's to widen (ruling 6,
  `conftest.py:60`); `ada` / `grace` / `reset_messaging` already cover this slice, and no slice
  adds a third signed-in user without a Contract question.

### B. Backend — `src/services/messaging/`

- `messaging/messages.py` — S3's domain module, extended. Follows `channels.py` exactly: plain
  async functions, `AsyncSession` first, no FastAPI imports, one exception per rule
  (`channels.py:41-66`).
  - New exceptions `NotAuthorError`, `NotDeletableError`, `AlreadyDeletedError`.
    **`VersionConflictError` is imported from `messaging/channels.py`, where S2 defines it**
    (ruling 3) — one exception, not two with the same name.
  - `edit(session, *, workspace_id, user_id, message_id, body, expected_version) -> Message`.
    **S3's `messages.get(session, *, message_id)` is workspace-blind on purpose** — S3 puts the
    visibility guard in its router, in `_visible_message`. So these domain functions call
    `channels.get_visible(...)` themselves against the loaded row's `channel_id`, and take the
    workspace from `workspace_id` — **never `channels.is_member`** (ruling 12). Do not assume the
    load guards anything; built on that assumption, edit and delete authorize on nothing. Then: `None` → caller's 404; `deleted_at` set →
    `AlreadyDeletedError`; `author_id != user_id` → `NotAuthorError`; body through the same
    validation S3's send path uses. Then ruling 3's conditional update, with `edited_at=func.now()`
    and **no `updated_at`** (gap 8), `rowcount == 0` → `VersionConflictError`, then
    `await session.refresh(message)`.
  - `delete(session, *, workspace_id, user_id, message_id) -> Message`. Same load and 404.
    Authority is `author_id == user_id or await channels.is_admin(session, channel_id=…, user_id=…)`
    (`channels.py:221`) → else `NotDeletableError`. Already deleted → return the row unchanged
    (gap 3). Otherwise unconditional on version (ruling 3) but conditional on
    `deleted_at IS NULL`, setting `deleted_at=func.now(), version=Message.version + 1`, then
    refresh.
  - Body validation calls **S3's `messages.validate_body(raw, *, max_chars)`**, which ruling 21
    makes a named domain function in S3 and explicitly says this slice does not extract. If it is
    inline when this slice starts, that is a defect against S3 — fix it there and say so, rather
    than absorbing the extraction here.
- `messaging/routers/messages.py` — S3's router, extended with `PATCH` and `DELETE`. Copy
  `routers/channels.py`'s idiom: module docstring stating the rules once, a private `_guard`
  helper at the top translating the domain exceptions, signature order `principal: UserPrincipal =
  Depends(require_user)` then `session: AsyncSession = Depends(db_session)`. Plain `require_user`,
  never `require_user_sensitive` — message edits are not in the fail-closed set (doc 02 §3.1).
  Translation per gap 1: `None` → `ProblemException.not_found("No such message.")`;
  `NotAuthorError` → `.forbidden(...)`; `NotDeletableError` → `.forbidden(...)`;
  `AlreadyDeletedError` → `.conflict("This message was deleted.")`; `VersionConflictError` →
  `.conflict(...)`. Build the response *then* `await session.commit()`, as
  `create_channel` does (`routers/channels.py:111-113`) — and leave the commit as the last
  statement, because S5 slots its publisher call in immediately after it.
- `messaging/schemas.py` — add `EditMessageRequest(CamelRequest)` per gap 2. `CamelRequest` is
  deliberately not `populate_by_name` (`schemas.py:27`); leave that alone. The `Message` response
  model is S3's and is not touched (ruling 13).
- `messaging/models.py` — **no change.** `Message` and its columns ship in S3 (ruling 2).
- `messaging/alembic/versions/` — **no new revision** (ruling 2).
- `tests/test_messages.py` — S3's file, extended; `pytestmark = pytest.mark.integration`, real
  Postgres via `tests/conftest.py`, tokens through the `ada` / `grace` fixtures
  (`tests/conftest.py:176-183`). Cases: author edits and `editedAt` appears and `version`
  increments · non-author edits → 403 · channel admin edits someone else's → 403 (gap 1) · edit
  with a stale `version` → 409 · edit with a blank or over-long body → 400 with `errors.body` ·
  edit a deleted message → 409 · author deletes → 200, `body == ""`, `deletedAt` set,
  `version` bumped, **the row's stored body is unchanged** (gap 5, asserted against the database
  rather than the API) · admin deletes another user's → 200 · non-admin non-author deletes → 403 ·
  delete twice → same `deletedAt`, same `version` (gap 3) · a tombstone is still in
  `GET /channels/{id}/messages` and in `GET /messages/{id}` · a message in an archived channel →
  404 on both routes (gap 7).
- `tests/test_tenancy.py` — extended: a workspace-B token editing or deleting a workspace-A
  message gets 404, and the row is untouched. `workspace_id` comes only from
  `principal.workspace_id`; there is no workspace anywhere in these two requests to substitute.

### C. Frontend — `src/frontend/`

- `src/lib/api/messaging.ts` — `editMessage(accessToken, messageId, {body, version})` and
  `deleteMessage(accessToken, messageId)`, each mirroring `createChannel` (`messaging.ts:53`):
  `openapi-fetch` call, `if (error !== undefined) throw problem(response.status, error)`, generated
  types only. Types come from `src/types/messaging.ts`, which is generated output no slice edits
  (ruling 8).
- `src/features/channels/useMessages.ts` — S3's module, extended with `useEditMessage` and
  `useDeleteMessage`. Both write the returned `Message` back through **S3's infinite-query replace
  helper** (ruling 7) and **must not `invalidateQueries`** (gap 8). `messageKeys.list` is S3's and
  is used as defined — no second key.
- `src/features/channels/MessageItem.tsx` — S3's component; S4 adds the affordances inside it
  (ruling 7). Edit control when `message.authorId === userId`; delete control when
  `message.authorId === userId || myRole === 'admin'`. **The hidden control is a courtesy, not
  authorization** — the server decides, and the 403 tests are what prove it. A row with
  `deletedAt` renders "This message was deleted" from `deletedAt`, never from the empty `body`
  (ruling 1), carries no controls, and shows **no** edited marker even when `editedAt` is set
  (gap 5). A live row with `editedAt` shows the marker.
- `src/features/channels/MessageEditor.tsx` — new (ruling 7). Inline textarea seeded from the
  current body, save and cancel. Renders `ProblemError.fieldError('body')` against the input and
  `message` in a banner otherwise, exactly as `CreateChannelDialog.tsx:26-30` splits them — the
  409 from a version conflict has no `errors` map and belongs in the banner.
- `src/App.tsx` — `ChannelRoute` currently passes only `accessToken` and `workspaceId`
  (`App.tsx:103-112`), so **no component below it knows who the signed-in user is**. Thread
  `userId={state.session.profile.id}` (`lib/auth/api.ts:28`) through `ChannelView` to
  `MessageList` to `MessageItem`. `myRole` needs no new fetch: `ChannelView` already holds the
  channel query (`ChannelView.tsx:32-40`).
- `src/stores/chat.ts` — **untouched.** No server state in Zustand (D24 🟢, ruling 7);
  `connectionStatus` is S5's and nothing here needs it.
- `openapi/messaging.json` and `src/types/messaging.ts` — regenerated, because this slice adds two
  routes and a request model (ruling 8). Commands in Verification.
- No `docs/design/06-frontend-spa.md` change: §5.2 belongs to S5 and S6 (ruling 9).

### D. Decisions recorded

- `docs/adr/` — the **D8d** ADR via the `adr-writer` skill: no time window, author edits own,
  author or channel admin deletes, tombstones retained in history, and the documented exception to
  CLAUDE.md's "queries filter `deleted_at IS NULL`". States the D16 boundary explicitly (gap 9).
- `docs/design/07-open-decisions-register.md` — **D8d → 🟢** with the scoped wording in gap 9.
  D16 stays 🔴 and is not touched beyond leaving its cross-reference correct.
- `docs/design/02-messaging-service.md`:
  - §3.1 — the Auth column of the `PATCH /messages/{id}` and `DELETE /messages/{id}` rows only
    (ruling 9 gives S4 those two rows and no others).
  - **new §3.1.4** — gap 1's outcomes table, gap 2's request DTO, gap 3's already-deleted rules,
    gap 4's `200 → Message` response, gap 5's "redact on the way out, never in the row", gap 7's
    archived-channel freeze, and ruling 1's tombstone wire table. Ruling 9 names this section
    "tombstones in history"; it covers the whole edit/delete contract, and S4 owns all of it.
  - §9 — **strike the "Edit/delete windows and tombstone retention" open-decision line** (ruling
    9), replacing it with a pointer to the ADR and noting that retention values remain D16 🔴.

**Contract question (Slice 6):** doc 02 §3.2 gives the inbound socket event as
`edit_message {messageId, body}` — **no `version`** — while ruling 3 makes the expected version
required on the edit path, and the delivery plan requires S6 to call "the same domain functions
the REST routers call". One of the two has to move. *Recommendation:* keep
`messages.edit(..., expected_version: int)` required, and have S6 add `version` to the
`edit_message` payload and write it into doc 02 §3.2, which S6 owns. A socket client holds the
cached message exactly as the REST client does, so it has the number for the same reason ruling 3
gives. S4 does not make this change.

**Contract question (Slice 6):** the ack payload for `delete_message`. This slice returns the
tombstoned `Message` from `DELETE /messages/{id}` (gap 4), while the server→client broadcast is
fixed at `{messageId, channelId}` (doc 02 §3.2, S5's). *Recommendation:* S6's ack returns the same
`Message` the REST route does, so the SPA reconciles through one code path — S3's replace helper —
whichever way the delete was issued. S6's call.

> **Both answered by ruling 18, 2026-08-15 — both as recommended, and S5 and S6 reached the same
> conclusions independently.** `edit_message` carries `{ messageId, body, version }` and S6 writes
> that row; the socket is not a way around ruling 3. `delete_message`'s ack returns the tombstoned
> `Message`, **and so does the `message_deleted` broadcast** — doc 02 §3.2's
> `{messageId, channelId}` is overturned for the same reason, because a client cannot render
> ruling 1's tombstone from an id. S5 writes the broadcast row. **Nothing in this slice changes:**
> `messages.edit(..., expected_version)` and the 200-with-tombstone response are what both paths
> are built on.

---

## Verification

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -m "not integration and not bdd"          # fast path, no Docker
uv run pytest src/services/messaging src/services/shared

uv run python -m messaging.openapi > src/frontend/openapi/messaging.json   # ruling 8
cd src/frontend && npm run generate:api                 # → src/types/messaging.ts, never hand-edited
npm run typecheck && npm run build

docker compose up -d --build                              # the demo stack: SPA :5173
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build   # the throwaway one
uv run pytest tests/bdd -m bdd
uv run pytest tests/bdd -m bdd --headed                 # watch it drive the browser
```

Both stacks, and both need `--build`: the Gherkin runs against the throwaway one on :5183
because it truncates tables between scenarios, and the manual demo below is on the
development stack at :5173. They run side by side on different ports.

No migration runs in this slice — ruling 2 keeps every messages column in S3's `0002_messages`, so
`--build` on the test stack is the only thing that has to happen before the suite.

**Manual demo:** sign in at <http://localhost:5173> as `ada@collabhub.dev` / `collabhub`, create
`#general` and post in it; open a second browser profile as `grace@collabhub.dev` and post there
too without joining. As Ada: edit your own message and watch the "edited" marker appear; delete
another and confirm the tombstone survives a reload; delete Grace's as the channel's admin. Then
confirm Grace has no edit control on Ada's message and no delete control either.

**Done:** the five scenarios in `tests/bdd/features/messages.feature` green headed against the
test stack, ruff clean, the messaging integration suite green, `npm run build` clean, the D8d ADR
and register flip written — and the working tree left dirty.
