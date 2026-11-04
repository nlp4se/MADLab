/**
 * Designer state store (Zustand) — the two-way sync hub (Req 6.8).
 *
 * This store is the single source of truth while the designer is open. It holds
 * the live `MADArtifact` (V = participants.nodes, E = interaction.topology.edges)
 * plus a UI-only `LayoutMap` of node positions and `EdgeBendMap` of edge bends
 * (see `layout.ts` / `edgeGeometry.ts`). Both are seeded from and saved into
 * the artifact's presentation-only `ui` field (task 11.4), which the engine
 * ignores.
 *
 * Both directions of the sync flow through here:
 *   - artifact -> canvas: `selectFlowGraph` derives React Flow nodes/edges from
 *     the artifact + layout, so the rendered graph is always a projection of the
 *     artifact.
 *   - canvas -> artifact: every canvas edit (addNode, moveNode, connectNodes,
 *     removeNode, removeEdge, applyTopology) mutates the artifact (and layout)
 *     in place, so what gets persisted via PUT /api/configs/{id} reflects the
 *     canvas exactly.
 *
 * A `dirty` flag tracks unsaved edits so the toolbar can enable/disable Save and
 * warn on navigation.
 */
import { create } from "zustand";

import {
  normalizeArtifact,
  type AgreementArtifact,
  type ApplicableTopology,
  type EdgeArtifact,
  type FormatArtifact,
  type InteractionArtifact,
  type MADArtifact,
  type ParticipantNodeArtifact,
  type ParticipantsArtifact,
} from "./artifact";
import type { FieldError } from "@/api";
import {
  effectiveEntryNodeIds,
  effectiveExitNodeIds,
  entryConnectorId,
  exitConnectorId,
  isJudgeOnly,
  parseConnectorId,
} from "./ioNodes";
import {
  autoLayout,
  reconcileLayout,
  seedLayout,
  type LayoutMap,
  type NodeSizeMap,
  type XYPosition,
} from "./layout";
import {
  alignModels,
  alignPersonas,
  applyNodePatch,
  broadcastModel,
  broadcastPersona,
  clearPersonas,
  inheritShared,
  type ModelFields,
  type PersonaFields,
} from "./participantScope";
import { END_NODE_ID, START_NODE_ID } from "./StartEndNodes";
import { withPlaceholderLabel, withTemplate } from "./inputEditor";
import { buildTopologyEdges, topologyMeta } from "./topology";
import {
  firstCompatibleResolution,
  pruneProtocolRef,
  resolutionCompat,
  type Authority,
  type Resolution,
} from "./interactionScope";

/**
 * UI-only edge bends (task 11.4): canvas edge id -> offset of the edge's drag
 * knob from the straight midpoint between its two node centres (see
 * `edgeGeometry.ts`). Absent = default shape (straight, or the reciprocal-pair
 * bow). Persisted into `artifact.ui.edges` on Save.
 */
export type EdgeBendMap = Record<string, XYPosition>;

/** The synthetic Start/End sentinel ids that may carry a stored position. */
const SENTINEL_IDS = [START_NODE_ID, END_NODE_ID];

/**
 * A selected canvas element (participant node or edge), the synthetic Start
 * node (`input`: it opens the Input panel, task 11.10; never deletable), or
 * nothing.
 */
export type Selection =
  | { kind: "node"; id: string }
  | { kind: "edge"; id: string }
  | { kind: "input" }
  | null;

export interface DesignerState {
  /** The config's DB id (route param); null before a config is loaded. */
  configId: number | null;
  /** The live artifact — the canvas is a projection of this (Req 6.8). */
  artifact: MADArtifact | null;
  /**
   * UI-only node positions, keyed by node id (incl. the Start/End sentinels).
   * Seeded from `artifact.ui.nodes` on load; written back into `ui` on Save.
   */
  layout: LayoutMap;
  /** UI-only edge bends keyed by canvas edge id (see {@link EdgeBendMap}). */
  edgeBends: EdgeBendMap;
  /** Currently selected node/edge (for the inspector, task 8.4). */
  selection: Selection;
  /** Unsaved-edits flag; set by every mutation, cleared on load/save. */
  dirty: boolean;
  /** Field errors from the last server-side validation (Req 7.3), if any. */
  validationErrors: FieldError[];

