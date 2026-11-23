# CollabHub on a phone — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** Below 768px the sidebar is a modal drawer behind ☰ on every shell screen, the thread and
member panels cover the message view with a back control, every screen fits 360px, and crossing the
breakpoint loses nothing.

**Architecture:** One hook, `useNarrow()`, reads `matchMedia('(min-width: 768px)')` and is the only
source of "narrow"; the shell and the channel view choose classes and attributes from it in JS. **The
element tree is the same at every width**: narrow changes classes, attributes and leaf siblings,
never the type or position of an ancestor of the route's content, `MessageList`, `MessageComposer` or
`ThreadPanel` — so a rotation re-renders and never remounts. The drawer is `ChatLayout` state; a
panel covers the message column as an overlay while the column stays mounted, which is what keeps
its scroll position.

**Tech Stack:** React 19, react-router-dom 7, TanStack Query, Zustand, Tailwind CSS v4 · Vitest +
jsdom + MSW + user-event 14.6 · pytest-bdd + Playwright (sync).

**Issue:** `docs/plans/gh-9/00-issue.md` — read it first. This plan argues from it and does not
repeat it.

**Worktree:** `../caw-gh-9`, branch `feature/gh-9`, from `main` at `380693a` (gh-8, the "⋯" menu
this builds on, is merged there).

## Decisions

Decided by the issue:

| # | Question | Answer |
|---|---|---|
| 1 | The breakpoint | Narrow is a viewport under 768px; 768px and over is today's layout |
| 2 | ☰ | On every shell screen (`/`, a channel, a DM, `/search`, `/settings`); any navigation made from the drawer closes it |
| 3 | The drawer | A modal: backdrop, focus in and held, focus back to ☰ on close |
| 4 | Back | Unchanged: it closes a thread; nothing else is added to history |
| 5 | Platform | Responsive web only; **D20 stays 🔴 and untouched** |
| 6 | Palette | Light only (D26, D28) |

