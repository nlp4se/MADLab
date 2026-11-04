import { Boxes, Shuffle, Users } from "lucide-react";

import { useTaxonomy } from "@/taxonomy/TaxonomyContext";
import { useDesignerStore } from "../designerStore";
import { FieldGroup, TaxonomySelect } from "./fields";

/**
 * Config-level (dimension-wide) participant settings.
 *
 * These are NOT per-node: persona/base-model heterogeneity and persona
 * assignment describe the participant *set* as a whole, so editing them must
 * not require selecting a participant. The inspector shows this panel on the
 * Participants tab whenever no node is selected.
 *
 * They are largely *descriptive* — they reflect how you actually configure the
 * participants (which personas/models you assign per node) rather than
 * independently driving execution — so each carries an info hint saying so.
 */
const DESCRIPTIVE_HINT =
  "Descriptive: this reflects how you actually set up the participants " +
  "(the personas and models you assign to each node). It documents intent " +
  "rather than independently changing how the debate runs.";

export function ParticipantsDimensionPanel() {
  const { getSubDimension, isUnderDevelopment } = useTaxonomy();
  const artifact = useDesignerStore((s) => s.artifact);
  const updateParticipants = useDesignerStore((s) => s.updateParticipants);

  if (!artifact) return null;

  const participants = artifact.participants;
  const personaHetSub = getSubDimension("participants", "persona_heterogeneity");
  const personaAssignSub = getSubDimension("participants", "persona_assignment");
  const baseModelHetSub = getSubDimension(
    "participants",
    "base_model_heterogeneity",
  );
  const nodeCount = participants.nodes.length;

  return (
    <div className="space-y-6">
      <p className="rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
        These settings describe the participant set as a whole
        ({nodeCount} {nodeCount === 1 ? "participant" : "participants"}). To edit
        a single participant's roles, persona, and model, select its node on the
        canvas.
      </p>

      <FieldGroup title="Participant set" tone="structured" icon={Users}>
        {personaHetSub ? (
          <TaxonomySelect
            sub={personaHetSub}
            value={participants.persona_heterogeneity}
            onChange={(v) =>
              updateParticipants({
                persona_heterogeneity: v as "homogeneous" | "heterogeneous",
              })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="dim-persona-het"
            icon={Users}
            hint={DESCRIPTIVE_HINT}
          />
        ) : null}
        {baseModelHetSub ? (
          <TaxonomySelect
            sub={baseModelHetSub}
            value={participants.base_model_heterogeneity}
            onChange={(v) =>
              updateParticipants({
                base_model_heterogeneity: v as "homogeneous" | "heterogeneous",
              })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="dim-model-het"
            icon={Boxes}
            hint={DESCRIPTIVE_HINT}
          />
        ) : null}
        {personaAssignSub ? (
          <TaxonomySelect
            sub={personaAssignSub}
            value={participants.persona_assignment}
            onChange={(v) =>
              updateParticipants({
                persona_assignment: v as "unspecified" | "manual" | "automatic",
              })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="dim-persona-assign"
            icon={Shuffle}
            hint={DESCRIPTIVE_HINT}
          />
        ) : null}
      </FieldGroup>
    </div>
  );
}
