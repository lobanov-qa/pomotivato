/**
 * Vitest configuration (spec 03 §8): jsdom + testing-library.
 *
 * The "test" block lives here rather than package.json so the environment
 * and setup file are typed; vite's own build config stays in vite.config.ts.
 */

import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
