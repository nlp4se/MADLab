/**
 * Debate-level Interaction and Agreement scope (task 11.7).
 *
 * Pure helpers (no store access) that encode what the engine actually does
 * with the Interaction / Agreement settings, so the panels show a dependent
 * field only when it has an effect and disable options that would fail at run
 * time (with the engine's reason). Mirrors:
 *  - `backend/mad/engine/graph.py`: explicit edges win; otherwise the edges are
 *    derived from structure/pattern (grouped = fully connected within each
 *    `node.group`); undirected edges count as both arcs.
 *  - `backend/mad/engine/protocol.py`: `fixed` uses `protocol.order` (empty =
 *    declaration order), `randomized` shuffles per round, `coordinator` is
 *    under development, `hybrid` requires at least one phase (ValueError).
 *  - `backend/mad/engine/orchestrator.py`: judge-only nodes take no turn; the
 *    summarizer is the first summarizer-role node; the deciding judge is the
 *    first judge (in `exit_nodes` when set).
 *  - `backend/mad/engine/format.py`: `summarized` without a summarizer falls
 *    back to verbatim history and records a note (non-fatal).
 *  - `backend/mad/engine/agreement.py`: see {@link resolutionCompat}.
 */
import {
  APPLICABLE_TOPOLOGIES,
  type AgreementArtifact,
  type ApplicableTopology,
  type EdgeArtifact,
  type MADArtifact,
  type ParticipantNodeArtifact,
  type PhaseArtifact,
  type ProtocolArtifact,
  type TopologyArtifact,
} from "./artifact";
import { isJudgeOnly } from "./ioNodes";
import { buildTopologyEdges, fullyConnected, topologyLabel } from "./topology";

/* -------------------------------- topology -------------------------------- */

/**
 * Templates the toolbar offers. `grouped` is NOT offered: the engine derives
 * grouped edges from per-node group assignments (`node.group` /
 * `participants.groups`), which the designer has no UI for, so applying it
 * would draw groups the artifact does not record. Loaded artifacts that
 * declare `grouped` are still recognised (summary + drift detection).
 */
export const OFFERED_TOPOLOGIES: ApplicableTopology[] = APPLICABLE_TOPOLOGIES.filter(
  (t) => t !== "grouped",
);

/** The template the topology meta (structure/pattern) declares, if any. */
export function appliedTemplate(
  topology: Pick<TopologyArtifact, "structure" | "pattern">,
): ApplicableTopology | null {
  const structure = topology.structure ?? "fully_connected";
  if (structure === "fully_connected") return "fully_connected";
  if (structure === "grouped") return "grouped";
  return topology.pattern ?? null;
}

/**
 * The edges `template` produces over the current nodes. Uses the same builders
 * as the toolbar (`applyTopology`); `grouped` mirrors the engine's
 * `_grouped_edges` (fully connected within each `node.group`).
 */
export function templateEdges(
  template: ApplicableTopology,
  nodes: ParticipantNodeArtifact[],
): EdgeArtifact[] {
  if (template === "grouped") {
    const members = new Map<string, string[]>();
    for (const n of nodes) {
      if (n.group == null) continue;
      members.set(n.group, [...(members.get(n.group) ?? []), n.id]);
    }
    return [...members.values()].flatMap((ids) => fullyConnected(ids));
  }
  return buildTopologyEdges(
    template,
    nodes.map((n) => n.id),
  );
}

/**
 * The directed arcs an edge list means to the engine (`_to_arcs`): a directed
 * edge is one arc, an undirected edge both. Order-insensitive; labels/colours
 * are presentation and ignored.
 */
export function arcSet(edges: EdgeArtifact[]): Set<string> {
  const arcs = new Set<string>();
  for (const e of edges) {
    arcs.add(`${e.source}->${e.target}`);
    if (e.directed === false) arcs.add(`${e.target}->${e.source}`);
  }
  return arcs;
}

export function sameArcs(a: EdgeArtifact[], b: EdgeArtifact[]): boolean {
  const x = arcSet(a);
  const y = arcSet(b);
  if (x.size !== y.size) return false;
  for (const arc of x) if (!y.has(arc)) return false;
  return true;
}

