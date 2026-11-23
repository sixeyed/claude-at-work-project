# Test review — gh-8, round 1: approved

The red is real: 28 tests fail for the stated reasons and 3 files fail to load because every test in
them needs the missing module. Against a correct sketch all 101 tests in the 9 files go green, and
every wrong build I tried is caught except two that are minor and recorded below. No critical or
major finding.

## Expectations

Written before the red report or any test file was opened. Read: issue, plan, plan reviews,
`MessageItem.tsx`, `ReactionPicker.tsx`.

**Pure rules (`actionRules`, `menuPlacement`).** Fail today with `Failed to resolve import` (load
error, right: every test needs the module). Vacuous: a placement test with only the "fits" case; a
single boundary side (590 vs 606); an `offeredActions` fixture where author and admin coincide, or
`threads` and `threadRootId` flip together. Wrong build: `<` for `≤`, edit for admins, ignoring
`threads`. Pins: "exactly the actions the message allows today", pending/deleted none.

**Store.** `openMessageMenuFor is not a function`. Vacuous: closing another's id that happens to be
the open one. Wrong build: `closeMessageMenu` clears unconditionally.

**`MessageActions`.** Load error. Vacuous: Escape test where focus is already on "⋯"; the outside-tap
test on an element that is focusable (focus never falls to body); the race test using `fireEvent.click`
(no pointerdown, so no race); one-at-a-time test with `user.click` on both (pointerdown closes A anyway);
same-array rerender test with focus on the first item (coincides); fallback-focus test with only the
"focus goes to fallback" half; placement test with stubbed rects that give the same answer above or
below. Wrong builds: close on blur; `[actions]` identity dependency; contains-check against React tree;
always focus fallback on unmount.

**Rows.** Fail today with no "Message actions". Vacuous: "no ⋯ on tombstone" with no live positive;
"no hover row" asserting only absence; Edit focus-return test where focus is on "⋯" anyway; "no Reply in
thread" passes today for a thread row, so needs the positive (confirmed channel row offers it).
Wrong builds: Enter in editor reopens menu; focus to body on delete; Reply offered in panel.

**BDD.** Parses and binds; steps moved to conftest keep other features binding. Vacuous: `_open_actions`
without the opacity check, hit-test only at centre, `tap` used on a non-touch context. Wrong build:
a hover-gated "⋯".

## What ran
- `npm --prefix src/frontend test -- <the 9 files>`: 28 tests failed, 3 files failed to load
  (`Failed to resolve import "./actionRules" | "./menuPlacement" | "./MessageActions"`). First lines match
  the red report's table, including its one departure (`chat.test.ts` test 1 fails on
  `expected undefined to be null`, still the missing field). Existing untouched tests still pass.
- `npm --prefix src/frontend run typecheck`: only the 18 expected errors (missing modules, missing
  `ChatState` members). Matches the report's *Types*.
- `uv run pytest tests/bdd --collect-only -q`: 26 collected. `--generate-missing`: no stubs, every step binds.
- `git diff HEAD~1`: only test files, page objects, step modules, `tests/bdd/conftest.py` and the report.
  No production code, config or docs.
- **Sketch, correct build** (`actionRules`, `menuPlacement`, store, `MessageActions`, `MessageItem`,
  `data-focus-fallback` on the list and panel): all 9 files, 101 tests, green.
- **Sketch, wrong builds**, each against the files that should catch it:
  - effect depends on `[actions]` identity: the same-array test and the `MessageList.actions` live reaction/edit test fail.
  - outside `pointerdown` closes without focusing "⋯": the touch-scroll test fails.
  - close on `focusout` to outside the popup: only the toggle test fails (finding 2).
  - local open state, no shared id: one-at-a-time, unmount-id and ChannelView cross-surface tests fail.
  - unmount always focuses the fallback: **all pass** (finding 1).
  - unmount clears the store unconditionally: the unmount-id test fails.
  - Escape closes without refocusing: both Escape tests fail.
  - "⋯" focused on every row mount: only the keyboard-path test fails (Tab moves past it).
  - no re-placement on scroll: the placement test fails.
  - `preventDefault` on an outside `mousedown`: the outside-input test fails.
  Sketch removed with `sketch.sh clean`.

