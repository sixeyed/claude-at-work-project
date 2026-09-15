/**
 * Rendering a component or a hook with the providers the app gives it.
 *
 * **A fresh `QueryClient` per test.** A shared one carries cache from one test
 * into the next, which is the classic TanStack flake. `retry: false`, because a
 * test that stubs a failure wants to see it at once; `gcTime: Infinity`, so no
 * garbage-collection timer outlives the test.
 *
 * The router is a `MemoryRouter` at `route`. With `path`, the UI is mounted as
 * that route, so `useParams` works. `location()` reports where the app has
 * navigated to, which is how a test asserts a redirect without a page to land
 * on.
 *
 * `socket` is what `useSocket()` returns: a fresh, unconnected `FakeSocket` by
 * default, or `null` for "not connected yet". The socket a hook opens itself
 * through `connect()` is a different one — see `latestSocket()`.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, renderHook, type RenderOptions } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect, type ReactElement, type ReactNode } from 'react'
import { MemoryRouter, Route, Routes, useLocation, type Location } from 'react-router-dom'

import { SocketProvider } from '../lib/realtime/SocketProvider'
import { asSocket, FakeSocket } from './socket'

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  })
}

export interface ProviderOptions {
  route?: string
  path?: string
  queryClient?: QueryClient
  socket?: FakeSocket | null
}

function LocationSpy({ onChange }: { onChange: (location: Location) => void }) {
  const location = useLocation()
  useEffect(() => onChange(location), [location, onChange])
  return null
}

function setUp({ route = '/', path, queryClient, socket }: ProviderOptions) {
  const client = queryClient ?? createTestQueryClient()
  const fake = socket === undefined ? new FakeSocket('test-token') : socket
  const seen: { current: Location | null } = { current: null }
  const onLocation = (location: Location) => {
    seen.current = location
  }

  function Providers({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[route]}>
          <SocketProvider socket={fake ? asSocket(fake) : null}>
            {path ? (
              <Routes>
                <Route path={path} element={children} />
                <Route path="*" element={null} />
              </Routes>
            ) : (
              children
            )}
            <LocationSpy onChange={onLocation} />
          </SocketProvider>
        </MemoryRouter>
      </QueryClientProvider>
    )
  }

  const location = () => {
    if (!seen.current) throw new Error('the router has not rendered')
    return seen.current
  }

  return { Providers, queryClient: client, socket: fake, location }
}

export function renderWithProviders(
  ui: ReactElement,
  options: ProviderOptions & Omit<RenderOptions, 'wrapper'> = {},
) {
  const { route, path, queryClient, socket, ...renderOptions } = options
  const { Providers, ...rest } = setUp({ route, path, queryClient, socket })
  const user = userEvent.setup()
  return { ...render(ui, { wrapper: Providers, ...renderOptions }), ...rest, user }
}

export function renderHookWithProviders<Result>(
  hook: () => Result,
  options: ProviderOptions = {},
) {
  const { Providers, ...rest } = setUp(options)
  return { ...renderHook(hook, { wrapper: Providers }), ...rest }
}
