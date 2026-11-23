# Red tests — gh-8, round 1

TDD down the pyramid plus the plan's one BDD journey. Seven Vitest files (three new pure/component
files, one new real-list file, four existing files rewritten or extended) and one touch-device
journey with its page-object changes. Every new or rewritten Vitest test fails (28 failures in the
five files that load, 3 files fail to load as planned); the journey parses and every step binds.
Nothing was green by accident.

## Baseline
Run before any change (`npm --prefix src/frontend test -- <5 files>`): **5 files, 49 tests passed**
— `stores/chat.test.ts`, `MessageItem.test.tsx`, `MessageItem.thread.test.tsx`,
`ThreadPanel.test.tsx`, `ChannelView.thread.test.tsx`.
After: the 9 files (those 5 plus `actionRules`, `menuPlacement`, `MessageActions`,
`MessageList.actions`): **9 files failed; 28 tests failed, 35 passed (63 run)**; the three load-error
files report no tests. Of the 35 passing, every one is an existing test the plan leaves alone
(author/time/edited marker, summaries, scrolling, the old store tests, the panel's other tests, the
other thread-panel tests) or a `MessageItem` row test that never touched actions. No existing
untouched test changed result.
BDD baseline: 25 scenarios collected; now **26** (the new one).

## Tests
Observed red is the first failure line of each, from `npm --prefix src/frontend test`.

| File · test | Layer | Plan task | Proves | Expected red (plan) | Observed red (verbatim) | Match |
|---|---|---|---|---|---|---|
| `actionRules.test.ts` · all 7 | Vitest | 1 | the offered set, order, each input alone, pending, deleted | load error | `Error: Failed to resolve import "./actionRules" from "src/features/channels/actionRules.test.ts"` | yes |
| `menuPlacement.test.ts` · all 7 | Vitest | 1 | below/above/clamp, both sides of each boundary, left/right | load error | `Error: Failed to resolve import "./menuPlacement" …` | yes |
| `chat.test.ts` · one message menu is open at a time… | Vitest | 1 | replaces | `openMessageMenuFor is not a function` | `AssertionError: expected undefined to be null` | **differs** — the test first asserts the initial `null`, which is `undefined` today; still red for the missing field |
| `chat.test.ts` · closing names its menu… | Vitest | 1 | only the named closes | same | `TypeError: openMessageMenuFor is not a function` | yes |
| `MessageActions.test.tsx` · all 24 (incl. `it.each` ×3) | Vitest | 2 | the menu component | load error | `Error: Failed to resolve import "./MessageActions" from "src/features/channels/MessageActions.test.tsx"` | yes |
| `MessageItem.test.tsx` · no hover-revealed row… | Vitest | 3 | old row gone, Edit a menuitem | assertion: old buttons in DOM | `AssertionError: expected [ <button …(5)></button>, …(3) ] to have a length of +0 but got 4` | yes |
| `MessageItem.test.tsx` · own / Grace / admin "⋯" offers… (3) | Vitest | 3 | items per role | no "Message actions" | `TestingLibraryElementError: Unable to find an accessible element with the role "button" and name "Message actions"` | yes |
| `MessageItem.test.tsx` · tombstone has no ⋯ / pending has no ⋯ (2) | Vitest | 3 | guards + live positive | positive half fails | same `Unable to find … "Message actions"` (on the live row first) | yes |
| `MessageItem.test.tsx` · choosing Edit; editing…; Escape in editor; Delete; keyboard only (5) | Vitest | 3 | focus round trip, version, keyboard path | no "⋯" | same `Unable to find … "Message actions"` | yes |
| `MessageItem.thread.test.tsx` · top-level offers Reply, which opens it | Vitest | 3 | open then Reply | no "Message actions" | same `Unable to find …` | yes |
| `MessageItem.thread.test.tsx` · none on pending / deleted / reply / without onOpenThread (4) | Vitest | 3 | guards, each with its positive on the confirmed row | no "Message actions" | `Error: expect(received).toBeInTheDocument()` — `received` is `null`, from the confirmed row's positive half | yes (reason: confirmed row has no "⋯") |
| `MessageList.actions.test.tsx` · all 4 | Vitest | 3 | live delete, role end, reaction+edit leave open, pending→confirmed | no "⋯" | `Unable to find an accessible element with the role "button" and name "Message actions"` | yes |
| `ThreadPanel.test.tsx` · root has reactions…, replies offer no Reply, reply deleted while menu open (3) | Vitest | 3 | panel rows | no "Message actions" | same | yes |
| `ChannelView.thread.test.tsx` · closing thread / switching channel / one menu across surfaces (3) | Vitest | 3 | unmount paths, cross-surface | no "⋯" | same | yes |
| `message_actions.feature` · On a touch screen… | BDD | 4 | touch react + reply | cannot run | see BDD | n/a |

