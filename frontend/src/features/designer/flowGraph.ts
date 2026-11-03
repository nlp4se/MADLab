/**
 * Artifact -> React Flow projection (Req 6.8, direction: artifact drives canvas).
 *
 * Pure functions that turn the designer store's `MADArtifact` + `LayoutMap`
 * into the `Node[]` / `Edge[]` React Flow renders. Keeping this projection pure
 * (no store access) makes it unit-testable and keeps the canvas a faithful,
 * one-way-rendered view of the artifact; user gestures flow back through the
 * store mutations, never by mutating these derived objects.
 */
import { MarkerType, type Edge as FlowEdge, type Node as FlowNode } from "reactflow";

import type { MADArtifact } from "./artifact";
import { edgeId } from "./designerStore";
import type { LayoutMap } from "./layout";
import type { ParticipantNodeData } from "./ParticipantNode";

/** Default edge colour (Interaction dimension teal) when none is set. */
export const DEFAULT_EDGE_COLOR = "#0d9488";

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
      // `directed` defaults to true; show an arrowhead for directed edges.
      markerEnd:
        edge.directed === false
          ? undefined
          : { type: MarkerType.ArrowClosed, color },
      style: {
        stroke: color,
        strokeWidth: isSelected ? 2.5 : 1.5,
      },
      labelStyle: { fill: color, fontWeight: 600 },
    } satisfies FlowEdge;
  });
}
