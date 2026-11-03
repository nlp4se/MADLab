import { Badge, type BadgeProps } from "@/components/ui/badge";
import type { JsonObject } from "@/api";

/**
 * Small presentational helpers shared by the executions history + detail views:
 * a status badge, timestamp + percent formatting, and aggregate-metric
 * extraction (Req 11.1, 11.5).
 */

/** Map a lifecycle status to a Badge variant + label. */
export function StatusBadge({ status }: { status: string }) {
  const variant: BadgeProps["variant"] =
    status === "completed"
      ? "default"
      : status === "failed"
        ? "destructive"
        : status === "partial"
          ? "agreement"
          : status === "cancelled"
            ? "outline"
            : "secondary";
  return (
    <Badge variant={variant} className="capitalize" data-status={status}>
      {status}
    </Badge>
  );
}

/** Format an ISO timestamp for display; empty string when absent. */
export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}

/** Format a 0–1 progress fraction as a rounded percentage string. */
export function formatPercent(fraction: number): string {
  return `${Math.round(Math.min(1, Math.max(0, fraction)) * 100)}%`;
}

export interface AggregateMetric {
  label: string;
  value: string;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/**
 * Extract a short, display-ready list of aggregate metrics from the backend
 * metrics payload (Req 11.1, 11.5). The runner stores metrics in the
 * evaluation shape `{ overall: { accuracy }, per_class: { label: {...} } }`
 * (see `backend/mad/evaluation/metrics.py`); we surface overall accuracy plus
 * the per-class count, degrading gracefully for any other shape.
 */
export function aggregateMetrics(
  metrics: JsonObject | null | undefined,
): AggregateMetric[] {
  if (!metrics) return [];
  const out: AggregateMetric[] = [];
  const overall = asRecord(metrics.overall);
  if (typeof overall.accuracy === "number") {
    out.push({
      label: "Accuracy",
      value: `${(overall.accuracy * 100).toFixed(1)}%`,
    });
  }
  const perClass = asRecord(metrics.per_class);
  const classes = Object.keys(perClass);
  if (classes.length > 0) {
    out.push({ label: "Classes", value: String(classes.length) });
  }
  return out;
}

/**
 * The per-class precision/recall/F1/support breakdown, ready for a table.
 * Returns an empty list when the payload has no per-class section (Req 11.5).
 */
export interface PerClassRow {
  label: string;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  support: number | null;
}

export function perClassRows(
  metrics: JsonObject | null | undefined,
): PerClassRow[] {
  if (!metrics) return [];
  const perClass = asRecord(metrics.per_class);
  const num = (v: unknown): number | null =>
    typeof v === "number" && Number.isFinite(v) ? v : null;
  return Object.entries(perClass).map(([label, raw]) => {
    const r = asRecord(raw);
    return {
      label,
      precision: num(r.precision),
      recall: num(r.recall),
      f1: num(r["f1-score"]),
      support: num(r.support),
    };
  });
}
