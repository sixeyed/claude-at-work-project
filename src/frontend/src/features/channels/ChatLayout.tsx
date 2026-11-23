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

import {
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import * as session from '../../lib/auth/session'
import type { Session } from '../../lib/auth/session'
import { useNarrow } from '../../lib/layout/useNarrow'
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

const FOCUSABLE = 'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'

export function ChatLayout({ current, children }: Props) {
  const navigate = useNavigate()
  const { pathname } = useLocation()

  // Below 768px the sidebar is a modal drawer behind ☰ (register D48). The element
  // tree is the same at every width — narrow changes classes, attributes and leaf
  // siblings only — so a rotation re-renders and never remounts the route's content.
  const narrow = useNarrow()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const shown = narrow && drawerOpen
  const sidebarId = useId()
  const sidebar = useRef<HTMLElement>(null)
  const hamburger = useRef<HTMLButtonElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)

  // Crossing to wide drops the open state, so a later return to narrow starts closed.
  // Set during render, the pattern React documents for state derived from a prop.
  if (!narrow && drawerOpen) setDrawerOpen(false)

  // Read by callbacks that outlive the render that made them (a DM that opens after
  // a network round trip) and by the arrival effect, which must not depend on it.
  const narrowRef = useRef(narrow)
  useEffect(() => {
    narrowRef.current = narrow
  })

  // ☰ is inert while the drawer is open, so focus can only go back to it after the
  // commit that removes `inert`: closing asks, an effect on `shown` does it.
  const focusHamburger = useRef(false)

  const openDrawer = useCallback(() => {
    // A "⋯" menu closes on a pointer-down elsewhere, which a keyboard or screen
    // reader activation of ☰ never sends.
    useChatStore.setState({ openMessageMenu: null })
    setDrawerOpen(true)
  }, [])

  // Every close goes through here.
  const closeDrawer = useCallback(() => {
    setDrawerOpen(false)
    if (narrowRef.current) focusHamburger.current = true
  }, [])

  useEffect(() => {
    if (shown) {
      closeButton.current?.focus()
    } else if (focusHamburger.current) {
      focusHamburger.current = false
      hamburger.current?.focus()
    }
  }, [shown])

  // "/" is Pick a channel: a screen with nothing on it but the drawer, so it opens
  // there whenever the path becomes "/" while narrow — and not on a rotation.
  useEffect(() => {
    if (pathname === '/' && narrowRef.current) setDrawerOpen(true)
  }, [pathname])

  // Crossing to narrow with focus in the sidebar, which has just become a closed
  // drawer: put it on ☰ rather than let it drop to the body. Layout effect, so it
  // reads focus before the browser's own fixup of a hidden element.
  const wasNarrow = useRef(narrow)
  useLayoutEffect(() => {
    if (narrow && !wasNarrow.current && sidebar.current?.contains(document.activeElement)) {
      hamburger.current?.focus()
    }
    wasNarrow.current = narrow
  }, [narrow])

  function onDrawerKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (!shown) return
    if (event.key === 'Escape') {
      event.preventDefault()
      closeDrawer()
      return
    }
    if (event.key !== 'Tab') return

    // Hold Tab inside the drawer: wrap at either end.
    const controls = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE),
    ).filter((element) => !element.hasAttribute('disabled'))
    const first = controls[0]
    const last = controls[controls.length - 1]
    if (!first || !last) return
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

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
      <div
        className={
          narrow
            ? 'grid h-full grid-cols-[minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)]'
            : 'grid h-full grid-cols-[16rem_1fr]'
        }
      >
        {narrow && (
          <div
            inert={shown}
            className="flex items-center gap-3 border-b border-border bg-surface px-3 py-2"
          >
            <button
              ref={hamburger}
              type="button"
              data-testid="drawer-open"
              aria-label="Open sidebar"
              aria-expanded={shown}
              aria-controls={sidebarId}
              onClick={openDrawer}
              className="rounded px-2 py-1 text-lg text-ink hover:bg-surface-sunken"
            >
              <span aria-hidden="true">☰</span>
            </button>
            <span className="text-sm font-semibold text-ink">CollabHub</span>
          </div>
        )}
        {shown && (
          <button
            type="button"
            tabIndex={-1}
            data-testid="drawer-backdrop"
            aria-label="Dismiss sidebar"
            onClick={closeDrawer}
            className="fixed inset-0 z-20 bg-black/40"
          />
        )}
        <aside
          ref={sidebar}
          id={sidebarId}
          data-testid="sidebar"
          // Closed is `hidden`, not a class: it takes the drawer's controls out of the
          // tab order and the accessibility tree, and preflight's `[hidden]` is
          // `!important`, so the `flex` below cannot undo it.
          hidden={narrow && !shown}
          role={shown ? 'dialog' : undefined}
          aria-modal={shown ? true : undefined}
          aria-label={shown ? 'Sidebar' : undefined}
          onKeyDown={onDrawerKeyDown}
          className={
            narrow
              ? 'fixed inset-y-0 left-0 z-30 flex w-72 max-w-[85vw] flex-col border-r border-border bg-surface-sunken'
              : 'flex flex-col border-r border-border bg-surface-sunken'
          }
        >
          {shown && (
            <button
              ref={closeButton}
              type="button"
              data-testid="drawer-close"
              aria-label="Close sidebar"
              onClick={closeDrawer}
              className="self-end px-3 pt-2 text-xs text-ink-muted underline"
            >
              Close
            </button>
          )}
          <SearchBox workspaceId={current.activeWorkspaceId} onNavigate={closeDrawer} />
          <WorkspaceSwitcher current={current} onNavigate={closeDrawer} />

          <nav className="flex-1 overflow-y-auto">
            <ChannelList
              accessToken={current.accessToken}
              workspaceId={current.activeWorkspaceId}
              onNavigate={closeDrawer}
            />
            <DirectMessageList
              accessToken={current.accessToken}
              workspaceId={current.activeWorkspaceId}
              userId={current.profile.id}
              onNavigate={closeDrawer}
            />
          </nav>

          <div className="border-t border-border">
            <CreateChannelDialog
              accessToken={current.accessToken}
              workspaceId={current.activeWorkspaceId}
              onCreated={(channelId) => {
                navigate(`/c/${channelId}`)
                closeDrawer()
              }}
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

        <main
          inert={shown}
          className={
            narrow ? 'min-h-0 overflow-y-auto bg-surface' : 'h-full overflow-y-auto bg-surface'
          }
        >
          {children}
        </main>
      </div>
      </ClockContext.Provider>
    </SocketProvider>
  )
}
