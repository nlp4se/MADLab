import { Handle, Position } from "reactflow";

import { cn } from "@/lib/utils";

/**
 * Four direction-agnostic connection handles, one per side (task 11.4).
 *
 * With `ConnectionMode.Loose` on the canvas every handle is a `source` that can
 * connect to any other handle, so a connection can start or end on any side of
 * a node; direction is conveyed by the arrowhead only (floating edges ignore
 * handle positions when drawing). The handles are subtle dots that appear on
 * node hover (the node root needs the Tailwind `group` class); the node body
 * itself stays draggable. Dropping a connection anywhere on a node's body also
 * connects (handled by the canvas' `onConnectEnd`).
 */
const SIDES = [
  { id: "top", position: Position.Top },
  { id: "right", position: Position.Right },
  { id: "bottom", position: Position.Bottom },
  { id: "left", position: Position.Left },
] as const;

export function SideHandles({ color }: { color: string }) {
  return (
    <>
      {SIDES.map((side) => (
        <Handle
          key={side.id}
          id={side.id}
          type="source"
          position={side.position}
          className={cn(
            "!size-2.5 !border-2 !border-background opacity-0 transition-opacity",
            "group-hover:opacity-100",
          )}
          style={{ background: color }}
        />
      ))}
    </>
  );
}
