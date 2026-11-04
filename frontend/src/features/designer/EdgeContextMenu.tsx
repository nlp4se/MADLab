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

/**
 * Right-click context menu for canvas edges (task 11.2).
 *
 * Works for ANY canvas edge: real participant edges and the Start/End IO
 * connectors. "Delete" goes through the store's `deleteCanvasEdge`, which
 * routes by id (participant edge -> `removeEdge`, `__start__->X` ->
 * `removeEntryNode`, `X->__end__` -> `removeExitNode`), so the artifact only
 * ever mutates through store actions.
 *
 * Rendered in a PORTAL to `document.body` with a high z-index (same approach
 * as `DropdownMenuContent`) because the React Flow canvas otherwise paints over
 * inline menus. Closes on outside click, Escape, or after choosing; the canvas
 * also closes it on pane click.
 */
export interface EdgeMenuState {
  edgeId: string;
  /** Viewport (client) coordinates of the right-click. */
  x: number;
  y: number;
}

/** Menu state + the `onEdgeContextMenu` handler React Flow calls. */
export function useEdgeContextMenu() {
  const [menu, setMenu] = useState<EdgeMenuState | null>(null);
  const onEdgeContextMenu = useCallback(
    (event: MouseEvent, edge: { id: string }) => {
      // Suppress the browser's native context menu.
      event.preventDefault();
      setMenu({ edgeId: edge.id, x: event.clientX, y: event.clientY });
    },
    [],
  );
  const close = useCallback(() => setMenu(null), []);
  return { menu, onEdgeContextMenu, close };
}

export function EdgeContextMenu({
  menu,
  onClose,
}: {
  menu: EdgeMenuState | null;
  onClose: () => void;
}) {
  const deleteCanvasEdge = useDesignerStore((s) => s.deleteCanvasEdge);
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

  return createPortal(
    <div
      ref={ref}
      role="menu"
      aria-label="Edge actions"
      data-testid="edge-context-menu"
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
          deleteCanvasEdge(menu.edgeId);
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
