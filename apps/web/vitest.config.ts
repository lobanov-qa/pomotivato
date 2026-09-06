/**
 * Vitest configuration (spec 03 §8): jsdom + testing-library.
 *
 * The "test" block lives here rather than package.json so the environment
 * and setup file are typed; vite's own build config stays in vite.config.ts.
 */

import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
