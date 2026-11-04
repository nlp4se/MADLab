import { MessagesSquare, Network, Workflow } from "lucide-react";

import { Input } from "@/components/ui/input";
import { useTaxonomy } from "@/taxonomy/TaxonomyContext";
import type { FormatArtifact } from "../artifact";
import { useDesignerStore } from "../designerStore";
import { topologyLabel } from "../topology";
import {
  Disclosure,
  Field,
  FieldGroup,
  TaxonomyMultiSelect,
  TaxonomySelect,
} from "./fields";

/**
 * Interaction-dimension panel (Req 2.*, 7.4).
 *
 * The TOPOLOGY (structure/pattern and the edge set E) is designed on the canvas
 * and via the toolbar's topology templates — NOT here. Editing the structure in
 * a form while the graph is drawn on the canvas was misleading, so this panel no
 * longer offers topology-structure selects; it shows a read-only summary of the
 * current topology (a reminder that it is canvas-driven) and configures the
 * remaining Interaction concerns:
 *  - protocol: mechanism / max_rounds / ordering
 *  - format: syntax / content strategy + metadata signals / memory
 */
export function InteractionPanel() {
  const { getSubDimension, getValue, isUnderDevelopment } = useTaxonomy();
  const artifact = useDesignerStore((s) => s.artifact);
  const updateProtocol = useDesignerStore((s) => s.updateProtocol);
  const updateFormat = useDesignerStore((s) => s.updateFormat);

  if (!artifact) return null;

  const topology = artifact.interaction.topology;
  const protocol = artifact.interaction.protocol ?? {};
  const format = artifact.interaction.format ?? {};
  const content = format.content ?? {};

  const mechanismSub = getSubDimension("interaction", "protocol_mechanism");
  const orderingSub = getSubDimension("interaction", "protocol_ordering");
  const syntaxSub = getSubDimension("interaction", "format_syntax");
  const contentSub = getSubDimension("interaction", "format_content");
  const metadataSub = getSubDimension("interaction", "format_content_metadata");
  const memorySub = getSubDimension("interaction", "format_memory");

  const structureLabel =
    getValue("interaction", "topology_structure", topology.structure ?? "")
      ?.label ??
    topologyLabel(
      (topology.structure ?? "fully_connected") as never,
    );
  const patternLabel = topology.pattern
    ? getValue("interaction", "topology_pattern", topology.pattern)?.label ??
      topologyLabel(topology.pattern as never)
    : null;
  const edgeCount = topology.edges.length;

  const toggleMetadata = (key: string, next: boolean) => {
    const set = new Set(content.metadata_signals ?? []);
    if (next) set.add(key);
    else set.delete(key);
    updateFormat({ content: { metadata_signals: [...set] } });
  };

  return (
    <div className="space-y-6">
      {/* --- Topology (read-only summary; edited on the canvas/toolbar) --- */}
      <FieldGroup title="Topology" tone="structured" icon={Network}>
        <div className="rounded-md border bg-muted/40 p-3 text-sm">
          <p className="flex items-center gap-1.5 font-medium">
            <Workflow className="size-4 text-interaction" aria-hidden />
            {structureLabel}
            {patternLabel ? (
              <span className="text-muted-foreground">· {patternLabel}</span>
            ) : null}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {edgeCount} {edgeCount === 1 ? "edge" : "edges"}. The topology is
            designed on the canvas — use the <strong>Topology</strong> button in
            the toolbar to apply a template, or draw edges between nodes.
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            <strong>Edges set visibility, not turn order.</strong> An arrow
            A&nbsp;→&nbsp;B means B can read A''s messages on its turn; a node
            with several outgoing arrows is simply read by several others.
            <em>When</em> each agent speaks is decided by the{" "}
            <strong>Protocol</strong> below (its mechanism and ordering), not by
            the arrows.
          </p>
        </div>
      </FieldGroup>

      {/* --- Protocol --- */}
      <FieldGroup title="Protocol" tone="structured" icon={Workflow}>
        {mechanismSub ? (
          <TaxonomySelect
            sub={mechanismSub}
            value={protocol.mechanism}
            onChange={(v) =>
              updateProtocol({
                mechanism: v as "sequential" | "simultaneous" | "hybrid",
              })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="proto-mechanism"
          />
        ) : null}
        <Field
          label="Max rounds"
          description="The iteration cap for the debate."
          htmlFor="proto-max-rounds"
        >
          <Input
            id="proto-max-rounds"
            type="number"
            min={1}
            value={protocol.max_rounds ?? 1}
            onChange={(e) =>
              updateProtocol({
                max_rounds: Math.max(1, Number(e.target.value) || 1),
              })
            }
          />
        </Field>
        {orderingSub ? (
          <TaxonomySelect
            sub={orderingSub}
            value={protocol.ordering}
            onChange={(v) =>
              updateProtocol({
                ordering: v as "fixed" | "randomized" | "coordinator",
              })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="proto-ordering"
          />
        ) : null}
      </FieldGroup>

      {/* --- Format --- */}
      <FieldGroup title="Format" tone="structured" icon={MessagesSquare}>
        {syntaxSub ? (
          <TaxonomySelect
            sub={syntaxSub}
            value={format.syntax}
            onChange={(v) =>
              updateFormat({ syntax: v as FormatArtifact["syntax"] })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="fmt-syntax"
          />
        ) : null}
        {contentSub ? (
          <TaxonomySelect
            sub={contentSub}
            value={content.strategy}
            onChange={(v) =>
              updateFormat({
                content: { strategy: v as "verbatim" | "summarized" | "other" },
              })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="fmt-content"
          />
        ) : null}
        <Disclosure summary="Advanced format options">
          {metadataSub ? (
            <TaxonomyMultiSelect
              sub={metadataSub}
              selected={content.metadata_signals ?? []}
              onToggle={toggleMetadata}
              isUnderDevelopment={isUnderDevelopment}
            />
          ) : null}
          {memorySub ? (
            <TaxonomySelect
              sub={memorySub}
              value={format.memory}
              onChange={(v) =>
                updateFormat({ memory: v as FormatArtifact["memory"] })
              }
              isUnderDevelopment={isUnderDevelopment}
              id="fmt-memory"
            />
          ) : null}
        </Disclosure>
      </FieldGroup>
    </div>
  );
}
