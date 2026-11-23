# Plan review — gh-9, round 1: changes_requested

A strong plan: one tree at every width, the overlay over a mounted column, per-control
`onNavigate` and the hand-rolled trap are all argued and checked against installed sources, and
nearly every expectation below is settled in a decision row. Three major holes remain, each small
to fix: the issue's "rotate with a thread open and a draft" path meets Decision 19 with no row and
no test, Req 4's "can be closed" has no test, and the 360px checks for sign-in, Settings and the
composer rest on a hand run no stage performs.

## Expectations

Written before the plan was opened, from the issue, doc 06 (§5.2 Threads, Message actions,
§9), the register (D20, D26, D28, D47), `ChatLayout`, `ChannelView`, `MessageList`,
`MessageActions`, `useThreadParam`, `SearchBox`, `DirectMessageList`, `WorkspaceSwitcher`,
`session.changeWorkspace`, `src/test/setup.ts` and `tests/bdd/conftest.py` + page objects.

### Decisions
- E1. How is "narrow" computed so a Vitest test can set it — one hook over `matchMedia('(min-width: 768px)')`? Exactly 768px is wide (Req 1): which side is the test boundary on (767 / 768)?
- E2. Is the drawer the same `<aside>` node restyled, or a separately mounted copy? Two copies would duplicate `data-testid`s and queries; an unmounted-when-closed drawer removes `connection-status` (read by `wait_for_join`) and `workspace-name`/`workspace-option` (read by `SignInPage.use_workspace` on every new context) from the DOM.
- E3. "Any navigation made from it" — is closing driven by the location changing, or by each control? `session.changeWorkspace` changes no URL; `SearchBox` submitting the query already on `/search` navigates nowhere; a channel link to the channel already open, or your name while on `/settings`, changes no pathname; a new DM and a created channel navigate only after a mutation resolves (and not if it fails). Which closes the drawer, and when?
- E4. "Opens on arrival" on a narrow `/` (Req 4): only the first load of the app, or every arrival at `/` (sign-in redirect, a workspace switch, a later in-app navigation to `/`, crossing wide→narrow while on `/`)?
- E5. How does a panel "cover the message view" — overlay with the list still laid out, `hidden`/`display:none`, or unmounted? Only the first keeps the list's `scrollTop` (display:none and remount both lose it — `MessageList` remount starts at the newest message).
- E6. Where does "member panel open on narrow" live (component state vs Zustand), and is its header button narrow-only (Req 1: wide is today's layout)? DMs have no member panel — no button there?
- E7. The thread's back control: the existing close (replace) or something else? Back closes a thread as today (pushes on open) — no new history entries for drawer or member panel.
- E8. The keyboard mechanism: `100dvh`, `interactive-widget=resizes-content`, or both — and recorded as unproven until a real device.
- E9. The focus trap: native `<dialog>.showModal()`, `inert` on the rest, or a hand-rolled trap — and does jsdom support the one chosen?
- E10. D48 🟢 register entry and doc 06's new section — wording that leaves D20 🔴.

### Conflicts
- C1. Req 1 "at 768px and over, the layout is today's" vs Req 7 "the member panel takes its default for the new width" — any new member-panel toggle must not appear on wide.
- C2. Req 2 "Escape closes" vs the "⋯" menu's document-level Escape handler and the new-DM disclosure — which Escape wins when both are open (Where the rules meet says opening the drawer closes the menu)?
- C3. Req 5 "the member panel and the drawer close only with their own controls" vs Req 7 "the drawer is closed whenever the width is 768px or more" and Req 2 (navigation closes it) — consistent, but the plan should state the member panel's reset on crossing is the only non-control close.
- C4. *Decided already* 4 (nothing added to history) vs any implementation of drawer/member panel via URL params.

### Tests
- T1. Vitest, narrow flag stubbed: drawer closed by default off `/`, open on `/`; each close path (close button, backdrop, Escape, channel, DM pick, new DM, search submit, `/settings` link, workspace switch, channel created) and each non-close (typing in create-channel, opening the new-DM list) — each non-close test also proving a close in the same test.
- T2. Focus moves in, Tab stays in, returns to ☰ on close.
- T3. Opening the drawer closes an open "⋯" menu; a backdrop tap closes nothing else (no click falls through to what is under it).
- T4. Thread / member panel cover the view with a back control; closing a thread keeps the list's `scrollTop` (a real non-zero value, not 0 or bottom).
- T5. Crossing both ways: thread kept, channel draft and thread draft kept, scroll kept, drawer closed on wide, member panel reset — with the "same as before" fixture differing before and after.
- T6. The default `matchMedia` stub keeps every existing test wide (jsdom has no `matchMedia`; new code calling it would crash every test that renders `ChatLayout`).
- T7. BDD: one phone journey (390×844, `has_touch`, `is_mobile`?) whose last `Then` proves the server; every desktop journey unchanged.
- T8. Req 6 (no sideways scroll at 360px, images and chips fit) — jsdom has no layout: which test, if any, proves it, or is it declared acceptance-only?

### Risks
- R1. Reading state: `MessageList` marks the channel read while `attending && atBottom`. Covered by a full-screen thread or member panel (or the drawer) on narrow, does it still count as being read? A hidden scroller measures 0/0/0 → "at bottom".
- R2. Ghost click: closing the drawer on `pointerdown` on the backdrop lets the tap's `click` land on the control beneath.
- R3. Focus lost to `<body>` when crossing wide→narrow with focus in the sidebar, or when the drawer closes because a navigation unmounted its trigger context.
- R4. The "⋯" menu (portal at end of `<body>`) and the drawer's focus trap — the menu closing returns focus to "⋯", the drawer opening moves focus into it: order.
- R5. Ripple: `src/test/setup.ts` (matchMedia stub, reset of any new store) is a test helper — RED work; existing tests whose markup the shell change breaks are RED work; `conftest.py` needs a phone context; `index.html` meta; `SignInPage.use_workspace` on a phone context.
- R6. The new-DM / create-channel completions navigate asynchronously after `pick` closes the picker: a drawer closed early, or left open on failure.

## Coverage

| Issue item or expectation | Plan | Outcome |
|---|---|---|
| Req 1 — narrow is below 768px | Decision 7; `useNarrow` 767/768; `ChannelView.narrow` 767/768 | covered |
| Req 2 — drawer closed by default, ☰ on every shell screen | it.each over channel, DM, `/search`, `/settings` | covered |
| Req 2 — closes on close button, backdrop, Escape, each navigation | one test per close path, both `SearchBox` branches, Decision 12 | covered |
| Req 2 — "nothing else closes it" | typing / new-DM list / blank search / refused create rows | covered |
| Req 3 — modal: backdrop, focus in and held, back to ☰ | Decision 14, `inert`, Tab-wrap row, focus asserted per close | covered |
| Req 4 — narrow `/` opens on arrival **and can be closed** | "opens on a narrow /"; no test closes it on `/` | **missing** — finding 2 |
| Req 4 — a link straight elsewhere opens closed | it.each | covered |
| Req 5 — panels cover, back control, scroll kept, Back closes thread only | `ChannelView.narrow` rows + journey | covered |
| Req 5 "close only with their own controls" vs Decision 17 (member panel also resets on channel switch / thread open) | Decision 17, **assumed**, reasoned | settled (Left for later) |
| Req 6 — 360px, no sideways scroll, every control usable | Task 7 by reading; journey at 390 on a channel; acceptance check 4; Task 9 hand run | **partly missing** — finding 3 |
| Req 6 — images and chips fit | Task 7 | covered (acceptance) |
| Req 6 — composer above keyboard | Decision 21, human | settled |
| Req 7 — thread kept, draft kept, scroll kept, drawer closed on wide, member default | crossing table | covered, except the combined path — finding 1 |
| Rules meet: drawer & "⋯" | "opening it closes an open menu"; backdrop row | covered |
| Rules meet: drawer & navigation (new DM) | Decision 13 assumed, deferred-POST row | settled |
| Rules meet: narrow thread, Back | two `ChannelView.narrow` rows, journey | covered |
| Rules meet: search & drawer | two search rows, result row | covered |
| Rules meet: member panel across breakpoint | two crossing rows | covered |
| Paths: "Rotate with a thread open and a draft" vs acceptance check 3 vs Decision 19 (panel covers composer) | no row names it; no test holds both | **missing** — finding 1 |
| Decided already 1–6 | Decisions 1–6; D20 untouched | covered |
| Tests: Vitest list; one phone BDD journey; desktop journeys pass | Tasks 1–3, Task 9 e2e whole layer | covered |
| Record: doc 06 section, D48 🟢 leaving D20 open | Task 8 (+ ADR, vocabulary §36, D47 pointer) | covered |
| Not in this issue | *Not in this plan* | covered |
| E1 narrow source | Decision 7 | settled |
| E2 one aside, testids/`connection-status` in DOM | Decisions 8, 11 (`hidden`, same node) | settled |
| E3 per-control closing; no-navigation branches | Decision 12 | settled |
| E4 "on arrival" | Decision 16, assumed | settled |
| E5 how a panel covers | Decision 9 | settled |
| E6 member state, narrow-only button, none on DM | Decision 17, Task 2 table | settled |
| E7 back controls, history | Decision 18 | settled |
| E8 keyboard | Decision 21 | settled |
| E9 focus trap mechanism | Decision 14 (hand-rolled, user-event behaviour checked) | settled |
| E10 D48 wording | Decision 22, Task 8 | settled |
| C1 wide stays today's | `onToggleMembers` only when narrow; "wide /" row | settled |
| C2 Escape vs "⋯" | drawer closes the menu on open; Escape on the aside | settled |
| C4 no history for drawer/members | `location().key` row | settled |
| T6 default `matchMedia` stub | Task 1, `setup.ts` at 1024 | settled |
| T8 360px test | *What no test covers* | settled, but see finding 3 |
| R1 read state while covered | Decision 20, assumed | settled (Left for later) |
| R2 ghost click | backdrop is a `<button>` closing on click | settled |
| R3 focus lost on crossing / panel close | not addressed | minor — finding 6 |
| R5 ripple | setup.ts RED, step move RED, conftest | settled; one gap — finding 4 |
| R6 async DM/create | Decisions 12, 13 | settled |

## Findings

### 1. "Rotate with a thread open and a draft" meets Decision 19 with no row and no test — major
**Where:** Decision 19; crossing table (`App.narrow`) · **Checked:** issue *Paths* row 6 and
*Acceptance* 3; plan Decision 19 and the crossing rows.
Decision 19 has the covering panel cover the list **and the composer**, and the column is `inert`
(Task 2 table). At 390 with a thread open, the channel composer can't be typed in — so the issue's
acceptance check 3 ("Ada opens a thread and types a draft in the channel composer, then … 844×390
and back") can't be performed as written, and *Paths* "Rotate with a thread open and a draft"
names a draft the plan doesn't place: the channel composer's (typed before opening, or at the
wide end) or the thread composer's (the only one usable at 390). No decision row names this
pair. In the tests, "the composer's draft and its node survive both crossings" opens no thread,
and "a thread stays open" types no draft — nothing crosses the breakpoint with both, and the
thread composer's draft never crosses at all.
**Settles it:** a decision row naming the conflict between Decision 19 and acceptance check 3,
saying which draft the path means and how check 3 is performed (for the acceptance-reviewer);
and the draft crossing test held with a thread open, asserting the draft(s) the row names
survive 1024 → 390 → 1024 (and/or 390 → 1024 → 390).

### 2. Req 4's "and can be closed" has no test — major
**Where:** `App.narrow` drawer table; Task 5 "Arrival" · **Checked:** issue Req 4; every row of the
table.
The close rows (button, backdrop, Escape) all run on a channel; on `/` the only exit tested is
picking a channel, which navigates away. The arrival rule is an effect, and a build whose effect
reopens the drawer whenever it is closed on `/` (depending on `drawerOpen`, or on a re-render)
passes every row while breaking "can be closed". **Settles it:** a row on a narrow `/`: close it
(e.g. Close sidebar or Escape), then something that re-renders the shell (the channel list
refetching, a width change that stays narrow) — still no dialog, ☰ focused.

### 3. 360px for sign-in, Settings and the composer rests on a step no stage performs — major
**Where:** *What no test covers*; Task 7 bullet 3; Task 9 "First real run" · **Checked:**
`.claude/agents/code-writer.md:141` ("A first real run by hand … list each in the report as left
for the human"); issue *Acceptance* 4.
Task 7 fixes what reading the classes found and defers "the composer row, the Settings page and
the sign-in page at 360" to Task 9's hand run in a browser's device mode, which the code-writer
doesn't do — so those fixes never happen before acceptance. The journey's sideways check runs at
390 on one channel, not at 360. *What no test covers* says acceptance check 4 covers "every screen
at 360", but check 4 has no sign-in, which Req 6 lists. **Settles it:** something that actually
runs at 360 — e.g. the journey's sideways step resized to 360×740 (`set_viewport_size`, as the
issue suggests) over the screens it already visits — and *What no test covers* correcting its
claim and naming sign-in (and anything else unchecked at 360) for the acceptance-reviewer and the
human.

### 4. The journey's expected red names the wrong step, and the phone sign-in leans on Decision 16 unsaid — minor
**Where:** Task 3 *Expected red*; fixtures · **Checked:** `chat_page.py:279-292`,
`sign_in_page.py:30-64`, `steps/conftest.py:37-46`.
Task 3 makes `create_channel` call `_ensure_drawer_open()` first; on today's build there is no
`sidebar` testid, so it presses `drawer-open` and times out at `Given Ada has created a public
channel named "general"`, before `When Ada opens…`. Separately, `ada_phone_context` signs in
through `SignInPage.sign_in`, which waits for `workspace-name` **visible**, then
`use_workspace` clicks a `workspace-option` — on a phone both hold only because Decision 16 opens
the drawer when the callback lands on `/`. Say so (and that `sign_in_page.py` needs no change), so
a later change to Decision 16 doesn't break every phone fixture silently.

### 5. The journey's last `Then` is local — minor
**Where:** Task 3 Gherkin · **Checked:** the shared context's *The journey proves the server*.
The server is proven mid-scenario (Grace's reaction and reply counts); the final two `Then`s are
the SPA's own scroll and layout, which is the point of the journey. Fine — but say it under
*What no test covers* (or the feature's narrative) so the test-reviewer doesn't raise it.

### 6. Focus on two narrow-only paths is unspecified — minor
**Where:** Tasks 5, 6 · **Checked:** Decision 14; `ThreadPanel.tsx:144-152`.
Crossing wide → narrow with focus in the sidebar hides the `<aside>` and drops focus to `<body>`;
pressing **Back to channel** unmounts the covering panel (thread or members) with focus on it, to
`<body>`. The issue doesn't require either; one line each (where focus goes, or "not handled")
would stop the code pair guessing.

### 7. Task 9's conventions command won't run as written — minor
**Where:** Task 9 bullet 2 · **Checked:** shared context (a `$` makes a command refused);
`code-writer.md:137-140`.
`$(git diff --name-only HEAD)` is refused and misses new files; the code-writer's own file says to
pass each changed file by name from `git status --short`. Inherited from the exemplar — worth
matching the agent file.

## Left for later stages

- **Decision 20 (assumed):** a channel covered by a full-screen thread or the member panel still
  counts as being read when its list is at the bottom. Defensible and recorded; the human should
  know a phone reader "reads" a channel they can't see.
- **Decision 17 (assumed):** the member panel also closes on a channel switch and on a thread
  opening, against Req 5's "close only with their own controls" read literally. Recorded with its
  reason; accepted.
- **Decision 16 (assumed):** the drawer opens on every arrival at `/` while narrow, not only the
  first load.
- **Decision 13 (assumed):** a new DM closes the drawer on success, not at the pick.
- `AttachmentList.tsx`'s file chip `truncate` is at `:166`, not `:164` — cosmetic.

## Checked and sound

- Base commit `380693a` is the parent of the plan-writer's commit `ab7e8b2` (`git log`); gh-8 is in.
- Corrections to the issue: `TOUCH_TABLET`/`ada_touch_context` at `conftest.py:262, :349-360` and
  `ThreadPanel` `w-80 shrink-0` at `:142` — both confirmed.
- Library claims, in the primary checkout's `node_modules`: jsdom `Window.js` has no `matchMedia`;
  Tailwind preflight `[hidden]` at `:396`; user-event `dispatchEvent.js:22-41` skips the default
  when keydown is prevented; react-router `chunk-KS7C4IRE.mjs:6329-6340` renders `RenderedRoute`
  unkeyed; `@testing-library/dom` treats `element.hidden` as inaccessible (`role-helpers.js:34`).
- `session.changeWorkspace` neither navigates nor sets `loading`, so the shell isn't remounted and
  only a per-control close catches it (Decision 12 right).
- `thread-close` reads "Close thread" today and existing tests query that name — kept when wide,
  so no existing test breaks.
- `setup.ts` stub is RED (Task 1), every RED task precedes GREEN with the test-reviewer gate,
  *Found while building* empty, no task commits, nothing built on a 🔴 (D20 untouched), record task
  present, verification names `lint unit` and `e2e` only, 469 lines.
- Expected reds: `Failed to resolve import "./useNarrow"` is right for a file whose every test
  needs it; the `App.narrow`/`ChannelView.narrow` reds are role-query failures of a running test;
  the one green-at-red row ("wide /") is declared and answered.
- Guards prove their positive (blank search, refused create, typing/new-DM list anchored to the
  typed value and `aria-expanded`); the scroll journey guards its own arrangement (`_left_at`
  between 100 and max−100).
- Moved step `Grace has sent "…" in "…"` (`parsers.re`, needs a quote) can't collide with the new
  `Grace has sent {count:d} messages in "…"`.
- No API, env var, ingress, migration or BDD truncation change applies.
