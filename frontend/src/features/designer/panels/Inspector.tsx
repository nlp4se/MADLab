import { useEffect, useState } from "react";

import { DIMENSION_THEMES, type DimensionKey } from "@/taxonomy/dimensions";
import { cn } from "@/lib/utils";
import { useDesignerStore } from "../designerStore";
import { AgreementPanel } from "./AgreementPanel";
import { EdgePanel } from "./EdgePanel";
import { InteractionPanel } from "./InteractionPanel";
import { ParticipantsPanel } from "./ParticipantsPanel";

/**
 * The designer inspector (task 8.4, Req 6.3, 6.6).
 *
 * Context-sensitive: clicking a node focuses the Participants panel for that
 * participant; selecting an edge focuses the edge props. Three colour-themed
 * dimension tabs (Participants / Interaction / Agreement, Req 6.6) let the user
 * configure the config-level dimensions regardless of canvas selection.
 *
 * Selecting a node/edge auto-switches the active tab to the relevant dimension
 * so the user always knows which dimension they are editing.
 */
const TABS: DimensionKey[] = ["participants", "interaction", "agreement"];

export function Inspector() {
  const selection = useDesignerStore((s) => s.selection);
  const [activeTab, setActiveTab] = useState<DimensionKey>("participants");

  // Selecting a node/edge pulls the inspector to the relevant dimension tab.
  useEffect(() => {
    if (selection?.kind === "node") setActiveTab("participants");
    else if (selection?.kind === "edge") setActiveTab("interaction");
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
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === "participants" ? <ParticipantsTab /> : null}
        {activeTab === "interaction" ? <InteractionTab /> : null}
        {activeTab === "agreement" ? <AgreementPanel /> : null}
      </div>
    </aside>
  );
}

/** Participants tab: the selected node's panel, or a dimension-level hint. */
function ParticipantsTab() {
  const selection = useDesignerStore((s) => s.selection);
  if (selection?.kind === "node") {
    return <ParticipantsPanel nodeId={selection.id} />;
  }
  return (
    <EmptyHint text="Select a participant node on the canvas to edit its roles, persona, and base model." />
  );
}

/** Interaction tab: edge props when an edge is selected, else topology/protocol/format. */
function InteractionTab() {
  const selection = useDesignerStore((s) => s.selection);
  if (selection?.kind === "edge") {
    return <EdgePanel edgeId={selection.id} />;
  }
  return <InteractionPanel />;
}

function EmptyHint({ text }: { text: string }) {
  return <p className="text-sm text-muted-foreground">{text}</p>;
}
