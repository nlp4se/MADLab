/**
 * UI-only node layout side-channel (task 8.3, persisted since task 11.4) and
 * the flow-aware auto layout (task 11.8).
 *
 * Node positions are not part of the participant schema (no `x`/`y` on a
 * node). While editing, the designer keeps a `LayoutMap` (node id -> top-left
 * {x, y}, incl. the Start/End sentinels) in the Zustand store; on Save it is
 * written into the artifact's optional, presentation-only `ui.nodes` (ignored
 * by the engine), and `loadArtifact` seeds the map from it via `seedLayout`.
 *
 * `autoLayout` is a dependency-free layered (Sugiyama-style) layout over the
 * whole canvas graph, Start and End included:
 *   1. Strongly connected components of the participant edges are condensed
 *      (a fully connected or ring debate is ONE component) so the rest is a DAG.
 *   2. Ranks = longest path from Start (Start = rank 0, End = last rank).
 *      Components nobody feeds (e.g. a judge-only node) are pulled right, next
 *      to what they feed, so judges/summarizers sit by their connections.
 *   3. Each multi-node component becomes a compact cluster: two nodes stacked,
 *      three or more on an ellipse just large enough that no intra-cluster
 *      edge (with its reciprocal bow) runs through another member's box.
 *   4. Barycenter sweeps (down/up, best kept) order each rank to reduce
 *      crossings; ranks become columns spaced from the real node sizes.
 *   5. Edge clearance: every rendered curve (same bezier/attachment model as
 *      `FloatingEdge`, see `edgeGeometry.ts`) that passes through a non-endpoint
 *      node box gets the smallest bend that routes it around; reciprocal pairs
 *      move together and keep their separation. Column gaps grow with the
 *      steepest edge between them so adjacent-column edges leave/enter nodes
 *      through their sides rather than through stacked neighbours.
 *   6. Repair: if a single bend cannot clear an edge (a long edge lined up
 *      with a node boxed in by its column neighbours), the blocking column is
 *      slid up/down (bounded search) while that reduces the remaining hits.
 *
 * Deterministic: no randomness, ties always broken by declaration order.
 */
import type { MADArtifact, ParticipantNodeArtifact } from "./artifact";
import {
  floatingEdgeGeometry,
  polylineHitsRect,
  RECIPROCAL_OFFSET,
  reciprocalOffset,
  rectCenter,
  sampleEdgeCurve,
  type Rect,
} from "./edgeGeometry";
import {
  effectiveEntryNodeIds,
  effectiveExitNodeIds,
  entryConnectorId,
  exitConnectorId,
} from "./ioNodes";
import { END_NODE_ID, START_NODE_ID } from "./StartEndNodes";

export interface XYPosition {
  x: number;
  y: number;
}

export type LayoutMap = Record<string, XYPosition>;

/** Edge id -> knob offset from the centres' midpoint (see `edgeGeometry.ts`). */
export type BendMap = Record<string, XYPosition>;

export interface NodeSize {
  width: number;
  height: number;
}

/** Node id -> rendered size (React Flow's measured width/height). */
export type NodeSizeMap = Record<string, NodeSize>;

/* ------------------------------ node sizes ------------------------------ */

/** `ParticipantNode`: `min-w-[200px]`, border-2, py-3, 36px icon row + badge. */
export const PARTICIPANT_MIN_WIDTH = 200;
export const PARTICIPANT_HEIGHT = 96;
const PARTICIPANT_MAX_WIDTH = 420;
/** `StartNode` / `EndNode`: rounded pill, px-3 py-2, 16px icon + text-sm label. */
export const START_SIZE: NodeSize = { width: 90, height: 40 };
export const END_SIZE: NodeSize = { width: 80, height: 40 };

const CENTER: XYPosition = { x: 360, y: 260 };

/** Minimum gap between any two node boxes. */
export const NODE_GAP = 40;
/** Vertical gap between stacked items of one rank (room for edges to pass). */
const ITEM_GAP = 60;
/** Base horizontal gap between rank columns. */
const RANK_GAP = 110;
/** Minimum centre dx / dy of an edge between adjacent columns. */
const STEEPNESS = 1.1;
/** Clearance a routed edge keeps from non-endpoint boxes. */
export const EDGE_CLEARANCE = 10;
/** Samples per curve for the hit tests. */
const CURVE_SEGMENTS = 40;

/**
 * Size estimate for a participant node before React Flow has measured it,
 * mirroring `ParticipantNode`: the box grows with its label / model badge
 * (it is shrink-to-fit with a 200px minimum).
 */
export function estimateParticipantSize(node: ParticipantNodeArtifact): NodeSize {
  const label = node.label ?? "";
  const roles = (node.roles ?? []).join(", ") || "debater";
  const model = node.base_model?.model_key ?? "no model";
  const provider = node.base_model?.provider_id ? `#${node.base_model.provider_id} · ` : "";
  // padding + border + icon + gap, then the widest text line (15px / 11px).
  const header = 28 + 36 + 10 + Math.max(label.length * 8.4, roles.length * 6.2);
  const badge = 28 + 18 + (provider.length + model.length) * 6.2;
  const width = Math.min(
    PARTICIPANT_MAX_WIDTH,
    Math.max(PARTICIPANT_MIN_WIDTH, Math.ceil(header), Math.ceil(badge)),
  );
  return { width, height: PARTICIPANT_HEIGHT };
}