  /** Replace the whole artifact (e.g. on load or after a save round-trip). */
  loadArtifact: (configId: number, raw: Record<string, unknown>) => void;
  /**
   * Replace the artifact from an AI-assistant proposal (task 11.1).
   *
   * Like {@link loadArtifact} it normalizes the raw artifact and reconciles the
   * canvas layout, but it keeps the current `configId` and — crucially — marks
   * the store `dirty` so the user can review on the canvas and then Save (an
   * applied proposal is an unsaved edit, unlike a fresh load).
   */
  setArtifactFromAssistant: (raw: Record<string, unknown>) => void;
  /**
   * Edit the config name / description (task 11.10, designer header). The
   * name is trimmed and an empty one is rejected (returns false, nothing
   * changes); an unchanged value is a no-op. Saved with the existing Save
   * (the backend syncs the configurations row from the artifact).
   */
  updateMeta: (patch: { name?: string; description?: string }) => boolean;
  /**
   * Edit the input template (task 11.10): placeholders are re-detected and the
   * per-placeholder labels synced (see `inputEditor.ts`).
   */
  updateInputTemplate: (template: string) => void;
  /** Set the run-form label of one template placeholder. */
  updateInputLabel: (key: string, label: string) => void;
  /** Add a new participant node with sensible defaults; returns its id. */
  addNode: (partial?: Partial<ParticipantNodeArtifact>) => string;
  /** Patch a single participant node's fields (Req 1.*, inspector). */
  updateNode: (id: string, patch: Partial<ParticipantNodeArtifact>) => void;
  /**
   * Raw patch of participant-dimension-level fields (heterogeneity,
   * assignment). Does NOT touch node data — used e.g. by the conflict fixes
   * "Switch to heterogeneous" / "Switch to Manual". The panel's mode selects
   * use the scope-aware setters below.
   */
  updateParticipants: (
    patch: Partial<Omit<ParticipantsArtifact, "nodes" | "groups">>,
  ) => void;
  /**
   * Scope-aware participant settings (task 11.6). Switching assignment to
   * `unspecified` clears every node's persona; switching a heterogeneity to
   * `homogeneous` copies the source node's value to every governed node (the
   * UI confirms first when they diverge).
   */
  setPersonaAssignment: (
    value: NonNullable<ParticipantsArtifact["persona_assignment"]>,
  ) => void;
  setPersonaHeterogeneity: (
    value: NonNullable<ParticipantsArtifact["persona_heterogeneity"]>,
  ) => void;
  setModelHeterogeneity: (
    value: NonNullable<ParticipantsArtifact["base_model_heterogeneity"]>,
  ) => void;
  /** Edit the shared persona: applied to every debater-role node. */
  updateSharedPersona: (patch: Partial<PersonaFields>) => void;
  /** Edit the shared provider/model (+ derived family): applied to every node. */
  updateSharedModel: (patch: Partial<ModelFields>) => void;
  /** Conflict fix: copy the source debater's persona to every debater. */
  alignPersonas: () => void;
  /** Conflict fix: copy the source node's model to every node. */
  alignModels: () => void;
  /** Conflict fix / unspecified switch: clear every node's persona. */
  clearPersonas: () => void;
  /** Patch a single edge's properties (name/colour/direction, Req 6.4). */
  updateEdge: (edgeId: string, patch: Partial<EdgeArtifact>) => void;
  /** Patch the topology meta (adaptability/structure/pattern) without touching E. */
  updateTopologyMeta: (
    patch: Partial<
      Pick<
        InteractionArtifact["topology"],
        "adaptability" | "structure" | "pattern" | "dynamic_policy"
      >
    >,
  ) => void;
  /** Patch the protocol (mechanism/max_rounds/ordering). */
  updateProtocol: (
    patch: Partial<NonNullable<InteractionArtifact["protocol"]>>,
  ) => void;
  /** Patch the format (syntax/content/memory + metadata signals). */
  updateFormat: (patch: Partial<FormatArtifact>) => void;
  /** Patch the agreement (authority/resolution/params/output_schema). */
  updateAgreement: (patch: Partial<AgreementArtifact>) => void;
  /**
   * Set the agreement authority keeping the resolution valid (task 11.7): if
   * the current resolution is incompatible with the new authority (see
   * `resolutionCompat`), switch to the first compatible one and return the
   * switch so the UI can say so; `null` when the resolution was kept.
   */
  setAuthority: (authority: Authority) => { from: Resolution; to: Resolution } | null;
  /**
   * Add a judge-role participant (inheriting the shared values, task 11.6);
   * when the End connectors are set by hand under judge-based / hybrid
   * authority, the new judge is connected to End. Returns its id.
   */
  addJudge: () => string;
  /** Reset the End connectors to the default derivation (`exit_nodes: null`). */
  resetExitNodes: () => void;
  /** Record server-side validation field errors (Req 7.3). */
  setValidationErrors: (errors: FieldError[]) => void;
  /** Update a node's canvas position (UI-only layout). */
  moveNode: (id: string, position: XYPosition) => void;
  /** Set an edge's bend (knob offset from the centres' midpoint); marks dirty. */
  setEdgeBend: (edgeId: string, offset: XYPosition) => void;
  /** Reset an edge to its default shape; marks dirty. */
  resetEdgeBend: (edgeId: string) => void;
  /** Create a directed edge between two existing nodes (no self/dup edges). */
  connectNodes: (source: string, target: string) => void;
  /** Remove a node and every edge incident to it. */
  removeNode: (id: string) => void;
  /** Remove a single edge by its synthetic id (`source->target`). */
  removeEdge: (edgeId: string) => void;
  /**
   * Start/End IO connectors (task 11.2). Each materializes the current
   * *effective* list (explicit or default, see `ioNodes.ts`) into
   * `interaction.topology.entry_nodes` / `exit_nodes` minus / plus `id`.
   * Removing the last connector leaves an empty list on purpose: Save
   * validation then reports "must be non-empty".
   */
  removeEntryNode: (id: string) => void;
  addEntryNode: (id: string) => void;
  removeExitNode: (id: string) => void;
  addExitNode: (id: string) => void;
  /**
   * Delete any canvas edge by its id, routing to the right action: a real
   * participant edge -> `removeEdge`; `__start__->X` -> `removeEntryNode(X)`;
   * `X->__end__` -> `removeExitNode(X)`. Used by the edge context menu, the
   * keyboard Delete, and the toolbar Delete.
   */
  deleteCanvasEdge: (edgeId: string) => void;
  /** Apply a topology template, regenerating E over the current nodes (Req 6.5). */
  applyTopology: (topology: ApplicableTopology) => void;
  /**
   * Re-run the flow-aware auto layout over the whole canvas (participants AND
   * Start/End, task 11.8), replacing every edge bend with the ones the layout
   * needs to route edges around node boxes. `sizes` are React Flow's measured
   * node sizes when available (else rendering-matched estimates).
   */
  relayout: (sizes?: NodeSizeMap | null) => void;
  /** Set the current selection. */
  setSelection: (selection: Selection) => void;
  /** Mark the artifact as saved (clears `dirty` and validation errors). */
  markSaved: () => void;
}

