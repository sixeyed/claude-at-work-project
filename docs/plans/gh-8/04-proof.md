# gh-8 — acceptance proof: accepted

## Summary
- Every message that allows an action now shows an always-visible "⋯" ("Message actions") button, in the channel and in the thread panel. The hover-revealed row is gone.
- The button opens one menu of what that message allows: React, Reply in thread, Edit, Delete. A reply in the thread panel gets no "Reply in thread".
- On a 1024×768 touch context Ada taps "⋯" and reacts, and Grace sees the reaction live without reloading. Editing through the menu returns focus to that message's "⋯".
- Escape and a tap outside close the menu and the emoji row, and no reaction is added. Keyboard-only works on desktop: Tab, Enter, then Escape, with focus back on "⋯".
- The menu stays whole inside the viewport on the last message of a 30-message channel, and on a reply at the thread panel's right edge.

## Try it
- On GitHub, the PR's own preview: its origin is in the preview comment on the PR, and it stays up until the PR is approved or closed. Sign in as ada@collabhub.dev (grace@collabhub.dev too) with the preview password, which goes to the delivery's Slack thread — `collabhub` where Slack isn't set up
- Locally: `BRANCH=feature/gh-8 scripts/deploy.sh preview up`, then `preview url`; `preview down` when you're done

## Acceptance criteria
Criteria are the issue's six *Acceptance* checks. Each fails on `main`, which has no "Message actions" button, so each test fails at its first step there. The page object `_open_actions` waits for that button.

| # | Criterion | Proven by | Result | Screenshot |
|---|---|---|---|---|
| 1 | Touch: Ada taps "⋯" on Grace's message; React and Reply are offered; she reacts; Grace sees it without reloading | `test_1_touch_tap_offers_react_and_reply_and_grace_sees_the_reaction` | **proven**, with one wording difference (see *For the human* 1): the menu also offers Delete, because Ada is an admin | [menu](../../../build/acceptance/feature/screenshots/test-1-touch-tap-offers-react-and-reply-and-grace-sees-the-reaction-chromium-ada-menu-on-graces-message.png) · [Grace](../../../build/acceptance/feature/screenshots/test-1-touch-tap-offers-react-and-reply-and-grace-sees-the-reaction-chromium-grace-sees-reaction.png) |
| 2 | Own message: React, Reply, Edit, Delete; edit through the menu; focus on that "⋯" after saving | `test_2_own_message_offers_four_and_edit_returns_focus_to_the_button` | **proven** | [menu](../../../build/acceptance/feature/screenshots/test-2-own-message-offers-four-and-edit-returns-focus-to-the-button-chromium-own-message-menu.png) · [after edit](../../../build/acceptance/feature/screenshots/test-2-own-message-offers-four-and-edit-returns-focus-to-the-button-chromium-after-edit-focus-on-button.png) |
| 3 | Desktop, keyboard only: Tab to "⋯", Enter, reach Reply, open thread; another "⋯", Escape, focus on it | `test_3_keyboard_only_on_desktop` | **proven** (the second "⋯" is focused with `.focus()`, not Tabbed to) | [Escape, focus ring on "⋯"](../../../build/acceptance/feature/screenshots/test-3-keyboard-only-on-desktop-chromium-escape-focus-on-button.png) |
| 4 | Emoji row closes on Escape and on an outside tap, with no reaction added; then an emoji tap still reacts | `test_4_escape_and_outside_tap_close_the_emoji_row_without_reacting` | **proven** | [row open](../../../build/acceptance/feature/screenshots/test-4-escape-and-outside-tap-close-the-emoji-row-without-reacting-chromium-emoji-row-open.png) · [closed, no reaction](../../../build/acceptance/feature/screenshots/test-4-escape-and-outside-tap-close-the-emoji-row-without-reacting-chromium-closed-by-outside-tap-no-reaction.png) |
| 5 | In a thread, "⋯" on a reply offers no Reply in thread (the root in the channel does) | `test_5_a_reply_in_the_thread_offers_no_reply_in_thread` | **proven** | [menu](../../../build/acceptance/feature/screenshots/test-5-a-reply-in-the-thread-offers-no-reply-in-thread-chromium-reply-menu-in-thread.png) |
| 6 | Scrolling channel: "⋯" on the last message opens in full inside the viewport | `test_6_menu_on_the_last_message_of_a_scrolling_channel_is_fully_visible` | **proven** | [menu](../../../build/acceptance/feature/screenshots/test-6-menu-on-the-last-message-of-a-scrolling-channel-is-fully-visible-chromium-last-message-menu.png) |
| 6b | Beyond the issue, as the plan asked: a reply's menu and emoji row at the thread panel's right edge are whole | `test_6b_menu_on_a_reply_at_the_thread_panels_right_edge_is_fully_visible` | **proven** | [emoji row](../../../build/acceptance/feature/screenshots/test-6b-menu-on-a-reply-at-the-thread-panels-right-edge-is-fully-visible-chromium-panel-edge-emoji-row.png) |

