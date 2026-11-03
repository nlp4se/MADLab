import { Input } from "@/components/ui/input";
import { useTaxonomy } from "@/taxonomy/TaxonomyContext";
import type {
  FormatArtifact,
  InteractionArtifact,
  TopologyPattern,
} from "../artifact";
import { useDesignerStore } from "../designerStore";
import {
  Disclosure,
  Field,
  FieldGroup,
  TaxonomyMultiSelect,
  TaxonomySelect,
} from "./fields";

/**
 * Interaction-dimension panel (Req 2.*, 7.4). Configures, all data-driven from
 * the taxonomy catalog:
 *  - topology meta: adaptability / structure / pattern
 *  - protocol: mechanism / max_rounds / ordering
 *  - format: syntax / content strategy + metadata signals / memory
 *
 * The edge set itself (E) is edited on the canvas; this panel edits the
 * surrounding topology metadata and leaves the edges untouched.
 */
export function InteractionPanel() {
  const { getSubDimension, isUnderDevelopment } = useTaxonomy();
  const artifact = useDesignerStore((s) => s.artifact);
  const updateTopologyMeta = useDesignerStore((s) => s.updateTopologyMeta);
  const updateProtocol = useDesignerStore((s) => s.updateProtocol);
  const updateFormat = useDesignerStore((s) => s.updateFormat);

  if (!artifact) return null;

  const topology = artifact.interaction.topology;
  const protocol = artifact.interaction.protocol ?? {};
  const format = artifact.interaction.format ?? {};
  const content = format.content ?? {};

  const adaptabilitySub = getSubDimension("interaction", "topology_adaptability");
  const structureSub = getSubDimension("interaction", "topology_structure");
  const patternSub = getSubDimension("interaction", "topology_pattern");
  const mechanismSub = getSubDimension("interaction", "protocol_mechanism");
  const orderingSub = getSubDimension("interaction", "protocol_ordering");
  const syntaxSub = getSubDimension("interaction", "format_syntax");
  const contentSub = getSubDimension("interaction", "format_content");
  const metadataSub = getSubDimension("interaction", "format_content_metadata");
  const memorySub = getSubDimension("interaction", "format_memory");

  const toggleMetadata = (key: string, next: boolean) => {
    const set = new Set(content.metadata_signals ?? []);
    if (next) set.add(key);
    else set.delete(key);
    updateFormat({ content: { metadata_signals: [...set] } });
  };

  return (
    <div className="space-y-6">
      {/* --- Topology --- */}
      <FieldGroup title="Topology" tone="structured">
        {adaptabilitySub ? (
          <TaxonomySelect
            sub={adaptabilitySub}
            value={topology.adaptability}
            onChange={(v) =>
              updateTopologyMeta({ adaptability: v as "static" | "dynamic" })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="topo-adapt"
          />
        ) : null}
        {structureSub ? (
          <TaxonomySelect
            sub={structureSub}
            value={topology.structure}
            onChange={(v) =>
              updateTopologyMeta({
                structure: v as InteractionArtifact["topology"]["structure"],
                // clear the pattern when leaving structured_network
                pattern:
                  v === "structured_network" ? topology.pattern ?? null : null,
              })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="topo-structure"
          />
        ) : null}
        {patternSub && topology.structure === "structured_network" ? (
          <TaxonomySelect
            sub={patternSub}
            value={topology.pattern ?? undefined}
            onChange={(v) =>
              updateTopologyMeta({ pattern: v as TopologyPattern })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="topo-pattern"
          />
        ) : null}
      </FieldGroup>

      {/* --- Protocol --- */}
      <FieldGroup title="Protocol" tone="structured">
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
      <FieldGroup title="Format" tone="structured">
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
