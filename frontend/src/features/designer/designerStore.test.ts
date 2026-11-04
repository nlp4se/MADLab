import { beforeEach, describe, expect, it } from "vitest";

import { edgeId, useDesignerStore } from "./designerStore";
import { toFlowEdges, toFlowNodes } from "./flowGraph";

/* ------------------------------- fixtures -------------------------------- */

/** A minimal RE-binary-style artifact: two debaters + a judge, 2 edges. */
function makeArtifact() {
  return {
    schema_version: "1.0",
    name: "Test config",
    description: "",
    participants: {
      nodes: [
        {
          id: "functional",
          label: "Functional debater",
          roles: ["debater"],
          base_model: { model_key: "gpt-4o", provider_id: "openai" },
        },
        {
          id: "non-functional",
          label: "Non-functional debater",
          roles: ["debater"],
          base_model: { model_key: "gpt-4o", provider_id: "openai" },
        },
        {
          id: "judge",
          label: "Judge",
          roles: ["judge"],
          base_model: { model_key: "gpt-4o", provider_id: "openai" },
        },
      ],
    },
    interaction: {
      topology: {
        structure: "structured_network",
        pattern: "star",
        edges: [
          { source: "functional", target: "judge", directed: true },
          { source: "non-functional", target: "judge", directed: true },
        ],
      },
      protocol: { mechanism: "sequential", order: ["functional", "non-functional", "judge"] },
    },
    agreement: { authority: "judge_based", resolution: "argument_evaluation" },
  };
}

/** Reset the singleton store to a loaded state before each test. */
function loadFixture() {
  useDesignerStore.getState().loadArtifact(42, makeArtifact());
}

function current() {
  return useDesignerStore.getState();
}

