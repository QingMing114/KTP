/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const apiProxyTarget = loadEnv(mode, '.', '').VITE_API_PROXY_TARGET || 'http://127.0.0.1:8005'

  return {
    plugins: [react()],
    server: {
      port: 3000,
      open: true,
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
          configure: (proxy) => {
            proxy.on('proxyRes', (proxyRes) => {
              if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
                proxyRes.headers['cache-control'] = 'no-cache'
                proxyRes.headers['x-accel-buffering'] = 'no'
              }
            })
          },
        },
        '/v2': {
          target: apiProxyTarget,
          changeOrigin: true,
          configure: (proxy) => {
            proxy.on('proxyRes', (proxyRes) => {
              if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
                proxyRes.headers['cache-control'] = 'no-cache'
                proxyRes.headers['x-accel-buffering'] = 'no'
              }
            })
          },
        },
        '/chat': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
        '/health': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
        '/detect': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      sourcemap: false,
      minify: 'terser',
      terserOptions: {
        compress: {
          drop_console: true,
          drop_debugger: true,
        },
        mangle: {
          toplevel: true,
        },
      },
      rollupOptions: {
        output: {
          manualChunks: {
            'vendor-react': ['react', 'react-dom', 'react-router-dom'],
            'vendor-markdown': ['react-markdown', 'remark-gfm', 'react-syntax-highlighter'],
            'vendor-icons': ['lucide-react'],
          },
        },
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      css: true,
    },
  }
})
