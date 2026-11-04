import {
  ArrowDown,
  ArrowUp,
  ListOrdered,
  MessagesSquare,
  Network,
  Plus,
  RotateCcw,
  Trash2,
  Workflow,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useTaxonomy } from "@/taxonomy/TaxonomyContext";
import type { FormatArtifact, MADArtifact, PhaseArtifact } from "../artifact";
import { useDesignerStore } from "../designerStore";
import {
  addToTurnOrder,
  catalogTopologyLabel,
  confirmApplyTopology,
  effectiveTurnOrder,
  hybridPhasesError,
  missingFromTurnOrder,
  moveInTurnOrder,
  moveItem,
  phasesOf,
  protocolVisibility,
  speakingNodes,
  summarizerNode,
  togglePhaseParticipant,
  topologyStatus,
  usesDeclarationOrder,
} from "../interactionScope";
import { isJudgeOnly } from "../ioNodes";
import {
  Disclosure,
  Field,
  FieldGroup,
  Notice,
  TaxonomyMultiSelect,
  TaxonomySelect,
} from "./fields";

/**
 * Debate-level Interaction settings (Req 2.*, 7.4; scope rule of task 11.7).
 *
 * Every Interaction setting is edited here, with no canvas selection; the edge
 * inspector only edits an edge's label / colour / direction. Dependent fields
 * appear only when they have an effect (mirroring the engine, see
 * `interactionScope.ts`):
 *  - Topology: adaptability + a summary of the applied template. The edges are
 *    drawn on the canvas / applied from the toolbar; when they no longer match
 *    the template the summary says "Custom (edited from <template>)" and offers Re-apply.
 *  - Protocol, mechanism first. Sequential: ordering (fixed -> Turn order list;
 *    randomized -> note). Simultaneous: note. Hybrid: phases editor.
 *  - Format: syntax / content (summarized needs a summarizer) / memory.
 */
export function InteractionPanel() {
  const artifact = useDesignerStore((s) => s.artifact);
  if (!artifact) return null;
  return (
    <div className="space-y-6">
      <TopologySection artifact={artifact} />
      <ProtocolSection artifact={artifact} />
      <FormatSection artifact={artifact} />
    </div>
  );
}

/* -------------------------------- topology -------------------------------- */

function TopologySection({ artifact }: { artifact: MADArtifact }) {
  const { getSubDimension, getValue, isUnderDevelopment } = useTaxonomy();
  const updateTopologyMeta = useDesignerStore((s) => s.updateTopologyMeta);
  const applyTopology = useDesignerStore((s) => s.applyTopology);

  const topology = artifact.interaction.topology;
  const adaptabilitySub = getSubDimension("interaction", "topology_adaptability");
  const status = topologyStatus(artifact, catalogTopologyLabel(getValue));
  const edgeCount = topology.edges.length;

  const reapply = () => {
    if (!status.template) return;
    if (!confirmApplyTopology(artifact, status.templateLabel)) return;
    applyTopology(status.template);
  };

  return (
    <FieldGroup title="Topology" tone="structured" icon={Network}>
      {adaptabilitySub ? (
        <TaxonomySelect
          sub={adaptabilitySub}
          value={topology.adaptability}
          onChange={(v) => updateTopologyMeta({ adaptability: v as "static" | "dynamic" })}
          isUnderDevelopment={isUnderDevelopment}
          id="topo-adaptability"
        />
      ) : null}
      <div className="rounded-md border bg-muted/40 p-3 text-sm" data-testid="topology-summary">
        <p className="flex items-center gap-1.5 font-medium">
          <Workflow className="size-4 text-interaction" aria-hidden />
          <span data-testid="topology-status">{status.label}</span>
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {edgeCount} {edgeCount === 1 ? "edge" : "edges"}. Edges are drawn on the
          canvas; use the <strong>Topology</strong> button in the toolbar to apply a
          template.
        </p>
        {status.drifted ? (
          <div className="mt-2 space-y-1.5">
            <p className="text-xs text-muted-foreground">
              The edges no longer match the {status.templateLabel} template over the
              current participants.
            </p>
            {status.reappliable ? (
              <Button type="button" size="sm" variant="outline" onClick={reapply}>
                <RotateCcw className="size-3.5" aria-hidden />
                Re-apply {status.templateLabel}
              </Button>
            ) : null}
          </div>
        ) : null}
        {status.derivedAtRunTime ? (
          <p className="mt-2 text-xs text-muted-foreground" data-testid="topology-derived">
            No edges are drawn: at run time the engine builds the{" "}
            {status.templateLabel} edges over the participants.
          </p>
        ) : null}
        {status.template === "grouped" ? (
          <p className="mt-2 text-xs text-muted-foreground" data-testid="topology-grouped-note">
            {status.templateLabel} is not offered as a template: the designer
            cannot assign participants to groups yet. The drawn edges are what
            runs.
          </p>
        ) : null}
        <p className="mt-2 text-xs text-muted-foreground">
          <strong>Edges set visibility, not turn order.</strong> An arrow
          A&nbsp;→&nbsp;B means B can read A&apos;s messages on its turn.{" "}
          <em>When</em> each agent speaks is decided by the{" "}
          <strong>Protocol</strong> below.
        </p>
      </div>
    </FieldGroup>
  );
}