/** Synthetic, stable id for an edge derived from its endpoints. */
export function edgeId(edge: Pick<EdgeArtifact, "source" | "target">): string {
  return `${edge.source}->${edge.target}`;
}

/** Generate a unique node id not already used in the artifact. */
function nextNodeId(artifact: MADArtifact): string {
  const used = new Set(artifact.participants.nodes.map((n) => n.id));
  let i = artifact.participants.nodes.length + 1;
  let candidate = `participant-${i}`;
  while (used.has(candidate)) {
    i += 1;
    candidate = `participant-${i}`;
  }
  return candidate;
}

/** A fresh participant node with defaults (Req 7.1: immediately valid). */
function defaultNode(
  id: string,
  index: number,
  partial?: Partial<ParticipantNodeArtifact>,
): ParticipantNodeArtifact {
  const { id: _ignored, ...rest } = partial ?? {};
  void _ignored;
  return {
    label: partial?.label ?? `Participant ${index}`,
    roles: partial?.roles ?? ["debater"],
    persona: partial?.persona ?? {},
    base_model: partial?.base_model ?? { family: "closed_weight" },
    system_prompt: partial?.system_prompt ?? null,
    group: partial?.group ?? null,
    ...rest,
    id, // id always wins (supplied explicitly by the caller)
  };
}

