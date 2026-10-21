import { useEffect } from 'react'
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useSearchParams,
} from 'react-router-dom'

import { ChannelView } from './features/channels/ChannelView'
import { ChatLayout } from './features/channels/ChatLayout'
import { SearchPage } from './features/search/SearchPage'
import { SettingsPage } from './features/settings/SettingsPage'
import * as session from './lib/auth/session'
import { useSession } from './lib/auth/useSession'

/**
 * Routes and the guard that decides which of them a visitor may see.
 *
 * The guard is one component rather than a check repeated in each page: a
 * signed-out user reaching a channel by pasting its URL has to land on sign-in,
 * and that has to be true for every protected route including the ones a later
 * slice adds.
 */

/** The route a redirect to sign-in carried in its state, if it carried one. */
function returnTarget(routerState: unknown): string | undefined {
  if (typeof routerState !== 'object' || routerState === null || !('from' in routerState)) return
  return typeof routerState.from === 'string' ? routerState.from : undefined
}

function SignIn() {
  const state = useSession()
  const from = returnTarget(useLocation().state)

  // Without this the sign-in form paints for one frame while the session is
  // still restoring from the refresh cookie, and a returning user sees a flash
  // of "sign in" before being redirected home.
  if (state.status === 'loading') return <Loading />
  if (state.status === 'signedIn') return <Navigate to="/" replace />

  return (
    <main className="mx-auto flex max-w-md flex-col gap-4 p-8">
      <h1 className="text-2xl font-semibold text-ink">CollabHub</h1>
      <p className="text-ink-muted">Sign in with your CollabHub account.</p>
      {state.status === 'signedOut' && state.error && (
        <p data-testid="sign-in-error" role="alert" className="text-sm text-danger">
          {state.error}
        </p>
      )}
      <button
        type="button"
        data-testid="sign-in"
        onClick={() => void session.signIn('dex', from)}
        className="rounded bg-accent px-4 py-2 font-medium text-accent-ink"
      >
        Sign in
      </button>
    </main>
  )
}

/**
 * Where the Auth service sends the browser once identity is established.
 *
 * The code in the query string is spent exactly once. React's StrictMode runs
 * effects twice in development, so the guard against a second exchange lives in
 * the store (it clears the verifier before spending it) rather than here — an
 * effect cleanup would not be enough.
 */
function Callback() {
  const [query] = useSearchParams()
  const navigate = useNavigate()

  useEffect(() => {
    void session.completeSignIn(query).then((signedIn) => {
      // Back to the route the visitor first asked for, if they were sent here from one.
      navigate(signedIn ? session.takeReturnPath() : '/sign-in', { replace: true })
    })
  }, [query, navigate])

  return <Loading label="Signing you in…" />
}

function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <p data-testid="app-loading" className="p-8 text-ink-muted">
      {label}
    </p>
  )
}

/** Renders the chat shell for a signed-in user, or sends them to sign in. */
function Protected({ children }: { children: React.ReactNode }) {
  const state = useSession()
  const location = useLocation()

  if (state.status === 'loading') return <Loading />
  // Remember where they were going: the sign-in page hands it to `signIn`, and the
  // callback sends them back to it.
  if (state.status === 'signedOut') {
    return <Navigate to="/sign-in" replace state={{ from: location.pathname + location.search }} />
  }

  return <ChatLayout current={state.session}>{children}</ChatLayout>
}

function NoChannelSelected() {
  return (
    <p data-testid="no-channel-selected" className="p-6 text-sm text-ink-muted">
      Pick a channel, or create one.
    </p>
  )
}

function NotFound() {
  return <p className="p-8 text-ink-muted">No such page.</p>
}

function ChannelRoute() {
  const state = useSession()
  if (state.status !== 'signedIn') return null
  return (
    <ChannelView
      accessToken={state.session.accessToken}
      workspaceId={state.session.activeWorkspaceId}
      // Who is signed in, so a message row can tell its own words from
      // someone else's. Nothing below this point had any way to know.
      userId={state.session.profile.id}
    />
  )
}

function SearchRoute() {
  const state = useSession()
  if (state.status !== 'signedIn') return null
  return (
    <SearchPage
      accessToken={state.session.accessToken}
      workspaceId={state.session.activeWorkspaceId}
    />
  )
}

function SettingsRoute() {
  const state = useSession()
  if (state.status !== 'signedIn') return null
  return <SettingsPage accessToken={state.session.accessToken} userId={state.session.profile.id} />
}

export function App() {
  useEffect(() => {
    void session.restore()
  }, [])

  return (
    <Routes>
      <Route
        path="/"
        element={
          <Protected>
            <NoChannelSelected />
          </Protected>
        }
      />
      <Route
        path="/c/:channelId"
        element={
          <Protected>
            <ChannelRoute />
          </Protected>
        }
      />
      <Route
        path="/search"
        element={
          <Protected>
            <SearchRoute />
          </Protected>
        }
      />
      <Route
        path="/settings"
        element={
          <Protected>
            <SettingsRoute />
          </Protected>
        }
      />
      <Route path="/sign-in" element={<SignIn />} />
      <Route path="/auth/callback" element={<Callback />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
