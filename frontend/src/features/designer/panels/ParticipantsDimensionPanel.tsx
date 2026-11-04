import { AlertTriangle, Boxes, Shuffle, Sparkles, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useTaxonomy } from "@/taxonomy/TaxonomyContext";
import type { ParticipantsArtifact } from "../artifact";
import { useDesignerStore } from "../designerStore";
import {
  detectConflicts,
  hasPersonaData,
  isDebater,
  isModelShared,
  modelSourceNode,
  modelsDiverge,
  personaMode,
  personaSourceNode,
  personasDiverge,
  type ParticipantConflict,
} from "../participantScope";
import { FieldGroup, TaxonomySelect } from "./fields";
import { ModelEditor, PersonaEditor } from "./sharedEditors";

/**
 * Debate-level Participants settings (task 11.6), shown on the Participants
 * tab whenever no node is selected.
 *
 * These settings DRIVE what is edited where (a setting is edited in exactly
 * one place):
 *  - Persona assignment (first): `unspecified` = no personas (fields disabled
 *    everywhere), `manual` = personas are set by hand, `automatic` = under
 *    development (fields disabled).
 *  - Persona heterogeneity (only with `manual`): `homogeneous` edits ONE shared
 *    persona here, applied to every debater-role node (judges / summarizers
 *    keep their own); `heterogeneous` = set per participant.
 *  - Base model heterogeneity: `homogeneous` edits ONE shared provider / model /
 *    family here, applied to ALL nodes; `heterogeneous` = set per participant.
 *
 * Data that contradicts the declared mode (a loaded / imported / assistant
 * config) is never silently rewritten: an inline banner offers the two fixes.
 */
type Assignment = NonNullable<ParticipantsArtifact["persona_assignment"]>;
type Heterogeneity = NonNullable<ParticipantsArtifact["persona_heterogeneity"]>;