All six are visible criteria; none is internal. The pack's discriminating check is its first step in each test. On `main` there is no `message-actions` button, so every test times out there. Test 4's positive half taps an emoji after the closes, so "no reaction" cannot be the result of a row that never works. Test 6 first asserts that the list scrolls (`scrollHeight > clientHeight + 100`) and that the menu's box lies within the viewport.

## Preview
- Branch `feature/gh-8`, commit `d78daf5` (worktree clean at the pass), namespace `preview-feature-gh-8`.
- Deploy outcome: `collabhub-deps` and `collabhub` installed, status deployed. Log: `build/acceptance/preview-up.log`.
- Origin: `https://vid-duty-whilst-telling.trycloudflare.com` (a tunnel, gone by the time you read this). Object-store origin: a second tunnel.

## Standard smoke pack
Passed, 6 of 6 (run alone, and again beside the feature pack): the app loads, signing keys published, the internal API isn't routed, Ada signs in, a message survives a reload, an image round-trips.

## Feature smoke pack
`build/acceptance/smoke/test_gh_8.py`, 7 tests, all passed on the second run. The first run failed test 1 on my own over-strict assertion, a test error and not a feature fault (see *For the human* 1). Ada's context is 1024×768 with touch for tests 1, 2, 4, 5, 6 and 6b. Test 3 uses the standard desktop context (1280×800). Grace is a second signed-in context at 1280×800. Each test creates its own `<run_id>-cN` channel.

## Screenshots
**1. Ada's tap on Grace's message: the menu (React, Reply in thread, Delete) opens below "⋯", whole.**
![Ada's menu on Grace's message](../../../build/acceptance/feature/screenshots/test-1-touch-tap-offers-react-and-reply-and-grace-sees-the-reaction-chromium-ada-menu-on-graces-message.png)

**1. Grace's window, never reloaded, shows the 🎉 1 chip on her message.**
![Grace sees the reaction](../../../build/acceptance/feature/screenshots/test-1-touch-tap-offers-react-and-reply-and-grace-sees-the-reaction-chromium-grace-sees-reaction.png)

**2. Ada's own message: the menu offers React, Reply in thread, Edit, Delete.**
![Own message menu](../../../build/acceptance/feature/screenshots/test-2-own-message-offers-four-and-edit-returns-focus-to-the-button-chromium-own-message-menu.png)

**2. After the edit is saved: "(edited)" shows, no menu is open, and focus has returned to that message's "⋯" (asserted in the test; the focus ring is faint on touch).**
![After edit](../../../build/acceptance/feature/screenshots/test-2-own-message-offers-four-and-edit-returns-focus-to-the-button-chromium-after-edit-focus-on-button.png)

**3. Keyboard only: after Escape the menu is closed and the second message's "⋯" has the focus ring. The thread panel opened earlier by keyboard is on the right.**
![Escape returns focus](../../../build/acceptance/feature/screenshots/test-3-keyboard-only-on-desktop-chromium-escape-focus-on-button.png)

**4. The emoji row open beside "⋯", all six options in view.**
![Emoji row open](../../../build/acceptance/feature/screenshots/test-4-escape-and-outside-tap-close-the-emoji-row-without-reacting-chromium-emoji-row-open.png)

**4. After a tap outside: the row is closed and the message has no reaction chip.**
![Closed, no reaction](../../../build/acceptance/feature/screenshots/test-4-escape-and-outside-tap-close-the-emoji-row-without-reacting-chromium-closed-by-outside-tap-no-reaction.png)

