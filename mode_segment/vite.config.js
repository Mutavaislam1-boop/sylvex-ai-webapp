import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Builds Pro Studio's mode switch (React Bits RubberSegment + React +
// motion) into one script and stylesheet under webapp/js/vendor/mode-segment/.
// The output is committed and loaded on demand by js/cabinet.js; rebuild
// with `npm install && npm run build` after changing src/.
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': '"production"' },
  build: {
    outDir: '../webapp/js/vendor/mode-segment',
    emptyOutDir: true,
    sourcemap: false,
    lib: {
      entry: 'src/main.jsx',
      formats: ['iife'],
      name: 'SylvexModeSegmentBundle',
      fileName: () => 'mode-segment.js'
    },
    rollupOptions: { output: { assetFileNames: 'mode-segment[extname]' } }
  }
});
