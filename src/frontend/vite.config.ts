import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  // Tailwind v4 is a Vite plugin rather than a PostCSS pipeline — no
  // tailwind.config.js and no postcss.config.js; the theme lives in index.css.
  plugins: [react(), tailwindcss()],
  server: {
    // host: true so the dev server is reachable from outside a container.
    host: true,
    port: 5173,
  },
})
