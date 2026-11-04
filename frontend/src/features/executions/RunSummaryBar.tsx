import { Card, CardContent } from "@/components/ui/card";
import type { ExecutionInstanceResult, RunSummary } from "@/api";

import { formatCost, formatCount, formatDuration, MISSING } from "./format";

/**
 * Run summary bar + compact per-instance / per-row figures (task 11.18).
 *
 * Wall time is the run's clock time (start → finish, elapsed so far while
 * running); model time sums every model call's latency. Token counts and calls
 * cover every model call (debater turns, judge, summarizer). Missing values
 * (old runs without timestamps, providers that report no cost) show `—`.
 */

export const WALL_VS_MODEL_HINT =
  "Wall time is the clock time from start to finish (elapsed so far while " +
  "running). Model time adds up the latency of every model call, so it can " +
  "exceed wall time when instances run in parallel, or fall below it because " +
  "of retries and overhead between calls.";

export function RunSummaryBar({
  summary,
}: {
  summary: RunSummary | null | undefined;
}) {
  const items: { label: string; value: string; title?: string }[] = [
    { label: "Wall time", value: formatDuration(summary?.wall_time_s) },
    { label: "Model time", value: formatDuration(summary?.model_time_s) },
    {
      label: "Input tokens",
      value: formatCount(summary?.input_tokens),
      title: summary ? `${formatCount(summary.total_tokens)} total tokens` : undefined,
    },
    { label: "Output tokens", value: formatCount(summary?.output_tokens) },
    { label: "Cost", value: formatCost(summary?.cost_usd) },
    { label: "Calls", value: formatCount(summary?.calls) },
  ];

  return (
    <Card className="mb-4 min-w-0" data-testid="run-summary">
      <CardContent className="space-y-2 py-4">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-6">
          {items.map((item) => (
            <div key={item.label} className="min-w-0" title={item.title}>
              <dt className="text-xs text-muted-foreground">{item.label}</dt>
              <dd
                className="truncate text-sm font-medium tabular-nums"
                data-testid={`run-summary-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
              >
                {item.value}
              </dd>
            </div>
          ))}
        </dl>
        <p className="text-xs text-muted-foreground">{WALL_VS_MODEL_HINT}</p>
      </CardContent>
    </Card>
  );
}

/** `12.3 s · 1,234 in / 456 out`, or null when nothing was recorded. */
export function instanceFiguresText(
  instance: Pick<ExecutionInstanceResult, "usage" | "duration_s">,
): string | null {
  const usage = instance.usage ?? null;
  const duration = instance.duration_s ?? null;
  if (usage == null && duration == null) return null;
  const tokens = usage
    ? `${formatCount(usage.input_tokens)} in / ${formatCount(usage.output_tokens)} out`
    : `${MISSING} in / ${MISSING} out`;
  return `${formatDuration(duration)} · ${tokens}`;
}

/** Per-instance time + tokens, shown in each instance header. */
export function InstanceFigures({
  instance,
}: {
  instance: Pick<ExecutionInstanceResult, "usage" | "duration_s">;
}) {
  const text = instanceFiguresText(instance);
  if (text == null) return null;
  return (
    <span
      className="shrink-0 text-xs font-normal tabular-nums text-muted-foreground"
      data-testid="instance-figures"
      title="Debate wall time · input / output tokens"
    >
      {text}
    </span>
  );
}
