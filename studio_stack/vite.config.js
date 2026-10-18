import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Builds Pro Studio's reference stack (React Bits Stack + React + motion)
// into one script and stylesheet under webapp/js/vendor/ref-stack/. The
// build output is committed, like store_lanyard and admin_console/dist, so
// the Railway Python image needs no Node step; rebuild with
// `npm install && npm run build` after changing src/.
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': '"production"' },
  build: {
    outDir: '../webapp/js/vendor/ref-stack',
    emptyOutDir: true,
    sourcemap: false,
    lib: {
      entry: 'src/main.jsx',
      formats: ['iife'],
      name: 'SylvexRefStackBundle',
      fileName: () => 'ref-stack.js'
    },
    rollupOptions: { output: { assetFileNames: 'ref-stack[extname]' } }
  }
});
