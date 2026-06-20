import { defineConfig } from "vite";

// API base is injected from VITE_API_BASE (08_conventions §3) — never hardcoded.
export default defineConfig({
  root: "src",
  build: { outDir: "../dist", emptyOutDir: true },
  define: {
    "window.__VITE_API_BASE__": JSON.stringify(process.env.VITE_API_BASE || ""),
  },
  server: { port: 1420, strictPort: true },
});