function validSize(s: unknown): s is NodeSize {
  const v = s as NodeSize | null;
  return (
    typeof v === "object" &&
    v !== null &&
    Number.isFinite(v.width) &&
    Number.isFinite(v.height) &&
    v.width > 0 &&
    v.height > 0
  );
}

/**
 * Size of every canvas node (participants + Start/End): the measured size when
 * a valid one is given, else the rendering-matched estimate.
 */
export function nodeSizes(
  artifact: MADArtifact,
  measured?: NodeSizeMap | null,
): NodeSizeMap {
  const m = measured ?? {};
  const pick = (id: string, fallback: NodeSize): NodeSize => {
    const s = m[id];
    return validSize(s) ? { width: s.width, height: s.height } : fallback;
  };
  const sizes: NodeSizeMap = {};
  for (const node of artifact.participants.nodes) {
    sizes[node.id] = pick(node.id, estimateParticipantSize(node));
  }
  sizes[START_NODE_ID] = pick(START_NODE_ID, START_SIZE);
  sizes[END_NODE_ID] = pick(END_NODE_ID, END_SIZE);
  return sizes;
}

/* ------------------------------ canvas edges ------------------------------ */

export interface LayoutEdge {
  /** Canvas edge id (`source->target`, or a Start/End connector id). */
  id: string;
  source: string;
  target: string;
  /** The reverse participant edge exists (rendered as a ±30px bowed pair). */
  reciprocal: boolean;
  kind: "edge" | "entry" | "exit";
}

/**
 * Every edge the canvas draws: participant edges (as `toFlowEdges`, minus
 * self-loops, duplicates and dangling refs) plus the Start/End connectors
 * (as `toStartEndEdges`).
 */
export function layoutEdges(artifact: MADArtifact): LayoutEdge[] {
  const known = new Set(artifact.participants.nodes.map((n) => n.id));
  if (known.size === 0) return [];
  const real: Array<{ id: string; source: string; target: string }> = [];
  const seen = new Set<string>();
  for (const e of artifact.interaction.topology.edges) {
    if (!known.has(e.source) || !known.has(e.target) || e.source === e.target) continue;
    // Same id format as `edgeId` in designerStore (not imported: no cycle).
    const id = `${e.source}->${e.target}`;
    if (seen.has(id)) continue;
    seen.add(id);
    real.push({ id, source: e.source, target: e.target });
  }
  return [
    ...real.map((e) => ({
      ...e,
      reciprocal: seen.has(`${e.target}->${e.source}`),
      kind: "edge" as const,
    })),
    ...effectiveEntryNodeIds(artifact).map((id) => ({
      id: entryConnectorId(id),
      source: START_NODE_ID,
      target: id,
      reciprocal: false,
      kind: "entry" as const,
    })),
    ...effectiveExitNodeIds(artifact).map((id) => ({
      id: exitConnectorId(id),
      source: id,
      target: END_NODE_ID,
      reciprocal: false,
      kind: "exit" as const,
    })),
  ];
}

/* ------------------------------ small helpers ------------------------------ */

const rectAt = (center: XYPosition, size: NodeSize): Rect => ({
  x: center.x - size.width / 2,
  y: center.y - size.height / 2,
  width: size.width,
  height: size.height,
});

const rectFromTopLeft = (p: XYPosition, size: NodeSize): Rect => ({
  x: p.x,
  y: p.y,
  width: size.width,
  height: size.height,
});

/** True when the two boxes are closer than `gap` on both axes. */
export function boxesOverlap(a: Rect, b: Rect, gap = 0): boolean {
  return !(
    a.x + a.width + gap <= b.x ||
    b.x + b.width + gap <= a.x ||
    a.y + a.height + gap <= b.y ||
    b.y + b.height + gap <= a.y
  );
}

interface Polyline {
  points: XYPosition[];
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

function polyline(points: XYPosition[]): Polyline {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const p of points) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  return { points, minX, maxX, minY, maxY };
}

function polylineHits(line: Polyline, rect: Rect, margin: number): boolean {
  if (
    line.maxX < rect.x - margin ||
    line.minX > rect.x + rect.width + margin ||
    line.maxY < rect.y - margin ||
    line.minY > rect.y + rect.height + margin
  ) {
    return false;
  }
  return polylineHitsRect(line.points, rect, margin);
}

/** The rendered curve of an edge, exactly as `FloatingEdge` draws it. */
function edgeCurve(
  sRect: Rect,
  tRect: Rect,
  bend: XYPosition | null,
  reciprocal: boolean,
  segments = CURVE_SEGMENTS,
): Polyline {
  const def = reciprocal ? reciprocalOffset(rectCenter(sRect), rectCenter(tRect)) : null;
  const geo = floatingEdgeGeometry(sRect, tRect, bend, def);
  return polyline(sampleEdgeCurve(geo, segments));
}

/** Coarse samples for screening bend candidates (re-checked at full detail). */
const COARSE_SEGMENTS = 14;

/* -------------------------- 1. components (SCC) -------------------------- */

