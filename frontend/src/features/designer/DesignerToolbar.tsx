import { LayoutGrid, Loader2, Plus, RotateCcw, Save, Trash2, Workflow } from "lucide-react";

import { topologyIconUrl } from "@/assets/icons";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { type ApplicableTopology } from "./artifact";
import { TOPOLOGY_PATTERNS } from "./artifact";
import type { TopologyStatus } from "./interactionScope";
import { topologyLabel } from "./topology";

/**
 * Designer canvas toolbar (Req 6.2, 6.5).
 *
 * Exposes the canvas-level actions that are not per-element drag gestures:
 * add a participant, apply a topology template, auto-layout, delete the current
 * selection, and save the artifact (PUT /api/configs/{id}).
 *
 * The topology menu offers Fully connected and the Structured-network patterns,
 * so choosing one (re)initializes the graph for that structure. Grouped is not
 * offered (no group-assignment UI). The page confirms before overwriting an
 * existing graph. The button shows the current template, or "Custom (edited
 * from <template>)" with a Re-apply item once the edges drifted (task 11.7).
 */
export interface DesignerToolbarProps {
  onAddNode: () => void;
  onApplyTopology: (topology: ApplicableTopology) => void;
  onAutoLayout: () => void;
  onDeleteSelection: () => void;
  onSave: () => void;
  canDeleteSelection: boolean;
  dirty: boolean;
  saving: boolean;
  /** A new, never-saved configuration (task 11.15): Save creates it. */
  isNew?: boolean;
  /**
   * The applied template vs the drawn edges (task 11.7): the Topology button
   * shows its label ("Chain" / "Custom (edited from Chain)") and, when the
   * edges drifted, the menu offers "Re-apply <template>".
   */
  topologyStatus?: TopologyStatus;
}

function TopologyItem({
  topology,
  onApply,
}: {
  topology: ApplicableTopology;
  onApply: (t: ApplicableTopology) => void;
}) {
  const iconUrl = topologyIconUrl(topology);
  return (
    <DropdownMenuItem onClick={() => onApply(topology)}>
      {iconUrl ? (
        <img src={iconUrl} alt="" className="size-4" aria-hidden />
      ) : (
        <Workflow className="size-4" aria-hidden />
      )}
      {topologyLabel(topology)}
    </DropdownMenuItem>
  );
}

export function DesignerToolbar({
  onAddNode,
  onApplyTopology,
  onAutoLayout,
  onDeleteSelection,
  onSave,
  canDeleteSelection,
  dirty,
  saving,
  isNew = false,
  topologyStatus,
}: DesignerToolbarProps) {
  const reapply =
    topologyStatus?.reappliable && topologyStatus.template ? topologyStatus.template : null;
  return (
    <div className="flex flex-wrap items-center gap-2 border-b bg-background/80 px-3 py-2 backdrop-blur">
      <Button size="sm" variant="outline" onClick={onAddNode}>
        <Plus className="size-4" aria-hidden />
        Add participant
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger>
          <Button
            size="sm"
            variant="outline"
            aria-label={
              topologyStatus
                ? `Apply topology template (current: ${topologyStatus.label})`
                : "Apply topology template"
            }
          >
            <Workflow className="size-4" aria-hidden />
            Topology
            {topologyStatus ? (
              <span
                className="max-w-[16rem] truncate font-normal text-muted-foreground"
                data-testid="toolbar-topology-status"
              >
                : {topologyStatus.label}
              </span>
            ) : null}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          {reapply ? (
            <>
              <DropdownMenuItem onClick={() => onApplyTopology(reapply)}>
                <RotateCcw className="size-4" aria-hidden />
                Re-apply {topologyStatus?.templateLabel}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
            </>
          ) : null}
          <DropdownMenuLabel>Structure</DropdownMenuLabel>
          <TopologyItem topology="fully_connected" onApply={onApplyTopology} />
          {/* "Grouped" is not offered: the designer has no group-assignment UI
              (see OFFERED_TOPOLOGIES in interactionScope.ts). */}
          <DropdownMenuSeparator />
          <DropdownMenuLabel>Structured network</DropdownMenuLabel>
          {TOPOLOGY_PATTERNS.map((pattern) => (
            <TopologyItem
              key={pattern}
              topology={pattern}
              onApply={onApplyTopology}
            />
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      <Button size="sm" variant="outline" onClick={() => onAutoLayout()}>
        <LayoutGrid className="size-4" aria-hidden />
        Auto-layout
      </Button>

      <Button
        size="sm"
        variant="outline"
        onClick={onDeleteSelection}
        disabled={!canDeleteSelection}
      >
        <Trash2 className="size-4" aria-hidden />
        Delete
      </Button>

      <div className="ml-auto flex items-center gap-2">
        {isNew ? (
          <span className="text-xs text-muted-foreground" data-testid="designer-not-saved">
            New configuration · not saved yet
          </span>
        ) : dirty ? (
          <span className="text-xs text-muted-foreground">Unsaved changes</span>
        ) : null}
        <Button size="sm" onClick={onSave} disabled={!dirty || saving}>
          {saving ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <Save className="size-4" aria-hidden />
          )}
          Save
        </Button>
      </div>
    </div>
  );
}
