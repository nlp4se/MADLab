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
 * edges (V and E). The synthetic Start/End nodes and their edges are produced
 * by the separate `toStartEndNodes` / `toStartEndEdges` helpers and concatenated
 * by the canvas, so the pure artifact<->canvas projection (and its round-trip
 * tests) stay exactly 1:1 with the artifact.
 */
import { MarkerType, type Edge as FlowEdge, type Node as FlowNode } from "reactflow";

import type { MADArtifact } from "./artifact";
import { edgeId } from "./designerStore";
import type { LayoutMap, XYPosition } from "./layout";
import type { ParticipantNodeData } from "./ParticipantNode";
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

/** Larger arrowhead so direction reads clearly on the canvas. */
const ARROW = { type: MarkerType.ArrowClosed, width: 22, height: 22 } as const;

export function toFlowNodes(
  artifact: MADArtifact,
  layout: LayoutMap,
  selectedId: string | null,
): FlowNode<ParticipantNodeData>[] {
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
    },
  }));
}

export function toFlowEdges(
  artifact: MADArtifact,
  selectedId: string | null,
): FlowEdge[] {
  return artifact.interaction.topology.edges.map((edge) => {
    const id = edgeId(edge);
    const color = edge.color ?? DEFAULT_EDGE_COLOR;
    const isSelected = id === selectedId;
    return {
      id,
      source: edge.source,
      target: edge.target,
      label: edge.label ?? undefined,
      selected: isSelected,
      // smoothstep avoids the tight bezier loop that overlapped arrowheads.
      type: "smoothstep",
      pathOptions: { borderRadius: 18 },
      // `directed` defaults to true; show an arrowhead for directed edges.
      markerEnd:
        edge.directed === false ? undefined : { ...ARROW, color },
      style: {
        stroke: color,
        strokeWidth: isSelected ? 3 : 2,
      },
      labelStyle: { fill: color, fontWeight: 600 },
    } satisfies FlowEdge;
  });
}

/* ----------------------- synthetic Start / End nodes ---------------------- */

/**
 * Entry participants = nodes with NO incoming participant->participant edge.
 * When none exist (e.g. fully_connected, where every node has an incoming
 * edge), fall back to the first node in the protocol order (or the first
 * participant). These are the nodes the instance input is fed into.
 */
function entryNodeIds(artifact: MADArtifact): string[] {
  const nodes = artifact.participants.nodes;
  if (nodes.length === 0) return [];
  const withIncoming = new Set(
    artifact.interaction.topology.edges.map((e) => e.target),
  );
  const entries = nodes.filter((n) => !withIncoming.has(n.id)).map((n) => n.id);
  if (entries.length > 0) return entries;
  const order = artifact.interaction.protocol?.order ?? [];
  const first = order.find((id) => nodes.some((n) => n.id === id)) ?? nodes[0].id;
  return [first];
}

/**
 * Terminal participants = nodes with NO outgoing edge. When none exist, prefer
 * judge-role nodes (they produce the final decision); else fall back to the
 * last node in the protocol order (or the last participant). These feed End.
 */
function terminalNodeIds(artifact: MADArtifact): string[] {
  const nodes = artifact.participants.nodes;
  if (nodes.length === 0) return [];
  const withOutgoing = new Set(
    artifact.interaction.topology.edges.map((e) => e.source),
  );
  const terminals = nodes.filter((n) => !withOutgoing.has(n.id)).map((n) => n.id);
  if (terminals.length > 0) return terminals;
  const judges = nodes.filter((n) => (n.roles ?? []).includes("judge")).map((n) => n.id);
  if (judges.length > 0) return judges;
  const order = artifact.interaction.protocol?.order ?? [];
  const last =
    [...order].reverse().find((id) => nodes.some((n) => n.id === id)) ??
    nodes[nodes.length - 1].id;
  return [last];
}

/** Bounding box of the participant layout, for placing Start/End on the sides. */
function layoutBounds(nodeIds: string[], layout: LayoutMap) {
  const pts = nodeIds
    .map((id) => layout[id])
    .filter((p): p is XYPosition => p != null);
  if (pts.length === 0) {
    return { minX: 0, maxX: 360, centerY: 260 };
  }
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    centerY: (Math.min(...ys) + Math.max(...ys)) / 2,
  };
}

/**
 * The synthetic Start and End nodes, positioned to the left/right of the
 * participant cloud. Non-selectable and non-deletable (draggable is harmless);
 * ids are reserved sentinels that cannot collide with participant ids. Returns
 * an empty list when there are no participants.
 */
export function toStartEndNodes(
  artifact: MADArtifact,
  layout: LayoutMap,
): FlowNode<StartEndNodeData>[] {
  const nodes = artifact.participants.nodes;
  if (nodes.length === 0) return [];
  const { minX, maxX, centerY } = layoutBounds(
    nodes.map((n) => n.id),
    layout,
  );
  // Default placement flanks the participant cloud; a user drag is remembered
  // in the UI-only layout map (keyed by the sentinel ids) and takes precedence,
  // so Start/End can be repositioned like any node. Positions are never part of
  // the artifact.
  const startPos = layout[START_NODE_ID] ?? { x: minX - 180, y: centerY };
  const endPos = layout[END_NODE_ID] ?? { x: maxX + 220, y: centerY };
  const common = {
    selectable: false as const,
    deletable: false as const,
    draggable: true as const,
  };
  return [
    {
      id: START_NODE_ID,
      type: "start",
      position: startPos,
      data: { label: "Start" },
      ...common,
    },
    {
      id: END_NODE_ID,
      type: "end",
      position: endPos,
      data: { label: "End" },
      ...common,
    },
  ];
}

/**
 * The synthetic edges: Start -> each entry participant, and each terminal
 * participant -> End. Dashed + arrow-headed so they read as the input/output
 * flow and are visually distinct from the real (solid) participant edges. Their
 * ids are namespaced with the sentinel node ids so they never collide with a
 * real edge id. NOT part of the artifact.
 */
export function toStartEndEdges(artifact: MADArtifact): FlowEdge[] {
  const nodes = artifact.participants.nodes;
  if (nodes.length === 0) return [];
  const edges: FlowEdge[] = [];
  for (const entry of entryNodeIds(artifact)) {
    edges.push({
      id: `${START_NODE_ID}->${entry}`,
      source: START_NODE_ID,
      target: entry,
      type: "smoothstep",
      pathOptions: { borderRadius: 18 },
      deletable: false,
      markerEnd: { ...ARROW, color: START_EDGE_COLOR },
      style: { stroke: START_EDGE_COLOR, strokeWidth: 2, strokeDasharray: "5 4" },
    });
  }
  for (const terminal of terminalNodeIds(artifact)) {
    edges.push({
      id: `${terminal}->${END_NODE_ID}`,
      source: terminal,
      target: END_NODE_ID,
      type: "smoothstep",
      pathOptions: { borderRadius: 18 },
      deletable: false,
      markerEnd: { ...ARROW, color: END_EDGE_COLOR },
      style: { stroke: END_EDGE_COLOR, strokeWidth: 2, strokeDasharray: "5 4" },
    });
  }
  return edges;
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
