import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Builds the app's notices (React Bits SwipeToast + React + motion) into one
// script and stylesheet under webapp/js/vendor/swipe-toast/. The output is
// committed and loaded on the first notice by js/ui.js; rebuild with
// `npm install && npm run build` after changing src/.
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': '"production"' },
  build: {
    outDir: '../webapp/js/vendor/swipe-toast',
    emptyOutDir: true,
    sourcemap: false,
    lib: {
      entry: 'src/main.jsx',
      formats: ['iife'],
      name: 'SylvexSwipeToastBundle',
      fileName: () => 'swipe-toast.js'
    },
    rollupOptions: { output: { assetFileNames: 'swipe-toast[extname]' } }
  }
});
