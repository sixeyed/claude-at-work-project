import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // host: true so the dev server is reachable from outside a container.
    host: true,
    port: 5173,
  },
})
