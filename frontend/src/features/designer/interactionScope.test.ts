import { describe, expect, it } from "vitest";

import { normalizeArtifact, type MADArtifact, type ParticipantNodeArtifact } from "./artifact";
import {
  OFFERED_TOPOLOGIES,
  RESOLUTION_KEYS,
  addToTurnOrder,
  agreementNotices,
  effectiveTurnOrder,
  firstCompatibleResolution,
  hybridPhasesError,
  missingFromTurnOrder,
  moveInTurnOrder,
  moveItem,
  protocolVisibility,
  pruneProtocolRef,
  resolutionCompat,
  sameArcs,
  togglePhaseParticipant,
  topologyStatus,
  turnNumbers,
  type Authority,
} from "./interactionScope";
import { buildTopologyEdges } from "./topology";

/** Pure Interaction/Agreement scope helpers (task 11.7). */

const debater = (id: string, extra: Partial<ParticipantNodeArtifact> = {}) => ({
  id,
  label: id.toUpperCase(),
  roles: ["debater"],
  ...extra,
});

function make(raw: Record<string, unknown> = {}): MADArtifact {
  return normalizeArtifact({
    name: "scope",
    participants: { nodes: [debater("a"), debater("b"), debater("c")] },
    interaction: { topology: { edges: [] } },
    ...raw,
  });
}

function withTopology(a: MADArtifact, topology: Partial<MADArtifact["interaction"]["topology"]>) {
  return { ...a, interaction: { ...a.interaction, topology: { ...a.interaction.topology, ...topology } } };
}

function withProtocol(a: MADArtifact, protocol: MADArtifact["interaction"]["protocol"]) {
  return { ...a, interaction: { ...a.interaction, protocol: { ...a.interaction.protocol, ...protocol } } };
}

describe("topology drift detection", () => {
  const ids = ["a", "b", "c"];
  const chainApplied = () =>
    withTopology(make(), {
      structure: "structured_network",
      pattern: "chain",
      edges: buildTopologyEdges("chain", ids),
    });

  it("matches the applied template", () => {
    const s = topologyStatus(chainApplied());
    expect(s).toMatchObject({ template: "chain", drifted: false, label: "Chain" });
  });

  it("is order-insensitive and ignores label/colour", () => {
    const edges = buildTopologyEdges("chain", ids)
      .reverse()
      .map((e) => ({ ...e, label: "x", color: "#fff" }));
    expect(topologyStatus(withTopology(chainApplied(), { edges })).drifted).toBe(false);
  });

  it("reports Custom (edited from <template>) after editing edges", () => {
    const a = chainApplied();
    const edited = withTopology(a, { edges: a.interaction.topology.edges.slice(1) });
    const s = topologyStatus(edited);
    expect(s.drifted).toBe(true);
    expect(s.reappliable).toBe(true);
    expect(s.label).toBe("Custom (edited from Chain)");
  });

  it("compares against the template rebuilt over the CURRENT nodes", () => {
    const a = chainApplied();
    const grown = {
      ...a,
      participants: { ...a.participants, nodes: [...a.participants.nodes, debater("d")] },
    };
    expect(topologyStatus(grown).drifted).toBe(true);
  });

  it("an undirected edge counts as both arcs (engine _to_arcs)", () => {
    const fc = withTopology(make(), {
      structure: "fully_connected",
      edges: [
        { source: "a", target: "b", directed: false },
        { source: "a", target: "c", directed: false },
        { source: "b", target: "c", directed: false },
      ],
    });
    expect(topologyStatus(fc).drifted).toBe(false);
    expect(sameArcs([{ source: "a", target: "b", directed: false }], [{ source: "a", target: "b" }])).toBe(false);
  });

  it("no drawn edges: not drifted, derived at run time", () => {
    const s = topologyStatus(make());
    expect(s).toMatchObject({ template: "fully_connected", drifted: false, derivedAtRunTime: true });
  });

  it("grouped mirrors the engine (node.group) and is never offered/re-applied", () => {
    expect(OFFERED_TOPOLOGIES).not.toContain("grouped");
    const a = make({
      participants: {
        groups: [{ id: "g1", label: "G1" }],
        nodes: [debater("a", { group: "g1" }), debater("b", { group: "g1" }), debater("c")],
      },
    });
    const ok = withTopology(a, {
      structure: "grouped",
      edges: [
        { source: "a", target: "b" },
        { source: "b", target: "a" },
      ],
    });
    expect(topologyStatus(ok).drifted).toBe(false);
    const edited = withTopology(ok, { edges: [{ source: "a", target: "c" }] });
    expect(topologyStatus(edited)).toMatchObject({ drifted: true, reappliable: false });
  });
});

