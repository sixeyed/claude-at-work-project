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

import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

import * as session from '../../lib/auth/session'
import type { Session } from '../../lib/auth/session'
import { SocketProvider } from '../../lib/realtime/SocketProvider'
import { useChannelSocket } from '../../lib/realtime/useChannelSocket'
import { useChatStore } from '../../stores/chat'
import { ChannelList } from './ChannelList'
import { CreateChannelDialog } from './CreateChannelDialog'
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

  const socket = useChannelSocket(
    current.accessToken,
    current.activeWorkspaceId,
    activeChannelId,
  )

  return (
    <SocketProvider socket={socket}>
      <div className="grid h-full grid-cols-[16rem_1fr]">
        <aside className="flex flex-col border-r border-border bg-surface-sunken">
          <WorkspaceSwitcher current={current} />

          <nav className="flex-1 overflow-y-auto">
            <ChannelList
              accessToken={current.accessToken}
              workspaceId={current.activeWorkspaceId}
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
              {/* Read by the reconnect scenario, so recovery is asserted on an
                  event rather than on a timeout. */}
              <span
                data-testid="connection-status"
                data-status={connectionStatus}
                className="text-xs text-ink-muted"
              >
                {STATUS_LABEL[connectionStatus]}
              </span>
            </div>
          </div>
        </aside>

        <main className="h-full overflow-y-auto bg-surface">{children}</main>
      </div>
    </SocketProvider>
  )
}
