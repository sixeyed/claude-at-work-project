/**
 * Where the "⋯" menu goes. Pure, because jsdom has no layout: the arithmetic is
 * proven in unit tests and the real geometry in a browser.
 */

/** Pixels between "⋯" and the menu. */
export const MENU_GAP = 4
/** Pixels the menu keeps from every viewport edge. */
export const VIEWPORT_MARGIN = 8

export interface Box {
  top: number
  bottom: number
  left: number
  right: number
}
export interface Size {
  width: number
  height: number
}

/** Clamp into `[min, max]`; an empty range (max < min) gives `min`. */
function clamp(value: number, min: number, max: number): number {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

/**
 * Below "⋯" when the menu fits there, otherwise above when it fits there,
 * otherwise below and clamped inside the viewport. Right-aligned to "⋯" and
 * clamped to the viewport's width.
 */
export function placeMenu(
  anchor: Box,
  menu: Size,
  viewport: Size,
): { top: number; left: number } {
  const below = anchor.bottom + MENU_GAP
  const above = anchor.top - MENU_GAP - menu.height
  const maxTop = viewport.height - VIEWPORT_MARGIN - menu.height

  let top: number
  if (below <= maxTop) top = below
  else if (above >= VIEWPORT_MARGIN) top = above
  else top = clamp(below, VIEWPORT_MARGIN, maxTop)

  const left = clamp(
    anchor.right - menu.width,
    VIEWPORT_MARGIN,
    viewport.width - VIEWPORT_MARGIN - menu.width,
  )
  return { top, left }
}
