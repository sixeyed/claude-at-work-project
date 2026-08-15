/**
 * The chat shell: workspace identity and channels on the left, the open channel
 * on the right.
 */

import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

import * as session from '../../lib/auth/session'
import type { Session } from '../../lib/auth/session'
import { ChannelList } from './ChannelList'
import { CreateChannelDialog } from './CreateChannelDialog'
import { WorkspaceSwitcher } from './WorkspaceSwitcher'

interface Props {
  current: Session
  children: ReactNode
}

export function ChatLayout({ current, children }: Props) {
  const navigate = useNavigate()

  return (
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
          <div className="px-3 pb-3">
            <button
              type="button"
              data-testid="sign-out"
              onClick={() => void session.signOut()}
              className="text-xs text-ink-muted underline"
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <main className="h-full overflow-y-auto bg-surface">{children}</main>
    </div>
  )
}
