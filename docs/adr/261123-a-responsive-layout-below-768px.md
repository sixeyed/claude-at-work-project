# A responsive layout below 768px: one element tree, narrow computed in JavaScript

- **Status:** Accepted
- **Date:** 2026-11-23

## Context

The shell was a fixed two-column grid with a 16rem sidebar, and the thread and member panels
sat beside the message list. On a phone that left a few dozen pixels for the messages. The
issue asks for a drawer, covering panels and 360px screens, and for a rotation that loses
nothing: a draft, an open thread, a scroll position. The message list is keyed and starts at its
newest message when it mounts, and a thread panel owns its scroll, so anything that remounts them
on a rotation loses exactly what the issue wants kept. jsdom evaluates no media query, so a layout
done in CSS alone cannot be tested.

## Decision

We will compute "narrow" once, in JavaScript: `useNarrow()` reads `matchMedia('(min-width:
768px)')` through `useSyncExternalStore` and is the only source of the breakpoint. The shell and
the channel view choose classes and attributes from it; no `md:` variants carry the layout.
The element tree is the same at every width — narrow changes classes, attributes and leaf
siblings, never the type or position of an ancestor of the route's content, the message list,
the composer or the thread panel. The drawer is `ChatLayout` state, and a panel covers the
message column as an absolutely positioned overlay while the column stays mounted (and `inert`),
never `display:none` and never unmounted. This is a responsive web layout; it leaves
register D20 (React Native vs. PWA) open.

## Consequences

A rotation re-renders and never remounts, so scroll positions and drafts survive; Vitest can move
the breakpoint, and CSS and JS cannot disagree at 767/768. The cost is that the layout depends on
JavaScript, and that every width-dependent choice goes through the hook rather than a class.
A modal drawer needs focus handling written by hand (focus in, a Tab wrap, focus back, `inert`
behind it). Only a device proves the keyboard and a real rotation.

## Alternatives Considered

### `md:` classes plus the hook

Two copies of the breakpoint, one of which the test harness cannot see.

### Two shells, `MobileShell` and `DesktopShell`

Simpler to read, but a rotation would remount the message list and the thread panel and lose
the scroll position the issue keeps.

### Unmount the message column while a panel covers it

Loses the scroll position outright. `display:none` is no better: a scroller whose box is
destroyed can come back at the top.