export function ParticipantsDimensionPanel() {
  const { getSubDimension, isUnderDevelopment } = useTaxonomy();
  const artifact = useDesignerStore((s) => s.artifact);
  const setPersonaAssignment = useDesignerStore((s) => s.setPersonaAssignment);
  const setPersonaHeterogeneity = useDesignerStore((s) => s.setPersonaHeterogeneity);
  const setModelHeterogeneity = useDesignerStore((s) => s.setModelHeterogeneity);
  const updateSharedPersona = useDesignerStore((s) => s.updateSharedPersona);
  const updateSharedModel = useDesignerStore((s) => s.updateSharedModel);

  if (!artifact) return null;

  const participants = artifact.participants;
  const nodes = participants.nodes;
  const personaHetSub = getSubDimension("participants", "persona_heterogeneity");
  const personaAssignSub = getSubDimension("participants", "persona_assignment");
  const baseModelHetSub = getSubDimension("participants", "base_model_heterogeneity");

  const mode = personaMode(participants);
  const modelShared = isModelShared(participants);
  const conflicts = detectConflicts(participants);
  const personaConflict = conflicts.some(
    (c) => c.kind === "persona_divergent" || c.kind === "personas_without_manual",
  );
  const modelConflict = conflicts.some((c) => c.kind === "model_divergent");
  const hasDebaters = nodes.some(isDebater);
  const labelOf = (id?: string) => nodes.find((n) => n.id === id)?.label ?? id ?? "";

  const onAssignment = (value: Assignment) => {
    if (value === "unspecified" && nodes.some((n) => hasPersonaData(n.persona))) {
      const ok = window.confirm(
        "Set persona assignment to Unspecified?\n\n" +
          "This clears the persona (template, background, personality, stance) " +
          "of every participant. System prompts are kept.",
      );
      if (!ok) return;
    }
    setPersonaAssignment(value);
  };

  const onPersonaHet = (value: Heterogeneity) => {
    if (value === "homogeneous" && mode === "per_node" && personasDiverge(nodes)) {
      const source = personaSourceNode(nodes);
      const ok = window.confirm(
        "Make personas homogeneous?\n\n" +
          `The debaters have different personas. "${source?.label}"'s persona ` +
          "will be copied to every debater.",
      );
      if (!ok) return;
    }
    setPersonaHeterogeneity(value);
  };

  const onModelHet = (value: Heterogeneity) => {
    if (value === "homogeneous" && !modelShared && modelsDiverge(nodes)) {
      const source = modelSourceNode(nodes);
      const ok = window.confirm(
        "Make the base model homogeneous?\n\n" +
          `The participants use different models. "${source?.label}"'s ` +
          "provider/model will be copied to every participant.",
      );
      if (!ok) return;
    }
    setModelHeterogeneity(value);
  };

  const nodeCount = nodes.length;
  const sharedPersonaNode = personaSourceNode(nodes);
  const sharedModelNode = modelSourceNode(nodes);

  return (
    <div className="space-y-6">
      <p className="rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
        Debate-level settings for the participant set ({nodeCount}{" "}
        {nodeCount === 1 ? "participant" : "participants"}). Values shared here
        are read-only on the nodes; select a node to edit its name, roles,
        instructions, and anything set per participant.
      </p>

      {conflicts.map((c) => (
        <ConflictBanner key={c.kind} conflict={c} labelOf={labelOf} />
      ))}

      {/* --- Personas --- */}
      <FieldGroup title="Personas" tone="prompt" icon={Sparkles}>
        {personaAssignSub ? (
          <TaxonomySelect
            sub={personaAssignSub}
            value={participants.persona_assignment}
            onChange={(v) => onAssignment(v as Assignment)}
            isUnderDevelopment={isUnderDevelopment}
            id="dim-persona-assign"
            icon={Shuffle}
            hint="Decides whether participants get personas at all, and who sets them."
            note={
              mode === "unspecified" ? (
                <span data-testid="dim-persona-unspecified-note">
                  No personas: persona fields are disabled. Choose Manual to set them.
                </span>
              ) : mode === "automatic" ? (
                <span data-testid="dim-persona-automatic-note">
                  Automatic assignment is under development: persona fields are
                  disabled.
                </span>
              ) : null
            }
          />
        ) : null}
        {personaHetSub ? (
          <TaxonomySelect
            sub={personaHetSub}
            value={participants.persona_heterogeneity}
            onChange={(v) => onPersonaHet(v as Heterogeneity)}
            isUnderDevelopment={isUnderDevelopment}
            id="dim-persona-het"
            icon={Users}
            hint="Homogeneous: one shared persona for every debater (edited here). Heterogeneous: each participant has its own."
            disabled={mode !== "shared" && mode !== "per_node"}
            note={
              mode === "shared" || mode === "per_node" ? null : (
                <span data-testid="dim-persona-het-hint">
                  Only applies when personas are assigned manually.
                </span>
              )
            }
          />
        ) : null}

        {mode === "shared" ? (
          <div className="space-y-3 rounded-md border p-3" data-testid="dim-shared-persona">
            <p className="text-xs text-muted-foreground">
              Shared persona, applied to every debater. Judges and summarizers keep
              their own persona (edit it on the node).
            </p>
            {!hasDebaters ? (
              <p className="text-xs text-muted-foreground">
                Add a participant with the Debater role to set the shared persona.
              </p>
            ) : null}
            {personaConflict ? (
              <p className="text-xs text-amber-700 dark:text-amber-400">
                Resolve the conflict above to edit the shared persona.
              </p>
            ) : null}
            <PersonaEditor
              idPrefix="dim-"
              value={sharedPersonaNode?.persona}
              disabled={!hasDebaters || personaConflict}
              onChange={updateSharedPersona}
            />
          </div>
        ) : null}
        {mode === "per_node" ? (
          <p
            className="rounded-md border border-dashed p-3 text-xs text-muted-foreground"
            data-testid="dim-persona-per-node"
          >
            Personas are set per participant: select a node on the canvas to edit
            its persona.
          </p>
        ) : null}
      </FieldGroup>

      {/* --- Base model --- */}
      <FieldGroup title="Base model" tone="structured" icon={Boxes}>
        {baseModelHetSub ? (
          <TaxonomySelect
            sub={baseModelHetSub}
            value={participants.base_model_heterogeneity}
            onChange={(v) => onModelHet(v as Heterogeneity)}
            isUnderDevelopment={isUnderDevelopment}
            id="dim-model-het"
            icon={Boxes}
            hint="Homogeneous: one shared provider/model for every participant (edited here). Heterogeneous: each participant has its own."
          />
        ) : null}

        {modelShared ? (
          <div className="space-y-3 rounded-md border p-3" data-testid="dim-shared-model">
            <p className="text-xs text-muted-foreground">
              Shared base model, applied to every participant.
            </p>
            {nodeCount === 0 ? (
              <p className="text-xs text-muted-foreground">
                Add a participant to set the shared model.
              </p>
            ) : null}
            {modelConflict ? (
              <p className="text-xs text-amber-700 dark:text-amber-400">
                Resolve the conflict above to edit the shared model.
              </p>
            ) : null}
            <ModelEditor
              idPrefix="dim-"
              value={sharedModelNode?.base_model}
              disabled={nodeCount === 0 || modelConflict}
              onChange={updateSharedModel}
            />
          </div>
        ) : (
          <p
            className="rounded-md border border-dashed p-3 text-xs text-muted-foreground"
            data-testid="dim-model-per-node"
          >
            Models are set per participant: select a node on the canvas to bind its
            provider and model.
          </p>
        )}
      </FieldGroup>
    </div>
  );
}

