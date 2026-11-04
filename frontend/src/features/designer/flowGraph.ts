/**
 * Artifact -> React Flow projection (Req 6.8, direction: artifact drives canvas).
 *
 * Pure functions that turn the designer store's `MADArtifact` + `LayoutMap`
 * into the `Node[]` / `Edge[]` React Flow renders. Keeping this projection pure
 * (no store access) makes it unit-testable and keeps the canvas a faithful,
 * one-way-rendered view of the artifact; user gestures flow back through the
 * store mutations, never by mutating these derived objects.
 *
 * `toFlowNodes` / `toFlowEdges` project ONLY the real artifact participants and
 * edges (V and E). The synthetic Start/End nodes and their IO connector edges
 * (derived from `topology.entry_nodes` / `exit_nodes` or their engine-mirroring
 * defaults, see `ioNodes.ts`) are produced by the separate `toStartEndNodes` /
 * `toStartEndEdges` helpers and concatenated by the canvas, so the pure
 * artifact<->canvas edge projection (and its round-trip tests) stay exactly 1:1
 * with `topology.edges`.
 */
import { MarkerType, type Edge as FlowEdge, type Node as FlowNode } from "reactflow";

import type { MADArtifact } from "./artifact";
import { edgeId, type EdgeBendMap } from "./designerStore";
import type { XYPosition as BendOffset } from "./layout";
import {
  effectiveEntryNodeIds,
  effectiveExitNodeIds,
  entryConnectorId,
  exitConnectorId,
} from "./ioNodes";
import { isInputTemplateEmpty } from "./inputEditor";
import { startEndFallback, type LayoutMap } from "./layout";
import type { ParticipantNodeData } from "./ParticipantNode";
import { conflictNodeIds } from "./participantScope";
import { turnNumbers } from "./interactionScope";
import {
  END_NODE_ID,
  START_NODE_ID,
  type StartEndNodeData,
} from "./StartEndNodes";

/** Default edge colour (Interaction dimension teal) when none is set. */
export const DEFAULT_EDGE_COLOR = "#0d9488";

/** Colour for the synthetic Start/End flow edges (emerald / slate). */
const START_EDGE_COLOR = "#10b981";
const END_EDGE_COLOR = "#64748b";

/** React Flow edge type key for the custom floating edge (see FloatingEdge.tsx). */
export const FLOATING_EDGE_TYPE = "floating";

/** Data carried by every floating edge. */
export interface FloatingEdgeData {
  /** Stored knob offset from the centres' midpoint; null = default shape. */
  bend: BendOffset | null;
  /** True when the reverse edge exists (bow the pair to opposite sides). */
  reciprocal: boolean;
  /** Stroke colour (also used for the edge label / knob). */
  color: string;
}

/** Larger arrowhead so direction reads clearly on the canvas. */
const ARROW = { type: MarkerType.ArrowClosed, width: 22, height: 22 } as const;

export function toFlowNodes(
  artifact: MADArtifact,
  layout: LayoutMap,
  selectedId: string | null,
): FlowNode<ParticipantNodeData>[] {
  // Nodes whose data contradicts the declared participant modes (task 11.6).
  const conflicts = conflictNodeIds(artifact.participants);
  // Turn-number badges, only under sequential + fixed ordering (task 11.7).
  const turns = turnNumbers(artifact);
  return artifact.participants.nodes.map((node) => ({
    id: node.id,
    type: "participant",
    position: layout[node.id] ?? { x: 0, y: 0 },
    selected: node.id === selectedId,
    data: {
      label: node.label,
      roles: node.roles ?? [],
      modelKey: node.base_model?.model_key ?? null,
      providerId: node.base_model?.provider_id ?? null,
      conflict: conflicts.has(node.id),
      turn: turns.get(node.id) ?? null,
    },
  }));
}

/**
 * The real participant edges (E), as floating edges (task 11.4): they attach
 * to the node borders, carry their stored bend (if any), and are flagged
 * `reciprocal` when the reverse edge also exists so the pair renders as two
 * separated curves. Direction is conveyed by the arrowhead only.
 */
export function toFlowEdges(
  artifact: MADArtifact,
  selectedId: string | null,
  edgeBends: EdgeBendMap = {},
): FlowEdge<FloatingEdgeData>[] {
  const edges = artifact.interaction.topology.edges;
  const ids = new Set(edges.map(edgeId));
  return edges.map((edge) => {
    const id = edgeId(edge);
    const color = edge.color ?? DEFAULT_EDGE_COLOR;
    const isSelected = id === selectedId;
    return {
      id,
      source: edge.source,
      target: edge.target,
      label: edge.label ?? undefined,
      selected: isSelected,
      type: FLOATING_EDGE_TYPE,
      data: {
        bend: edgeBends[id] ?? null,
        reciprocal: ids.has(`${edge.target}->${edge.source}`),
        color,
      },
      // `directed` defaults to true; show an arrowhead for directed edges.
      markerEnd:
        edge.directed === false ? undefined : { ...ARROW, color },
      style: {
        stroke: color,
        strokeWidth: isSelected ? 3 : 2,
      },
      labelStyle: { fill: color, fontWeight: 600 },
    } satisfies FlowEdge<FloatingEdgeData>;
  });
}

