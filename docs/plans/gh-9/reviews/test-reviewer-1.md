# Test review — gh-9, round 1: changes_requested

The red is real for 33 of the 39 new Vitest tests that can run, and the tests are well aimed: ten wrong drawer builds and three wrong panel builds each failed the test meant to catch them. But five tests can never pass against any correct build. They type into or focus the message composer, which is `disabled` unless the store's `connectionStatus` is `'connected'`, and no new test sets it. A code-writer would work until the end of the round on tests no code can turn green. That is critical; the fix is small and in the tests only.

## Expectations

Written before opening the red report or any test file. Read: the issue, the plan, plan-reviewer-3, `ChatLayout.tsx` as it stands (no `useNarrow`, no drawer, no `matchMedia`).

**What fails today:** `window.matchMedia` does not exist in jsdom; the fake in `test/viewport.ts` is the test-writer's. Task 1 fails at `Failed to resolve import "./useNarrow"` (whole file); every `App.narrow`/`ChannelView.narrow` test fails on a missing role/name (`Open sidebar`, dialog `Sidebar`, `Back to channel`, `Members`). Wide-only tests are green by design.

| Behaviour | Vacuous version | Clause it must pin | Wrong build to catch |
|---|---|---|---|
| `useNarrow` | widths taken from `NARROW_BELOW` (NaN at red); one side of 768 only; no unsubscribe positive | "under 768": 767 narrow AND 768 wide | `<= 768`; no cleanup; matchMedia cached at module load |
| Viewport harness | a fake that never fires `change`; accepts any query | unsupported queries throw | — |
| Drawer closed by default, open on `/` | "closed" asserted by absence of dialog only; no link-hidden check | closed for any other screen | always-open; arrival effect re-opening after a close |
| ☰ on every screen | only `/c/…` tried | `/`, channel, DM, `/search`, `/settings` | ☰ in ChannelHeader only |
| Closes on each navigation, not on anything else | close tested only where the click also routes | each navigation closes; typing / new-DM list do not | close on any click; a location listener (misses same-query search, workspace switch) |
| Backdrop | no check that URL/thread unchanged | "nothing else" | backdrop click navigates |
| Modal: focus in, trap, return | no positive; Tab wrap one direction only | focus in, held, back to ☰ | no wrap; focus return on one close path only |
| "⋯" closed by opening the drawer | menu never opened first | — | drawer leaves the menu open |
| Panels cover | `inert` not asserted; scroll test whose fixture a remount survives | scroll position kept; Back closes thread; no history for the member panel | `display:none` / unmounted column; remount |
| Crossing | node identity not asserted; draft in one composer only | thread open, drafts and scroll kept, drawer closed at ≥768, member panel resets | two layouts; drawer left open; member panel carried over |
| Journey | a `Then` that acts; a tour that defaults to pass; a scroll arrangement that cannot separate the readings | scroll neither top nor bottom; no sideways scroll at 360 | remounted list (bottom) or lost box (top) |

## What ran

- `npm --prefix src/frontend test -- src/App.narrow.test.tsx src/features/channels/ChannelView.narrow.test.tsx src/lib/layout/useNarrow.test.ts`: 3 files failed; **38 failed, 1 passed (by design)** in the 2 files that load; `useNarrow.test.ts` fails to load (`Failed to resolve import "./useNarrow"`), its 3 tests unrun. First lines match the report's *Observed red*.
- Whole Vitest suite: `Test Files 3 failed | 60 passed (63)`, `Tests 38 failed | 621 passed (659)` — the 620 existing tests plus the by-design green all pass.
- `npm --prefix src/frontend run typecheck`: one error, `useNarrow.test.ts(13,27) TS2307 Cannot find module './useNarrow'` — as reported.
- `uv run pytest tests/bdd --collect-only -q`: 27 collected. `--generate-missing --feature tests/bdd/features`: no stub printed. The journey cannot run before the code-writer; its page object and steps were read, not run (**unverified** beyond binding).
- **Sketches** (`sketch.sh frontend`, copy under `build/sketch/`, removed with `sketch.sh clean`):
  - Correct build (hook, `ChatLayout` drawer, `onNavigate` on four components, `ChannelView`/`ChannelHeader`/`MemberPanel`/`ThreadPanel` panels), tests as written: `useNarrow` 3/3; drawer 26/26; whole of the three files **5 failed of 42** — the five in Finding 1.
  - Same build with the sketch's copy of the tests setting `connectionStatus` to `'connected'` (nothing else changed) and a reset of the member panel on crossing to wide: **42/42**. So the five failures are the tests', not the build's.
  - Wrong drawer builds, each caught by the named test(s): arrival effect keyed on `drawerOpen` (8 tests incl. "can be closed, and stays closed"); arrival effect keyed on `narrow` ("crossing to narrow on /"); no `onNavigate` on the same-query search branch; closing at the DM pick rather than when it opens; closing on any click in the aside (3 tests); no Tab/Shift+Tab wrap; no `onNavigate` on workspace switch; opening that leaves the "⋯" menu open; no reset of the drawer on crossing to wide ("closed after crossing to wide and back"); Escape that does not return focus to ☰ (2 tests).
  - Wrong panel builds: thread panel keyed by width, i.e. remounted on a crossing (5 extra tests fail); member panel state not keyed by channel ("closes on a channel switch" fails).
  - Wrong hook builds: `(max-width: 768px)` (both 767/768 tests fail); no unsubscribe ("stops listening" fails).

## Coverage

