import {
  memo,
  useCallback,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  useReactFlow,
  useStore,
  type EdgeProps,
  type Node as FlowNode,
  type ReactFlowState,
} from "reactflow";

import { useDesignerStore } from "./designerStore";
import {
  bendFromKnob,
  floatingEdgeGeometry,
  reciprocalOffset,
  rectCenter,
  type Rect,
} from "./edgeGeometry";
import type { FloatingEdgeData } from "./flowGraph";

/**
 * Floating, bendable canvas edge (task 11.4).
 *
 * Ignores handle positions: the ends attach where the line toward the other
 * node (or toward the bend) meets each node's border, computed from the nodes'
 * absolute positions and measured sizes. The path is a quadratic bezier whose
 * drag knob sits ON the curve at t = 0.5 (see `edgeGeometry.ts`).
 *
 * The knob appears on hover/selection; dragging it stores the bend in the
 * designer store (`setEdgeBend`), double-clicking resets it. The edge keeps
 * React Flow's wide invisible interaction path, so click-to-select and the
 * right-click context menu still work on the whole curve.
 */

/** A measured node's rect in flow coordinates, or null before measurement. */
function nodeRect(node: FlowNode | undefined): Rect | null {
  if (!node || !node.width || !node.height) return null;
  const pos = node.positionAbsolute ?? node.position;
  return { x: pos.x, y: pos.y, width: node.width, height: node.height };
}

const KNOB_RADIUS = 6;

function FloatingEdgeComponent({
  id,
  source,
  target,
  markerEnd,
  style,
  label,
  labelStyle,
  selected,
  data,
}: EdgeProps<FloatingEdgeData>) {
  const sourceNode = useStore(
    useCallback((s: ReactFlowState) => s.nodeInternals.get(source), [source]),
  );
  const targetNode = useStore(
    useCallback((s: ReactFlowState) => s.nodeInternals.get(target), [target]),
  );
  const { screenToFlowPosition } = useReactFlow();
  const setEdgeBend = useDesignerStore((s) => s.setEdgeBend);
  const resetEdgeBend = useDesignerStore((s) => s.resetEdgeBend);

  const [hovered, setHovered] = useState(false);
  const [dragging, setDragging] = useState(false);
  // Latest node centres for the drag handler (nodes don't move mid-drag).
  const centres = useRef<{ s: { x: number; y: number }; t: { x: number; y: number } } | null>(
    null,
  );

  const onPointerDown = useCallback((e: ReactPointerEvent<SVGCircleElement>) => {
    // Keep the pane from panning and nodes from dragging.
    e.stopPropagation();
    e.preventDefault();
    e.currentTarget.setPointerCapture?.(e.pointerId);
    setDragging(true);
  }, []);

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<SVGCircleElement>) => {
      if (!dragging || !centres.current) return;
      e.stopPropagation();
      const knob = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      setEdgeBend(id, bendFromKnob(knob, centres.current.s, centres.current.t));
    },
    [dragging, id, screenToFlowPosition, setEdgeBend],
  );

  const endDrag = useCallback((e: ReactPointerEvent<SVGCircleElement>) => {
    e.stopPropagation();
    e.currentTarget.releasePointerCapture?.(e.pointerId);
    setDragging(false);
  }, []);

  const onDoubleClick = useCallback(
    (e: ReactMouseEvent) => {
      e.stopPropagation();
      resetEdgeBend(id);
    },
    [id, resetEdgeBend],
  );

  const sRect = nodeRect(sourceNode);
  const tRect = nodeRect(targetNode);
  if (!sRect || !tRect) return null;

  const sc = rectCenter(sRect);
  const tc = rectCenter(tRect);
  centres.current = { s: sc, t: tc };
  const geo = floatingEdgeGeometry(
    sRect,
    tRect,
    data?.bend ?? null,
    data?.reciprocal ? reciprocalOffset(sc, tc) : null,
  );
  const color = data?.color ?? (style?.stroke as string | undefined) ?? "currentColor";
  const showKnob = hovered || selected || dragging;

  return (
    <g
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      data-testid="floating-edge"
    >
      <BaseEdge
        id={id}
        path={geo.path}
        markerEnd={markerEnd}
        style={style}
        interactionWidth={24}
      />
      {showKnob ? (
        <circle
          className="nodrag nopan"
          data-testid="edge-bend-knob"
          cx={geo.knob.x}
          cy={geo.knob.y}
          r={KNOB_RADIUS}
          fill="hsl(var(--background))"
          stroke={color}
          strokeWidth={2}
          style={{ cursor: dragging ? "grabbing" : "grab", pointerEvents: "all" }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onMouseDown={(e) => e.stopPropagation()}
          onDoubleClick={onDoubleClick}
        >
          <title>Drag to bend · double-click to reset</title>
        </circle>
      ) : null}
      {label ? (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan pointer-events-none absolute rounded bg-background/85 px-1.5 py-0.5 text-[11px]"
            style={{
              transform: `translate(-50%, -100%) translate(${geo.knob.x}px, ${geo.knob.y - KNOB_RADIUS - 4}px)`,
              color,
              fontWeight: 600,
              ...(labelStyle as object | undefined),
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </g>
  );
}

export const FloatingEdge = memo(FloatingEdgeComponent);
