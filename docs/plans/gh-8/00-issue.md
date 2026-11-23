# One "⋯" menu for message actions, at every width

## Summary

Every message's actions — react, reply in thread, edit, delete — move behind one always-visible "⋯" button, at every width. Today they appear only on hover, so on a touch screen nobody can react, reply, edit or delete. The reaction picker also learns to close on Escape and on a tap outside it.

## Services touched

**The SPA only.** Read `docs/design/06-frontend-spa.md` — no section covers message actions, touch or hover yet; this issue adds one — and its *Threads* section (:336-341) for the thread panel's rows.

## What exists already

- **Hover-only actions:** `MessageItem.tsx:135`, a span with `opacity-0 group-hover:opacity-100 focus-within:opacity-100` (the `group` is the `<article>` at :115) holding `ReactionPicker`, "Reply in thread" (`thread-open`), Edit (`message-edit`) and Delete (`message-delete`), gated by `canReact` (:95), `canReply` (:99, which needs `onOpenThread`), `canEdit` (:91) and `canDelete` (:92). It is the only hover-revealed control in the SPA.
- **Thread rows:** `ThreadPanel.tsx:118-131` reuses `MessageItem` without `onOpenThread`, so a thread row has no "Reply in thread".
- **`ReactionPicker.tsx`:** a "React" button (`reaction-picker`, `aria-expanded`, `aria-label="Add a reaction"`, :28-37) toggling an absolutely positioned row (:40) of the six `REACTION_EMOJI` (`reactions.ts:18`), each a `reaction-option`. It closes only on a pick or a second click: no Escape, no outside click, no focus handling — and on purpose not on blur, which races the option's click (its header, :8-12).
- **Editing:** `MessageEditor.tsx:46` cancels on Escape.
- **Delete** has no confirmation: there is no `window.confirm` or modal anywhere in the SPA.
- **Always visible already:** `ReactionBar` chips, `ThreadSummary`, the channel header's controls, the member panel's remove buttons.
- **Tests:** Vitest clicks the actions by role and passes whatever the CSS — jsdom has none (`src/test/layout.ts:1-4`). In `tests/bdd/pages/chat_page.py`, `react_to` (:349-364) and `reply_in_thread` (:383-) hover first; `edit_message` (:296-307) and `delete_message` (:309-311) click straight through the transparent row. Every Playwright context is `browser.new_context()` with defaults (`tests/bdd/conftest.py:259, :342`): a desktop viewport, no touch.

## Requirements

1. **"⋯" on every message.** Every message that allows at least one action — in the channel and in the thread panel, at every width — shows a "⋯" button, always visible. It opens a menu of exactly the actions that message allows today, under the existing `can*` rules: React, Reply in thread, Edit, Delete. A pending or deleted message allows none, so it has no "⋯". The hover-revealed row is removed.
2. **React from the menu.** "React" opens the six-emoji row; picking one toggles that reaction, as the picker does today.
3. **Closing.** The menu and the emoji row close on Escape, on a click or tap anywhere outside them — including the touch that starts a scroll — and after any choice. Opening one message's menu closes any other, in the channel or the thread panel.
4. **Accessible.** "⋯" is a menu button: `aria-haspopup`, `aria-expanded`, and the accessible name **"Message actions"**. Opening it moves focus into the menu; every item can be reached and chosen from the keyboard; closing it returns focus to "⋯".
5. **Fully visible.** The menu and the emoji row always appear in full inside the viewport — never clipped by the scrolling message list or the thread panel, including on the last message and at the panel's right edge.

## Where the rules meet

- **A live delete and an open menu (Req 1, Req 3, Req 4):** Grace deletes a message while Ada has its menu open. The message becomes a tombstone with no "⋯"; the menu closes and Ada's focus moves to the message list — never to the page body. The same holds if the message stops allowing the action Ada was about to choose.
- **Edit and the menu (Req 3, Req 4):** choosing Edit closes the menu and opens the editor in the row. Saving, or Escape in the editor (which cancels, as today), returns focus to that message's "⋯"; the menu does not reopen.
- **React and closing (Req 2, Req 3):** picking an emoji closes the row and the menu. Escape in the row closes both and returns focus to "⋯".
- **Closing and the option's click (Req 2, Req 3):** closing on an outside tap must not swallow a tap on an emoji option — the race `ReactionPicker`'s header describes.
- **The thread panel (Req 1):** its rows get the same "⋯", without "Reply in thread", as today.

## Paths each rule holds on

