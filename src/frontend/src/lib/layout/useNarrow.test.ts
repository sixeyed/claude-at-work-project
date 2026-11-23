/**
 * `useNarrow`: narrow is a viewport under 768px (issue Req 1).
 *
 * The widths are literals, never the hook module's `NARROW_BELOW`: an export that
 * does not exist yet is `undefined`, and a width of `NaN` would read the same on
 * both sides of the line.
 */

import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { changeListenerCount, installViewport, setViewportWidth } from '../../test/viewport'
import { useNarrow } from './useNarrow'

describe('useNarrow', () => {
  it('is narrow at 767px and wide at 768px', () => {
    // The harness itself reads the two sides differently, so the hook is the variable.
    installViewport(767)
    expect(window.matchMedia('(min-width: 768px)').matches).toBe(false)
    const narrow = renderHook(() => useNarrow())
    expect(narrow.result.current).toBe(true)
    narrow.unmount()

    installViewport(768)
    expect(window.matchMedia('(min-width: 768px)').matches).toBe(true)
    const wide = renderHook(() => useNarrow())
    expect(wide.result.current).toBe(false)
  })

  it('follows the width across 768 in both directions', () => {
    const { result } = renderHook(() => useNarrow())
    expect(result.current).toBe(false)

    setViewportWidth(767)
    expect(result.current).toBe(true)

    setViewportWidth(768)
    expect(result.current).toBe(false)

    setViewportWidth(500)
    expect(result.current).toBe(true)

    setViewportWidth(1024)
    expect(result.current).toBe(false)
  })

  it('stops listening when unmounted', () => {
    const before = changeListenerCount()

    const { unmount } = renderHook(() => useNarrow())
    expect(changeListenerCount()).toBeGreaterThan(before)

    unmount()
    expect(changeListenerCount()).toBe(before)
  })
})
