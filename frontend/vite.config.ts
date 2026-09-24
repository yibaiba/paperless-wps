import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiTarget = process.env.PRESALES_API_TARGET ?? 'http://127.0.0.1:8016';

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': apiTarget, '/diagram-editor': 'http://127.0.0.1:8086' } },
  preview: { proxy: { '/api': apiTarget, '/diagram-editor': 'http://127.0.0.1:8086' } },
});
