import { useEffect } from 'react'
import { Navigate, Route, Routes, useNavigate, useSearchParams } from 'react-router-dom'

import { ChannelView } from './features/channels/ChannelView'
import { ChatLayout } from './features/channels/ChatLayout'
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

function SignIn() {
  const state = useSession()

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
        onClick={() => void session.signIn()}
        className="rounded bg-accent px-4 py-2 font-medium text-accent-ink"
      >
        Sign in
      </button>
      <p className="text-sm text-ink-muted">
        Locally this is Dex — try <code>ada@collabhub.dev</code> with the password{' '}
        <code>collabhub</code>.
      </p>
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
      navigate(signedIn ? '/' : '/sign-in', { replace: true })
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

  if (state.status === 'loading') return <Loading />
  if (state.status === 'signedOut') return <Navigate to="/sign-in" replace />

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
    />
  )
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
      <Route path="/sign-in" element={<SignIn />} />
      <Route path="/auth/callback" element={<Callback />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