| Path | What must be true |
|---|---|
| Someone else's message, on touch | "⋯" offers React and Reply only |
| Your own message | "⋯" offers React, Reply, Edit, Delete |
| A message in the thread panel | "⋯" offers no Reply |
| A pending message, then confirmed | no "⋯" while pending; "⋯" once confirmed |
| Keyboard only, desktop | Tab reaches "⋯", Enter opens it, every item can be reached and chosen, Escape closes and focus returns to "⋯" |
| Switching channel, or closing the thread, with a menu open | the menu goes with it; nothing stays open on the next view |
| The last message in a long channel | the menu opens in full, not cut off by the list |

## What this assumes — check before building on it

- **jsdom has no layout.** Req 5 can't be proven in Vitest; prove it in the BDD journey or the acceptance pack, where a real browser measures the menu's box against the viewport.
- **Playwright treats an `opacity-0` element as visible**, which is why today's `edit_message` and `delete_message` work without hovering. Once the row is gone, every page object action opens "⋯" first.
- **Closing on `pointerdown` outside the menu does not race a click inside it**, because the option is inside. Check it against the blur race `ReactionPicker.tsx:8-12` describes before relying on it.

## Timing

n/a — no throttle, window or race beyond Req 3's closing. A delete broadcast closes the menu whenever it lands; *Where the rules meet* says what follows.

## Decided already

1. One "⋯" menu at every width; the hover row is removed everywhere, desktop included.
2. The accessible name is "Message actions".
3. The reaction picker's missing Escape and outside-tap close come into this issue.
4. Delete stays immediate, as today.
5. The layout does not change: a narrow screen is #9 (gh-9). **D20** (React Native vs. PWA) stays 🔴 and untouched.

Left to the plan, on purpose: the menu's markup and keyboard model beyond Req 4, whether React opens a submenu or replaces the menu's items, how Req 5 positions the menu, and the icon.

## Tests

- **Vitest:** the menu's items for each `can*` combination; no "⋯" on a pending or deleted message; Escape, an outside pointer-down and a choice each close it; one menu open at a time; focus in and back, including after Edit; a delete arriving while the menu is open; the emoji row's closing.
- **One BDD journey on a touch context:** Ada, on a 1024×768 context with touch, reacts to Grace's message through "⋯" and replies in its thread.
- **The page objects change:** `react_to`, `reply_in_thread`, `edit_message` and `delete_message` open "⋯" instead of hovering or clicking through. Every existing journey must still pass.

## Record in this slice

- Doc 06: a new section on message actions — the "⋯" menu, its closing and focus rules.
- Register: a new entry **D47 🟢** — message actions behind one "⋯" menu at every width.
- An ADR: one menu at every width, rather than hover on desktop and something else on touch.

## Not in this issue

- Any layout change below 768px — the drawer, full-screen panels — which is #9 (gh-9).
- A confirmation before Delete.
- Long-press, swipe or any other gesture.
- A PWA, a service worker or a native app (D20).

## Acceptance — on the branch's preview

Ada and Grace in two browsers; Ada's is a **1024×768 context with touch** unless a check says otherwise. Each check fails on `main`, which has no "Message actions" button, and each posts its own message, so none depends on state an earlier one used:

1. Grace posts; Ada taps "⋯" on it and sees React and Reply only. She reacts; Grace sees the reaction without reloading.
2. Ada posts; "⋯" on her message offers React, Reply, Edit and Delete. She edits it through the menu; after saving, focus is on that message's "⋯".
3. On a desktop context, keyboard only: Ada tabs to "⋯" on a message, opens it with Enter, reaches Reply and opens the thread. She opens another "⋯" and presses Escape: the menu closes and focus is on that "⋯".
4. Ada opens "⋯", chooses React, then presses Escape: the row closes. She opens it again and taps outside it: it closes, and no reaction was added. On `main` the picker ignores both.
5. In a thread Ada opened, "⋯" on a reply offers no Reply in thread.
6. In a channel with enough messages to scroll, "⋯" on the last message opens in full inside the viewport.

## References

- `src/frontend/src/features/channels/MessageItem.tsx`, `ReactionPicker.tsx`, `MessageEditor.tsx`, `reactions.ts`
- `src/frontend/src/features/threads/ThreadPanel.tsx`
- `tests/bdd/pages/chat_page.py`; `tests/bdd/conftest.py`
- `docs/design/06-frontend-spa.md`; register D20
- `docs/issues/008.md` — the issue this and #9 were split from
