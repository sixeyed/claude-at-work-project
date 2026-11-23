# One "⋯" menu holds a message's actions, at every width

- **Status:** Accepted
- **Date:** 2026-11-23

## Context

A message's actions — react, reply in a thread, edit, delete — were a row of buttons revealed
on hover (`opacity-0 group-hover:opacity-100`). A touch screen has no hover, so on a tablet
the actions were invisible. Playwright also treats `opacity-0` as visible, so no test noticed.
The emoji row, once open, closed only when an emoji was picked or its button pressed again.

## Decision

We will put every message action behind one always-visible "⋯" menu button, at every width, in
the channel and the thread panel, and remove the hover row everywhere. The menu is a WAI-ARIA
menu button offering exactly what `offeredActions` says the message allows. It is drawn in a
portal on `document.body`, `position: fixed`, so the scrolling list and panel cannot clip it,
and it closes on a press outside, Escape or a choice — never on blur. One menu is open at a
time, through an instance id in the chat store.

## Consequences

Touch and keyboard users reach every action, and the rules for what a message offers are in
one pure function. One more control per message is always on screen. Delete stays immediate
with no confirmation; layout below 768px is a separate issue. The menu code owns its own
placement arithmetic (`placeMenu`) rather than a library, and Tab is kept inside the menu
rather than closing it, which is a deliberate departure from the APG's optional behaviour.

## Alternatives Considered

### Hover on desktop plus long-press on touch

Keeps the desktop look, but a long-press is undiscoverable, conflicts with text selection, and
leaves two ways to do everything to test and keep in step.

### A per-width split

A hover row above a breakpoint and a menu below it. Two implementations of one rule, and a
touch laptop or a tablet wider than the breakpoint would still get the wrong one.
