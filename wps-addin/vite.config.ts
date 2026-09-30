import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    strictPort: true,
    proxy: { '/api': process.env.PRESALES_API_TARGET ?? 'http://127.0.0.1:8016' },
  },
  preview: {
    proxy: { '/api': process.env.PRESALES_API_TARGET ?? 'http://127.0.0.1:8016' },
  },
  build: {
    rollupOptions: {
      input: { index: 'index.html', taskpane: 'taskpane.html', inline: 'inline.html' },
    },
  },
});