export const useDesignerStore = create<DesignerState>((set, get) => ({
  configId: null,
  artifact: null,
  layout: {},
  edgeBends: {},
  selection: null,
  dirty: false,
  validationErrors: [],

  loadArtifact: (configId, raw) => {
    const artifact = normalizeArtifact(raw);
    // Seed from the persisted presentation-only layout. Without one (no `ui`,
    // new config) the whole canvas is auto-laid-out, Start/End and bends
    // included; a stored layout is kept and only participants without a
    // position are placed in free space (Start/End without a stored position
    // fall back to their computed default in the canvas projection).
    const seeded = seedLayout(artifact, artifact.ui?.nodes, SENTINEL_IDS, {
      bends: sanitizeBends(artifact.ui?.edges),
    });
    set({
      configId,
      artifact,
      layout: seeded.layout,
      edgeBends: seeded.bends ?? pruneBends(artifact, sanitizeBends(artifact.ui?.edges)),
      selection: null,
      dirty: false,
      validationErrors: [],
    });
  },

  setArtifactFromAssistant: (raw) => {
    const artifact = normalizeArtifact(raw);
    const state = get();
    // The live canvas wins for ids that carry over (the proposal's `ui`, if
    // any, may be a stale echo of the last save); a proposal `ui` only fills
    // ids the canvas doesn't know; anything else is placed in free space near
    // its neighbours (or, if no position is known at all, auto-laid-out).
    const proposalUi = artifact.ui ?? null;
    const mergedBends = { ...sanitizeBends(proposalUi?.edges), ...state.edgeBends };
    const seeded = seedLayout(
      artifact,
      { ...(proposalUi?.nodes ?? {}), ...state.layout },
      SENTINEL_IDS,
      { bends: mergedBends },
    );
    set({
      artifact,
      layout: seeded.layout,
      edgeBends: seeded.bends ?? pruneBends(artifact, mergedBends),
      selection: null,
      // An applied proposal is an unsaved edit — the user reviews then Saves.
      dirty: true,
      validationErrors: [],
    });
  },

  updateMeta: (patch) => {
    const state = get();
    if (!state.artifact) return false;
    const next: MADArtifact = { ...state.artifact };
    if (patch.name !== undefined) {
      const name = patch.name.trim();
      if (!name) return false;
      next.name = name;
    }
    if (patch.description !== undefined) next.description = patch.description.trim();
    const changed =
      next.name !== state.artifact.name ||
      (next.description ?? "") !== (state.artifact.description ?? "");
    if (changed) set({ artifact: next, dirty: true });
    return true;
  },

  updateInputTemplate: (template) => {
    const state = get();
    if (!state.artifact) return;
    set({
      artifact: {
        ...state.artifact,
        input_spec: withTemplate(state.artifact.input_spec, template),
      },
      dirty: true,
    });
  },

  updateInputLabel: (key, label) => {
    const state = get();
    if (!state.artifact) return;
    set({
      artifact: {
        ...state.artifact,
        input_spec: withPlaceholderLabel(state.artifact.input_spec, key, label),
      },
      dirty: true,
    });
  },

  addNode: (partial) => {
    const state = get();
    if (!state.artifact) return "";
    const id = partial?.id ?? nextNodeId(state.artifact);
    const index = state.artifact.participants.nodes.length + 1;
    const existing = state.artifact.participants.nodes;
    // New nodes inherit the debate-level shared persona/model (task 11.6).
    const node = inheritShared(
      state.artifact.participants,
      existing,
      defaultNode(id, index, partial),
    );
    const nodes = [...existing, node];
    // A custom (non-empty) turn order must not silently leave a new speaking
    // participant out: under fixed ordering it would never take a turn.
    const protocol = state.artifact.interaction.protocol;
    const order = protocol?.order ?? [];
    const interaction =
      protocol && order.length > 0 && !isJudgeOnly(node) && !order.includes(id)
        ? { ...state.artifact.interaction, protocol: { ...protocol, order: [...order, id] } }
        : state.artifact.interaction;
    const artifact: MADArtifact = {
      ...state.artifact,
      participants: { ...state.artifact.participants, nodes },
      interaction,
    };
    // Free space near the new node's neighbours; nothing else moves.
    const layout = reconcileLayout(artifact, state.layout, { bends: state.edgeBends });
    set({ artifact, layout, dirty: true });
    return id;
  },

  updateNode: (id, patch) => {
    const state = get();
    if (!state.artifact) return;
    // Broadcasts governed values / inherits on role gain (task 11.6).
    const nodes = applyNodePatch(state.artifact.participants, id, patch);
    set({
      artifact: {
        ...state.artifact,
        participants: { ...state.artifact.participants, nodes },
      },
      dirty: true,
    });
  },

  updateParticipants: (patch) => {
    const state = get();
    if (!state.artifact) return;
    set({
      artifact: {
        ...state.artifact,
        participants: { ...state.artifact.participants, ...patch },
      },
      dirty: true,
    });
  },

  setPersonaAssignment: (value) =>
    patchParticipants(get, set, (p) => ({
      ...p,
      persona_assignment: value,
      nodes: value === "unspecified" ? clearPersonas(p.nodes) : p.nodes,
    })),

  setPersonaHeterogeneity: (value) =>
    patchParticipants(get, set, (p) => ({
      ...p,
      persona_heterogeneity: value,
      nodes:
        value === "homogeneous" && p.persona_assignment === "manual"
          ? alignPersonas(p.nodes)
          : p.nodes,
    })),

  setModelHeterogeneity: (value) =>
    patchParticipants(get, set, (p) => ({
      ...p,
      base_model_heterogeneity: value,
      nodes: value === "homogeneous" ? alignModels(p.nodes) : p.nodes,
    })),

  updateSharedPersona: (patch) =>
    patchParticipants(get, set, (p) => ({
      ...p,
      nodes: broadcastPersona(p.nodes, patch),
    })),

  updateSharedModel: (patch) =>
    patchParticipants(get, set, (p) => ({
      ...p,
      nodes: broadcastModel(p.nodes, patch),
    })),

  alignPersonas: () =>
    patchParticipants(get, set, (p) => ({ ...p, nodes: alignPersonas(p.nodes) })),

  alignModels: () =>
    patchParticipants(get, set, (p) => ({ ...p, nodes: alignModels(p.nodes) })),

  clearPersonas: () =>
    patchParticipants(get, set, (p) => ({ ...p, nodes: clearPersonas(p.nodes) })),

  updateEdge: (id, patch) => {
    const state = get();
    if (!state.artifact) return;
    const edges = state.artifact.interaction.topology.edges.map((e) =>
      edgeId(e) === id ? { ...e, ...patch } : e,
    );
    set({ artifact: withEdges(state.artifact, edges), dirty: true });
  },

  updateTopologyMeta: (patch) => {
    const state = get();
    if (!state.artifact) return;
    set({
      artifact: {
        ...state.artifact,
        interaction: {
          ...state.artifact.interaction,
          topology: { ...state.artifact.interaction.topology, ...patch },
        },
      },
      dirty: true,
    });
  },

  updateProtocol: (patch) => {
    const state = get();
    if (!state.artifact) return;
    set({
      artifact: {
        ...state.artifact,
        interaction: {
          ...state.artifact.interaction,
          protocol: { ...state.artifact.interaction.protocol, ...patch },
        },
      },
      dirty: true,
    });
  },

  updateFormat: (patch) => {
    const state = get();
    if (!state.artifact) return;
    const current = state.artifact.interaction.format ?? {};
    // `content` is a nested object; merge it rather than replace wholesale.
    const content =
      patch.content !== undefined
        ? { ...current.content, ...patch.content }
        : current.content;
    set({
      artifact: {
        ...state.artifact,
        interaction: {
          ...state.artifact.interaction,
          format: { ...current, ...patch, content },
        },
      },
      dirty: true,
    });
  },

  updateAgreement: (patch) => {
    const state = get();
    if (!state.artifact) return;
    set({
      artifact: {
        ...state.artifact,
        agreement: { ...state.artifact.agreement, ...patch },
      },
      dirty: true,
    });
  },

  setAuthority: (authority) => {
    const state = get();
    if (!state.artifact) return null;
    const current = state.artifact.agreement?.resolution ?? "majority_vote";
    const compatible = resolutionCompat(authority, current).allowed;
    const resolution = compatible ? current : firstCompatibleResolution(authority);
    set({
      artifact: {
        ...state.artifact,
        agreement: { ...state.artifact.agreement, authority, resolution },
      },
      dirty: true,
    });
    return compatible ? null : { from: current, to: resolution };
  },

  addJudge: () => {
    const id = get().addNode({ label: "Judge", roles: ["judge"] });
    const artifact = get().artifact;
    const authority = artifact?.agreement?.authority;
    // Hand-set End connectors don't follow the default rule: connect the new
    // judge so it can actually decide.
    if (
      artifact?.interaction.topology.exit_nodes != null &&
      (authority === "judge_based" || authority === "hybrid")
    ) {
      get().addExitNode(id);
    }
    return id;
  },

  resetExitNodes: () => {
    const state = get();
    if (!state.artifact) return;
    const artifact = withTopologyPatch(state.artifact, { exit_nodes: null });
    set({ artifact, edgeBends: pruneBends(artifact, state.edgeBends), dirty: true });
  },

  setValidationErrors: (errors) => set({ validationErrors: errors }),

  moveNode: (id, position) => {
    const state = get();
    if (!state.artifact) return;
    set({ layout: { ...state.layout, [id]: position }, dirty: true });
  },

  setEdgeBend: (id, offset) => {
    const state = get();
    if (!state.artifact) return;
    set({
      edgeBends: { ...state.edgeBends, [id]: { x: offset.x, y: offset.y } },
      dirty: true,
    });
  },

  resetEdgeBend: (id) => {
    const state = get();
    if (!state.artifact) return;
    const { [id]: _removed, ...edgeBends } = state.edgeBends;
    void _removed;
    set({ edgeBends, dirty: true });
  },

  connectNodes: (source, target) => {
    const state = get();
    if (!state.artifact) return;
    if (source === target) return; // no self-loops on the canvas
    const edges = state.artifact.interaction.topology.edges;
    const exists = edges.some(
      (e) => e.source === source && e.target === target,
    );
    if (exists) return; // no duplicate directed edges
    const nextEdges = [...edges, { source, target, directed: true }];
    set({
      artifact: withEdges(state.artifact, nextEdges),
      dirty: true,
    });
  },

  removeNode: (id) => {
    const state = get();
    if (!state.artifact) return;
    const nodes = state.artifact.participants.nodes.filter((n) => n.id !== id);
    const edges = state.artifact.interaction.topology.edges.filter(
      (e) => e.source !== id && e.target !== id,
    );
    const topology = state.artifact.interaction.topology;
    const protocol = state.artifact.interaction.protocol;
    const artifact: MADArtifact = {
      ...state.artifact,
      participants: { ...state.artifact.participants, nodes },
      interaction: {
        ...state.artifact.interaction,
        topology: {
          ...topology,
          edges,
          // Drop the deleted node from the IO lists (only touch them if set).
          ...(topology.entry_nodes != null
            ? { entry_nodes: withoutRef(topology.entry_nodes, id) }
            : {}),
          ...(topology.exit_nodes != null
            ? { exit_nodes: withoutRef(topology.exit_nodes, id) }
            : {}),
        },
        // Prune the turn order and the hybrid phases (task 11.7).
        protocol: protocol ? pruneProtocolRef(protocol, id) : undefined,
      },
    };
    const { [id]: _removed, ...layout } = state.layout;
    void _removed;
    const sel = state.selection;
    const selection =
      (sel?.kind === "node" && sel.id === id) ||
      (sel?.kind === "edge" &&
        (sel.id.startsWith(`${id}->`) || sel.id.endsWith(`->${id}`)))
        ? null
        : sel;
    set({
      artifact,
      layout,
      edgeBends: pruneBends(artifact, state.edgeBends),
      selection,
      dirty: true,
    });
  },

  removeEdge: (id) => {
    const state = get();
    if (!state.artifact) return;
    const edges = state.artifact.interaction.topology.edges.filter(
      (e) => edgeId(e) !== id,
    );
    const selection =
      state.selection?.kind === "edge" && state.selection.id === id
        ? null
        : state.selection;
    const artifact = withEdges(state.artifact, edges);
    set({
      artifact,
      edgeBends: pruneBends(artifact, state.edgeBends),
      selection,
      dirty: true,
    });
  },

  removeEntryNode: (id) => {
    const state = get();
    if (!state.artifact) return;
    const entries = effectiveEntryNodeIds(state.artifact).filter((x) => x !== id);
    const artifact = withTopologyPatch(state.artifact, { entry_nodes: entries });
    set({
      artifact,
      edgeBends: pruneBends(artifact, state.edgeBends),
      selection: clearSelectionIf(state.selection, entryConnectorId(id)),
      dirty: true,
    });
  },

  addEntryNode: (id) => {
    const state = get();
    if (!state.artifact || !hasNode(state.artifact, id)) return;
    const entries = effectiveEntryNodeIds(state.artifact);
    if (entries.includes(id)) return;
    const artifact = withTopologyPatch(state.artifact, {
      entry_nodes: [...entries, id],
    });
    set({ artifact, edgeBends: pruneBends(artifact, state.edgeBends), dirty: true });
  },

  removeExitNode: (id) => {
    const state = get();
    if (!state.artifact) return;
    const exits = effectiveExitNodeIds(state.artifact).filter((x) => x !== id);
    const artifact = withTopologyPatch(state.artifact, { exit_nodes: exits });
    set({
      artifact,
      edgeBends: pruneBends(artifact, state.edgeBends),
      selection: clearSelectionIf(state.selection, exitConnectorId(id)),
      dirty: true,
    });
  },

  addExitNode: (id) => {
    const state = get();
    if (!state.artifact || !hasNode(state.artifact, id)) return;
    const exits = effectiveExitNodeIds(state.artifact);
    if (exits.includes(id)) return;
    const artifact = withTopologyPatch(state.artifact, { exit_nodes: [...exits, id] });
    set({ artifact, edgeBends: pruneBends(artifact, state.edgeBends), dirty: true });
  },

  deleteCanvasEdge: (id) => {
    const connector = parseConnectorId(id);
    if (connector?.kind === "entry") get().removeEntryNode(connector.nodeId);
    else if (connector?.kind === "exit") get().removeExitNode(connector.nodeId);
    else get().removeEdge(id);
  },

  applyTopology: (topology) => {
    const state = get();
    if (!state.artifact) return;
    const nodeIds = state.artifact.participants.nodes.map((n) => n.id);
    const edges = buildTopologyEdges(topology, nodeIds);
    const meta = topologyMeta(topology);
    const artifact: MADArtifact = {
      ...state.artifact,
      interaction: {
        ...state.artifact.interaction,
        topology: {
          ...state.artifact.interaction.topology,
          edges,
          structure: meta.structure,
          pattern: meta.pattern,
        },
      },
    };
    set({ artifact, edgeBends: pruneBends(artifact, state.edgeBends), dirty: true });
  },

  relayout: (sizes) => {
    const state = get();
    if (!state.artifact) return;
    // `sizes` may be anything when wired straight to an event handler; the
    // layout only uses entries that look like a measured size.
    const measured = sizes && typeof sizes === "object" ? sizes : null;
    const { positions, bends } = autoLayout(state.artifact, measured);
    set({ layout: positions, edgeBends: bends, dirty: true });
  },

  setSelection: (selection) => set({ selection }),

  markSaved: () => set({ dirty: false, validationErrors: [] }),
}));