/* -------------------------------- protocol -------------------------------- */

function ProtocolSection({ artifact }: { artifact: MADArtifact }) {
  const { getSubDimension, isUnderDevelopment } = useTaxonomy();
  const updateProtocol = useDesignerStore((s) => s.updateProtocol);

  const protocol = artifact.interaction.protocol ?? {};
  const mechanismSub = getSubDimension("interaction", "protocol_mechanism");
  const orderingSub = getSubDimension("interaction", "protocol_ordering");
  const visible = protocolVisibility(protocol);

  return (
    <FieldGroup title="Protocol" tone="structured" icon={Workflow}>
      {mechanismSub ? (
        <TaxonomySelect
          sub={mechanismSub}
          value={protocol.mechanism}
          onChange={(v) =>
            updateProtocol({ mechanism: v as "sequential" | "simultaneous" | "hybrid" })
          }
          isUnderDevelopment={isUnderDevelopment}
          id="proto-mechanism"
          note={
            visible.simultaneousNote ? (
              <span data-testid="proto-simultaneous-note">
                Every participant acts at once in each round; no one sees the others&apos;
                messages from the same round.
              </span>
            ) : null
          }
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
            updateProtocol({ max_rounds: Math.max(1, Number(e.target.value) || 1) })
          }
        />
      </Field>
      {visible.ordering && orderingSub ? (
        <TaxonomySelect
          sub={orderingSub}
          value={protocol.ordering}
          onChange={(v) =>
            updateProtocol({ ordering: v as "fixed" | "randomized" | "coordinator" })
          }
          isUnderDevelopment={isUnderDevelopment}
          id="proto-ordering"
          note={
            visible.randomizedNote ? (
              <span data-testid="proto-randomized-note">
                The order is shuffled in every round (reproducible per run), so
                there is no turn list to set.
              </span>
            ) : null
          }
        />
      ) : null}
      {visible.turnOrder ? <TurnOrderList artifact={artifact} /> : null}
      {visible.phases ? <PhasesEditor artifact={artifact} /> : null}
    </FieldGroup>
  );
}

function TurnOrderList({ artifact }: { artifact: MADArtifact }) {
  const updateProtocol = useDesignerStore((s) => s.updateProtocol);
  const nodes = artifact.participants.nodes;
  const labelOf = (id: string) => nodes.find((n) => n.id === id)?.label ?? id;
  const order = effectiveTurnOrder(artifact);
  const declaration = usesDeclarationOrder(artifact);
  const missing = missingFromTurnOrder(artifact);
  const judgeOnly = nodes.filter(isJudgeOnly);

  return (
    <Field
      label="Turn order"
      icon={ListOrdered}
      description="Who speaks when, repeated in every round. The canvas shows each participant's turn number."
    >
      {declaration ? (
        <p className="text-xs text-muted-foreground" data-testid="turn-order-declaration">
          Declaration order (the order participants were added).
        </p>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => updateProtocol({ order: [] })}
        >
          <RotateCcw className="size-3.5" aria-hidden />
          Reset to declaration order
        </Button>
      )}
      {order.length === 0 ? (
        <p className="text-xs text-muted-foreground">No participant takes a turn yet.</p>
      ) : (
        <ol className="space-y-1" aria-label="Turn order" data-testid="turn-order">
          {order.map((id, i) => {
            const label = labelOf(id);
            return (
              <li
                key={id}
                className="flex items-center gap-2 rounded-md border px-2 py-1 text-sm"
                data-testid="turn-order-item"
              >
                <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-interaction text-[10px] font-bold text-white">
                  {i + 1}
                </span>
                <span className="min-w-0 flex-1 truncate">{label}</span>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  aria-label={`Move ${label} up`}
                  disabled={i === 0}
                  onClick={() => updateProtocol({ order: moveInTurnOrder(artifact, id, -1) })}
                >
                  <ArrowUp className="size-3.5" aria-hidden />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  aria-label={`Move ${label} down`}
                  disabled={i === order.length - 1}
                  onClick={() => updateProtocol({ order: moveInTurnOrder(artifact, id, 1) })}
                >
                  <ArrowDown className="size-3.5" aria-hidden />
                </Button>
              </li>
            );
          })}
        </ol>
      )}
      {missing.length > 0 ? (
        <Notice
          testId="turn-order-missing"
          actions={missing.map((id) => ({
            label: `Add ${labelOf(id)}`,
            onClick: () => updateProtocol({ order: addToTurnOrder(artifact, id) }),
          }))}
        >
          Not in the turn order, so they never speak:{" "}
          {missing.map(labelOf).join(", ")}.
        </Notice>
      ) : null}
      {judgeOnly.length > 0 ? (
        <p className="text-xs text-muted-foreground">
          Judges ({judgeOnly.map((n) => n.label).join(", ")}) take no turn: they
          decide after the rounds.
        </p>
      ) : null}
    </Field>
  );
}

