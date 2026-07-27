import { Link, Route, Routes } from 'react-router-dom'

/**
 * Scaffold shell.
 *
 * The structure in docs/design/06-frontend-spa.md §3 — /lib/api, /lib/realtime,
 * /lib/auth, /lib/yjs and the feature folders — is not built yet, and neither are
 * the decisions it depends on: the state manager (register D24), the canvas
 * renderer (D21) and refresh-token storage (D22) are all still open, so no
 * library that would settle them is installed.
 */

const SERVICES = [
  { name: 'Auth', url: import.meta.env.VITE_AUTH_URL },
  { name: 'Messaging', url: import.meta.env.VITE_MESSAGING_URL },
  { name: 'Canvas', url: import.meta.env.VITE_CANVAS_URL },
  { name: 'Asset', url: import.meta.env.VITE_ASSET_URL },
]

function Home() {
  return (
    <>
      <p>
        The scaffold is up. Nothing below is wired to a backend yet — these are the
        service URLs baked into this build.
      </p>
      <ul>
        {SERVICES.map((service) => (
          <li key={service.name}>
            <strong>{service.name}</strong> <code>{service.url ?? 'unset'}</code>
          </li>
        ))}
      </ul>
    </>
  )
}

function NotFound() {
  return <p>No such page.</p>
}

export function App() {
  return (
    <main>
      <h1>CollabHub</h1>
      <nav>
        <Link to="/">Home</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </main>
  )
}
