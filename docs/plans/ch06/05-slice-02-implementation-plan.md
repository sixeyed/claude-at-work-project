# Slice 2 — Channel administration and membership

## Context

[`02-messaging-core-delivery-plan.md`](./02-messaging-core-delivery-plan.md) gives this slice one
paragraph. This plan does two things with it, in that order: it **validates that paragraph against
the design docs and the code Slice 1 shipped**, and it **specifies Slice 2** in enough detail to
build from without inventing a pattern the repo already has.

The slice ends with Ada renaming a channel and archiving another, creating a private channel,
adding Grace to it and removing her again — with Grace's sidebar changing to match on her next
load. Real-time is Slice 5, so every cross-user assertion here is after a reload, and the scenarios
say so.

Slice 2 is the first slice that *updates* a row rather than only inserting and reading one, and the
first with an authority rule beyond "can you see it". Both are where the gaps clustered.

The frozen rulings in [`04-slice-contracts.md`](./04-slice-contracts.md) are binding and are cited
rather than re-argued — ruling 2 (no migration in this slice), ruling 3 (optimistic concurrency,
which **S2 defines**), ruling 6 (BDD growth), ruling 7 (frontend seams), ruling 8 (OpenAPI
regeneration), ruling 9 (doc ownership) and ruling 12 (visibility gates reading).

Validation found **nine gaps**, two of them defects in code Slice 1 already shipped, and raised
**two contract questions**.

---

## Gaps closed

### 1. Rename and archive authority — the design gives neither the rule nor the status code

Doc 02 §3.1 marks `PATCH`/`DELETE /channels/{id}` "channel admin" and stops there. Doc 02 §3.1.1
defines visibility and says nothing about authority. So two questions are open: what a *visible but
not administered* channel returns, and what an *invisible* one returns. Getting the second wrong is
the disclosure bug Slice 1's gap 1 already fixed for reads.

**The call — visibility decides 404, role decides 403, and they are evaluated in that order:**

| Caller, for `PATCH`/`DELETE /channels/{id}` and every `/members` write | Result |
|---|---|
| `channels.get_visible` returns `None` (other workspace, archived, private non-member, absent) | **404** `not-found` |
| Visible, `my_role` is `null` or `member` | **403** `forbidden` |
| Visible, `my_role == 'admin'` | proceed |

403 is right for the middle row and only that row: a public channel is already known to the whole
workspace (doc 02 §3.1.1), so "you are not an admin of it" discloses nothing the caller could not
already read. A private channel never reaches that row, because it is invisible first. **One guard
sequence, `_visible_or_404` then `_admin_or_403`, on all five write routes.**

The consequence for the delivery plan is that its scenario **"A non-admin cannot rename a
channel" cannot be observed in a browser**. `myRole` ships on the DTO precisely so the UI hides the
admin controls (doc 02 §3.1.3, `schemas.py:59`), so Grace has no rename control to click; a step
that drove one would be testing a control the slice deliberately does not render. **The Gherkin
asserts the absence of the controls — "A member without admin rights is not offered the channel
controls" — and the 403 is covered in `tests/test_channels.py`**, the same division ruling 3 makes
for the 409.

**Write the 404/403 rule into `docs/design/02-messaging-service.md` §3.1.1** (S2 owns that section
per ruling 9).

### 2. `PATCH` does not archive, and archiving is one-way

Doc 02 §3.1 gives `PATCH /channels/{id}` the purpose "Rename / change topic / archive" and
`DELETE /channels/{id}` "Soft-delete (archive)". Two routes for one state change, and the `PATCH`
form implies a client sending an `archivedAt` timestamp — a client writing a server clock.

**The call: `DELETE` archives. `PATCH` carries `name`, `topic` and `version` only.** `archivedAt`
is not accepted on any request body.

The second half matters more. Ruling 12 confirms that `get_visible` filters `archived_at IS NULL`
and that an archived channel's messages are unreachable through the same code path — "correct, and
deliberate". Every read in the service goes through that query, so **an archived channel is
invisible to everyone including its own admin, and nothing in this scope can un-archive it.** There
is no `GET /channels?archived=true`, no restore route, and adding either would mean a read path
that sees archived rows — which is the thing ruling 12 froze shut.