function PhasesEditor({ artifact }: { artifact: MADArtifact }) {
  const { getValue } = useTaxonomy();
  const updateProtocol = useDesignerStore((s) => s.updateProtocol);
  const protocol = artifact.interaction.protocol ?? {};
  const phases = phasesOf(protocol);
  const error = hybridPhasesError(protocol);
  const nodes = artifact.participants.nodes;
  const speaking = speakingNodes(nodes);
  const declaration = nodes.map((n) => n.id);
  const mechLabel = (key: string) =>
    getValue("interaction", "protocol_mechanism", key)?.label ?? key;

  const write = (next: PhaseArtifact[]) => updateProtocol({ phases: next });
  const patch = (i: number, phase: PhaseArtifact) =>
    write(phases.map((p, j) => (j === i ? phase : p)));

  return (
    <Field
      label="Phases"
      icon={ListOrdered}
      description="Each round runs these phases in order. Each phase is sequential (one at a time) or simultaneous (all at once)."
    >
      {error ? (
        <p role="alert" className="text-xs text-destructive" data-testid="hybrid-phases-error">
          {error}
        </p>
      ) : null}
      <ol className="space-y-2" aria-label="Phases" data-testid="phases">
        {phases.map((phase, i) => {
          const n = i + 1;
          return (
            <li key={i} className="space-y-2 rounded-md border p-2" data-testid="phase">
              <div className="flex items-center gap-1">
                <span className="flex-1 text-sm font-medium">Phase {n}</span>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  aria-label={`Move phase ${n} up`}
                  disabled={i === 0}
                  onClick={() => write(moveItem(phases, i, -1))}
                >
                  <ArrowUp className="size-3.5" aria-hidden />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  aria-label={`Move phase ${n} down`}
                  disabled={i === phases.length - 1}
                  onClick={() => write(moveItem(phases, i, 1))}
                >
                  <ArrowDown className="size-3.5" aria-hidden />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7 text-muted-foreground hover:text-destructive"
                  aria-label={`Remove phase ${n}`}
                  onClick={() => write(phases.filter((_, j) => j !== i))}
                >
                  <Trash2 className="size-3.5" aria-hidden />
                </Button>
              </div>
              <Select
                aria-label={`Phase ${n} mechanism`}
                value={phase.mechanism}
                onChange={(e) =>
                  patch(i, {
                    ...phase,
                    mechanism: e.target.value as PhaseArtifact["mechanism"],
                  })
                }
              >
                <option value="sequential">{mechLabel("sequential")}</option>
                <option value="simultaneous">{mechLabel("simultaneous")}</option>
              </Select>
              <fieldset className="space-y-1">
                <legend className="text-xs text-muted-foreground">
                  Participants (none checked = every participant)
                </legend>
                {speaking.map((node) => (
                  <label key={node.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="size-4 rounded border-input"
                      aria-label={`Phase ${n}: ${node.label}`}
                      checked={phase.participants.includes(node.id)}
                      onChange={(e) =>
                        patch(
                          i,
                          togglePhaseParticipant(phase, node.id, e.target.checked, declaration),
                        )
                      }
                    />
                    {node.label}
                  </label>
                ))}
              </fieldset>
            </li>
          );
        })}
      </ol>
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => write([...phases, { mechanism: "sequential", participants: [] }])}
      >
        <Plus className="size-3.5" aria-hidden />
        Add phase
      </Button>
    </Field>
  );
}

