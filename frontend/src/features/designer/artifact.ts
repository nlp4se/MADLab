/**
 * TypeScript model of the MAD Configuration Artifact (task 8.3).
 *
 * These interfaces mirror the backend Pydantic schema in
 * `backend/mad/taxonomy/schema.py` (`MADConfig` and friends). The typed API
 * client carries the artifact as an opaque `JsonObject` (see `api/types.ts`);
 * the designer is the feature that owns a richer model of it, so we narrow the
 * shape here.
 *
 * Only the structure the canvas reads/writes is modelled strictly
 * (participants.nodes = V, interaction.topology.edges = E, protocol order);
 * everything else is preserved verbatim so a round-trip through the designer
 * never drops fields it does not understand.
 *
 * While editing, node positions and edge bends live in the store's UI-only
 * `layout` / `edgeBends` (see `layout.ts`); on Save they are written into the
 * optional, presentation-only `ui` field so a config reopens with its layout.
 */

export interface PersonaArtifact {
  background?: string | null;
  personality?: string | null;
  stance?: string | null;
  template_ref?: string | null;
}

export interface BaseModelArtifact {
  provider_id?: string | null;
  model_key?: string | null;
  family?: "open_weight" | "closed_weight";
  temperature?: number;
  params?: Record<string, unknown>;
}

export interface ParticipantNodeArtifact {
  id: string;
  label: string;
  roles: string[];
  persona?: PersonaArtifact;
  base_model?: BaseModelArtifact;
  system_prompt?: string | null;
  group?: string | null;
}

export interface GroupArtifact {
  id: string;
  label: string;
  color?: string | null;
}

export interface ParticipantsArtifact {
  base_model_heterogeneity?: "homogeneous" | "heterogeneous";
  persona_heterogeneity?: "homogeneous" | "heterogeneous";
  persona_assignment?: "unspecified" | "manual" | "automatic";
  nodes: ParticipantNodeArtifact[];
  groups?: GroupArtifact[];
}

export interface EdgeArtifact {
  source: string;
  target: string;
  directed?: boolean;
  label?: string | null;
  color?: string | null;
}

export type TopologyStructure =
  | "fully_connected"
  | "grouped"
  | "structured_network";

export type TopologyPattern =
  | "chain"
  | "ring"
  | "star"
  | "tree"
  | "layered"
  | "sparse"
  | "bipartite";

export interface TopologyArtifact {
  adaptability?: "static" | "dynamic";
  dynamic_policy?: Record<string, unknown> | null;
  structure?: TopologyStructure;
  pattern?: TopologyPattern | null;
  edges: EdgeArtifact[];
  /**
   * Participants that receive the task input (the Start connectors). `null` /
   * absent = default: every participant that speaks in the rounds.
   */
  entry_nodes?: string[] | null;
  /**
   * Participants whose outputs form the final decision (the End connectors).
   * `null` / absent = default: the judge (judge_based) or the aggregated
   * debaters (otherwise). See `ioNodes.ts`.
   */
  exit_nodes?: string[] | null;
}

/** One phase of a hybrid protocol (mirrors the backend `Phase`). */
export interface PhaseArtifact {
  mechanism: "sequential" | "simultaneous";
  /** Participant ids acting in this phase; empty = every participant. */
  participants: string[];
}

export interface ProtocolArtifact {
  mechanism?: "sequential" | "simultaneous" | "hybrid";
  max_rounds?: number;
  ordering?: "fixed" | "randomized" | "coordinator";
  order?: string[];
  phases?: PhaseArtifact[] | null;
}

export interface ContentSpecArtifact {
  strategy?: "verbatim" | "summarized" | "other";
  metadata_signals?: string[];
  transform_ref?: string | null;
}

export interface FormatArtifact {
  syntax?: "natural_language" | "embeddings";
  content?: ContentSpecArtifact;
  memory?: "short_term" | "long_term" | "knowledge_retrieval" | "parametric";
}

export interface InteractionArtifact {
  topology: TopologyArtifact;
  protocol?: ProtocolArtifact;
  format?: FormatArtifact;
}

export interface AgreementArtifact {
  authority?: "collective" | "judge_based" | "hybrid" | "other";
  resolution?:
    | "argument_evaluation"
    | "majority_vote"
    | "weighted_vote"
    | "scoring"
    | "average"
    | "consensus";
  resolution_params?: Record<string, unknown>;
  output_schema?: Record<string, unknown> | null;
}

/** A human label for one template placeholder (mirrors the backend `AdHocField`). */
export interface AdHocFieldArtifact {
  key: string;
  label: string;
}

