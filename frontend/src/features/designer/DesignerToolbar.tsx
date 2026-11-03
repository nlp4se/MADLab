import { LayoutGrid, Loader2, Plus, Save, Trash2, Workflow } from "lucide-react";

import { topologyIconUrl } from "@/assets/icons";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  APPLICABLE_TOPOLOGIES,
  type ApplicableTopology,
} from "./artifact";
import { topologyLabel } from "./topology";

/**
 * Designer canvas toolbar (Req 6.2, 6.5).
 *
 * Exposes the canvas-level actions that are not per-element drag gestures:
 * add a participant, apply a topology template (chain/ring/star/.../fully
 * connected), auto-layout, delete the current selection, and save the artifact
 * (PUT /api/configs/{id}). The Save button reflects the store's `dirty` flag and
 * the mutation's pending state.
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
}: DesignerToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b bg-background/80 px-3 py-2 backdrop-blur">
      <Button size="sm" variant="outline" onClick={onAddNode}>
        <Plus className="size-4" aria-hidden />
        Add participant
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger>
          <Button size="sm" variant="outline" aria-label="Apply topology template">
            <Workflow className="size-4" aria-hidden />
            Topology
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          {APPLICABLE_TOPOLOGIES.map((topology) => {
            const iconUrl = topologyIconUrl(topology);
            return (
              <DropdownMenuItem
                key={topology}
                onClick={() => onApplyTopology(topology)}
              >
                {iconUrl ? (
                  <img src={iconUrl} alt="" className="size-4" aria-hidden />
                ) : (
                  <Workflow className="size-4" aria-hidden />
                )}
                {topologyLabel(topology)}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>

      <Button size="sm" variant="outline" onClick={onAutoLayout}>
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
        {dirty ? (
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
