import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Builds the store's 3D subscription card (React Bits Lanyard + React +
// three.js) into one self-contained script and stylesheet under
// webapp/js/vendor/store-lanyard/. The build output is committed, like
// admin_console/dist, so the Railway Python image needs no Node step;
// rebuild with `npm install && npm run build` after changing src/.
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': '"production"' },
  build: {
    outDir: '../webapp/js/vendor/store-lanyard',
    emptyOutDir: true,
    sourcemap: false,
    lib: {
      entry: 'src/main.jsx',
      formats: ['iife'],
      name: 'SylvexLanyardBundle',
      fileName: () => 'store-lanyard.js'
    },
    rollupOptions: { output: { assetFileNames: 'store-lanyard[extname]' } }
  }
});
