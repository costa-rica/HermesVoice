import { defineConfig } from 'vite'

export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8700',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:8700',
        changeOrigin: true,
      },
      '/login': {
        target: 'http://127.0.0.1:8700',
        changeOrigin: true,
      },
      '/logout': {
        target: 'http://127.0.0.1:8700',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8700',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