/** Tarjan's SCCs; members in declaration order, components by first member. */
function stronglyConnected(ids: string[], succ: Map<string, string[]>): string[][] {
  const order = new Map(ids.map((id, i) => [id, i]));
  const index = new Map<string, number>();
  const low = new Map<string, number>();
  const onStack = new Set<string>();
  const stack: string[] = [];
  const comps: string[][] = [];
  let counter = 0;
  const visit = (v: string) => {
    index.set(v, counter);
    low.set(v, counter);
    counter += 1;
    stack.push(v);
    onStack.add(v);
    for (const w of succ.get(v) ?? []) {
      if (!index.has(w)) {
        visit(w);
        low.set(v, Math.min(low.get(v)!, low.get(w)!));
      } else if (onStack.has(w)) {
        low.set(v, Math.min(low.get(v)!, index.get(w)!));
      }
    }
    if (low.get(v) === index.get(v)) {
      const comp: string[] = [];
      let w: string;
      do {
        w = stack.pop()!;
        onStack.delete(w);
        comp.push(w);
      } while (w !== v);
      comps.push(comp);
    }
  };
  for (const id of ids) if (!index.has(id)) visit(id);
  for (const c of comps) c.sort((a, b) => order.get(a)! - order.get(b)!);
  comps.sort((a, b) => order.get(a[0])! - order.get(b[0])!);
  return comps;
}

/* --------------------------- 3. compact clusters --------------------------- */

interface Cluster {
  members: string[];
  /** Member centre offsets from the cluster's bounding-box centre. */
  offsets: Map<string, XYPosition>;
  width: number;
  height: number;
}

/** Wider than tall: participant boxes are ~2:1. */
const CLUSTER_ASPECT = 1.4;

function buildCluster(
  members: string[],
  sizes: NodeSizeMap,
  internal: LayoutEdge[],
): Cluster {
  const raw = new Map<string, XYPosition>();
  if (members.length === 1) {
    raw.set(members[0], { x: 0, y: 0 });
  } else if (members.length === 2) {
    // Stacked: the reciprocal pair bows sideways, visible from Start and End.
    const [a, b] = members;
    const total = sizes[a].height + sizes[b].height + ITEM_GAP;
    raw.set(a, { x: 0, y: -total / 2 + sizes[a].height / 2 });
    raw.set(b, { x: 0, y: total / 2 - sizes[b].height / 2 });
  } else {
    // Ellipse, declaration order clockwise from the left. Odd sizes put the
    // first member on the left (facing Start); even sizes leave the horizontal
    // axis free so Start/End see into the cluster through the side gaps.
    const k = members.length;
    const angles = members.map(
      (_, i) => Math.PI + (2 * Math.PI * i) / k + (k % 2 === 0 ? Math.PI / k : 0),
    );
    const at = (s: number) =>
      members.map((id, i) => ({
        id,
        c: { x: s * CLUSTER_ASPECT * Math.cos(angles[i]), y: s * Math.sin(angles[i]) },
      }));
    const fits = (s: number): boolean => {
      const pts = at(s);
      const rects = new Map(pts.map((p) => [p.id, rectAt(p.c, sizes[p.id])]));
      for (let i = 0; i < pts.length; i += 1) {
        for (let j = i + 1; j < pts.length; j += 1) {
          if (boxesOverlap(rects.get(pts[i].id)!, rects.get(pts[j].id)!, NODE_GAP)) {
            return false;
          }
        }
      }
      for (const e of internal) {
        const line = edgeCurve(rects.get(e.source)!, rects.get(e.target)!, null, e.reciprocal);
        for (const id of members) {
          if (id === e.source || id === e.target) continue;
          if (polylineHits(line, rects.get(id)!, EDGE_CLEARANCE + 6)) return false;
        }
      }
      return true;
    };
    let s = 80;
    for (let i = 0; i < 120 && !fits(s); i += 1) s *= 1.06;
    s = Math.ceil(s);
    for (const p of at(s)) raw.set(p.id, p.c);
  }
  // Re-centre on the bounding box.
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const id of members) {
    const r = rectAt(raw.get(id)!, sizes[id]);
    minX = Math.min(minX, r.x);
    maxX = Math.max(maxX, r.x + r.width);
    minY = Math.min(minY, r.y);
    maxY = Math.max(maxY, r.y + r.height);
  }
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const offsets = new Map<string, XYPosition>();
  for (const id of members) {
    const p = raw.get(id)!;
    offsets.set(id, { x: p.x - cx, y: p.y - cy });
  }
  return { members, offsets, width: maxX - minX, height: maxY - minY };
}

/* ------------------------- 2 + 4. ranks and order ------------------------- */

interface Layered {
  /** Rank of the End column (Start is rank 0). */
  endRank: number;
  /** Rank of every canvas node. */
  rankOf: Map<string, number>;
  /** Node centres, every column moved vertically by `shift[rank]`. */
  place: (shift: number[]) => Map<string, XYPosition>;
}

