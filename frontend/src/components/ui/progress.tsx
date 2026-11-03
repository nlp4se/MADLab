import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Minimal, dependency-free progress bar (shadcn/ui style).
 *
 * Renders a determinate bar whose fill width tracks `value` (0–100). Used by
 * the executions history + detail views to show per-run progress (Req 10.5,
 * 11.1). Exposes the ARIA `progressbar` role with the standard value
 * attributes so the control is accessible.
 */
export interface ProgressProps
  extends React.HTMLAttributes<HTMLDivElement> {
  /** Completion percentage, 0–100. Clamped to that range. */
  value?: number;
  /** Optional class applied to the moving indicator (e.g. a themed colour). */
  indicatorClassName?: string;
}

const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(
  ({ className, value = 0, indicatorClassName, ...props }, ref) => {
    const clamped = Math.min(100, Math.max(0, value));
    return (
      <div
        ref={ref}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(clamped)}
        className={cn(
          "relative h-2 w-full overflow-hidden rounded-full bg-muted",
          className,
        )}
        {...props}
      >
        <div
          className={cn(
            "h-full rounded-full bg-primary transition-all",
            indicatorClassName,
          )}
          style={{ width: `${clamped}%` }}
        />
      </div>
    );
  },
);
Progress.displayName = "Progress";

export { Progress };
