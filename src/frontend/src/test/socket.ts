/**
 * An in-memory stand-in for the part of `socket.io-client` the app uses.
 *
 * `src/test/setup.ts` mocks `connect()` in `lib/realtime/socket.ts` to return
 * one of these, so no unit test opens a real connection. A test plays the
 * server: `serverConnect()`, `serverEmit(event, payload)`, and `onEmit(event,
 * responder)` to acknowledge what the app sends.
 *
 * **An emit with no responder is never acknowledged**, which is exactly what a
 * real socket does when the server is gone. A `timeout(ms).emit` then fails
 * with a timeout after `ms`, so the lost-ack path is testable with fake timers.
 * Acknowledgements are delivered on a microtask, never synchronously, because
 * a real one always crosses the network.
 */

import type { Socket } from '../lib/realtime/socket'

type Listener = (...args: unknown[]) => void
type Responder = (...payload: never[]) => unknown
type Ack = (...args: unknown[]) => void

export interface Emitted {
  event: string
  args: unknown[]
}

export class FakeSocket {
  connected = false
  closed = false
  readonly emitted: Emitted[] = []
  private readonly listeners = new Map<string, Set<Listener>>()
  private readonly responders = new Map<string, Responder>()

  constructor(readonly accessToken: string) {}

  on(event: string, listener: Listener): this {
    const set = this.listeners.get(event) ?? new Set()
    set.add(listener)
    this.listeners.set(event, set)
    return this
  }

  off(event: string, listener?: Listener): this {
    if (listener) this.listeners.get(event)?.delete(listener)
    else this.listeners.delete(event)
    return this
  }

  listenerCount(event: string): number {
    return this.listeners.get(event)?.size ?? 0
  }

  emit(event: string, ...args: unknown[]): this {
    this.send(event, args, null)
    return this
  }

  timeout(ms: number): { emit: (event: string, ...args: unknown[]) => FakeSocket } {
    return {
      emit: (event, ...args) => {
        this.send(event, args, ms)
        return this
      },
    }
  }

  disconnect(): this {
    this.connected = false
    this.closed = true
    return this
  }

  close(): this {
    return this.disconnect()
  }

  // --- the server's side ---------------------------------------------------

  /** Answer every `event` the app emits with an ack built from its payload. */
  onEmit<T extends unknown[]>(event: string, responder: (...payload: T) => unknown): void {
    this.responders.set(event, responder as Responder)
  }

  serverEmit(event: string, ...args: unknown[]): void {
    for (const listener of [...(this.listeners.get(event) ?? [])]) listener(...args)
  }

  serverConnect(): void {
    this.connected = true
    this.serverEmit('connect')
  }

  serverDisconnect(reason = 'transport close'): void {
    this.connected = false
    this.serverEmit('disconnect', reason)
  }

  serverRefuse(message = 'unauthorized'): void {
    this.serverEmit('connect_error', new Error(message))
  }

  private send(event: string, args: unknown[], timeoutMs: number | null): void {
    const last = args.at(-1)
    const ack = typeof last === 'function' ? (last as Ack) : undefined
    const payload = ack ? args.slice(0, -1) : args
    this.emitted.push({ event, args: payload })
    if (!ack) return

    const responder = this.responders.get(event)
    if (!responder) {
      if (timeoutMs !== null) {
        setTimeout(() => ack(new Error('operation has timed out')), timeoutMs)
      }
      return
    }

    const response = (responder as (...payload: unknown[]) => unknown)(...payload)
    // A responder may return a promise, which is how a test holds an ack back
    // to look at the state before it lands. A timeout emit acks
    // `(err, response)`; a plain one acks `(response)`.
    void Promise.resolve(response).then((value) =>
      timeoutMs === null ? ack(value) : ack(null, value),
    )
  }
}

/** The fake as the type the app's code expects. */
export function asSocket(fake: FakeSocket): Socket {
  return fake as unknown as Socket
}

const opened: FakeSocket[] = []

/** What `connect()` is mocked to: a fresh fake per call, remembered in order. */
export function fakeConnect(accessToken: string): Socket {
  const fake = new FakeSocket(accessToken)
  opened.push(fake)
  return asSocket(fake)
}

/** The socket `connect()` most recently returned. */
export function latestSocket(): FakeSocket {
  const fake = opened.at(-1)
  if (!fake) throw new Error('connect() has not been called')
  return fake
}

export function openedSockets(): readonly FakeSocket[] {
  return opened
}

export function resetSockets(): void {
  opened.length = 0
}