/* ----------------------- synthetic Start / End nodes ---------------------- */

// The Start/End derivation rule lives in `ioNodes.ts` (shared with the store);
// re-exported here so canvas callers/tests have one import site.
export {
  effectiveEntryNodeIds,
  effectiveExitNodeIds,
  entryConnectorId,
  exitConnectorId,
  isJudgeOnly,
  parseConnectorId,
} from "./ioNodes";

/**
 * The synthetic Start and End nodes, positioned to the left/right of the
 * participant cloud. Both are non-deletable (no keyboard Delete, no context
 * menu; draggable is harmless); ids are reserved sentinels that cannot collide
 * with participant ids. Start is selectable (task 11.10): selecting it opens
 * the Input panel (`inputSelected` mirrors the store's `{ kind: "input" }`
 * selection) and it carries a marker when the input template is empty. End
 * stays non-selectable. Returns an empty list when there are no participants.
 */
export function toStartEndNodes(
  artifact: MADArtifact,
  layout: LayoutMap,
  inputSelected = false,
): FlowNode<StartEndNodeData>[] {
  const nodes = artifact.participants.nodes;
  if (nodes.length === 0) return [];
  // Auto layout (task 11.8) and user drags write Start/End positions into the
  // UI-only layout map (keyed by the sentinel ids); on Save they persist in
  // the presentation-only `artifact.ui.nodes` (never in the graph itself). A
  // stored layout without them falls back to flanking the participant cloud.
  const fallback = startEndFallback(
    nodes.map((n) => n.id),
    layout,
  );
  const startPos = layout[START_NODE_ID] ?? fallback.start;
  const endPos = layout[END_NODE_ID] ?? fallback.end;
  const common = {
    deletable: false as const,
    draggable: true as const,
  };
  return [
    {
      id: START_NODE_ID,
      type: "start",
      position: startPos,
      data: { label: "Start", inputMissing: isInputTemplateEmpty(artifact) },
      selectable: true,
      selected: inputSelected,
      ...common,
    },
    {
      id: END_NODE_ID,
      type: "end",
      position: endPos,
      data: { label: "End" },
      selectable: false,
      ...common,
    },
  ];
}

/**
 * The IO connector edges: Start -> each effective entry participant, and each
 * effective exit participant -> End (see `ioNodes.ts` for the rule, which
 * mirrors the engine). Dashed + arrow-headed so they read as the input/output
 * flow and are visually distinct from the real (solid) participant edges. Their
 * ids are namespaced with the sentinel node ids so they never collide with a
 * real edge id.
 *
 * They are selectable and deletable: a delete (keyboard or context menu) is
 * routed by the canvas to the store's `removeEntryNode` / `removeExitNode`,
 * which persist `interaction.topology.entry_nodes` / `exit_nodes`.
 */
export function toStartEndEdges(
  artifact: MADArtifact,
  selectedId: string | null = null,
  edgeBends: EdgeBendMap = {},
): FlowEdge<FloatingEdgeData>[] {
  const nodes = artifact.participants.nodes;
  if (nodes.length === 0) return [];
  const connector = (
    id: string,
    source: string,
    target: string,
    color: string,
  ): FlowEdge<FloatingEdgeData> => ({
    id,
    source,
    target,
    // Same floating, bendable edge as participant edges (task 11.4).
    type: FLOATING_EDGE_TYPE,
    data: { bend: edgeBends[id] ?? null, reciprocal: false, color },
    deletable: true,
    selected: id === selectedId,
    markerEnd: { ...ARROW, color },
    style: {
      stroke: color,
      strokeWidth: id === selectedId ? 3 : 2,
      strokeDasharray: "5 4",
    },
  });
  return [
    ...effectiveEntryNodeIds(artifact).map((entry) =>
      connector(entryConnectorId(entry), START_NODE_ID, entry, START_EDGE_COLOR),
    ),
    ...effectiveExitNodeIds(artifact).map((exit) =>
      connector(exitConnectorId(exit), exit, END_NODE_ID, END_EDGE_COLOR),
    ),
  ];
}

/** True for the reserved synthetic node/edge ids (so canvas handlers skip them). */
export function isSyntheticId(id: string): boolean {
  return (
    id === START_NODE_ID ||
    id === END_NODE_ID ||
    id.startsWith(`${START_NODE_ID}->`) ||
    id.endsWith(`->${END_NODE_ID}`)
  );
}
