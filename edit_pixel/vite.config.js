import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Builds the Edit workspace's photo upload card (React Bits PixelCard +
// React) into one script and stylesheet under webapp/js/vendor/edit-pixel/.
// The output is committed and loaded on demand by js/cabinet.js; rebuild
// with `npm install && npm run build` after changing src/.
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': '"production"' },
  build: {
    outDir: '../webapp/js/vendor/edit-pixel',
    emptyOutDir: true,
    sourcemap: false,
    lib: {
      entry: 'src/main.jsx',
      formats: ['iife'],
      name: 'SylvexEditPixelBundle',
      fileName: () => 'edit-pixel.js'
    },
    rollupOptions: { output: { assetFileNames: 'edit-pixel[extname]' } }
  }
});
