import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      // Two pages from one build: the tenant app and the platform console
      // (served on its own subdomain by its own process, platform_main.py).
      input: {
        main: resolve(__dirname, 'index.html'),
        platform: resolve(__dirname, 'platform.html'),
      },
    },
  },
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      // dev: open http://127.0.0.1:5173/platform.html (console API on :8001)
      '/api/platform': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/uploads': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