/** Ranks, clusters and in-rank order; node centres via `place`. */
function layeredCenters(
  artifact: MADArtifact,
  edges: LayoutEdge[],
  sizes: NodeSizeMap,
): Layered {
  const ids = artifact.participants.nodes.map((n) => n.id);
  const real = edges.filter((e) => e.kind === "edge");
  const succ = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const e of real) succ.get(e.source)!.push(e.target);

  const comps = stronglyConnected(ids, succ);
  const compOf = new Map<string, number>();
  comps.forEach((members, c) => members.forEach((id) => compOf.set(id, c)));
  const C = comps.length;

  // Condensed DAG (with multiplicities for the ordering heuristics).
  const cSucc: Array<Set<number>> = comps.map(() => new Set());
  const cPred: Array<Set<number>> = comps.map(() => new Set());
  const compEdges: Array<[number, number]> = [];
  const internal: LayoutEdge[][] = comps.map(() => []);
  for (const e of real) {
    const a = compOf.get(e.source)!;
    const b = compOf.get(e.target)!;
    if (a === b) {
      internal[a].push(e);
    } else {
      cSucc[a].add(b);
      cPred[b].add(a);
      compEdges.push([a, b]);
    }
  }
  const isEntry = new Set(edges.filter((e) => e.kind === "entry").map((e) => compOf.get(e.target)!));

  // Longest path from Start (Kahn, ties by component index).
  const indeg = cPred.map((p) => p.size);
  const ready: number[] = [];
  for (let c = 0; c < C; c += 1) if (indeg[c] === 0) ready.push(c);
  const topo: number[] = [];
  while (ready.length > 0) {
    ready.sort((a, b) => a - b);
    const c = ready.shift()!;
    topo.push(c);
    for (const s of cSucc[c]) {
      indeg[s] -= 1;
      if (indeg[s] === 0) ready.push(s);
    }
  }
  const rank = new Array<number>(C).fill(1);
  for (const c of topo) for (const s of cSucc[c]) rank[s] = Math.max(rank[s], rank[c] + 1);
  const fedRanks = comps.map((_, c) => c).filter((c) => cPred[c].size > 0 || isEntry.has(c));
  const maxFed = Math.max(1, ...fedRanks.map((c) => rank[c]));
  // Pull components nobody feeds (not Start, no participant) next to what they
  // feed, or next to End when they only feed End / nothing (judge-only nodes).
  for (let c = 0; c < C; c += 1) {
    if (cPred[c].size > 0 || isEntry.has(c)) continue;
    rank[c] =
      cSucc[c].size > 0 ? Math.min(...[...cSucc[c]].map((s) => rank[s])) - 1 : maxFed;
  }
  const maxRank = Math.max(1, ...rank);

  const clusters = comps.map((members, c) => buildCluster(members, sizes, internal[c]));

  // Layers 1..maxRank, initial order = declaration order.
  const layers: number[][] = Array.from({ length: maxRank + 1 }, () => []);
  for (let c = 0; c < C; c += 1) layers[rank[c]].push(c);

  const yOf = new Array<number>(C).fill(0);
  const assignY = (r: number) => {
    const layer = layers[r];
    const total =
      layer.reduce((sum, c) => sum + clusters[c].height, 0) +
      ITEM_GAP * Math.max(0, layer.length - 1);
    let y = -total / 2;
    for (const c of layer) {
      yOf[c] = y + clusters[c].height / 2;
      y += clusters[c].height + ITEM_GAP;
    }
  };
  for (let r = 1; r <= maxRank; r += 1) assignY(r);

  const nbrs: number[][] = comps.map(() => []);
  for (const [a, b] of compEdges) {
    nbrs[a].push(b);
    nbrs[b].push(a);
  }
  const reorder = (r: number, side: (nb: number) => boolean) => {
    const layer = layers[r];
    const keyed = layer.map((c, i) => {
      const ns = nbrs[c].filter(side);
      const bary = ns.length > 0 ? ns.reduce((s, n) => s + yOf[n], 0) / ns.length : yOf[c];
      return { c, i, bary };
    });
    keyed.sort((p, q) => p.bary - q.bary || p.i - q.i);
    layers[r] = keyed.map((k) => k.c);
    assignY(r);
  };
  const crossings = (): number => {
    const groups = new Map<string, Array<[number, number]>>();
    for (const [a, b] of compEdges) {
      const key = `${rank[a]}:${rank[b]}`;
      const g = groups.get(key) ?? [];
      g.push([a, b]);
      groups.set(key, g);
    }
    let count = 0;
    for (const g of groups.values()) {
      for (let i = 0; i < g.length; i += 1) {
        for (let j = i + 1; j < g.length; j += 1) {
          const [a1, b1] = g[i];
          const [a2, b2] = g[j];
          if ((yOf[a1] - yOf[a2]) * (yOf[b1] - yOf[b2]) < 0) count += 1;
        }
      }
    }
    return count;
  };
  let best = layers.map((l) => [...l]);
  let bestCross = crossings();
  for (let iter = 0; iter < 8 && bestCross > 0; iter += 1) {
    for (let r = 2; r <= maxRank; r += 1) reorder(r, (nb) => rank[nb] < r);
    for (let r = maxRank - 1; r >= 1; r -= 1) reorder(r, (nb) => rank[nb] > r);
    const cross = crossings();
    if (cross < bestCross) {
      bestCross = cross;
      best = layers.map((l) => [...l]);
    }
  }
  for (let r = 1; r <= maxRank; r += 1) {
    layers[r] = best[r];
    assignY(r);
  }

  // Columns: rank 0 = Start, maxRank + 1 = End, widths/heights from real sizes.
  const endRank = maxRank + 1;
  const colW: number[] = [];
  const colH: number[] = [];
  for (let r = 0; r <= endRank; r += 1) {
    if (r === 0) {
      colW.push(sizes[START_NODE_ID].width);
      colH.push(sizes[START_NODE_ID].height);
    } else if (r === endRank) {
      colW.push(sizes[END_NODE_ID].width);
      colH.push(sizes[END_NODE_ID].height);
    } else {
      const layer = layers[r];
      colW.push(Math.max(0, ...layer.map((c) => clusters[c].width)));
      colH.push(
        layer.reduce((s, c) => s + clusters[c].height, 0) +
          ITEM_GAP * Math.max(0, layer.length - 1),
      );
    }
  }
  const rankOf = new Map<string, number>();
  for (let c = 0; c < C; c += 1) {
    for (const id of clusters[c].members) rankOf.set(id, rank[c]);
  }
  rankOf.set(START_NODE_ID, 0);
  rankOf.set(END_NODE_ID, endRank);
  const entries = edges.filter((e) => e.kind === "entry").map((e) => e.target);
  const exits = edges.filter((e) => e.kind === "exit").map((e) => e.source);

  const place = (shift: number[]): Map<string, XYPosition> => {
    // Vertical centres (independent of x), each column moved by its shift;
    // Start/End at their neighbours' mean.
    const yCenter = new Map<string, number>();
    for (let c = 0; c < C; c += 1) {
      for (const id of clusters[c].members) {
        yCenter.set(id, yOf[c] + shift[rank[c]] + clusters[c].offsets.get(id)!.y);
      }
    }
    const meanY = (list: string[]) =>
      list.length > 0 ? list.reduce((s, id) => s + yCenter.get(id)!, 0) / list.length : 0;
    yCenter.set(START_NODE_ID, meanY(entries) + shift[0]);
    yCenter.set(END_NODE_ID, meanY(exits) + shift[endRank]);

    // Column spacing: an edge between adjacent columns can only leave/enter a
    // node through its side (instead of crossing its stacked neighbours) when
    // it is not too steep, so the gap grows with the largest vertical span.
    const maxDy = new Array<number>(endRank).fill(0);
    for (const e of edges) {
      const ra = rankOf.get(e.source)!;
      const rb = rankOf.get(e.target)!;
      if (Math.abs(ra - rb) !== 1) continue;
      const r = Math.min(ra, rb);
      maxDy[r] = Math.max(maxDy[r], Math.abs(yCenter.get(e.source)! - yCenter.get(e.target)!));
    }
    const colX: number[] = [0];
    for (let r = 1; r <= endRank; r += 1) {
      const halfWidths = colW[r - 1] / 2 + colW[r] / 2;
      const gap = Math.max(
        RANK_GAP + 0.1 * Math.max(colH[r - 1], colH[r]),
        STEEPNESS * maxDy[r - 1] - halfWidths,
      );
      colX.push(colX[r - 1] + halfWidths + gap);
    }

    const centers = new Map<string, XYPosition>();
    for (let c = 0; c < C; c += 1) {
      for (const id of clusters[c].members) {
        const o = clusters[c].offsets.get(id)!;
        centers.set(id, { x: colX[rank[c]] + o.x, y: yCenter.get(id)! });
      }
    }
    centers.set(START_NODE_ID, { x: colX[0], y: yCenter.get(START_NODE_ID)! });
    centers.set(END_NODE_ID, { x: colX[endRank], y: yCenter.get(END_NODE_ID)! });
    return centers;
  };
  return { endRank, rankOf, place };
}