/** Replace `participants` via `fn` and mark dirty (no-op without an artifact). */
function patchParticipants(
  get: () => DesignerState,
  set: (partial: Partial<DesignerState>) => void,
  fn: (p: ParticipantsArtifact) => ParticipantsArtifact,
): void {
  const artifact = get().artifact;
  if (!artifact) return;
  set({
    artifact: { ...artifact, participants: fn(artifact.participants) },
    dirty: true,
  });
}

/** Immutably patch the artifact's topology (e.g. entry_nodes / exit_nodes). */
function withTopologyPatch(
  artifact: MADArtifact,
  patch: Partial<MADArtifact["interaction"]["topology"]>,
): MADArtifact {
  return {
    ...artifact,
    interaction: {
      ...artifact.interaction,
      topology: { ...artifact.interaction.topology, ...patch },
    },
  };
}

/** True if `id` is an existing participant node. */
function hasNode(artifact: MADArtifact, id: string): boolean {
  return artifact.participants.nodes.some((n) => n.id === id);
}

/**
 * Drop `id` from an IO list. If that empties a list which was non-empty, reset
 * it to `null` (the default) rather than leaving an invalid empty list behind;
 * a list the user already emptied by hand stays empty.
 */
function withoutRef(list: string[], id: string): string[] | null {
  const next = list.filter((ref) => ref !== id);
  return next.length === 0 && list.length > 0 ? null : next;
}