| Plan test | Test as written | Outcome |
|---|---|---|
| Task 1 (3 hook tests) | `useNarrow.test.ts`, literals for widths | present; red by load failure, needed by every test in it |
| Task 2 drawer table (21 rows, `it.each` ×4) | `App.narrow.test.tsx` `the drawer` | present, 26 tests; all sketch-green |
| Task 2 crossing table (8 rows) | `crossing the breakpoint` | present; **3 can't pass** (Finding 1) |
| Task 2 panels (6 rows) | `ChannelView.narrow.test.tsx` | present; **2 can't pass** (Finding 1) |
| Task 3 journey, steps, page object, fixtures | `phone_layout.feature` and the rest | present; binds; not run |
| Departures | `Link` "Open the DM", extra args on `sideways_tour_at_360`, `filler` | reasonable, accepted |

## Findings

### 1. Five tests type into or focus a composer that is disabled — no correct build can pass them — critical
**Where:** `App.narrow.test.tsx` — `with a thread open, both drafts and their nodes survive…`, `acceptance check 3’s order…`, `crossing to narrow with focus in the sidebar moves it to ☰` (its neighbour half); `ChannelView.narrow.test.tsx` — `a thread covers the list; Back to channel returns at the scroll position left` and `Members opens a covering panel; Back to channel closes it…` (both assert focus on the composer) · **Checked:** by sketch, as above.
`MessageComposer.tsx:105` makes the textarea `disabled` while `connectionStatus !== 'connected'` (`ThreadComposer.tsx:41` the same for **Reply**). The store starts `'disconnected'`; `ChatLayout`'s socket hook sets `'connecting'`. Existing tests that use a composer call `useChatStore.getState().setConnectionStatus('connected')` (`ChannelView.test.tsx:422`, `ThreadPanel.test.tsx:61` …); none of the new ones do. `renderShell` sets `FakeSocket.connected = true`, which the store never reads. Result against a correct build: `user.type` into the disabled box types nothing (`toHaveValue('channel draft')` fails with an empty value), and `.focus()` on it leaves `document.activeElement` on `<body>`. Both draft rows — the ones that carry Req 7's "the draft is kept" and Decision 23 — cannot go green, and nor can Decision 24's focus assertions.
**Fix, tests only:** in `ChannelView.narrow` `renderShell`, `useChatStore.getState().setConnectionStatus('connected')` (the file's `setup.ts` resets the store after each test). In `App.narrow`, once the channel has loaded, `act(() => chat.useChatStore.getState().setConnectionStatus('connected'))` using the fresh `chat` module the file already imports after `vi.resetModules()` — a static `import … from './test/socket'` is a *different* module instance after a reset, and `latestSocket()` throws; setting the store is enough and survives `ChatLayout` (sketch: 42/42 this way). The thread composer needs the same, which that one call gives.

### 2. The red report says 41 of 42 fail "as planned", but five of them are red for a reason code won't fix — major
**Where:** `02-red-tests.md` · **Checked:** as Finding 1.
At red these five fail on the first missing element (`Back to channel`, ☰), so the disabled composer is hidden behind them; the report's *Observed red* for them is true and tells the code-writer nothing is wrong. Once Finding 1 is fixed, state in the report that the sketch-green run of every test was seen, or that it was not.

### 3. Decision 17's mechanism fails the test that pins it — plan fault, no test change — minor (for the code-writer)
**Where:** `App.narrow.test.tsx` `the member panel takes each width’s default` (the second return to 390) · **Checked:** sketch.
The plan holds the member panel as `membersOpenFor` compared with `` `${channelId}|${threadId}|${narrow}` `` "so no effect resets it". Open at 390, go to 1024, return to 390: the stored key equals the current one and the panel **reopens**; the test (and Req 7: "closed when narrow") is right. A build that follows the plan literally fails it. In the sketch an effect clearing the state when `narrow` turns false passes it. The test stays as it is; the code-writer should say the departure in *Found while building*.

### 4. The journey's scroll arrangement is untested by a run — minor, unverified
**Where:** `chat_page.py` `is_where_left` · it raises `the arrangement did not separate the readings` when the left-at position is within 100px of either end. With 10 + 1 + 15 filler messages at 844px that is plausible, but it was not run; if it trips, the red is the arrangement's, not the code's. The code-writer's first e2e run settles it; they may adjust the 10/15 counts (a test-file change they cannot make, so it would go back as a send-back).

## Left for later stages
- **Finding 3** (above): the code-writer resets the member panel on crossing to wide.
- **Finding 4:** if `is_where_left` raises its arrangement message at the first e2e run, send it back to the test pair for more filler.
- A `display:none` build that loses the scroll position is caught only by the journey (the plan says so); nothing at Vitest can show it.
- Plan-reviewer-3's notes stand: the 360 tour starts a DM with Grace and writes to the server; acceptance check 3 is performed in Decision 23's order; Decision 24 is assumed.

## Checked and sound
- Every red is the behaviour missing (module not found, missing role/name, heading still present); no typo, bad path or fixture error among the 38 that run. The by-design green, `wide / shows the sidebar and no ☰`, passes today and is the positive for the narrow tests.
- No existing test was touched except `setup.ts` (adds the fake and its reset) and the moved BDD step, unchanged in body; 621 passed, none removed or loosened.
- Widths are literals in the hook test; `matchMedia` is read inside `subscribe`/`getSnapshot`, as the plan requires; the harness throws on unsupported queries.
- Each negative drawer test has its positive in the same test or its neighbour (blank search then real search; held DM post then release; Escape/close then ☰ reopens).
- Files changed are all in the plan's file map; the report's list matches `git show --stat 5bb945a`; no production code, config or docs written.
- Page objects hold the new testids; step definitions contain no selectors; `Then none of them scrolls sideways` reads `tour["result"]` and fails with a `KeyError` if the `When` never ran.
