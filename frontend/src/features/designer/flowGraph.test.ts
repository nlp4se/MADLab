import { describe, expect, it } from "vitest";
import { MarkerType } from "reactflow";

import { normalizeArtifact } from "./artifact";
import {
  effectiveEntryNodeIds,
  effectiveExitNodeIds,
  FLOATING_EDGE_TYPE,
  parseConnectorId,
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

const layoutOf = (a: ReturnType<typeof chainArtifact>) => autoLayout(a).positions;

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

  it("renders every edge (participant + Start/End connectors) as a floating edge", () => {
    const a = chainArtifact();
    const all = [...toFlowEdges(a, null), ...toStartEndEdges(a)];
    expect(all.every((e) => e.type === FLOATING_EDGE_TYPE)).toBe(true);
    // No stored bend -> default shape; a chain has no reciprocal pairs.
    expect(all.every((e) => e.data?.bend === null && e.data?.reciprocal === false)).toBe(
      true,
    );
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

describe("flowGraph — synthetic Start/End nodes + IO connectors", () => {
  it("produces non-deletable Start and End nodes; only Start is selectable (task 11.10)", () => {
    const a = chainArtifact();
    const nodes = toStartEndNodes(a, layoutOf(a));
    const ids = nodes.map((n) => n.id);
    expect(ids).toEqual([START_NODE_ID, END_NODE_ID]);
    for (const n of nodes) {
      expect(n.deletable).toBe(false);
      expect(n.draggable).toBe(true);
    }
    const [start, end] = nodes;
    expect(start.selectable).toBe(true);
    expect(start.selected).toBe(false);
    expect(end.selectable).toBe(false);
    // The Input selection highlights Start.
    expect(toStartEndNodes(a, layoutOf(a), true)[0].selected).toBe(true);
  });

  it("flags Start when the input template is empty", () => {
    const a = chainArtifact();
    expect(toStartEndNodes(a, layoutOf(a))[0].data.inputMissing).toBe(true);
    const withInput = { ...a, input_spec: { template: "{{input}}" } };
    expect(toStartEndNodes(withInput, layoutOf(a))[0].data.inputMissing).toBe(false);
  });

  it("wires Start -> every speaker and the aggregated debaters -> End (engine default)", () => {
    // Chain a -> b -> c(judge), collective: the engine gives the task to every
    // speaking node (a, b; c is judge-only) and aggregates a + b.
    const a = chainArtifact();
    const edges = toStartEndEdges(a);
    const ids = edges.map((e) => e.id);
    expect(ids).toEqual([
      `${START_NODE_ID}->a`,
      `${START_NODE_ID}->b`,
      `a->${END_NODE_ID}`,
      `b->${END_NODE_ID}`,
    ]);
    // Connectors are dashed and deletable (routed to the store by the canvas).
    expect(edges[0].style?.strokeDasharray).toBeDefined();
    expect(edges.every((e) => e.deletable === true)).toBe(true);
  });

  it("derives the same default for fully connected (topology does not matter)", () => {
    const a = fullyConnectedArtifact();
    const ids = toStartEndEdges(a).map((e) => e.id);
    expect(ids).toEqual([
      `${START_NODE_ID}->a`,
      `${START_NODE_ID}->b`,
      `a->${END_NODE_ID}`,
      `b->${END_NODE_ID}`,
    ]);
  });

  it("marks the selected connector as selected", () => {
    const a = chainArtifact();
    const edges = toStartEndEdges(a, `${START_NODE_ID}->b`);
    expect(edges.find((e) => e.id === `${START_NODE_ID}->b`)!.selected).toBe(true);
    expect(edges.find((e) => e.id === `${START_NODE_ID}->a`)!.selected).toBe(false);
  });

  it("produces nothing for an empty graph", () => {
    const a = normalizeArtifact({ name: "empty", participants: { nodes: [] }, interaction: { topology: { edges: [] } } });
    expect(toStartEndNodes(a, {})).toEqual([]);
    expect(toStartEndEdges(a)).toEqual([]);
  });
});

describe("flowGraph — effective entry/exit derivation (mirrors the engine)", () => {
  const withAgreement = (authority: "collective" | "judge_based" | "hybrid") => {
    const a = chainArtifact();
    return { ...a, agreement: { ...a.agreement, authority } };
  };

  it("entries default to every non-judge-only participant", () => {
    const a = normalizeArtifact({
      name: "roles",
      participants: {
        nodes: [
          { id: "d", label: "D", roles: ["debater"] },
          { id: "jd", label: "JD", roles: ["judge", "debater"] },
          { id: "j", label: "J", roles: ["judge"] },
          { id: "s", label: "S", roles: ["summarizer"] },
        ],
      },
      interaction: { topology: { edges: [] } },
    });
    // A judge that is also a debater speaks; a summarizer speaks too.
    expect(effectiveEntryNodeIds(a)).toEqual(["d", "jd", "s"]);
    // Collective aggregates non-judge, non-summarizer nodes only.
    expect(effectiveExitNodeIds(a)).toEqual(["d"]);
  });

  it("exits default per authority: judge_based -> first judge; hybrid -> debaters + judge", () => {
    expect(effectiveExitNodeIds(withAgreement("collective"))).toEqual(["a", "b"]);
    expect(effectiveExitNodeIds(withAgreement("judge_based"))).toEqual(["c"]);
    expect(effectiveExitNodeIds(withAgreement("hybrid"))).toEqual(["a", "b", "c"]);
  });

  it("explicit entry_nodes / exit_nodes override the defaults", () => {
    const a = chainArtifact();
    const overridden = {
      ...a,
      interaction: {
        ...a.interaction,
        topology: { ...a.interaction.topology, entry_nodes: ["b"], exit_nodes: ["c"] },
      },
    };
    expect(effectiveEntryNodeIds(overridden)).toEqual(["b"]);
    expect(effectiveExitNodeIds(overridden)).toEqual(["c"]);
    expect(toStartEndEdges(overridden).map((e) => e.id)).toEqual([
      `${START_NODE_ID}->b`,
      `c->${END_NODE_ID}`,
    ]);
    // An explicit empty list means "no connectors" (Save validation reports it).
    const emptied = {
      ...a,
      interaction: { ...a.interaction, topology: { ...a.interaction.topology, entry_nodes: [] } },
    };
    expect(effectiveEntryNodeIds(emptied)).toEqual([]);
  });

  it("parses connector ids and tells them apart from real edges", () => {
    expect(parseConnectorId(`${START_NODE_ID}->a`)).toEqual({ kind: "entry", nodeId: "a" });
    expect(parseConnectorId(`b->${END_NODE_ID}`)).toEqual({ kind: "exit", nodeId: "b" });
    expect(parseConnectorId("a->b")).toBeNull();
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