describe("designer store — canvas<->artifact sync (Req 6.8)", () => {
  beforeEach(() => {
    useDesignerStore.setState({
      configId: null,
      artifact: null,
      layout: {},
      selection: null,
      dirty: false,
    });
    loadFixture();
  });

  it("loads the artifact and derives V/E, auto-placing nodes (not dirty)", () => {
    const s = current();
    expect(s.configId).toBe(42);
    expect(s.artifact?.participants.nodes).toHaveLength(3);
    expect(s.artifact?.interaction.topology.edges).toHaveLength(2);
    // Every node got a layout position (UI-only side-channel).
    expect(Object.keys(s.layout)).toHaveLength(3);
    expect(s.layout["judge"]).toBeDefined();
    // A fresh load is clean.
    expect(s.dirty).toBe(false);
  });

  it("adding a node updates the artifact and marks it dirty", () => {
    const before = current().artifact!.participants.nodes.length;
    const id = current().addNode({ label: "Summarizer", roles: ["summarizer"] });

    const s = current();
    expect(s.artifact!.participants.nodes).toHaveLength(before + 1);
    const added = s.artifact!.participants.nodes.find((n) => n.id === id);
    expect(added).toMatchObject({ label: "Summarizer", roles: ["summarizer"] });
    // The new node is reflected in the layout and the canvas projection.
    expect(s.layout[id]).toBeDefined();
    expect(toFlowNodes(s.artifact!, s.layout, null).some((n) => n.id === id)).toBe(
      true,
    );
    expect(s.dirty).toBe(true);
  });

  it("connecting two nodes creates a directed edge; duplicates/self are ignored", () => {
    const beforeEdges = current().artifact!.interaction.topology.edges.length;

    current().connectNodes("functional", "non-functional");
    expect(current().artifact!.interaction.topology.edges).toHaveLength(
      beforeEdges + 1,
    );

    // Duplicate connection is a no-op.
    current().connectNodes("functional", "non-functional");
    expect(current().artifact!.interaction.topology.edges).toHaveLength(
      beforeEdges + 1,
    );

    // Self-loop is rejected.
    current().connectNodes("judge", "judge");
    expect(current().artifact!.interaction.topology.edges).toHaveLength(
      beforeEdges + 1,
    );
  });

  it("removing a node drops it, its incident edges, and its order ref", () => {
    current().removeNode("judge");
    const s = current();
    expect(s.artifact!.participants.nodes.map((n) => n.id)).not.toContain("judge");
    // Both edges pointed at the judge, so E is now empty.
    expect(s.artifact!.interaction.topology.edges).toHaveLength(0);
    // The protocol order reference is cleaned up too.
    expect(s.artifact!.interaction.protocol!.order).not.toContain("judge");
    // Layout no longer leaks the removed node.
    expect(s.layout["judge"]).toBeUndefined();
  });

  it("removing an edge drops exactly that edge", () => {
    const target = current().artifact!.interaction.topology.edges[0];
    const id = edgeId(target);
    current().removeEdge(id);
    const s = current();
    expect(s.artifact!.interaction.topology.edges).toHaveLength(1);
    expect(
      s.artifact!.interaction.topology.edges.map(edgeId),
    ).not.toContain(id);
  });

  it("applying a topology template regenerates E over the current nodes (Req 6.5)", () => {
    // Chain over 3 nodes -> exactly 2 directed edges, structured_network/chain.
    current().applyTopology("chain");
    let s = current();
    expect(s.artifact!.interaction.topology.edges).toHaveLength(2);
    expect(s.artifact!.interaction.topology.structure).toBe("structured_network");
    expect(s.artifact!.interaction.topology.pattern).toBe("chain");

    // Fully connected over 3 nodes -> n(n-1) = 6 edges, structure updated, no pattern.
    current().applyTopology("fully_connected");
    s = current();
    expect(s.artifact!.interaction.topology.edges).toHaveLength(6);
    expect(s.artifact!.interaction.topology.structure).toBe("fully_connected");
    expect(s.artifact!.interaction.topology.pattern).toBeNull();

    // Ring over 3 nodes -> n = 3 edges.
    current().applyTopology("ring");
    s = current();
    expect(s.artifact!.interaction.topology.edges).toHaveLength(3);
  });

  it("the canvas projection mirrors the artifact (artifact -> canvas)", () => {
    const s = current();
    const flowNodes = toFlowNodes(s.artifact!, s.layout, "judge");
    const flowEdges = toFlowEdges(s.artifact!, null);

    expect(flowNodes).toHaveLength(3);
    // Node data carries the role + model badge inputs (Req 6.1, 6.7).
    const judge = flowNodes.find((n) => n.id === "judge")!;
    expect(judge.data.roles).toEqual(["judge"]);
    expect(judge.data.modelKey).toBe("gpt-4o");
    expect(judge.data.providerId).toBe("openai");
    expect(judge.selected).toBe(true);

    // Edges carry a synthetic id and an arrowhead for directed links (Req 6.4).
    expect(flowEdges).toHaveLength(2);
    expect(flowEdges[0].id).toBe("functional->judge");
    expect(flowEdges[0].markerEnd).toBeDefined();
  });

  it("markSaved clears the dirty flag after a persist round-trip", () => {
    current().addNode();
    expect(current().dirty).toBe(true);
    current().markSaved();
    expect(current().dirty).toBe(false);
  });

  it("round-trips a canvas edit back into the artifact (artifact -> canvas -> edit -> artifact, Req 6.8)", () => {
    // 1. artifact -> canvas: project the loaded artifact to React Flow nodes.
    const before = current();
    const projectedNodes = toFlowNodes(before.artifact!, before.layout, null);
    const projectedEdges = toFlowEdges(before.artifact!, null);
    expect(projectedNodes.map((n) => n.id)).toEqual([
      "functional",
      "non-functional",
      "judge",
    ]);
    expect(projectedEdges.map((e) => e.id)).toEqual([
      "functional->judge",
      "non-functional->judge",
    ]);

    // 2. edit on the canvas: connect the two debaters (the same path
    //    onConnect drives) — a brand-new edge that was not in the artifact.
    expect(
      projectedEdges.some((e) => e.id === "functional->non-functional"),
    ).toBe(false);
    current().connectNodes("functional", "non-functional");

    // 3. edit -> artifact: the artifact's E now carries the new edge, so the
    //    canvas projection re-derived from the artifact mirrors it exactly.
    const after = current();
    expect(
      after.artifact!.interaction.topology.edges.some(
        (e) => e.source === "functional" && e.target === "non-functional",
      ),
    ).toBe(true);

    const reProjected = toFlowEdges(after.artifact!, null);
    expect(reProjected.map((e) => e.id)).toContain(
      "functional->non-functional",
    );
    // The projection is a faithful function of the artifact: exactly the
    // artifact's edges, nothing more, nothing less.
    expect(reProjected.map((e) => e.id).sort()).toEqual(
      after.artifact!.interaction.topology.edges
        .map((e) => `${e.source}->${e.target}`)
        .sort(),
    );
    expect(after.dirty).toBe(true);
  });

  /* ------------------- Start/End IO connectors (task 11.2) ------------------ */

  const topo = () => current().artifact!.interaction.topology;

  it("removeEntryNode materializes the effective entries minus the node", () => {
    // Default (null) entries = the two debaters (the judge is judge-only).
    expect(topo().entry_nodes ?? null).toBeNull();
    current().removeEntryNode("functional");
    expect(topo().entry_nodes).toEqual(["non-functional"]);
    expect(current().dirty).toBe(true);
    // Removing the last one is allowed (Save validation reports "non-empty").
    current().removeEntryNode("non-functional");
    expect(topo().entry_nodes).toEqual([]);
  });

  it("addEntryNode appends to the effective entries without duplicates", () => {
    current().addEntryNode("functional"); // already a default entry -> no-op
    expect(topo().entry_nodes ?? null).toBeNull();
    expect(current().dirty).toBe(false);

    current().addEntryNode("judge");
    expect(topo().entry_nodes).toEqual(["functional", "non-functional", "judge"]);
    current().addEntryNode("judge");
    expect(topo().entry_nodes).toEqual(["functional", "non-functional", "judge"]);
    current().addEntryNode("ghost"); // unknown node -> ignored
    expect(topo().entry_nodes).toHaveLength(3);
    expect(current().dirty).toBe(true);
  });

  it("removeExitNode / addExitNode edit the effective exits (judge_based default = judge)", () => {
    current().addExitNode("functional");
    expect(topo().exit_nodes).toEqual(["judge", "functional"]);
    current().removeExitNode("judge");
    expect(topo().exit_nodes).toEqual(["functional"]);
    current().addExitNode("functional"); // duplicate -> no change
    expect(topo().exit_nodes).toEqual(["functional"]);
  });

  it("deleteCanvasEdge routes participant edges and Start/End connectors", () => {
    current().deleteCanvasEdge("__start__->functional");
    expect(topo().entry_nodes).toEqual(["non-functional"]);

    current().deleteCanvasEdge("judge->__end__");
    expect(topo().exit_nodes).toEqual([]);

    current().deleteCanvasEdge("functional->judge");
    expect(topo().edges.map(edgeId)).toEqual(["non-functional->judge"]);
  });

  it("removeNode drops the node from entry/exit lists, resetting emptied lists to null", () => {
    current().removeEntryNode("non-functional"); // entry_nodes = [functional]
    current().addExitNode("functional"); // exit_nodes = [judge, functional]
    current().setSelection({ kind: "edge", id: "__start__->functional" });

    current().removeNode("functional");
    // The only entry was deleted -> back to the default (null), not [].
    expect(topo().entry_nodes).toBeNull();
    expect(topo().exit_nodes).toEqual(["judge"]);
    // A selected connector of the deleted node is cleared.
    expect(current().selection).toBeNull();
  });

  it("removeNode leaves unset (default) entry/exit lists untouched", () => {
    current().removeNode("non-functional");
    expect(topo().entry_nodes ?? null).toBeNull();
    expect(topo().exit_nodes ?? null).toBeNull();
  });

  it("round-trips a node-label edit from artifact to canvas projection (Req 6.8)", () => {
    // A field edit through the store (canvas -> artifact) is reflected in the
    // next canvas projection (artifact -> canvas), closing the two-way loop.
    current().updateNode("judge", { label: "Presiding judge" });

    const s = current();
    expect(
      s.artifact!.participants.nodes.find((n) => n.id === "judge")!.label,
    ).toBe("Presiding judge");

    const judgeNode = toFlowNodes(s.artifact!, s.layout, null).find(
      (n) => n.id === "judge",
    )!;
    expect(judgeNode.data.label).toBe("Presiding judge");
  });
});
