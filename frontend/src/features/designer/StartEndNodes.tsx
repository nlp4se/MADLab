import { memo } from "react";
import { Handle, Position, type NodeProps } from "reactflow";
import { FlagTriangleRight, LogIn, LogOut } from "lucide-react";

/**
 * Synthetic Start / End canvas nodes (visual only).
 *
 * These are NOT part of the MAD artifact — they are rendered from the graph to
 * make the data flow legible: Start feeds the instance input into the entry
 * participants, and End collects the final participants' output. They are not
 * selectable, not deletable, and never serialized; see `flowGraph.ts`
 * (`toStartEndNodes` / `toStartEndEdges`) for how they are derived and
 * `DesignerPage` for how change events on them are ignored.
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
      title="Input — the instance data fed into the first participant(s)."
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
      title="Output — the final decision collected from the last participant(s)."
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