## Coverage
| Plan test or expectation | Test as written | Outcome |
|---|---|---|
| `actionRules` ×7 | all 7, each input flipped alone, each guard has its positive | present |
| `menuPlacement` ×7 | all 7: exact-pixel fits (606/607, 162/161), tall menu, right and left clamps | present |
| store ×2 | both | present; test 1 departs (asserts initial `null`), accepted |
| `MessageActions` ×24 | every row of the plan's table, plus a portal test | present |
| `MessageItem` ×11, `.thread` ×5 | all; thread guards each keep a positive | present |
| `MessageList.actions` ×4 | all four | present |
| `ThreadPanel` ×3, `ChannelView.thread` ×3 | all | present |
| Touch journey and page objects | feature, step module, conftest, `_open_actions` | present |
| Expectation: "exactly the actions today" | `offeredActions` plus MessageItem and ThreadPanel item lists | present |
| Expectation: Req 5 in a real browser | corner hit-test in `_open_actions` only | partial, as the plan says |

## Findings
### 1. The "focus elsewhere" half of the unmount test cannot fail — minor
**Where:** `MessageActions.test.tsx`, "unmounting with focus on ⋯ or in its menu moves focus to the fallback; with focus elsewhere, leaves it", third case · **Checked:** sketch, verified.
A build whose unmount cleanup always focuses the fallback passes. React restores focus to the still-attached input at the end of the commit; I probed it: focus is on the fallback inside the cleanup and on the input after the commit. The report and plan name this half as the positive that such a build fails. It is harmless in a browser for the same reason, so it is minor. The code-writer should not treat this half as a guard.

### 2. The race test does not fail a focus-aware blur close — minor
**Where:** "a tap on an emoji is not swallowed by the outside-close" · **Checked:** sketch, verified.
A build that closes on `focusout` only when the new focus is outside the popup passes it, because user-event focuses the option, so `relatedTarget` is inside. Only a close on any blur fails it, and that also breaks the arrow-key tests. The Safari case, where a button click leaves `relatedTarget` null, is not emulated. The plan's code adds no blur handler, so the code-writer needs only to keep it that way.

### 3. The four-corner hit test assumes a small border radius — minor
**Where:** `chat_page.py` `_CORNERS_HIT_THE_MENU` · **Checked:** **unverified**, by reading.
A point 2px inside a corner lies outside the rounded border once the radius passes about 6px (`rounded-lg`), and `elementFromPoint` honours the radius. The code-writer should use `rounded` or `rounded-md`, or the journey fails for a reason that is not clipping.

## Left for later stages
- Findings 1–3, for the code pair.
- The horizontal clamp with an empty range (menu wider than the viewport) has no test; the vertical one has. Minor.
- Req 5 in a real browser for the last message of a scrolled list and for a reply at the panel's edge is the acceptance-reviewer's, as the plan says.
- plan-reviewer-2's note holds: the code-writer must not add `preventDefault` on an outside `mousedown`; the outside-input test fails it.

## Checked and sound
- Red for the right reason: 28 behaviour tests fail on the missing "Message actions" button, store member or old row; load errors only where every test needs the module.
- No test is green by accident, and none is driven by an import from a missing module (plan values are literals).
- Both sides of each placement boundary, and each `offeredActions` input on its own.
- The touch-scroll and outside-input tests use `fireEvent.pointerDown` and `user.click` respectively, as plan-reviewer-2 asked.
- Existing assertions: the removed `MessageItem` and `ThreadPanel` tests are replaced by menu equivalents; none weakened, and the rest still pass.
- The report matches the tree: every changed file is in the plan's file map.
- BDD: scenario collected, all steps bind, moved steps resolve from `steps/conftest.py`, the effective-opacity check precedes the press.