Taken in this plan:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 7 | How "narrow" is computed | `useNarrow()` in `lib/layout/useNarrow.ts`, `useSyncExternalStore` over `window.matchMedia('(min-width: 768px)')`, narrow = `!matches`. The shell's width-dependent classes are chosen in JS from it — no `md:` variants for them | jsdom evaluates no media query (issue, *What this assumes*), so a layout in CSS alone is untestable; one source means CSS and JS can't disagree at 767/768. Alternative: `md:` classes plus the hook — two copies of the breakpoint |
| 8 | Remounting | One tree at every width (see *Architecture*) | `MessageList` is keyed and starts at its newest message on mount (`ChannelView.tsx:95-97`); `ThreadPanel` is keyed by root and owns its scroll. Two layouts (`MobileShell`/`DesktopShell`) would remount both on a rotation and lose the scroll position Req 7 keeps |
| 9 | How a panel covers | Absolutely positioned over the message column, which stays mounted and laid out, and carries `inert` while covered. Never `display:none` on the column | A scroller whose box is destroyed by `display:none` can come back at `scrollTop` 0, and jsdom can't show it — only the journey can, which is why its last check is the scroll position. Alternative: unmount the column while covered — loses the position outright |
| 10 | Where the drawer's state lives | `useState` in `ChatLayout` | The shell is one instance across the four shell routes: react-router renders each match as an unkeyed `RenderedRoute` (`node_modules/react-router/dist/development/chunk-KS7C4IRE.mjs:6291-6340`), so `<Protected>`→`ChatLayout` is reconciled, not remounted — the socket comment at `ChatLayout.tsx:5-10` relies on the same fact. Alternative: the chat store — nothing outside the shell reads it |
| 11 | A closed drawer | The `hidden` attribute on the `<aside>`, not only a class | Tailwind's preflight makes `[hidden]` `display: none !important` (`node_modules/tailwindcss/preflight.css:396-398`), so a `flex` class can't override it; it takes the drawer's controls out of the tab order and the accessibility tree, which is also how Vitest sees "closed" |
| 12 | Closing on navigation | An optional `onNavigate?: () => void` prop on `ChannelList`, `DirectMessageList`, `SearchBox` and `WorkspaceSwitcher`, and `CreateChannelDialog`'s existing `onCreated`; `ChatLayout` passes its one `closeDrawer` to all five | A location listener would miss two members of the family: submitting the query already on `/search` navigates nowhere (`SearchBox.tsx:7-9`), and switching workspace doesn't navigate (`session.changeWorkspace`). A failed create doesn't navigate, so the drawer stays open on its error |
| 13 | A new DM — **assumed** | The drawer closes when the DM opens and the app navigates (`onSuccess`), not at the pick | The issue says picking "navigates, so it closes". A failed open shows nothing today, and closing at the pick would leave the user on the old screen with no sign why. Changing it is one line and one test |
| 14 | Focus in the drawer | Opening focuses the drawer's **Close sidebar** button; Tab on the last control and Shift+Tab on the first wrap inside it (a keydown handler, `preventDefault`); `<main>` and the top bar are `inert` while it is open; every close while narrow focuses ☰ | The trap is code, so Vitest proves it: user-event skips Tab's default when keydown is prevented (`@testing-library/user-event/dist/esm/event/dispatchEvent.js:23-41`), as `MessageActions` already relies on |
| 15 | Where ☰ sits — **assumed** | A narrow-only top bar in the shell above `<main>`: ☰ and the word "CollabHub". Below it, each screen's own header as today | One ☰ for every screen, in the shell that owns the drawer. Alternative: ☰ inside each screen's header — four places. Changing it is markup in two files |
| 16 | "Opens on arrival" — **assumed** | The drawer opens whenever the pathname becomes `/` while narrow: the first load, the return from sign-in, an archive (`navigate('/')`), Settings' Back to chat with no channel. Crossing to narrow while on `/` does **not** open it | `/` is "Pick a channel" — a screen with nothing on it but the drawer. A modal appearing on a rotation would be a surprise. Alternative: the very first load only; one condition |
| 17 | The member panel when narrow — **assumed** in part | A **Members** button in `ChannelHeader` (not on a DM), `aria-expanded`, toggles a covering panel with a **Back to channel** control. Its open state belongs to one (channel, thread, width): changing any of them closes it | Req 7 resets it on crossing; resetting on a channel switch and on a thread opening follows the same reading (a panel left open in the next channel, or reappearing when a thread closes, would contradict Req 5's "returns to the channel"). Held as `membersOpenFor: string \| null` compared with `` `${channelId}|${threadId}|${narrow}` ``, so no effect resets it |
| 18 | The back controls | The thread's existing `thread-close` button, named **Back to channel** when narrow and **Close thread** when wide; the member panel's **Back to channel** (`members-close`) | The issue leaves their look to the plan. One control per panel; the thread's keeps its `replace` (`useThreadParam.ts:28-39`), so Back still doesn't reopen it |
| 19 | What a covering panel leaves visible — **assumed** | The shell's top bar and the channel header stay; the panel covers the list and the composer | The reader can still see which channel the thread belongs to, and ☰ stays reachable (Req 2). Alternative: cover the header too — classes only |
| 20 | Read state under a covering panel — **assumed** | Unchanged: the covered list counts as read exactly as it does beside a thread when wide | No requirement speaks to it, and changing it touches `readState`. Alternative: stop reading while covered — one predicate and a test |
| 21 | The keyboard | `interactive-widget=resizes-content` in the viewport meta, and `#root` at `100dvh` | The issue's own assumption, provable only on a device: left for the human (*Acceptance*) |
| 22 | The register | **D48 🟢**, a responsive web layout below 768px, leaving D20 open; an ADR as D47 had | The issue's *Record in this slice* |

Nothing here builds on a 🔴 entry. **D20** (React Native vs PWA) is the nearest and stays open: no
manifest, no service worker, nothing platform-specific in `/lib`. D26 and D28 are 🟢 and only
followed (Tailwind v4, light palette).

## Corrections to the issue

- **"Every Playwright context is `browser.new_context()` with defaults (`tests/bdd/conftest.py:259,
  :342`)"** is out of date: gh-8 added `TOUCH_TABLET` (1024×768, `has_touch`) at `conftest.py:262`
  and `ada_touch_context` at `:349-360`. It is still wider than 768px, so the conclusion stands —
  every existing journey runs the wide layout — and Task 3 updates its comment, which names gh-9.
- `ThreadPanel`'s `w-80 shrink-0` is at `ThreadPanel.tsx:142`, not `:139`. No consequence.

## Test approach — recommendation to the test pair

**BDD outside-in, with one journey.** This is a new capability a user sees, and it changes journeys
the suite already has (picking a channel, a thread and Back). Only a real browser proves three
things here: the drawer is tappable on a phone context, the thread's Back returns to a scroll
position jsdom cannot hold, and nothing scrolls sideways. Write the journey first; everything under
it goes down to Vitest.

| Behaviour | Layer | File |
|---|---|---|
| On a phone, Ada picks #general from the drawer, reacts and replies through "⋯", goes Back to where she was, and nothing scrolls sideways | **BDD** | `tests/bdd/features/phone_layout.feature` |
| `useNarrow`: 767 narrow, 768 wide, follows changes both ways, unsubscribes | Vitest | `src/lib/layout/useNarrow.test.ts` |
| The drawer — first load, ☰ on every screen, each way it closes and doesn't, modal focus, "⋯" closed by it, the search path — and crossing the breakpoint with a thread, a draft, a scroll position and the member panel | Vitest, through the real `App` | `src/App.narrow.test.tsx` |
| The panels covering, their back controls, browser Back, the member panel's default and its resets | Vitest, through `ChannelView` with the real `ChannelList` | `src/features/channels/ChannelView.narrow.test.tsx` |

**What no test covers**, and who checks it instead:
- **360px on every screen** — the CSS in Task 7. jsdom does no layout; the journey checks sideways
  scroll at 390 on a channel; the acceptance-reviewer's check 4 covers every screen at 360.
- **The composer above the on-screen keyboard** (Decision 21), and a real rotation — the human, on
  a real phone (*Acceptance*, "For the human").
- The drawer's look and animation — not specified.

**Baseline**, from `docs/test-report.md` at `9dfde148e3b1-dirty`: unit 2099 passed, of which the
frontend's Vitest 620; end-to-end 26 passed; integration not run. Expected counts are "N or more".

## Global constraints

- Server state stays in TanStack Query and no copy goes into Zustand (D24); this slice adds no server
  state at all. The drawer and member-panel state are component state.
- Vitest queries by role, label and text only; `data-testid`s are for `tests/bdd` and live in the page
  object (CLAUDE.md).
- No API, route, env var, chart or Compose change. The SPA's routes and the Ingress allow-list are
  untouched (checked: no new path).
- Everything else as CLAUDE.md says; the lint hook blocks on eslint/ruff findings.

## File map

| File | Change | Responsibility | Task |
|---|---|---|---|
| `src/frontend/src/test/viewport.ts` | create | fake `matchMedia` and `setViewportWidth` | 1 |
| `src/frontend/src/test/setup.ts` | modify | install the fake at 1024px; reset it after each test | 1 |
| `src/frontend/src/lib/layout/useNarrow.test.ts` | create | the hook | 1 |
| `src/frontend/src/App.narrow.test.tsx` | create | drawer and crossing, through `App` | 2 |
| `src/frontend/src/features/channels/ChannelView.narrow.test.tsx` | create | the panels | 2 |
| `tests/bdd/features/phone_layout.feature` · `steps/test_phone_layout_steps.py` | create · create | the journey | 3 |
| `tests/bdd/steps/conftest.py` · `steps/test_message_action_steps.py` | modify · modify | `Grace has sent "{body}" in "{channel}"` moves to conftest, unchanged | 3 |
| `tests/bdd/conftest.py` | modify | `PHONE`, `ada_phone_context`; `TOUCH_TABLET`'s comment | 3 |
| `tests/bdd/pages/chat_page.py` | modify | `phone=`, the drawer, Back, where-left, sideways | 3 |
| `src/frontend/src/lib/layout/useNarrow.ts` | create | the hook | 4 |
| `src/frontend/index.html` · `src/frontend/src/index.css` | modify | viewport meta; `#root` height | 4 |
| `features/channels/ChatLayout.tsx` | modify | top bar, drawer, backdrop, focus, `onNavigate` wiring | 5 |
| `features/channels/ChannelList.tsx` · `DirectMessageList.tsx` · `WorkspaceSwitcher.tsx` · `features/search/SearchBox.tsx` | modify | `onNavigate` | 5 |
| `features/channels/ChannelView.tsx` · `ChannelHeader.tsx` · `MemberPanel.tsx` · `features/threads/ThreadPanel.tsx` | modify | covering panels, Members button, back controls | 6 |
| `features/channels/MessageItem.tsx` · `features/attachments/AttachmentList.tsx` · `features/search/SearchResult.tsx` | modify | fit 360px | 7 |
| `docs/design/06-frontend-spa.md` · `07-open-decisions-register.md` · `docs/adr/261123-a-responsive-layout-below-768px.md` · `docs/plans/ch06/gherkin/00-scenario-vocabulary.md` | modify · modify · create · modify | the record | 8 |

Paths under `features/` are relative to `src/frontend/src/`. Deliberately unchanged:
`stores/chat.ts` (Decision 10), `useThreadParam.ts` (Back works as today), `MessageList.tsx`
(Decision 20), `tests/bdd/conftest.py`'s truncation (no table), `MessageActions.tsx` — the drawer
closes the menu through the store's existing `openMessageMenu`.

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–3 | test-writer | failing Vitest tests and a journey that binds, each failing for the reason given — **test-reviewer gate** |
| GREEN — the hook | 4 | code-writer | Task 1 passes |
| GREEN — shell and panels | 5–7 | code-writer | Task 2 passes; `tsc` clean |
| Finish | 8–9 | code-writer | the record, then verification and the journey's first run |

One red phase: nothing is typed from a generated contract, so the SPA's red needs nothing built.

---

## Task 1: Viewport harness and `useNarrow` (RED)

**Files:** `src/test/viewport.ts` (create), `src/test/setup.ts` (modify),
`src/lib/layout/useNarrow.test.ts` (create)

**Interfaces** — the hook Task 4 builds, in `src/frontend/src/lib/layout/useNarrow.ts`:
- `export const NARROW_BELOW = 768`
- `export function useNarrow(): boolean` — `true` when `window.matchMedia('(min-width: 768px)')`
  does not match. It calls `window.matchMedia` inside `subscribe`/`getSnapshot`, **never at module
  load**: the fake is replaced after every test, and a cached `MediaQueryList` would listen to the
  previous test's.

**The harness**, `src/test/viewport.ts` (test-writer's; a test helper, never GREEN's):
- `installViewport(width = 1024): void` — defines `window.matchMedia` (jsdom has none — no
  `matchMedia` in `jsdom/lib/jsdom/browser/Window.js`) returning a fake `MediaQueryList`:
  `media`, a live `matches`, `addEventListener`/`removeEventListener('change')`, the legacy
  `addListener`/`removeListener`, `onchange`. It understands `(min-width: Npx)` and
  `(max-width: Npx)` only and throws `Unsupported media query: <q>` for anything else, so a hook
  asking a rem query fails loudly rather than quietly reading wide.
- `setViewportWidth(width: number): void` — inside `act`: sets `window.innerWidth`, fires `change`
  on every list whose `matches` flipped, then a window `resize`.
- `changeListenerCount(): number` — live `change` listeners, for the unsubscribe test.
- `setup.ts` calls `installViewport()` at import (before any test module) and re-installs it at
  1024 in its `afterEach`. Every existing test therefore runs wide, as today.

| Test | Proves | Expected red |
|---|---|---|
| `is narrow at 767px and wide at 768px` | both sides of the breakpoint, each from its own first render | `Failed to resolve import "./useNarrow"` — the whole file; every test in it needs the module |
| `follows the width across 768 in both directions` | 1024 → 767 turns true, 767 → 768 turns false, in one mounted hook | same |
| `stops listening when unmounted` | `changeListenerCount()` back to its value before the mount, having been one more while mounted | same |

The width literals are in the tests, never `NARROW_BELOW` — an import that doesn't exist yet would
make them `NaN` (*Tests that prove something*). Leave uncommitted.

## Task 2: The shell and the panels (RED)

**Files:** `src/App.narrow.test.tsx`, `src/features/channels/ChannelView.narrow.test.tsx` (create)

**Interfaces** — markup and props Tasks 5 and 6 build, and the names the tests query:

| Where | When | What |
|---|---|---|
| shell top bar | narrow only | `<button aria-label="Open sidebar" aria-expanded aria-controls={sidebar id}>` (☰), `data-testid="drawer-open"` |
| `<aside>` (the sidebar, `data-testid="sidebar"`, same element at every width) | narrow and open | `role="dialog" aria-modal="true" aria-label="Sidebar"`, first child `<button aria-label="Close sidebar">` (`drawer-close`) |
| | narrow and closed | the `hidden` attribute |
| | wide | as today: no role, no `hidden`, no Close sidebar |
| backdrop | narrow and open | `<button type="button" tabIndex={-1} aria-label="Dismiss sidebar">` (`drawer-backdrop`), outside the aside, covering the page |
| `<main>`, top bar | narrow and open | `inert` |
| `ChannelHeader` | narrow, not a DM, no thread open | `<button aria-expanded={membersOpen}>Members</button>` (`members-open`); new props `onToggleMembers?: () => void`, `membersOpen?: boolean` — the button renders when `onToggleMembers` is given |
| `MemberPanel` | narrow, opened | new prop `onBack?: () => void`; given, the panel covers and shows `<button>Back to channel</button>` (`members-close`) |
| `ThreadPanel` | narrow | new prop `fullScreen?: boolean` (default `false`); `thread-close`'s accessible name is **Back to channel** when true, **Close thread** when false |
| the message column (list + composer) | narrow and a panel open | `inert` |
| `ChannelList`, `DirectMessageList`, `SearchBox`, `WorkspaceSwitcher` | every width | new prop `onNavigate?: () => void`, called by: a channel link's click · a DM link's click · a DM pick, when it navigates · a non-blank search submit, both when it navigates and when it only refetches · the **current-user** link's click · a workspace option's click |

"Shown"/"closed" as the tests read them: the drawer is open ⇔ `getByRole('dialog', { name:
'Sidebar' })`; closed when narrow ⇔ no such dialog **and** the sidebar's `link`s (channels, your
name) not accessible (the `hidden` attribute). The member panel is shown ⇔ the heading **Members**.
A node is "the same" ⇔ `toBe` the element held before the change.