describe("turn order (sequential + fixed)", () => {
  const withJudge = () =>
    make({
      participants: {
        nodes: [debater("a"), { id: "j", label: "J", roles: ["judge"] }, debater("b"), debater("c")],
      },
    });

  it("empty order = declaration order of the speaking participants", () => {
    expect(effectiveTurnOrder(withJudge())).toEqual(["a", "b", "c"]);
    expect(missingFromTurnOrder(withJudge())).toEqual([]);
  });

  it("moving writes an explicit order; moving back normalizes to []", () => {
    const a = withJudge();
    const moved = moveInTurnOrder(a, "c", -1);
    expect(moved).toEqual(["a", "c", "b"]);
    const back = moveInTurnOrder(withProtocol(a, { order: moved }), "c", 1);
    expect(back).toEqual([]);
  });

  it("a partial explicit order leaves participants out (they never speak)", () => {
    const a = withProtocol(withJudge(), { order: ["b", "a"] });
    expect(effectiveTurnOrder(a)).toEqual(["b", "a"]);
    expect(missingFromTurnOrder(a)).toEqual(["c"]);
    expect(addToTurnOrder(a, "c")).toEqual(["b", "a", "c"]);
  });

  it("turn numbers only under sequential + fixed, judges excluded", () => {
    const a = withProtocol(withJudge(), { order: ["c", "j", "a", "b"] });
    expect([...turnNumbers(a)]).toEqual([
      ["c", 1],
      ["a", 2],
      ["b", 3],
    ]);
    expect(turnNumbers(withProtocol(a, { ordering: "randomized" })).size).toBe(0);
    expect(turnNumbers(withProtocol(a, { mechanism: "simultaneous" })).size).toBe(0);
    expect(turnNumbers(withProtocol(a, { mechanism: "hybrid" })).size).toBe(0);
  });
});

describe("protocol visibility per mechanism / ordering", () => {
  it.each([
    [{ mechanism: "sequential", ordering: "fixed" }, { ordering: true, turnOrder: true, randomizedNote: false, simultaneousNote: false, phases: false }],
    [{ mechanism: "sequential", ordering: "randomized" }, { ordering: true, turnOrder: false, randomizedNote: true, simultaneousNote: false, phases: false }],
    [{ mechanism: "sequential", ordering: "coordinator" }, { ordering: true, turnOrder: false, randomizedNote: false, simultaneousNote: false, phases: false }],
    [{ mechanism: "simultaneous", ordering: "fixed" }, { ordering: false, turnOrder: false, randomizedNote: false, simultaneousNote: true, phases: false }],
    [{ mechanism: "hybrid", ordering: "fixed" }, { ordering: false, turnOrder: false, randomizedNote: false, simultaneousNote: false, phases: true }],
  ] as const)("%o", (protocol, expected) => {
    expect(protocolVisibility(protocol)).toEqual(expected);
  });
});

