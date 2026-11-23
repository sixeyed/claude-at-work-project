# CollabHub on a phone: a drawer, full-screen panels, and 360px

## Summary

CollabHub works on a phone. Below 768px the sidebar becomes a drawer, opened by a ☰ on every screen; the member and thread panels take the whole screen; and every screen works at 360px wide with no sideways scrolling. Rotating or resizing across 768px loses nothing.

**Depends on #8 (gh-8)**, the "⋯" message menu, which makes every message action reachable on touch. Build this on top of it.

## Services touched

**The SPA only.** Read `docs/design/06-frontend-spa.md` — no section covers layout below 768px; this issue adds one — its *Threads* section (:336-341, the thread panel "in the channel's right column in place of the member panel") and §9 (:496-503, `/settings` "inside the chat shell, reached from your name in the sidebar").

## What exists already

- **No responsive layout at all.** No `sm:`/`md:`/`lg:` class, `@media` rule or `matchMedia` anywhere in `src/frontend/src`. The viewport meta is `width=device-width, initial-scale=1.0` (`index.html:5`).
- **The shell:** `ChatLayout.tsx:80`, `grid h-full grid-cols-[16rem_1fr]` — a 256px `<aside>` (:81-126) and `<main>` (:128). The aside holds, in order: `SearchBox`; `WorkspaceSwitcher` (the workspace name, your display name linking to `/settings` as `current-user`, and the switcher list when you have more than one workspace); a `<nav>` with `ChannelList` and `DirectMessageList`; and a footer with `CreateChannelDialog`, Sign out and the connection status. No drawer, no toggle.
- **Nothing is a modal.** `CreateChannelDialog` is an always-visible inline form (`create-channel-form`); new DM is an inline disclosure (`dm-new`, `aria-expanded`, `dm-pick` options); the workspace switcher is an inline list. All of them live in the sidebar.
- **Routes in the shell** (`App.tsx:158-194`): `/` (`NoChannelSelected`), `/c/:channelId` (`ChannelView`, channels and DMs), `/search` (`SearchPage`, reached from `SearchBox`; a result links to `/c/:id?message=`), `/settings` (`SettingsPage`, with a back link to the last channel). `/sign-in` and `/auth/callback` are outside it.
- **The right column:** `ChannelView.tsx:93-146` puts `ThreadPanel` (`w-80 shrink-0`, `ThreadPanel.tsx:139`) or, with no thread open and not a DM (:142), `MemberPanel` (`w-64 shrink-0`, `MemberPanel.tsx:46`) beside the message column (`flex min-w-0 flex-1`, :94). On a wide screen the member panel always shows when no thread is open. At 390px the message column is squeezed to nothing.
- **The open thread is in the URL** (`useThreadParam`): opening pushes `?thread=`, closing replaces it, so the browser's Back already closes a thread. The member panel and anything else are not in the URL.
- **Tests:** Vitest's jsdom evaluates no media query (`src/test/layout.ts` stubs only scroll geometry; there is no `matchMedia` stub in `src/test/setup.ts`). Every Playwright context is `browser.new_context()` with defaults (`tests/bdd/conftest.py:259, :342`): desktop, no touch.

## Requirements

1. **Narrow is below 768px.** Every rule below about "narrow" means a viewport under 768px wide; at 768px and over, the layout is today's.
2. **The drawer.** When narrow, the sidebar is a drawer, closed by default, opened by a ☰ button present on every screen in the chat shell — `/`, a channel, a DM, `/search` and `/settings`. It closes on its close button, on a tap on its backdrop, on Escape, and on **any navigation** made from it: picking a channel or DM, starting a new DM, submitting a search, following your name to `/settings`, switching workspace, creating a channel. Nothing else inside it closes it — typing in the create-channel form or opening the new-DM list leaves it open.
3. **The drawer is a modal.** While open it has a backdrop, focus moves into it and stays in it, and closing it returns focus to ☰.
4. **First load.** On a narrow `/`, with no channel open, the drawer opens on arrival and can be closed. A link straight to any other screen opens with the drawer closed.
5. **Panels take the screen.** When narrow, the thread panel and the member panel each cover the message view, with a back control that returns to it. Closing a thread returns to the channel at the scroll position it left. The browser's Back closes a thread, as it does today; the member panel and the drawer close only with their own controls.
6. **360px works.** At 360px wide, no screen scrolls sideways — the page's scroll width equals its width — and every control can be reached and used: sign-in, a channel and its composer, a thread, a DM, search and its results, `/settings`, and the drawer with the create-channel form and the new-DM list open. Inline images and attachment chips fit the width. The composer stays above the on-screen keyboard.
7. **Crossing the breakpoint** — a rotation or a resize — loses nothing: an open thread stays open (side panel ⇄ full screen), the composer's draft and the scroll position are kept, and the drawer is closed whenever the width is 768px or more. The member panel takes its default for the new width: shown when wide with no thread open, closed when narrow.

## Where the rules meet

