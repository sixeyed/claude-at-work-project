# gh-9 — acceptance proof: accepted

## Summary
- Below 768px the sidebar is a modal drawer behind ☰. On a 390×844 touch phone, loading `/` opens it with the channel list, and picking a channel closes it so the channel fills the screen.
- A thread opened from "⋯" covers the whole message view with a **Back to channel** control. Going Back returns the channel at the scroll position Ada left.
- Crossing the breakpoint (390 → 844×390 → 390) keeps the thread open, in its side-panel form at 844 and full-screen at 390. It also keeps the reply draft in the thread and the channel draft behind it.
- At 360×740 no screen scrolls sideways: channel, thread, drawer with the create form filled and the new-DM list open, DM, search results, Settings and sign-in.
- Searching from the drawer closes it and shows the results. Picking a result opens the channel at that message with the drawer still closed.

## Try it
- On GitHub, the PR's own preview: its origin is in the preview comment on the PR, and it stays up until the PR is approved or closed. Sign in as ada@collabhub.dev (grace@collabhub.dev too) with the preview password, which goes to the delivery's Slack thread — `collabhub` where Slack isn't set up. Use a phone-sized window (or the browser's device mode at 390×844).
- Locally: `BRANCH=feature/gh-9 scripts/deploy.sh preview up`, then `preview url`; `preview down` when you're done.

## Acceptance criteria
All criteria are visible. Every test would fail on `main`, which has no `sidebar`/☰ and no covering thread. Screenshot links are in the table; the images are under *Screenshots*.

