# Plan review — gh-8, round 1: changes_requested

A careful plan: every reference checked out, the react-dom and Playwright claims hold in the
installed versions, and nearly every expectation is settled in a decision row. Two majors
remain, both in `MessageActions`' closing rules. After an outside tap, focus is left inside a
menu that has just been removed, so it falls to the page body. And nothing proves that a
re-render with the same actions keeps the menu open. Both can be fixed from this review.

## Expectations                 (round 1 — written before the plan was opened)

Read first: the issue, `MessageItem.tsx`, `ReactionPicker.tsx`, `MessageEditor.tsx`,
`ThreadPanel.tsx`, `MessageList.tsx` (:285-359), doc 06 *Threads* (:336-365), register D20
and the register's tail (D46 is the last entry), `tests/bdd/pages/chat_page.py` (:296-402),
`tests/bdd/conftest.py` (:259, :342), the Vitest files that click the row's buttons, and the
frontend's `package.json` (no popover/floating library installed; user-event 14.6.7).

### Decisions
- D1. React from the menu — a submenu, or the emoji row replacing the menu's items? (left
  to the plan by the issue; must be a row.)
- D2. Markup and keyboard model: `role="menu"`/`menuitem` with roving arrow keys, or a
  disclosure of plain buttons reached by Tab? Req 4 says "every item can be reached and
  chosen from the keyboard" — which keys, and does Tab out of the menu close it?
- D3. Where does focus land on open — the first item? On closing by an outside tap, does
  focus return to "⋯" (Req 4 "closing it returns focus") or stay where the tap went?
- D4. After **Reply in thread** — the menu closes after a choice; does focus return to "⋯"
  (Req 4 literally) or move into the thread panel? Nothing in the SPA focuses the thread
  composer today (no `autoFocus` outside `MessageEditor`).
