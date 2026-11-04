import { useEffect, useState } from "react";
import { AlertTriangle, LogIn } from "lucide-react";

import { DIMENSION_THEMES, type DimensionKey } from "@/taxonomy/dimensions";
import { cn } from "@/lib/utils";
import { useDesignerStore } from "../designerStore";
import { isInputTemplateEmpty } from "../inputEditor";
import { AgreementPanel } from "./AgreementPanel";
import { EdgePanel } from "./EdgePanel";
import { InputPanel } from "./InputPanel";
import { InteractionPanel } from "./InteractionPanel";
import { ParticipantsPanel } from "./ParticipantsPanel";
import { ParticipantsDimensionPanel } from "./ParticipantsDimensionPanel";

/**
 * The designer inspector (Req 6.3, 6.6).
 *
 * Context-sensitive: clicking a node focuses the Participants panel for that
 * participant; selecting an edge focuses the edge props. Three colour-themed
 * dimension tabs (Participants / Interaction / Agreement, Req 6.6) let the user
 * configure the config-level dimensions regardless of canvas selection.
 *
 * With NO node selected the Participants tab shows the *dimension-level*
 * participant settings (persona/base-model heterogeneity and assignment) — these
 * are config-wide, not per-node, so editing them must not require selecting a
 * participant.
 *
 * A fourth Input tab (task 11.10) edits the instance input (`input_spec`); it
 * opens when the Start node is selected and is flagged when the template is
 * empty.
 */
const TABS: DimensionKey[] = ["participants", "interaction", "agreement"];

/** The inspector tabs: the three dimensions plus the Input tab (task 11.10). */
type InspectorTab = DimensionKey | "input";

export function Inspector() {
  const selection = useDesignerStore((s) => s.selection);
  const inputMissing = useDesignerStore((s) => isInputTemplateEmpty(s.artifact));
  const [activeTab, setActiveTab] = useState<InspectorTab>("participants");

  useEffect(() => {
    if (selection?.kind === "node") setActiveTab("participants");
    else if (selection?.kind === "edge") setActiveTab("interaction");
    else if (selection?.kind === "input") setActiveTab("input");
  }, [selection]);

  return (
    <aside
      className="flex h-full w-[360px] shrink-0 flex-col border-l bg-background"
      data-testid="designer-inspector"
      aria-label="Designer inspector"
    >
      <div className="flex border-b" role="tablist">
        {TABS.map((key) => {
          const theme = DIMENSION_THEMES[key];
          const active = activeTab === key;
          const Icon = theme.icon;
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setActiveTab(key)}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 border-b-2 px-2 py-2.5 text-xs font-medium transition-colors",
                active
                  ? cn(theme.classes.border, theme.classes.text)
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden />
              {theme.label}
            </button>
          );
        })}
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "input"}
          onClick={() => setActiveTab("input")}
          className={cn(
            "relative flex flex-1 items-center justify-center gap-1.5 border-b-2 px-2 py-2.5 text-xs font-medium transition-colors",
            activeTab === "input"
              ? "border-emerald-500 text-emerald-700 dark:text-emerald-400"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          <LogIn className="size-4" aria-hidden />
          Input
          {inputMissing ? (
            <AlertTriangle
              className="size-3 text-amber-500"
              aria-label="No input template"
              data-testid="input-tab-warning"
            />
          ) : null}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === "participants" ? <ParticipantsTab /> : null}
        {activeTab === "interaction" ? <InteractionTab /> : null}
        {activeTab === "agreement" ? <AgreementPanel /> : null}
        {activeTab === "input" ? <InputPanel /> : null}
      </div>
    </aside>
  );
}

/**
 * Participants tab: the selected node's per-node panel, or — when nothing is
 * selected — the config-level participant-dimension settings (so those are
 * editable without picking a participant).
 */
function ParticipantsTab() {
  const selection = useDesignerStore((s) => s.selection);
  if (selection?.kind === "node") {
    return <ParticipantsPanel nodeId={selection.id} />;
  }
  return <ParticipantsDimensionPanel />;
}

/** Interaction tab: edge props when an edge is selected, else topology/protocol/format. */
function InteractionTab() {
  const selection = useDesignerStore((s) => s.selection);
  if (selection?.kind === "edge") {
    return <EdgePanel edgeId={selection.id} />;
  }
  return <InteractionPanel />;
}