/* ---------------------------- 5. edge clearance ---------------------------- */

interface Candidate {
  u: number; // along the edge direction
  v: number; // along its left normal
}

/** Knob shifts to try, cheapest first (perpendicular before along-edge). */
function candidates(length: number, preferPositive: boolean): Candidate[] {
  const vs: number[] = [0];
  for (let v = 10; v <= 200; v += 10) vs.push(v);
  for (let v = 220; v <= 600; v += 20) vs.push(v);
  for (let v = 640; v <= Math.max(800, 0.8 * length); v += 40) vs.push(v);
  const us = [0];
  for (const f of [0.1, 0.2, 0.3, 0.4]) us.push(f * length, -f * length);
  const out: Array<Candidate & { cost: number; order: number }> = [];
  let order = 0;
  for (const v of vs) {
    const signs = v === 0 ? [1] : preferPositive ? [1, -1] : [-1, 1];
    for (const sign of signs) {
      for (const u of us) {
        out.push({ u, v: sign * v, cost: v + 0.6 * Math.abs(u), order });
        order += 1;
      }
    }
  }
  out.sort((a, b) => a.cost - b.cost || a.order - b.order);
  return out.map(({ u, v }) => ({ u, v }));
}

const roundPt = (p: XYPosition): XYPosition => ({ x: Math.round(p.x), y: Math.round(p.y) });

/**
 * Bends for every edge whose rendered curve would pass through a node box it
 * does not connect. Edges that are already clear (straight, or the default
 * reciprocal bow) get no entry. When no single bend clears an edge, the one
 * with the fewest hits is kept.
 */
export function clearEdgeBends(
  edges: LayoutEdge[],
  positions: LayoutMap,
  sizes: NodeSizeMap,
): BendMap {
  return routeEdges(edges, positions, sizes).bends;
}

interface Routing {
  bends: BendMap;
  /** Node ids still crossed, per edge that no single bend could clear. */
  blocked: Array<{ edge: string; blockers: string[] }>;
  /** Total (edge, crossed node) pairs left. */
  hitCount: number;
}

