/**
 * Pure geometry for floating, bendable canvas edges (task 11.4).
 *
 * Edges ignore React Flow handle positions: each end attaches where the line
 * toward the other end (or toward the bend) crosses the node's border, so a
 * connection can leave/enter any side and arrowheads alone convey direction.
 *
 * Every edge is a quadratic bezier S -> T whose visible drag knob M lies ON the
 * curve at t = 0.5. Given M, the control point is C = 2M - (S + T) / 2, because
 * B(0.5) = S/4 + C/2 + T/4. The bend is stored as the offset of M from the
 * straight midpoint between the two node CENTRES (flow coordinates), so moving
 * a node keeps the bend's shape sensible.
 *
 * Kept free of React/React Flow so it is unit-testable (jsdom cannot measure
 * nodes).
 */
import type { XYPosition } from "./layout";

/** Axis-aligned node rectangle in flow coordinates (top-left + size). */
export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Perpendicular separation of a reciprocal pair (A->B and B->A), in px. */
export const RECIPROCAL_OFFSET = 30;

export function rectCenter(rect: Rect): XYPosition {
  return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
}

export function midpoint(a: XYPosition, b: XYPosition): XYPosition {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

/**
 * Where the ray from the rect's centre toward `toward` crosses the rect border.
 * Returns the centre itself when `toward` coincides with it (degenerate).
 */
export function rectBoundaryPoint(rect: Rect, toward: XYPosition): XYPosition {
  const c = rectCenter(rect);
  const dx = toward.x - c.x;
  const dy = toward.y - c.y;
  const hw = rect.width / 2;
  const hh = rect.height / 2;
  if ((dx === 0 && dy === 0) || hw <= 0 || hh <= 0) return c;
  // Scale the direction so it just reaches the nearer of the two border pairs.
  const scale = 1 / Math.max(Math.abs(dx) / hw, Math.abs(dy) / hh);
  return { x: c.x + dx * scale, y: c.y + dy * scale };
}

/** Quadratic control point whose curve passes through `mid` at t = 0.5. */
export function quadraticControlPoint(
  source: XYPosition,
  target: XYPosition,
  mid: XYPosition,
): XYPosition {
  return {
    x: 2 * mid.x - (source.x + target.x) / 2,
    y: 2 * mid.y - (source.y + target.y) / 2,
  };
}

/** Point on the quadratic bezier S-C-T at parameter t. */
export function quadraticPoint(
  s: XYPosition,
  c: XYPosition,
  t: XYPosition,
  u: number,
): XYPosition {
  const a = (1 - u) * (1 - u);
  const b = 2 * (1 - u) * u;
  const d = u * u;
  return { x: a * s.x + b * c.x + d * t.x, y: a * s.y + b * c.y + d * t.y };
}

/**
 * Default knob offset for one edge of a reciprocal pair: perpendicular to the
 * edge's own direction (rotated to its left), `distance` px long. Because A->B
 * and B->A have opposite directions, the same rule bows them to opposite
 * sides, so a circular exchange shows as two separate curves.
 */
export function reciprocalOffset(
  sourceCenter: XYPosition,
  targetCenter: XYPosition,
  distance = RECIPROCAL_OFFSET,
): XYPosition {
  const dx = targetCenter.x - sourceCenter.x;
  const dy = targetCenter.y - sourceCenter.y;
  const len = Math.hypot(dx, dy);
  if (len === 0) return { x: 0, y: distance };
  return { x: (dy / len) * distance, y: (-dx / len) * distance };
}

/** Bend offset (relative to the centres' midpoint) for a knob at `knob`. */
export function bendFromKnob(
  knob: XYPosition,
  sourceCenter: XYPosition,
  targetCenter: XYPosition,
): XYPosition {
  const m = midpoint(sourceCenter, targetCenter);
  return { x: knob.x - m.x, y: knob.y - m.y };
}

export interface FloatingEdgeGeometry {
  /** Source / target attachment points on the node borders. */
  source: XYPosition;
  target: XYPosition;
  /** Quadratic control point. */
  control: XYPosition;
  /** The drag knob (on the curve at t = 0.5). */
  knob: XYPosition;
  /** Midpoint of the two node centres (the bend's origin). */
  origin: XYPosition;
  /** SVG path data. */
  path: string;
}

const isZero = (p: XYPosition) => Math.abs(p.x) < 1e-9 && Math.abs(p.y) < 1e-9;

/**
 * Full geometry of a floating edge between two node rects.
 *
 * `bend` is the stored knob offset; when absent, `defaultOffset` (e.g. the
 * reciprocal offset) applies, else the edge is straight. Unbent edges attach
 * toward the other node's centre; bent ones attach toward the control point so
 * they leave/enter the node along the curve's tangent.
 */
export function floatingEdgeGeometry(
  sourceRect: Rect,
  targetRect: Rect,
  bend?: XYPosition | null,
  defaultOffset?: XYPosition | null,
): FloatingEdgeGeometry {
  const cs = rectCenter(sourceRect);
  const ct = rectCenter(targetRect);
  const origin = midpoint(cs, ct);
  const offset = bend ?? defaultOffset ?? { x: 0, y: 0 };
  const knob = { x: origin.x + offset.x, y: origin.y + offset.y };

  let source: XYPosition;
  let target: XYPosition;
  let control: XYPosition;
  if (isZero(offset)) {
    source = rectBoundaryPoint(sourceRect, ct);
    target = rectBoundaryPoint(targetRect, cs);
    control = quadraticControlPoint(source, target, knob);
  } else {
    // First aim at the knob, then refine once toward the resulting control
    // point (the curve's tangent direction at each end).
    const s0 = rectBoundaryPoint(sourceRect, knob);
    const t0 = rectBoundaryPoint(targetRect, knob);
    const c0 = quadraticControlPoint(s0, t0, knob);
    source = rectBoundaryPoint(sourceRect, c0);
    target = rectBoundaryPoint(targetRect, c0);
    control = quadraticControlPoint(source, target, knob);
  }

  const path =
    `M ${source.x},${source.y} ` +
    `Q ${control.x},${control.y} ${target.x},${target.y}`;
  return { source, target, control, knob, origin, path };
}
