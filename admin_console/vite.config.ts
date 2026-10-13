import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served by the webapp at /admin/ (FastAPI route in main.py). The built
// dist/ is committed so the Railway Python image needs no Node build step;
// rebuild with `npm run build` after changing src/.
export default defineConfig({
  base: "/admin/",
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
  server: { proxy: { "/api": "http://localhost:8000", "/health": "http://localhost:8000" } },
});
