import { useCallback, useEffect, useMemo, useRef } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import ReactFlow, {
  Background,
  ConnectionMode,
  Controls,
  ReactFlowProvider,
  applyNodeChanges,
  type Connection,
  type Edge as FlowEdge,
  type EdgeChange,
  type Node as FlowNode,
  type NodeChange,
  type OnConnectStartParams,
  useReactFlow,
} from "reactflow";
import "reactflow/dist/style.css";

import { AlertTriangle, Wrench } from "lucide-react";

import { configsApi, type JsonObject } from "@/api";
import { useTaxonomy } from "@/taxonomy/TaxonomyContext";
import type { ApplicableTopology } from "./artifact";
import { DesignerHeader } from "./DesignerHeader";
import { DesignerToolbar } from "./DesignerToolbar";
import { Inspector } from "./panels/Inspector";
import { ParticipantNode } from "./ParticipantNode";
import { END_NODE_ID, EndNode, START_NODE_ID, StartNode } from "./StartEndNodes";
import {
  FLOATING_EDGE_TYPE,
  toFlowEdges,
  toFlowNodes,
  toStartEndEdges,
  toStartEndNodes,
} from "./flowGraph";
import { FloatingEdge } from "./FloatingEdge";
import { resolveConnection } from "./ioNodes";
import { AssistantChat } from "./AssistantChat";
import { CanvasContextMenu, useCanvasContextMenu } from "./EdgeContextMenu";
import { useDesignerStore, withUiLayout } from "./designerStore";
import type { NodeSizeMap } from "./layout";
import {
  catalogTopologyLabel,
  confirmApplyTopology,
  topologyStatus,
} from "./interactionScope";
import { useConfigDetailQuery, useUpdateConfig } from "./useConfigDetail";

/** Register custom node types once (stable reference). */
const NODE_TYPES = {
  participant: ParticipantNode,
  start: StartNode,
  end: EndNode,
} as const;

/** Register the floating, bendable edge type once (stable reference). */
const EDGE_TYPES = { [FLOATING_EDGE_TYPE]: FloatingEdge } as const;

/** The canvas node id under a pointer/touch event, if any. */
function nodeIdAtEvent(event: MouseEvent | TouchEvent): string | null {
  const point =
    "changedTouches" in event ? event.changedTouches[0] : (event as MouseEvent);
  if (!point || typeof document.elementFromPoint !== "function") return null;
  const el = document.elementFromPoint(point.clientX, point.clientY);
  const nodeEl = el?.closest(".react-flow__node");
  return nodeEl?.getAttribute("data-id") ?? null;
}

