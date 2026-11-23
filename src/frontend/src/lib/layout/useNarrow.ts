/**
 * Whether the viewport is narrower than the breakpoint (register D48).
 *
 * This is the only source of "narrow" in the SPA: the shell and the channel view
 * choose their classes and attributes from it in JavaScript rather than with
 * `md:` variants, so CSS and JS can never disagree at 767/768 — and so a test can
 * move the line, since jsdom evaluates no media query.
 *
 * `window.matchMedia` is called inside `subscribe` and `getSnapshot`, never at
 * module load: a cached `MediaQueryList` would keep listening to a window that a
 * test has since replaced.
 */

import { useSyncExternalStore } from 'react'

/** Below this many CSS pixels the layout is the phone layout. */
export const NARROW_BELOW = 768

const WIDE_QUERY = `(min-width: ${NARROW_BELOW}px)`

function subscribe(onChange: () => void): () => void {
  const list = window.matchMedia(WIDE_QUERY)
  list.addEventListener('change', onChange)
  return () => list.removeEventListener('change', onChange)
}

function getSnapshot(): boolean {
  return !window.matchMedia(WIDE_QUERY).matches
}

/** The server has no viewport; the SPA is client-rendered, so this is only a fallback. */
function getServerSnapshot(): boolean {
  return false
}

export function useNarrow(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}
