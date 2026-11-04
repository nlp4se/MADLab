import { describe, expect, it } from "vitest";

import {
  RECIPROCAL_OFFSET,
  bendFromKnob,
  floatingEdgeGeometry,
  quadraticControlPoint,
  quadraticPoint,
  reciprocalOffset,
  rectBoundaryPoint,
  rectCenter,
  sampleEdgeCurve,
  polylineHitsRect,
  segmentHitsRect,
  type Rect,
} from "./edgeGeometry";
import { resolveConnection } from "./ioNodes";

const RECT: Rect = { x: 0, y: 0, width: 200, height: 100 }; // centre (100, 50)

/** True if `p` lies on the border of `r` (within float tolerance). */
function onBorder(r: Rect, p: { x: number; y: number }) {
  const eps = 1e-6;
  const inX = p.x >= r.x - eps && p.x <= r.x + r.width + eps;
  const inY = p.y >= r.y - eps && p.y <= r.y + r.height + eps;
  const onV = Math.abs(p.x - r.x) < eps || Math.abs(p.x - (r.x + r.width)) < eps;
  const onH = Math.abs(p.y - r.y) < eps || Math.abs(p.y - (r.y + r.height)) < eps;
  return inX && inY && (onV || onH);
}

describe("edgeGeometry — rect boundary intersection", () => {
  it("hits the side facing the target point", () => {
    expect(rectBoundaryPoint(RECT, { x: 500, y: 50 })).toEqual({ x: 200, y: 50 });
    expect(rectBoundaryPoint(RECT, { x: -300, y: 50 })).toEqual({ x: 0, y: 50 });
    expect(rectBoundaryPoint(RECT, { x: 100, y: 400 })).toEqual({ x: 100, y: 100 });
    expect(rectBoundaryPoint(RECT, { x: 100, y: -400 })).toEqual({ x: 100, y: 0 });
  });

  it("hits a corner on the diagonal and stays on the border for any direction", () => {
    expect(rectBoundaryPoint(RECT, { x: 300, y: 150 })).toEqual({ x: 200, y: 100 });
    for (let k = 0; k < 64; k += 1) {
      const a = (2 * Math.PI * k) / 64;
      const toward = { x: 100 + 1000 * Math.cos(a), y: 50 + 1000 * Math.sin(a) };
      const p = rectBoundaryPoint(RECT, toward);
      expect(onBorder(RECT, p)).toBe(true);
      // ...and along the ray from the centre toward the target.
      const cross = (p.x - 100) * (toward.y - 50) - (p.y - 50) * (toward.x - 100);
      expect(Math.abs(cross)).toBeLessThan(1e-6);
    }
  });

  it("returns the centre for a degenerate direction", () => {
    expect(rectBoundaryPoint(RECT, rectCenter(RECT))).toEqual({ x: 100, y: 50 });
  });
});

describe("edgeGeometry — quadratic through a mid knob", () => {
  it("places the knob on the curve at t = 0.5", () => {
    const s = { x: 0, y: 0 };
    const t = { x: 100, y: 0 };
    const m = { x: 50, y: 40 };
    const c = quadraticControlPoint(s, t, m);
    expect(c).toEqual({ x: 50, y: 80 });
    expect(quadraticPoint(s, c, t, 0.5)).toEqual(m);
  });

  it("keeps a straight edge straight when the knob is the midpoint", () => {
    const c = quadraticControlPoint({ x: 0, y: 0 }, { x: 10, y: 20 }, { x: 5, y: 10 });
    expect(c).toEqual({ x: 5, y: 10 });
  });
});

describe("edgeGeometry — reciprocal default offset", () => {
  it("is perpendicular, RECIPROCAL_OFFSET long, and opposite for the reverse edge", () => {
    const a = { x: 0, y: 0 };
    const b = { x: 100, y: 0 };
    const ab = reciprocalOffset(a, b);
    const ba = reciprocalOffset(b, a);
    expect(Math.hypot(ab.x, ab.y)).toBeCloseTo(RECIPROCAL_OFFSET);
    expect(ab.x * (b.x - a.x) + ab.y * (b.y - a.y)).toBeCloseTo(0); // perpendicular
    expect(ba.x).toBeCloseTo(-ab.x);
    expect(ba.y).toBeCloseTo(-ab.y);
  });
});

