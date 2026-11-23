# Red tests — gh-9, round 1

BDD outside-in, as the plan recommends: one phone journey (`phone_layout.feature`, parses and binds, cannot run before the code-writer) and 42 Vitest tests under it (3 hook, 33 shell, 6 panels) plus the harness they stand on. Of the 42 Vitest tests, **41 fail as planned** (3 by a load failure that every one of them needs, 38 running and failing) and **1 passes by design** (`wide / shows the sidebar and no ☰`). Every one of the 620 existing Vitest tests still passes.

## Baseline
| Run | Before | After |
|---|---|---|
| Whole Vitest suite (`setup.ts` is the one existing test file changed; it touches every file) | 60 files, 620 passed | 63 files (3 new, all red), **621 passed** (620 + the by-design green), 38 failed; `useNarrow.test.ts` fails to load, so its 3 tests are not in the count |
| `tests/bdd --collect-only` | 26 collected | 27 collected (the new scenario); `message_actions.feature` still collects after its step moved |

## Tests
Layer: V = Vitest, B = BDD. Task numbers are the plan's. "Match" is whether the observed first line is the plan's.

| File · test | L | Task | Proves | Observed red (verbatim, first line) | Match |
|---|---|---|---|---|---|
| `useNarrow.test.ts` · 767 narrow / 768 wide | V | 1 | both sides of the line, each from its own first render | `Failed to resolve import "./useNarrow" from "src/lib/layout/useNarrow.test.ts"` (whole file) | yes |
| · follows the width across 768 both ways | V | 1 | 1024→767→768→500→1024 in one mounted hook | same | yes |
| · stops listening when unmounted | V | 1 | listener count rises, then returns to its start | same | yes |
| `App.narrow` · opens on a narrow / and holds focus inside it | V | 2 | Req 4, 3 | `Unable to find role="dialog" and name "Sidebar"` | yes |
| · on a narrow / it can be closed, and stays closed | V | 2 | close by button, reopen by ☰, Escape; each re-render keeps it shut | `Unable to find role="dialog" and name "Sidebar"` | yes |
| · a link straight to a channel / a DM / /search / /settings (`it.each`, 4) | V | 2 | Req 4, 2's every screen | `Unable to find role="button" and name "Open sidebar"` | yes |
| · **wide / shows the sidebar and no ☰** | V | 2 | wide side of Req 1 | **passes — green by design** | yes |
| · crossing to narrow on / leaves it closed | V | 2 | Decision 16 | `Unable to find role="button" and name "Open sidebar"` | yes |
| · ☰ opens it and Close sidebar closes it, focus on ☰ | V | 2 | Req 2, 3 | same | yes |
| · a press on the backdrop closes it and nothing else | V | 2 | rules meet | same | yes |
| · Escape closes it, focus back on ☰ | V | 2 | Req 2, 3 | same | yes |
| · Tab and Shift+Tab wrap inside it | V | 2 | Req 3 | `Unable to find role="dialog" and name "Sidebar"` | yes |
| · picking a channel closes it and opens the channel | V | 2 | Req 2 | `Unable to find role="dialog" and name "Sidebar"` | yes |
| · picking a DM from the list closes it | V | 2 | Req 2 | `Unable to find role="button" and name "Open sidebar"` | yes |
| · starting a new DM closes it once it opens | V | 2 | Decision 13: open while the POST is held, closed once it opens | `Unable to find role="dialog" and name "Sidebar"` | yes |
| · submitting a search closes it and shows /search | V | 2 | Req 2 | same | yes |
| · submitting the query already on /search closes it | V | 2 | the no-navigation branch | `Unable to find role="button" and name "Open sidebar"` | yes |
| · a blank search leaves it open | V | 2 | guard; its positive (a real query closes it) is in the same test | `Unable to find role="dialog" and name "Sidebar"` | yes |
| · following your name to /settings closes it | V | 2 | Req 2 | same | yes |
| · switching workspace closes it | V | 2 | Req 2; the same `<aside>` node survives, so a remount can't fake the close | `Unable to find role="button" and name "Open sidebar"` | yes |
| · creating a channel closes it and opens the channel | V | 2 | Req 2 | `Unable to find role="dialog" and name "Sidebar"` | yes |
| · a refused create leaves it open, with the error | V | 2 | failure side | same | yes |
| · typing in the create form or opening the new-DM list leaves it open | V | 2 | Req 2 "nothing else" | same | yes |
| · opening it closes an open "⋯" menu | V | 2 | rules meet | `Unable to find role="button" and name "Open sidebar"` | yes |
| · picking a search result opens the channel with the drawer still closed | V | 2 | rules meet | `Unable to find role="dialog" and name "Sidebar"` | yes |
| · a thread stays open, the same panel, side ⇄ full screen | V | 2 | Req 7 | `Unable to find an accessible element with the role "button" and name "Back to channel"` | yes |
| · both drafts and their nodes survive 1024 → 390 → 1024 | V | 2 | Req 7, Decision 23 | same | yes |
| · acceptance check 3's order … 390 → 844 → 390 | V | 2 | Decision 23, 24 | `Unable to find role="button" and name "Open sidebar"` | yes |
| · the channel list keeps its scroll position across both crossings | V | 2 | Req 7 | same | yes |
| · the member panel takes each width's default | V | 2 | Req 7 | `expect(element).not.toBeInTheDocument()` (heading **Members** still there at 390) | yes |
| · wide to narrow with a thread open keeps the thread covering | V | 2 | rules meet | `Unable to find an accessible element with the role "button" and name "Back to channel"` | yes |
| · the drawer is closed after crossing to wide and back | V | 2 | Req 7 | `Unable to find role="button" and name "Open sidebar"` | yes |
| · crossing to narrow with focus in the sidebar moves it to ☰ | V | 2 | Decision 24 + neighbour | `AssertionError: expected null not to be null` (☰ absent) | yes |
| `ChannelView.narrow` · at 768 beside the list; at 767 closed with Members | V | 2 | Req 1 on the panel | `expect(element).not.toBeInTheDocument()` (heading present at 767) | yes |
| · a thread covers the list; Back to channel returns at the scroll position | V | 2 | Req 5 | `AssertionError: expected false to be true` (column not `inert`; asserted before the button) | differs in order only: both are the missing cover |
| · the browser's Back closes a covering thread at the same position | V | 2 | Req 5 | `Unable to find an accessible element with the role "button" and name "Back to channel"` | yes |
| · Members opens a covering panel; Back to channel closes it; no history entry | V | 2 | Req 5 | `expect(element).not.toBeInTheDocument()` (heading present before any press; the plan said "Unable to find … Members") | differs: same cause, the narrow default is missing |
| · the member panel closes on a channel switch | V | 2 | Decision 17 | `Unable to find an accessible element with the role "button" and name "Members"` | yes |
| · a DM offers no Members button | V | 2 | DM rule, anchored on general's button | `Unable to find an accessible element with the role "button" and name "Members"` | yes |
| `phone_layout.feature` · the one scenario | B | 3 | journey | cannot run — see BDD | n/a |