| # | Criterion | Proven by | Result | Screenshot |
|---|---|---|---|---|
| 1 | Ada loads `/` at 390: the drawer shows the channels; she picks a channel: drawer closes, channel fills the screen | `test_1_drawer_on_slash_then_pick_channel` — fails on `main` (no `sidebar`, no `drawer-open`) | proven | [drawer](../../../build/acceptance/feature/screenshots/test-1-drawer-on-slash-then-pick-channel-chromium-drawer-open-on-arrival.png), [channel](../../../build/acceptance/feature/screenshots/test-1-drawer-on-slash-then-pick-channel-chromium-channel-fills-screen.png) |
| 2 | Grace posts; Ada opens its thread from "⋯": it covers the screen. She replies, goes Back: the channel is at the scroll position she left | `test_2_thread_covers_and_back_returns_where_left` — measures the panel at the full 390 width; `is_where_left` first checks the position is neither top nor bottom of the list | proven | [thread](../../../build/acceptance/feature/screenshots/test-2-thread-covers-and-back-returns-where-left-chromium-thread-covers-screen.png), [back](../../../build/acceptance/feature/screenshots/test-2-thread-covers-and-back-returns-where-left-chromium-back-at-same-scroll-position.png) |
| 3 | A thread and drafts survive 390 → 844×390 → 390 | `test_3_thread_and_drafts_survive_resize` — in Decision 23's order: channel draft, then the thread and a reply draft. It asserts the panel is full-width at 390, a ~320px side panel at 844 and full-width again; then Back to channel shows the channel draft | proven (the draft surviving alone would pass on `main`; the full-screen/side-panel width assertions are what the change decides) | [landscape](../../../build/acceptance/feature/screenshots/test-3-thread-and-drafts-survive-resize-chromium-landscape-thread-side-panel.png), [portrait again](../../../build/acceptance/feature/screenshots/test-3-thread-and-drafts-survive-resize-chromium-back-to-portrait-thread-open.png), [draft kept](../../../build/acceptance/feature/screenshots/test-3-thread-and-drafts-survive-resize-chromium-channel-draft-kept.png) |
| 4 | At 360×740 nothing scrolls sideways: channel, thread, DM, `/search` with results, `/settings`, the drawer with the create form and new-DM list open — and sign-in (the plan's addition) | `test_4_nothing_scrolls_sideways_at_360` — document and every `overflow-x: auto/scroll` element, per screen | proven | [drawer](../../../build/acceptance/feature/screenshots/test-4-nothing-scrolls-sideways-at-360-chromium-360-drawer-with-form-and-dm-list.png), [search](../../../build/acceptance/feature/screenshots/test-4-nothing-scrolls-sideways-at-360-chromium-360-search-results.png), [settings](../../../build/acceptance/feature/screenshots/test-4-nothing-scrolls-sideways-at-360-chromium-360-settings.png), [sign-in](../../../build/acceptance/feature/screenshots/test-4-nothing-scrolls-sideways-at-360-chromium-360-sign-in.png) |
| 5 | Ada searches from the drawer and picks a result: the channel opens at that message, drawer closed | `test_5_search_from_drawer_opens_result_with_drawer_closed` | proven | [channel at result](../../../build/acceptance/feature/screenshots/test-5-search-from-drawer-opens-result-with-drawer-closed-chromium-channel-at-result-drawer-closed.png) |

## Preview
- Branch `feature/gh-9`, commit `94a48b4` (no uncommitted changes besides this proof).
- Namespace `preview-feature-gh-9`; deploy outcome: `collabhub-deps` and `collabhub` both installed, "preview is up" (`build/acceptance/preview-up.log`).
- Origin `https://drama-beaver-statutory-juvenile.trycloudflare.com` (the tunnel is gone by the time this is read). The standard pack's checks of the origin passed.

## Standard smoke pack
6 passed, 0 failed, 0 skipped (`build/acceptance/standard`), and again 6 passed beside the feature pack: the app loads without errors, signing keys published, internal API not routed, Ada signs in, a message survives a reload, an image round-trips through object storage.

## Feature smoke pack
`build/acceptance/smoke/test_gh_9.py`, 5 passed. It runs once per preview in the sense that a module fixture creates a `smoke-…-phone` channel (Ada from her phone drawer) and Grace posts 26 messages. Everything is named with `run_id`. Ada is on a 390×844 touch, mobile context; Grace is on a 1280×800 desktop.
1. Loads `/`, expects the dialog **Sidebar** visible with the channel listed, picks the channel, expects ☰ visible and the channel view spanning the screen.
2. Opens the root's thread from "⋯", replies, measures the panel's full width and **Back to channel**, goes Back and checks the scroll position (within 2px).
3. Types a channel draft, opens the thread, types a reply draft, resizes to 844×390 and back, checks the thread and both drafts, and the panel width each time.
4. At 360×740 visits each screen and records sideways scrollers; plus a signed-out 360 sign-in page.
5. Searches from the drawer, expects the drawer hidden with results, picks one and expects the channel with the message on screen, drawer hidden.

Pack-writing notes: my first run of test 3 failed on my own assertion, which read the panel width the instant after the resize, before the re-render. I waited for the width instead. I probed it (the panel was 320px wide, ☰ absent, Back-control name absent at 844, as designed). Test 5's first screenshot showed "Loading messages…", so I added a wait for the message before the shot.

## Screenshots
**1. The drawer open on arrival at `/` (390×844), channels listed, with its Close button.**

![drawer open on arrival](../../../build/acceptance/feature/screenshots/test-1-drawer-on-slash-then-pick-channel-chromium-drawer-open-on-arrival.png)

**1. After picking the channel: drawer closed, ☰ in the top bar, the channel fills the screen.**

![channel fills the screen](../../../build/acceptance/feature/screenshots/test-1-drawer-on-slash-then-pick-channel-chromium-channel-fills-screen.png)

**2. The thread covering the screen, Ada's reply sent, "Back to channel" at the top right.**

![thread covers screen](../../../build/acceptance/feature/screenshots/test-2-thread-covers-and-back-returns-where-left-chromium-thread-covers-screen.png)

**2. After Back: the channel scrolled to the root, "lunch at noon…", where it was left, not the top and not the newest.**

![back at same scroll position](../../../build/acceptance/feature/screenshots/test-2-thread-covers-and-back-returns-where-left-chromium-back-at-same-scroll-position.png)

**3. At 844×390 the thread is a side panel beside the channel; both drafts are there ("channel draft", "reply draft").**

![landscape thread side panel](../../../build/acceptance/feature/screenshots/test-3-thread-and-drafts-survive-resize-chromium-landscape-thread-side-panel.png)

**3. Back at 390×844 the thread covers the screen again with "reply draft" kept.**

![portrait thread open](../../../build/acceptance/feature/screenshots/test-3-thread-and-drafts-survive-resize-chromium-back-to-portrait-thread-open.png)

**3. After Back to channel the composer still holds "channel draft".**

![channel draft kept](../../../build/acceptance/feature/screenshots/test-3-thread-and-drafts-survive-resize-chromium-channel-draft-kept.png)

**4. 360px: the drawer with the long channel name typed and the new-DM list open (grace).**

![360 drawer](../../../build/acceptance/feature/screenshots/test-4-nothing-scrolls-sideways-at-360-chromium-360-drawer-with-form-and-dm-list.png)

**4. 360px: search results.**

![360 search](../../../build/acceptance/feature/screenshots/test-4-nothing-scrolls-sideways-at-360-chromium-360-search-results.png)

**4. 360px: Settings (the profile section was still "Loading…" when it was taken; see For the human).**

![360 settings](../../../build/acceptance/feature/screenshots/test-4-nothing-scrolls-sideways-at-360-chromium-360-settings.png)

**4. 360px: sign-in.**

![360 sign-in](../../../build/acceptance/feature/screenshots/test-4-nothing-scrolls-sideways-at-360-chromium-360-sign-in.png)

**5. The channel opened from a search result, drawer closed, the root message on screen.**

![channel at result](../../../build/acceptance/feature/screenshots/test-5-search-from-drawer-opens-result-with-drawer-closed-chromium-channel-at-result-drawer-closed.png)

## For the human
**Assumed decisions** (plan; all recorded and accepted by the reviews): 13 a new DM closes the drawer once it opens, not at the pick; 15 ☰ sits in a narrow-only top bar in the shell; 16 the drawer opens whenever the pathname becomes `/` while narrow (not on a rotation); 17 the member panel is a **Members** button in the channel header when narrow, and resets on a channel, thread or width change; 19 a covering panel leaves the top bar and channel header visible; 20 read state under a covering panel is unchanged; 23 "rotate with a thread and a draft" means both drafts, check 3 done in the order channel draft → thread → reply draft; 24 **Back to channel** focuses the channel composer, and crossing to narrow with focus in the sidebar moves it to ☰.

**Departures** (green report): the image cap uses a button-level `[&>img]` rule so the existing `max-w-80` test still holds; the member panel and `drawerOpen` are cleared during render while wide, not by an effect; the close button shows "Close" with `aria-label="Close sidebar"`. Red report: a test-only `Link` in `ChannelView.narrow`'s shell; `sideways_tour_at_360` takes two extra keyword arguments.

**Code review, left for the human** (minor): Escape is handled on the drawer only, so on a narrowed desktop window it does nothing once a click has put focus on `<body>`; doc 06 says every close returns focus to ☰ (true for narrow closes; crossing to wide moves none); `ChannelHeader` always renders its controls wrapper, even empty.

**Unpinned by any test** (code review): the top bar's `inert` while the drawer is open; the key handler being inert at wide width; a new DM resolving after a workspace switch not closing the drawer; the covering classes on the thread and member panels (read only as `inert` in Vitest — the thread's covering is shown by this pack and the journey, the **member panel covering is shown by no browser test**); the layout height with the top bar; D24's layout-effect timing in a real browser.