describe("hybrid phases", () => {
  it("errors only for hybrid without phases", () => {
    expect(hybridPhasesError({ mechanism: "hybrid", phases: [] })).toMatch(/at least one phase/);
    expect(hybridPhasesError({ mechanism: "hybrid", phases: null })).not.toBeNull();
    expect(
      hybridPhasesError({ mechanism: "hybrid", phases: [{ mechanism: "sequential", participants: [] }] }),
    ).toBeNull();
    expect(hybridPhasesError({ mechanism: "sequential", phases: [] })).toBeNull();
  });

  it("moves items with clamping", () => {
    expect(moveItem([1, 2, 3], 0, 1)).toEqual([2, 1, 3]);
    expect(moveItem([1, 2, 3], 2, 1)).toEqual([1, 2, 3]);
  });

  it("toggles participants in declaration order", () => {
    const phase = { mechanism: "sequential" as const, participants: ["c"] };
    expect(togglePhaseParticipant(phase, "a", true, ["a", "b", "c"]).participants).toEqual(["a", "c"]);
    expect(togglePhaseParticipant(phase, "c", false, ["a", "b", "c"]).participants).toEqual([]);
  });

  it("pruning drops the node from order and phases, and phases it alone made up", () => {
    const pruned = pruneProtocolRef(
      {
        mechanism: "hybrid",
        order: ["a", "s"],
        phases: [
          { mechanism: "simultaneous", participants: ["a", "s"] },
          { mechanism: "sequential", participants: ["s"] },
          { mechanism: "sequential", participants: [] },
        ],
      },
      "s",
    );
    expect(pruned.order).toEqual(["a"]);
    expect(pruned.phases).toEqual([
      { mechanism: "simultaneous", participants: ["a"] },
      { mechanism: "sequential", participants: [] },
    ]);
  });
});

describe("agreement compatibility matrix (engine-derived)", () => {
  const allowed = (authority: Authority) =>
    RESOLUTION_KEYS.filter((r) => resolutionCompat(authority, r).allowed);

  it("collective: everything but argument_evaluation (no judge -> wiring error)", () => {
    expect(allowed("collective")).toEqual(RESOLUTION_KEYS.filter((r) => r !== "argument_evaluation"));
    expect(resolutionCompat("collective", "argument_evaluation").reason).toMatch(/judge/i);
  });

  it("judge_based: only argument_evaluation (the judge's reply is the decision)", () => {
    expect(allowed("judge_based")).toEqual(["argument_evaluation"]);
  });

  it("hybrid and other: every resolution", () => {
    expect(allowed("hybrid")).toEqual(RESOLUTION_KEYS);
    expect(allowed("other")).toEqual(RESOLUTION_KEYS);
  });

  it("every disallowed pair carries a short and a full reason; first compatible is allowed", () => {
    for (const authority of ["collective", "judge_based", "hybrid", "other"] as Authority[]) {
      for (const r of RESOLUTION_KEYS) {
        const c = resolutionCompat(authority, r);
        if (!c.allowed) {
          expect(c.short).toBeTruthy();
          expect(c.reason).toBeTruthy();
        }
      }
      expect(resolutionCompat(authority, firstCompatibleResolution(authority)).allowed).toBe(true);
    }
    expect(firstCompatibleResolution("collective")).toBe("majority_vote");
    expect(firstCompatibleResolution("judge_based")).toBe("argument_evaluation");
  });
});

describe("agreement notices", () => {
  const judge = { id: "j", label: "J", roles: ["judge"] };
  const kinds = (a: MADArtifact) => agreementNotices(a).map((n) => n.kind);

  it("judge_based / hybrid without a judge -> no_judge", () => {
    expect(kinds(make({ agreement: { authority: "judge_based", resolution: "argument_evaluation" } }))).toEqual(["no_judge"]);
    expect(kinds(make({ agreement: { authority: "hybrid" } }))).toEqual(["no_judge"]);
  });

  it("collective with judges -> judges_ignored", () => {
    const a = make({ participants: { nodes: [debater("a"), judge] } });
    expect(kinds(a)).toEqual(["judges_ignored"]);
  });

  it("hand-set End connectors are flagged; judge_based needs a judge among them", () => {
    const a = withTopology(
      make({
        participants: { nodes: [debater("a"), judge] },
        agreement: { authority: "judge_based", resolution: "argument_evaluation" },
      }),
      { exit_nodes: ["a"] },
    );
    expect(agreementNotices(a)).toEqual([{ kind: "custom_exits", missingJudge: true }]);
  });
});
