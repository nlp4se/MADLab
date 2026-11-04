/**
 * UI-only node layout side-channel (task 8.3, persisted since task 11.4).
 *
 * Node positions are not part of the participant schema (no `x`/`y` on a
 * node). While editing, the designer keeps a `LayoutMap` (node id -> {x, y})
 * in the Zustand store; on Save it is written into the artifact's optional,
 * presentation-only `ui.nodes` (ignored by the engine), and `loadArtifact`
 * seeds the map from it via `seedLayout`.
 *
 * `autoLayout` arranges nodes on a circle — deterministic, dependency-free, and
 * good enough for a readable default that the user can then drag around.
 */

export interface XYPosition {
  x: number;
  y: number;
}

export type LayoutMap = Record<string, XYPosition>;

const CENTER: XYPosition = { x: 360, y: 260 };
const RADIUS = 220;

/**
 * Arrange `nodeIds` evenly on a circle around a fixed center. A single node is
 * placed at the center. Order is preserved so the layout is stable for a given
 * node ordering (useful for tests and for chain/ring readability).
 */
export function autoLayout(nodeIds: string[]): LayoutMap {
  const layout: LayoutMap = {};
  const n = nodeIds.length;
  if (n === 0) return layout;
  if (n === 1) {
    layout[nodeIds[0]] = { ...CENTER };
    return layout;
  }
  nodeIds.forEach((id, index) => {
    const angle = (2 * Math.PI * index) / n - Math.PI / 2;
    layout[id] = {
      x: Math.round(CENTER.x + RADIUS * Math.cos(angle)),
      y: Math.round(CENTER.y + RADIUS * Math.sin(angle)),
    };
  });
  return layout;
}

/**
 * Ensure every node id has a position, auto-placing any that are missing while
 * preserving positions that already exist. Positions for ids no longer present
 * are dropped so the layout map never leaks stale nodes.
 */
export function reconcileLayout(
  nodeIds: string[],
  existing: LayoutMap,
): LayoutMap {
  const missing = nodeIds.filter((id) => existing[id] === undefined);
  const generated = missing.length > 0 ? autoLayout(nodeIds) : {};
  const next: LayoutMap = {};
  for (const id of nodeIds) {
    next[id] = existing[id] ?? generated[id] ?? { ...CENTER };
  }
  return next;
}

/**
 * Build the layout for `nodeIds` from stored positions (e.g. `artifact.ui.nodes`),
 * auto-placing ONLY participants without a stored position. `extraIds` (the
 * Start/End sentinels) are copied when stored and otherwise left out, so the
 * canvas falls back to their computed default placement. Unknown keys and
 * malformed points are ignored.
 */
export function seedLayout(
  nodeIds: string[],
  stored: Record<string, unknown> | null | undefined,
  extraIds: string[] = [],
): LayoutMap {
  const valid = (p: unknown): p is XYPosition =>
    typeof p === "object" &&
    p !== null &&
    Number.isFinite((p as XYPosition).x) &&
    Number.isFinite((p as XYPosition).y);
  const src = stored ?? {};
  const generated = nodeIds.some((id) => !valid(src[id])) ? autoLayout(nodeIds) : {};
  const next: LayoutMap = {};
  for (const id of nodeIds) {
    const p = src[id];
    next[id] = valid(p) ? { x: p.x, y: p.y } : (generated[id] ?? { ...CENTER });
  }
  for (const id of extraIds) {
    const p = src[id];
    if (valid(p)) next[id] = { x: p.x, y: p.y };
  }
  return next;
}
