import { describe, expect, it } from "vitest";

import { normalizeArtifact, type ApplicableTopology, type MADArtifact } from "./artifact";
import {
  floatingEdgeGeometry,
  quadraticPoint,
  reciprocalOffset,
  rectCenter,
  type Rect,
} from "./edgeGeometry";
import { toFlowEdges, toFlowNodes, toStartEndEdges, toStartEndNodes } from "./flowGraph";
import { OFFERED_TOPOLOGIES } from "./interactionScope";
import {
  autoLayout,
  boxesOverlap,
  nodeSizes,
  reconcileLayout,
  type BendMap,
  type LayoutMap,
  type XYPosition,
} from "./layout";
import { END_NODE_ID, START_NODE_ID } from "./StartEndNodes";
import { buildTopologyEdges } from "./topology";

/* ------------------------------- fixtures -------------------------------- */

type Variant = "plain" | "judge" | "summarizer" | "applied";

/**
 * n debaters wired by `topology`, plus:
 *  - judge:      a judge every debater reports to (judge-based authority);
 *  - summarizer: a summarizer every debater reports to (collective, default IO);
 *  - applied:    a judge included in the template, as the toolbar applies it.
 */
function makeArtifact(topology: ApplicableTopology, n: number, variant: Variant): MADArtifact {
  const debaters = Array.from({ length: n }, (_, i) => `d${i + 1}`);
  const nodes = debaters.map((id) => ({ id, label: `Debater ${id}`, roles: ["debater"] }));
  let edges = buildTopologyEdges(topology, debaters);
  let authority = "collective";
  if (variant === "judge" || variant === "applied") {
    nodes.push({ id: "judge", label: "Judge", roles: ["judge"] });
    authority = "judge_based";
    edges =
      variant === "judge"
        ? [...edges, ...debaters.map((d) => ({ source: d, target: "judge", directed: true }))]
        : buildTopologyEdges(topology, [...debaters, "judge"]);
  } else if (variant === "summarizer") {
    nodes.push({ id: "sum", label: "Summarizer", roles: ["summarizer"] });
    edges = [...edges, ...debaters.map((d) => ({ source: d, target: "sum", directed: true }))];
  }
  return normalizeArtifact({
    name: `${topology}-${n}-${variant}`,
    participants: { nodes },
    interaction: { topology: { structure: "structured_network", edges } },
    agreement: { authority },
  });
}

/** The old fixed declaration-order circle (pre task 11.8), for comparison. */
function legacyCircle(ids: string[]): LayoutMap {
  const layout: LayoutMap = {};
  ids.forEach((id, i) => {
    const angle = (2 * Math.PI * i) / ids.length - Math.PI / 2;
    layout[id] = {
      x: Math.round(360 + 220 * Math.cos(angle)),
      y: Math.round(260 + 220 * Math.sin(angle)),
    };
  });
  return layout;
}

/* ------------------- rendered geometry (as the canvas) ------------------- */

interface Rendered {
  rects: Map<string, Rect>;
  curves: Array<{ id: string; source: string; target: string; points: XYPosition[] }>;
}

/** Node boxes + edge curves exactly as DesignerPage / FloatingEdge render them. */
function render(artifact: MADArtifact, layout: LayoutMap, bends: BendMap): Rendered {
  const sizes = nodeSizes(artifact);
  const rects = new Map<string, Rect>();
  for (const n of [...toFlowNodes(artifact, layout, null), ...toStartEndNodes(artifact, layout)]) {
    rects.set(n.id, { ...n.position, ...sizes[n.id] });
  }
  const edges = [
    ...toFlowEdges(artifact, null, bends),
    ...toStartEndEdges(artifact, null, bends),
  ];
  const curves = edges.map((e) => {
    const s = rects.get(e.source)!;
    const t = rects.get(e.target)!;
    const geo = floatingEdgeGeometry(
      s,
      t,
      e.data?.bend ?? null,
      e.data?.reciprocal ? reciprocalOffset(rectCenter(s), rectCenter(t)) : null,
    );
    const points: XYPosition[] = [];
    for (let i = 0; i <= 200; i += 1) {
      points.push(quadraticPoint(geo.source, geo.control, geo.target, i / 200));
    }
    return { id: e.id, source: e.source, target: e.target, points };
  });
  return { rects, curves };
}

