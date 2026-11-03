import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite configuration for the MAD management webapp.
//
// - `@`      -> src/            (ergonomic absolute imports)
// - `@icons` -> ../shared/icons (single source of role/topology SVGs, shared
//   with the website; see Req 6.7 / 13.4). Consuming the shared icons via an
//   alias avoids duplicating the SVGs in the frontend tree.
//
// The Vitest config lives in `vitest.config.ts` so this file keeps Vite's own
// `defineConfig` typing (mixing the two `defineConfig` overloads trips up the
// type checker because Vitest ships a nested copy of Vite).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@icons": path.resolve(__dirname, "../shared/icons"),
    },
  },
  server: {
    port: 5173,
  },
});
