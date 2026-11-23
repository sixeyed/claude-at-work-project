# Code review — gh-8, round 1: changes_requested

The build does what the plan says, and everything the plan names is green: Vitest 620/620,
`tsc`, lint, build, and e2e 26/26 with the touch journey passing. Six mutants and six probes
found no bug in the code. One major finding stands, in the record: doc 06's new section says focus
goes to the fallback, "never the body", when the thread closes or a role changes, and the code
does neither. It is a wording fix in the doc.

## Expectations

Written before the green report or any file the writer touched was opened. Read: the issue,
the plan (its *Found while building* is already filled in, and was read with it), the red
report, the plan and test reviews, `MessageActions.test.tsx`, `MessageList.actions.test.tsx`,
and `MessageItem.tsx`, `ReactionPicker.tsx`, `stores/chat.ts`, `ThreadPanel.tsx` at `9dfde14`.
A grep for `Escape|keydown|tabIndex` over the SPA showed two lines of the new code by accident.
It also showed that no other part of the SPA handles Escape apart from `MessageEditor`.

**Task 5: `offeredActions`, `placeMenu`, store.**
- *Unpinned:* the docstrings that move the `can*` reasons (forgery/moderation, single-level
  threads) out of `MessageItem`. The store's doc comment saying it holds an instance id, never a
  message (D24). The empty horizontal range (a menu wider than the viewport → `V`) has no test.
- *Takes for granted:* `isPending` stays the `temp:` marker and `deletedAt` the tombstone, as in
  `MessageItem.tsx:85-99`.
- *Wrong build:* `<` for `≤`, edit for admins, or a `threads` flag that is ignored. All of these
  are pinned by the unit tests. A horizontal clamp that lets `left` go below `V` for a wide menu
  would not be caught.

**Task 6: `MessageActions`.**
- *Unpinned:*
  - `aria-controls` only while open.
  - `preventScroll` on each focus.
  - Listeners present only while open, and every one removed on close or unmount (`pointerdown`
    capture, `keydown`, `scroll` capture, `resize`). The capture flag must match on remove.
  - `resize` re-placement.
  - Re-placement on the swap to emoji. The six-emoji row has a different width, so it is
    right-aligned wrongly if it is not measured again.
  - The blur-race note in the header. No `onBlur`/`focusout`.
  - `z-50` and the theme tokens.
  - **The emoji mode is reset when the menu closes.** If it is not, the next "⋯" opens straight
    on the emoji row. I don't expect a test for this, so it is my first mutant. This includes a
    close caused by another menu opening, which happens through the store.
  - Escape handled only by the open instance.
- *Takes for granted:*
  - `useId()` is unique across the channel and panel rows.
  - The layout-effect cleanup runs before the host node is detached (the plan checked this in
    react-dom).
  - **The cleanup that clears the id and moves focus runs only on unmount.** If its deps
    include `open`, mode, or anything else that changes, it runs on every change, and could
    move focus to the fallback or clear the store mid-use.
  - A close caused by the store (another menu opened) leaves focus where the other menu put it.
- *Could go wrong:*
  - Too little: the menu isn't re-placed on scroll, a listener is left after unmount, and
    reopening shows the emoji row.
  - Too much: the outside-pointerdown handler also fires for the trigger, and Escape with the
    menu shut still steals focus. The `actions` comparison closes on identity (pinned), or
    closes when the menu is shut.
- *Plausible wrong build:* the effect deps on `[actions]` (pinned), unmount cleanup in an effect
  with changing deps (likely unpinned), and the mode not reset (unpinned).

**Task 7: rows.**
- *Unpinned:*
  - `group` removed from the article.
  - The header comment updated.
  - Focus on "⋯" only on an editing true→false change, **never on mount**. If it fires on mount,
    every row steals focus as it renders, which the test-reviewer found is caught only by the
    keyboard-path test.
  - `tabIndex={-1}` on both fallbacks.
