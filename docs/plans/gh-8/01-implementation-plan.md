# One "⋯" menu for message actions — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** Every message that allows an action shows an always-visible "⋯" button, at every width,
in the channel and the thread panel. It opens one menu of exactly the actions the message allows.
The hover-revealed row is gone, and the emoji row closes on Escape and on a tap outside it.

**Architecture:** A pure `offeredActions()` decides what a row offers. That moves the `can*` rules
out of `MessageItem` into one function. A new `MessageActions` component draws "⋯" and an APG menu
button, rendered **in a portal on `document.body` with `position: fixed`**, placed by a pure
`placeMenu()`. The scrolling list and the thread panel therefore cannot clip it. Choosing React
swaps the menu's items for the six-emoji row in the same popup. One menu is open at a time, through
a client-state id in the Zustand chat store (D24). A row whose "⋯" goes away while it holds focus
hands focus to the nearest `[data-focus-fallback]`: the channel's message list, or the thread
panel. `ReactionPicker.tsx` is folded into `MessageActions` and deleted.

**Tech Stack:** React 19.2, TypeScript, Tailwind v4, Zustand, Vitest + Testing Library + user-event
14 · pytest-bdd + Playwright (sync). No new dependency.

**Issue:** `docs/plans/gh-8/00-issue.md` — read it first. This plan argues from it and does not
repeat it.

**Worktree:** `/home/runner/work/claude-at-work-project/caw-gh-8`, branch `feature/gh-8`, from
`main` at `df51879`.

## Decisions

Decided by the issue:

| # | Question | Answer |
|---|---|---|
| 1 | Where actions live | One "⋯" menu at every width. The hover row is removed everywhere, desktop included (*Decided* 1) |
| 2 | Accessible name | "Message actions" (*Decided* 2) |
| 3 | The picker's closing | Escape and outside tap close it, in this issue (*Decided* 3) |
| 4 | Delete | Immediate, no confirmation (*Decided* 4) |
| 5 | Layout | Unchanged. Narrow screens are gh-9 (*Decided* 5) |
| 6 | The record | Doc 06 section, register **D47 🟢**, an ADR (*Record in this slice*) |