Every behaviour test is red for its stated reason or earlier than the one it exists to pin; those
that stop at the first `Unable to find … "Message actions"` have not yet reached their pinned
half — the code-writer's green run is what exercises them. Each "wrong build" per test is the one in
the plan's table; the ones I added are listed under *Departures*.

**Wrong builds the pinning halves fail** (the plan's, as written into the tests):
- `fireEvent.pointerDown` alone on a `<div>`, focus before: a build that closes without focusing "⋯"
  (focus falls to `body`), or listens for `click`/`mousedown`.
- `user.click(outsideInput)`: a build that holds focus on "⋯" (`preventDefault` on `mousedown`) or
  refocuses "⋯" after the press.
- Same-contents rerender with focus on the second item: a build whose effect depends on `[actions]`.
- Two instances, `fireEvent.click(B)` with no pointer-down: a build with no shared open id (two menus).
- Third unmount case (focus on an outside input): a build that always focuses the fallback.
- Unmount A with B open: a build whose cleanup clears the store unconditionally; unmount B: a build
  that never clears.
- "⋯" toggles: a build that treats the trigger's own `pointerdown` as outside (closes, then reopens).
- Placement: a build that places once and ignores scroll; a menu not `position: fixed`.

## Types
`npm --prefix src/frontend run typecheck`: 18 errors, all expected —
`Cannot find module './actionRules'` (×2), `'./MessageActions'`, `'./menuPlacement'`
(missing modules), and `Property 'openMessageMenu' | 'openMessageMenuFor' | 'closeMessageMenu' does
not exist on type 'ChatState'` in `chat.test.ts`, `MessageActions.test.tsx` and
`ChannelView.thread.test.tsx`. Nothing else.

## BDD
- `uv run pytest tests/bdd --collect-only -q` → **26 tests collected**, including
  `test_message_action_steps.py::test_on_a_touch_screen_ada_reacts_to_graces_message_and_replies_in_its_thread`;
  the 25 old ones still collect (the four moved steps resolve from `steps/conftest.py`).
- `uv run pytest tests/bdd --generate-missing --feature tests/bdd/features` → prints no stubs: every
  step binds.
- `ruff check` / `ruff format --check` on `tests/bdd`: clean.
- **Expected red under `e2e` before green** (cannot run here): the new scenario, and the existing
  *Ada edits her own message…*, *Ada deletes her own message…*, *Ada's edit/delete propagates…*,
  *Grace sees Ada's reaction…* and *Grace sees Ada's reply in a thread…* all time out in
  `_open_actions` at `expect(button).to_be_visible()` — no `message-actions` test id exists.
  After green, the new scenario's first failure would be the effective-opacity check, then the
  four-corner hit test, if "⋯" were hover-gated or the menu clipped.

## Departures from the plan
- **No tests dropped, none moved layer.** Every named test exists under the plan's name, or one
  that says the same.
- **Added:** `MessageActions.test.tsx` · `is in a portal on the document body, not inside the
  component's own node` (Req 5's portal as a unit fact: fails an in-row popup, which the list would
  clip). `MessageItem.thread.test.tsx`'s `none on a reply` also asserts Ada's own reply *has* a "⋯"
  with Edit, and `without onOpenThread` asserts the menu holds Delete — so `null` cannot come from a
  build with no menu. `ThreadPanel.test.tsx`'s `replies offer no Reply` adds Grace's reply
  (menu: React only) beside Ada's (React, Edit, Delete), so the two menus differ.
- **chat store test 1** asserts the initial `null` first, so it fails with an assertion, not
  `is not a function` (see table). The second fails as planned.
- **MessageList.actions**: Ada has no `onOpenThread` there, so her menu on Grace's message holds
  React and (admin) Delete; the role test removes Delete. The "pending" test passes its first half
  only after the positive (Grace's row has "⋯"), so it is red for the missing "⋯" and not a guard
  that passes alone.
- **`ChannelView.thread`**: the channel-switch test goes back to `general` after `random` to check
  "none on the next view" with a row that exists; the third test asserts `aria-controls` equals the
  open menu's `id`, since the menu is in a portal and `within(panel)` can't find it.
- Menu items and the emoji row are queried by role and accessible name only; no `data-testid` is
  read in Vitest. The reaction menu items use `aria-label` names (`thumbs up`, `heart`, `celebrate`,
  `smile`, `eyes`, `check`) from `reactions.ts`'s `labelFor`, as the plan's markup gives.
- Step phrase `Grace has sent "…" in "…"` is defined in `test_message_action_steps.py` as the plan
  says; `Ada has sent` in `steps/conftest.py` is unrelated and unchanged.

## Picked up from earlier reviews
- plan-reviewer-2, *Left for later stages*, test-writer: the outside-input test uses `user.click` (so
  `mousedown`'s default runs), and the touch test uses `fireEvent.pointerDown` alone on a
  non-focusable `<div>`. Done as written.
- The #15 mouse-press-on-nothing case is not tested (it is assumed behaviour: focus ends on `body` as
  a browser does); no test asserts either way, so no `preventDefault` build is encouraged.
- Acceptance-reviewer items (panel-edge measurement) are not mine.

## For the code-writer
- `MessageActions` must read `getBoundingClientRect()` of the trigger (`aria-haspopup="menu"`) and
  the menu (`role="menu"`) — the placement test stubs exactly those two — and set inline
  `style.position='fixed'`, `style.top`, `style.left` in px on the `role="menu"` node. It must
  re-place on a `scroll` event fired on any element outside the menu (captured at `window`).
- The menu must be the `role="menu"` node with `id` = the trigger's `aria-controls` while open; the
  emoji row is `role="menu"` named "Add a reaction" with items named by `aria-label`
  (`labelFor`), `React` item text content `React`, others `Reply in thread`, `Edit`, `Delete`.
  The item tests read `textContent`, so the visible text must be exactly that (glyph `⋯` only
  inside the trigger).
- Tab/Shift+Tab must `preventDefault` and cycle inside the menu (user-event only moves focus on Tab
  when the keydown isn't default-prevented).
- `MessageList.actions` expects, on a live delete, focus on `[data-focus-fallback]` = the
  message list's scroller (the article's parent); `ThreadPanel.test` expects the `<aside>`
  (`role=complementary`, "Thread") to hold focus, so it needs `tabIndex={-1}`.
- `MessageItem` must refocus "⋯" (not reopen the menu) after Enter-save and after Escape in the
  editor, and focus the editor when Edit is chosen.
- A `temp:` row and a tombstone render no "⋯" at all (not a disabled one): tests assert absence.
- Stale state: `useChatStore.openMessageMenu` is reset between tests by `setup.ts`; no extra reset
  needed.
- `ReactionPicker.tsx` is not referenced by any test; `grep` showed no test imports it, so deleting
  it breaks nothing.