- *Takes for granted:* `save` sets `editing=false` even when the edit later fails. The trigger
  still exists when editing ends. A delete during editing unmounts "⋯", so the ref is null and
  the code needs a null guard.
- *Could go wrong:* "⋯" focused on mount or on a remount (a pending→confirmed swap is a new
  key, so a new mount). A live delete while the editor is open.
  `tabIndex={-1}` on the scroller means a mouse press on the list's blank space now focuses it.
  That is harmless unless something reads the focus.
- *Plausible wrong build:* the ref initialised to `editing` on mount, which is fine, against one
  that focuses whenever `!editing`. The second is caught only by the keyboard test.

**Task 8: the record.**
- Doc 06 gets a *Message actions* block covering #7–#16.
- Register D47 🟢, naming what was built and linking the ADR.
- The ADR, with hover+long-press and a per-width split as the alternatives.
- Vocabulary §35, and the four moved steps.
- The sweep: no stale "hover" or `ReactionPicker` in `src/frontend/src`, `docs/design` or
  `tests/bdd`.
- Each claim is checked against the code, not the plan.

**Task 9.**
- `docs/test-report.md` shows unit (Vitest ≥ 568 + new) and e2e 26/26 at this tree's revision,
  and `e2e.xml` lists the touch journey as passed.
- The by-hand first run cannot be done headless. The plan's *Found while building* already says
  so, and it goes to the human.

## What ran

- `npm --prefix src/frontend test`: 60 files, **620 passed**. `run typecheck`: clean.
  `run lint`: clean. `run build`: built in 1.8s. `dist/` is ignored, and `git status` shows only
  this review.
- `python3 .claude/hooks/checks/conventions.py` over the seven changed source files: no findings.
- `docs/test-report.md`: revision `9dfde148e3b1-dirty`. That is the test-review commit plus the
  code-writer's uncommitted work, which the runner then committed as `627f5e7`, so the report
  covers this tree. Lint passed. Unit passed: 2099, with frontend 620, matching the green report.
  End-to-end passed 26/0, and *Message actions 1 of 1*. Integration shows ⚪ not run, which the
  plan's verification leaves out.
- `build/test-results/e2e.xml`: `errors="0" failures="0" tests="26"`, and it contains
  `test_message_action_steps…test_on_a_touch_screen_ada_reacts_to_graces_message_and_replies_in_its_thread`.
- `git diff --name-only 9dfde14 HEAD -- tests src/frontend/src/test`: empty. The code-writer
  touched no test, helper or fixture.
- The sweep, a case-insensitive grep for `hover|ReactionPicker` over `src/frontend/src`,
  `docs/design` and `tests/bdd`, finds only new text and unrelated `hover:` utility classes.
  Nothing is stale.

**Mutants** (sketch, one at a time, each reverted before the next):

| # | File: change | Tests run | Result |
|---|---|---|---|
| M1 | `MessageActions.tsx`: drop `setMode('menu')` in `toggle` (reopen keeps the emoji row) | `MessageActions`, `MessageItem` | **survived**, 38/38 |
| M2 | `MessageActions.tsx`: unmount cleanup deps `[id]` → `[id, open]` | `MessageActions`, `MessageList.actions`, `MessageItem`, probes | caught, 20+ failures |
| M3 | `MessageActions.tsx`: drop `if (!open) return` from the listener effect (Escape and pointer listeners always on) | the above + `ThreadPanel`, `ChannelView.thread` | **survived** the approved tests (73/73). Only probe P5 fails |
| M4 | `MessageActions.tsx`: actions-change effect closes (and focuses "⋯") even when shut | `MessageActions`, `MessageList.actions`, `MessageItem`, probes | **survived** the approved tests. Only probe P4 fails |
| M5 | `MessageActions.tsx`: `place()` only in `mode === 'menu'` (no re-placement on the emoji swap) | `MessageActions` | **survived**, 24/24 |
| M6 | `MessageItem.tsx`: focus "⋯" whenever `!editing` (so on mount too) | `MessageItem`, `.thread`, `MessageList`, `MessageList.actions`, `ThreadPanel`, `ChannelView.thread` | caught, by the keyboard-only test alone |
| M7 | `MessageActions.tsx`: the trigger counts as "outside" | `MessageActions` | caught, by the toggle test |