describe("edgeGeometry — floating edge between two rects", () => {
  const left: Rect = { x: 0, y: 0, width: 100, height: 50 }; // centre (50, 25)
  const right: Rect = { x: 300, y: 0, width: 100, height: 50 }; // centre (350, 25)

  it("attaches unbent edges to the facing borders, knob at the centres' midpoint", () => {
    const g = floatingEdgeGeometry(left, right);
    expect(g.source).toEqual({ x: 100, y: 25 });
    expect(g.target).toEqual({ x: 300, y: 25 });
    expect(g.knob).toEqual({ x: 200, y: 25 });
    expect(g.path.startsWith("M 100,25 Q")).toBe(true);
  });

  it("works the same in the reverse direction (any side can be the source)", () => {
    const g = floatingEdgeGeometry(right, left);
    expect(g.source).toEqual({ x: 300, y: 25 });
    expect(g.target).toEqual({ x: 100, y: 25 });
  });

  it("applies a stored bend (knob = origin + bend) and keeps the knob on the curve", () => {
    const bend = { x: 0, y: -120 };
    const g = floatingEdgeGeometry(left, right, bend);
    expect(g.knob).toEqual({ x: 200, y: -95 });
    expect(quadraticPoint(g.source, g.control, g.target, 0.5).x).toBeCloseTo(g.knob.x);
    expect(quadraticPoint(g.source, g.control, g.target, 0.5).y).toBeCloseTo(g.knob.y);
    // Bent upward: both ends leave/enter through the top half, on the border.
    expect(onBorder(left, g.source)).toBe(true);
    expect(onBorder(right, g.target)).toBe(true);
    expect(g.source.y).toBeLessThan(25);
    expect(g.target.y).toBeLessThan(25);
  });

  it("separates a reciprocal pair by default; a stored bend overrides it", () => {
    const ab = floatingEdgeGeometry(left, right, null, reciprocalOffset({ x: 50, y: 25 }, { x: 350, y: 25 }));
    const ba = floatingEdgeGeometry(right, left, null, reciprocalOffset({ x: 350, y: 25 }, { x: 50, y: 25 }));
    expect(Math.abs(ab.knob.y - ba.knob.y)).toBeCloseTo(2 * RECIPROCAL_OFFSET);
    const bent = floatingEdgeGeometry(left, right, { x: 0, y: 0 }, { x: 0, y: 30 });
    expect(bent.knob).toEqual({ x: 200, y: 25 });
  });

  it("bendFromKnob inverts the knob placement", () => {
    const bend = bendFromKnob({ x: 210, y: 5 }, { x: 50, y: 25 }, { x: 350, y: 25 });
    expect(bend).toEqual({ x: 10, y: -20 });
    expect(floatingEdgeGeometry(left, right, bend).knob).toEqual({ x: 210, y: 5 });
  });
});

describe("resolveConnection — direction-agnostic handles", () => {
  it("keeps drag direction between participants and rejects self-loops", () => {
    expect(resolveConnection("a", "b")).toEqual({ kind: "edge", source: "a", target: "b" });
    expect(resolveConnection("b", "a")).toEqual({ kind: "edge", source: "b", target: "a" });
    expect(resolveConnection("a", "a")).toBeNull();
  });

  it("normalizes anything touching Start/End, rejecting Start<->End", () => {
    expect(resolveConnection("__start__", "a")).toEqual({ kind: "entry", nodeId: "a" });
    expect(resolveConnection("a", "__start__")).toEqual({ kind: "entry", nodeId: "a" });
    expect(resolveConnection("a", "__end__")).toEqual({ kind: "exit", nodeId: "a" });
    expect(resolveConnection("__end__", "a")).toEqual({ kind: "exit", nodeId: "a" });
    expect(resolveConnection("__start__", "__end__")).toBeNull();
    expect(resolveConnection("__end__", "__start__")).toBeNull();
  });
});

describe("edgeGeometry — curve vs box hit tests (task 11.8)", () => {
  it("segmentHitsRect detects crossing, containment and misses (with margin)", () => {
    const box: Rect = { x: 100, y: 100, width: 100, height: 50 };
    expect(segmentHitsRect({ x: 0, y: 125 }, { x: 300, y: 125 }, box)).toBe(true);
    expect(segmentHitsRect({ x: 120, y: 110 }, { x: 130, y: 120 }, box)).toBe(true);
    expect(segmentHitsRect({ x: 0, y: 90 }, { x: 300, y: 90 }, box)).toBe(false);
    expect(segmentHitsRect({ x: 0, y: 95 }, { x: 300, y: 95 }, box, 10)).toBe(true);
    // Diagonal passing just outside a corner.
    expect(segmentHitsRect({ x: 0, y: 190 }, { x: 90, y: 100 }, box)).toBe(false);
  });

  it("a bent curve can route around a box that blocks the straight line", () => {
    const s: Rect = { x: 0, y: 0, width: 80, height: 40 };
    const t: Rect = { x: 600, y: 0, width: 80, height: 40 };
    const blocker: Rect = { x: 280, y: -30, width: 120, height: 100 };
    const straight = sampleEdgeCurve(floatingEdgeGeometry(s, t, null));
    expect(polylineHitsRect(straight, blocker)).toBe(true);
    const bent = sampleEdgeCurve(floatingEdgeGeometry(s, t, { x: 0, y: -160 }));
    expect(polylineHitsRect(bent, blocker)).toBe(false);
  });
});
