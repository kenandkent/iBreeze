import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 51421,
    strictPort: true,
    proxy: {
      '/admin/api': {
        target: 'http://127.0.0.1:51080',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:51080',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
});
