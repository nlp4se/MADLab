import { memo } from "react";
import { Handle, Position, type NodeProps } from "reactflow";

import { roleIconUrl } from "@/assets/icons";
import { DIMENSION_THEMES } from "@/taxonomy/dimensions";
import { cn } from "@/lib/utils";
import { useProvidersQuery } from "./useProviders";
import { providerColor, roleColor } from "./nodeStyle";

/**
 * Data carried by a participant node on the canvas (Req 6.1, 6.7).
 *
 * A participant renders with a role icon (from the shared `role/*` SVGs) and a
 * base-model badge. The node BODY is tinted by the participant's primary ROLE
 * and the model badge by its PROVIDER, so roles and providers are each visually
 * distinct across the graph. The provider is shown by NAME (resolved from the
 * configured providers) rather than its opaque database id.
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
 * Pick the primary role for the icon/colour: prefer a known shared-icon role,
 * else the first role, else "debater".
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

  // Resolve the provider id -> name + kind from the configured providers so the
  // badge shows a human name (not the opaque DB id) and a provider-specific
  // colour. Falls back to the id when the provider can't be resolved.
  const providers = useProvidersQuery().data ?? [];
  const provider = providers.find(
    (p) => String(p.id) === String(data.providerId),
  );
  const providerName = provider?.name ?? (data.providerId ? `#${data.providerId}` : null);

  const role_c = roleColor(role);
  const prov_c = provider
    ? providerColor(provider.kind || provider.name)
    : data.providerId
      ? providerColor(String(data.providerId))
      : null;

  return (
    <div
      className="relative min-w-[200px] rounded-lg border-2 bg-background px-3 py-3 shadow-sm transition-shadow"
      style={{
        borderColor: role_c.solid,
        boxShadow: selected ? `0 0 0 3px ${role_c.soft}` : undefined,
      }}
      data-testid="participant-node"
      data-role={role}
    >
      {/* INPUT port (left): incoming messages. Caption sits above the handle. */}
      <Handle
        id="in"
        type="target"
        position={Position.Left}
        className={cn(HANDLE_CLASS)}
        style={{ background: "hsl(var(--muted-foreground))" }}
      />
      <span className={cn(PORT_LABEL_CLASS, "left-0 text-muted-foreground")}>
        in
      </span>

      {/* OUTPUT port (right): outgoing messages. Caption sits above the handle. */}
      <Handle
        id="out"
        type="source"
        position={Position.Right}
        className={cn(HANDLE_CLASS)}
        style={{ background: role_c.solid }}
      />
      <span
        className={cn(PORT_LABEL_CLASS, "right-0")}
        style={{ color: role_c.solid }}
      >
        out
      </span>

      <div className="flex items-center gap-2.5">
        <span
          className="flex size-9 shrink-0 items-center justify-center rounded-md"
          style={{ background: role_c.soft, color: role_c.solid }}
          aria-hidden
        >
          {iconUrl ? (
            <img src={iconUrl} alt="" className="size-5" />
          ) : (
            <PARTICIPANTS.icon className="size-5" />
          )}
        </span>
        <div className="min-w-0">
          <p className="truncate text-[15px] font-semibold leading-tight" title={data.label}>
            {data.label}
          </p>
          <p
            className="truncate text-[11px] font-medium capitalize leading-tight"
            style={{ color: role_c.solid }}
          >
            {data.roles.join(", ") || "debater"}
          </p>
        </div>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-1">
        <span
          className="inline-flex max-w-full items-center gap-1 truncate rounded-full border px-2 py-0.5 text-[11px] font-medium"
          style={
            prov_c
              ? {
                  borderColor: prov_c.solid,
                  background: prov_c.soft,
                  color: prov_c.solid,
                }
              : undefined
          }
          title={
            providerName
              ? `${providerName} · ${modelLabel}`
              : modelLabel
          }
        >
          <span className="truncate">
            {providerName ? `${providerName} · ` : ""}
            {modelLabel}
          </span>
        </span>
      </div>
    </div>
  );
}

export const ParticipantNode = memo(ParticipantNodeComponent);