/**
 * Inline banner for data that contradicts the declared participant mode, with
 * the two explicit fixes (nothing is rewritten until the user picks one).
 */
function ConflictBanner({
  conflict,
  labelOf,
}: {
  conflict: ParticipantConflict;
  labelOf: (id?: string) => string;
}) {
  const updateParticipants = useDesignerStore((s) => s.updateParticipants);
  const alignPersonas = useDesignerStore((s) => s.alignPersonas);
  const alignModels = useDesignerStore((s) => s.alignModels);
  const clearPersonas = useDesignerStore((s) => s.clearPersonas);

  const n = conflict.nodeIds.length;
  const source = labelOf(conflict.sourceId);
  let message: string;
  let fixes: Array<{ label: string; run: () => void }>;
  switch (conflict.kind) {
    case "personas_without_manual":
      message = `Persona assignment is Unspecified, but ${n} ${
        n === 1 ? "participant has" : "participants have"
      } a persona.`;
      fixes = [
        { label: "Switch to Manual", run: () => updateParticipants({ persona_assignment: "manual" }) },
        { label: "Clear personas", run: clearPersonas },
      ];
      break;
    case "persona_divergent":
      message = "Personas are homogeneous, but the debaters have different personas.";
      fixes = [
        { label: `Make all match ${source}`, run: alignPersonas },
        {
          label: "Switch to heterogeneous",
          run: () => updateParticipants({ persona_heterogeneity: "heterogeneous" }),
        },
      ];
      break;
    case "model_divergent":
      message = "The base model is homogeneous, but the participants use different models.";
      fixes = [
        { label: `Make all match ${source}`, run: alignModels },
        {
          label: "Switch to heterogeneous",
          run: () => updateParticipants({ base_model_heterogeneity: "heterogeneous" }),
        },
      ];
      break;
  }

  return (
    <div
      role="alert"
      data-testid={`participant-conflict-${conflict.kind}`}
      className="space-y-2 rounded-md border border-amber-500/50 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-300"
    >
      <p className="flex items-start gap-1.5 font-medium">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        {message}
      </p>
      <div className="flex flex-wrap gap-2">
        {fixes.map((f) => (
          <Button key={f.label} type="button" size="sm" variant="outline" onClick={f.run}>
            {f.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
