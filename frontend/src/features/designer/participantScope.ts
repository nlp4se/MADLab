/**
 * Debate-level vs node-level scope for the Participants settings (task 11.6).
 *
 * Pure helpers (no store access) that encode the invariants the designer store
 * keeps between the dimension-level participant settings and the per-node
 * values the engine actually reads:
 *
 *  - Persona assignment gates personas: only `manual` makes persona fields
 *    editable; `unspecified` means "no personas" and `automatic` is under
 *    development (fields disabled).
 *  - Persona heterogeneity (only when `manual`): `homogeneous` = ONE shared
 *    persona applied to every node with the `debater` role (judges /
 *    summarizers keep their own); `heterogeneous` = per node.
 *  - Base model heterogeneity: `homogeneous` = ONE shared provider / model
 *    applied to ALL nodes (the provider-derived family follows it);
 *    `heterogeneous` = per node. Homogeneity compares provider/model only.
 *
 * The shared value is not a separate schema field (the schema is unchanged):
 * it is derived from a "source" node (first debater with persona data / first
 * node with a bound provider) and broadcast to the governed nodes. Loaded data
 * that contradicts the declared mode is NEVER rewritten here implicitly;
 * {@link detectConflicts} reports it so the UI can offer explicit fixes.
 */
import type {
  BaseModelArtifact,
  ParticipantNodeArtifact,
  ParticipantsArtifact,
  PersonaArtifact,
} from "./artifact";

/** The persona fields governed by the persona settings. */
export const PERSONA_FIELDS = [
  "background",
  "personality",
  "stance",
  "template_ref",
] as const;

/**
 * The base-model fields broadcast under a shared model. `family` is included
 * so the provider-derived family (written on bind, task 11.9) follows the
 * provider to every node, but it is NOT compared: see {@link COMPARED_MODEL_FIELDS}.
 */
export const MODEL_FIELDS = ["provider_id", "model_key", "family"] as const;

/**
 * The fields base-model homogeneity compares: provider and model only. The
 * family is derived from the provider, so it is never an independent source of
 * divergence (task 11.9).
 */
export const COMPARED_MODEL_FIELDS = ["provider_id", "model_key"] as const;

/** Schema default for `base_model.family` (used when no family is stored). */
const DEFAULT_FAMILY = "closed_weight";

export type PersonaFields = Pick<PersonaArtifact, (typeof PERSONA_FIELDS)[number]>;
export type ModelFields = Pick<BaseModelArtifact, (typeof MODEL_FIELDS)[number]>;

/* --------------------------------- modes --------------------------------- */

export type PersonaMode = "unspecified" | "automatic" | "shared" | "per_node";

/** Debate-level persona mode derived from assignment + heterogeneity. */
export function personaMode(p: ParticipantsArtifact): PersonaMode {
  const assignment = p.persona_assignment ?? "unspecified";
  if (assignment === "unspecified") return "unspecified";
  if (assignment === "automatic") return "automatic";
  return (p.persona_heterogeneity ?? "homogeneous") === "heterogeneous"
    ? "per_node"
    : "shared";
}

/** True when one shared base model governs every node. */
export function isModelShared(p: ParticipantsArtifact): boolean {
  return (p.base_model_heterogeneity ?? "homogeneous") === "homogeneous";
}

export function isDebater(node: Pick<ParticipantNodeArtifact, "roles">): boolean {
  return (node.roles ?? []).includes("debater");
}

/**
 * How the persona of one node is edited:
 *  - `disabled`: personas are off (unspecified / automatic);
 *  - `shared`: governed at debate level (read-only on the node);
 *  - `own`: edited on the node itself.
 */
export function nodePersonaScope(
  p: ParticipantsArtifact,
  node: ParticipantNodeArtifact,
): "disabled" | "shared" | "own" {
  const mode = personaMode(p);
  if (mode === "unspecified" || mode === "automatic") return "disabled";
  if (mode === "shared" && isDebater(node)) return "shared";
  return "own";
}

/* ------------------------------ value helpers ----------------------------- */

/** Normalize a governed value for comparison: blank / missing -> null. */
function norm(v: unknown): string | null {
  if (v == null) return null;
  const s = String(v);
  return s.trim() === "" ? null : s;
}

/** The governed persona fields, normalized (empty -> null). */
export function pickPersona(persona: PersonaArtifact | undefined): PersonaFields {
  return {
    background: norm(persona?.background),
    personality: norm(persona?.personality),
    stance: norm(persona?.stance),
    template_ref: norm(persona?.template_ref),
  };
}