- D5. After **Delete** of one's own message — delete is not optimistic (`useMessages.ts`
  has no `onMutate` for it), so focus returns to "⋯", which then unmounts when the
  tombstone lands. Is this the same "focus moves to the message list" rule as a live
  delete by Grace? And for a refused delete (the list's `ProblemBanner`)?
- D6. "Focus moves to the message list" — `data-testid="message-list"` is a plain
  `div` with no `tabIndex`; what element, made focusable how? In the **thread panel**,
  which list — the `Replies` log, the root's box, or the panel?
- D7. "The same holds if the message stops allowing the action Ada was about to choose"
  — does the menu close whenever the set of allowed actions changes, or only drop the
  item? (Today the only live change that removes an action is a delete; a role change
  could remove Delete.)
- D8. Req 5 positioning with no library: fixed/portal positioned from
  `getBoundingClientRect`, the Popover API, or CSS anchor positioning? What happens on
  scroll or resize while open (Req 3 closes on the touch that starts a scroll, but a wheel
  scroll or keyboard scroll isn't a pointerdown)? Flip above when below doesn't fit?
- D9. "One open at a time" across channel list and thread panel — state where? (Zustand
  is client state, allowed; or a context.) Does a single owner also make D7/switch-channel
  close fall out?
- D10. Outside close on `pointerdown` vs the option's `click` — capture phase on
  `document`, containment check including the portal if the menu is portaled.
- D11. Icon and the testids the page objects and BDD step will use.

### Conflicts
- C1. Req 4 "closing returns focus to ⋯" against *Where the rules meet* "a live delete …
  Ada's focus moves to the message list" — the plan must say which wins when "⋯" is gone.
- C2. Req 4 "closing returns focus" against choosing Reply in thread (focus into the
  panel?) and choosing Delete (D5).
- C3. Req 3 "close on the touch that starts a scroll" against Req 5 "always in full in the
  viewport" for scrolls that aren't a pointerdown (wheel, keyboard) — reposition, or close?
- C4. ReactionPicker's header ("not on blur") against outside-close — the plan must say
  why `pointerdown`-outside doesn't reintroduce the race (issue's assumption 3).

### Tests
- Vitest per `can*` combination: other's message (React, Reply), own (all four),
  admin on other's (React, Reply, Delete), thread row (no Reply), pending → none then
  "⋯" once confirmed, deleted → none. Exactly the items — a test that asserts presence
  only would pass with an extra item.
- No "⋯" on a pending/deleted message must prove the positive in the same test.
- Closing: Escape, outside `pointerdown` (positive: an inside pointerdown on an option
  still toggles the reaction — the race), after each choice. Each with focus asserted.
- One open at a time — across a channel row and a thread row, not just two channel rows.
- Focus: open moves focus inside; Escape returns to "⋯"; Edit → save returns to "⋯"
  and the menu not reopened; Edit → Escape in the editor the same.
- Live delete while open: menu closes, focus on the list, not `document.body`
  (positive: focus was inside the menu before).
- Emoji row: Escape closes row and menu, focus to "⋯"; pick closes both and toggles.
- Switch channel / close thread with a menu open → nothing open after.
- Existing tests that break: `MessageItem.test.tsx` (:38-39, :126, :137),
  `MessageItem.thread.test.tsx` (:54, :61), `ThreadPanel.test.tsx` (:98-114) — RED work,
  rewritten by the test-writer, never the code-writer.
- BDD: one touch journey on a 1024×768 `has_touch` context — a new context fixture, since
  both contexts are `browser.new_context()`; last step must show the server (Grace sees
  the reaction, the reply is confirmed). Req 5 proven in a real browser (BDD or
  acceptance), with a bounding-box check.
- Page objects: `react_to`, `reply_in_thread`, `edit_message`, `delete_message` open "⋯";
  the hover comments go.

### Risks
- R1. Portal + outside-close: a menu portaled out of the `<article>` is "outside" the
  row by DOM containment unless the check includes the menu's own node.
- R2. Edit unmounts nothing but the editor replaces the body; focus return after save
  needs "⋯" still mounted (it is in the header row) — but `editPending` re-renders.
- R3. Positioning captured once at open — the list scrolls (a new message arrives and
  sticks to bottom, or older ones are prepended with anchor scroll) while the menu is
  open; a fixed-position menu would detach from its row. What does the plan do?
- R4. A message re-rendered by a live edit/reaction while its menu is open must keep the
  menu (state keyed by id, not by object).
- R5. Thread panel's root box is `max-h-48 overflow-y-auto` — a second clip container.
- R6. Every existing BDD journey that edits, deletes, reacts or replies goes through the
  changed page objects — `steps/conftest.py:187,192`, `test_thread_steps.py:29`,
  `test_reaction_steps.py:46`.
- R7. Record: doc 06 new section, register D47 🟢, ADR; D20 untouched.

## Coverage

| Issue item or expectation | Plan | Outcome |
|---|---|---|
| Req 1 "⋯" on every message allowing an action, channel and thread, exactly the `can*` actions; none on pending/deleted; hover row removed | `offeredActions` (Task 1, 7 tests, one input flipped each); MessageItem/ThreadPanel/MessageList tests; hover row deleted (Task 7) | covered |
| Req 2 React opens six emoji; pick toggles | #8 swap; Task 2 emoji tests | covered |
| Req 3 Escape, outside click/tap incl. scroll-start touch, after any choice; one open at a time across channel and panel | Task 2 closing tests; #12 store id; ChannelView ×3 | covered. The focus half of outside-close is open: **Finding 1** |
| Req 4 `aria-haspopup`, `aria-expanded`, "Message actions"; focus in; keyboard reach; focus back | #7, #10; Task 2/3 tests | covered, except focus after an outside tap: **Finding 1** |
| Req 5 in full, not clipped, last message, panel right edge | #9 portal + `placeMenu`; boundary tests; `_open_actions` hit-test; acceptance 6 | covered (Finding 4 on the attribution) |
| *A live delete* — tombstone, menu closes, focus to list, never body; "stops allowing" | #13, #14; MessageList.actions, ThreadPanel tests; unmount-order claim verified | covered. #14's comparison: **Finding 2** |
| *Edit and the menu* | Task 2 choice rule + Task 7 effect; MessageItem tests | covered |
| *React and closing*, *Closing and the option's click* | Task 2 emoji/race tests (`user.click(option)`) | covered |
| *The thread panel* — no Reply | `threads` flag; ThreadPanel tests | covered |
| *Paths* rows (7) | Vitest per row; last message → acceptance | covered |
| Decided 1–5 | Decisions 1–5; D20 named and untouched | covered |
| Tests: Vitest list; one touch BDD journey 1024×768; page objects open "⋯"; every journey still passes | Tasks 2–4; `ada_touch_context`; Task 9 whole e2e | covered |
| Record: doc 06, D47 🟢 (free — D46 is the last), ADR | Task 8 | covered |
| Not in this issue | *Not in this plan* | covered |
| D1 submenu vs swap | #8 | settled |
| D2 markup / keys, Tab | #7, #10 (Tab wraps inside the menu, recorded with alternative) | settled |
| D3 focus on open / after outside tap | #10 / #15 | settled. #15 can't hold as written: **Finding 1** |
| D4 focus after Reply in thread | Task 2 "a choice … focuses ⋯" | settled (Req 4 literally) |
| D5 own Delete, then tombstone | choice focuses ⋯; unmount → fallback (Task 2 unmount test, "focus on ⋯" case) | settled |
| D6 which element is "the list"; thread panel | #13 `data-focus-fallback`, `tabIndex=-1`, **assumed** | settled |
| D7 actions changing while open | #14 **assumed** | settled. Comparison unpinned: **Finding 2** |
| D8 positioning, wheel/keyboard scroll | #9, #16 **assumed** | settled (Finding 5, minor) |
| D9 one-open state | #12 Zustand id via `useId` (D24-compatible; store is not persisted) | settled |
| D10 pointerdown containment incl. portal | *Corrections* bullet 3; race test | settled |
| D11 icon, test ids | #11, #18 | settled |
| C1 Req 4 vs live delete | #13: fallback when ⋯ is gone | settled |
| C2 Req 4 vs Reply/Delete choice | choice → ⋯; unmount → fallback | settled |
| C3 Req 3 vs Req 5 on non-pointer scroll | #16 | settled |
| C4 blur race | no blur/focusout handler; race test | settled |
| R3 position captured once | re-placed on scroll/resize; placement test follows a scroll | settled |
| R4 re-render keeps the menu | — | **missing: Finding 2** |
| R5 root box clip | #9 names `ThreadPanel.tsx:161` | settled |
| R6 existing journeys / breaking Vitest files | file map, Task 3/4, steps moved to `steps/conftest.py` | covered |

## Findings

### 1. Focus after an outside tap falls to the page body — major
**Where:** Decision #15; Task 2's test `a touch pointer-down outside closes it, chooses nothing
and leaves focus where it was` · **Checked:** Task 2's behaviour list and Decision #10, against
each other.
Opening the menu always moves focus into it (#10). An outside `pointerdown` closes the menu
"without moving focus" (#15), so the focused menuitem is removed from the document. In jsdom,
and in a browser when the tap lands on nothing focusable (the channel header, the sidebar's
text), focus then falls to `document.body`. That contradicts Req 4 ("closing it returns focus
to ⋯"), and the issue's own wording elsewhere ("never to the page body"). The test as named
can't pass as the plan describes it: "where it was" is a removed node. A test-writer will
either assert `body`, which pins the bug, or invent a rule. #15's reason, not taking focus from
whatever was tapped, is sound, but it only covers a tap on something focusable. **To settle:**
a decision row for an outside close while focus is in the menu. One defensible answer: move
focus to "⋯" (with `preventScroll`) before the menu goes, and let the tap's own default focus
whatever focusable thing it landed on. Then two tests: an outside tap on nothing focusable
leaves focus on "⋯", not `body`; a tap on a focusable outside input (or a focus moved there,
since `fireEvent.pointerDown` performs no default) ends with focus on that input.

### 2. "Actions changing closes the menu" — nothing pins value against identity — major
**Where:** Decision #14; Task 2 *Actions changing* and the test `the actions changing while open
closes the menu`; Task 7 `const actions = offeredActions(…)` · **Checked:** Task 1's interface
(it returns a fresh array on every call) and Task 7 (it is called on every render).
Every render of `MessageItem` passes a new `actions` array. A build whose effect depends on
`[actions]` closes the menu on every re-render. That includes a reaction, an edit, a
`thread_summary_changed` from someone else arriving on the message Ada is looking at, and a
`MessageList` render for a new message elsewhere. The one planned test changes the contents,
so it passes for the identity reading and the value reading alike: it is a fixture where two
readings coincide. This is new background work amplifying existing live updates, and in a busy
channel the menu would close under Ada's finger. **To settle:** say in #14/Task 2 that the
comparison is by value, and add a test that re-renders with equal contents in a new array
(`['react','reply']` → `['react','reply']`): the menu stays open and focus stays put. Better
still, one at the row level: a live reaction or edit to the message, through the real
`MessageList` cache helpers, leaves its open menu open.

### 3. The no-hover-row guard has no positive — minor
**Where:** Task 3, `MessageItem.test.tsx`, `no hover-revealed row: before "⋯" is pressed, no
React, Reply, Edit or Delete control is in the document`.
After green it also passes for a row that renders no actions at all. Pressing "⋯" in the same
test and finding `Edit` as a menuitem would make it prove its own positive. Other tests cover
the positive, so this is minor.

### 4. The thread panel's right edge is attributed to an acceptance check that doesn't test it — minor
**Where:** *Test approach*, "What no test here covers" (:105-109) · **Checked:** issue
*Acceptance* 1–6.
Check 5 is about Reply in a thread, not placement. Only check 6 (the last message) measures
the menu. The right edge is covered only by `placeMenu`'s unit test and Task 9's manual run.
The acceptance-reviewer should know to measure a reply's menu in the panel as well.

### 5. A scroll that carries "⋯" out of its list leaves a detached menu — minor
**Where:** Decision #16.
On a wheel or keyboard scroll (not a pointerdown), the fixed menu follows a button that may
now be outside the list's visible area. `placeMenu` then clamps it into the viewport, over the
header or the composer, with no visible "⋯" beside it. #16 is recorded and defensible. Closing
when the anchor leaves its scroll container's box would be the refinement. That is for the
code pair's first real run to judge, not a blocker.

## Left for later stages
- Findings 3–5, if the writer leaves them.
- Assumed rows the human should see at the end: #13 (focus fallback element), #14, #15 (as
  revised), #16 (follow on scroll), #17 (⋯ stays while editing), #10 (Tab cycles inside the
  menu rather than APG's Tab-closes).
- Test-writer: Task 2's placement test stubs `getBoundingClientRect` on both the trigger and the
  menu, so it pins that the menu is measured that way. Keep that consistent with the code.

## Checked and sound
- Base commit `df51879` = `git log` parent of the plan-writer's commit.
- References in *Corrections* (MessageItem :85-99/:115/:135, ThreadPanel :118-161, ReactionPicker
  :8-12, chat_page :296-311/:349-364/:383, conftest :258-259/:342) opened and accurate.
- react-dom 19.2.8 (primary checkout): function-component layout destroys at :14363-14377 run
  before host removal at :14289-14333. The unmount-focus rule works.
- Playwright `Locator.tap` needs `has_touch` (`_generated.py:20186-20216`).
- `steps/conftest.py:3-7` on step resolution; moving the four steps keeps reactions/threads bound;
  module-level `ada` override has precedent (`test_session_steps.py:45`); Alan's send step is the
  model for Grace's.
- `upsertMessage`/`removeMessage` (`useMessages.ts:144,205`), `upsertThreadMessage`
  (`threadCache.ts:58`), `MessageList.test.tsx:51`, `ChannelView.thread.test.tsx:169` exist as cited.
- Expected failures: load errors only where every test needs the module (Tasks 1, 2); Task 3 files
  import nothing new; store test red is `… is not a function`.
- `placeMenu` fixtures: arithmetic checked for every row, both sides of each boundary.
- Ripple: only `MessageItem` imports `ReactionPicker`; every breaking Vitest file and every page
  object action is in the map; no API/env/chart/migration change.
- Workflow: 600 lines; RED 1–4 before GREEN 5–7 with the test-reviewer gate; no committing task;
  *Found while building* empty; record task; verification names `lint unit` and `e2e`; every
  file in its stage's write scope (vocabulary doc is under `docs/plans/ch06`, writable by the
  code-writer); no 🔴 built on (D20 named, untouched; D47 is free).
- The journey's last step is Grace's window (server state).
