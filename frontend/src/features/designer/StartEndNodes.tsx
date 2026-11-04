import { memo } from "react";
import { Handle, Position, type NodeProps } from "reactflow";
import { FlagTriangleRight, LogIn, LogOut } from "lucide-react";

/**
 * Synthetic Start / End canvas nodes.
 *
 * The nodes themselves are NOT part of the MAD artifact (not selectable, not
 * deletable, positions live in the UI-only layout map). Their connectors ARE:
 * Start -> X persists as `interaction.topology.entry_nodes` and X -> End as
 * `exit_nodes` (null = engine default, see `ioNodes.ts`). See `flowGraph.ts`
 * (`toStartEndNodes` / `toStartEndEdges`) for the projection and
 * `DesignerPage` for how connector deletes/drags route to the store.
 */

export const START_NODE_ID = "__start__";
export const END_NODE_ID = "__end__";

export interface StartEndNodeData {
  label: string;
}

/** Start: emits the instance input. Has only a source (output) handle. */
function StartNodeComponent(_props: NodeProps<StartEndNodeData>) {
  return (
    <div
      className="flex items-center gap-1.5 rounded-full border-2 border-emerald-500 bg-emerald-500/10 px-3 py-2 text-sm font-semibold text-emerald-700 shadow-sm dark:text-emerald-400"
      data-testid="start-node"
      title="Input — the task input fed into the connected participant(s). Drag from here to a participant to connect it."
    >
      <LogIn className="size-4" aria-hidden />
      Start
      <Handle
        type="source"
        position={Position.Right}
        className="!size-3 !border-2 !border-background !bg-emerald-500"
      />
    </div>
  );
}

/** End: collects the final output. Has only a target (input) handle. */
function EndNodeComponent(_props: NodeProps<StartEndNodeData>) {
  return (
    <div
      className="flex items-center gap-1.5 rounded-full border-2 border-slate-500 bg-slate-500/10 px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm dark:text-slate-300"
      data-testid="end-node"
      title="Output — the final decision formed from the connected participant(s). Drag from a participant to here to connect it."
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!size-3 !border-2 !border-background !bg-slate-500"
      />
      <FlagTriangleRight className="size-4" aria-hidden />
      End
      <LogOut className="size-4 opacity-0" aria-hidden />
    </div>
  );
}

export const StartNode = memo(StartNodeComponent);
export const EndNode = memo(EndNodeComponent);
