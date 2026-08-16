/**
 * Both halves of the typing indicator: telling people, and being told.
 *
 * Its own file rather than more responsibilities in `useChannelSocket`, because
 * this is a feature and that is infrastructure — and because everything here is
 * ephemeral. Nothing typed is persisted, cached, or written to a store.
 *
 * **The throttle leads, it does not trail.** A trailing debounce delays the
 * indicator by its own window, which is the opposite of the point: the first
 * keystroke should tell people immediately. So the first emit goes out at once
 * and then at most one per window for as long as someone keeps typing.
 *
 * **Expiry is receiver-side, and there is no stop event.** A server that
 * tracked who was typing would need that state shared across pods for something
 * the design calls ephemeral — and it would still have to invent a timeout for
 * the person who closed their laptop mid-word. The receiver has to have one
 * either way, so the receiver is where it lives: two missed windows and the
 * name goes.
 *
 * **The name comes from the workspace directory, not from the event.** Putting
 * a display name on the payload is tempting — an ephemeral event cannot go
 * stale — but it would make two sources for one name, and the person typing is
 * by definition in the workspace the directory has already fetched.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import type { Socket } from '../../lib/realtime/socket'

/** First keystroke emits at once; then at most one emit per window. */
const TYPING_EMIT_INTERVAL_MS = 2000
/** Two missed windows. A name is dropped this long after its last event. */
const TYPING_TTL_MS = 4000

interface TypingEvent {
  channelId: string
  userId: string
}

export function useTyping(
  socket: Socket | null,
  channelId: string,
  userId: string,
): { typingUserIds: string[]; onKeystroke: () => void } {
  const [typingAt, setTypingAt] = useState<Record<string, number>>({})
  const lastEmit = useRef(0)

  const onKeystroke = useCallback(() => {
    if (!socket) return

    const now = Date.now()
    if (now - lastEmit.current < TYPING_EMIT_INTERVAL_MS) return
    lastEmit.current = now
    socket.emit('typing', { channelId })
  }, [socket, channelId])

  useEffect(() => {
    if (!socket) return

    function onUserTyping(event: TypingEvent) {
      // The server already skips the sender's own socket; this also covers the
      // same person's second tab, which `skip_sid` cannot see.
      if (event.userId === userId) return
      if (event.channelId !== channelId) return
      setTypingAt((current) => ({ ...current, [event.userId]: Date.now() }))
    }

    socket.on('user_typing', onUserTyping)
    return () => {
      socket.off('user_typing', onUserTyping)
    }
  }, [socket, channelId, userId])

  // A different channel is a different conversation; nobody carries over.
  useEffect(() => {
    setTypingAt({})
    lastEmit.current = 0
  }, [channelId])

  // The expiry sweep. A timer rather than a check-on-render, because "Ada
  // stopped typing" is not caused by anything the app renders — without this
  // the indicator would linger until something else happened to re-render.
  useEffect(() => {
    const timer = setInterval(() => {
      const cutoff = Date.now() - TYPING_TTL_MS
      setTypingAt((current) => {
        const fresh = Object.fromEntries(Object.entries(current).filter(([, at]) => at > cutoff))
        return Object.keys(fresh).length === Object.keys(current).length ? current : fresh
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  return { typingUserIds: Object.keys(typingAt), onKeystroke }
}