function routeEdges(edges: LayoutEdge[], positions: LayoutMap, sizes: NodeSizeMap): Routing {
  const rects = new Map<string, Rect>();
  for (const [id, p] of Object.entries(positions)) {
    if (sizes[id]) rects.set(id, rectFromTopLeft(p, sizes[id]));
  }
  const byId = new Map(edges.map((e) => [e.id, e]));
  const bends: BendMap = {};
  const done = new Set<string>();

  const blocked: Routing["blocked"] = [];
  let hitCount = 0;
  const hits = (
    line: Polyline,
    skipA: string,
    skipB: string,
    limit: number,
    out?: string[],
  ): number => {
    let n = 0;
    for (const [id, r] of rects) {
      if (id === skipA || id === skipB) continue;
      if (polylineHits(line, r, EDGE_CLEARANCE)) {
        n += 1;
        out?.push(id);
        if (n >= limit) return n;
      }
    }
    return n;
  };
  /** Record what an edge still crosses with its final shape. */
  const recordBlocked = (
    id: string,
    sR: Rect,
    tR: Rect,
    bend: XYPosition | null,
    reciprocal: boolean,
    source: string,
    target: string,
  ) => {
    const ids: string[] = [];
    hits(edgeCurve(sR, tR, bend, reciprocal), source, target, Infinity, ids);
    if (ids.length > 0) {
      blocked.push({ edge: id, blockers: ids });
      hitCount += ids.length;
    }
  };

  for (const e of edges) {
    if (done.has(e.id)) continue;
    done.add(e.id);
    const sR = rects.get(e.source);
    const tR = rects.get(e.target);
    if (!sR || !tR) continue;
    const sc = rectCenter(sR);
    const tc = rectCenter(tR);
    const len = Math.hypot(tc.x - sc.x, tc.y - sc.y) || 1;
    const dir = { x: (tc.x - sc.x) / len, y: (tc.y - sc.y) / len };
    const nrm = { x: dir.y, y: -dir.x }; // left normal, as `reciprocalOffset`
    const partner = e.reciprocal ? byId.get(`${e.target}->${e.source}`) : undefined;
    if (partner) done.add(partner.id);

    // Default shape first (straight / reciprocal bow): no bend needed if clear.
    const lineA0 = edgeCurve(sR, tR, null, e.reciprocal);
    const lineB0 = partner ? edgeCurve(tR, sR, null, true) : null;
    let bestHits =
      hits(lineA0, e.source, e.target, Infinity) +
      (lineB0 ? hits(lineB0, e.source, e.target, Infinity) : 0);
    if (bestHits === 0) continue;

    let bestA: XYPosition | null = null;
    let bestB: XYPosition | null = null;
    const prefer = e.kind !== "exit";
    for (const cand of candidates(len, prefer)) {
      const c = { x: cand.u * dir.x + cand.v * nrm.x, y: cand.u * dir.y + cand.v * nrm.y };
      let total: number;
      let offA: XYPosition;
      let offB: XYPosition | null = null;
      // Screen with a coarse sampling, confirm at full detail.
      const score = (segments: number, limit: number): number => {
        let n = hits(edgeCurve(sR, tR, offA, !!partner, segments), e.source, e.target, limit);
        if (offB && n < limit) {
          n += hits(edgeCurve(tR, sR, offB, true, segments), e.source, e.target, limit - n);
        }
        return n;
      };
      if (partner) {
        // Move the pair together, keeping the ±30px separation.
        offA = roundPt({ x: c.x + RECIPROCAL_OFFSET * nrm.x, y: c.y + RECIPROCAL_OFFSET * nrm.y });
        offB = roundPt({ x: c.x - RECIPROCAL_OFFSET * nrm.x, y: c.y - RECIPROCAL_OFFSET * nrm.y });
      } else {
        offA = roundPt(c);
      }
      total = score(COARSE_SEGMENTS, bestHits);
      if (total < bestHits) total = score(CURVE_SEGMENTS, bestHits);
      if (total < bestHits) {
        bestHits = total;
        bestA = offA;
        bestB = offB;
        if (total === 0) break;
      }
    }
    if (bestA) {
      bends[e.id] = bestA;
      if (partner && bestB) bends[partner.id] = bestB;
    }
    if (bestHits > 0) {
      recordBlocked(e.id, sR, tR, bestA, e.reciprocal, e.source, e.target);
      if (partner) {
        recordBlocked(partner.id, tR, sR, bestB, true, e.source, e.target);
      }
    }
  }
  return { bends, blocked, hitCount };
}

/* ------------------------------- public API ------------------------------- */

export interface AutoLayoutResult {
  /** Top-left positions for every participant AND the Start/End sentinels. */
  positions: LayoutMap;
  /** Edge bends replacing all previous ones (only edges that need routing). */
  bends: BendMap;
}

/**
 * Lay out the whole canvas graph (see the module doc). `measured` are React
 * Flow's measured node sizes when available; otherwise sizes are estimated
 * from the node data. An artifact without participants yields an empty map
 * (the canvas then shows no Start/End either).
 */
