# Code review — gh-9, round 1: approved

**Verdict: approved.** The build follows the plan step by step. I re-ran every check the plan
names and each one passed: Vitest 662, typecheck, lint, build, the convention checks, and e2e 27
including the phone journey (from the evidence on disk). Every premise I listed in my expectations
holds in the code. No finding is critical or major. Three of the six mutants survived, and each
survivor is a place where reading the code shows it is right. Those are listed under *Unpinned*.

## Expectations

Written from the issue, the plan, the red report, the approved tests, the earlier reviews and the
pre-writer code (`git show cc60f55:<path>` — HEAD already holds the writer's commit). Honesty note:
the plan file carries the code-writer's *Found while building*, which I read with the plan, and one
Grep for `openMessageMenu` showed a line of the new `ChatLayout`. Nothing else of the writer's was
open when this section was written.

**Task 4 — `useNarrow`, viewport.**
- No test pins: `index.html`'s `interactive-widget=resizes-content`; `#root` at `100dvh` with
  `html, body` kept at `100%`; `NARROW_BELOW` exported. `matchMedia` inside `subscribe`/`getSnapshot`
  (the harness would catch module-load caching, since it reinstalls after each test).
- Takes for granted: `useSyncExternalStore` re-reads `getSnapshot` after a `change`; each call to
  `matchMedia` gives a fresh list in a browser — fine, the snapshot is a boolean.
- Wrong build: a `md:` class as well (two copies of the breakpoint); `max-width: 767px` (fractional
  widths 767.5 fall between) — reading only.

**Task 5 — the shell and the drawer.**
- No test pins: the top bar's `inert` while open (only `<main>`'s is asserted); `aria-controls` on ☰;
  `aria-modal`; the backdrop's `tabIndex={-1}`; narrow classes (`fixed`, `max-w-[85vw]`, z-order above
  the backdrop); that the narrow-only children are `{narrow && …}` in fixed slots; `closeDrawer` the
  only close path; all of the CSS that decides whether the page fits the viewport.
- Takes for granted: (a) the shell is reconciled across shell routes (Decision 10 — the workspace test
  holds the aside node); (b) `session.changeWorkspace` doesn't navigate (grep: no `navigate` in
  `session.ts` — true), so the arrival effect doesn't reopen on a switch while on `/`; (c) the "⋯" menu
  closes when the store's `openMessageMenu` is nulled (`MessageActions.tsx:83` reads it — true) and
  its own focus-restoring `close()` is not run on that path, so focus isn't pulled back to "⋯" behind
  the drawer; (d) the narrow flag read by the arrival effect is the current one.
- Where it could go wrong:
  1. **Height with a top bar.** `<main>` is `h-full` today. If the narrow grid adds a top-bar row
     without `grid-rows-[auto_1fr]`/`min-h-0`, main is 100% *plus* the bar: the page scrolls vertically
     and the composer sits partly below the fold — no test sees height. Too much: the dvh on `#root`
     *and* `h-full` on `html/body` disagreeing on iOS.
  2. **Focus to ☰ on close.** Too little: a navigation close (channel, create) leaving focus on a node
     in the hidden aside (body in a browser). Too much: `closeDrawer` called at **wide** (every channel
     link calls `onNavigate`) leaving a pending "focus ☰" request that fires later, e.g. on the next
     narrow close or crossing; or `closeDrawer` on an already-closed narrow drawer (a DM `onSuccess`
     after the user closed it) yanking focus from the composer to ☰.
  3. **Escape** handled on the aside only: focus on `<body>` after a click on a non-focusable part of
     the drawer means Escape does nothing. As planned, so reading only.
  4. **Tab wrap**: the focusable list must skip `disabled` (the active workspace option), `tabindex=-1`
     and hidden descendants, or Tab lands nowhere/wrong. Last control is Sign out today; with the DM
     picker open there are more.
  5. **Arrival effect**: keyed on `pathname` only; a `narrow` ref updated in render or a layout effect
     — if updated in a later effect, the first narrow render might read a stale value. Opens on
     every return to `/` (Settings' back, archive) — intended.
  6. **Crossing to narrow with focus in the sidebar** (Decision 24): the check must run before the
     browser's focus fixup moves focus off the newly hidden aside — in render or a layout effect. A
     `useEffect` reading `document.activeElement` works in jsdom (which never fixes focus up) and fails
     in Chrome. Unpinnable in jsdom; reading only.
  7. Crossing to wide: `drawerOpen` cleared; `<main>`/top bar `inert` gone; no focus moved.
- Wrong builds: arrival keyed on `drawerOpen` (caught: "stays closed"); `onNavigate` only on navigate
  in `SearchBox` (caught); closing at the DM pick (caught); top bar not `inert` (likely survives);
  focus to ☰ at wide (likely survives — no wide focus assertion after a channel click).

**Task 6 — the panels.**
- No test pins: `ThreadPanel`'s `absolute inset-0 z-10 w-full bg-surface` (cover is read only as
  `inert`); that the row is `relative`; the member panel covering with the same classes; the header
  staying uncovered (Decision 19); `members-open`/`members-close` testids (BDD only).
