/**
 * Start/End IO connections (task 11.2) — the single rule shared by the canvas
 * projection (`flowGraph.ts`), the designer store, and the tests.
 *
 * The artifact carries two optional lists on `interaction.topology`:
 *   - `entry_nodes`: participants that receive the task input (Start -> X);
 *   - `exit_nodes`:  participants whose outputs form the final decision (X -> End).
 * `null`/absent means "default", which mirrors what the engine
 * (`backend/mad/engine/orchestrator.py`) does today:
 *   - entries = every participant that speaks in the rounds, i.e. every node
 *     that is not judge-only (`_is_judge_only`: has "judge" but not "debater");
 *   - exits   = judge_based -> the first judge-role node (`_deciding_judge`);
 *               hybrid      -> the aggregated debaters + the first judge (the
 *                              vote step plus its judge fallback);
 *               otherwise   -> the aggregated debaters (non-judge,
 *                              non-summarizer nodes, `_debater_outputs`).
 *
 * The synthetic connector edge ids are namespaced with the sentinel Start/End
 * node ids (`__start__->X`, `X->__end__`) so they never collide with a real
 * participant edge id (`source->target`).
 */
import type { MADArtifact, ParticipantNodeArtifact } from "./artifact";
import { END_NODE_ID, START_NODE_ID } from "./StartEndNodes";

const START_PREFIX = `${START_NODE_ID}->`;
const END_SUFFIX = `->${END_NODE_ID}`;

/** Mirror of the engine's `_is_judge_only`: a judge that is not also a debater. */
export function isJudgeOnly(node: Pick<ParticipantNodeArtifact, "roles">): boolean {
  const roles = node.roles ?? [];
  return roles.includes("judge") && !roles.includes("debater");
}

/** Nodes the engine aggregates in collective resolution (non-judge, non-summarizer). */
function aggregatedNodeIds(artifact: MADArtifact): string[] {
  return artifact.participants.nodes
    .filter((n) => {
      const roles = n.roles ?? [];
      return !roles.includes("judge") && !roles.includes("summarizer");
    })
    .map((n) => n.id);
}

/** First judge-role node in declaration order, or null. */
function firstJudgeId(artifact: MADArtifact): string | null {
  return (
    artifact.participants.nodes.find((n) => (n.roles ?? []).includes("judge"))?.id ??
    null
  );
}

/** Keep only ids that reference an existing participant (defensive). */
function existing(artifact: MADArtifact, ids: string[]): string[] {
  const known = new Set(artifact.participants.nodes.map((n) => n.id));
  return ids.filter((id) => known.has(id));
}

/** Participants that receive the task input (explicit list, else the default). */
export function effectiveEntryNodeIds(artifact: MADArtifact): string[] {
  const explicit = artifact.interaction.topology.entry_nodes;
  if (explicit != null) return existing(artifact, explicit);
  return artifact.participants.nodes.filter((n) => !isJudgeOnly(n)).map((n) => n.id);
}

/** Participants whose outputs form the decision (explicit list, else the default). */
export function effectiveExitNodeIds(artifact: MADArtifact): string[] {
  const explicit = artifact.interaction.topology.exit_nodes;
  if (explicit != null) return existing(artifact, explicit);
  const authority = artifact.agreement?.authority ?? "collective";
  const judge = firstJudgeId(artifact);
  if (authority === "judge_based") return judge ? [judge] : [];
  const aggregated = new Set(aggregatedNodeIds(artifact));
  if (authority === "hybrid" && judge) aggregated.add(judge);
  // Declaration order keeps the connectors (and a materialized list) stable.
  return artifact.participants.nodes
    .filter((n) => aggregated.has(n.id))
    .map((n) => n.id);
}

/** Id of the synthetic Start -> participant connector. */
export function entryConnectorId(nodeId: string): string {
  return `${START_PREFIX}${nodeId}`;
}

/** Id of the synthetic participant -> End connector. */
export function exitConnectorId(nodeId: string): string {
  return `${nodeId}${END_SUFFIX}`;
}

/**
 * Classify a canvas edge id: a Start connector, an End connector, or a real
 * participant edge (`null`).
 */
export function parseConnectorId(
  id: string,
): { kind: "entry"; nodeId: string } | { kind: "exit"; nodeId: string } | null {
  if (id.startsWith(START_PREFIX)) {
    return { kind: "entry", nodeId: id.slice(START_PREFIX.length) };
  }
  if (id.endsWith(END_SUFFIX)) {
    return { kind: "exit", nodeId: id.slice(0, -END_SUFFIX.length) };
  }
  return null;
}

/** What a canvas connection gesture means for the artifact (task 11.4). */
export type ResolvedConnection =
  | { kind: "entry"; nodeId: string }
  | { kind: "exit"; nodeId: string }
  | { kind: "edge"; source: string; target: string }
  | null;

/**
 * Normalize a drag-to-connect gesture. Handles are direction-agnostic (any side
 * of a node can start or end a connection), so the drag direction only matters
 * between two participants (source = drag start, target = drop). Anything
 * touching Start always means Start -> participant, anything touching End
 * means participant -> End; Start<->End and self-connections are rejected.
 */
export function resolveConnection(source: string, target: string): ResolvedConnection {
  if (!source || !target || source === target) return null;
  const ends = new Set([source, target]);
  if (ends.has(START_NODE_ID) && ends.has(END_NODE_ID)) return null;
  if (ends.has(START_NODE_ID)) {
    return { kind: "entry", nodeId: source === START_NODE_ID ? target : source };
  }
  if (ends.has(END_NODE_ID)) {
    return { kind: "exit", nodeId: source === END_NODE_ID ? target : source };
  }
  return { kind: "edge", source, target };
}