const strictlyInside = (p: XYPosition, r: Rect) =>
  p.x > r.x + 0.5 && p.x < r.x + r.width - 0.5 && p.y > r.y + 0.5 && p.y < r.y + r.height - 0.5;

/** "edge id through node id" for every curve entering a non-endpoint box. */
function edgeThroughNode({ rects, curves }: Rendered): string[] {
  const out: string[] = [];
  for (const c of curves) {
    for (const [id, r] of rects) {
      if (id === c.source || id === c.target) continue;
      if (c.points.some((p) => strictlyInside(p, r))) out.push(`${c.id} through ${id}`);
    }
  }
  return out;
}

function overlappingBoxes({ rects }: Rendered): string[] {
  const list = [...rects];
  const out: string[] = [];
  for (let i = 0; i < list.length; i += 1) {
    for (let j = i + 1; j < list.length; j += 1) {
      if (boxesOverlap(list[i][1], list[j][1])) out.push(`${list[i][0]} / ${list[j][0]}`);
    }
  }
  return out;
}

function segmentsCross(a: XYPosition, b: XYPosition, c: XYPosition, d: XYPosition) {
  const cross = (o: XYPosition, p: XYPosition, q: XYPosition) =>
    (p.x - o.x) * (q.y - o.y) - (p.y - o.y) * (q.x - o.x);
  const d1 = cross(c, d, a);
  const d2 = cross(c, d, b);
  const d3 = cross(a, b, c);
  const d4 = cross(a, b, d);
  return d1 * d2 < 0 && d3 * d4 < 0;
}

/** Pairs of rendered curves (not sharing a node) that cross at least once. */
function crossingPairs({ curves }: Rendered): number {
  const coarse = curves.map((c) => ({
    ...c,
    pts: c.points.filter((_, i) => i % 4 === 0),
  }));
  let count = 0;
  for (let i = 0; i < coarse.length; i += 1) {
    for (let j = i + 1; j < coarse.length; j += 1) {
      const a = coarse[i];
      const b = coarse[j];
      const shared = new Set([a.source, a.target]);
      if (shared.has(b.source) || shared.has(b.target)) continue;
      let hit = false;
      for (let p = 0; p < a.pts.length - 1 && !hit; p += 1) {
        for (let q = 0; q < b.pts.length - 1 && !hit; q += 1) {
          hit = segmentsCross(a.pts[p], a.pts[p + 1], b.pts[q], b.pts[q + 1]);
        }
      }
      if (hit) count += 1;
    }
  }
  return count;
}

/* --------------------------------- tests --------------------------------- */

const SIZES = [2, 3, 4, 5, 6, 7, 8, 9, 10];
const VARIANTS: Variant[] = ["plain", "judge", "summarizer", "applied"];

describe("autoLayout — every offered template x 2..10 participants (task 11.8)", () => {
  for (const topology of OFFERED_TOPOLOGIES) {
    for (const variant of VARIANTS) {
      it(`${topology} / ${variant}: no overlaps, no edge through a node, Start/End flank, deterministic`, () => {
        const through: string[] = [];
        for (const n of SIZES) {
          const artifact = makeArtifact(topology, n, variant);
          const { positions, bends } = autoLayout(artifact);
          const r = render(artifact, positions, bends);
          const label = `${topology} n=${n} ${variant}`;

          expect(positions[START_NODE_ID], label).toBeDefined();
          expect(positions[END_NODE_ID], label).toBeDefined();
          expect(overlappingBoxes(r), label).toEqual([]);
          through.push(...edgeThroughNode(r).map((x) => `n=${n}: ${x}`));

          const start = r.rects.get(START_NODE_ID)!;
          const end = r.rects.get(END_NODE_ID)!;
          for (const node of artifact.participants.nodes) {
            const box = r.rects.get(node.id)!;
            expect(start.x + start.width, `${label} Start left of ${node.id}`).toBeLessThan(box.x);
            expect(end.x, `${label} End right of ${node.id}`).toBeGreaterThan(box.x + box.width);
          }

          expect(autoLayout(artifact), label).toEqual({ positions, bends });
        }
        expect(through).toEqual([]);
      });
    }
  }
});