/** Clear the selection when it is the (now removed) edge `id`. */
function clearSelectionIf(selection: Selection, id: string): Selection {
  return selection?.kind === "edge" && selection.id === id ? null : selection;
}

/** Immutably replace the artifact's topology edge list. */
function withEdges(artifact: MADArtifact, edges: EdgeArtifact[]): MADArtifact {
  return {
    ...artifact,
    interaction: {
      ...artifact.interaction,
      topology: { ...artifact.interaction.topology, edges },
    },
  };
}

/* ------------------------ persisted layout (task 11.4) ------------------------ */

/**
 * Every edge id the canvas currently draws: the real participant edges plus
 * the Start/End IO connectors (`__start__->X`, `X->__end__`).
 */
export function canvasEdgeIds(artifact: MADArtifact): Set<string> {
  return new Set([
    ...artifact.interaction.topology.edges.map(edgeId),
    ...effectiveEntryNodeIds(artifact).map(entryConnectorId),
    ...effectiveExitNodeIds(artifact).map(exitConnectorId),
  ]);
}

/** Keep only bends whose edge still exists on the canvas. */
export function pruneBends(artifact: MADArtifact, bends: EdgeBendMap): EdgeBendMap {
  const live = canvasEdgeIds(artifact);
  const next: EdgeBendMap = {};
  for (const [id, offset] of Object.entries(bends)) {
    if (live.has(id)) next[id] = offset;
  }
  return next;
}