export interface TopologyStatus {
  /** The declared template, or null (structured_network without a pattern). */
  template: ApplicableTopology | null;
  templateLabel: string;
  /** True when the drawn edges no longer match the template over the nodes. */
  drifted: boolean;
  /** True when the template can be re-applied from the toolbar/summary. */
  reappliable: boolean;
  /** No edges drawn: the engine builds the template's edges at run time. */
  derivedAtRunTime: boolean;
  /** "Chain" or "Custom (edited from Chain)". */
  label: string;
}

/** Drift detection between the drawn edges and the applied template. */
export function topologyStatus(
  artifact: MADArtifact,
  labelOf: (t: ApplicableTopology) => string = topologyLabel,
): TopologyStatus {
  const topology = artifact.interaction.topology;
  const template = appliedTemplate(topology);
  if (template === null) {
    return {
      template,
      templateLabel: "Custom",
      drifted: false,
      reappliable: false,
      derivedAtRunTime: false,
      label: "Custom",
    };
  }
  const templateLabel = labelOf(template);
  const expected = templateEdges(template, artifact.participants.nodes);
  const edges = topology.edges;
  // Explicit edges win in the engine; with none it derives the template's.
  const derivedAtRunTime = edges.length === 0 && expected.length > 0;
  const drifted = edges.length > 0 && !sameArcs(edges, expected);
  return {
    template,
    templateLabel,
    drifted,
    reappliable: drifted && OFFERED_TOPOLOGIES.includes(template),
    derivedAtRunTime,
    label: drifted ? `Custom (edited from ${templateLabel})` : templateLabel,
  };
}

/**
 * A template labeller backed by the taxonomy catalog (structure labels for
 * fully_connected / grouped, pattern labels otherwise), falling back to the
 * title-cased key. Shared by the Interaction summary and the toolbar.
 */
export function catalogTopologyLabel(
  getValue: (dim: string, sub: string, key: string) => { label: string } | undefined,
): (t: ApplicableTopology) => string {
  return (t) => {
    const sub = t === "fully_connected" || t === "grouped" ? "topology_structure" : "topology_pattern";
    return getValue("interaction", sub, t)?.label ?? topologyLabel(t);
  };
}

/**
 * The overwrite confirmation shared by the toolbar and the Re-apply action:
 * applying a template regenerates every edge, so ask when edges exist.
 */
export function confirmApplyTopology(
  artifact: MADArtifact | null,
  label: string,
): boolean {
  const hasGraph =
    (artifact?.participants.nodes.length ?? 0) > 0 &&
    (artifact?.interaction.topology.edges.length ?? 0) > 0;
  if (!hasGraph) return true;
  return window.confirm(
    `Apply the "${label}" topology?\n\n` +
      "This regenerates the connections between the current participants " +
      "and overrides the existing edges. Participant nodes are kept.",
  );
}

/* -------------------------------- protocol -------------------------------- */

/** Participants that take turns in the rounds (judge-only nodes do not). */
export function speakingNodes(nodes: ParticipantNodeArtifact[]): ParticipantNodeArtifact[] {
  return nodes.filter((n) => !isJudgeOnly(n));
}

/** Declaration order of the speaking participants. */
function declarationOrder(artifact: MADArtifact): string[] {
  return speakingNodes(artifact.participants.nodes).map((n) => n.id);
}

/** True when `protocol.order` is empty, i.e. declaration order applies. */
export function usesDeclarationOrder(artifact: MADArtifact): boolean {
  return (artifact.interaction.protocol?.order ?? []).length === 0;
}

/**
 * Who takes a turn, in order, under sequential + fixed ordering: the explicit
 * `protocol.order` (restricted to existing speaking nodes) when set, else the
 * declaration order (engine `_fixed_order` + the judge-only skip).
 */
export function effectiveTurnOrder(artifact: MADArtifact): string[] {
  const order = artifact.interaction.protocol?.order ?? [];
  const speaking = declarationOrder(artifact);
  if (order.length === 0) return speaking;
  const known = new Set(speaking);
  return order.filter((id, i) => known.has(id) && order.indexOf(id) === i);
}

/** Speaking participants a non-empty explicit order leaves out (they take no turn). */
export function missingFromTurnOrder(artifact: MADArtifact): string[] {
  if (usesDeclarationOrder(artifact)) return [];
  const listed = new Set(effectiveTurnOrder(artifact));
  return declarationOrder(artifact).filter((id) => !listed.has(id));
}

/** Store an order; an order equal to declaration order is stored as `[]`. */
function normalizeOrder(artifact: MADArtifact, order: string[]): string[] {
  const decl = declarationOrder(artifact);
  const same = order.length === decl.length && order.every((id, i) => id === decl[i]);
  return same ? [] : order;
}

