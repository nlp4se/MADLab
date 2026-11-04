import { describe, expect, it } from "vitest";
import { MarkerType } from "reactflow";

import { normalizeArtifact } from "./artifact";
import {
  toFlowEdges,
  toStartEndEdges,
  toStartEndNodes,
} from "./flowGraph";
import { autoLayout } from "./layout";
import { END_NODE_ID, START_NODE_ID } from "./StartEndNodes";

/* ------------------------------- fixtures -------------------------------- */

/** Chain a -> b -> c: pure entry (a) and pure terminal (c). */
function chainArtifact() {
  return normalizeArtifact({
    name: "chain",
    participants: {
      nodes: [
        { id: "a", label: "A", roles: ["debater"] },
        { id: "b", label: "B", roles: ["debater"] },
        { id: "c", label: "C", roles: ["judge"] },
      ],
    },
    interaction: {
      topology: {
        structure: "structured_network",
        pattern: "chain",
        edges: [
          { source: "a", target: "b", directed: true },
          { source: "b", target: "c", directed: true },
        ],
      },
      protocol: { order: ["a", "b", "c"] },
    },
  });
}

/** Fully connected a<->b<->c: every node has in+out edges (no pure entry/terminal). */
function fullyConnectedArtifact() {
  const ids = ["a", "b", "c"];
  const edges = ids.flatMap((u) =>
    ids.filter((v) => v !== u).map((v) => ({ source: u, target: v, directed: true })),
  );
  return normalizeArtifact({
    name: "fc",
    participants: {
      nodes: [
        { id: "a", label: "A", roles: ["debater"] },
        { id: "b", label: "B", roles: ["debater"] },
        { id: "c", label: "C", roles: ["judge"] },
      ],
    },
    interaction: {
      topology: { structure: "fully_connected", edges },
      protocol: { order: ["a", "b", "c"] },
    },
  });
}

const layoutOf = (a: ReturnType<typeof chainArtifact>) =>
  autoLayout(a.participants.nodes.map((n) => n.id));

/* --------------------------------- tests --------------------------------- */

describe("flowGraph — arrows", () => {
  it("gives directed edges a sized arrowhead", () => {
    const a = chainArtifact();
    const edges = toFlowEdges(a, null);
    for (const e of edges) {
      expect(e.markerEnd).toMatchObject({
        type: MarkerType.ArrowClosed,
        width: 22,
        height: 22,
      });
    }
  });

  it("omits the arrowhead for an explicitly undirected edge", () => {
    const a = normalizeArtifact({
      name: "x",
      participants: { nodes: [{ id: "a", label: "A", roles: [] }, { id: "b", label: "B", roles: [] }] },
      interaction: {
        topology: { edges: [{ source: "a", target: "b", directed: false }] },
      },
    });
    expect(toFlowEdges(a, null)[0].markerEnd).toBeUndefined();
  });
});

describe("flowGraph — synthetic Start/End (visual only)", () => {
  it("produces non-selectable, non-deletable Start and End nodes", () => {
    const a = chainArtifact();
    const nodes = toStartEndNodes(a, layoutOf(a));
    const ids = nodes.map((n) => n.id);
    expect(ids).toEqual([START_NODE_ID, END_NODE_ID]);
    for (const n of nodes) {
      expect(n.selectable).toBe(false);
      expect(n.deletable).toBe(false);
    }
  });

  it("wires Start -> entry node and terminal node -> End for a chain", () => {
    const a = chainArtifact();
    const edges = toStartEndEdges(a);
    const ids = edges.map((e) => e.id);
    // Entry = a (no incoming), terminal = c (no outgoing).
    expect(ids).toContain(`${START_NODE_ID}->a`);
    expect(ids).toContain(`c->${END_NODE_ID}`);
    // Synthetic edges are dashed.
    expect(edges[0].style?.strokeDasharray).toBeDefined();
  });

  it("falls back to protocol order / judge when there is no pure entry/terminal", () => {
    const a = fullyConnectedArtifact();
    const edges = toStartEndEdges(a);
    const ids = edges.map((e) => e.id);
    // First in order is the entry fallback; judge (c) is the terminal fallback.
    expect(ids).toContain(`${START_NODE_ID}->a`);
    expect(ids).toContain(`c->${END_NODE_ID}`);
  });

  it("produces nothing for an empty graph", () => {
    const a = normalizeArtifact({ name: "empty", participants: { nodes: [] }, interaction: { topology: { edges: [] } } });
    expect(toStartEndNodes(a, {})).toEqual([]);
    expect(toStartEndEdges(a)).toEqual([]);
  });
});

describe("flowGraph — toFlowEdges regression guard", () => {
  it("returns ONLY the artifact edges, never the synthetic ones", () => {
    const a = chainArtifact();
    const ids = toFlowEdges(a, null).map((e) => e.id).sort();
    // Exactly the artifact's two edges, by id — no __start__/__end__ leakage.
    expect(ids).toEqual(["a->b", "b->c"]);
    expect(ids.some((id) => id.includes("__start__") || id.includes("__end__"))).toBe(
      false,
    );
  });
});
