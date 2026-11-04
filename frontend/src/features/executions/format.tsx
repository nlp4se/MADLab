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

/** Placeholder for a figure that is unknown (old runs, nothing reported). */
export const MISSING = "—";

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

const pad2 = (n: number) => String(n).padStart(2, "0");

/**
 * Format a duration in seconds: `850 ms`, `12.3 s`, `2 min 05 s`,
 * `1 h 02 min`; `—` when missing (task 11.18).
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (!isFiniteNumber(seconds) || seconds < 0) return MISSING;
  const ms = Math.round(seconds * 1000);
  if (ms < 1000) return `${ms} ms`;
  const tenths = Math.round(seconds * 10) / 10;
  if (tenths < 60) return `${tenths.toFixed(1)} s`;
  const whole = Math.round(seconds);
  if (whole < 3600) {
    return `${Math.floor(whole / 60)} min ${pad2(whole % 60)} s`;
  }
  const minutes = Math.round(seconds / 60);
  return `${Math.floor(minutes / 60)} h ${pad2(minutes % 60)} min`;
}

const COUNT_FORMAT = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

/** Format a count with thousands separators (`12,345`); `—` when missing. */
export function formatCount(value: number | null | undefined): string {
  return isFiniteNumber(value) ? COUNT_FORMAT.format(value) : MISSING;
}

/** Format a USD cost (`$0.0123`, `$1.25`); `—` when no call reported one. */
export function formatCost(usd: number | null | undefined): string {
  if (!isFiniteNumber(usd)) return MISSING;
  return `$${usd.toFixed(Math.abs(usd) < 1 ? 4 : 2)}`;
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
