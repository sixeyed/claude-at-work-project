import { useEffect } from 'react'
import { Navigate, Route, Routes, useNavigate, useSearchParams } from 'react-router-dom'

import * as session from './lib/auth/session'
import { useSession } from './lib/auth/useSession'

/**
 * Scaffold shell, now with a real sign-in.
 *
 * Federated login against Dex works end to end (register D5), which is enough to
 * prove the flow in a browser. Everything else in docs/design/06-frontend-spa.md
 * §3 — the feature folders, /lib/realtime, /lib/yjs — is still to come, and the
 * decisions it waits on are still open: the state manager (D24), the canvas
 * renderer (D21) and refresh-token storage (D22).
 */

function SignIn() {
  const state = useSession()

  if (state.status === 'signedIn') return <Navigate to="/" replace />

  return (
    <>
      <p>Sign in with your CollabHub account.</p>
      {state.status === 'signedOut' && state.error && <p role="alert">{state.error}</p>}
      <button type="button" onClick={() => void session.signIn()}>
        Sign in
      </button>
      <p>
        <small>
          Locally this is Dex — try <code>ada@collabhub.dev</code> with the password{' '}
          <code>collabhub</code>.
        </small>
      </p>
    </>
  )
}

/**
 * Where the Auth service sends the browser once identity is established.
 *
 * The code in the query string is spent exactly once. React 18's StrictMode runs
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

  return <p>Signing you in…</p>
}

function Home() {
  const state = useSession()

  if (state.status === 'loading') return <p>Loading…</p>
  if (state.status === 'signedOut') return <Navigate to="/sign-in" replace />

  const { profile, workspaces, activeWorkspaceId } = state.session

  return (
    <>
      <p>
        Signed in as <strong>{profile.displayName}</strong> ({profile.email}).
      </p>

      <h2>Workspaces</h2>
      <ul>
        {workspaces.map((workspace) => (
          <li key={workspace.id}>
            <button
              type="button"
              onClick={() => void session.changeWorkspace(workspace.id)}
              disabled={workspace.id === activeWorkspaceId}
            >
              {workspace.name}
            </button>{' '}
            <small>
              {workspace.role}
              {workspace.id === activeWorkspaceId && ' — active'}
            </small>
          </li>
        ))}
      </ul>
      <p>
        <small>
          Switching exchanges the refresh token for one scoped to that workspace
          (Conventions §5.4).
        </small>
      </p>

      <button type="button" onClick={() => void session.signOut()}>
        Sign out
      </button>
    </>
  )
}

function NotFound() {
  return <p>No such page.</p>
}

export function App() {
  useEffect(() => {
    void session.restore()
  }, [])

  return (
    <main>
      <h1>CollabHub</h1>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/sign-in" element={<SignIn />} />
        <Route path="/auth/callback" element={<Callback />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </main>
  )
}