/**
 * The instance input (mirrors the backend `InputSpec`, task 11.10): a template
 * with `{{placeholder}}` tags resolved per run (single form values or mapped
 * CSV columns). The engine appends "Task: <resolved template>" to the system
 * prompt of the entry participants; judges see it in their context.
 */
export interface InputSpecArtifact {
  template?: string;
  placeholders?: string[];
  ad_hoc_fields?: AdHocFieldArtifact[];
  [key: string]: unknown;
}

export interface UiPoint {
  x: number;
  y: number;
}

/**
 * Presentation-only canvas layout (task 11.4), mirroring the backend
 * `UiLayout`. The engine ignores it.
 *   - `nodes`: node id (incl. the `__start__` / `__end__` sentinels) -> position.
 *   - `edges`: canvas edge id (`source->target`, `__start__->X`, `X->__end__`)
 *     -> knob offset from the straight midpoint of the two node centres.
 * Unknown/stale keys are ignored by the designer.
 */
export interface UiLayoutArtifact {
  nodes?: Record<string, UiPoint>;
  edges?: Record<string, UiPoint>;
}

export interface MADArtifact {
  schema_version?: string;
  id?: string;
  name: string;
  description?: string;
  participants: ParticipantsArtifact;
  interaction: InteractionArtifact;
  agreement?: AgreementArtifact;
  input_spec?: InputSpecArtifact;
  ui?: UiLayoutArtifact | null;
  // Any additional fields the designer doesn't model are preserved by spreads.
  [key: string]: unknown;
}

/** All canonical topology pattern keys (for the toolbar). */
export const TOPOLOGY_PATTERNS: TopologyPattern[] = [
  "chain",
  "ring",
  "star",
  "tree",
  "layered",
  "sparse",
  "bipartite",
];

/**
 * All topology templates the designer knows. "fully_connected" and "grouped"
 * are topology *structures*; the rest are structured-network *patterns*. The
 * designer treats them uniformly. Ordered structures-first. The toolbar offers
 * all of them except "grouped" (see `OFFERED_TOPOLOGIES` in
 * `interactionScope.ts`): the designer has no group-assignment UI.
 */
export type ApplicableTopology =
  | "fully_connected"
  | "grouped"
  | TopologyPattern;

export const APPLICABLE_TOPOLOGIES: ApplicableTopology[] = [
  "fully_connected",
  "grouped",
  "chain",
  "ring",
  "star",
  "tree",
  "layered",
  "sparse",
  "bipartite",
];

/**
 * Normalize an opaque artifact (`JsonObject` from the API) into a `MADArtifact`
 * with guaranteed `participants.nodes` and `interaction.topology.edges` arrays,
 * so the canvas never has to null-check the core graph shape. Unknown fields
 * pass through unchanged.
 */
export function normalizeArtifact(raw: Record<string, unknown>): MADArtifact {
  const artifact = { ...(raw as MADArtifact) };

  const participants = (artifact.participants ?? {}) as ParticipantsArtifact;
  artifact.participants = {
    ...participants,
    nodes: Array.isArray(participants.nodes) ? participants.nodes : [],
    groups: Array.isArray(participants.groups) ? participants.groups : [],
  };

  const interaction = (artifact.interaction ?? {}) as InteractionArtifact;
  const topology = (interaction.topology ?? {}) as TopologyArtifact;
  const protocol = (interaction.protocol ?? {}) as ProtocolArtifact;
  const format = (interaction.format ?? {}) as FormatArtifact;
  const content = (format.content ?? {}) as ContentSpecArtifact;
  artifact.interaction = {
    ...interaction,
    topology: {
      ...topology,
      edges: Array.isArray(topology.edges) ? topology.edges : [],
      structure: topology.structure ?? "fully_connected",
      adaptability: topology.adaptability ?? "static",
    },
    protocol: {
      mechanism: protocol.mechanism ?? "sequential",
      max_rounds: protocol.max_rounds ?? 1,
      ordering: protocol.ordering ?? "fixed",
      order: Array.isArray(protocol.order) ? protocol.order : [],
      ...protocol,
    },
    format: {
      syntax: format.syntax ?? "natural_language",
      memory: format.memory ?? "short_term",
      ...format,
      content: {
        strategy: content.strategy ?? "verbatim",
        metadata_signals: Array.isArray(content.metadata_signals)
          ? content.metadata_signals
          : [],
        ...content,
      },
    },
  };

  const agreement = (artifact.agreement ?? {}) as AgreementArtifact;
  artifact.agreement = {
    authority: agreement.authority ?? "collective",
    resolution: agreement.resolution ?? "majority_vote",
    resolution_params: agreement.resolution_params ?? {},
    ...agreement,
  };

  return artifact;
}
