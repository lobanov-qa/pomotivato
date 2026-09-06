import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// Dev proxy: the browser talks same-origin, so no CORS noise while the
// server runs on :8000 (spec 03 §8). SSE streams pass through unchanged.
// fileURLToPath (not URL.pathname) — the repo path contains Cyrillic, which
// pathname percent-encodes and vite then cannot resolve (lesson of E3).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
