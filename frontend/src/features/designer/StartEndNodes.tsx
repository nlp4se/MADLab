import { memo } from "react";
import type { NodeProps } from "reactflow";
import { AlertTriangle, FlagTriangleRight, LogIn } from "lucide-react";

import { cn } from "@/lib/utils";
import { SideHandles } from "./SideHandles";

/**
 * Synthetic Start / End canvas nodes.
 *
 * The nodes themselves are NOT part of the debate graph (not deletable; only
 * Start is selectable, to open the Input panel; their positions live in the UI-only layout map and are saved in
 * the presentation-only `artifact.ui.nodes`). Their connectors ARE: Start -> X
 * persists as `interaction.topology.entry_nodes` and X -> End as `exit_nodes`
 * (null = engine default, see `ioNodes.ts`). See `flowGraph.ts`
 * (`toStartEndNodes` / `toStartEndEdges`) for the projection and
 * `DesignerPage` for how connector deletes/drags route to the store.
 *
 * Like participants they expose direction-agnostic handles on every side; a
 * connection touching Start always means Start -> participant and one touching
 * End always means participant -> End (`resolveConnection` in `ioNodes.ts`).
 */

export const START_NODE_ID = "__start__";
export const END_NODE_ID = "__end__";

export interface StartEndNodeData {
  label: string;
  /** Start only (task 11.10): the input template is empty, so runs carry no task. */
  inputMissing?: boolean;
}

/**
 * Start: emits the instance input. Clicking it opens the Input panel (task
 * 11.10); an amber marker flags an empty input template.
 */
function StartNodeComponent({ data, selected }: NodeProps<StartEndNodeData>) {
  const missing = data?.inputMissing === true;
  return (
    <div
      className={cn(
        "group relative flex items-center gap-1.5 rounded-full border-2 border-emerald-500 bg-emerald-500/10 px-3 py-2 text-sm font-semibold text-emerald-700 shadow-sm dark:text-emerald-400",
        selected && "ring-2 ring-emerald-500 ring-offset-2 ring-offset-background",
      )}
      data-testid="start-node"
      title={
        missing
          ? "Input — no input template yet: runs would give the participants no task. Click to define the input."
          : "Input — the task input fed into the connected participant(s). Click to edit it; drag from here to a participant to connect it."
      }
    >
      <LogIn className="size-4" aria-hidden />
      Start
      {missing ? (
        <span
          className="absolute -right-1.5 -top-1.5 flex size-4 items-center justify-center rounded-full bg-amber-500 text-white shadow"
          data-testid="start-node-input-missing"
          aria-label="No input template"
        >
          <AlertTriangle className="size-2.5" aria-hidden />
        </span>
      ) : null}
      <SideHandles color="#10b981" />
    </div>
  );
}

/** End: collects the final output. */
function EndNodeComponent(_props: NodeProps<StartEndNodeData>) {
  return (
    <div
      className="group relative flex items-center gap-1.5 rounded-full border-2 border-slate-500 bg-slate-500/10 px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm dark:text-slate-300"
      data-testid="end-node"
      title="Output — the final decision formed from the connected participant(s). Drag from a participant to here to connect it."
    >
      <FlagTriangleRight className="size-4" aria-hidden />
      End
      <SideHandles color="#64748b" />
    </div>
  );
}

export const StartNode = memo(StartNodeComponent);
export const EndNode = memo(EndNodeComponent);