Each `App.narrow` test follows `App.settings.test.tsx`: `vi.resetModules()`, a fresh `App`, a
returning user's Auth stubs, a channel list `general` and `random` plus a DM with Grace, and
`setViewportWidth(390)` **before** rendering unless the test says otherwise. Each `ChannelView.narrow`
test follows `ChannelView.thread.test.tsx`'s `Shell` (`Back`, `ChannelList`, `ChannelView`) and its
stubs, at 390 unless it says otherwise. Messages use `fireEvent.click` where a pointer event would
close a "⋯" menu by itself.

**`App.narrow.test.tsx` — the drawer**

| Test | Proves | Expected red |
|---|---|---|
| `opens on a narrow / and holds focus inside it` | Req 4 first load; Req 3 focus in: dialog **Sidebar** present, `document.activeElement` inside it, `<main>` `inert` | `Unable to find role="dialog" and name "Sidebar"` |
| `a link straight to a channel, a DM, /search or /settings opens closed, with ☰` | Req 4; Req 2's every screen — four renders in one `it.each`, each: ☰ present, no dialog, channel links inaccessible | `Unable to find role="button" and name "Open sidebar"` |
| `wide / shows the sidebar and no ☰` | the wide side of Req 1 and 4: at 1024 no dialog, no ☰, the `general` link accessible | **passes at red, by design** — today's layout; it fails a build that opens the drawer or shows ☰ at 768+ |
| `crossing to narrow on / leaves it closed` | Decision 16: render at 1024 on `/`, `setViewportWidth(767)`: ☰ present, no dialog | `Unable to find … "Open sidebar"` |
| `☰ opens it and Close sidebar closes it, focus back on ☰` | Req 2, Req 3 | `Unable to find … "Open sidebar"` |
| `a press on the backdrop closes it and nothing else` | *Where the rules meet*: on `/c/general?thread=<root>`, open, press **Dismiss sidebar**: dialog gone, `location()` pathname and search unchanged, thread panel still there, focus on ☰ | same |
| `Escape closes it, focus back on ☰` | Req 2, Req 3 | same |
| `Tab and Shift+Tab wrap inside it` | Req 3: Shift+Tab from **Close sidebar** lands inside the dialog; Tab from the last control (the connection status has none — the last is **Sign out**) lands on **Close sidebar** | same |
| `picking a channel closes it and opens the channel` | Req 2; Paths "First load of `/`": from `/`, click `general`: dialog gone, `/c/<general>`, focus on ☰ | `Unable to find role="dialog"` (first load) |
| `picking a DM from the list closes it` | Req 2 | `Unable to find … "Open sidebar"` |
| `starting a new DM closes it once it opens` | *Where the rules meet* (Req 2, 4); Decision 13: **New direct message** → pick Grace with the open-DM `POST` held on a deferred: dialog **still open** while held; released: dialog gone, at the DM | same |
| `submitting a search closes it and shows /search` | Req 2, *Search and the drawer*: type, Enter: dialog gone, `/search?q=…` | same |
| `submitting the query already on /search closes it` | the other branch of `SearchBox.submit` (no navigation) | same |
| `a blank search leaves it open` | the positive's neighbour: nothing submitted, nothing closes | same |
| `following your name to /settings closes it` | Req 2 | same |
| `switching workspace closes it` | Req 2 | same |
| `creating a channel closes it and opens the channel` | Req 2 | same |
| `a refused create leaves it open, with the error` | the failure side: a 409 stub, dialog still open, the banner shown | same |
| `typing in the create form or opening the new-DM list leaves it open` | Req 2 "nothing else": type a name; press **New direct message** (`aria-expanded` true); dialog still open after each, anchored to the typed value and the expanded list | same |
| `opening it closes an open "⋯" menu` | *Where the rules meet*: on a channel, `fireEvent.click` "Message actions" (menu open), `fireEvent.click` ☰: no `role="menu"`, `openMessageMenu` null, dialog open | same |
| `picking a search result opens the channel with the drawer still closed` | *Search and the drawer*: search from the drawer, click a result: `/c/<id>?message=<id>` (or the param already removed), no dialog, ☰ present | same |

