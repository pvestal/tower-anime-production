import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/anime/',
  server: {
    host: '0.0.0.0',  // Listen on all network interfaces
    port: 5173,
    allowedHosts: ['tower.local', '192.168.50.135', 'localhost', '.duckdns.org'],
    proxy: {
      '/api': {
        target: 'http://localhost:8328',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: '../static/dist',
    emptyOutDir: true
  }
})