/** The governed base-model fields, normalized (family falls back to default). */
export function pickModel(model: BaseModelArtifact | undefined): ModelFields {
  return {
    provider_id: norm(model?.provider_id),
    model_key: norm(model?.model_key),
    family: model?.family ?? DEFAULT_FAMILY,
  };
}

export function hasPersonaData(persona: PersonaArtifact | undefined): boolean {
  const p = pickPersona(persona);
  return PERSONA_FIELDS.some((f) => p[f] != null);
}

const personaSig = (n: ParticipantNodeArtifact) => JSON.stringify(pickPersona(n.persona));
const modelSig = (n: ParticipantNodeArtifact) => {
  const m = pickModel(n.base_model);
  return JSON.stringify(COMPARED_MODEL_FIELDS.map((f) => m[f]));
};

/** The source of the shared persona: first debater with persona data, else first debater. */
export function personaSourceNode(
  nodes: ParticipantNodeArtifact[],
): ParticipantNodeArtifact | undefined {
  const debaters = nodes.filter(isDebater);
  return debaters.find((n) => hasPersonaData(n.persona)) ?? debaters[0];
}

/** The source of the shared model: first node with a bound provider, else first node. */
export function modelSourceNode(
  nodes: ParticipantNodeArtifact[],
): ParticipantNodeArtifact | undefined {
  return nodes.find((n) => pickModel(n.base_model).provider_id != null) ?? nodes[0];
}

/** The shared persona (from the source debater), or empty when there is none. */
export function sharedPersona(nodes: ParticipantNodeArtifact[]): PersonaFields {
  return pickPersona(personaSourceNode(nodes)?.persona);
}

/** The shared model (from the source node), or the defaults when there is none. */
export function sharedModel(nodes: ParticipantNodeArtifact[]): ModelFields {
  return pickModel(modelSourceNode(nodes)?.base_model);
}

/** True when the debaters do not all carry the same persona. */
export function personasDiverge(nodes: ParticipantNodeArtifact[]): boolean {
  return new Set(nodes.filter(isDebater).map(personaSig)).size > 1;
}

/** True when the nodes do not all carry the same provider/model (family is derived). */
export function modelsDiverge(nodes: ParticipantNodeArtifact[]): boolean {
  return new Set(nodes.map(modelSig)).size > 1;
}

/* ------------------------------- transforms ------------------------------- */

/**
 * Merge a patch into a node, deep-merging `persona` and `base_model` so a
 * partial update (e.g. just `persona.stance`) keeps sibling fields.
 */
export function mergeNode(
  node: ParticipantNodeArtifact,
  patch: Partial<ParticipantNodeArtifact>,
): ParticipantNodeArtifact {
  return {
    ...node,
    ...patch,
    persona:
      patch.persona !== undefined ? { ...node.persona, ...patch.persona } : node.persona,
    base_model:
      patch.base_model !== undefined
        ? { ...node.base_model, ...patch.base_model }
        : node.base_model,
    id: node.id, // id is immutable through a patch
  };
}

/** Only the governed keys present in a patch (so broadcasts never leak others). */
function governedPatch<T extends object>(
  patch: T | undefined,
  fields: readonly string[],
): Partial<T> | null {
  if (!patch) return null;
  const out: Partial<T> = {};
  let any = false;
  for (const f of fields) {
    if (f in patch) {
      (out as Record<string, unknown>)[f] = (patch as Record<string, unknown>)[f];
      any = true;
    }
  }
  return any ? out : null;
}

/** Copy the source debater's persona to every debater. */
export function alignPersonas(nodes: ParticipantNodeArtifact[]): ParticipantNodeArtifact[] {
  const shared = sharedPersona(nodes);
  return nodes.map((n) => (isDebater(n) ? { ...n, persona: { ...n.persona, ...shared } } : n));
}

/** Copy the source node's provider/model/family to every node. */
export function alignModels(nodes: ParticipantNodeArtifact[]): ParticipantNodeArtifact[] {
  const shared = sharedModel(nodes);
  return nodes.map((n) => ({ ...n, base_model: { ...n.base_model, ...shared } }));
}

/** Remove every node's persona data (background/personality/stance/template). */
export function clearPersonas(nodes: ParticipantNodeArtifact[]): ParticipantNodeArtifact[] {
  return nodes.map((n) => (hasPersonaData(n.persona) ? { ...n, persona: {} } : n));
}

/** Apply a shared persona patch to every debater. */
export function broadcastPersona(
  nodes: ParticipantNodeArtifact[],
  patch: Partial<PersonaFields>,
): ParticipantNodeArtifact[] {
  return nodes.map((n) => (isDebater(n) ? { ...n, persona: { ...n.persona, ...patch } } : n));
}