**`App.narrow.test.tsx` — crossing the breakpoint**

| Test | Proves | Expected red |
|---|---|---|
| `a thread stays open, the same panel, side ⇄ full screen` | Req 7; Paths "Rotate": at 1024 on `/c/general?thread=<root>`, hold the thread panel node; → 390: same node, **Back to channel**, message column `inert`; → 1024: same node, **Close thread**, column not `inert` | `Unable to find role="button" and name "Back to channel"` |
| `the composer's draft and its node survive both crossings` | Req 7: type in the channel composer at 1024; → 390 → 1024: the same textarea, its value kept, ☰ present at 390 | `Unable to find … "Open sidebar"` |
| `the channel list keeps its scroll position across both crossings` | Req 7: `giveLayout` the list's scroller at `scrollTop` 300 of 1200 (viewport 500); → 390 → 1024: the same node at 300, ☰ present at 390 | same |
| `the member panel takes each width's default` | Req 7, *The member panel across the breakpoint*: 1024 shown; → 390 hidden and **Members** offered; open it; → 1024 shown, no **Back to channel**; → 390 hidden again | heading **Members** still present at 390 |
| `wide to narrow with a thread open keeps the thread covering` | *The member panel across the breakpoint*, its exception: → 390: thread panel, **Back to channel**, no **Members** heading | `Unable to find … "Back to channel"` |
| `the drawer is closed after crossing to wide and back` | Req 7: open at 390; → 1024: no dialog, no ☰, sidebar links accessible; → 390: no dialog | `Unable to find … "Open sidebar"` |

