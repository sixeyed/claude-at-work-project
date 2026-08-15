/**
 * Switching the active workspace.
 *
 * Not a UI filter: an access token carries exactly one workspace in its `wsp`
 * claim, so switching exchanges the refresh token for a token scoped to the
 * other one (Conventions §5.4). Everything fetched under the old token belongs
 * to the old workspace, which is why the query keys carry the workspace id —
 * see `useChannels`.
 */

import * as session from '../../lib/auth/session'
import type { Session } from '../../lib/auth/session'

interface Props {
  current: Session
}

export function WorkspaceSwitcher({ current }: Props) {
  const active = current.workspaces.find((w) => w.id === current.activeWorkspaceId)

  return (
    <div className="border-b border-border px-3 py-4">
      <p data-testid="workspace-name" className="text-sm font-semibold text-ink">
        {active?.name ?? 'No workspace'}
      </p>
      <p data-testid="current-user" className="text-xs text-ink-muted">
        {current.profile.displayName}
      </p>

      {current.workspaces.length > 1 && (
        <ul data-testid="workspace-switcher" className="mt-2 flex flex-col gap-1">
          {current.workspaces.map((workspace) => (
            <li key={workspace.id}>
              <button
                type="button"
                data-testid="workspace-option"
                data-workspace-name={workspace.name}
                disabled={workspace.id === current.activeWorkspaceId}
                onClick={() => void session.changeWorkspace(workspace.id)}
                className="text-xs text-ink-muted underline disabled:no-underline disabled:opacity-50"
              >
                {workspace.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
