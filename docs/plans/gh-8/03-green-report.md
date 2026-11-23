# Green — gh-8, round 2

Built the "⋯" message-actions menu: two pure rules, three store members, `MessageActions` (portal menu button), the row and the two focus fallbacks, plus the record. Every test and check is green: Vitest 620/620, typecheck, lint, build, and e2e 26/26.

## Baseline
Not run separately before building: the red report and the test-reviewer's review (28 failing tests, 3 load errors, 18 typecheck errors, 26 BDD collected) were taken as the tree the gate approved. The first full Vitest run after the build had no failures, so nothing differed.

## Built
| Task | Files | Tests now | Notes |
|---|---|---|---|
| 5 | `actionRules.ts`, `menuPlacement.ts`, `stores/chat.ts` | pass | `offeredActions` follows the old `can*` rules; `placeMenu` per the plan's arithmetic; store gains `openMessageMenu`, `openMessageMenuFor`, `closeMessageMenu` |
| 6 | `MessageActions.tsx`; `ReactionPicker.tsx` removed | pass | portal, fixed, placed in a layout effect, listeners only while open |
| 7 | `MessageItem.tsx`, `MessageList.tsx`, `ThreadPanel.tsx` | pass | hover row and `group` gone; `data-focus-fallback` + `tabIndex={-1}` on the list scroller and the panel |
| 8 | doc 06 §5.2 block, register D47, ADR `261123-one-message-actions-menu-at-every-width`, vocabulary §35 | n/a | sweep for `hover`/`ReactionPicker` finds nothing stale |

## What ran
- `npm --prefix src/frontend test`: 60 files, **620 passed** (baseline 568 + new).
- `npm --prefix src/frontend run typecheck`: clean. `run lint`: clean. `run build`: built.
- `scripts/test.sh lint unit`: passed (unit report 2099 passed, 0 failed).
- `scripts/test.sh e2e` (whole layer): passed, **26 passed, 0 failed** (baseline 25).
- `python3 .claude/hooks/checks/conventions.py` on the changed source files: no findings. `.claude/hooks/security.sh`: "Security pass clean".

## Beyond the tests
- Doc-comments carrying the reasons: the blur-race note and portal/placement/focus rules in `MessageActions.tsx`'s header; the `can*` reasons in `actionRules.ts`; the client-state note on the store members.
- `rounded-md` on the menu so the page object's corner hit test (test-review finding 3) cannot fail on the radius.
- No `onBlur`, no `preventDefault` on an outside `mousedown` (plan reviews).
- Scroll re-places the menu and never closes it (#16).

## Departures from the plan
None. Small implementation choice: unmount cleanup finds the menu by `document.getElementById(id)`, not a ref.

## Picked up from earlier reviews
- Test-review 1 (unmount "elsewhere" half cannot fail): not relied on; the code only refocuses when focus is on "⋯" or in the menu.
- Test-review 2 (no focus-aware blur guard): no blur handler exists.
- Test-review 3 (corner radius): `rounded-md`.
- Plan-review 2: no `preventDefault` on outside `mousedown`.
- Horizontal clamp with an empty range has no test; `clamp` returns the margin as the plan says.

## Left for the human
- The first real run in Chromium touch emulation at 1024×768: "⋯" on the last message of a scrolled channel and on a reply at the thread panel's right edge (each menu whole); a touch that starts a scroll with a menu open (closes); on desktop, wheel-scroll "⋯" out of the list with its menu open and judge #16 (the menu stays, clamped, with no "⋯" beside it).
- Assumed decisions to read: #10, #13, #14, #15 (a mouse press on nothing focusable leaves focus on the body), #16, #17.

## Review responses (round 2)
- Code-review finding 1 (major, doc 06 overclaimed focus on role change and thread close): fixed in `docs/design/06-frontend-spa.md`, *Focus when "⋯" goes away*. It now says a live delete moves focus to the fallback; a change to the offered actions closes the menu and returns focus to "⋯"; closing the thread or switching channel claims nothing about focus. Doc-only, no code changed.
- Surviving mutants M1/M3/M4/M5 are gaps in the approved tests, not in the code (probes pass). Not mine to fix.
- Rerun after the change: nothing. It is a Markdown-only fix, and round 1's results stand for the unchanged code. I did not rerun lint, because Bash was denied in this session.
