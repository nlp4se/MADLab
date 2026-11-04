import { Badge } from "@/components/ui/badge";
import { cn, SCROLL_PRE, WRAP_TEXT } from "@/lib/utils";

import { decisionDisplay, type DisplayValue } from "./decisionDisplay";
import type { TranscriptDecision } from "./transcript";

/**
 * Shared rendering of a final decision for the chat replay and the execution
 * detail view (task 11.12): only the short label goes into the pill; long text
 * and structured objects render as a normal block, with the raw JSON kept in a
 * "Structured decision" disclosure.
 */

/** Recursive, readable rendering of a {@link DisplayValue}. */
export function DisplayValueView({
  value,
  className,
}: {
  value: DisplayValue;
  className?: string;
}) {
  switch (value.kind) {
    case "text":
      return (
        <p className={cn(WRAP_TEXT, className)}>{value.text}</p>
      );
    case "list":
      return (
        <ul className={cn("list-disc space-y-1 pl-5", className)}>
          {value.items.map((item, i) => (
            <li key={i} className="min-w-0 break-words [overflow-wrap:anywhere]">
              <DisplayValueView value={item} />
            </li>
          ))}
        </ul>
      );
    case "fields":
      return (
        <dl className={cn("space-y-2", className)}>
          {value.fields.map((field) => (
            <div key={field.key}>
              <dt className="text-xs font-medium text-muted-foreground">
                {field.label}
              </dt>
              <dd className="mt-0.5 min-w-0">
                <DisplayValueView value={field.value} />
              </dd>
            </div>
          ))}
        </dl>
      );
  }
}

export function DecisionContent({
  decision,
  outputSchema,
}: {
  decision: TranscriptDecision;
  outputSchema: unknown;
}) {
  const { label, body } = decisionDisplay(decision.decision, outputSchema);
  return (
    <>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {decision.undecided ? (
          <>
            <Badge variant="outline">Undecided</Badge>
            {label != null ? (
              <span className="text-xs text-muted-foreground">
                reply: <span data-testid="decision-reply">{label}</span>
              </span>
            ) : null}
          </>
        ) : label != null ? (
          <Badge
            variant="agreement"
            className="max-w-full break-words text-sm"
            data-testid="decision-label"
          >
            {label}
          </Badge>
        ) : body == null ? (
          <span className="text-sm text-muted-foreground">—</span>
        ) : null}
        {decision.authority ? (
          <span className="text-xs text-muted-foreground">
            authority: {decision.authority}
          </span>
        ) : null}
        {decision.resolution ? (
          <span className="text-xs text-muted-foreground">
            resolution: {decision.resolution}
          </span>
        ) : null}
      </div>

      {decision.undecided && decision.detail ? (
        <p
          className={cn("mt-2 text-xs text-muted-foreground", WRAP_TEXT)}
          data-testid="decision-reason"
        >
          <span className="font-medium">Why undecided: </span>
          {decision.detail}
        </p>
      ) : null}

      {body ? (
        <div
          className="mt-2 rounded-md bg-background/60 p-3 text-sm"
          data-testid="decision-body"
        >
          <DisplayValueView value={body} />
        </div>
      ) : null}

      {decision.structured != null ? (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-muted-foreground">
            Structured decision
          </summary>
          <pre
            className={cn("mt-1 max-h-60 overflow-auto rounded bg-background/60 p-2", SCROLL_PRE)}
            data-testid="decision-structured"
          >
            {JSON.stringify(decision.structured, null, 2)}
          </pre>
        </details>
      ) : null}
    </>
  );
}
