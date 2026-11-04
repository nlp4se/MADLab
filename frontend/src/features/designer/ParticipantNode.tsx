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
 *
 * The left handle is the INPUT (incoming messages) and the right handle is the
 * OUTPUT (outgoing messages). The "in"/"out" captions sit ABOVE each port (not
 * on the connection line) so they never overlap the edges/arrowheads.
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

/** Shared handle styling: a clear, moderate port marker. */
const HANDLE_CLASS = "!size-3 !border-2 !border-background";

/** Port caption placed above the handle so it never sits on the edge line. */
const PORT_LABEL_CLASS =
  "pointer-events-none absolute -top-5 text-[10px] font-semibold uppercase tracking-wide";

function ParticipantNodeComponent({ data, selected }: NodeProps<ParticipantNodeData>) {
  const role = primaryRole(data.roles);
  const iconUrl = roleIconUrl(role);
  const modelLabel = data.modelKey ?? "no model";

  return (
    <div
      className={cn(
        "relative min-w-[200px] rounded-lg border-2 bg-background px-3 py-3 shadow-sm transition-colors",
        selected
          ? "border-participants ring-2 ring-participants"
          : "border-participants/40",
      )}
      data-testid="participant-node"
    >
      {/* INPUT port (left): incoming messages. Caption sits above the handle. */}
      <Handle
        id="in"
        type="target"
        position={Position.Left}
        className={cn(HANDLE_CLASS, "!bg-muted-foreground")}
      />
      <span className={cn(PORT_LABEL_CLASS, "left-0 text-muted-foreground")}>
        in
      </span>

      {/* OUTPUT port (right): outgoing messages. Caption sits above the handle. */}
      <Handle
        id="out"
        type="source"
        position={Position.Right}
        className={cn(HANDLE_CLASS, "!bg-participants")}
      />
      <span className={cn(PORT_LABEL_CLASS, "right-0 text-participants")}>
        out
      </span>

      <div className="flex items-center gap-2.5">
        <span
          className="flex size-9 shrink-0 items-center justify-center rounded-md bg-participants-muted"
          aria-hidden
        >
          {iconUrl ? (
            <img src={iconUrl} alt="" className="size-5" />
          ) : (
            <PARTICIPANTS.icon className="size-5 text-participants" />
          )}
        </span>
        <div className="min-w-0">
          <p className="truncate text-[15px] font-semibold leading-tight" title={data.label}>
            {data.label}
          </p>
          <p className="truncate text-[11px] capitalize leading-tight text-muted-foreground">
            {data.roles.join(", ") || "debater"}
          </p>
        </div>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-1">
        <Badge
          variant="participants"
          className="max-w-full gap-1 py-0 text-[11px] font-normal"
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