- Takes for granted: `useThreadParam.closeThread` replaces, so Back to channel adds no entry; the
  column stays laid out under an absolute overlay, so `scrollTop` is kept (jsdom can't show; the
  journey can); hooks before `ChannelView`'s early returns.
- Where it could go wrong: the focus-composer request after **Back to channel** left pending if the
  thread doesn't close (it always does) — or fired on a later unrelated thread close (wide **Close
  thread**, browser Back), stealing focus; `membersOpenFor` reset by render-time `setState` (React
  permits it on the same component; loops if the condition doesn't converge); the member panel
  reappearing on narrow→wide→narrow (writer clears it while wide — said in *Found while building*);
  `ChannelHeader` receiving `onToggleMembers` at wide or in a DM (caught by tests).
- Wrong builds: `display:none` on the column (journey only); keyed remount by width (caught by node
  identity); focus composer via `useThreadParam` (would change browser-Back focus — unpinned).

**Task 7 — 360px.** None pinned by Vitest: `AttachmentList` cap and chip `max-w-full`;
`[overflow-wrap:anywhere]` on `MessageItem` and `SearchResult` bodies; header `<h2>` `break-words`,
header row wraps or truncates. Only the journey's tour sees overflow.

**Task 8 — the record.** Doc 06 §3 new subsection (hook, one tree, drawer and its closes, arrival at
`/`, covering panels, crossing, viewport meta, device-only), §5.2 "below 768px covers the message
view", §9 "in the drawer below 768px"; register D48 🟢 with what's built against it and D20 still
open, D47's gh-9 pointer replaced; ADR `261123-a-responsive-layout-below-768px.md`; vocabulary §36 with
five phrases; nothing stale on "gh-9"/"narrow".

**Task 9.** `docs/test-report.md` at this tree with unit and e2e passed (e2e ≥ 27 with the phone
journey among the passed in `build/test-results/e2e.xml`); conventions over every changed file.

## What ran

- `npm --prefix src/frontend test`: 63 files, **662 passed**. This is 620 + 42, which matches the
  report.
- `npm --prefix src/frontend run typecheck`, `run lint`, `run build`: all clean. The build produced
  `dist/` (git-ignored), and `git status --short` shows only this review.
- `python3 .claude/hooks/checks/conventions.py` over all 15 changed `src/frontend` files, by name:
  no output.
- **Evidence for `scripts/test.sh`.** `docs/test-report.md` is at `cc60f55a2ccc-dirty`, and the
  writer's commit is HEAD on top of `cc60f55`, so that is this tree:
  - Lint passed.
  - Unit passed, 2141, with frontend 662.
  - End-to-end passed, 27 — the baseline 26 plus the new phone scenario.
  - `build/test-results/e2e.xml`: `tests="27" failures="0" errors="0"`, and
    `test_on_a_phone_ada_picks_a_channel_from_the_drawer_replies_in_a_thread_and_goes_back` is among
    the passed.
  - Integration was not run. The plan names no integration run, and no service changed.
- **Mutants** run in `build/sketch/`, each reverted before the next:
  1. `ChatLayout`: drop `inert` on the top bar. Ran `App.narrow`: 33 passed — **survived**.
  2. `ChannelView`: drop the render-time `setMembersOpenFor(null)` while wide. Ran both narrow
     files: **caught** by `the member panel takes each width's default`. Mutant 1 was still applied
     during this run because my first reset used the wrong path; that does not change the result.
  3. `ChatLayout`: drop the `if (!shown) return` guard in `onDrawerKeyDown`, so the Tab trap and
     Escape stay active at wide. Ran `App.narrow`, `App.test`, `features/channels`: 382 passed —
     **survived**.
  4. `DirectMessageList`: call `onNavigate` outside the workspace-still-current check. Ran
     `App.narrow` and `features/channels`: 376 passed — **survived**.
  5. `ChatLayout`: the arrival effect reads `narrow` as a dependency instead of the ref. **Caught**
     by `crossing to narrow on / leaves it closed`.
  6. Already caught by the test-reviewer's sketches and not re-run: closing at the DM pick,
     `SearchBox` without its no-navigation branch, the "⋯" reset missing, remounting by width.
- No probes. Each survivor is code that is present and correct when read, and none of them leaves
  a premise of the issue in doubt. See below.

## Conformance

| Plan task or decision | Code | Outcome |
|---|---|---|
| T4 `useNarrow`, `NARROW_BELOW`, matchMedia inside subscribe/getSnapshot | `lib/layout/useNarrow.ts` | as planned |
| T4 viewport meta, `#root` 100dvh, `html, body` 100% | `index.html:5`, `index.css:28-37` | as planned |
| T5 `openDrawer` clears `openMessageMenu`; one `closeDrawer` | `ChatLayout.tsx:84-95` | as planned |
| T5 markup: ☰ `aria-expanded`/`aria-controls`; aside dialog/`aria-modal`/`hidden`; backdrop `tabIndex=-1`; `inert` on main and the top bar; fixed child slots | `ChatLayout.tsx:184-309` | as planned |
| T5 focus in (Close sidebar), Escape, Tab wrap over non-disabled focusables | `:97-104`, `:123-146` | as planned |
| T5 arrival on `pathname` via a ref (D16) | `:106-110` | as planned |
| T5 width: clear while wide; to narrow with focus in the aside → ☰ (D24), in a layout effect | `:71`, `:115-121` | departed: a render-time set instead of an effect; recorded in *Found while building* |
| T5 `onNavigate` at each listed point; `onCreated` navigates then closes | `ChannelList`, `DirectMessageList` (inside the workspace check), `WorkspaceSwitcher` (link and option), `SearchBox` (after the blank check, both branches) | as planned |
| T6 `membersOpenFor` keyed `channel\|thread\|narrow`; row `relative`; column `inert` when covered | `ChannelView.tsx:55-58`, `:112`, `:135-136` | as planned, plus a reset while wide (recorded) |
| T6 `ThreadPanel fullScreen`: classes and **Back to channel**; same element and key | `ThreadPanel.tsx:146-164`, `ChannelView.tsx:171-184` | as planned |
| T6 member panel covering with `onBack`; `ChannelHeader` props only when narrow, not a DM, no thread | `MemberPanel.tsx`, `ChannelView.tsx:127-131,186-194` | as planned |
| T6 D24 composer focus through `ChannelView`'s handler, narrow only | `:63-70`, `:114-118`, `onClose={narrow ? backToChannel : closeThread}` | as planned |
| T7 attachment cap, chip `max-w-full`, `overflow-wrap:anywhere` ×2, `<h2>` `break-words`, header row `flex-wrap` | as listed | the image cap departs (an existing test pins `max-w-80`); recorded with a reason that holds |
| T8 doc 06 §3 subsection, §5.2, §9; D48 🟢 and the D47 pointer; ADR; vocabulary §36 | all present | as planned |
| T9 verification and *Found while building* | report and plan | as planned |

## Findings

None that block approval. The two items below are minor and are listed under *Left for the human*.

## Unpinned

- **The top bar's `inert` while the drawer is open** (mutant 1 survived). Only `<main>`'s `inert` is
  asserted. The attribute is present at `ChatLayout.tsx:193`.
- **The key handler is inert at wide** (mutant 3 survived). At 768px and over, nothing but the
  `if (!shown) return` at `:124` stops Tab from wrapping inside the desktop sidebar and Escape from
  doing anything. The guard is there.
- **A new DM that resolves after a workspace switch does not close the drawer** (mutant 4
  survived). The behaviour is right by reading: `onNavigate` sits inside the existing
  workspace-still-current check.
- **Covering is read only as `inert`.** Vitest never sees the `absolute inset-0` classes on the
  thread and member panels. The journey shows the thread covering and Back returning to the same
  scroll position on a real browser. The member panel covering is shown by no browser test.
- **Height with the top bar.** The narrow grid is `grid-rows-[auto_minmax(0,1fr)]`, and `<main>`
  drops `h-full` for `min-h-0`. The aside and the backdrop are `fixed`, so they take no grid cell.
  By reading, the page does not grow taller than `#root`. No test measures height.
- **D24 crossing focus** runs in a layout effect (`:116`), before the browser's focus fixup. jsdom
  never fixes focus up, so only reading or a real browser can tell this apart from a `useEffect`.

## Left for the human

- **Minor — Escape after a tap on blank drawer space.** Escape is handled on the aside's
  `onKeyDown`, as the plan says. In a desktop-width browser narrowed below 768px, a click on a
  non-focusable part of the drawer moves focus to `<body>`. After that, Escape does nothing until
  focus is back inside the drawer. A phone has no Escape key, so this only matters on a narrow
  desktop window. The alternative is a `document` keydown listener while `shown`: one effect.
- **Minor — doc 06 wording.** Doc 06 says "every close … returns focus to ☰". Crossing to wide
  also closes the drawer and, correctly, moves no focus, because ☰ is gone. The sentence lists only
  narrow closes, so it is accurate as written. If you want it unambiguous, add "while narrow".
- **On a real phone** — as the green report says: every control reachable at 360×740 and 390×844,
  the composer above the keyboard, a real rotation with a thread and drafts. The acceptance-reviewer
  adds sign-in to check 4 and does check 3 in Decision 23's order.
- `ChannelHeader` now always renders the controls wrapper `div`, even when it is empty (a
  non-admin at wide). It is harmless, and `channel-controls` still appears only for an admin.

## Checked and sound

- Every premise in my expectations: (a) the shell is reconciled across routes, held by the
  workspace test's node identity. (b) `changeWorkspace` does not navigate. (c) the "⋯" menu closes
  through the store, and `MessageActions.tsx:83` reads it. (d) `narrowRef` updates in an effect
  declared before the arrival effect, so it is current in the same commit and was initialised from
  the first render.
- `closeDrawer` at wide sets no focus request (`narrowRef` is false). A request left pending after
  a no-op narrow close is consumed only by a later open-then-close, or dropped harmlessly when ☰
  has unmounted.
- `focusComposerOnReturn` is set only by **Back to channel**. The browser's Back and the wide
  **Close thread** go through `closeThread` without it.
- Hooks in `ChannelView` all run before its early returns. The render-time `setState` calls
  converge: each sets its value to null or false once.
- No test, helper or fixture was touched by the writer: `git diff --stat cc60f55 HEAD` lists none.
  Every changed file is in the plan's file map. The run files are the runner's own.
- React 19 (`package.json`) renders the boolean `inert` prop.
- The register (D48 and the D47 pointer), the ADR, doc 06 §3, §5.2 and §9, and vocabulary §36 say
  what the code does. The sweep of `docs/design` for "gh-9", "mobile" and "below 768" found
  nothing stale. The D20 mentions are the open entry.
- Mutants 2 and 5 were caught.
