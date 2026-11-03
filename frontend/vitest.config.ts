import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Vitest configuration (kept separate from `vite.config.ts` — see the note
// there). Mirrors the `@`/`@icons` aliases so tests resolve imports the same
// way the app build does, and wires the jsdom harness + RTL setup file.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@icons": path.resolve(__dirname, "../shared/icons"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