**`ChannelView.narrow.test.tsx` — the panels**

| Test | Proves | Expected red |
|---|---|---|
| `at 768 the member panel is beside the list; at 767 it is closed with a Members button` | Req 1's boundary on the panel, two renders | at 767: heading **Members** still present |
| `a thread covers the list; Back to channel returns at the scroll position left` | Req 5; Paths "A thread, then Back": `giveLayout` the list at 300; open a thread from its summary: **Back to channel**, column `inert`; press it: no panel, the same scroller at 300, `?thread` gone | `Unable to find … "Back to channel"` |
| `the browser's Back closes a covering thread at the same position` | Req 5, *A thread opened from a narrow channel*: as above, closing with the `Back` button (`navigate(-1)`); asserts the covering form before Back | same |
| `Members opens a covering panel; Back to channel closes it; no history entry` | Req 5: press **Members** (`aria-expanded` true): heading **Members**, column `inert`, `location().key` unchanged; **Back to channel**: heading gone, column not `inert` | `Unable to find role="button" and name "Members"` |
| `the member panel closes on a channel switch` | Decision 17: open in `general`, click `random`: no **Members** heading in `random` | same |
| `a DM offers no Members button` | the DM rule, anchored: `general` shows **Members**; open the DM: none, no panel | same |

Leave uncommitted.