describe("autoLayout — structure", () => {
  it("ranks a chain along the flow and puts a judge next to End", () => {
    const a = makeArtifact("chain", 4, "judge");
    const { positions } = autoLayout(a);
    const xs = ["d1", "d2", "d3", "d4", "judge"].map((id) => positions[id].x);
    expect([...xs].sort((p, q) => p - q)).toEqual(xs);
    const participantsRight = Math.max(...xs);
    expect(positions.judge.x).toBe(participantsRight);
    expect(positions[END_NODE_ID].x).toBeGreaterThan(positions.judge.x);
  });

  it("keeps a fully connected debate in one compact column (one rank)", () => {
    const a = makeArtifact("fully_connected", 6, "plain");
    const { positions } = autoLayout(a);
    const sizes = nodeSizes(a);
    const xs = a.participants.nodes.map((n) => positions[n.id].x + sizes[n.id].width / 2);
    const start = positions[START_NODE_ID].x + sizes[START_NODE_ID].width;
    const end = positions[END_NODE_ID].x;
    // A single cluster between Start and End, much narrower than the same
    // six nodes ranked one after another (a chain).
    expect(Math.min(...xs)).toBeGreaterThan(start);
    expect(Math.max(...xs)).toBeLessThan(end);
    const chain = autoLayout(makeArtifact("chain", 6, "plain")).positions;
    const chainSpread = chain.d6.x - chain.d1.x;
    expect(Math.max(...xs) - Math.min(...xs)).toBeLessThan(chainSpread / 2);
  });

  it("uses measured sizes when given (wider nodes, wider spacing)", () => {
    const a = makeArtifact("chain", 3, "plain");
    const narrow = autoLayout(a).positions;
    const wide = autoLayout(a, {
      d1: { width: 400, height: 120 },
      d2: { width: 400, height: 120 },
      d3: { width: 400, height: 120 },
    }).positions;
    expect(wide.d3.x - wide.d1.x).toBeGreaterThan(narrow.d3.x - narrow.d1.x);
  });

  it("returns an empty layout for an empty graph", () => {
    const a = normalizeArtifact({ name: "x", participants: { nodes: [] }, interaction: { topology: { edges: [] } } });
    expect(autoLayout(a)).toEqual({ positions: {}, bends: {} });
  });
});

describe("autoLayout — crossings vs the old circle", () => {
  for (const topology of ["chain", "star", "tree"] as const) {
    it(`${topology}: not more crossing edge pairs than the declaration-order circle`, () => {
      for (const n of SIZES) {
        const a = makeArtifact(topology, n, "plain");
        const { positions, bends } = autoLayout(a);
        const fresh = crossingPairs(render(a, positions, bends));
        const old = crossingPairs(
          render(a, legacyCircle(a.participants.nodes.map((x) => x.id)), {}),
        );
        expect(fresh, `${topology} n=${n} (old ${old})`).toBeLessThanOrEqual(old);
      }
    });
  }
});

describe("reconcileLayout — new-node placement", () => {
  for (const topology of ["fully_connected", "chain", "star", "tree"] as const) {
    it(`${topology}: a new node lands in free space and nothing else moves`, () => {
      for (const n of [3, 6, 9]) {
        const a = makeArtifact(topology, n, "plain");
        const { positions, bends } = autoLayout(a);
        const withNew = normalizeArtifact({
          ...a,
          participants: {
            ...a.participants,
            nodes: [...a.participants.nodes, { id: "new", label: "Participant", roles: ["debater"] }],
          },
          interaction: {
            ...a.interaction,
            topology: {
              ...a.interaction.topology,
              edges: [...a.interaction.topology.edges, { source: "d1", target: "new", directed: true }],
            },
          },
        });
        const next = reconcileLayout(withNew, positions, { bends });
        for (const [id, p] of Object.entries(positions)) expect(next[id]).toEqual(p);
        const r = render(withNew, next, bends);
        expect(overlappingBoxes(r), `${topology} n=${n}`).toEqual([]);
      }
    });
  }
});
