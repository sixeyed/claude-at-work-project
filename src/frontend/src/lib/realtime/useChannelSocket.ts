/**
 * One socket for the whole chat shell, and the inbound events it carries.
 *
 * Mounted in `ChatLayout`, not in `ChannelView` — one long-lived connection
 * (doc 06 §5.1), not one that is torn down and rebuilt on every navigation.
 *
 * Four rules run through this file, and each of them is a bug that would
 * otherwise be found in production rather than in a test.
 *
 * **The access token is the connection's identity, so it is the effect's
 * dependency.** It changes on renewal *and* on a workspace switch, so one key
 * satisfies both Conventions §5.4 (a connection keeps the workspace of the
 * token that opened it) and doc 06 §4 (a switch drops the socket) without a
 * second lifecycle hook that somebody has to remember.
 *
 * **A refused handshake stops; a dropped transport retries.** Socket.IO's
 * built-in backoff is right for a network blip and wrong for a token the server
 * has already rejected — that will be rejected identically forever, and the
 * retry loop hides the real problem behind a spinner. `connect_error` therefore
 * disconnects, and recovery comes from this effect re-running with a fresh
 * token, which is the only thing that could change the answer.
 *
 * **Every connect re-joins *and* refetches.** python-socketio has no
 * connection-state recovery: re-entering a room replays nothing, so everything
 * broadcast while the client was away is simply gone. The refetch is the
 * recovery mechanism and the re-join only resumes the live stream from that
 * point — one line, and the difference between a reconnect that works and one
 * that works when the timing is lucky.
 *
 * **An event for a channel with no cached history is dropped.**
 * `setQueryData` on an empty key stores whatever the updater returns, so a
 * handler that built a fresh page there would invent a complete one-message
 * history with no cursor — and the real history would never load. The helpers
 * in `useMessages.ts` no-op on an absent entry; handlers key on **the event's**
 * `channelId`, so a background channel that *is* cached still updates.
 */

import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import type { Message } from '../api/messaging'
import { messageKeys, upsertMessage } from '../../features/channels/useMessages'
import { useChatStore } from '../../stores/chat'
import { connect, type Socket } from './socket'

export function useChannelSocket(
  accessToken: string,
  workspaceId: string | null,
  channelId: string | null,
): Socket | null {
  const queryClient = useQueryClient()
  const setConnectionStatus = useChatStore((state) => state.setConnectionStatus)
  const [socket, setSocket] = useState<Socket | null>(null)

  // The handlers below are registered once, on mount, and would otherwise close
  // over whichever channel was open at that moment. A ref is what lets the
  // `connect` handler re-join the channel the user is looking at *now*.
  const activeChannel = useRef(channelId)
  activeChannel.current = channelId

  useEffect(() => {
    setConnectionStatus('connecting')
    const live = connect(accessToken)
    setSocket(live)

    function onConnect() {
      setConnectionStatus('connected')

      const current = activeChannel.current
      if (!current) return

      live.emit('join_channel', current)
      // Whatever was said while this client was away went to a room it was not
      // in. Re-joining does not replay it; refetching does.
      void queryClient.invalidateQueries({ queryKey: messageKeys.list(workspaceId, current) })
    }

    function onDisconnect() {
      setConnectionStatus('disconnected')
    }

    function onConnectError() {
      // The server said no. Retrying says the same thing forever.
      live.disconnect()
      setConnectionStatus('disconnected')
    }

    function onMessage(message: Message) {
      upsertMessage(queryClient, messageKeys.list(workspaceId, message.channelId), message)
    }

    live.on('connect', onConnect)
    live.on('disconnect', onDisconnect)
    live.on('connect_error', onConnectError)
    // All three events carry the full `Message`, including the delete — a
    // client holding only an id could not render the tombstone.
    live.on('message_received', onMessage)
    live.on('message_edited', onMessage)
    live.on('message_deleted', onMessage)

    return () => {
      live.close()
      setSocket(null)
      setConnectionStatus('disconnected')
    }
  }, [accessToken, workspaceId, queryClient, setConnectionStatus])

  // Joining and leaving follow the open channel, and are separate from the
  // connection's own lifecycle: navigating between channels must not reconnect.
  useEffect(() => {
    if (!socket || !channelId) return

    if (socket.connected) socket.emit('join_channel', channelId)
    return () => {
      if (socket.connected) socket.emit('leave_channel', channelId)
    }
  }, [socket, channelId])

  return socket
}
