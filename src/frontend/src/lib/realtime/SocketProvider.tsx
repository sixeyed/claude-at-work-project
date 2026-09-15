/**
 * The live socket, as a React context.
 *
 * `useChannelSocket` owns the connection's lifecycle and returns nothing, so
 * without this there is no way for a component to *send* on it — which the
 * composer needs the moment sending moves off REST.
 *
 * A context and not the Zustand store, deliberately. That store holds client
 * state (register D24) and this is neither client state nor server state: it is
 * a resource with a lifecycle, and a context is what React has for those.
 * `connectionStatus` — a fact *about* the resource — does live in the store.
 */

/* eslint-disable react-refresh/only-export-components --
   `useSocket` is this context's only reader and belongs beside the provider
   that supplies it. Splitting them to keep Fast Refresh happy would scatter one
   idea across two files; a full reload on edits to this file is the cheaper
   trade. */

import { createContext, useContext, type ReactNode } from 'react'

import type { Socket } from './socket'

const SocketContext = createContext<Socket | null>(null)

export function SocketProvider({
  socket,
  children,
}: {
  socket: Socket | null
  children: ReactNode
}) {
  return <SocketContext.Provider value={socket}>{children}</SocketContext.Provider>
}

/** The live socket, or `null` while it is connecting or has been refused. */
export function useSocket(): Socket | null {
  return useContext(SocketContext)
}