/** The `protocol.order` after moving `id` by `delta` places (clamped). */
export function moveInTurnOrder(artifact: MADArtifact, id: string, delta: number): string[] {
  const order = effectiveTurnOrder(artifact);
  return normalizeOrder(artifact, moveItem(order, order.indexOf(id), delta));
}

/** The `protocol.order` after appending a participant left out of it. */
export function addToTurnOrder(artifact: MADArtifact, id: string): string[] {
  const order = effectiveTurnOrder(artifact);
  return normalizeOrder(artifact, order.includes(id) ? order : [...order, id]);
}

/**
 * Turn-number badges for the canvas: only under sequential + fixed ordering
 * (randomized/coordinator orders are not known at design time, and simultaneous
 * / hybrid have no single turn sequence).
 */
export function turnNumbers(artifact: MADArtifact): Map<string, number> {
  const protocol = artifact.interaction.protocol ?? {};
  const turns = new Map<string, number>();
  if ((protocol.mechanism ?? "sequential") !== "sequential") return turns;
  if ((protocol.ordering ?? "fixed") !== "fixed") return turns;
  effectiveTurnOrder(artifact).forEach((id, i) => turns.set(id, i + 1));
  return turns;
}

/** Which dependent protocol fields have an effect for the current mechanism. */
export function protocolVisibility(protocol: ProtocolArtifact) {
  const mechanism = protocol.mechanism ?? "sequential";
  const ordering = protocol.ordering ?? "fixed";
  const sequential = mechanism === "sequential";
  return {
    ordering: sequential,
    turnOrder: sequential && ordering === "fixed",
    randomizedNote: sequential && ordering === "randomized",
    simultaneousNote: mechanism === "simultaneous",
    phases: mechanism === "hybrid",
  };
}

/** The hybrid phases (never null). */
export function phasesOf(protocol: ProtocolArtifact | undefined): PhaseArtifact[] {
  return Array.isArray(protocol?.phases) ? protocol.phases : [];
}

/** Engine error for hybrid without phases (`_schedule_hybrid` ValueError). */
export function hybridPhasesError(protocol: ProtocolArtifact | undefined): string | null {
  if ((protocol?.mechanism ?? "sequential") !== "hybrid") return null;
  return phasesOf(protocol).length === 0
    ? "A hybrid protocol needs at least one phase: the run fails without one."
    : null;
}

/** Move `list[index]` by `delta` places (clamped); returns a new list. */
export function moveItem<T>(list: T[], index: number, delta: number): T[] {
  if (index < 0 || index >= list.length) return list;
  const target = Math.max(0, Math.min(list.length - 1, index + delta));
  if (target === index) return list;
  const next = [...list];
  const [item] = next.splice(index, 1);
  next.splice(target, 0, item);
  return next;
}

/**
 * Toggle a participant in a phase, keeping the phase's participants in
 * declaration order (`declaration` = all node ids in order).
 */
export function togglePhaseParticipant(
  phase: PhaseArtifact,
  id: string,
  on: boolean,
  declaration: string[],
): PhaseArtifact {
  const set = new Set(phase.participants);
  if (on) set.add(id);
  else set.delete(id);
  return { ...phase, participants: declaration.filter((x) => set.has(x)) };
}

/**
 * Drop a removed node from `protocol.order` and every phase. A phase whose
 * participants were ONLY that node is dropped too (empty would mean "every
 * participant", silently changing what the phase does).
 */
export function pruneProtocolRef(protocol: ProtocolArtifact, id: string): ProtocolArtifact {
  const next: ProtocolArtifact = {
    ...protocol,
    order: (protocol.order ?? []).filter((ref) => ref !== id),
  };
  if (Array.isArray(protocol.phases)) {
    next.phases = protocol.phases
      .filter((p) => !(p.participants.length > 0 && p.participants.every((ref) => ref === id)))
      .map((p) => ({ ...p, participants: p.participants.filter((ref) => ref !== id) }));
  }
  return next;
}

/* --------------------------------- format --------------------------------- */

/** The node the engine wires as summarizer (first summarizer-role node). */
export function summarizerNode(
  nodes: ParticipantNodeArtifact[],
): ParticipantNodeArtifact | undefined {
  return nodes.find((n) => (n.roles ?? []).includes("summarizer"));
}

/* -------------------------------- agreement ------------------------------- */