/** Drop malformed points from a stored `ui.edges` map (defensive). */
function sanitizeBends(raw: Record<string, unknown> | null | undefined): EdgeBendMap {
  const next: EdgeBendMap = {};
  for (const [id, p] of Object.entries(raw ?? {})) {
    const pt = p as XYPosition | null;
    if (pt && Number.isFinite(pt.x) && Number.isFinite(pt.y)) {
      next[id] = { x: pt.x, y: pt.y };
    }
  }
  return next;
}

/**
 * Return `artifact` with its presentation-only `ui` replaced by the current
 * canvas layout + edge bends, restricted to ids that exist (participants, the
 * Start/End sentinels when they have participants to flank, and live canvas
 * edges). Used by Save so the persisted config carries its layout.
 */
export function withUiLayout(
  artifact: MADArtifact,
  layout: LayoutMap,
  edgeBends: EdgeBendMap,
): MADArtifact {
  const participantIds = artifact.participants.nodes.map((n) => n.id);
  const nodeIds = participantIds.length > 0 ? [...participantIds, ...SENTINEL_IDS] : [];
  const nodes: Record<string, XYPosition> = {};
  for (const id of nodeIds) {
    const p = layout[id];
    if (p) nodes[id] = { x: p.x, y: p.y };
  }
  const edges: Record<string, XYPosition> = {};
  for (const [id, p] of Object.entries(pruneBends(artifact, edgeBends))) {
    edges[id] = { x: p.x, y: p.y };
  }
  return { ...artifact, ui: { nodes, edges } };
}
