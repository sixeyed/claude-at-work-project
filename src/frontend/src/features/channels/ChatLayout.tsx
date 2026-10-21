/**
 * The chat shell: workspace identity and channels on the left, the open channel
 * on the right — and the one live socket the whole app shares.
 *
 * **The socket is mounted here, not in `ChannelView`.** One long-lived
 * connection for the session (doc 06 §5.1): mounting it a level down would tear
 * it down and rebuild it on every navigation between channels, which is a
 * handshake, a JWKS check and a room re-join for something the user experiences
 * as clicking a link. Which channel is open is read from the store — the same
 * value `ChannelView` sets — so the hook follows navigation without owning it.
 */

import { type ReactNode, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

import * as session from '../../lib/auth/session'
import type { Session } from '../../lib/auth/session'
import { SocketProvider } from '../../lib/realtime/SocketProvider'
import { useChannelSocket } from '../../lib/realtime/useChannelSocket'
import { useAttachmentStore } from '../../stores/attachments'
import { useChatStore } from '../../stores/chat'
import { SearchBox } from '../search/SearchBox'
import { ClockContext } from '../settings/clock'
import { usePreferences } from '../settings/usePreferences'
import { cancelAll } from '../attachments/uploads'
import { ChannelList } from './ChannelList'
import { CreateChannelDialog } from './CreateChannelDialog'
import { DirectMessageList } from './DirectMessageList'
import { WorkspaceSwitcher } from './WorkspaceSwitcher'

interface Props {
  current: Session
  children: ReactNode
}

const STATUS_LABEL: Record<string, string> = {
  connecting: 'Connecting…',
  connected: 'Live',
  disconnected: 'Reconnecting…',
}

export function ChatLayout({ current, children }: Props) {
  const navigate = useNavigate()
  const activeChannelId = useChatStore((state) => state.activeChannelId)
  const connectionStatus = useChatStore((state) => state.connectionStatus)
  const joinedChannelId = useChatStore((state) => state.joinedChannelId)

  // A token is scoped to one workspace, so an upload started under the old one
  // must not carry on and a chip from it must not be offered in the new. The
  // cleanup runs when the workspace changes and when the shell goes away
  // (sign-out unmounts it); a reload loses chips by itself, they are in memory.
  // Likewise "the last channel", which Settings offers a way back to: an id from
  // the old workspace would open its 404.
  const workspaceId = current.activeWorkspaceId
  useEffect(
    () => () => {
      cancelAll()
      useAttachmentStore.getState().reset()
      useChatStore.getState().clearLastChannel()
    },
    [workspaceId],
  )

  // The clock preference, offered to every time on screen through a context so a
  // choice re-renders cached messages without refetching them (register D28).
  const preferences = usePreferences(current.accessToken, current.profile.id)

  const socket = useChannelSocket(
    current.accessToken,
    current.activeWorkspaceId,
    activeChannelId,
    // Who "I" am, so a reaction event can tell my own lit state from everyone
    // else's — the count is the channel's, the highlight is one person's.
    current.profile.id,
  )

  return (
    <SocketProvider socket={socket}>
      <ClockContext.Provider value={preferences.data?.clock}>
      <div className="grid h-full grid-cols-[16rem_1fr]">
        <aside className="flex flex-col border-r border-border bg-surface-sunken">
          <SearchBox workspaceId={current.activeWorkspaceId} />
          <WorkspaceSwitcher current={current} />

          <nav className="flex-1 overflow-y-auto">
            <ChannelList
              accessToken={current.accessToken}
              workspaceId={current.activeWorkspaceId}
            />
            <DirectMessageList
              accessToken={current.accessToken}
              workspaceId={current.activeWorkspaceId}
              userId={current.profile.id}
            />
          </nav>

          <div className="border-t border-border">
            <CreateChannelDialog
              accessToken={current.accessToken}
              workspaceId={current.activeWorkspaceId}
              onCreated={(channelId) => navigate(`/c/${channelId}`)}
            />
            <div className="flex items-center justify-between px-3 pb-3">
              <button
                type="button"
                data-testid="sign-out"
                onClick={() => void session.signOut()}
                className="text-xs text-ink-muted underline"
              >
                Sign out
              </button>
              {/* Read by the live-delivery scenarios, so they wait on an event
                  rather than a timeout: `data-joined-channel` is set once the
                  server acknowledges the open channel's join, which is when its
                  broadcasts start arriving — `connected` alone is too early. */}
              <span
                data-testid="connection-status"
                data-status={connectionStatus}
                data-joined-channel={joinedChannelId ?? undefined}
                className="text-xs text-ink-muted"
              >
                {STATUS_LABEL[connectionStatus]}
              </span>
            </div>
          </div>
        </aside>

        <main className="h-full overflow-y-auto bg-surface">{children}</main>
      </div>
      </ClockContext.Provider>
    </SocketProvider>
  )
}
