import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发端口 8090,/api 代理到后端 8000
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 8090,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
