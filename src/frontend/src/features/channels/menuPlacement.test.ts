/**
 * Where the "⋯" menu opens (gh-8 Req 5). jsdom has no layout, so the arithmetic
 * is proven here on plain numbers; the real geometry is checked in a browser.
 *
 * Viewport 1024×768, menu 160×150, margin 8, gap 4. Every vertical case sits on
 * the boundary and one pixel past it.
 */

import { describe, expect, it } from 'vitest'

import { placeMenu } from './menuPlacement'

const viewport = { width: 1024, height: 768 }
const menu = { width: 160, height: 150 }
const at = (top: number, bottom: number, right = 600) => ({
  top,
  bottom,
  left: right - 20,
  right,
})

describe('placeMenu', () => {
  it('opens below "⋯" when it fits, to the pixel', () => {
    // 606 + 4 + 150 = 760 = 768 − 8: the last pixel that fits.
    expect(placeMenu(at(586, 606), menu, viewport).top).toBe(610)
  })

  it('opens above when one more pixel would cross the bottom margin', () => {
    // 607 + 4 + 150 = 761 > 760: below no longer fits. Above: 587 − 4 − 150 = 433.
    expect(placeMenu(at(587, 607), menu, viewport).top).toBe(433)
  })

  it('above is taken down to the top margin, and not one pixel past it', () => {
    // Below never fits (bottom 700). 162 − 4 − 150 = 8: exactly on the margin, so above.
    expect(placeMenu(at(162, 700), menu, viewport).top).toBe(8)
    // 161 − 4 − 150 = 7 < 8: neither side fits, so below, clamped to 768 − 8 − 150 = 610.
    expect(placeMenu(at(161, 700), menu, viewport).top).toBe(610)
  })

  it('a menu taller than the viewport starts at the top margin', () => {
    expect(placeMenu(at(300, 320), { width: 160, height: 800 }, viewport).top).toBe(8)
  })

  it('right-aligned to "⋯"', () => {
    expect(placeMenu(at(100, 120, 600), menu, viewport).left).toBe(440)
  })

  it('held inside the right edge — "⋯" at the thread panel’s edge', () => {
    // 1020 − 160 = 860 would reach 1020 > 1016: clamped to 1024 − 8 − 160 = 856.
    expect(placeMenu(at(100, 120, 1020), menu, viewport).left).toBe(856)
  })

  it('held inside the left edge', () => {
    expect(placeMenu(at(100, 120, 100), menu, viewport).left).toBe(8)
  })
})