**Probes** (sketch tests against the real, unmutated code):

| # | Path | Result |
|---|---|---|
| P1 | open → React → Escape → open again: the actions menu, not the emoji row | passed |
| P2 | A in emoji mode, B opened by a bare `click`, A reopened: actions menu, focus on React | passed |
| P3 | parent re-renders with focus on the second item: focus stays | passed |
| P4 | actions change while shut, focus in an input: focus stays in the input | passed |
| P5 | Escape with no menu open, focus in an input: focus stays | passed |
| P6 | a `data-focus-fallback` aside unmounted with focus in its reply's menu: focus ends on `document.body` | passed. This confirms Finding 1 |

`sketch.sh clean` ran.

## Conformance

| Plan task or decision | Code | Outcome |
|---|---|---|
| T5 `offeredActions` (interface, order, rules, docstrings carry the `can*` reasons) | `actionRules.ts` | as planned |
| T5 `placeMenu`, `MENU_GAP`, `VIEWPORT_MARGIN`, empty-range → `V` | `menuPlacement.ts` | as planned |
| T5 store members + D24 comment | `stores/chat.ts:62-72, :95-98` | as planned |
| T6 / #7 markup: trigger attrs, `aria-controls` only while open, glyph `aria-hidden`, portal menu, item test ids | `MessageActions.tsx:233-289` | as planned |
| #8 React swaps items, `aria-label="Add a reaction"`, focus first emoji | `:225`, `:123-127`, `:253` | as planned |
| #9/#16 portal, fixed, `placeMenu`, re-placed on mode, `scroll` capture, `resize`; no close on scroll | `:109-127`, `:149-150` | as planned |
| #10 keys incl. Tab trap with `preventDefault` | `:185-213` | as planned |
| #12 one open at a time via `useId` in the store | `:82-83`, `:221` | as planned |
| #14 by-value compare, closes only if open | `:162-168` | as planned |
| #15 outside `pointerdown` (capture, DOM containment, trigger excluded), focus "⋯" first only if focus is in the menu, no `preventDefault` | `:131-140` | as planned |
| Escape on `document` only while open | `:141-146` | as planned |
| Unmount cleanup: clears own id, fallback only if focus was on "⋯"/menu | `:174-183` (`getElementById` instead of a ref: recorded in *Found while building*) | as planned |
| No blur/focusout; blur-race note in the header | header `:22-28` | as planned |
| `z-50`, theme tokens; `rounded-md` (test-review finding 3) | `:258` | as planned |
| `ReactionPicker.tsx` deleted | gone | as planned |
| T7 hover span and `group` out; `MessageActions` at `ml-auto`; `triggerRef`; focus on edit true→false only; header comment | `MessageItem.tsx` | as planned |
| #17 "⋯" stays while editing | rendered regardless of `editing` | as planned |
| T7 `data-focus-fallback` + `tabIndex={-1}` | `MessageList.tsx:301-303`, `ThreadPanel.tsx:139-141` | as planned |
| T8 doc 06 block | `06-frontend-spa.md:367-394` | departed in one bullet (Finding 1) |
| T8 register D47 🟢, built-against, ADR link | register :174 | as planned |
| T8 ADR, with both alternatives | `docs/adr/261123-…` | as planned |
| T8 vocabulary §35 | done | as planned |
| T9 `lint unit`, `e2e` whole, conventions, security | test-report, e2e.xml | as planned. The by-hand run was not done, and is recorded |

## Findings