/* --------------------------------- format --------------------------------- */

function FormatSection({ artifact }: { artifact: MADArtifact }) {
  const { getSubDimension, isUnderDevelopment } = useTaxonomy();
  const updateFormat = useDesignerStore((s) => s.updateFormat);
  const addNode = useDesignerStore((s) => s.addNode);

  const format = artifact.interaction.format ?? {};
  const content = format.content ?? {};
  const syntaxSub = getSubDimension("interaction", "format_syntax");
  const contentSub = getSubDimension("interaction", "format_content");
  const metadataSub = getSubDimension("interaction", "format_content_metadata");
  const memorySub = getSubDimension("interaction", "format_memory");
  const summarizer = summarizerNode(artifact.participants.nodes);

  const toggleMetadata = (key: string, next: boolean) => {
    const set = new Set(content.metadata_signals ?? []);
    if (next) set.add(key);
    else set.delete(key);
    updateFormat({ content: { metadata_signals: [...set] } });
  };

  return (
    <FieldGroup title="Format" tone="structured" icon={MessagesSquare}>
      {syntaxSub ? (
        <TaxonomySelect
          sub={syntaxSub}
          value={format.syntax}
          onChange={(v) => updateFormat({ syntax: v as FormatArtifact["syntax"] })}
          isUnderDevelopment={isUnderDevelopment}
          id="fmt-syntax"
        />
      ) : null}
      {contentSub ? (
        <TaxonomySelect
          sub={contentSub}
          value={content.strategy}
          onChange={(v) =>
            updateFormat({ content: { strategy: v as "verbatim" | "summarized" | "other" } })
          }
          isUnderDevelopment={isUnderDevelopment}
          id="fmt-content"
        />
      ) : null}
      {content.strategy === "summarized" ? (
        summarizer ? (
          <Notice tone="info" testId="fmt-summarizer">
            {summarizer.label} (the first participant with the Summarizer role)
            compresses each agent&apos;s visible history into one message.
          </Notice>
        ) : (
          <Notice
            testId="fmt-no-summarizer"
            actions={[
              {
                label: "Add summarizer",
                onClick: () => addNode({ label: "Summarizer", roles: ["summarizer"] }),
              },
            ]}
          >
            Summarized content needs a participant with the Summarizer role. Without
            one the run falls back to verbatim history (and notes it in the
            transcript).
          </Notice>
        )
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
            onChange={(v) => updateFormat({ memory: v as FormatArtifact["memory"] })}
            isUnderDevelopment={isUnderDevelopment}
            id="fmt-memory"
          />
        ) : null}
      </Disclosure>
    </FieldGroup>
  );
}
