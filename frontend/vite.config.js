import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  base: '/anime/',
  server: {
    port: 5173,
    host: '0.0.0.0',
    cors: true,
    allowedHosts: [
      'vestal-garcia.duckdns.org',
      'tower.local',
      '192.168.50.135',
      'localhost',
      '.duckdns.org'
    ],
    hmr: {
      host: 'vestal-garcia.duckdns.org',
      protocol: 'wss'
    },
    proxy: {
      '/anime-studio/api': {
        target: 'http://localhost:8328',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/anime-studio/, '')
      },
      '/anime-studio/images': {
        target: 'http://localhost:8328',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/anime-studio/, '')
      }
    }
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  }
})
