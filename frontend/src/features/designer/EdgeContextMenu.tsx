import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent,
  type SyntheticEvent,
} from "react";
import { createPortal } from "react-dom";
import { Trash2 } from "lucide-react";

import { useDesignerStore } from "./designerStore";
import { END_NODE_ID, START_NODE_ID } from "./StartEndNodes";

/**
 * Right-click context menu for canvas edges (task 11.2) and participant nodes
 * (task 11.5).
 *
 * Edges: works for ANY canvas edge, real participant edges and the Start/End
 * IO connectors. "Delete" goes through the store's `deleteCanvasEdge`, which
 * routes by id (participant edge -> `removeEdge`, `__start__->X` ->
 * `removeEntryNode`, `X->__end__` -> `removeExitNode`).
 *
 * Nodes: "Delete" calls `removeNode`, which also drops incident edges, the
 * node's Start/End connectors, its layout position and edge bends. The
 * synthetic Start/End nodes are always present, so they get no menu (the
 * native menu is still suppressed there).
 *
 * The artifact only ever mutates through store actions. A single menu state
 * means at most one menu is open at a time. Rendered in a PORTAL to
 * `document.body` with a high z-index (same approach as `DropdownMenuContent`)
 * because the React Flow canvas otherwise paints over inline menus. Closes on
 * outside click, Escape, or after choosing; the canvas also closes it on pane
 * click and when the viewport starts moving.
 */
export interface CanvasMenuState {
  kind: "edge" | "node";
  /** Edge id (`source->target`) or participant node id. */
  id: string;
  /** Viewport (client) coordinates of the right-click. */
  x: number;
  y: number;
}

/**
 * Menu state + the `onEdgeContextMenu` / `onNodeContextMenu` handlers React
 * Flow calls.
 */
export function useCanvasContextMenu() {
  const [menu, setMenu] = useState<CanvasMenuState | null>(null);
  const onEdgeContextMenu = useCallback(
    (event: MouseEvent, edge: { id: string }) => {
      // Suppress the browser's native context menu.
      event.preventDefault();
      setMenu({ kind: "edge", id: edge.id, x: event.clientX, y: event.clientY });
    },
    [],
  );
  const onNodeContextMenu = useCallback(
    (event: MouseEvent, node: { id: string }) => {
      event.preventDefault();
      // Start/End are synthetic and always present: nothing to delete.
      if (node.id === START_NODE_ID || node.id === END_NODE_ID) {
        setMenu(null);
        return;
      }
      setMenu({ kind: "node", id: node.id, x: event.clientX, y: event.clientY });
    },
    [],
  );
  const close = useCallback(() => setMenu(null), []);
  return { menu, onEdgeContextMenu, onNodeContextMenu, close };
}

/** Edge-only name kept for existing callers (task 11.2). */
export const useEdgeContextMenu = useCanvasContextMenu;

export function CanvasContextMenu({
  menu,
  onClose,
}: {
  menu: CanvasMenuState | null;
  onClose: () => void;
}) {
  const deleteCanvasEdge = useDesignerStore((s) => s.deleteCanvasEdge);
  const removeNode = useDesignerStore((s) => s.removeNode);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu) return;
    const onDown = (e: globalThis.MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menu, onClose]);

  if (!menu) return null;

  const stop = (e: SyntheticEvent) => e.stopPropagation();
  const isNode = menu.kind === "node";

  return createPortal(
    <div
      ref={ref}
      role="menu"
      aria-label={isNode ? "Node actions" : "Edge actions"}
      data-testid={isNode ? "node-context-menu" : "edge-context-menu"}
      style={{ position: "fixed", top: menu.y, left: menu.x }}
      className="z-[1000] min-w-[8rem] overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
      onMouseDown={stop}
      onPointerDown={stop}
      onClick={stop}
      onContextMenu={(e) => e.preventDefault()}
    >
      <button
        type="button"
        role="menuitem"
        autoFocus
        className="flex w-full cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm text-destructive outline-none transition-colors hover:bg-destructive/10 focus:bg-destructive/10"
        onClick={() => {
          if (isNode) removeNode(menu.id);
          else deleteCanvasEdge(menu.id);
          onClose();
        }}
      >
        <Trash2 className="size-4" aria-hidden />
        Delete
      </button>
    </div>,
    document.body,
  );
}

/** Edge-only name kept for existing callers (task 11.2). */
export const EdgeContextMenu = CanvasContextMenu;
