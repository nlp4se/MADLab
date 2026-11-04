import { beforeEach, describe, expect, it } from "vitest";

import { useDesignerStore } from "./designerStore";
import { effectiveExitNodeIds, toFlowNodes, toStartEndEdges } from "./flowGraph";
import { topologyStatus } from "./interactionScope";

/** Store invariants for the Interaction / Agreement scope (task 11.7). */

const s = () => useDesignerStore.getState();
const art = () => s().artifact!;

function seed(raw: Record<string, unknown> = {}) {
  useDesignerStore.getState().loadArtifact(1, {
    name: "Interaction store",
    participants: {
      base_model_heterogeneity: "homogeneous",
      nodes: [
        { id: "a", label: "Alpha", roles: ["debater"], base_model: { provider_id: "1", model_key: "gpt-4o" } },
        { id: "b", label: "Beta", roles: ["debater"], base_model: { provider_id: "1", model_key: "gpt-4o" } },
        { id: "s", label: "Sum", roles: ["summarizer"], base_model: { provider_id: "1", model_key: "gpt-4o" } },
      ],
    },
    interaction: { topology: { edges: [] } },
    ...raw,
  });
}

beforeEach(() => {
  useDesignerStore.setState({ artifact: null, layout: {}, edgeBends: {}, selection: null, dirty: false });
});

describe("removeNode prunes the protocol", () => {
  it("drops the node from order and phases (and phases it alone made up)", () => {
    seed({
      interaction: {
        topology: { edges: [] },
        protocol: {
          mechanism: "hybrid",
          order: ["b", "s", "a"],
          phases: [
            { mechanism: "simultaneous", participants: ["a", "b"] },
            { mechanism: "sequential", participants: ["s"] },
          ],
        },
      },
    });
    s().removeNode("s");
    expect(art().interaction.protocol?.order).toEqual(["b", "a"]);
    expect(art().interaction.protocol?.phases).toEqual([
      { mechanism: "simultaneous", participants: ["a", "b"] },
    ]);
  });
});

describe("addNode keeps a custom turn order complete", () => {
  it("appends a new speaking participant to a non-empty order", () => {
    seed({ interaction: { topology: { edges: [] }, protocol: { order: ["b", "a"] } } });
    const id = s().addNode();
    expect(art().interaction.protocol?.order).toEqual(["b", "a", id]);
  });

  it("leaves declaration order ([]) and judges alone", () => {
    seed();
    s().addNode();
    expect(art().interaction.protocol?.order).toEqual([]);
    seed({ interaction: { topology: { edges: [] }, protocol: { order: ["b", "a"] } } });
    s().addNode({ roles: ["judge"] });
    expect(art().interaction.protocol?.order).toEqual(["b", "a"]);
  });
});

describe("setAuthority keeps the resolution valid", () => {
  it("switches an incompatible resolution to the first compatible one", () => {
    seed({ agreement: { authority: "collective", resolution: "majority_vote" } });
    expect(s().setAuthority("judge_based")).toEqual({ from: "majority_vote", to: "argument_evaluation" });
    expect(art().agreement).toMatchObject({ authority: "judge_based", resolution: "argument_evaluation" });
    expect(s().setAuthority("collective")).toEqual({ from: "argument_evaluation", to: "majority_vote" });
  });

  it("keeps a compatible resolution", () => {
    seed({ agreement: { authority: "collective", resolution: "consensus" } });
    expect(s().setAuthority("hybrid")).toBeNull();
    expect(art().agreement?.resolution).toBe("consensus");
  });

  it("End connectors follow the authority at once (default derivation)", () => {
    seed({ agreement: { authority: "collective", resolution: "majority_vote" } });
    s().addJudge();
    const judgeId = art().participants.nodes.find((n) => n.roles.includes("judge"))!.id;
    expect(effectiveExitNodeIds(art())).toEqual(["a", "b"]);
    s().setAuthority("judge_based");
    expect(toStartEndEdges(art()).map((e) => e.id)).toContain(`${judgeId}->__end__`);
    expect(effectiveExitNodeIds(art())).toEqual([judgeId]);
  });
});

describe("addJudge", () => {
  it("adds a judge that inherits the shared model", () => {
    seed({ agreement: { authority: "judge_based", resolution: "argument_evaluation" } });
    const id = s().addJudge();
    const judge = art().participants.nodes.find((n) => n.id === id)!;
    expect(judge.roles).toEqual(["judge"]);
    expect(judge.base_model).toMatchObject({ provider_id: "1", model_key: "gpt-4o" });
  });

  it("connects the judge to End when the End connectors were set by hand", () => {
    seed({
      interaction: { topology: { edges: [], exit_nodes: ["a"] } },
      agreement: { authority: "judge_based", resolution: "argument_evaluation" },
    });
    const id = s().addJudge();
    expect(art().interaction.topology.exit_nodes).toEqual(["a", id]);
    s().resetExitNodes();
    expect(art().interaction.topology.exit_nodes).toBeNull();
  });
});

describe("turn badges and drift on the canvas projection", () => {
  it("projects turn numbers only under sequential + fixed", () => {
    seed({ interaction: { topology: { edges: [] }, protocol: { order: ["b", "a", "s"] } } });
    const turns = () => toFlowNodes(art(), {}, null).map((n) => [n.id, n.data.turn]);
    expect(turns()).toEqual([
      ["a", 2],
      ["b", 1],
      ["s", 3],
    ]);
    s().updateProtocol({ ordering: "randomized" });
    expect(turns().every(([, t]) => t === null)).toBe(true);
  });

  it("applyTopology clears drift; an edit brings it back; Re-apply restores", () => {
    seed();
    s().applyTopology("ring");
    expect(topologyStatus(art()).drifted).toBe(false);
    s().removeEdge("a->b");
    expect(topologyStatus(art()).label).toBe("Custom (edited from Ring)");
    s().applyTopology("ring");
    expect(topologyStatus(art()).drifted).toBe(false);
  });
});
