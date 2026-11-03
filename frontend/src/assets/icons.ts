/**
 * Shared role + topology SVG icons (Reqs 6.7, 13.4).
 *
 * The single source of truth for these icons lives in `shared/icons/` at the
 * repo root (shared with the website). The frontend consumes them via the
 * `@icons` Vite alias (configured in `vite.config.ts`) and `import.meta.glob`,
 * which eagerly collects every SVG's resolved URL at build time. No copies are
 * kept in the frontend tree, so editing an icon in `shared/icons/` updates both
 * consumers.
 *
 * `roleIconUrl("debater")` / `topologyIconUrl("chain")` return the bundled URL
 * for use as an `<img src>` or a background image.
 */

// `import.meta.glob` with `{ eager, query: '?url', import: 'default' }` yields a
// record of module path -> resolved asset URL.
const roleModules = import.meta.glob<string>("@icons/role/*.svg", {
  eager: true,
  query: "?url",
  import: "default",
});

const topologyModules = import.meta.glob<string>("@icons/topology/*.svg", {
  eager: true,
  query: "?url",
  import: "default",
});

function indexByBasename(
  modules: Record<string, string>,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [filePath, url] of Object.entries(modules)) {
    const file = filePath.split("/").pop() ?? filePath;
    const name = file.replace(/\.svg$/, "");
    out[name] = url;
  }
  return out;
}

export const ROLE_ICONS: Record<string, string> = indexByBasename(roleModules);
export const TOPOLOGY_ICONS: Record<string, string> =
  indexByBasename(topologyModules);

/** Known role icon keys shipped in `shared/icons/role`. */
export type RoleIconName =
  | "debater"
  | "judge"
  | "summarizer"
  | "leader"
  | "verifier"
  | "editor";

/** Known topology icon keys shipped in `shared/icons/topology`. */
export type TopologyIconName =
  | "chain"
  | "ring"
  | "star"
  | "tree"
  | "layered"
  | "sparse"
  | "bipartite"
  | "fully_connected";

/** Resolve a role icon URL by key (e.g. "debater"); undefined if unknown. */
export function roleIconUrl(name: string): string | undefined {
  return ROLE_ICONS[name];
}

/** Resolve a topology icon URL by key (e.g. "chain"); undefined if unknown. */
export function topologyIconUrl(name: string): string | undefined {
  return TOPOLOGY_ICONS[name];
}
