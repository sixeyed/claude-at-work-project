# Plan review — gh-8, round 2: approved

Both round-1 majors are fixed. Each fix has a decision row and tests that fail the wrong build.
The minors are answered too. The plan's one new claim, about the installed user-event, holds in
the source. No critical or major finding is open.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. Focus after an outside tap falls to the body (major) | #15 rewritten. With focus in the menu, `pointerdown` focuses "⋯" (`preventScroll`) and then closes the menu. The press's own default then applies. Two tests replace the old one: a lone touch `pointerDown` on a non-focusable div ends on "⋯", and `user.click` on an outside input ends in the input | **resolved.** Checked `user-event/dist/esm/system/pointer/mouse.js:63-75` (`mousedown` dispatched, then `focusElement(target)`) and `event/focus.js:12-23` (closest focusable, else blur) in the primary checkout. The plan's account is exact. The first test fails a build that closes without refocusing, because the removed menuitem leaves focus on `body`. The second test fails a `preventDefault` build. The mouse-on-nothing case is recorded in #15 with its alternative, so it is settled (see *Left for later stages*) |
| 2. Actions compared by identity (major) | #14 and Task 2 say the comparison is by value, never `[actions]`. A same-contents rerender test is added in Task 2, and a live reaction, then a live edit, through `upsertMessage` in `MessageList.actions` | **resolved.** The Task 2 test moves focus to the second item before the rerender, so "focus where it was" can't pass by coinciding with the first item. The row-level test runs through the real `offeredActions` call on every render, which is the path a `[actions]` dependency would break |
| 3. No-hover guard lacks a positive (minor) | The test now opens "⋯" and finds Edit as a menuitem | resolved |
| 4. Panel edge credited to acceptance check 5 (minor) | Credits check 6 with the last message only. The acceptance-reviewer is asked to measure a reply's menu at the panel's edge, and Task 9 does it first | resolved |
| 5. A wheel scroll leaves a detached menu (minor) | Kept #16. The detached case and the refinement are named in the row, and Task 9 wheel-scrolls and judges it | let go. Recorded and defensible, as round 1 said |

## Findings

None.

## Left for later stages

- **#15, a mouse press on nothing focusable** (assumed). "⋯" takes focus and the browser's
  `mousedown` default then blurs it to `body`. This is a defensible reading of Req 4: the menu
  returns focus, and the platform moves it after. It differs from the issue's "never to the page
  body", which the issue says only of a live delete. The human should see it. The code-writer
  should not add `preventDefault` to make the case "pass".
- **#16, a wheel scroll that carries "⋯" out of the list.** Task 9's first run judges it. If the
  run changes the behaviour, record it under *Found while building*, with a test.
- Assumed rows for the human at the end: #10 (Tab cycles inside the menu), #13 (the fallback
  element), #14 (closing on a value change), #15, #16, #17 (⋯ stays while editing).
- Test-writer: the outside-input test must use `user.click`, not `fireEvent`, or the `mousedown`
  default that the test depends on never runs. The touch test must use `fireEvent.pointerDown`
  alone, on a non-focusable element.
- Acceptance-reviewer: measure a reply's menu at the thread panel's right edge, as well as
  check 6.

## Checked and sound

- Base commit `df51879` is unchanged. Round 2's diff (`git diff c23517c c775e09`) touches only
  the plan, apart from the runner's own `run/` files.
- Length: 591 lines before *Review responses*, inside 250–600.
- The edits trimmed prose and changed no path, task order, file map row or RED/GREEN split.
  Round 1's checks of references, react-dom unmount order, Playwright `tap`, step relocation,
  ripple and write scope still stand.
- The new tests sit in RED Tasks 2 and 3 and import nothing new. Their expected failures are as
  stated: a load error for the `MessageActions` file, and `no "Message actions"` for
  `MessageList.actions`.
- Task 8's doc 06 record now includes the outside-press focus rule (#15).