/** Apply a shared model patch to every node. */
export function broadcastModel(
  nodes: ParticipantNodeArtifact[],
  patch: Partial<ModelFields>,
): ParticipantNodeArtifact[] {
  return nodes.map((n) => ({ ...n, base_model: { ...n.base_model, ...patch } }));
}

/**
 * Give a NEW node the shared values governing it (inherit on add): the shared
 * model when models are homogeneous, and the shared persona when it is a
 * debater under a shared persona. `existing` are the nodes already present.
 */
export function inheritShared(
  p: ParticipantsArtifact,
  existing: ParticipantNodeArtifact[],
  node: ParticipantNodeArtifact,
): ParticipantNodeArtifact {
  let next = node;
  if (isModelShared(p) && existing.length > 0) {
    next = { ...next, base_model: { ...next.base_model, ...sharedModel(existing) } };
  }
  if (personaMode(p) === "shared" && isDebater(next) && existing.some(isDebater)) {
    next = { ...next, persona: { ...next.persona, ...sharedPersona(existing) } };
  }
  return next;
}

/**
 * Apply a per-node patch while keeping the scope invariants:
 *  - a governed base-model change under a shared model is broadcast to all nodes;
 *  - a persona change on a debater under a shared persona is broadcast to all
 *    debaters;
 *  - a node that GAINS the debater role under a shared persona inherits it.
 */
export function applyNodePatch(
  p: ParticipantsArtifact,
  id: string,
  patch: Partial<ParticipantNodeArtifact>,
): ParticipantNodeArtifact[] {
  const before = p.nodes.find((n) => n.id === id);
  if (!before) return p.nodes;
  let nodes = p.nodes.map((n) => (n.id === id ? mergeNode(n, patch) : n));
  const after = nodes.find((n) => n.id === id)!;

  if (isModelShared(p)) {
    const modelPatch = governedPatch(patch.base_model, MODEL_FIELDS);
    if (modelPatch) nodes = broadcastModel(nodes, modelPatch);
  }

  if (personaMode(p) === "shared" && isDebater(after)) {
    const personaPatch = governedPatch(patch.persona, PERSONA_FIELDS);
    if (personaPatch) {
      nodes = broadcastPersona(nodes, personaPatch);
    } else if (!isDebater(before)) {
      // Gained the debater role: inherit the shared persona of the others.
      const others = nodes.filter((n) => n.id !== id);
      if (others.some(isDebater)) {
        const shared = sharedPersona(others);
        nodes = nodes.map((n) =>
          n.id === id ? { ...n, persona: { ...n.persona, ...shared } } : n,
        );
      }
    }
  }
  return nodes;
}

/* -------------------------------- conflicts ------------------------------- */

export type ParticipantConflictKind =
  | "personas_without_manual"
  | "persona_divergent"
  | "model_divergent";

export interface ParticipantConflict {
  kind: ParticipantConflictKind;
  /** Nodes whose data contradicts the declared mode (amber on the canvas). */
  nodeIds: string[];
  /** The node whose value "Make all match" would copy, if any. */
  sourceId?: string;
}

/**
 * Detect data that contradicts the declared participant modes (e.g. a loaded,
 * imported, or assistant-applied artifact). Nothing is rewritten; the UI offers
 * the fixes.
 */
export function detectConflicts(p: ParticipantsArtifact): ParticipantConflict[] {
  const nodes = p.nodes;
  const conflicts: ParticipantConflict[] = [];
  const mode = personaMode(p);

  if (mode === "unspecified") {
    const withPersona = nodes.filter((n) => hasPersonaData(n.persona));
    if (withPersona.length > 0) {
      conflicts.push({
        kind: "personas_without_manual",
        nodeIds: withPersona.map((n) => n.id),
      });
    }
  }

  if (mode === "shared" && personasDiverge(nodes)) {
    const source = personaSourceNode(nodes)!;
    const sig = personaSig(source);
    conflicts.push({
      kind: "persona_divergent",
      sourceId: source.id,
      nodeIds: nodes.filter((n) => isDebater(n) && personaSig(n) !== sig).map((n) => n.id),
    });
  }

  if (isModelShared(p) && modelsDiverge(nodes)) {
    const source = modelSourceNode(nodes)!;
    const sig = modelSig(source);
    conflicts.push({
      kind: "model_divergent",
      sourceId: source.id,
      nodeIds: nodes.filter((n) => modelSig(n) !== sig).map((n) => n.id),
    });
  }

  return conflicts;
}

/** Every node id involved in any participant-scope conflict. */
export function conflictNodeIds(p: ParticipantsArtifact): Set<string> {
  return new Set(detectConflicts(p).flatMap((c) => c.nodeIds));
}
