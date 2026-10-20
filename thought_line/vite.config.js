import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Builds the generation progress line (ThoughtLine + React + motion +
// Hugeicons) into one script and stylesheet under
// webapp/js/vendor/thought-line/. The output is committed and loaded on
// demand by js/cabinet.js; rebuild with `npm install && npm run build` after
// changing src/.
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': '"production"' },
  build: {
    outDir: '../webapp/js/vendor/thought-line',
    emptyOutDir: true,
    sourcemap: false,
    lib: {
      entry: 'src/main.jsx',
      formats: ['iife'],
      name: 'SylvexThoughtLineBundle',
      fileName: () => 'thought-line.js'
    },
    rollupOptions: { output: { assetFileNames: 'thought-line[extname]' } }
  }
});
