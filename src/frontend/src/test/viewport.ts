/**
 * A viewport for jsdom, which evaluates no media query and has no `matchMedia`.
 *
 * `installViewport(width)` defines `window.matchMedia` over one width, returning a
 * fake `MediaQueryList` whose `matches` is live; `setViewportWidth(width)` changes
 * the width the way a rotation or a resize does, inside `act`: `innerWidth`, then
 * a `change` on every list whose answer flipped, then a window `resize`.
 *
 * Only `(min-width: Npx)` and `(max-width: Npx)` are understood. Anything else
 * throws, so a hook that asks a rem query fails loudly instead of quietly reading
 * as wide.
 *
 * `setup.ts` installs it at 1024 before every test file and again after every
 * test, so a test that does not mention the viewport runs wide, as it did before
 * the layout had a narrow side.
 */

import { act } from '@testing-library/react'

type Listener = (event: MediaQueryListEvent) => void

interface FakeList {
  media: string
  matches: boolean
  onchange: Listener | null
  listeners: Set<Listener>
}

let width = 1024
let lists = new Set<FakeList>()

const QUERY = /^\(\s*(min|max)-width:\s*(\d+(?:\.\d+)?)px\s*\)$/

function evaluate(query: string): boolean {
  const parsed = QUERY.exec(query.trim())
  if (!parsed) throw new Error(`Unsupported media query: ${query}`)
  const limit = Number(parsed[2])
  return parsed[1] === 'min' ? width >= limit : width <= limit
}

function makeList(query: string): MediaQueryList {
  evaluate(query) // throws for what it cannot read
  const list: FakeList = { media: query, matches: evaluate(query), onchange: null, listeners: new Set() }
  lists.add(list)
  const add = (_type: string, listener: Listener) => void list.listeners.add(listener)
  const remove = (_type: string, listener: Listener) => void list.listeners.delete(listener)
  return {
    get media() {
      return list.media
    },
    get matches() {
      return list.matches
    },
    get onchange() {
      return list.onchange
    },
    set onchange(value) {
      list.onchange = value as Listener | null
    },
    addEventListener: add,
    removeEventListener: remove,
    addListener: (listener: Listener) => add('change', listener),
    removeListener: (listener: Listener) => remove('change', listener),
    dispatchEvent: () => true,
  } as unknown as MediaQueryList
}

function setInnerWidth(value: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value })
}

export function installViewport(initial = 1024): void {
  width = initial
  lists = new Set()
  setInnerWidth(initial)
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query: string) => makeList(query),
  })
}

export function setViewportWidth(next: number): void {
  act(() => {
    width = next
    setInnerWidth(next)
    for (const list of [...lists]) {
      const matches = evaluate(list.media)
      if (matches === list.matches) continue
      list.matches = matches
      const event = { matches, media: list.media } as MediaQueryListEvent
      list.onchange?.(event)
      for (const listener of [...list.listeners]) listener(event)
    }
    window.dispatchEvent(new Event('resize'))
  })
}

/** Live `change` listeners across every list: what an unmounted hook must give back. */
export function changeListenerCount(): number {
  let count = 0
  for (const list of lists) count += list.listeners.size
  return count
}
