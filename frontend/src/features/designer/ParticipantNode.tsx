import { memo } from "react";
import { Handle, Position, type NodeProps } from "reactflow";

import { roleIconUrl } from "@/assets/icons";
import { Badge } from "@/components/ui/badge";
import { DIMENSION_THEMES } from "@/taxonomy/dimensions";
import { cn } from "@/lib/utils";

/**
 * Data carried by a participant node on the canvas (Req 6.1, 6.7).
 *
 * A participant renders with a role icon (from the shared `role/*` SVGs) and a
 * base-model badge (provider + model_key). Colouring uses the Participants
 * dimension theme so the three dimensions stay visually distinct (Req 6.6).
 */
export interface ParticipantNodeData {
  label: string;
  roles: string[];
  modelKey: string | null;
  providerId: string | null;
  selected?: boolean;
}

const PARTICIPANTS = DIMENSION_THEMES.participants;

/**
 * Pick the primary role for the icon: prefer a known shared-icon role, else the
 * first role, else "debater".
 */
function primaryRole(roles: string[]): string {
  const known = roles.find((r) => roleIconUrl(r) !== undefined);
  return known ?? roles[0] ?? "debater";
}

function ParticipantNodeComponent({ data, selected }: NodeProps<ParticipantNodeData>) {
  const role = primaryRole(data.roles);
  const iconUrl = roleIconUrl(role);
  const modelLabel = data.modelKey ?? "no model";

  return (
    <div
      className={cn(
        "min-w-[180px] rounded-lg border-2 bg-background p-3 shadow-sm transition-colors",
        selected
          ? "border-participants ring-2 ring-participants"
          : "border-participants/40",
      )}
      data-testid="participant-node"
    >
      {/* Target handle (incoming edges) on the left, source (outgoing) on right. */}
      <Handle type="target" position={Position.Left} className="!bg-participants" />
      <Handle type="source" position={Position.Right} className="!bg-participants" />

      <div className="flex items-center gap-2">
        <span
          className="flex size-9 shrink-0 items-center justify-center rounded-md bg-participants-muted"
          aria-hidden
        >
          {iconUrl ? (
            <img src={iconUrl} alt="" className="size-6" />
          ) : (
            <PARTICIPANTS.icon className="size-5 text-participants" />
          )}
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium" title={data.label}>
            {data.label}
          </p>
          <p className="truncate text-xs capitalize text-muted-foreground">
            {data.roles.join(", ") || "debater"}
          </p>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1">
        <Badge
          variant="participants"
          className="max-w-full gap-1 font-normal"
          title={
            data.providerId
              ? `${data.providerId} · ${modelLabel}`
              : modelLabel
          }
        >
          <span className="truncate">
            {data.providerId ? `${data.providerId} · ` : ""}
            {modelLabel}
          </span>
        </Badge>
      </div>
    </div>
  );
}

export const ParticipantNode = memo(ParticipantNodeComponent);
