/**
 * Runs before every Vitest file.
 *
 * - jest-dom's matchers (`toBeInTheDocument`, `toHaveAttribute`, …).
 * - **MSW listens before the test file is imported**, not in a `beforeAll`.
 *   `openapi-fetch` captures `globalThis.fetch` when `lib/api/messaging.ts`
 *   creates its client at import time, so a server that started listening
 *   afterwards would never see those requests.
 * - `onUnhandledRequest: 'error'`: a call nothing stubbed fails the test rather
 *   than reaching whatever is listening on localhost.
 * - `connect()` is replaced with the fake socket for every test, so no unit
 *   test can open a real connection.
 * - `window.matchMedia` is the fake of `viewport.ts`, at 1024px.
 * - After each test: handlers, recorded requests, sockets, the page's focus and
 *   visibility, the DOM and the Zustand store go back to where they started.
 */

import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, vi } from 'vitest'

import { useChatStore } from '../stores/chat'
import { resetRequests, server } from './api'
import { resetPageAttention } from './page'
import { resetSockets } from './socket'
import { installViewport } from './viewport'

vi.mock('../lib/realtime/socket', async () => {
  const { fakeConnect } = await import('./socket')
  return { connect: fakeConnect }
})

server.listen({ onUnhandledRequest: 'error' })

// jsdom has no `matchMedia`: every test runs at 1024px, the wide layout, unless
// it calls `setViewportWidth`. Installed again after each test, below.
installViewport()

const initialChat = useChatStore.getState()

afterEach(() => {
  cleanup()
  installViewport()
  server.resetHandlers()
  resetRequests()
  resetSockets()
  resetPageAttention()
  useChatStore.setState(initialChat, true)
})

afterAll(() => {
  server.close()
})
