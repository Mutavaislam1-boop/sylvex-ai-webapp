import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Builds the Grid Mode side panel (React Bits Dock + React) into one script
// and stylesheet under webapp/js/vendor/grid-dock/. The output is committed
// and loaded on demand by js/cabinet.js; rebuild with
// `npm install && npm run build` after changing src/.
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': '"production"' },
  build: {
    outDir: '../webapp/js/vendor/grid-dock',
    emptyOutDir: true,
    sourcemap: false,
    lib: {
      entry: 'src/main.jsx',
      formats: ['iife'],
      name: 'SylvexGridDockBundle',
      fileName: () => 'grid-dock.js'
    },
    rollupOptions: { output: { assetFileNames: 'grid-dock[extname]' } }
  }
});