## Task 3: The journey (RED)

**Files:** `tests/bdd/features/phone_layout.feature`, `tests/bdd/steps/test_phone_layout_steps.py`
(create); `tests/bdd/steps/conftest.py`, `steps/test_message_action_steps.py`, `tests/bdd/conftest.py`,
`tests/bdd/pages/chat_page.py` (modify)

```gherkin
@bdd
Feature: CollabHub on a phone

  Below 768px the sidebar is a drawer behind ☰, and a thread covers the channel
  until Back returns to it, where it was left. The drawer's rules, the panels and
  crossing the breakpoint are proven lower down.

  Background:
    Given Ada is signed in

  # Ada is on a 390 by 844 phone with touch; Grace is on a desktop.
  Scenario: On a phone, Ada picks a channel from the drawer, replies in a thread and goes Back
    Given Ada has created a public channel named "general"
    And Ada has created a public channel named "random"
    And Grace has sent 10 messages in "general"
    And Grace has sent "lunch at noon?" in "general"
    And Grace has sent 15 messages in "general"
    When Ada opens the "general" channel
    Then Ada is looking at the "general" channel
    When Ada reacts to "lunch at noon?" with "tada"
    Then Grace sees "lunch at noon?" with 1 "tada" reaction
    When Ada replies "count me in" in the thread on "lunch at noon?"
    Then Grace sees 1 reply on "lunch at noon?" without reloading
    When Ada goes Back
    Then Ada sees the "general" channel where she left it
    And nothing on Ada's screen scrolls sideways
```

- **Reused verbatim:** `Ada is signed in`, `Ada has created a public channel named`, `Ada opens the
  "{name}" channel`, `Ada is looking at the "{name}" channel`, `Ada reacts to … with …`, `Grace sees
  … with {count} "{emoji}" reaction`, `Ada replies … in the thread on …`, `Grace sees N reply on …
  without reloading`, and `Grace has sent "{body}" in "{channel}"` — moved, unchanged, from
  `test_message_action_steps.py` into `steps/conftest.py` (pytest-bdd resolves from the calling
  module and conftest only; vocabulary §35 did the same).
- **New:** `Given Grace has sent {count:d} messages in "{channel}"` (one `grace.open()`, open the
  channel, wait for the join, then `count` × `send_message_and_wait` with bodies unique in the
  scenario) · `When Ada goes Back` · `Then Ada sees the "{name}" channel where she left it` · `Then
  nothing on Ada's screen scrolls sideways`.
- **Why 10, then the message, then 15:** the list opens at its newest; reaching "lunch at noon?"
  scrolls it up to a position that is neither the top (a scroller that lost its box comes back at 0)
  nor the bottom (a remounted list starts at its newest). Both wrong builds then fail the last-but-one
  `Then`.
- **Fixtures** (`tests/bdd/conftest.py`): `PHONE = {"viewport": {"width": 390, "height": 844},
  "has_touch": True, "is_mobile": True}` and a function-scoped `ada_phone_context`, as
  `ada_touch_context` is and for its reason. `TOUCH_TABLET`'s comment stops saying narrow screens
  are gh-9's and says they are `PHONE`'s. The steps module overrides `ada` with
  `ChatPage(page, base_url, touch=True, phone=True)`, as `test_message_action_steps.py` does.
- **Page object** (`chat_page.py`), new testids only there:
  - `phone: bool = False` in `__init__`.
  - `_ensure_drawer_open()` — phone only: if `sidebar` is not visible, press `drawer-open` and
    expect `sidebar` visible. `create_channel` calls it first.
  - `open_channel` on a phone: `_ensure_drawer_open()`, press the channel, expect the named view,
    then **expect `sidebar` hidden** (the drawer closed by the navigation). Unchanged elsewhere.
  - `reply_in_thread` records the `message-list` element's `scrollTop` just before pressing
    `thread-open`, in `self._left_at` (every device; harmless on wide).
  - `go_back()` — `page.go_back()`, then expect `thread-panel` to have count 0.
  - `is_where_left(name) -> bool` — first asserts the arrangement separated the readings:
    `_left_at` ≥ 100 and ≤ `scrollHeight − clientHeight − 100`, else raises `AssertionError("the
    arrangement did not separate the readings: …")`; then waits (`wait_for_function`) for the
    named view's `message-list` `scrollTop` within 2px of `_left_at`.
  - `sideways_scrollers() -> list[str]` — evaluated in the page: the document if its `scrollWidth >
    clientWidth`, and every element whose computed `overflow-x` is `auto` or `scroll` with
    `scrollWidth > clientWidth + 1`, each described by tag and `data-testid`. The step asserts it is
    `[]`. (An `overflow-y-auto` scroller computes `overflow-x: auto`, so `<main>` and the list are
    checked, not only the page.)