## Types
`npm --prefix src/frontend run typecheck` prints exactly one error: `src/lib/layout/useNarrow.test.ts(13,27): error TS2307: Cannot find module './useNarrow'` — the hook Task 4 creates. Nothing else: the `inert`, `aria-*` and prop names the tests rely on are queried by role, not imported.

## BDD
- `uv run pytest tests/bdd --collect-only -q`: 27 collected, including `test_on_a_phone_ada_picks_a_channel_from_the_drawer_replies_in_a_thread_and_goes_back`.
- `uv run pytest tests/bdd --generate-missing --feature tests/bdd/features`: no stub printed — every step binds, including `Grace has sent "…" in "…"` after its move to `steps/conftest.py`, and `Grace has sent 10 messages in "general"` (a different pattern from the quoted one: it needs `sent <digits> messages`).
- `ruff check` and `ruff format --check` on `tests/bdd`: clean.
- **Expected red against today's build**, as the plan says: `Given Ada has created a public channel named "general"` — `create_channel` calls `_ensure_drawer_open()`; at 390 today the sidebar has no `sidebar` testid, so `is_visible()` is false, `drawer-open` is pressed and times out. (`ada_phone_context`'s sign-in passes today: the sidebar is simply visible.) Behind it, in order, the code-writer will meet: `Then Ada sees the "general" channel where she left it` (`is_where_left` raises `the arrangement did not separate the readings` if the 10/message/15 arrangement does not leave a position 100px clear of both ends) and `Then none of them scrolls sideways`.

