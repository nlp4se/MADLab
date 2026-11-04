import { useCallback, useEffect, useMemo } from "react";
import { useParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import ReactFlow, {
  Background,
  Controls,
  ReactFlowProvider,
  addEdge,
  applyNodeChanges,
  type Connection,
  type Edge as FlowEdge,
  type EdgeChange,
  type Node as FlowNode,
  type NodeChange,
} from "reactflow";
import "reactflow/dist/style.css";

import { AlertTriangle, Wrench } from "lucide-react";

import { configsApi, type JsonObject } from "@/api";
import { useTaxonomy } from "@/taxonomy/TaxonomyContext";
import type { ApplicableTopology } from "./artifact";
import { DesignerToolbar } from "./DesignerToolbar";
import { Inspector } from "./panels/Inspector";
import { ParticipantNode } from "./ParticipantNode";
import { END_NODE_ID, EndNode, START_NODE_ID, StartNode } from "./StartEndNodes";
import {
  isSyntheticId,
  toFlowEdges,
  toFlowNodes,
  toStartEndEdges,
  toStartEndNodes,
} from "./flowGraph";
import { AssistantChat } from "./AssistantChat";
import { useDesignerStore } from "./designerStore";
import { topologyLabel } from "./topology";
import { useConfigDetailQuery, useUpdateConfig } from "./useConfigDetail";

/** Register custom node types once (stable reference). */
const NODE_TYPES = {
  participant: ParticipantNode,
  start: StartNode,
  end: EndNode,
} as const;

/**
 * Visual debate designer — canvas (Reqs 6.1, 6.2, 6.4, 6.5, 6.7, 6.8).
 *
 * Loads a config by the `:configId` route param, seeds the designer store, and
 * renders the `G=(V,E)` graph with React Flow: participants as nodes (role icon
 * + model badge, labelled in/out ports), communication as directed edges, plus
 * synthetic Start/End nodes that visualise where the instance input enters and
 * the final output leaves (the Start/End are visual only — not in the artifact).
 */
export function DesignerPage() {
  const params = useParams<{ configId?: string }>();
  const configId = params.configId ? Number(params.configId) : null;

  const { data, isLoading, isError, error } = useConfigDetailQuery(configId);

  const loadArtifact = useDesignerStore((s) => s.loadArtifact);
  const artifact = useDesignerStore((s) => s.artifact);

  useEffect(() => {
    if (data) loadArtifact(data.id, data.artifact);
  }, [data, loadArtifact]);

  if (configId === null) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-sm text-muted-foreground">
        Open a configuration from the Configurations list to design it.
      </div>
    );
  }

  if (isLoading || (data && !artifact)) {
    return (
      <div className="flex h-full items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        Loading configuration…
      </div>
    );
  }

  if (isError) {
    return (
      <div
        role="alert"
        className="m-8 rounded-lg border border-destructive/50 bg-destructive/5 p-6 text-sm text-destructive"
      >
        Failed to load configuration: {error?.message}
      </div>
    );
  }

  return (
    <ReactFlowProvider>
      <DesignerCanvas configId={configId} />
    </ReactFlowProvider>
  );
}

