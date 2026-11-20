import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  build: {
    // Element Plus 整体作为独立 vendor 分块（~940KB），属预期体积
    chunkSizeWarningLimit: 1000,
    // 依赖分包：Vue 运行时、Element Plus、地区数据各自独立，利于长期缓存
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ['vue', 'vue-router'],
          'element-plus': ['element-plus'],
          'area-data': ['element-china-area-data'],
        },
      },
    },
  },
  server: {
    port: 5173,
    // 开发环境代理：/api 与 /static（商品实物图）转发到后端，避免跨域
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