## Departures from the plan
- **Harness API**: `viewport.ts` is as the plan says. `setViewportWidth` also sets `onchange` handlers, harmless.
- **`ChannelView.narrow` has a test-only `Link` ("Open the DM")** in its `Shell`: the plan's DM row needs a way into the DM, and the real `ChannelList` excludes DMs.
- **`App.narrow` asserts `aria-expanded` on ☰ and `hidden` on the aside** (the plan's table lists both). It also checks `Members` *button* absent in the wide-to-narrow-with-thread row (plan: "no **Members** heading"); the button's absence follows the table's "no thread open" condition.
- **`sideways_tour_at_360` takes two extra keyword arguments with defaults** (`thread_root`, `dm_partner`) so the page object does not hard-code Grace's display name; the step passes `GRACE_NAME`. `search("lunch")` is followed by an explicit `search-result` visible check so a Worker that has not indexed yet fails loudly instead of touring an empty page.
- `filler` fixture (function-scoped) in the phone steps gives the 10 and 15 filler messages distinct bodies (`filler message 001` …).
- No test dropped, renamed or moved layer. Test-writer's own checks that no scratch file remains: `git status --short` lists only the planned files.
- **The skill `superpowers:test-driven-development` is not installed in this environment** (`Unknown skill`); I followed its RED discipline from the shared context.

## Picked up from earlier reviews
- Plan review 3, *for the test-writer*: the `tour` fixture is function-scoped (`test_phone_layout_steps.py`), and `Then none of them scrolls sideways` reads `tour["result"]`, a `KeyError` if the `When` never ran.
- Plan review 3, the tour writes to the server (starts a DM with Grace): said in `sideways_tour_at_360`'s docstring; the scenario truncates messaging first.
- Decisions 23, 24: tested as above (two draft rows; focus assertions in the Back rows and the crossing row with its neighbour).

## For the code-writer
- **The `inert` readings.** Neither `@testing-library/dom` nor user-event looks at `inert`, so the tests read it as an attribute: `main` has `inert` while the drawer is open; the "message column" is covered ⇔ the composer (`Message #general`) has an `[inert]` ancestor. Put `inert` on a wrapper that contains the list **and** the composer and nothing else the tests need (the thread panel and the member panel must not be inside it). The thread panel found by `getByRole('complementary', { name: 'Thread' })` must be `toBe` the same node across a crossing.
- **"Closed"** is the `hidden` attribute on the `<aside>`; the closed sidebar's links are found with `hidden: true`, and "accessible" ones with the plain query. The held `<aside>` in the workspace test must be the same node after the close, with `hidden` set.
- **Focus** is asserted with `waitFor`, so an effect or a ref focus after the render is fine. ☰ is focused after every close while narrow (button, Escape, backdrop, channel pick, create, workspace switch via the closed drawer is not asserted for focus).
- **Tab wrap**: the last control is **Sign out**; Shift+Tab from **Close sidebar** must land inside the dialog and not on **Close sidebar**.
- **The DM POST** is held and the drawer must stay open until it resolves; closing at the pick fails.
- **Scroll**: `giveLayout` is stubbed on the list's scroller element; the crossing and the Back tests pass only if that element survives (no remount, no `display:none` that the stub can't show — the journey shows that).
- **Back to channel** focuses the `Message #general` textbox after the panel is gone, for the thread (narrow only) and the members panel; the browser's Back test does not assert focus.
- **Setup**: `src/test/setup.ts` now installs the fake `matchMedia` at 1024 before every file and after every test; `useNarrow` must call `window.matchMedia` in `subscribe`/`getSnapshot`, never at module load.
- The Vitest bodies use only roles, labels and text; the new testids are for `chat_page.py` (`sidebar`, `drawer-open`, `members-*`…): `sidebar` is the aside at every width, `drawer-open` the ☰.
- **Mutations the tests catch** (the wrong build each fails): arrival effect depending on `drawerOpen` (the "stays closed" re-render checks); closing at the DM pick (held POST); `onNavigate` missing from `SearchBox`'s no-navigation branch; workspace option not calling `onNavigate` (and a remount-based close, which the held aside node refutes); display:none for the covered column (journey only); two layouts (nodes held in the crossing rows).

## Left unproven here, by design
The 360px reach-and-use of every control, the composer above the keyboard, a real rotation — the acceptance-reviewer and the human, as the plan says.