**5. In the thread panel, the reply's menu: React, Edit, Delete, with no "Reply in thread".**
![Reply menu in thread](../../../build/acceptance/feature/screenshots/test-5-a-reply-in-the-thread-offers-no-reply-in-thread-chromium-reply-menu-in-thread.png)

**6. The last of 30 messages: the menu opens above its "⋯" because there is no room below, shown in full.**
![Last message menu](../../../build/acceptance/feature/screenshots/test-6-menu-on-the-last-message-of-a-scrolling-channel-is-fully-visible-chromium-last-message-menu.png)

**6b. At the thread panel's right edge: the emoji row of a reply, held inside the viewport.**
![Panel edge emoji row](../../../build/acceptance/feature/screenshots/test-6b-menu-on-a-reply-at-the-thread-panels-right-edge-is-fully-visible-chromium-panel-edge-emoji-row.png)

## For the human
1. **Issue check 1 says Ada sees "React and Reply only" on Grace's message; the menu also shows Delete.** Ada is a channel admin here (the member panel says "ada admin"), and the existing rule lets an admin delete others' messages. The branch keeps that rule from `main` (the plan's `offeredActions`, and *Requirements* 1 "under the existing `can*` rules"). So the issue's own table row "Someone else's message → React and Reply only" holds for a plain member, not for an admin. I judged it a wording gap in the issue and not a failure. My test asserts React and Reply come first and there is no Edit. A plain member's menu is unit-tested in `actionRules.test.ts` ("someone else's message offers react and reply only").
2. **Never exercised on a real browser until now (the code-writer's and code-reviewer's "first real run").** This pass did the by-hand checks they listed that a pack can: the last message of a scrolled channel (menu opens above, whole), and a reply at the panel's edge (whole). **Still not done:** a touch that *starts a scroll* with a menu open, and the desktop wheel-scroll of "⋯" out of the list with the menu open (#16; the plan expects the menu to stay, clamped, with no "⋯" beside it). Also unchecked: whether `tabIndex={-1}` on the list scroller and the thread panel shows a focus ring on a mouse press (code-reviewer-2).
3. **Assumed decisions** (plan, all recorded as assumed): #10 keyboard model (Tab cycles within the menu), #13 focus fallback is the list scroller or the thread panel, #14 a changed set of actions closes the menu, #15 a mouse press on nothing focusable leaves focus on the body, #16 scroll re-places and never closes the menu, #17 "⋯" stays while editing. Green report: no departures from the plan.
4. **Open from the test and code reviews (*Unpinned*, no test holds them):** M1 emoji mode reset on reopen; M3 document listeners attached only while open; M4 an actions change closes the menu only when it is open; M5 re-placement on the swap to the emoji row; listener removal with the same capture flag; the horizontal clamp with an empty range has no test. Probes showed the code right on each (code-reviewer-1 and -2). Test-reviewer-1: the unmount "focus elsewhere" half cannot fail, and is not relied on.
5. **The integration layer shows ⚪ not run in `docs/test-report.md`.** This branch touches no Python or SQL. Rerun it before relying on the report (code-reviewer-2).
6. **A record inconsistency, minor:** the round-2 green report says it did not rerun lint, and the code-reviewer let that go because only Markdown changed. Consistent with the tree.
7. **Test-3 scope:** I Tab to the first "⋯" and open the thread by keyboard, but focus the second "⋯" directly before Enter and Escape. The issue's line allows "she opens another ⋯".

## The run
- 01 plan-writer done (opus, 84 turns)
- 02 plan-reviewer changes_requested (2 major, 3 minor: focus after an outside tap, same-actions rerender)
- 03 plan-writer done (both majors fixed)
- 04 plan-reviewer approved
- 05 test-writer done (28 failing Vitest tests, 3 load errors as planned, 26 BDD scenarios collected)
- 06 test-reviewer approved (2 minor)
- 07 code-writer done (Vitest 620/620, e2e 26/26)
- 08 code-reviewer changes_requested (1 major: doc 06 overclaimed focus; 4 surviving mutants, not code bugs)
- 09 code-writer done (doc-only fix)
- 10 code-reviewer approved
- 11 acceptance-reviewer: this proof
