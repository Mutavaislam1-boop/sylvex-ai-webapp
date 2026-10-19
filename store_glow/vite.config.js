import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Builds the Store cards' glowing border (React Bits BorderGlow + React)
// into one script and stylesheet under webapp/js/vendor/store-glow/. The
// output is committed (and copied to sylvex-website/js/vendor/store-glow/),
// like store_lanyard; rebuild with `npm install && npm run build` after
// changing src/.
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': '"production"' },
  build: {
    outDir: '../webapp/js/vendor/store-glow',
    emptyOutDir: true,
    sourcemap: false,
    lib: {
      entry: 'src/main.jsx',
      formats: ['iife'],
      name: 'SylvexStoreGlowBundle',
      fileName: () => 'store-glow.js'
    },
    rollupOptions: { output: { assetFileNames: 'store-glow[extname]' } }
  }
});
