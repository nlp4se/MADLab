import { AlertTriangle, Gavel, Users, Workflow } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ConfigSummaryAttributes } from "@/api";

/**
 * Summary chips derived from `ConfigSummaryAttributes` (Req 5.1), colour-coded
 * by the taxonomy dimension each attribute belongs to:
 *
 *  - Participants (indigo): participant count
 *  - Interaction (teal): topology (structure / pattern), protocol mechanism
 *  - Agreement (amber): authority, resolution
 *
 * Plus an "under development" warning badge when the config selects any
 * non-executable value (Req 7.5 context), so the list signals it before a run
 * is ever attempted.
 */

/** Humanize a snake_case taxonomy key into a readable label. */
function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  return value
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function topologyLabel(attrs: ConfigSummaryAttributes): string {
  const structure = humanize(attrs.topology_structure);
  if (attrs.topology_pattern) {
    return `${structure} · ${humanize(attrs.topology_pattern)}`;
  }
  return structure;
}

export function ConfigSummaryChips({
  attributes,
  className,
}: {
  attributes: ConfigSummaryAttributes;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      <Badge variant="participants" className="gap-1">
        <Users className="size-3" aria-hidden />
        {attributes.participant_count}{" "}
        {attributes.participant_count === 1 ? "agent" : "agents"}
      </Badge>

      <Badge variant="interaction" className="gap-1">
        <Workflow className="size-3" aria-hidden />
        {topologyLabel(attributes)}
      </Badge>

      <Badge variant="interaction" className="gap-1">
        <Workflow className="size-3" aria-hidden />
        {humanize(attributes.protocol_mechanism)}
      </Badge>

      <Badge variant="agreement" className="gap-1">
        <Gavel className="size-3" aria-hidden />
        {humanize(attributes.authority)}
      </Badge>

      <Badge variant="agreement" className="gap-1">
        <Gavel className="size-3" aria-hidden />
        {humanize(attributes.resolution)}
      </Badge>

      {attributes.under_development ? (
        <Badge
          variant="outline"
          className="gap-1 border-amber-500 text-amber-600 dark:text-amber-400"
          title="This configuration selects a value that is not yet executable."
        >
          <AlertTriangle className="size-3" aria-hidden />
          Under development
        </Badge>
      ) : null}
    </div>
  );
}