Taken in this plan. Rows 7–11 are the choices the issue left to the plan on purpose; rows marked
**assumed** fill gaps:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 7 | Markup | `<button aria-haspopup="menu" aria-expanded aria-controls>` with `role="menu"` and `role="menuitem"` buttons (WAI-ARIA APG menu button) | Req 4 asks for `aria-haspopup`, which promises a menu. A disclosure of plain buttons would need `aria-haspopup` removed |
| 8 | How React opens the emoji | It **replaces the menu's items** with the six emoji in the same popup (`role="menu"`, `aria-label="Add a reaction"`). Focus goes to the first emoji | A submenu needs a second placement and a second focus scope for six buttons. With a swap, Escape and outside-close apply to one popup |
| 9 | Req 5's positioning | A portal into `document.body`, `position: fixed`, at `placeMenu()`'s result. It opens below "⋯" if the menu fits, otherwise above, and is clamped 8px inside the viewport. It is re-placed on any `scroll` (capture) or `resize` while open | An absolutely positioned popup inside the row is clipped by `MessageList`'s `overflow-y-auto` (`MessageList.tsx:300`) and the panel's root box (`ThreadPanel.tsx:161`, `max-h-48 overflow-y-auto`). A positioning library (floating-ui) would be a new dependency for one popup |
| 10 | Keyboard model | Opening focuses the first item. ArrowDown/ArrowUp and Tab/Shift+Tab move to the next/previous item, wrapping. Home and End go to the first and last item. Enter and Space choose (native `<button>`). Escape closes | The issue requires that every item can be reached from the keyboard, and Tab and the arrows both do it. The APG alternative, where Tab closes the menu, would send focus from a portal at the end of `<body>` out of the page. Changing to it is one key branch and one test |
| 11 | The icon | The text glyph "⋯" (U+22EF), `aria-hidden`, inside the labelled button | No icon set in the SPA |
| 12 | One menu at a time | `openMessageMenu: string \| null` in `useChatStore`, holding the open instance's `useId()` | It covers screen-reader activation, which sends a `click` with no `pointerdown`, so the outside-close never fires. Client state, so D24 allows it. `useId` tells the root's two rows (channel and panel) apart |
| 13 | Where focus goes when "⋯" disappears while focused — **assumed** | The nearest ancestor with `data-focus-fallback`: `MessageList`'s scroller (`tabIndex={-1}`) in the channel, the thread panel's `<aside>` (`tabIndex={-1}`) in a thread, via `focus({ preventScroll: true })` | The issue says "the message list". For the thread it does not say which element, and the root sits outside the replies log. Changing it means moving one attribute, plus one test |
| 14 | "Stops allowing the action" — **assumed** | Any change to the offered actions while the menu is open closes it, **compared by value**: the same actions in a new array (every render makes one) are no change, so a live reaction, edit or summary on the message leaves its menu open. Focus goes to "⋯" if "⋯" remains (it is inside the list), otherwise to the fallback (#13) | The case the issue names is a role change that removes Delete. Keeping the menu open with a changed item list would move items under the user's finger. Cost to change: one effect and one test |
| 15 | Focus after an outside press — **assumed** | If focus is in the menu, the `pointerdown` handler first focuses "⋯" (`preventScroll`), then closes. The press's own default then does what the platform does: a press on something focusable (the composer) focuses it; a mouse press on nothing focusable clears focus, as it does anywhere on a page. A touch that starts a scroll has no `mousedown`, so focus stays on "⋯" | Req 4: closing returns focus to "⋯", and the menu never leaves focus on a removed node. Holding focus on "⋯" against a mouse press would need `preventDefault` on every outside `mousedown`, blocking text selection and focus wherever Ada pressed. Cost to change: one listener, one test |
| 16 | A scroll while open — **assumed** | The menu follows its button (re-placed, still clamped to the viewport). It does not close | A new message at the live end scrolls the list programmatically, and closing on it would close Ada's menu every time someone speaks. A touch that *starts* a scroll still closes it, through `pointerdown` (Req 3). A wheel scroll that carries "⋯" out of the list leaves the menu clamped with no "⋯" beside it; Task 9's first run judges it, and closing when "⋯" leaves its scroller's box is the refinement. Closing on scroll instead is one listener change and one test |
| 17 | "⋯" while editing — **assumed** | It stays. Edit chosen again while editing changes nothing | The issue doesn't say. Hiding it would move the header under the editor. Cost: one condition |
| 18 | `ReactionPicker.tsx` | Deleted. The emoji row moves into `MessageActions` and the blur-race note moves into its header. The test ids stay (`reaction-picker` on the React item, `reaction-option` + `data-emoji` on each emoji, `thread-open`, `message-edit`, `message-delete` on the items) | Two components each owning an open state would need two closing rules. Keeping the test ids means the page objects change by one step: open "⋯" first |
| 19 | The touch journey's browser | A function-scoped `ada_touch_context` (1024×768, `has_touch=True`) in `tests/bdd/conftest.py`, like `ada_own_context`. The feature's step module overrides `ada` with it, and `ChatPage(touch=True)` taps instead of clicking | The session contexts are shared, so changing their viewport would change every journey. One more trip through Dex is the cost, paid by one scenario |

Nothing here touches a 🔴 entry. **D20** (React Native vs. PWA) is the nearest, and it stays
open: this is a web control at every width, with no platform split, no service worker and no
native code. D37 and D38 (session) are unrelated.

## Corrections to the issue

None. Every reference in *What exists already* holds at `df51879`. The *assumes* list is checked:

- **jsdom has no layout:** right. Req 5's arithmetic is unit-tested through `placeMenu`. The real
  geometry is checked in a browser (Task 4's page object, and acceptance check 6).
- **Playwright treats `opacity-0` as visible:** right. So Task 4's `_open_actions` asserts the
  button's effective opacity (its own times every ancestor's) is 1 before pressing it. Otherwise a
  hover-gated "⋯" would pass the touch journey.
- **`pointerdown` outside does not race a click inside:** right, provided the test is DOM
  containment against the portal's own node (`menu.contains(target)`), never React's tree. The
  blur race at `ReactionPicker.tsx:8-12` needs a blur handler, and this plan has none. The menu
  closes on `pointerdown` outside, Escape, or a choice, never on blur or `focusout`. Task 2 pins
  the race.

## Test approach — recommendation to the test pair

**TDD, plus the one BDD journey the issue asks for.** Every rule is provable in Vitest; the touch
journey is the browser proof that "⋯" is usable with no hover — an existing journey (reactions,
threads) on a new device. Write the journey and page objects first, then down the pyramid.

| Behaviour | Layer | File |
|---|---|---|
| What each message offers, every `can*` combination | Vitest (pure) | `features/channels/actionRules.test.ts` |
| Below/above/clamp placement, both sides of each boundary | Vitest (pure) | `features/channels/menuPlacement.test.ts` |
| One open id; closing only the one named | Vitest (pure) | `stores/chat.test.ts` |
| Menu button semantics, keyboard, closing, focus, emoji row, the race, one-at-a-time, unmount | Vitest | `features/channels/MessageActions.test.tsx` |
| The row: no hover row, items per role, pending/deleted, Edit focus round trip, keyboard path | Vitest | `MessageItem.test.tsx`, `MessageItem.thread.test.tsx` |
| Live delete / role change with a menu open; pending → confirmed | Vitest, real `MessageList` | `features/channels/MessageList.actions.test.tsx` |
| Thread rows: no Reply; live delete in the panel | Vitest, real `ThreadPanel` | `features/threads/ThreadPanel.test.tsx` |
| Switching channel / closing the thread with a menu open; one menu across list and panel | Vitest, real `ChannelView` | `features/channels/ChannelView.thread.test.tsx` |
| Ada on a touch tablet reacts and replies through "⋯"; Grace sees both live | **BDD** | `tests/bdd/features/message_actions.feature` |
| Every existing journey that edits, deletes, reacts or replies, through "⋯" | BDD (existing) | page objects |

**What no test here covers:** the menu shown in full on **the last message of a long channel** and
**at the thread panel's right edge** in a real browser. `placeMenu`'s unit tests prove the
arithmetic, and Task 4's page object checks the hit-test on every menu the journeys open, but
none of those opens on the last of a scrolled list or on a reply at the panel's edge. **Acceptance
check 6 covers the last message** (the issue's assumption 1). The issue has no check for the
panel's edge: **the acceptance-reviewer measures a reply's menu in the thread panel too**, against
the viewport, and Task 9's first run does it first. Also not covered: what a screen reader announces.

**Baseline**, from `docs/test-report.md` at `56fb009602cc-dirty`: unit 1993 passed (Vitest 568),
end-to-end 25 passed. Expected after: Vitest ≥ 568 plus the new tests, e2e ≥ 26.

## Global constraints

- TanStack Query owns server state. The store gains **client state only**: an id, never a message
  (D24).
- Vitest queries by role, label or text, and adds or reads no `data-testid`. The menu is in a
  portal: query it with `screen`, never `within(row)`.
- `data-testid`s live only in page objects, and a step contains no selector.
- No API, Python service, env var, chart or route change, so no OpenAPI regeneration and no
  Ingress check.
- Nothing writes `CLAUDE.md` or `.claude/`.

## File map

Paths under `src/frontend/src/` are shortened to start at `features/` or `stores/`.

| File | Change | Responsibility | Task |
|---|---|---|---|
| `features/channels/actionRules.test.ts` | create | `offeredActions` | 1 |
| `features/channels/menuPlacement.test.ts` | create | `placeMenu` | 1 |
| `stores/chat.test.ts` | modify | the open-menu id | 1 |
| `features/channels/MessageActions.test.tsx` | create | the menu component | 2 |
| `features/channels/MessageItem.test.tsx` | modify | existing Edit/Delete tests break: they click buttons the menu now holds | 3 |
| `features/channels/MessageItem.thread.test.tsx` | modify | existing Reply tests break the same way | 3 |
| `features/channels/MessageList.actions.test.tsx` | create | live paths through the real list | 3 |
| `features/threads/ThreadPanel.test.tsx` | modify | `:89-115` break (Add a reaction / Edit / Delete as buttons); live delete in the panel | 3 |
| `features/channels/ChannelView.thread.test.tsx` | modify | menu vs. channel switch, thread close, two surfaces | 3 |
| `tests/bdd/features/message_actions.feature` · `steps/test_message_action_steps.py` | create · create | the touch journey | 4 |
| `tests/bdd/steps/conftest.py` · `test_reaction_steps.py` · `test_thread_steps.py` | modify | four phrases move to the shared module | 4 |
| `tests/bdd/conftest.py` | modify | `_signed_in_context(**options)`, `ada_touch_context` | 4 |
| `tests/bdd/pages/chat_page.py` | modify | `touch`, `_press`, `_open_actions`; four actions open "⋯" | 4 |
| `features/channels/actionRules.ts` · `menuPlacement.ts` | create · create | the two pure rules | 5 |
| `stores/chat.ts` | modify | `openMessageMenu`, `openMessageMenuFor`, `closeMessageMenu` | 5 |
| `features/channels/MessageActions.tsx` | create | "⋯", the menu, the emoji row | 6 |
| `features/channels/ReactionPicker.tsx` | **delete** | folded into `MessageActions` | 6 |
| `features/channels/MessageItem.tsx` | modify | hover row out, `MessageActions` in, focus after editing | 7 |
| `features/channels/MessageList.tsx` · `features/threads/ThreadPanel.tsx` | modify | `data-focus-fallback` + `tabIndex={-1}` | 7 |
| `docs/design/06-frontend-spa.md` · `07-open-decisions-register.md` · `docs/adr/261123-one-message-actions-menu-at-every-width.md` · `docs/plans/ch06/gherkin/00-scenario-vocabulary.md` | modify · modify · create · modify | the record | 8 |

**The sweep.** `ReactionPicker` is imported only by `MessageItem.tsx:36`; `MessageItem`'s props and
callers (`MessageList.tsx:327`, `ThreadPanel.tsx:120`) don't change. Breaking tests: a grep for
`'Edit'`, `'Delete'`, `Reply in thread`, `Add a reaction` and the item test ids.
`ChannelView.thread.test.tsx:169`'s `article.parentElement` still finds the scroller. Hover
docstrings: `chat_page.py:352, :391`. No other branch is open. Unchanged: BDD truncation,
`ReactionBar`, `MessageEditor` (its Escape stays).

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–4 | test-writer | failing Vitest tests, each for the reason given. The journey parses and every step binds — **test-reviewer gate** |
| GREEN | 5–7 | code-writer | Tasks 1–3 pass; `tsc` clean |
| Finish | 8–9 | code-writer | the record, then `lint unit` and the whole `e2e` layer |

`tsc` is red from Task 1 until Task 5: the tests name store fields that don't exist yet.

---

## Task 1: The rules (RED)

**Files:** `features/channels/actionRules.test.ts`, `features/channels/menuPlacement.test.ts`
(create); `stores/chat.test.ts` (modify)

**Interfaces** — Task 5 implements these:

```ts
// features/channels/actionRules.ts
export type MessageAction = 'react' | 'reply' | 'edit' | 'delete'
export interface Viewer {
  userId: string
  myRole: string | null
  /** The row can open a thread — `MessageItem` got `onOpenThread`. */
  threads: boolean
}
/** In this order, always: react, reply, edit, delete. Empty for a pending or deleted message. */
export function offeredActions(message: Message, viewer: Viewer): MessageAction[]

// features/channels/menuPlacement.ts
export const MENU_GAP = 4         // px between "⋯" and the menu
export const VIEWPORT_MARGIN = 8  // px the menu keeps from every viewport edge
export interface Box { top: number; bottom: number; left: number; right: number }
export interface Size { width: number; height: number }
export function placeMenu(anchor: Box, menu: Size, viewport: Size): { top: number; left: number }

// stores/chat.ts — added to ChatState
openMessageMenu: string | null                 // initial null
openMessageMenuFor: (menuId: string) => void   // sets it, replacing any other
closeMessageMenu: (menuId: string) => void     // clears it only if menuId is the open one
```

`offeredActions` follows `MessageItem.tsx:85-99` as it is today. For a message that is neither
deleted nor pending: `react` always; `reply` when `threads` and `threadRootId === null`; `edit`
when the viewer is the author; `delete` when the viewer is the author or `myRole === 'admin'`.

`placeMenu`, with V = `VIEWPORT_MARGIN` and G = `MENU_GAP`:

- **Vertical.** Below (`top = anchor.bottom + G`) when `anchor.bottom + G + menu.height ≤
  viewport.height − V`. Otherwise above (`top = anchor.top − G − menu.height`) when that is `≥ V`.
  Otherwise below, clamped to `[V, viewport.height − V − menu.height]`, and `V` if that range is
  empty.
- **Horizontal.** Right-aligned to "⋯" (`left = anchor.right − menu.width`), clamped to `[V,
  viewport.width − V − menu.width]`, and `V` if that range is empty.

**`actionRules.test.ts`.** Expected red for every test: `Failed to resolve import
"./actionRules"`, a load error, and right for all of them, because every test needs the module.
Each case flips one input with the others held true:

| Test | Proves | Fails a build that… |
|---|---|---|
| `your own confirmed message offers react, reply, edit, delete — in that order` | the full set, the order | drops one, or orders by anything else |
| `someone else's message offers react and reply only` | no edit/delete for a member | offers edit to non-authors |
| `a channel admin gets delete, never edit, on someone else's message` | moderation is not forgery | gives admins edit |
| `with threads off — a thread panel row — there is no reply; the same message with threads on has one` | `threads` alone decides | ignores `threads` |
| `a reply in a thread offers no reply even with threads on` | single-level threads | ignores `threadRootId` |
| `a pending message offers nothing, even to its admin author with threads on` | Req 1 | forgets `temp:` |
| `a deleted message offers nothing, even to its admin author with threads on` | Req 1 | forgets `deletedAt` |

**`menuPlacement.test.ts`.** Viewport 1024×768, menu 160×150. Expected red for every test: `Failed
to resolve import "./menuPlacement"`.

| Test | Fixture → expected |
|---|---|
| `opens below "⋯" when it fits, to the pixel` | anchor bottom 606 (606+4+150 = 760 = 768−8) → top 610 |
| `opens above when one more pixel would cross the bottom margin` | anchor top 587, bottom 607 → top 433 |
| `above is taken down to the top margin, and not one pixel past it` | anchor top 162, bottom 700 (below doesn't fit; 162−4−150 = 8) → top 8, above. Anchor top 161, bottom 700 (neither side fits) → clamped, top 610 |
| `a menu taller than the viewport starts at the top margin` | menu height 800 → top 8 |
| `right-aligned to "⋯"` | anchor right 600 → left 440 |
| `held inside the right edge — "⋯" at the thread panel's edge` | anchor right 1020 → left 856 (1024−8−160) |
| `held inside the left edge` | anchor right 100 → left 8 |

**`stores/chat.test.ts`**, appended:

| Test | Expected red |
|---|---|
| `one message menu is open at a time: opening another replaces it` | `openMessageMenuFor is not a function` |
| `closing names its menu: closing another's leaves the open one open` | same |

- [ ] Write the three files, run `npm --prefix src/frontend test -- src/features/channels/actionRules.test.ts src/features/channels/menuPlacement.test.ts src/stores/chat.test.ts`, and record each failure. The store file's existing tests still pass.
- [ ] Leave uncommitted.

## Task 2: The menu component (RED)

**Files:** `features/channels/MessageActions.test.tsx` (create)

**Interface** — Task 6 implements it:

```ts
// features/channels/MessageActions.tsx
interface Props {
  actions: readonly MessageAction[]       // at least one; MessageItem renders nothing for none
  onReact: (emoji: string) => void
  onReply: () => void
  onEdit: () => void
  onDelete: () => void
  /** The "⋯" button, so MessageItem can return focus to it after editing. */
  triggerRef?: Ref<HTMLButtonElement>
}
export function MessageActions(props: Props): JSX.Element
```

The markup that the tests' queries and the page objects match:

- **Trigger.** `<button type="button" aria-label="Message actions" aria-haspopup="menu"
  aria-expanded={open} aria-controls={open ? menuId : undefined} data-testid="message-actions">`
  containing `<span aria-hidden="true">⋯</span>`.
- **Menu**, in a portal on `document.body`: `<div role="menu" id={menuId}
  aria-label="Message actions" data-testid="message-actions-menu" style={{ position: 'fixed', top,
  left }}>`. Its items are `<button role="menuitem">` named **React** (`data-testid="reaction-picker"`),
  **Reply in thread** (`thread-open`), **Edit** (`message-edit`) and **Delete** (`message-delete`),
  in `actions` order.
- **After React:** the same popup becomes `role="menu" aria-label="Add a reaction"`, holding six
  `<button role="menuitem" aria-label={labelFor(e)} data-testid="reaction-option" data-emoji={e}>`
  in `REACTION_EMOJI` order.

Behaviour:

- **Choosing.** A choice closes the menu, focuses "⋯", then calls the handler. Edit's editor then
  takes focus itself (`autoFocus`).
- **Closing.** `pointerdown` on `document` (capture) closes the menu when the target is in neither
  the trigger nor the menu node. If focus is in the menu, it focuses "⋯" first (#15); the press's
  `mousedown` default then moves focus where the platform puts it. **Checked in the installed
  user-event 14.6.7:** `user.click` dispatches `pointerdown`, then `mousedown`, whose default calls
  `focusElement(target)` (`dist/esm/system/pointer/mouse.js:63-75`), which focuses the closest
  focusable ancestor or, with none, blurs to `body` (`dist/esm/event/focus.js:12-23`), as a browser
  does. `fireEvent.pointerDown` alone has no default: it stands for a touch that starts a scroll.
  `keydown` Escape on `document` while open closes and focuses "⋯".
- **Placement.** `useLayoutEffect` measures the trigger and the menu, then applies `placeMenu` with
  `{ width: innerWidth, height: innerHeight }`. It runs again on the swap to emoji, and on `scroll`
  (capture) and `resize`.
- **Actions changing.** A change to `actions`' **contents** while open closes the menu and focuses
  "⋯" (#14). A new array with the same contents is no change: never depend on `[actions]`.
- **Unmount.** The layout-effect cleanup runs `closeMessageMenu(id)`. If `document.activeElement`
  is the trigger or inside the menu, it focuses `trigger.closest('[data-focus-fallback]')`.
  **Checked in the installed `react-dom` 19.2.8**
  (`node_modules/react-dom/cjs/react-dom-client.development.js`): a deleted function component's
  layout destroys run at `:14363-14377` *before* `recursivelyTraverseDeletionEffects` reaches the
  host nodes, which are removed at `:14289-14333`. So the cleanup still sees the focused trigger in
  the document.

Render each case with `renderWithProviders`. Two instances, or an instance inside `<div
data-focus-fallback tabIndex={-1}>`, are rendered together where a test says so. Expected red for
every test: `Failed to resolve import "./MessageActions"`. Each test is one the whole file needs.

| Test | Proves | Fails a build that… |
|---|---|---|
| `"Message actions" is a menu button, collapsed, with no menu until pressed` | Req 4 attributes | lacks `aria-haspopup="menu"` or `aria-expanded` |
| `pressing it opens exactly the given items, in order, and focuses the first` | Req 1, Req 4 | — rendered twice: all four, and `['react']` alone |
| `ArrowDown, ArrowUp, Home, End, Tab and Shift+Tab reach every item, wrapping at both ends` | Req 4 (#10) | traps no Tab, or doesn't wrap |
| `Enter on a focused item chooses it: Delete calls onDelete once, the menu closes, focus is on "⋯"` | keyboard choice | — |
| `each choice closes the menu and returns focus to "⋯"` | Req 3 "after any choice" | `it.each` over Reply, Edit and Delete: each handler once |
| `Escape closes the menu and focus returns to "⋯"` | Req 3, Req 4 | — |
| `a touch that starts a scroll outside closes it, chooses nothing, and focus is on "⋯", not the body` | Req 3 "the touch that starts a scroll", Req 4 (#15) | `fireEvent.pointerDown(outsideDiv, { pointerType: 'touch' })` alone, no click, on a non-focusable `<div>`; focus was on the first item before. Fails a build listening for `click`/`mousedown`, and one that closes without focusing "⋯" (focus falls to `body`) |
| `a press on an outside input closes the menu, chooses nothing and leaves focus in that input` | #15's other side | `user.click(outsideInput)`: fails a build that holds focus on "⋯" against the press (`preventDefault` on `mousedown`), or focuses "⋯" after the press |
| `a pointer-down inside the menu does not close it` | the positive of the above | closes on any `pointerdown` |
| `"⋯" toggles: a second press closes the menu` | the trigger is not "outside" | treats the trigger's `pointerdown` as outside (closes, then the click reopens) |
| `React swaps the items for the six emoji, focus on the first` | Req 2 (#8) | — |
| `picking an emoji calls onReact once with it, closes the row and the menu, focus on "⋯"` | Req 2, *React and closing* | — |
| `a tap on an emoji is not swallowed by the outside-close` | *Closing and the option's click* | `user.click(option)`: the full pointerdown, mouseup and click sequence; `onReact('tada')` called. Fails a containment check against React's tree, or a close on blur |
| `Escape in the emoji row closes both and returns focus to "⋯"` | *React and closing* | — |
| `a pointer-down outside the emoji row closes it and adds no reaction` | Req 3 for the row | — |
| `opening one menu closes another, even with no pointer-down` | Req 3, #12 | two instances: `user.click(A)`, then `fireEvent.click(B)`, as a screen reader activates. Exactly one `menu` in the document, B's. Fails a build with no shared open id |
| `the actions changing while open closes the menu, focus on "⋯"` | #14 | rerender `['react','reply','delete']` → `['react','reply']` |
| `a re-render with the same actions in a new array keeps the menu open and focus where it was` | #14, value not identity | open, ArrowDown to the second item, rerender `['react','reply','delete']` → a fresh `['react','reply','delete']`: the menu is still there and focus is still on Reply in thread. Fails a build whose effect depends on `[actions]` |
| `unmounting with focus on "⋯" or in its menu moves focus to the fallback; with focus elsewhere, leaves it` | *A live delete* (#13) | three cases. The third (focus on an outside input) is the positive that a build which always focuses the fallback fails |
| `unmounting clears its own open id, and not another's` | *Switching channel* | two instances, B open: unmount A → B's menu still open; unmount B → `openMessageMenu` null |
| `the menu sits where placeMenu puts it, and follows a scroll` | Req 5, #16 | `getBoundingClientRect` stubbed: trigger `{top:700,bottom:720,left:990,right:1010}`, menu 160×150 → `position: fixed; top: 546px; left: 850px`. Trigger moved to `{top:300,bottom:320,…}`, then `fireEvent.scroll(scrollerOutsideTheMenu)` → `top: 324px`. jsdom's window is 1024×768: assert that first |

- [ ] Write the file and run it alone: one load error. Record it. Leave uncommitted.

## Task 3: The rows, through their real parents (RED)

**Files:** `MessageItem.test.tsx`, `MessageItem.thread.test.tsx`, `ThreadPanel.test.tsx`,
`ChannelView.thread.test.tsx` (modify); `MessageList.actions.test.tsx` (create)

Shared helpers inside each file, not a new module: `actions(row?)` finds the "Message actions"
button (within the row when one is given); `items()` reads `screen.getAllByRole('menuitem')`'s
names. None of these files imports anything new, so **each test fails on its own**, typically
`Unable to find role="button" and name "Message actions"`. Tests that don't touch actions (author,
time, edited marker, summaries, scrolling) keep passing. The test-reviewer checks that.

**`MessageItem.test.tsx`.** `renderItem` gains an optional `onOpenThread`. The `edit()` and
`remove()` helpers go, because the buttons they query no longer exist outside the menu. Rewritten
and new:

| Test | Expected red |
|---|---|
| `no hover-revealed row: before "⋯" is pressed, no React, Reply, Edit or Delete control is in the document; after, Edit is a menuitem` | assertion: the old row's buttons are in the DOM (jsdom ignores `opacity-0`). The second half fails a row that renders no actions at all |
| `your own message's "⋯" offers React, Reply in thread, Edit, Delete` (with `onOpenThread`) | no "Message actions" |
| `"⋯" on Grace's message offers React and Reply in thread only` | same |
| `a channel admin's "⋯" on someone else's message offers Delete, never Edit` | same |
| `a tombstone has no "⋯" — the live message beside it does` | the positive half: no "⋯" on the live one |
| `a pending message has no "⋯" — the confirmed one beside it does` | same |
| `choosing Edit closes the menu and puts focus in the editor` | no "⋯" |
| `editing through the menu sends the version it holds; after Enter, focus is on "⋯" and no menu is open` | same — *Edit and the menu*; also fails a build whose Enter reopens the menu |
| `Escape in the editor cancels; focus returns to "⋯" and the menu stays shut` | same |
| `Delete in the menu asks for a delete once` | same |
| `keyboard only: Tab reaches "⋯", Enter opens it, ArrowDown reaches Reply in thread, Enter opens the thread` | `user.tab()` lands on nothing named "Message actions" — the *Paths* keyboard row |

**`MessageItem.thread.test.tsx`.** `replyAction(row)` becomes: open that row's "⋯", then
`queryByRole('menuitem', { name: 'Reply in thread' })`. Each guard keeps its positive: the confirmed
row offers Reply first. Expected red: no "Message actions". The summary tests are untouched.

**`MessageList.actions.test.tsx`** — the real `MessageList`, stubbed and rendered as
`MessageList.test.tsx:21-42` does, with Grace's message in history and `myRole: 'admin'` for Ada.
Cache writes go through `upsertMessage` / `removeMessage` from `useMessages`, which are the
helpers the socket handlers and the send path use:

| Test | Path | Expected red |
|---|---|---|
| `Grace's delete lands while Ada's menu is open: the tombstone has no "⋯", no menu is open, and focus is on the message list, not the body` | *A live delete* | no "⋯" to open |
| `Ada's admin role ends while her menu offers Delete: the menu closes and focus is on that message's "⋯"` | *stops allowing the action* (#14) | same. Rerender with `myRole: null` |
| `a live reaction, then a live edit, to the message leave its open menu open, focus on the item it was on` | #14 by value, through the real row | same. `upsertMessage` Grace's message with a reaction added, then with a new body and `editedAt`; after each the menu is there and focus is on its second item. Fails a build that closes on any re-render |
| `a pending message has no "⋯"; once confirmed, it does` | *Paths: pending, then confirmed* | `upsertMessage` a `temp:` row: no "⋯" (passes before green, and stays as a guard). Then `removeMessage` + `upsertMessage` with the confirmed row: "⋯" — fails here |

The message list is the element whose child is the article, as `MessageList.test.tsx:51` finds it.

**`ThreadPanel.test.tsx`.** `:89-105` and `:107-115` are rewritten to go through "⋯". The root's
"⋯" offers React, Edit and Delete and no Reply; a reply's "⋯" offers no Reply, with the positive
that Ada's own reply offers Edit. New:
`a reply deleted while its menu is open: no menu, and focus is on the thread panel`, using
`upsertThreadMessage` with a tombstone. Expected red: no "Message actions".

**`ChannelView.thread.test.tsx`**, appended to the describe block (real timers, `fireEvent`, as the
file does):

| Test | Path | Expected red |
|---|---|---|
| `closing the thread with a reply's menu open leaves no menu open anywhere` | *Paths: closing the thread* | no "⋯" in the panel |
| `switching channel with a menu open leaves no menu, and none on the next view` | *Paths: switching channel* | no "⋯" on `root B` |
| `a menu opened in the thread panel closes the one open in the channel` | Req 3 across surfaces | no "⋯" |

Each test finds the menu open first, so "no menu" cannot pass for a build that never opens one.

- [ ] Write the changes. Run `npm --prefix src/frontend test -- src/features/channels/MessageItem.test.tsx src/features/channels/MessageItem.thread.test.tsx src/features/channels/MessageList.actions.test.tsx src/features/threads/ThreadPanel.test.tsx src/features/channels/ChannelView.thread.test.tsx` and record each failure against the tables.
- [ ] Leave uncommitted.

## Task 4: The touch journey and the page objects (RED)

**Files:** `tests/bdd/features/message_actions.feature`, `steps/test_message_action_steps.py`
(create); `steps/conftest.py`, `steps/test_reaction_steps.py`, `steps/test_thread_steps.py`,
`tests/bdd/conftest.py`, `pages/chat_page.py` (modify)

```gherkin
@bdd
Feature: Message actions

  Everything you can do to a message — react, reply in a thread, edit, delete —
  is behind one "⋯" button that is always there, so a touch screen with no hover
  can do all of it. The menu offers only what that message allows.

  Background:
    Given Ada is signed in

  # Touch and no hover, through to Grace's window; the rules are proven in Vitest.
  Scenario: On a touch screen, Ada reacts to Grace's message and replies in its thread
    Given Ada has created a public channel named "general"
    And Grace has sent "lunch at noon?" in "general"
    When Ada reacts to "lunch at noon?" with "tada"
    Then Grace sees "lunch at noon?" with 1 "tada" reaction
    When Ada replies "count me in" in the thread on "lunch at noon?"
    Then Grace sees 1 reply on "lunch at noon?" without reloading
```

**Phrases** reused verbatim: `Ada is signed in`, `Ada has created a public channel named`
(`steps/conftest.py`); `Ada reacts to "{body}" with "{emoji}"`, `Grace sees "{body}" with {count:d}
"{emoji}" reaction` (`test_reaction_steps.py:44, :52`); `Ada replies "{reply}" in the thread on
"{body}"`, the `Grace sees N repl(y|ies) on "…" without reloading` regex (`test_thread_steps.py:27, :42`).

pytest-bdd resolves steps from the calling module and `conftest.py` only (`steps/conftest.py:3-7`),
so **those four definitions move, unchanged, into `steps/conftest.py`** and are deleted from their
modules. Then `reactions.feature` and `threads.feature` still bind.

**New, in `test_message_action_steps.py`:**
`@given(parsers.re(r'Grace has sent "(?P<body>[^"]*)" in "(?P<channel>[^"]*)"'))`. It runs
`grace.open()`, `open_channel(channel)`, `wait_for_channel_joined()` (so the reaction and the reply
reach her live), then `send_message_and_wait(body)`.

**The touch tablet:**

- **`tests/bdd/conftest.py`.** `_signed_in_context(browser, base_url, email, **options)` passes the
  options to `browser.new_context(**options)`. Add `TOUCH_TABLET = {"viewport": {"width": 1024,
  "height": 768}, "has_touch": True}` and a function-scoped `ada_touch_context` beside
  `ada_own_context`, with a docstring giving decision 19's reason.
- **`test_message_action_steps.py`.** Overrides `ada` for this feature only. A module-level fixture
  beats the conftest one for the tests `scenarios()` generates there:
  `ChatPage(ada_touch_context.new_page(), base_url, touch=True)`, closing the page on teardown.

**`chat_page.py`:**

- **`ChatPage(page, base_url, touch: bool = False)`**.
- **`_press(locator)`.** `locator.tap()` if `self.touch`, else `locator.click()`. `Locator.tap()`
  throws unless the context has `has_touch` (installed `playwright/sync_api/_generated.py:20186-20216`),
  hence the flag.
- **`_open_actions(item) -> Locator`.**
  1. The item's `message-actions` button has an **effective opacity of 1**, its own times every
     ancestor's, checked with `page.wait_for_function` over the element handle, as
     `has_inline_image` does. This runs before anything hovers.
  2. `_press` the button.
  3. `message-actions-menu` is visible, and its four corners, inset 2px, each hit-test
     (`document.elementFromPoint`) to a node inside the menu. That is Req 5 at this scale: a clipped
     or covered menu fails.
  4. Return the menu.
- **`react_to`** → `_open_actions`, `_press` the `reaction-picker` item, then `_press` the
  `reaction-option[data-emoji]` — then waits for the chip, as now. **`reply_in_thread`** →
  `_open_actions` on the channel item, then `_press` `thread-open`. **`edit_message`** /
  **`delete_message`** → `_open_actions`, then `_press` `message-edit` / `message-delete`.
- The two hover docstrings (`:352`, `:391`) are rewritten to say "⋯" opens the actions, at every
  width.

Expected red, which cannot run before the code-writer:

`uv run pytest tests/bdd --collect-only -q` collects the new scenario, and `uv run pytest
tests/bdd --generate-missing --feature tests/bdd/features` prints nothing. Under `e2e` before GREEN, the new scenario, and the existing *Ada edits her own message…*,
  *Ada deletes her own message…*, *Ada's edit/delete propagates…*, *Grace sees Ada's reaction…* and
  *Grace sees Ada's reply in a thread…*, all time out in `_open_actions` waiting for
  `message-actions`.

- [ ] Write the changes and run the two commands above. Leave uncommitted.

---

## Task 5: The rules (GREEN)

**Files:** `actionRules.ts`, `menuPlacement.ts` (create); `stores/chat.ts` (modify)

- [ ] `offeredActions` and `placeMenu` to Task 1's interfaces. Docstrings carry the reasons (the
  `can*` notes move from `MessageItem.tsx:16-21, :86-98`).
- [ ] The store's three members, with a doc comment: client state, an instance id and never a
  message (D24).
- [ ] Task 1 passes; typecheck is clean for these files. Leave uncommitted.

## Task 6: The menu (GREEN)

**Files:** `MessageActions.tsx` (create); `ReactionPicker.tsx` (`rm`)

- [ ] `MessageActions` to Task 2's interface and markup. `createPortal(menu, document.body)` only
  while open. `useId()` is both the store key and the menu id. `className` uses the theme tokens
  `ReactionPicker` used (`border-border bg-surface shadow`) and `z-50`.
- [ ] Listeners (`pointerdown`/`keydown` on `document`, `scroll` capture/`resize` on `window`)
  exist only while open. The header comment carries the blur race from `ReactionPicker.tsx:8-12`: why closing is
  `pointerdown`-outside and never blur. Then delete `ReactionPicker.tsx`.
- [ ] Task 2 passes. Leave uncommitted.

## Task 7: The rows (GREEN)

**Files:** `MessageItem.tsx`, `MessageList.tsx`, `ThreadPanel.tsx`

- [ ] `MessageItem`:
  - Delete the hover `<span>` (`:135-167`) and `group` from the article's class.
  - Compute `const actions = offeredActions(message, { userId, myRole, threads: onOpenThread !==
    undefined })`.
  - Render `{actions.length > 0 && <MessageActions …/>}` at `ml-auto` in the header line, with
    `onEdit={() => setEditing(true)}` and `onReply={onOpenThread}`.
  - Keep a `useRef<HTMLButtonElement>` as `triggerRef`. An effect focuses it when `editing` goes from
    `true` to `false` (a ref remembers the previous value), never on mount.
  - Update the header comment: actions are behind "⋯", and `offeredActions` is the rule.
- [ ] `MessageList`'s scroller (`:296-301`) and `ThreadPanel`'s `<aside>` (`:136-140`) get
  `data-focus-fallback` and `tabIndex={-1}`.
- [ ] Task 3 passes, all of Vitest passes and typecheck is clean. Leave uncommitted.

## Task 8: The record

- [ ] **Doc 06 §5.2:** a new block, **Message actions — added 2026-11-23** (register D47), after
  *Threads*: one "⋯" at every width and `offeredActions`; markup and keyboard (#7, #10); React's
  swap (#8); the portal and `placeMenu` (#9, #16); closing (pointerdown outside, Escape, a choice;
  never blur); one at a time (#12); focus in on open, back to "⋯" on Escape, a choice, an outside
  press (#15) or after editing, to `data-focus-fallback` when "⋯" goes (#13, #14).
- [ ] **Register:** D47 in *Frontend SPA*: 🟢 **Decided (2026-11-23, issue gh-8):** message actions
  behind one "⋯" menu at every width. Name what was built against it, and link the ADR.
- [ ] **ADR** `docs/adr/261123-one-message-actions-menu-at-every-width.md`, with the `adr-writer`
  skill's template. The decision is one menu at every width rather than hover on desktop and
  something else on touch. The alternatives are hover plus long-press, and a per-width split.
- [ ] **Vocabulary:** §35 in `docs/plans/ch06/gherkin/00-scenario-vocabulary.md`, in the shape of
  §33–34. It lists the phrases reused and the one new phrase, and the four definitions moved to
  `steps/conftest.py`.
- [ ] **Sweep:** `grep -rn "hover\|ReactionPicker" src/frontend/src docs/design tests/bdd` finds
  nothing stale.
- [ ] Leave uncommitted.

## Task 9: Verification

- [ ] `scripts/test.sh lint unit`, then `scripts/test.sh e2e` — each once. Green, with Vitest ≥ 568
  plus the new tests and e2e ≥ 26. No `integration`: no service's Python, SQL or stream changes.
  `e2e` runs whole because every journey that edits, deletes, reacts or replies goes through "⋯".
- [ ] `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)` and
  `.claude/hooks/security.sh`.
- [ ] **First real run** on the Compose stack, in Chromium's touch emulation at 1024×768: "⋯" on
  the last message of a scrolled channel and on a reply at the panel's right edge (each menu
  whole); start a scroll with a menu open (it closes); on desktop, wheel-scroll "⋯" out of the
  list with its menu open and judge #16; acceptance check 3 by keyboard. Fix anything found with a
  test, and record it below.
- [ ] Fill in *Found while building*; leave the worktree dirty.

## Found while building

- No departure from the plan. Every GREEN task went green on its first build: 620 Vitest tests, `tsc` clean, e2e 26 of 26 (the touch journey and the five reworked ones).
- Test-reviewer minors: no `onBlur`/`focusout` handler exists (finding 2); the menu uses `rounded-md` so the page object's four-corner hit test, inset 2px, stays inside the border (finding 3); the unmount "focus elsewhere" half is not relied on (finding 1).
- The unmount cleanup finds the menu with `document.getElementById(id)` rather than a ref, because the menu node exists only while open and a ref read in a cleanup trips `react-hooks/exhaustive-deps`.
- Task 9's by-hand first run (last message of a scrolled channel, a reply at the panel's edge, #16's wheel scroll) was not done: no person at a browser. Left for the human and the acceptance-reviewer. No test for it.

## Not in this plan

Anything below 768px (gh-9); a delete confirmation; long-press or swipe; a PWA (D20); opening the
menu with ArrowDown on "⋯" (APG's optional extra — Enter and Space do it).

## Self-review

| Issue item | Tasks | Tests |
|---|---|---|
| Req 1 | 1, 3, 5, 7 | actionRules ×7, MessageItem ×6, ThreadPanel, journey |
| Req 2 | 2, 6 | the emoji tests |
| Req 3 | 2, 3, 5 | outside / Escape / choice / one-at-a-time; ChannelView ×3 |
| Req 4 | 2, 3 | semantics, keyboard, focus, MessageItem keyboard path |
| Req 5 | 1, 2, 4 | placeMenu ×7, the placement test, `_open_actions` hit-test; acceptance 6 and the panel-edge measurement |
| *A live delete* | 2, 3 | MessageList.actions, ThreadPanel |
| *Edit and the menu* | 3 | MessageItem |
| *React and closing* | 2 | the emoji tests |
| *Closing and the option's click* | 2 | the race test |
| *The thread panel* | 3 | ThreadPanel, actionRules |
| *Paths* | 2, 3 | one test per row; the last message goes to acceptance |
| *Decided* 1–5 | Decisions 1–5 | |
| *Record* | 8 | |

**Names** are Task 1's and Task 2's throughout. Every existing test that breaks is RED work (Tasks 3, 4).

## Review responses

Round 1 (`reviews/plan-reviewer-1.md`):

1. **Fixed.** #15 rewritten: on an outside `pointerdown` with focus in the menu, "⋯" is focused first, then the press's default applies (user-event's behaviour checked at `mouse.js:63-75`, `focus.js:12-23`, cited in Task 2). Two tests replace the old one: a touch-scroll `pointerDown` alone ends on "⋯", not `body`; `user.click` on an outside input ends in that input. A mouse press on nothing focusable clears focus as a browser does: recorded in #15 with the `preventDefault` alternative.
2. **Fixed.** #14 and Task 2 say the comparison is by value, never `[actions]`. New tests: Task 2's same-contents rerender keeps the menu and focus; `MessageList.actions`' live reaction then live edit through `upsertMessage` leaves the open menu open.
3. **Fixed.** The no-hover-row test now opens "⋯" and finds Edit as a menuitem.
4. **Fixed.** *What no test covers* credits check 6 with the last message only, and asks the acceptance-reviewer to measure a reply's menu at the panel's edge.
5. **Kept #16**, with the detached-menu case and the refinement named in it; Task 9's first run wheel-scrolls "⋯" out of the list and judges it.