That is an acceptable scope boundary, not an accident, but it must be visible to the user before
they act: **the archive control confirms first** ("Archive #general? Nobody will be able to open it
again."), and the SPA navigates to `/` on success rather than leaving Ada looking at a channel
whose detail query now 404s.

**Write both — the `PATCH`/`DELETE` split and the irreversibility — into
`docs/design/02-messaging-service.md` §3.1**, on the two rows S2 owns.

### 3. The guarded update — `updated_at` is never written, and 409 must not swallow 404

Two defects in one statement.

**`channels.updated_at` has a `server_default` and no `onupdate`** (`models.py:84`, and the DDL in
doc 02 §4 is the same). Slice 1 never updated a row, so nothing noticed. A rename that leaves
`updated_at` at the creation time makes the column a lie on the first write the service ever does.
Ruling 3's shape already sets it, and **every guarded update in this slice sets
`updated_at=func.now()` explicitly**; nothing is added to the model, because an `onupdate` would fire
on a `session.flush()` nobody asked for.

**The version check cannot be the existence check.** `WHERE id = :id AND version = :expected`
returning `rowcount == 0` means *either* a stale version *or* a row that is not there — and
answering 409 for a channel in another workspace would tell that caller the channel exists. So the
order is fixed: `get_visible` (404) → admin (403) → guarded update (409). Per ruling 3, the
exception is **`VersionConflictError`, defined in `messaging/channels.py` by this slice** and
imported by `messaging/messages.py` in S4:

```python
result = await session.execute(
    update(Channel)
    .where(Channel.id == channel_id, Channel.version == expected_version)
    .values(name=name, version=Channel.version + 1, updated_at=func.now())
)
if result.rowcount == 0:
    raise VersionConflictError(channel_id)
```

`DELETE` is unconditional and takes no body (ruling 3), and still bumps `version` and sets
`archived_at`. A second `DELETE` is a 404, because the row is no longer visible — consistent with
gap 2 and with the 404-not-403 rule, and not something to special-case into a 204.

The response is built by **re-reading through `get_visible` after the flush**, not from the
in-session object, which the Core `UPDATE` has left stale. `auth/routers/workspaces.py`
`_member_response` is the precedent: what comes back is what was stored.

**Write the `version` / optimistic-concurrency note into `docs/design/02-messaging-service.md` §4**
(ruling 9 assigns that note to S2), including that `updated_at` is set by the application.

### 4. Membership DTOs do not exist, and Messaging cannot resolve a person

Doc 02 §3.1 says `POST /channels/{id}/members` — "Add member(s)" — and defines no request body, no
response body, and no list shape. Doc 02 §3.1.3 defines `Channel` and `Message` and nothing else.

The constraint that settles the shape is Conventions §2: **Messaging owns no user records and must
not read Auth's tables.** It cannot accept an email, it cannot validate a display name, and it will
not make a synchronous call to Auth on the path of a channel edit — the same reasoning
`auth/routers/users.py` gives for not checking `avatar_asset` against the Asset service.

**Singular, by id:**

```jsonc
// AddChannelMemberRequest
{ "userId": "uuid", "role": "member" }        // role optional, "member" | "admin", default "member"

// ChannelMember
{ "userId": "uuid", "role": "admin|member", "joinedAt": "..." }

// ChannelMemberListResponse
{ "items": [ /* ChannelMember */ ], "nextCursor": "…|null" }
```

- **Singular, not "member(s)".** A batch add has no honest status code when three of five ids are
  already members; five calls do.
- **No existence check on `userId`.** Messaging cannot make one. A membership row for an id that is
  not a user in this workspace grants nothing: `_visible_query` filters
  `Channel.workspace_id == principal.workspace_id`, so a token from another workspace still cannot
  see the channel, membership row or not. The row is inert; the tenancy guard is unaffected.
- **Already a member → 409** `conflict`, mirroring `identities.add_member`'s `ValueError` → 409.
- **Removing someone who is not a member → 404.** No user, no membership, same answer.
- **No self-join and no self-leave.** Ruling 12 states that nothing in this scope lets a user join a
  channel themselves; both member writes require a channel admin, including when the target is the
  caller.
- **Nothing is revoked on removal.** Channel membership is not in any token, which is the same fact
  that keeps these routes on plain `require_user` (doc 02 §3.1, Conventions §5.2). Contrast
  `auth/routers/workspaces.py` `remove_member`, which must revoke sessions — a reviewer who
  remembers that route will look for the equivalent here, and there is none to write.

**Write these three DTOs into `docs/design/02-messaging-service.md` §3.1.3** and the singular-add
rule onto the §3.1 members rows.

### 5. Who may see a channel's member list — doc 02 says "channel member", which is one guard too many

Doc 02 §3.1 marks `GET /channels/{id}/members` "channel member". Applied literally, Grace can see
`#general` in her sidebar, open it, read it (ruling 12) — and get a 403 asking who else is in it.
That is the same shape of rule Slice 1's gap 1 removed from `GET /channels/{id}`.

**The call: `GET /channels/{id}/members` uses the visibility test, not the membership test.** If
`get_visible` returns the channel, the caller sees its members. A private channel is invisible to
non-members already, so this widens exactly one case — a public channel, where who is in it is not
a secret from the workspace that can already read every word in it. Membership continues to gate
*administration*, which is the line ruling 12 drew.

One guard (`_visible_or_404`) on the read, two (`_visible_or_404` + `_admin_or_403`) on the writes.

**Correct the Auth column on the `GET /channels/{id}/members` row of doc 02 §3.1.**

### 6. Member list ordering — `joined_at` would need an index this slice may not add

`members_page` in Auth keysets on `(joined_at, user_id)` (`auth/identities.py:253`), and copying it
is the obvious move. It is the wrong one here. `channel_members` has `PRIMARY KEY (channel_id,
user_id)` and one other index, `ix_channel_members_user (user_id, channel_id)` — nothing leads with
`(channel_id, joined_at)`, so ordering by `joined_at` is a sort on top of a PK scan, and the index
that would fix it is a migration. **Ruling 2 forbids one: "No other slice adds a migration — not
S2."**

**The call: order by `user_id` ascending, keyset on `user_id` alone.**

- It is unique within a channel, so it satisfies `shared/pagination.py`'s "the sort key must be
  unique" without a second key part.
- `WHERE channel_id = :id ORDER BY user_id` walks the primary key in order — no sort node, no new
  index, no migration.
- The order is arbitrary to a human, and that is fine: **Messaging holds no display names, so no
  ordering it can express is meaningful anyway** (gap 4). The panel sorts the page it has by
  display name for rendering. With the default limit of 50 and channels this size that is the whole
  list; across pages the client-side sort would be per-page, which is a real limitation and is
  worth one sentence in the doc rather than an index for a query no one runs yet.

**Note the ordering on the `GET /channels/{id}/members` row of doc 02 §3.1.**

### 7. Nothing stops the last admin being removed

`channels.create` makes the creator an admin (Slice 1 gap 4, `channels.py:141`) because a channel
with no admin can never be administered — but nothing keeps it that way. As specified, Ada can
remove herself, or a second admin can remove her, and the channel is left with `PATCH`, `DELETE`
and both member writes permanently 403 for everyone. There is no route that can grant the role
back: doc 02 §3.1 has no `PATCH /channels/{id}/members/{userId}`, and this slice adds no route the
doc does not list.

Auth already refuses the equivalent — `identities.LastOwnerError`, "a workspace with no owner
cannot be administered by anyone".

**The call: `DELETE /channels/{id}/members/{userId}` returns 409 `conflict` when the target is the
channel's only admin**, with detail "This is the channel's only admin; make someone else an admin
first." The domain exception is `LastAdminError` in `messaging/channels.py`, modelled on
`_last_owner` (`auth/identities.py`). Adding a second admin is possible through the `role` field of
gap 4's add request, so the state is escapable.

**Add the rule to the `DELETE /channels/{id}/members/{userId}` row of doc 02 §3.1.**

### 8. The SPA cannot create a private channel — four of this slice's scenarios are unsatisfiable

`CreateChannelDialog.tsx:34` submits `{ name }` and nothing else; `lib/api/messaging.ts:59` fills in
`kind: 'public'`. The API has accepted `private` since Slice 1 (`models.py:42`), but no browser can
ask for one.

Every membership scenario in the delivery plan needs one. "An admin adds a member and they see the
channel" is not observable in a public channel — Grace can already see it, and adding her changes
only `myRole`. "Removing a member revokes their view" is *false* for a public channel: she keeps
seeing it. And "A non-member cannot open a private channel" needs a private channel to exist.

**The call: `CreateChannelDialog` gains a kind control** (`data-testid="create-channel-kind"`,
public/private, defaulting to public), and `createChannel` stops hard-coding the kind. **Private is
what the membership scenarios exercise, and the plan says so per scenario** rather than leaving the
Gherkin to imply it. No design-doc change — doc 02 §3.1.2 already says the API takes `public` and
`private`; only the SPA was short.

### 9. The harness cannot sign out — the delivery plan's last scenario would break every scenario after it

The delivery plan lists **"Signing in as a different user shows only that user's channels"**. Taken
literally that is a sign-out and a sign-in, and `ChatLayout.tsx:44` renders a `sign-out` button
ready to be clicked.

Clicking it is destructive. `POST /auth/logout` revokes the refresh token the cookie carries
(`auth/routers/auth.py:183-192`), and `tests/bdd/conftest.py` holds **session-scoped**, signed-in
contexts for Ada and Grace precisely because a rotating refresh token cannot be replayed (Slice 1's
gap 8). A sign-out in one scenario ends that user's session for the rest of the run, and every later
scenario fails somewhere unrelated. Ruling 6 makes the same point from the other side: no slice adds
a fixture that signs a third user in.

The behaviour the scenario is reaching for is real, though, and after gap 8 it is testable without
signing anyone out: **"Ada creates a private channel and only she can see it"** — Grace, already
signed in, loads the app and does not have it in her sidebar. Same assertion, two live contexts, no
session destroyed.

**Nothing in this slice clicks `sign-out`.** Worth stating in the plan because the control exists,
the step reads naturally, and the failure it causes surfaces three scenarios later.

### Also corrected in the delivery plan

- **Two of the slice's backend bullets shipped in Slice 1.** "Private-channel visibility in the list
  query" is `channels._visible_query` (`channels.py:152`), and "archived channels dropped from the
  list" is the `Channel.archived_at.is_(None)` clause in the same query. Neither is frontend work,
  and neither is Slice 2 work — the archive scenario passes on a server rule that already exists.
- **`ChannelHeader` does not exist.** Slice 1 put the channel header inline in `ChannelView.tsx:60`.
  This slice extracts it, rather than creating a component the plan assumes is already there.
- **Ruling 8 applies: S2 regenerates the OpenAPI document and the types.** The delivery plan's Slice
  2 paragraph predates D23 being implemented and does not mention it.
- **No migration.** Checked column by column: `version`, `archived_at`, `updated_at`, `role` and
  `joined_at` all shipped in `0001_channels` (ruling 2 confirms `last_read_id` did too). Nothing in
  this slice needs an `ALTER`.

**Contract question — resolving a display name for a bare user id.** Messaging returns `userId` and
holds no name (gap 4), so the member panel has nothing to render but a UUID. Ruling 13 raises the
identical question for `Message.authorId` and assigns it to S3 to *raise*, not answer — but S2 hits
it first, so answering it silently here would pre-empt S3. **Recommendation:** one hook,
`features/channels/useWorkspaceMembers.ts`, calling Auth's existing
`GET /api/v1/workspaces/{id}/members` (`auth/routers/workspaces.py`, plain `require_user`, returns
`user.displayName` per member) with query key `['workspace-members', workspaceId]`, exposing an
id → display-name map that S3 reuses unchanged for message authors. It needs one hand-written
function in `lib/auth/api.ts` — Auth publishes no OpenAPI document, and generating one is not this
slice's work. S2 builds the member panel on this recommendation; if the coordinator rules otherwise,
the panel renders ids and the hook is deleted.

> **Granted by ruling 14, 2026-08-15, exactly as recommended.** S3 raised the same question
> independently and reached the same answer with a different key (`['directory', …]`); **this
> slice's spelling wins** and S3 and S6 import `useWorkspaceMembers` rather than defining a second
> hook. Two things to hold to: the item shape is `{ user: { id, displayName, avatarAsset }, role,
> joinedAt }` — nested, per `auth/schemas.py:159` — and the endpoint is **cursor-paginated at 50**,
> so the hook pages to exhaustion or silently loses every member after the fiftieth. Option B
> (denormalising a name onto `messages`) is rejected: it would go stale on a rename and put a fact
> Auth owns into Messaging's database.

**Contract question — a member removed while their socket is live.** Ruling 12 evaluates
`join_channel` against the read rule at join time. Removing someone from a private channel in S2
does not eject them from `channel:{id}`, so from S5 onward they would keep receiving messages until
they disconnect. **Recommendation:** leave it — a forced room-leave means Messaging reaching into
the Socket.IO server from a REST handler, and this scope has no admin-initiated eviction in a live
UI. S5 documents the limitation in its doc 02 §3.2 writeback. Raised here because the removal
endpoint is S2's and the consequence is S5's.

> **Granted by ruling 20, 2026-08-15, as recommended — accepted as a limitation, not a defect.**
> The exposure is one already-authorized session on one *private* channel until its next
> reconnect; ruling 12 makes public channels workspace-visible, so there is nothing to revoke
> there. S5 writes it into doc 02 §3.2 along with the mitigation that already exists —
> `join_channel` re-authorizes, so a reconnect drops them. Not a Gherkin scenario: it asserts an
> absence over an unbounded wait.

---

## How the slice runs

Unchanged from the delivery plan. Six reminders, no more:

- **Gherkin first** — the two `.feature` files and nothing else.
- 🛑 **Stop and wait for explicit approval.** A question or a comment on one scenario is not one.
- **Build outside-in**, and watch the scenarios fail for the right reason first.
- **Never edit a scenario to fit the implementation.**
- **`data-testid` only, owned by page objects** — no raw locator in a step definition, ever.
- Branch **`feature/messaging-s2-admin`** (ruling 11). **Never commit**; leave the tree dirty.

**Scenarios.** Extending `channels.feature`: A channel admin renames a channel · A rename is visible
to everyone in the workspace · An admin archives a channel and it leaves the list · Ada creates a
private channel and only she can see it. New `permissions.feature`: A member without admin rights is
not offered the channel controls · An admin adds a member to a private channel and they can see it ·
Removing a member revokes their view of the private channel · A non-member cannot open a private
channel by its URL.

Every cross-user assertion is after Grace loads the app — real-time is Slice 5, and the step order
must put her load *after* Ada's change, or it asserts on a cached list.

Staying at integration level, never in Gherkin: the **409 version conflict** (ruling 3 — two
browsers racing a `PATCH` is not a scenario anyone can write honestly), the **403** for a non-admin
write (gap 1), the **409** on renaming into a taken name, the **409** last-admin removal, and
**cross-workspace 404s**.

---

## Work

### A. BDD — `tests/bdd/`

- `features/channels.feature` — append the four scenarios above to the existing file. Keep the
  `Background: Given Ada is signed in`. The rename scenarios need a channel first, and
  `Given Ada has created a public channel named "…"` already exists
  (`steps/test_channel_steps.py:54`).
- `features/permissions.feature` — new, the four permission scenarios. Its narrative paragraph
  states the rule the file is about: a public channel is the workspace's, a private channel is its
  members', and administering either takes a channel admin.
- `steps/test_channel_steps.py` — extend for the channels scenarios. **Named `test_*` and calling
  `scenarios("../features/channels.feature")` exactly once** (ruling 6) — it already does both;
  do not add a second call.
- `steps/test_permission_steps.py` — new, with `pytestmark = pytest.mark.bdd`,
  `scenarios("../features/permissions.feature")`. Copy the header and the `_COMPLAINTS`-style
  loose-matching idiom from `test_channel_steps.py`; assert on which rule was reported, not on exact
  copy.
- `pages/chat_page.py` — **one page object for the chat shell** (ruling 6): no second page object
  for the member panel. New methods, all `data-testid` and all synchronous:
  `create_private_channel(name)` · `open_channel(name)` (clicks the sidebar item) ·
  `current_channel_id()` (parses `page.url`; the URL is not a selector but it is still the page
  object's business) · `open_channel_by_id(id)` · `rename_channel(new_name)` ·
  `archive_channel()` (clicks through the confirm) · `has_admin_controls() -> bool` ·
  `member_names() -> list[str]` · `add_member(display_name)` · `remove_member(display_name)` ·
  `channel_error()` — distinct from the existing `error_message()`, which reads the *create form's*
  errors and would silently pass on the wrong element.
- `conftest.py` — **unchanged.** `MESSAGING_TABLES` is S3's to widen (ruling 6); the `ada` / `grace`
  fixtures already cover this slice; no new fixture, and nothing signs out (gap 9).

### B. Backend — `src/services/messaging/messaging/`

- `channels.py` — new domain functions, same idiom as the file already has: `AsyncSession` first,
  keyword-only after, no FastAPI imports, one exception per rule.
  - `VersionConflictError(Exception)` — **defined here, imported by `messages.py` in S4** (ruling 3).
    `LastAdminError(Exception)` — gap 7, modelled on `identities.LastOwnerError`.
    `AlreadyMemberError(Exception)` — mirrors the `ValueError` in `identities.add_member`.
  - `rename(session, *, channel_id, expected_version, name, topic, set_topic)` — validates through
    the existing `validate_name`, so the rename form gets the same `errors.name` map as create;
    catches `IntegrityError` → `DuplicateNameError`, exactly as `create` does (`channels.py:145`);
    guarded `UPDATE` per gap 3. `set_topic` is the `model_fields_set` signal from the router, so
    `topic: null` clears and an absent `topic` is left alone.
  - `archive(session, *, channel_id)` — unconditional, sets `archived_at=func.now()`,
    `updated_at=func.now()`, `version=Channel.version + 1` (ruling 3).
  - `members_page(session, *, channel_id, page)` — keyset on `user_id` alone (gap 6), built with
    `PageRequest.fetch_limit` + `build_page` like `list_page` (`channels.py:178`). Returns
    `ChannelMember` rows; there is nothing to join to.
  - `add_member(session, *, channel_id, user_id, role)` / `remove_member(...)` — `_role` already
    exists (`channels.py:225`) and answers both the duplicate check and the last-admin check;
    `count_admins` alongside it for gap 7.
- `schemas.py` — `UpdateChannelRequest(CamelRequest)` with `name: str | None`, `topic: str | None`,
  and **`version: int` required** (ruling 3: the expected version travels in the body, never as
  `If-Match`). `AddChannelMemberRequest`, `ChannelMemberResponse`, `ChannelMemberListResponse` per
  gap 4. Requests stay `CamelRequest` — the deliberate asymmetry in this file's docstring holds.
- `routers/channels.py` — five routes: `PATCH|DELETE /{channel_id}`,
  `GET|POST /{channel_id}/members`, `DELETE /{channel_id}/members/{user_id}`. Private guards at
  module top beside `_name_problem`: `_visible_or_404(session, principal, channel_id)` and
  `_admin_or_403(visible)`, applied in that order on every write (gap 1). Signature order as the
  file already has it — `page: PageParams`, then `principal: UserPrincipal = Depends(require_user)`,
  then `session: AsyncSession = Depends(db_session)`. Reuse `_NAME_PROBLEMS` for rename.
  **Plain `require_user` on the member writes too** — channel membership is not workspace
  membership, so they are outside the fail-closed set (Conventions §5.2, doc 02 §3.1); reaching for
  `require_user_sensitive` because the word "membership" appears is the mistake this line exists to
  stop. Commit explicitly; the `db_session` dependency does not.
- `openapi.py`, `models.py`, `settings.py`, `db.py`, `main.py`, `alembic/` — **untouched.** No new
  route module, no new setting, **no migration** (ruling 2).
- `tests/test_members.py` — new, `pytestmark = pytest.mark.integration`, driving the `client`,
  `ada`, `grace` and `tokens` fixtures already in `tests/conftest.py`: add and list; add twice →
  409; remove; remove a non-member → 404; remove the only admin → 409; non-admin add → 403; add to a
  private channel and assert Grace's `GET /channels` now contains it and `myRole` is `member`;
  member list on a public channel the caller has not joined → 200 (gap 5); `nextCursor` round-trip
  over `limit=1`.
- `tests/test_channels.py` — extend: rename happy path with `updated_at` strictly greater than
  `created_at` (gap 3); rename with a stale `version` → 409; rename to a taken name, case-folded →
  409; rename breaking a name rule → 400 with `errors.name`; archive, then `GET /channels/{id}` →
  404 and the list no longer contains it; archive twice → 404; non-admin `PATCH` on a visible public
  channel → 403; `PATCH` on a private channel the caller is not in → 404.
- `tests/test_tenancy.py` — extend: a workspace-B token gets 404 (never 403) on `PATCH`, `DELETE`,
  `GET /members` and both member writes against a workspace-A channel.

### C. Frontend — `src/frontend/src/`

- `types/messaging.ts` — **generated, never edited** (ruling 8). Regenerate after the routes land.
- `lib/api/messaging.ts` — `updateChannel`, `archiveChannel`, `listChannelMembers`, `addChannelMember`,
  `removeChannelMember`, following the existing `{ data, error, response }` → `throw problem(...)`
  shape (`messaging.ts:44`). `createChannel` takes `kind` from the caller instead of defaulting it
  in the spread (gap 8).
- `lib/auth/api.ts` — add `workspaceMembers(accessToken, workspaceId)` beside the existing
  `workspaces(...)` (`api.ts:101`). Hand-written like the rest of that file; Auth publishes no
  OpenAPI document. **Subject to the first contract question.**
- `features/channels/useChannels.ts` — add `useRenameChannel` and `useArchiveChannel`. Both
  invalidate `channelKeys.list(workspaceId)` **and** `channelKeys.detail(workspaceId, channelId)`;
  archive additionally navigates to `/` (gap 2). Keys stay in this file, mirroring `channelKeys`
  (`useChannels.ts:16`) and the workspace-id-first rule ruling 7 restates.
- `features/channels/useMembers.ts` — new. `memberKeys.list(workspaceId, channelId)` plus
  `useChannelMembers` / `useAddMember` / `useRemoveMember`, defined here rather than in
  `useChannels.ts` — the same split ruling 7 makes for `useMessages.ts`.
- `features/channels/useWorkspaceMembers.ts` — new, per the first contract question: id → display
  name, key `['workspace-members', workspaceId]`.
- `features/channels/ChannelHeader.tsx` — new, extracted from the inline `<header>` at
  `ChannelView.tsx:60`. Renders name and topic always; the rename form and the archive button
  **only when `channel.myRole === 'admin'`** (gap 1). Rename sends `version` from the cached channel
  (ruling 3) and renders `errors.name` against the field, `detail` in the banner — the split
  `CreateChannelDialog.tsx:26-30` already implements. Archive confirms first (gap 2).
- `features/channels/MemberPanel.tsx` — new, inside `ChannelView`. Lists members with names from the
  workspace-members map; the add picker and the remove buttons render only for an admin. Sorted by
  display name within the page (gap 6).
- `features/channels/CreateChannelDialog.tsx` — the kind control from gap 8.
- `components/ProblemBanner.tsx` — new, the first file in the `/components` folder doc 06 §3
  specifies. Takes an `unknown` caught value, renders `title` and `detail` from a `ProblemError` and
  falls back to `describeError` (`lib/api/client.ts:57`) otherwise. Used by the header, the panel
  and `ChannelView`; it is the "error banner" the delivery plan asks for, in one place rather than
  three.
- **No new Zustand state.** `stores/chat.ts` keeps `activeChannelId` and `drafts`; ruling 7 reserves
  the next addition (`connectionStatus`) for S5, and nothing server-shaped goes in there (D24 🟢).
- **`data-testid` on everything the steps touch:** `create-channel-kind`, `channel-rename-open`,
  `channel-rename-input`, `channel-rename-submit`, `channel-archive`, `channel-archive-confirm`,
  `member-panel`, `member-item` (+ `data-member-name`), `member-add-select`, `member-add-submit`,
  `member-remove` (+ `data-member-name`), `problem-banner`.

### D. Decisions and documents

- `docs/design/02-messaging-service.md` — the writebacks this slice owns under ruling 9, and no
  others: **§3.1** the `PATCH`/`DELETE /channels/{id}` and `/channels/{id}/members*` rows (gaps 2, 4,
  5, 6, 7); **§3.1.1** the 404/403 authority rule (gap 1); **§3.1.3** the three membership DTOs (gap
  4); **§4** the `version` and `updated_at` note (gap 3). Leave §3.1.2, the `Channel` DTO, the
  message rows and every §3.2 row alone — they belong to S1, S3, S4, S5 and S6.
- **No register change and no ADR.** Nothing 🔴 is settled here: D8d is S4's (ruling 9), D16 stays
  open, D28 stays open and this slice adds no stored per-user choice. D8b is unchanged — `dm` stays
  rejected by `CREATABLE_KINDS` (`models.py:42`), and the kind control from gap 8 offers public and
  private only.
- **Do not amend `02-messaging-core-delivery-plan.md`** — ruling 9 gives S7 the single dated
  amendment. The corrections above stay in this plan's "Gaps closed".
- `.env.example` — no new variable; nothing here is configurable.

---

## Verification

```bash
uv run ruff check . && uv run ruff format --check .          # line length 100, py312
uv run pytest -m "not integration and not bdd"               # fast path, no Docker
uv run pytest src/services/messaging src/services/shared     # testcontainers integration

uv run python -m messaging.openapi > src/frontend/openapi/messaging.json   # ruling 8
cd src/frontend && npm run generate:api                      # → src/types/messaging.ts
npm run typecheck && npm run build

docker compose up -d --build                              # the demo stack: SPA :5173
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build   # the throwaway one
uv run pytest tests/bdd -m bdd
uv run pytest tests/bdd -m bdd --headed                      # watch it drive the browser
```

Both stacks, and both need `--build`: the Gherkin runs against the throwaway one on :5183
because it truncates tables between scenarios, and the manual demo below is on the
development stack at :5173. They run side by side on different ports.

No schema change, so no migration step and nothing to run against a live database — `0001_channels`
is still head.

**Manual demo:** sign in at <http://localhost:5173> as `ada@collabhub.dev` / `collabhub`, create
`#general` and rename it to `#general-chat`; create a **private** `#launch-plans`; add
`grace@collabhub.dev` from the member panel; in a second browser profile signed in as Grace, reload
and confirm `#launch-plans` is in her sidebar; remove her, reload again, and confirm it is gone and
that opening its URL directly says the channel does not exist; archive `#general-chat`, reload both
windows, and confirm it is gone from each. **Every cross-window check in this slice is after a
reload** — nothing propagates live until Slice 5.

**Done:** every scenario in `tests/bdd/features/channels.feature` and
`tests/bdd/features/permissions.feature` green headed against the test stack, ruff clean, the
messaging and shared integration suites green, the regenerated OpenAPI document and types committed
to the working tree — and the tree left dirty for you to commit.