- **The drawer and the "⋯" menu (Req 2, Req 3):** opening the drawer closes any open "⋯" menu; a tap on the drawer's backdrop closes the drawer and nothing else.
- **The drawer and navigation (Req 2, Req 4):** picking a DM from the new-DM list navigates, so it closes the drawer, as picking a channel does.
- **A thread opened from a narrow channel (Req 5, Req 7):** closing it, with its back control or the browser's Back, returns to the channel at the scroll position it left.
- **Search and the drawer (Req 2, Req 6):** a search submitted from the drawer closes it and shows `/search`; picking a result opens the channel at that message, drawer still closed.
- **The member panel across the breakpoint (Req 5, Req 7):** narrow to wide shows it as today; wide to narrow shows the message view, unless a thread is open, which keeps covering the screen.

## Paths each rule holds on

| Path | What must be true |
|---|---|
| First load of `/` on a phone | the drawer shows the channels; picking one closes it and the channel fills the screen |
| A link straight to a channel, on a phone | the channel fills the screen, drawer closed, ☰ in its header |
| `/search` or `/settings` on a phone | ☰ is there; the screen does not scroll sideways |
| Open a DM from the drawer | the DM fills the screen; ☰ is there to go back |
| A thread, then Back | the channel, at the scroll position it left |
| Rotate with a thread open and a draft | the thread stays open, in its new form; the draft is kept |
| Composer focused, keyboard up | the composer is visible above the keyboard |

## What this assumes — check before building on it

- **`100dvh`, or `interactive-widget=resizes-content` in the viewport meta, keeps the composer above the on-screen keyboard** on current iOS Safari and Android Chrome. This is the rule most likely to need another mechanism, and only a real device proves it.
- **jsdom evaluates no media query.** "Narrow" must come from something a Vitest test can set — one hook over `matchMedia`, say, stubbed in tests — and the layout must read it from there, not only from CSS classes.
- **Playwright's emulation** (`has_touch`, `is_mobile`, a 390×844 viewport) is enough for the BDD journey and the acceptance pack to tap ☰, the drawer and "⋯". `set_viewport_size` stands in for a rotation.

## Timing

n/a — there is no throttle, window or race. The drawer and panels open and close on events; crossing the breakpoint is a re-render that keeps its state.

## Decided already

1. The breakpoint is 768px (Tailwind `md`).
2. ☰ is on every screen in the shell, and any navigation from the drawer closes it.
3. The drawer is a modal while open.
4. Back keeps today's behaviour: it closes a thread, and nothing else is added to history.
5. Responsive web only. **D20 stays 🔴 and untouched**: no PWA manifest, no service worker, no native app.
6. Light palette only, as D26 and D28 have it.

Left to the plan, on purpose: how "narrow" is computed, the drawer's animation, the back control's look, and where the member panel's button sits in the header.

## Tests

- **Vitest:** the drawer under a stubbed narrow flag — closed by default, open on `/`, each way it closes and each way it doesn't, focus in and back; the panels covering the view and their back controls; crossing the breakpoint keeps the thread and the draft and resets the member panel.
- **One BDD journey on a phone context:** Ada, on a 390×844 context with touch, opens the drawer, picks #general, reacts to Grace's message through "⋯", replies in its thread and goes Back to the channel.
- Every existing journey must still pass on its desktop context.

## Record in this slice

- Doc 06: a new section on layout below 768px — the drawer, the full-screen panels, the breakpoint.
- Register: a new entry **D48 🟢** — a responsive web layout below 768px — noting that it leaves D20 open.

## Not in this issue

- A PWA, a service worker, offline, a native app (D20).
- Swipe gestures, pull to refresh, haptics.
- Back closing the drawer or the member panel.
- Dark mode or any new per-user setting (D28).
- A layout for large tablets beyond what 768px and over already is.

## Acceptance — on the branch's preview

Ada on a **390×844 context with touch**, Grace on a desktop, unless a check says otherwise. Each check fails on `main`, which has no drawer and scrolls sideways at this width. The drawer opens on `/` for every user, so no check needs a fresh one:

1. Ada loads `/`: the drawer shows the channels. She picks #general: the drawer closes and the channel fills the screen.
2. Grace posts; Ada opens its thread from "⋯": it covers the screen. She replies, then goes Back: the channel is at the scroll position she left.
3. Ada opens a thread and types a draft in the channel composer, then the viewport is resized to 844×390 and back to 390×844: the thread is still open and the draft is still there.
4. At 360×740, none of these scrolls sideways: a channel, a thread, a DM, `/search` with results, `/settings`, and the drawer with the create-channel form and the new-DM list open.
5. Ada searches from the drawer and picks a result: the channel opens at that message with the drawer closed.

**For the human, on a real phone** — these can't be emulated: the composer stays above the on-screen keyboard; rotating the phone with a thread open keeps it open; attaching a photo from the camera roll sends it.

## References

- `src/frontend/src/features/channels/ChatLayout.tsx`, `ChannelView.tsx`, `MemberPanel.tsx`, `CreateChannelDialog.tsx`, `DirectMessageList.tsx`, `WorkspaceSwitcher.tsx`
- `src/frontend/src/features/threads/ThreadPanel.tsx`, `useThreadParam.ts`
- `src/frontend/src/features/search/SearchBox.tsx`, `SearchPage.tsx`; `src/frontend/src/features/settings/SettingsPage.tsx`; `src/frontend/src/App.tsx`
- `tests/bdd/conftest.py`
- `docs/design/06-frontend-spa.md`; register D20, D26, D28
- `docs/issues/008.md` — the issue this was split from