export function autoLayout(
  artifact: MADArtifact,
  measured?: NodeSizeMap | null,
): AutoLayoutResult {
  if (artifact.participants.nodes.length === 0) return { positions: {}, bends: {} };
  const sizes = nodeSizes(artifact, measured);
  const edges = layoutEdges(artifact);
  const layered = layeredCenters(artifact, edges, sizes);
  const evaluate = (shift: number[]) => {
    const positions: LayoutMap = {};
    for (const [id, c] of layered.place(shift)) {
      const s = sizes[id];
      positions[id] = roundPt({ x: c.x - s.width / 2, y: c.y - s.height / 2 });
    }
    return { positions, routing: routeEdges(edges, positions, sizes) };
  };

  // Repair: when some edge cannot be routed around a box with a single bend
  // (e.g. a long edge whose straight path is lined up with a node and boxed in
  // by its column neighbours), slide that node's whole column up or down —
  // columns stay non-overlapping — and keep the shift if fewer crossings
  // remain. Bounded and deterministic.
  let shift = new Array<number>(layered.endRank + 1).fill(0);
  let best = evaluate(shift);
  let budget = REPAIR_BUDGET;
  for (let round = 0; round < REPAIR_ROUNDS && best.routing.hitCount > 0; round += 1) {
    let improved = false;
    const tried = new Set<number>();
    search: for (const { blockers } of best.routing.blocked) {
      for (const blocker of blockers) {
        const r = layered.rankOf.get(blocker)!;
        if (tried.has(r)) continue;
        tried.add(r);
        for (const delta of REPAIR_SHIFTS) {
          if (budget <= 0) break search;
          budget -= 1;
          const next = [...shift];
          next[r] += delta;
          const cand = evaluate(next);
          if (cand.routing.hitCount < best.routing.hitCount) {
            shift = next;
            best = cand;
            improved = true;
            break search;
          }
        }
      }
    }
    if (!improved) break;
  }
  return { positions: best.positions, bends: best.routing.bends };
}

const REPAIR_ROUNDS = 8;
/** Max layouts evaluated by the repair (keeps a click well under ~150ms). */
const REPAIR_BUDGET = 20;
/** Column slides to try, smallest first. */
const REPAIR_SHIFTS = Array.from({ length: 12 }, (_, i) => (i + 1) * 26).flatMap((d) => [d, -d]);

/**
 * Default Start/End placement when the layout map has none for them (stored
 * layouts from before task 11.8): flanking the participant cloud. Used by the
 * canvas projection (`toStartEndNodes`) and by new-node placement.
 */
export function startEndFallback(
  nodeIds: string[],
  layout: LayoutMap,
): { start: XYPosition; end: XYPosition } {
  const pts = nodeIds.map((id) => layout[id]).filter((p): p is XYPosition => p != null);
  let minX = 0;
  let maxX = 360;
  let centerY = 260;
  if (pts.length > 0) {
    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y);
    minX = Math.min(...xs);
    maxX = Math.max(...xs);
    centerY = (Math.min(...ys) + Math.max(...ys)) / 2;
  }
  return { start: { x: minX - 180, y: centerY }, end: { x: maxX + 220, y: centerY } };
}

export interface PlacementOptions {
  /** Measured node sizes (React Flow), if known. */
  measured?: NodeSizeMap | null;
  /** Current edge bends, so placement can keep clear of the drawn curves. */
  bends?: BendMap | null;
  /** Write Start/End's (fallback) positions into the result so they stay put. */
  pinSentinels?: boolean;
}

const PLACE_STEP = 30;
const PLACE_RINGS_STRICT = 24;
const PLACE_RINGS_MAX = 60;

/**
 * Place every participant missing from `existing` in free space near its
 * neighbours (adjacent participants and, through its connectors, Start/End),
 * never moving a node that already has a position. A spot clear of both node
 * boxes (with `NODE_GAP`) and drawn edges is preferred; failing that, one clear
 * of node boxes. Positions of removed participants are dropped; stored
 * Start/End positions are kept.
 */