**Expected red** — the suite can't run before the code-writer; the test-writer proves the feature
parses and every step binds (`--collect-only`, `--generate-missing` printing nothing). Run against
today's build, it would fail at `When Ada opens the "general" channel`: the 390px sidebar is visible
(no ☰ needed), the press navigates, and *expect `sidebar` hidden* times out — there is no drawer.
Leave uncommitted.

## Task 4: The hook, the viewport (GREEN)

- [ ] `lib/layout/useNarrow.ts` to Task 1's interface. Task 1: 3 passed.
- [ ] `index.html:5`: `content="width=device-width, initial-scale=1.0, interactive-widget=resizes-content"`.
- [ ] `index.css:28-31`: keep `height: 100%` on `html, body`; give `#root` `height: 100dvh`.
- [ ] Leave uncommitted.

## Task 5: The shell and the drawer (GREEN)

- [ ] `ChatLayout`: `const narrow = useNarrow()`, `const [drawerOpen, setDrawerOpen] = useState(false)`,
  shown = `narrow && drawerOpen`. One `openDrawer()` — sets it, and
  `useChatStore.setState({ openMessageMenu: null })`, so a "⋯" menu closes even when no
  `pointerdown` did — and one `closeDrawer()` — clears it and, while narrow, focuses ☰ (a ref).
  Every close goes through `closeDrawer`.
- [ ] Markup to Task 2's table. Children of the grid stay `[top bar?, backdrop?, aside, main]` with
  the narrow-only ones written `{narrow && …}`, so `<aside>` and `<main>` keep their positions at
  every width; `{children}` stays the only child of `<main>`. Wide classes are today's; narrow:
  one column, the aside `fixed` at the left, `max-w-[85vw]`, above the backdrop.
- [ ] Focus: an effect on `shown` turning true focuses **Close sidebar**; the aside's `onKeyDown`
  handles Escape (`closeDrawer`) and the Tab wrap over its focusable, non-disabled descendants.
- [ ] Arrival: an effect on `pathname` opens the drawer when it is `/` and the width is narrow
  **at that moment** (read through a ref, so `narrow` is not a dependency — Decision 16).
- [ ] Width: when `narrow` turns false, set `drawerOpen` false without moving focus.
- [ ] `onNavigate={closeDrawer}` to `ChannelList`, `DirectMessageList`, `SearchBox`,
  `WorkspaceSwitcher`; `onCreated` navigates then closes. In each component, call `onNavigate` at
  exactly the points Task 2's table lists — `SearchBox` after its blank check, in both branches;
  `DirectMessageList` beside its `navigate` in `onSuccess`.
- [ ] Task 2's drawer tests pass. Leave uncommitted.

## Task 6: The panels (GREEN)

- [ ] `ChannelView`: `useNarrow()`; `membersOpenFor` as Decision 17; the row at `:93` becomes
  `relative`; the message column gets `inert` when narrow and a thread or the members are shown.
- [ ] `ThreadPanel fullScreen={narrow}`: when true, `absolute inset-0 z-10 w-full bg-surface`
  instead of `w-80 shrink-0`, and the close button reads **Back to channel**. Same element, same
  key, so no remount.
- [ ] Member panel: wide — as today when no thread and not a DM. Narrow — rendered only when open,
  with `onBack` closing it, covering as the thread does. `ChannelHeader` gets `onToggleMembers` and
  `membersOpen` only when narrow, not a DM and no thread is open.
- [ ] Task 2: every test passes. `npm --prefix src/frontend run typecheck` clean. Leave uncommitted.

## Task 7: 360px (GREEN)

Nothing at this layer can test it (*What no test covers*); the journey and acceptance check 4 do.
What overflows 360 today, found by reading the classes:

- [ ] `AttachmentList.tsx:141`: `max-w-80` (320px) inside a `px-6` row leaves 312px at 360 → cap at
  `max-w-[min(20rem,100%)]`; the file chip at `:164` gets `max-w-full` so `truncate` can work.
- [ ] `MessageItem.tsx:160` and `SearchResult.tsx:38`: add `[overflow-wrap:anywhere]` — a long URL
  in `whitespace-pre-wrap` text is one unbreakable word.
- [ ] `ChannelHeader`'s `<h2>`: `break-words` (a long name). Check the composer row, the Settings
  page and the sign-in page at 360 in the first real run (Task 9) and fix what is found there.
- [ ] Leave uncommitted.

## Task 8: The record

