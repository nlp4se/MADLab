import { beforeEach, describe, expect, it } from "vitest";

import { edgeId, useDesignerStore, withUiLayout } from "./designerStore";
import { toFlowEdges, toFlowNodes, toStartEndEdges } from "./flowGraph";
import { autoLayout } from "./layout";

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

/* ------------- edge bends + persisted layout (task 11.4) ------------- */

describe("designer store — edge bends", () => {
  beforeEach(loadFixture);

  it("setEdgeBend / resetEdgeBend store and clear a bend, marking dirty", () => {
    current().setEdgeBend("functional->judge", { x: 12, y: -30 });
    expect(current().edgeBends["functional->judge"]).toEqual({ x: 12, y: -30 });
    expect(current().dirty).toBe(true);
    // The projection hands the bend to the floating edge.
    const e = toFlowEdges(current().artifact!, null, current().edgeBends);
    expect(e.find((x) => x.id === "functional->judge")!.data!.bend).toEqual({
      x: 12,
      y: -30,
    });

    current().markSaved();
    current().resetEdgeBend("functional->judge");
    expect(current().edgeBends["functional->judge"]).toBeUndefined();
    expect(current().dirty).toBe(true);
  });

  it("Start/End connectors are bendable too", () => {
    current().setEdgeBend("__start__->functional", { x: 0, y: 40 });
    const conn = toStartEndEdges(current().artifact!, null, current().edgeBends);
    expect(conn.find((x) => x.id === "__start__->functional")!.data!.bend).toEqual({
      x: 0,
      y: 40,
    });
  });

  it("drops bends of edges that no longer exist (removeEdge / removeNode / connectors)", () => {
    const s = current();
    s.setEdgeBend("functional->judge", { x: 1, y: 1 });
    s.setEdgeBend("non-functional->judge", { x: 2, y: 2 });
    s.setEdgeBend("__start__->functional", { x: 3, y: 3 });
    s.setEdgeBend("__start__->non-functional", { x: 4, y: 4 });

    current().removeEdge("functional->judge");
    expect(Object.keys(current().edgeBends).sort()).toEqual([
      "__start__->functional",
      "__start__->non-functional",
      "non-functional->judge",
    ]);

    current().deleteCanvasEdge("__start__->functional");
    expect(current().edgeBends["__start__->functional"]).toBeUndefined();

    current().removeNode("non-functional");
    expect(current().edgeBends).toEqual({});
  });

  it("applyTopology keeps bends only for edges that survive; relayout clears all", () => {
    current().setEdgeBend("functional->judge", { x: 1, y: 1 });
    current().setEdgeBend("__start__->functional", { x: 5, y: 5 });
    // Chain over [functional, non-functional, judge] => functional->non-functional,
    // non-functional->judge: the old functional->judge edge is gone.
    current().applyTopology("chain");
    expect(current().edgeBends).toEqual({ "__start__->functional": { x: 5, y: 5 } });

    current().setEdgeBend("non-functional->judge", { x: 9, y: 9 });
    current().relayout();
    expect(current().edgeBends).toEqual({});
  });

  it("flags reciprocal pairs so they render as two separated curves", () => {
    current().connectNodes("judge", "functional");
    const edges = toFlowEdges(current().artifact!, null);
    const byId = Object.fromEntries(edges.map((e) => [e.id, e]));
    expect(byId["functional->judge"].data!.reciprocal).toBe(true);
    expect(byId["judge->functional"].data!.reciprocal).toBe(true);
    expect(byId["non-functional->judge"].data!.reciprocal).toBe(false);
  });
});