/**
 * Visual debate designer — canvas (Reqs 6.1, 6.2, 6.4, 6.5, 6.7, 6.8).
 *
 * Loads a config by the `:configId` route param, seeds the designer store, and
 * renders the `G=(V,E)` graph with React Flow: participants as nodes (role icon
 * + model badge, connectable from any side), communication as floating,
 * bendable directed edges (arrowheads convey direction, task 11.4), plus
 * synthetic Start/End nodes whose connectors show where the instance input
 * enters and the final output leaves. The Start/End nodes themselves are not in
 * the artifact (their positions are UI-only), but their connectors are: they
 * persist as `interaction.topology.entry_nodes` / `exit_nodes` (task 11.2).
 * Any edge or participant node can be deleted via right-click -> Delete
 * (task 11.5), and connectors can be re-added by dragging Start -> participant
 * or participant -> End.
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
  const edgeBends = useDesignerStore((s) => s.edgeBends);
  const selection = useDesignerStore((s) => s.selection);
  const dirty = useDesignerStore((s) => s.dirty);

  const addNode = useDesignerStore((s) => s.addNode);
  const moveNode = useDesignerStore((s) => s.moveNode);
  const connectNodes = useDesignerStore((s) => s.connectNodes);
  const addEntryNode = useDesignerStore((s) => s.addEntryNode);
  const addExitNode = useDesignerStore((s) => s.addExitNode);
  const removeNode = useDesignerStore((s) => s.removeNode);
  const deleteCanvasEdge = useDesignerStore((s) => s.deleteCanvasEdge);
  const applyTopology = useDesignerStore((s) => s.applyTopology);
  const relayout = useDesignerStore((s) => s.relayout);
  const { getNodes, fitView } = useReactFlow();
  // Auto layout with React Flow's measured node sizes (task 11.8), then bring
  // the whole new arrangement into view.
  const handleAutoLayout = useCallback(() => {
    const sizes: NodeSizeMap = {};
    for (const n of getNodes()) {
      if (n.width && n.height) sizes[n.id] = { width: n.width, height: n.height };
    }
    relayout(sizes);
    requestAnimationFrame(() => fitView({ padding: 0.15, duration: 200 }));
  }, [getNodes, fitView, relayout]);
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
  const inputSelected = selection?.kind === "input";
  const nodes = useMemo<FlowNode[]>(
    () =>
      artifact
        ? [
            ...toFlowNodes(artifact, layout, selectedNodeId),
            ...toStartEndNodes(artifact, layout, inputSelected),
          ]
        : [],
    [artifact, layout, selectedNodeId, inputSelected],
  );

  // `?panel=input` (the Run view's "define the input" link) opens the Input
  // panel once this config is the one loaded in the store (loading resets the
  // selection, so wait for the store's configId to match).
  const [searchParams] = useSearchParams();
  const storeConfigId = useDesignerStore((s) => s.configId);
  const openedInputFor = useRef<number | null>(null);
  useEffect(() => {
    if (
      searchParams.get("panel") === "input" &&
      storeConfigId === configId &&
      openedInputFor.current !== configId
    ) {
      openedInputFor.current = configId;
      setSelection({ kind: "input" });
    }
  }, [searchParams, storeConfigId, configId, setSelection]);
  const edges = useMemo<FlowEdge[]>(
    () =>
      artifact
        ? [
            ...toFlowEdges(artifact, selectedEdgeId, edgeBends),
            ...toStartEndEdges(artifact, selectedEdgeId, edgeBends),
          ]
        : [],
    [artifact, selectedEdgeId, edgeBends],
  );

  // Right-click on any edge (participant edge or Start/End connector) or on a
  // participant node (Start/End get no menu). One shared state = one menu.
  const {
    menu: canvasMenu,
    onEdgeContextMenu,
    onNodeContextMenu,
    close: closeCanvasMenu,
  } = useCanvasContextMenu();

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
          // Selecting Start opens the Input panel (task 11.10). Start/End are
          // never removable (and End is not selectable); ignore the rest.
          if (
            change.type === "select" &&
            change.selected &&
            changeId === START_NODE_ID
          ) {
            setSelection({ kind: "input" });
          }
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
        if (change.type === "remove") {
          // Routes participant edges to removeEdge and Start/End connectors to
          // removeEntryNode / removeExitNode — always through the store.
          deleteCanvasEdge(change.id);
        } else if (change.type === "select" && change.selected) {
          setSelection({ kind: "edge", id: change.id });
        }
      }
    },
    [deleteCanvasEdge, setSelection],
  );

  // Handles are direction-agnostic (ConnectionMode.Loose, any side to any
  // side), so normalize the gesture: anything touching Start = Start -> X,
  // anything touching End = X -> End, Start<->End rejected; between two
  // participants the drag start is the source (see `resolveConnection`).
  const applyConnection = useCallback(
    (source: string, target: string) => {
      const resolved = resolveConnection(source, target);
      if (resolved?.kind === "entry") addEntryNode(resolved.nodeId);
      else if (resolved?.kind === "exit") addExitNode(resolved.nodeId);
      else if (resolved?.kind === "edge") connectNodes(resolved.source, resolved.target);
    },
    [addEntryNode, addExitNode, connectNodes],
  );

  // The node a connection drag started from; lets a drop anywhere on a node's
  // body (not only on a handle) complete the connection in `onConnectEnd`.
  const connectingFrom = useRef<string | null>(null);

  const onConnectStart = useCallback(
    (_event: unknown, params: OnConnectStartParams) => {
      connectingFrom.current = params.nodeId ?? null;
    },
    [],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      // Dropped on a handle: React Flow resolved it (fires before onConnectEnd).
      connectingFrom.current = null;
      if (connection.source && connection.target) {
        applyConnection(connection.source, connection.target);
      }
    },
    [applyConnection],
  );

  const onConnectEnd = useCallback(
    (event: MouseEvent | TouchEvent) => {
      const from = connectingFrom.current;
      connectingFrom.current = null;
      if (!from) return;
      const to = nodeIdAtEvent(event);
      if (to && to !== from) applyConnection(from, to);
    },
    [applyConnection],
  );

  const onPaneClick = useCallback(() => {
    closeCanvasMenu();
    setSelection(null);
  }, [closeCanvasMenu, setSelection]);

  // Clicking Start opens the Input panel (also when it is already selected,
  // where React Flow emits no new select change).
  const onNodeClick = useCallback(
    (_event: unknown, node: { id: string }) => {
      if (node.id === START_NODE_ID) setSelection({ kind: "input" });
    },
    [setSelection],
  );

  // Apply a topology template, warning first if an existing graph would be
  // overwritten (Req 6.5 — initializing a structure replaces the current edges).
  const labelTopology = useMemo(() => catalogTopologyLabel(getValue), [getValue]);
  const handleApplyTopology = useCallback(
    (topology: ApplicableTopology) => {
      if (!confirmApplyTopology(artifact, labelTopology(topology))) return;
      applyTopology(topology);
    },
    [artifact, applyTopology, labelTopology],
  );
  // Applied template vs drawn edges, for the toolbar's Topology button.
  const status = useMemo(
    () => (artifact ? topologyStatus(artifact, labelTopology) : undefined),
    [artifact, labelTopology],
  );

  const handleSave = useCallback(async () => {
    if (!artifact) return;
    // Persist the canvas layout (node positions incl. Start/End + edge bends)
    // in the presentation-only `ui` field, restricted to ids that exist.
    const toSave = withUiLayout(artifact, layout, edgeBends) as unknown as JsonObject;
    const body = { artifact: toSave };
    try {
      const result = await configsApi.validate({ artifact: toSave });
      setValidationErrors(result.errors);
      if (!result.valid) return;
    } catch {
      /* fall through; the save itself will surface any error */
    }
    updateConfig.mutate(body, { onSuccess: () => markSaved() });
  }, [artifact, layout, edgeBends, updateConfig, markSaved, setValidationErrors]);

  const underDevSelections = useMemo(
    () => (artifact ? collectUnderDev(artifact, isUnderDevelopment, getValue) : []),
    [artifact, isUnderDevelopment, getValue],
  );

  return (
    <div className="flex h-full flex-col">
      <DesignerHeader />
      <DesignerToolbar
        onAddNode={() => addNode()}
        onApplyTopology={handleApplyTopology}
        onAutoLayout={handleAutoLayout}
        onDeleteSelection={() => {
          // The Start node (`input` selection) is never deletable.
          if (selection?.kind === "node") removeNode(selection.id);
          else if (selection?.kind === "edge") deleteCanvasEdge(selection.id);
        }}
        onSave={handleSave}
        canDeleteSelection={selection?.kind === "node" || selection?.kind === "edge"}
        dirty={dirty}
        saving={updateConfig.isPending}
        topologyStatus={status}
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
            edgeTypes={EDGE_TYPES}
            connectionMode={ConnectionMode.Loose}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnectStart={onConnectStart}
            onConnect={onConnect}
            onConnectEnd={onConnectEnd}
            onPaneClick={onPaneClick}
            onNodeClick={onNodeClick}
            onEdgeContextMenu={onEdgeContextMenu}
            onNodeContextMenu={onNodeContextMenu}
            onMoveStart={closeCanvasMenu}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background />
            <Controls />
          </ReactFlow>
          <CanvasContextMenu menu={canvasMenu} onClose={closeCanvasMenu} />
          <AssistantChat configId={configId} />
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
