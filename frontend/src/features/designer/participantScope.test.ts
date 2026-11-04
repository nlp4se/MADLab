import { beforeEach, describe, expect, it } from "vitest";

import type { ParticipantsArtifact } from "./artifact";
import { useDesignerStore } from "./designerStore";
import { toFlowNodes } from "./flowGraph";
import {
  applyNodePatch,
  conflictNodeIds,
  detectConflicts,
  inheritShared,
  modelsDiverge,
  nodePersonaScope,
  personaMode,
} from "./participantScope";

/**
 * Debate-level vs node-level scope for the Participants settings (task 11.6):
 * the pure invariants (participantScope.ts) and the store actions that use them.
 */

const ANGEL = { background: "Optimist", personality: "Warm", stance: "Pro", template_ref: null };
const DEVIL = { background: "Critic", personality: "Sharp", stance: "Con", template_ref: null };

function participants(overrides: Partial<ParticipantsArtifact> = {}): ParticipantsArtifact {
  return {
    persona_assignment: "manual",
    persona_heterogeneity: "homogeneous",
    base_model_heterogeneity: "homogeneous",
    nodes: [
      { id: "a", label: "Alpha", roles: ["debater"], persona: { ...ANGEL } },
      { id: "b", label: "Beta", roles: ["debater"], persona: { ...ANGEL } },
      { id: "j", label: "Judge", roles: ["judge"], persona: { stance: "Neutral" } },
    ],
    ...overrides,
  };
}

function seed(p: ParticipantsArtifact) {
  useDesignerStore.getState().loadArtifact(1, {
    name: "Scope fixture",
    participants: p,
    interaction: { topology: { edges: [] } },
  });
}

const state = () => useDesignerStore.getState();
const nodes = () => state().artifact!.participants.nodes;
const node = (id: string) => nodes().find((n) => n.id === id)!;

describe("participantScope — modes and node scope", () => {
  it("derives the persona mode from assignment + heterogeneity", () => {
    expect(personaMode(participants({ persona_assignment: "unspecified" }))).toBe("unspecified");
    expect(personaMode(participants({ persona_assignment: "automatic" }))).toBe("automatic");
    expect(personaMode(participants())).toBe("shared");
    expect(personaMode(participants({ persona_heterogeneity: "heterogeneous" }))).toBe("per_node");
    // Schema defaults: unspecified.
    expect(personaMode({ nodes: [] })).toBe("unspecified");
  });

  it("shared persona governs debaters only; judges keep their own", () => {
    const p = participants();
    expect(nodePersonaScope(p, p.nodes[0])).toBe("shared");
    expect(nodePersonaScope(p, p.nodes[2])).toBe("own");
    const off = participants({ persona_assignment: "unspecified" });
    expect(nodePersonaScope(off, off.nodes[2])).toBe("disabled");
  });
});

describe("participantScope — broadcast and inherit", () => {
  it("a persona edit on a debater is broadcast to every debater (not the judge)", () => {
    const next = applyNodePatch(participants(), "a", { persona: { stance: "Strongly pro" } });
    expect(next.find((n) => n.id === "b")!.persona?.stance).toBe("Strongly pro");
    expect(next.find((n) => n.id === "j")!.persona?.stance).toBe("Neutral");
  });

  it("a model edit under a shared model is broadcast to every node", () => {
    const next = applyNodePatch(participants(), "j", {
      base_model: { provider_id: "1", model_key: "gpt-4o" },
    });
    expect(next.every((n) => n.base_model?.model_key === "gpt-4o")).toBe(true);
  });

  it("heterogeneous modes keep edits on the node", () => {
    const p = participants({
      persona_heterogeneity: "heterogeneous",
      base_model_heterogeneity: "heterogeneous",
    });
    const next = applyNodePatch(p, "a", {
      persona: { stance: "Solo" },
      base_model: { model_key: "m1" },
    });
    expect(next.find((n) => n.id === "b")!.persona?.stance).toBe("Pro");
    expect(next.find((n) => n.id === "b")!.base_model?.model_key).toBeUndefined();
  });

  it("a node gaining the debater role inherits the shared persona", () => {
    const next = applyNodePatch(participants(), "j", { roles: ["judge", "debater"] });
    expect(next.find((n) => n.id === "j")!.persona).toMatchObject(ANGEL);
  });

  it("a new node inherits the shared model and (if a debater) persona", () => {
    const p = participants();
    p.nodes = p.nodes.map((n) => ({ ...n, base_model: { provider_id: "2", model_key: "llama3" } }));
    const fresh = inheritShared(p, p.nodes, { id: "c", label: "C", roles: ["debater"] });
    expect(fresh.persona).toMatchObject(ANGEL);
    expect(fresh.base_model).toMatchObject({ provider_id: "2", model_key: "llama3" });
    const judge = inheritShared(p, p.nodes, { id: "k", label: "K", roles: ["judge"] });
    expect(judge.persona).toBeUndefined();
  });
});