### 1. Doc 06 says focus goes to the fallback, never the body, on a role change and on the thread closing; the code does neither — major
**Where:** `docs/design/06-frontend-spa.md:392-394` (the *Focus when "⋯" goes away* bullet) ·
**Checked:** probe P6, and `MessageList.actions.test.tsx:87-96`.
The bullet reads: "(a live delete, a role change, the thread closing): to the nearest
`[data-focus-fallback]` … never the body."

- **A role change** never removes "⋯", because `react` is always offered. The menu closes and
  focus goes to "⋯" (#14), which is what `MessageActions.tsx:167` does and the role test asserts.
- **The thread closing** removes the `<aside>` that *is* the fallback. The cleanup focuses it, the
  aside is then detached, and focus ends on `document.body`. Probe P6 shows this. The issue only
  asks that "the menu goes with it" on that path, so the code is fine. The doc promises more than
  the code does.

A later change that trusted this sentence would be built on something that isn't so. **Fix:** say
that a live delete moves focus to the fallback. Say that a change to the offered actions closes
the menu and returns focus to "⋯". Say that closing the thread or switching channel takes the
menu away with the surface, and claims nothing about focus. No test is needed, because this is
doc only.

## Unpinned

What only reading protects, each walked through the real code:

- **M1, the emoji mode reset on reopen.** `toggle` sets `mode` to `'menu'` before opening
  (`:220`). P1 and P2 pass. A refactor that moves the reset into a close path would miss the
  close that comes from another menu opening through the store.
- **M3, the listeners only while open.** `if (!open) return` at `:130`. Without it, every row's
  Escape listener would steal focus to its "⋯", including Escape in `MessageEditor`. P5 passes.
- **M4, the actions-change close only when open.** The store check at `:167`. Without it, an
  admin demotion would pull focus from the composer to some "⋯". P4 passes.
- **M5, re-placement on the swap to emoji.** The effect's deps `[open, mode, place]` call
  `place()` without a condition. The emoji row is a different width, so a build without this
  would sit misaligned or past the right edge in a real browser.
- **Listener removal.** `:151-156` removes each listener with the same capture flag it was added
  with. Checked by reading. No test sees a leaked listener.
- **The horizontal empty-range clamp.** It shares `clamp` with the vertical case, which is tested
  at menu height 800.

## Left for the human

- **The first real run**, which nobody has done: a menu on the last message of a scrolled
  channel, and one on a reply at the panel's right edge, with each menu in full. A touch that
  starts a scroll should close the menu. On desktop, wheel-scroll "⋯" out of the list with its
  menu open and judge #16. The acceptance-reviewer does part of this.
- Assumed decisions to read: #10 (Tab cycles inside the menu), #13 (the fallback elements), #14,
  #15 (a mouse press on nothing focusable leaves focus on the body), #16 and #17.
- **Integration** now shows ⚪ not run in `docs/test-report.md`. The fresh worktree had no earlier
  JUnit for it. Nothing here is that layer's input, but rerun it before relying on the report.
- `tabIndex={-1}` makes the message list and the thread panel focus targets, so a mouse press on
  their blank space now focuses them. Browsers draw no ring for a mouse focus there. Worth a look
  in the first run.

## Checked and sound

- M2 (cleanup with changing deps), M6 (focus "⋯" on mount) and M7 (trigger as outside) are each
  caught.
- `offeredActions` matches `MessageItem.tsx:85-99` at `9dfde14`, rule for rule.
- `placeMenu` follows the plan's arithmetic exactly, including the empty-range case.
- The store is client state only: an instance id (D24). No server state was added outside
  TanStack Query.
- The layout-effect cleanup reads `trigger.current` before React detaches refs and host nodes.
  The live-delete tests prove it in the list and the panel.
- No blur or `focusout` handler, and no `preventDefault` on an outside `mousedown`.
- `MessageItem`'s edit-focus effect handles a ref that has gone (`?.`), for a delete during
  editing.
- No `data-testid` was added to or read by Vitest code. The page-object ids are unchanged.
- No file outside the plan's file map changed. No generated file. No suppression comment.
- The green report's *What ran* matches what I ran and the committed evidence.