describe("designer store — persisted layout (artifact.ui)", () => {
  const withUi = (ui: unknown) => ({ ...makeArtifact(), ui });

  it("loadArtifact seeds positions and bends from ui, auto-placing only the rest", () => {
    useDesignerStore.getState().loadArtifact(
      7,
      withUi({
        nodes: {
          functional: { x: 11, y: 22 },
          __start__: { x: -300, y: 5 },
          ghost: { x: 1, y: 1 }, // stale key -> ignored
        },
        edges: {
          "functional->judge": { x: 0, y: 25 },
          "ghost->judge": { x: 1, y: 1 }, // stale -> ignored
        },
      }),
    );
    const s = current();
    const auto = autoLayout(["functional", "non-functional", "judge"]);
    expect(s.layout.functional).toEqual({ x: 11, y: 22 });
    expect(s.layout["non-functional"]).toEqual(auto["non-functional"]);
    expect(s.layout.judge).toEqual(auto.judge);
    expect(s.layout.__start__).toEqual({ x: -300, y: 5 });
    // End has no stored position -> canvas falls back to its computed default.
    expect(s.layout.__end__).toBeUndefined();
    expect(s.layout.ghost).toBeUndefined();
    expect(s.edgeBends).toEqual({ "functional->judge": { x: 0, y: 25 } });
    expect(s.dirty).toBe(false);
  });

  it("loadArtifact without ui (or ui: null) auto-lays-out as before", () => {
    useDesignerStore.getState().loadArtifact(7, withUi(null));
    expect(current().layout).toEqual(autoLayout(["functional", "non-functional", "judge"]));
    expect(current().edgeBends).toEqual({});
  });

  it("withUiLayout (used by Save) writes the current layout + bends for existing ids only", () => {
    current().moveNode("judge", { x: 500, y: 600 });
    current().moveNode("__end__", { x: 900, y: 10 });
    current().setEdgeBend("functional->judge", { x: 3, y: -4 });
    // A stale entry sneaking into the maps must not be persisted.
    useDesignerStore.setState({
      layout: { ...current().layout, ghost: { x: 0, y: 0 } },
      edgeBends: { ...current().edgeBends, "ghost->judge": { x: 1, y: 1 } },
    });

    const s = current();
    const saved = withUiLayout(s.artifact!, s.layout, s.edgeBends);
    expect(Object.keys(saved.ui!.nodes!).sort()).toEqual(
      ["__end__", "functional", "judge", "non-functional"].sort(),
    );
    expect(saved.ui!.nodes!.judge).toEqual({ x: 500, y: 600 });
    expect(saved.ui!.nodes!.__end__).toEqual({ x: 900, y: 10 });
    expect(saved.ui!.edges).toEqual({ "functional->judge": { x: 3, y: -4 } });
    // The graph itself is untouched.
    expect(saved.participants).toEqual(s.artifact!.participants);
    expect(saved.interaction).toEqual(s.artifact!.interaction);

    // Round trip: reloading the saved artifact restores the same canvas.
    useDesignerStore.getState().loadArtifact(42, saved as unknown as Record<string, unknown>);
    expect(current().layout.judge).toEqual({ x: 500, y: 600 });
    expect(current().layout.__end__).toEqual({ x: 900, y: 10 });
    expect(current().edgeBends).toEqual({ "functional->judge": { x: 3, y: -4 } });
  });

  it("an assistant proposal without ui keeps current positions/bends for ids that still exist", () => {
    current().moveNode("judge", { x: 1, y: 2 });
    current().setEdgeBend("non-functional->judge", { x: 7, y: 7 });
    current().setEdgeBend("functional->judge", { x: 8, y: 8 });
    const proposal = makeArtifact();
    // Proposal drops the functional->judge edge and adds a new node.
    proposal.interaction.topology.edges = [
      { source: "non-functional", target: "judge", directed: true },
    ];
    proposal.participants.nodes.push({
      id: "summarizer",
      label: "Summarizer",
      roles: ["summarizer"],
      base_model: { model_key: "gpt-4o", provider_id: "openai" },
    });
    current().setArtifactFromAssistant(proposal);
    const s = current();
    expect(s.layout.judge).toEqual({ x: 1, y: 2 });
    expect(s.layout.summarizer).toBeDefined();
    expect(s.edgeBends).toEqual({ "non-functional->judge": { x: 7, y: 7 } });
    expect(s.dirty).toBe(true);
  });
});