function DesignerCanvas({ configId }: { configId: number }) {
  const artifact = useDesignerStore((s) => s.artifact);
  const layout = useDesignerStore((s) => s.layout);
  const selection = useDesignerStore((s) => s.selection);
  const dirty = useDesignerStore((s) => s.dirty);

  const addNode = useDesignerStore((s) => s.addNode);
  const moveNode = useDesignerStore((s) => s.moveNode);
  const connectNodes = useDesignerStore((s) => s.connectNodes);
  const removeNode = useDesignerStore((s) => s.removeNode);
  const removeEdge = useDesignerStore((s) => s.removeEdge);
  const applyTopology = useDesignerStore((s) => s.applyTopology);
  const relayout = useDesignerStore((s) => s.relayout);
  const setSelection = useDesignerStore((s) => s.setSelection);
  const markSaved = useDesignerStore((s) => s.markSaved);
  const setValidationErrors = useDesignerStore((s) => s.setValidationErrors);
  const validationErrors = useDesignerStore((s) => s.validationErrors);

  const { isUnderDevelopment, getValue } = useTaxonomy();
  const updateConfig = useUpdateConfig(configId);

  const selectedNodeId = selection?.kind === "node" ? selection.id : null;
  const selectedEdgeId = selection?.kind === "edge" ? selection.id : null;

  // Derive React Flow nodes/edges from the artifact + layout. The real graph
  // (V/E) and the synthetic Start/End overlay are projected separately then
  // concatenated, so `toFlowEdges` stays a faithful 1:1 of the artifact.
  const nodes = useMemo<FlowNode[]>(
    () =>
      artifact
        ? [
            ...toFlowNodes(artifact, layout, selectedNodeId),
            ...toStartEndNodes(artifact, layout),
          ]
        : [],
    [artifact, layout, selectedNodeId],
  );
  const edges = useMemo<FlowEdge[]>(
    () =>
      artifact
        ? [...toFlowEdges(artifact, selectedEdgeId), ...toStartEndEdges(artifact)]
        : [],
    [artifact, selectedEdgeId],
  );

  // Canvas gestures -> store mutations (canvas -> artifact). Synthetic Start/End
  // ids are ignored so they can never mutate the artifact.
  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      for (const change of changes) {
        const changeId = "id" in change ? change.id : undefined;
        const isSynthNode =
          changeId === START_NODE_ID || changeId === END_NODE_ID;
        if (change.type === "position" && change.position) {
          // Persist drags for participants AND the synthetic Start/End nodes
          // (their positions live in the UI-only layout map, keyed by the
          // sentinel ids — never in the artifact).
          moveNode(change.id, change.position);
        } else if (isSynthNode) {
          // Start/End are not removable or selectable; ignore other changes.
          continue;
        } else if (change.type === "remove") {
          removeNode(change.id);
        } else if (change.type === "select") {
          if (change.selected) setSelection({ kind: "node", id: change.id });
        }
      }
      void applyNodeChanges(changes, nodes);
    },
    [moveNode, removeNode, setSelection, nodes],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      for (const change of changes) {
        if ("id" in change && isSyntheticId(change.id)) continue;
        if (change.type === "remove") {
          removeEdge(change.id);
        } else if (change.type === "select" && change.selected) {
          setSelection({ kind: "edge", id: change.id });
        }
      }
    },
    [removeEdge, setSelection],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      // Never allow connecting to/from the synthetic Start/End nodes.
      if (
        connection.source &&
        connection.target &&
        !isSyntheticId(connection.source) &&
        !isSyntheticId(connection.target)
      ) {
        connectNodes(connection.source, connection.target);
      }
      void addEdge(connection, edges);
    },
    [connectNodes, edges],
  );

  const onPaneClick = useCallback(() => setSelection(null), [setSelection]);

  // Apply a topology template, warning first if an existing graph would be
  // overwritten (Req 6.5 — initializing a structure replaces the current edges).
  const handleApplyTopology = useCallback(
    (topology: ApplicableTopology) => {
      const hasGraph =
        (artifact?.participants.nodes.length ?? 0) > 0 &&
        (artifact?.interaction.topology.edges.length ?? 0) > 0;
      if (hasGraph) {
        const ok = window.confirm(
          `Apply the "${topologyLabel(topology)}" topology?\n\n` +
            "This regenerates the connections between the current participants " +
            "and overrides the existing edges. Participant nodes are kept.",
        );
        if (!ok) return;
      }
      applyTopology(topology);
    },
    [artifact, applyTopology],
  );

  const handleSave = useCallback(async () => {
    if (!artifact) return;
    const body = { artifact: artifact as unknown as JsonObject };
    try {
      const result = await configsApi.validate({
        artifact: artifact as unknown as JsonObject,
      });
      setValidationErrors(result.errors);
      if (!result.valid) return;
    } catch {
      /* fall through; the save itself will surface any error */
    }
    updateConfig.mutate(body, { onSuccess: () => markSaved() });
  }, [artifact, updateConfig, markSaved, setValidationErrors]);

  const underDevSelections = useMemo(
    () => (artifact ? collectUnderDev(artifact, isUnderDevelopment, getValue) : []),
    [artifact, isUnderDevelopment, getValue],
  );

  return (
    <div className="flex h-full flex-col">
      <DesignerToolbar
        onAddNode={() => addNode()}
        onApplyTopology={handleApplyTopology}
        onAutoLayout={relayout}
        onDeleteSelection={() => {
          if (selection?.kind === "node") removeNode(selection.id);
          else if (selection?.kind === "edge") removeEdge(selection.id);
        }}
        onSave={handleSave}
        canDeleteSelection={selection !== null}
        dirty={dirty}
        saving={updateConfig.isPending}
      />

      {updateConfig.isError ? (
        <p role="alert" className="px-3 py-1 text-xs text-destructive">
          Save failed: {updateConfig.error.message}
        </p>
      ) : null}

      {validationErrors.length > 0 ? (
        <div
          role="alert"
          className="border-b border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive"
        >
          <p className="flex items-center gap-1 font-medium">
            <AlertTriangle className="size-3.5" aria-hidden />
            {validationErrors.length} validation{" "}
            {validationErrors.length === 1 ? "issue" : "issues"} — not saved.
          </p>
          <ul className="mt-1 list-disc pl-5">
            {validationErrors.map((e, i) => (
              <li key={`${e.field}-${i}`}>
                {e.field ? <span className="font-mono">{e.field}</span> : null}
                {e.field ? ": " : ""}
                {e.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {underDevSelections.length > 0 ? (
        <div
          data-testid="under-dev-warning"
          className="flex flex-wrap items-center gap-2 border-b border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-300"
        >
          <span className="flex items-center gap-1 font-medium">
            <Wrench className="size-3.5" aria-hidden />
            Uses values under development — execution is blocked until changed:
          </span>
          {underDevSelections.map((label) => (
            <span
              key={label}
              className="rounded-full border border-amber-500/50 bg-background/60 px-2 py-0.5"
            >
              {label}
            </span>
          ))}
        </div>
      ) : null}

      <div className="flex flex-1 overflow-hidden">
        <div className="relative flex-1" data-testid="designer-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={NODE_TYPES}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onPaneClick={onPaneClick}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background />
            <Controls />
          </ReactFlow>
          <AssistantChat />
        </div>
        <Inspector />
      </div>
    </div>
  );
}

/**
 * Collect the artifact's selected taxonomy value keys that are flagged
 * "under development" (non-executable), returning their human-readable labels
 * for the pre-run warning (Req 7.5). Mirrors the backend's
 * `MADConfig.under_development_values`.
 */
function collectUnderDev(
  artifact: NonNullable<ReturnType<typeof useDesignerStore.getState>["artifact"]>,
  isUnderDevelopment: (key: string) => boolean,
  getValue: ReturnType<typeof useTaxonomy>["getValue"],
): string[] {
  const p = artifact.participants;
  const topo = artifact.interaction.topology;
  const proto = artifact.interaction.protocol ?? {};
  const fmt = artifact.interaction.format ?? {};
  const content = fmt.content ?? {};
  const agr = artifact.agreement ?? {};

  const candidates: Array<[string | undefined | null, string, string]> = [
    [p.persona_heterogeneity, "participants", "persona_heterogeneity"],
    [p.base_model_heterogeneity, "participants", "base_model_heterogeneity"],
    [p.persona_assignment, "participants", "persona_assignment"],
    [topo.adaptability, "interaction", "topology_adaptability"],
    [topo.structure, "interaction", "topology_structure"],
    [topo.pattern, "interaction", "topology_pattern"],
    [proto.mechanism, "interaction", "protocol_mechanism"],
    [proto.ordering, "interaction", "protocol_ordering"],
    [fmt.syntax, "interaction", "format_syntax"],
    [content.strategy, "interaction", "format_content"],
    [fmt.memory, "interaction", "format_memory"],
    [agr.authority, "agreement", "authority"],
    [agr.resolution, "agreement", "resolution"],
  ];

  const labels: string[] = [];
  const seen = new Set<string>();
  const push = (key: string | null | undefined, dim: string, sub: string) => {
    if (!key || seen.has(key) || !isUnderDevelopment(key)) return;
    seen.add(key);
    labels.push(getValue(dim, sub, key)?.label ?? key);
  };
  for (const [key, dim, sub] of candidates) push(key, dim, sub);
  for (const sig of content.metadata_signals ?? []) {
    push(sig, "interaction", "format_content_metadata");
  }
  return labels;
}
