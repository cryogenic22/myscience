import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@mz/design-tokens': path.resolve(__dirname, '../../packages/design-tokens/src'),
      '@mz/ui':            path.resolve(__dirname, '../../packages/ui/src'),
    },
  },
  server: { port: 5173, strictPort: false },
});