- [ ] Doc 06: a new subsection at the end of §3, *Layout below 768px — added 2026-11-23 (D48)*: the
  hook and the one-tree rule, the drawer (☰ on every shell screen, modal, focus, each way it
  closes, opens on arrival at `/`), the covering panels and their back controls, what crossing
  keeps, the viewport meta, and what only a device proves. In §5.2 *Threads*, the panel "below
  768px covers the message view (§3)". In §9, Settings is "reached from your name in the sidebar —
  in the drawer below 768px".
- [ ] Register: **D48 🟢** in the Frontend table — a responsive web layout below 768px; built
  against it: `useNarrow`, `ChatLayout`'s drawer, the covering panels, `phone_layout.feature`;
  **D20 stays open**. D47's "Layout below 768px is gh-9" becomes a pointer to D48.
- [ ] ADR with the `adr-writer` skill: one tree at every width, JS-computed narrow, overlay over a
  mounted column.
- [ ] Scenario vocabulary: §36, *CollabHub on a phone — four phrases, one phone journey (gh-9)*,
  in §35's shape.
- [ ] Sweep: `grep -rn "gh-9\|768\|narrow\|mobile" docs/design src/frontend/src tests/bdd` for
  anything saying narrow screens aren't built.

## Task 9: Verification

- [ ] `scripts/test.sh lint unit`, then `scripts/test.sh e2e` — the whole layer once: the journey's
  first run, and every existing journey on its desktop or tablet context (issue *Tests*). Counts at
  or above the baseline: Vitest 620 + this plan's new tests; e2e 27. `-- -k phone` is for
  iterating if it fails. No `integration`: no service's Python, SQL or stream changes.
- [ ] `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)` and
  `.claude/hooks/security.sh`.
- [ ] **First real run**, on the Compose stack, in a browser's device mode at 360×740 and 390×844:
  the five acceptance checks by hand, plus the composer row, `/settings`, sign-in and an admin's
  channel header. Expect it to find an overflow the tests didn't; fix it, and record it below.
- [ ] Fill in *Found while building*. Leave the worktree dirty and report.

## Found while building

*Filled in by the code-writer: every deviation from this plan, and every bug the first real run
found, each with the test that now pins it down. Empty until then.*

## Not in this plan

- Swipe, pull to refresh, haptics; Back closing the drawer or the member panel; dark mode; a tablet
  layout beyond 768+; a PWA or service worker (the issue's *Not in this issue*, D20).
- Changing what counts as reading a covered channel (Decision 20).

## Self-review

- **Requirements:** 1 → Tasks 1, 2 (767/768 in the hook and on the panel), 4. 2 → Task 2's drawer
  table: every screen (it.each), close button, backdrop, Escape, channel, DM, new DM, search (both
  branches), `/settings`, workspace, create — and the "doesn't" rows (typing, new-DM list, blank
  search, refused create); Tasks 5, 3 (☰ in the journey). 3 → focus in, Tab wrap, focus back on
  each close, `inert`; Task 5. 4 → first load, links straight to four screens, Decision 16; Task 5.
  5 → `ChannelView.narrow` rows, browser Back, no history entry; Task 6; the journey's Back. 6 →
  Task 7, the journey's sideways check, acceptance check 4 and the human. 7 → the crossing table;
  Tasks 5, 6.
- ***Where the rules meet*:** drawer and "⋯" → "opening it closes an open menu" + "backdrop …
  nothing else"; drawer and navigation → "starting a new DM"; a narrow thread → the two
  `ChannelView.narrow` thread rows and the journey; search and the drawer → the two search rows and
  the result row; member panel across the breakpoint → the two crossing rows.
- ***Paths*:** first load → "opens on a narrow /" + "picking a channel"; a link to a channel →
  it.each; `/search`/`/settings` → it.each (sideways: acceptance); a DM → "picking a DM"; thread
  then Back → the `ChannelView.narrow` rows and the journey; rotate → the crossing table, through
  `App`, so `ChatLayout`'s own narrow change is in the tree; keyboard → the human.
- ***Decided already*:** 1–6 → Decisions 1–6; D20 named above.
- **Interfaces with a test each:** `useNarrow` (Task 1); ☰, Close sidebar, Dismiss sidebar, the
  dialog, `hidden`, `inert` (Task 2 drawer table); `onNavigate` on each of four components (one row
  per call point); `onToggleMembers`/`membersOpen`, `onBack`, `fullScreen` (`ChannelView.narrow`
  and the crossing table).
- **Names:** **Back to channel** for both panels' back controls, never both on screen; **Sidebar**,
  **Open sidebar**, **Close sidebar**, **Dismiss sidebar** everywhere; testids `drawer-open`,
  `drawer-close`, `drawer-backdrop`, `sidebar`, `members-open`, `members-close` only in
  `chat_page.py`.
- **Known ripple:** `setup.ts` must install the fake before any test, or every test that renders
  `ChatLayout` fails on `window.matchMedia is not a function` — so it is Task 1, RED. The moved step
  definition is RED. No GREEN task touches a test file.