export function placeMissingNodes(
  artifact: MADArtifact,
  existing: LayoutMap,
  options: PlacementOptions = {},
): LayoutMap {
  const ids = artifact.participants.nodes.map((n) => n.id);
  const sizes = nodeSizes(artifact, options.measured);
  const next: LayoutMap = {};
  for (const id of ids) if (existing[id]) next[id] = { ...existing[id] };
  const missing = ids.filter((id) => !next[id]);
  const placedBefore = ids.filter((id) => next[id]);
  for (const id of [START_NODE_ID, END_NODE_ID]) {
    if (existing[id]) next[id] = { ...existing[id] };
  }
  if (missing.length === 0) return next;
  if (options.pinSentinels && placedBefore.length > 0) {
    const fb = startEndFallback(placedBefore, next);
    next[START_NODE_ID] ??= fb.start;
    next[END_NODE_ID] ??= fb.end;
  }
  const edges = layoutEdges(artifact);
  const bends = options.bends ?? {};

  for (const id of missing) {
    const placed = ids.filter((p) => next[p]);
    if (placed.length === 0) {
      next[id] = { ...CENTER };
      continue;
    }
    // Obstacles: placed participants + Start/End (stored or fallback).
    const fb = startEndFallback(placed, next);
    const rects = new Map<string, Rect>();
    for (const p of placed) rects.set(p, rectFromTopLeft(next[p], sizes[p]));
    rects.set(START_NODE_ID, rectFromTopLeft(next[START_NODE_ID] ?? fb.start, sizes[START_NODE_ID]));
    rects.set(END_NODE_ID, rectFromTopLeft(next[END_NODE_ID] ?? fb.end, sizes[END_NODE_ID]));

    // Drawn curves between already-placed nodes.
    const lines: Polyline[] = [];
    for (const e of edges) {
      if (e.source === id || e.target === id) continue;
      const sR = rects.get(e.source);
      const tR = rects.get(e.target);
      if (!sR || !tR) continue;
      lines.push(edgeCurve(sR, tR, bends[e.id] ?? null, e.reciprocal));
    }

    // Target: centroid of the placed neighbours, else of everything placed.
    const nbCenters: XYPosition[] = [];
    for (const e of edges) {
      const other = e.source === id ? e.target : e.target === id ? e.source : null;
      const r = other ? rects.get(other) : undefined;
      if (r) nbCenters.push(rectCenter(r));
    }
    const pool =
      nbCenters.length > 0 ? nbCenters : placed.map((p) => rectCenter(rects.get(p)!));
    const target = {
      x: pool.reduce((s, p) => s + p.x, 0) / pool.length,
      y: pool.reduce((s, p) => s + p.y, 0) / pool.length,
    };

    const size = sizes[id];
    const freeOfNodes = (r: Rect) => {
      for (const o of rects.values()) if (boxesOverlap(r, o, NODE_GAP)) return false;
      return true;
    };
    const freeOfEdges = (r: Rect) => {
      for (const line of lines) {
        const { minX, maxX, minY, maxY } = line;
        if (maxX < r.x || minX > r.x + r.width || maxY < r.y || minY > r.y + r.height) continue;
        if (polylineHitsRect(line.points, r, EDGE_CLEARANCE)) return false;
      }
      return true;
    };
    let chosen: Rect | null = null;
    let fallback: Rect | null = null;
    for (let k = 0; k <= PLACE_RINGS_MAX && !chosen; k += 1) {
      for (const [dx, dy] of ringOffsets(k)) {
        const r = rectAt(
          { x: target.x + dx * PLACE_STEP, y: target.y + dy * PLACE_STEP },
          size,
        );
        if (!freeOfNodes(r)) continue;
        if (!fallback) fallback = r;
        if (k <= PLACE_RINGS_STRICT && freeOfEdges(r)) {
          chosen = r;
          break;
        }
      }
      if (!chosen && fallback && k >= PLACE_RINGS_STRICT) chosen = fallback;
    }
    if (!chosen) {
      // Far right of everything (cannot overlap).
      const maxX = Math.max(...[...rects.values()].map((r) => r.x + r.width));
      chosen = { x: maxX + NODE_GAP, y: target.y - size.height / 2, ...size };
    }
    next[id] = roundPt({ x: chosen.x, y: chosen.y });
  }
  return next;
}

/** Grid offsets at Chebyshev distance `k`, nearest (Euclidean) first. */
function ringOffsets(k: number): Array<[number, number]> {
  if (k === 0) return [[0, 0]];
  const out: Array<[number, number]> = [];
  for (let i = -k; i <= k; i += 1) {
    for (let j = -k; j <= k; j += 1) {
      if (Math.max(Math.abs(i), Math.abs(j)) === k) out.push([i, j]);
    }
  }
  out.sort(
    (a, b) =>
      a[0] * a[0] + a[1] * a[1] - (b[0] * b[0] + b[1] * b[1]) ||
      Math.atan2(a[1], a[0]) - Math.atan2(b[1], b[0]),
  );
  return out;
}

/**
 * Ensure every participant has a position (used when adding a node): existing
 * positions — Start/End included, materialized from their fallback so they do
 * not shift — are kept, missing ones are placed in free space near their
 * neighbours, stale ids are dropped.
 */
export function reconcileLayout(
  artifact: MADArtifact,
  existing: LayoutMap,
  options: Omit<PlacementOptions, "pinSentinels"> = {},
): LayoutMap {
  return placeMissingNodes(artifact, existing, { ...options, pinSentinels: true });
}

/**
 * Build the layout from stored positions (e.g. `artifact.ui.nodes`).
 *
 * - No participant has a valid stored position (no `ui`, new config): full
 *   `autoLayout`, Start/End and bends included (`bends` is then non-null and
 *   replaces any stored bends).
 * - Otherwise the stored layout is kept as is (never re-laid-out): only
 *   participants without a position are placed in free space; `extraIds` (the
 *   Start/End sentinels) are copied when stored and otherwise left out, so the
 *   canvas falls back to their computed default. `bends` is null.
 *
 * Unknown keys and malformed points are ignored.
 */
export function seedLayout(
  artifact: MADArtifact,
  stored: Record<string, unknown> | null | undefined,
  extraIds: string[] = [],
  options: Omit<PlacementOptions, "pinSentinels"> = {},
): { layout: LayoutMap; bends: BendMap | null } {
  const valid = (p: unknown): p is XYPosition =>
    typeof p === "object" &&
    p !== null &&
    Number.isFinite((p as XYPosition).x) &&
    Number.isFinite((p as XYPosition).y);
  const src = stored ?? {};
  const ids = artifact.participants.nodes.map((n) => n.id);
  if (!ids.some((id) => valid(src[id]))) {
    const auto = autoLayout(artifact, options.measured);
    return { layout: auto.positions, bends: auto.bends };
  }
  const base: LayoutMap = {};
  for (const id of [...ids, ...extraIds]) {
    const p = src[id];
    if (valid(p)) base[id] = { x: p.x, y: p.y };
  }
  return { layout: placeMissingNodes(artifact, base, options), bends: null };
}