describe("participantScope — conflict detection", () => {
  it("is clean when data matches the declared modes", () => {
    expect(detectConflicts(participants())).toEqual([]);
  });

  it("flags personas present under Unspecified", () => {
    const [c] = detectConflicts(participants({ persona_assignment: "unspecified" }));
    expect(c.kind).toBe("personas_without_manual");
    expect(c.nodeIds).toEqual(["a", "b", "j"]);
  });

  it("flags divergent debater personas under homogeneous (source = first debater)", () => {
    const p = participants();
    p.nodes[1] = { ...p.nodes[1], persona: { ...DEVIL } };
    const [c] = detectConflicts(p);
    expect(c).toEqual({ kind: "persona_divergent", sourceId: "a", nodeIds: ["b"] });
  });

  it("flags divergent models under homogeneous (source = first bound node)", () => {
    const p = participants();
    p.nodes[1] = { ...p.nodes[1], base_model: { provider_id: "1", model_key: "gpt-4o" } };
    const [c] = detectConflicts(p);
    expect(c.kind).toBe("model_divergent");
    expect(c.sourceId).toBe("b");
    expect(conflictNodeIds(p)).toEqual(new Set(["a", "j"]));
  });

  it("homogeneity compares provider/model only, not the derived family (task 11.9)", () => {
    const p = participants();
    p.nodes = p.nodes.map((n, i) => ({
      ...n,
      base_model: {
        provider_id: "1",
        model_key: "gpt-4o",
        family: i === 0 ? "open_weight" : "closed_weight",
      },
    }));
    expect(modelsDiverge(p.nodes)).toBe(false);
    expect(detectConflicts(p)).toEqual([]);
  });

  it("the family still follows a shared provider change", () => {
    const next = applyNodePatch(participants(), "a", {
      base_model: { provider_id: "2", model_key: null, family: "open_weight" },
    });
    expect(next.every((n) => n.base_model?.family === "open_weight")).toBe(true);
  });
});

describe("designer store — participant scope invariants", () => {
  beforeEach(() => {
    useDesignerStore.setState({ artifact: null, layout: {}, selection: null, dirty: false });
  });

  it("switching to unspecified clears every persona but keeps system prompts", () => {
    const p = participants();
    p.nodes[0] = { ...p.nodes[0], system_prompt: "Be brief." };
    seed(p);
    state().setPersonaAssignment("unspecified");
    expect(nodes().every((n) => !n.persona?.stance && !n.persona?.background)).toBe(true);
    expect(node("a").system_prompt).toBe("Be brief.");
    expect(state().artifact!.participants.persona_assignment).toBe("unspecified");
  });

  it("heterogeneous -> homogeneous copies the first debater's persona (divergent case)", () => {
    const p = participants({ persona_heterogeneity: "heterogeneous" });
    p.nodes[1] = { ...p.nodes[1], persona: { ...DEVIL } };
    seed(p);
    state().setPersonaHeterogeneity("homogeneous");
    expect(node("b").persona).toMatchObject(ANGEL);
    expect(node("j").persona?.stance).toBe("Neutral");
  });

  it("heterogeneous -> homogeneous leaves already-agreeing nodes unchanged", () => {
    seed(participants({ persona_heterogeneity: "heterogeneous" }));
    const before = JSON.stringify(nodes().map((n) => n.persona));
    state().setPersonaHeterogeneity("homogeneous");
    expect(JSON.stringify(nodes().map((n) => n.persona))).toBe(before);
  });

  it("model heterogeneous -> homogeneous copies the first bound node's model to all", () => {
    const p = participants({ base_model_heterogeneity: "heterogeneous" });
    p.nodes[1] = { ...p.nodes[1], base_model: { provider_id: "2", model_key: "llama3" } };
    seed(p);
    state().setModelHeterogeneity("homogeneous");
    expect(nodes().every((n) => n.base_model?.model_key === "llama3")).toBe(true);
  });

  it("shared editors broadcast and new nodes inherit", () => {
    seed(participants());
    state().updateSharedModel({ provider_id: "1", model_key: "gpt-4o-mini" });
    state().updateSharedPersona({ stance: "Contrarian" });
    expect(nodes().every((n) => n.base_model?.model_key === "gpt-4o-mini")).toBe(true);
    expect(node("b").persona?.stance).toBe("Contrarian");
    expect(node("j").persona?.stance).toBe("Neutral");

    const id = state().addNode();
    expect(node(id).base_model?.model_key).toBe("gpt-4o-mini");
    expect(node(id).persona?.stance).toBe("Contrarian");
  });

  it("loading a contradicting artifact does NOT rewrite it; the fixes do", () => {
    const p = participants();
    p.nodes[1] = { ...p.nodes[1], persona: { ...DEVIL } };
    seed(p);
    expect(node("b").persona).toMatchObject(DEVIL); // untouched on load
    expect(state().dirty).toBe(false);

    state().alignPersonas();
    expect(node("b").persona).toMatchObject(ANGEL);
    expect(detectConflicts(state().artifact!.participants)).toEqual([]);
  });

  it("setArtifactFromAssistant keeps contradicting data as proposed", () => {
    seed(participants());
    const p = participants({ persona_assignment: "unspecified" });
    state().setArtifactFromAssistant({
      name: "Proposal",
      participants: p,
      interaction: { topology: { edges: [] } },
    });
    expect(node("a").persona).toMatchObject(ANGEL);
    expect(detectConflicts(state().artifact!.participants)[0].kind).toBe(
      "personas_without_manual",
    );
  });

  it("canvas projection reflects shared-model changes and conflicts at once", () => {
    const p = participants();
    p.nodes[1] = { ...p.nodes[1], base_model: { provider_id: "1", model_key: "gpt-4o" } };
    seed(p);
    let flow = toFlowNodes(state().artifact!, state().layout, null);
    expect(flow.filter((n) => n.data.conflict).map((n) => n.id)).toEqual(["a", "j"]);

    state().alignModels();
    flow = toFlowNodes(state().artifact!, state().layout, null);
    expect(flow.every((n) => n.data.modelKey === "gpt-4o" && n.data.providerId === "1")).toBe(true);
    expect(flow.some((n) => n.data.conflict)).toBe(false);

    state().updateSharedModel({ provider_id: "2", model_key: "llama3" });
    flow = toFlowNodes(state().artifact!, state().layout, null);
    expect(flow.every((n) => n.data.modelKey === "llama3")).toBe(true);
  });
});
