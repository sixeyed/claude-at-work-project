import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { App } from './App.tsx'
import { ProblemError } from './lib/api/client.ts'
import './index.css'

const root = document.getElementById('root')
if (!root) {
  throw new Error('#root is missing from index.html')
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A 4xx is the server's considered answer, not a blip — retrying a 404 or
      // a 403 just delays showing the user what it already said. Retry the rest
      // once, for a genuinely dropped connection.
      retry: (failureCount, error) => {
        if (error instanceof ProblemError && error.status < 500) return false
        return failureCount < 1
      },
    },
    mutations: { retry: false },
  },
})

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