export type Authority = NonNullable<AgreementArtifact["authority"]>;
export type Resolution = NonNullable<AgreementArtifact["resolution"]>;

/** Resolution keys in schema/catalog order (first compatible = first here). */
export const RESOLUTION_KEYS: Resolution[] = [
  "argument_evaluation",
  "majority_vote",
  "weighted_vote",
  "scoring",
  "average",
  "consensus",
];

export interface ResolutionCompat {
  allowed: boolean;
  /** Short reason shown in the option label when not allowed. */
  short?: string;
  /** Full reason / behaviour note (engine-derived). */
  reason?: string;
}

/**
 * The authority x resolution compatibility matrix, derived from
 * `backend/mad/engine/agreement.py`:
 *  - collective (`_apply_resolution`): every debater-side strategy runs;
 *    `argument_evaluation` raises an ExecutionError (no judge) -> disabled.
 *  - judge_based (`_resolve_judge_based`): the judge's reply IS the decision;
 *    no resolution strategy is applied, so only `argument_evaluation` (the
 *    judge evaluating the debate) has an effect -> the others are disabled.
 *  - hybrid (`_resolve_hybrid`): everything runs; the judge is consulted when
 *    the collective step is undecided (tie / no consensus), or directly for
 *    `argument_evaluation`; `average` is never undecided.
 *  - other: under development (no executable semantics) -> nothing to filter.
 */
export function resolutionCompat(authority: Authority, resolution: Resolution): ResolutionCompat {
  switch (authority) {
    case "collective":
      if (resolution === "argument_evaluation") {
        return {
          allowed: false,
          short: "needs a judge",
          reason:
            "Argument evaluation needs a judge: under Collective authority the run stops with a wiring error. Use Judge-based or Hybrid authority.",
        };
      }
      return { allowed: true };
    case "judge_based":
      if (resolution === "argument_evaluation") {
        return { allowed: true, reason: "The judge evaluates the debate and its reply is the decision." };
      }
      return {
        allowed: false,
        short: "not applied by a judge",
        reason:
          "Under Judge-based authority the judge's reply is the decision, so votes, scores, averages and consensus are not applied. Use Hybrid to aggregate first and ask the judge only when that is inconclusive.",
      };
    case "hybrid":
      switch (resolution) {
        case "argument_evaluation":
          return { allowed: true, reason: "Goes straight to the judge (there is no collective step)." };
        case "average":
          return { allowed: true, reason: "An average always decides, so the judge is never consulted." };
        case "consensus":
          return { allowed: true, reason: "Without unanimity the judge decides." };
        default:
          return { allowed: true, reason: "On an exact tie the judge decides." };
      }
    default:
      return { allowed: true };
  }
}

/** First resolution compatible with `authority` (in {@link RESOLUTION_KEYS} order). */
export function firstCompatibleResolution(authority: Authority): Resolution {
  return RESOLUTION_KEYS.find((r) => resolutionCompat(authority, r).allowed) ?? "majority_vote";
}

/** Participants with the judge role. */
export function judgeNodes(nodes: ParticipantNodeArtifact[]): ParticipantNodeArtifact[] {
  return nodes.filter((n) => (n.roles ?? []).includes("judge"));
}

export type AgreementNotice =
  | { kind: "no_judge"; authority: "judge_based" | "hybrid" }
  | { kind: "judges_ignored"; judgeIds: string[] }
  | { kind: "custom_exits"; missingJudge: boolean };

/** Inline notices for the agreement settings vs the participants/connectors. */
export function agreementNotices(artifact: MADArtifact): AgreementNotice[] {
  const authority = artifact.agreement?.authority ?? "collective";
  const judges = judgeNodes(artifact.participants.nodes);
  const notices: AgreementNotice[] = [];
  if ((authority === "judge_based" || authority === "hybrid") && judges.length === 0) {
    notices.push({ kind: "no_judge", authority });
  }
  if (authority === "collective" && judges.length > 0) {
    notices.push({ kind: "judges_ignored", judgeIds: judges.map((j) => j.id) });
  }
  const exits = artifact.interaction.topology.exit_nodes;
  if (exits != null) {
    const judgeIds = new Set(judges.map((j) => j.id));
    notices.push({
      kind: "custom_exits",
      missingJudge:
        authority === "judge_based" && judges.length > 0 && !exits.some((id) => judgeIds.has(id)),
    });
  }
  return notices;
}
