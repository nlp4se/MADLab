// @ts-check
import { defineConfig } from "astro/config";
import { fileURLToPath } from "node:url";

// Astro static documentation site (Req 13.1).
//
// Output is a fully static `dist/` with no runtime dependency on the backend or
// frontend: the taxonomy catalog is imported from a committed build-time
// snapshot (`src/data/taxonomy.json`) and the shared role/topology SVGs are
// consumed from the single source of truth at `../shared/icons` via the
// `@icons` alias — the same alias the frontend uses (see frontend/vite.config.ts),
// so the website and frontend share one icon source (Req 13.4 groundwork).
export default defineConfig({
  // Pure static build (prerendered); no SSR adapter so it can be deployed to
  // any static host independently of the other components (Req 13.1).
  output: "static",
  // The site/base can be overridden per deploy target; left root-relative here.
  vite: {
    resolve: {
      alias: {
        "@icons": fileURLToPath(new URL("../shared/icons", import.meta.url)),
        "@data": fileURLToPath(new URL("./src/data", import.meta.url)),
      },
    },
  },
});