**Found in this pass:**
- The 360 Settings screenshot was taken while the profile fields still read "Loading…", so the sideways check covered Preferences but not the profile field. Both packs (this one and the branch's journey) have the same gap. Settings' fields at 360 want a look by a person.
- "Every control reachable and usable at 360" is checked here only as *no sideways scroll*, as the plan said. I did not exercise the member panel at 360 or an admin's header with **Members**. Ada is an admin in the channels she creates, so her header showed Members, Rename and Archive wrapped on two rows at 390 and fit.
- On a real phone, still unproven: the composer above the on-screen keyboard (`interactive-widget=resizes-content` and `100dvh`), a real rotation with a thread open, and attaching a photo from the camera roll.
- After resizing to 844, the thread panel takes a moment to change its form: a measurement taken in the same instant sees the old width. It settles within a frame or two; not a defect, but a pack author should wait.

## The run
1. `01 plan-writer done [10m 65 turns $3.41 · opus]`
2. `02 plan-reviewer changes_requested [7m 72 turns $3.02 · opus]` — 0 critical, 3 major, 4 minor
3. `03 plan-writer done [2.9m 35 turns $1.29 · opus]`
4. `04 plan-reviewer changes_requested [1.2m 21 turns $0.8 · opus]` — 1 major
5. `05 plan-writer done [0.4m 12 turns $0.49 · opus]`
6. `06 plan-reviewer approved [0.3m 7 turns $0.32 · opus]`
7. `07 test-writer done [8.4m 92 turns $1.79 · sonnet]` — 42 Vitest tests, 41 red as planned, 1 green by design
8. `08 test-reviewer changes_requested [8.9m 134 turns $1.97 · sonnet]` — 1 critical, 1 major, 2 minor
9. `09 test-writer done [2.4m 30 turns $0.37 · sonnet]`
10. `10 test-reviewer approved [1m 13 turns $0.23 · sonnet]`
11. `11 code-writer done [11.1m 105 turns $1.39 · sonnet]` — Vitest 662, e2e 27/27
12. `12 code-reviewer approved [6.2m 62 turns $2.54 · opus]` — no critical or major; 2 minor for the human
13. acceptance-reviewer (this pass): approved — 5/5 visible criteria proven, standard pack 6/6.
