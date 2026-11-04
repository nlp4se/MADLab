import { cn, WRAP_TEXT } from "@/lib/utils";

import type { TranscriptError } from "./transcript";

/**
 * The "Instance failed" alert (task 11.17): the instance-level error plus the
 * call errors the transcript recorded before the failure (the provider's own
 * text, e.g. a rate limit), so the user sees why a run failed without digging
 * through the transcript. Shared by the execution detail view and the chat
 * replay; long text wraps inside the card (11.15 `WRAP_TEXT`).
 */
export function InstanceFailedAlert({
  error,
  callErrors = [],
  labelFor,
  rounds,
  className,
}: {
  error: string;
  callErrors?: TranscriptError[];
  /** Display name for a node id (defaults to the id). */
  labelFor?: (nodeId: string) => string;
  /** Debate round count; errors at or past it are labelled "verdict". */
  rounds?: number;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "min-w-0 rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive",
        className,
      )}
      data-testid="instance-failed"
    >
      <p className="font-medium">Instance failed</p>
      <p className={cn("mt-1", WRAP_TEXT)}>{error}</p>
      {callErrors.length > 0 ? (
        <div className="mt-3">
          <p className="text-xs font-medium uppercase tracking-wide">
            Call errors ({callErrors.length})
          </p>
          <ul className="mt-1 space-y-1" data-testid="instance-call-errors">
            {callErrors.map((err, i) => (
              <li key={i} className={cn("text-foreground/80", WRAP_TEXT)}>
                <span className="font-medium">{labelFor ? labelFor(err.node_id) : err.node_id}</span>{" "}
                ·{" "}
                {rounds != null && err.round_index >= rounds
                  ? "verdict"
                  : `round ${err.round_index + 1}`}{" "}
                · {err.attempts}{" "}
                {err.attempts === 1 ? "attempt" : "attempts"}: {err.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
