import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/cache': 'http://127.0.0.1:5000',
      '/backend': 'http://127.0.0.1:5000',
      '/backends': 'http://127.0.0.1:5000',
      '/health': 'http://127.0.0.1:5000',
      '/stats': 'http://127.0.0.1:5000',
      '/benchmark': 'http://127.0.0.1:5000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.js',
  },
});
