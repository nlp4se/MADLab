import { useMemo, useState } from "react";
import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useTaxonomy } from "@/taxonomy/TaxonomyContext";
import type { ParticipantNodeArtifact } from "../artifact";
import { useDesignerStore } from "../designerStore";
import { useProvidersQuery } from "../useProviders";
import {
  Disclosure,
  Field,
  FieldGroup,
  TaxonomyMultiSelect,
  TaxonomySelect,
  findError,
} from "./fields";

const CUSTOM_ROLE_PREFIX = "custom:";

/**
 * Participants-dimension inspector for the selected node (Req 1.*, 6.3).
 *
 * Renders, all data-driven from the taxonomy catalog:
 *  - roles multi-select incl. custom/user-defined roles (Req 1.5, 1.6)
 *  - persona background/personality/stance free-form fields + a persona-template
 *    picker drawn from `templates.persona_patterns` (Req 1.2, 1.9, 1.10)
 *  - base-model binding to a configured provider + model (Req 1.8, 8.6)
 *  - dimension-level heterogeneity / assignment selectors (Req 1.3, 1.4, 1.7)
 *
 * Prompt-designed fields (persona, system prompt) and structured fields
 * (everything else) are visually grouped and labelled (the design's
 * distinction). Advanced options sit behind progressive disclosure (Req 7.2).
 */
export function ParticipantsPanel({ nodeId }: { nodeId: string }) {
  const { getSubDimension, taxonomy, isUnderDevelopment } = useTaxonomy();
  const artifact = useDesignerStore((s) => s.artifact);
  const updateNode = useDesignerStore((s) => s.updateNode);
  const updateParticipants = useDesignerStore((s) => s.updateParticipants);
  const errors = useDesignerStore((s) => s.validationErrors);
  const providersQuery = useProvidersQuery();

  const node = artifact?.participants.nodes.find((n) => n.id === nodeId);
  const nodeIndex = artifact?.participants.nodes.findIndex(
    (n) => n.id === nodeId,
  );

  const rolesSub = getSubDimension("participants", "roles");
  const personaAttrsSub = getSubDimension("participants", "persona_attributes");
  const personaHetSub = getSubDimension("participants", "persona_heterogeneity");
  const personaAssignSub = getSubDimension("participants", "persona_assignment");
  const familySub = getSubDimension("participants", "base_model_family");
  const baseModelHetSub = getSubDimension(
    "participants",
    "base_model_heterogeneity",
  );

  const [customRole, setCustomRole] = useState("");

  if (!node || !artifact) {
    return (
      <p className="p-4 text-sm text-muted-foreground">
        The selected participant no longer exists.
      </p>
    );
  }

  const roles = node.roles ?? [];
  const customRoles = roles.filter((r) => r.startsWith(CUSTOM_ROLE_PREFIX));

  const toggleRole = (key: string, next: boolean) => {
    const set = new Set(roles);
    if (next) set.add(key);
    else set.delete(key);
    updateNode(nodeId, { roles: [...set] });
  };

  const addCustomRole = () => {
    const name = customRole.trim();
    if (!name) return;
    const key = `${CUSTOM_ROLE_PREFIX}${name}`;
    if (!roles.includes(key)) updateNode(nodeId, { roles: [...roles, key] });
    setCustomRole("");
  };

  const removeCustomRole = (key: string) => {
    updateNode(nodeId, { roles: roles.filter((r) => r !== key) });
  };

  const patchPersona = (patch: Partial<ParticipantNodeArtifact["persona"]>) =>
    updateNode(nodeId, { persona: { ...node.persona, ...patch } });

  const providers = providersQuery.data ?? [];
  const boundProvider = providers.find(
    (p) => String(p.id) === String(node.base_model?.provider_id),
  );

  const rolesError = findError(
    errors,
    `participants.nodes.${nodeIndex}.roles`,
  );

  const personaPatterns = taxonomy.templates.persona_patterns;

  return (
    <div className="space-y-6">
      <div>
        <Label htmlFor="node-label">Name</Label>
        <Input
          id="node-label"
          value={node.label}
          onChange={(e) => updateNode(nodeId, { label: e.target.value })}
        />
      </div>

      {/* --- Roles (structured, Req 1.5, 1.6) --- */}
      <FieldGroup
        title="Roles"
        description="Functional roles this participant combines."
        tone="structured"
      >
        {rolesSub ? (
          <TaxonomyMultiSelect
            sub={rolesSub}
            selected={roles}
            onToggle={toggleRole}
            isUnderDevelopment={isUnderDevelopment}
            extra={
              <div className="space-y-1.5 pt-1">
                {customRoles.map((key) => (
                  <div key={key} className="flex items-center gap-2 text-sm">
                    <span className="rounded bg-participants-muted px-2 py-0.5 text-xs">
                      {key.slice(CUSTOM_ROLE_PREFIX.length)}
                    </span>
                    <button
                      type="button"
                      className="text-muted-foreground hover:text-destructive"
                      aria-label={`Remove custom role ${key.slice(
                        CUSTOM_ROLE_PREFIX.length,
                      )}`}
                      onClick={() => removeCustomRole(key)}
                    >
                      <X className="size-3.5" aria-hidden />
                    </button>
                  </div>
                ))}
                <div className="flex items-center gap-2">
                  <Input
                    aria-label="Custom role name"
                    placeholder="Custom role…"
                    value={customRole}
                    onChange={(e) => setCustomRole(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addCustomRole();
                      }
                    }}
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={addCustomRole}
                  >
                    <Plus className="size-4" aria-hidden />
                    Add
                  </Button>
                </div>
                {rolesError ? (
                  <p role="alert" className="text-xs text-destructive">
                    {rolesError}
                  </p>
                ) : null}
              </div>
            }
          />
        ) : null}
      </FieldGroup>

      {/* --- Persona (prompt-designed, Req 1.2, 1.9, 1.10) --- */}
      <FieldGroup
        title="Persona"
        description="Free-form, prompt-designed attributes. Start from a pattern, then edit freely."
        tone="prompt"
      >
        <PersonaTemplatePicker
          nodeId={nodeId}
          patterns={personaPatterns}
          currentRef={node.persona?.template_ref ?? null}
        />
        {personaAttrsSub?.values.map((attr) => (
          <Field
            key={attr.key}
            label={attr.label}
            description={attr.description}
            htmlFor={`persona-${attr.key}`}
          >
            <Textarea
              id={`persona-${attr.key}`}
              rows={2}
              value={
                (node.persona?.[
                  attr.key as "background" | "personality" | "stance"
                ] as string) ?? ""
              }
              onChange={(e) =>
                patchPersona({ [attr.key]: e.target.value || null })
              }
            />
          </Field>
        ))}
        <Field
          label="System prompt"
          description="A raw system prompt overriding the composed persona (optional)."
          htmlFor="node-system-prompt"
        >
          <Textarea
            id="node-system-prompt"
            rows={3}
            value={node.system_prompt ?? ""}
            onChange={(e) =>
              updateNode(nodeId, { system_prompt: e.target.value || null })
            }
          />
        </Field>
      </FieldGroup>

      {/* --- Base model (structured, Req 1.8, 8.6) --- */}
      <FieldGroup
        title="Base model"
        description="Bind this participant to a configured provider and model."
        tone="structured"
      >
        <Field
          label="Provider"
          description="A provider configured in the Providers view."
          htmlFor="node-provider"
        >
          <Select
            id="node-provider"
            value={node.base_model?.provider_id ?? ""}
            onChange={(e) =>
              updateNode(nodeId, {
                base_model: {
                  provider_id: e.target.value || null,
                  // reset model when provider changes
                  model_key: null,
                },
              })
            }
          >
            <option value="">— Select provider —</option>
            {providers.map((p) => (
              <option key={p.id} value={String(p.id)}>
                {p.name}
              </option>
            ))}
          </Select>
          {providersQuery.isLoading ? (
            <p className="text-xs text-muted-foreground">Loading providers…</p>
          ) : null}
          {!providersQuery.isLoading && providers.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No providers configured yet — add one in the Providers view.
            </p>
          ) : null}
        </Field>

        <Field
          label="Model"
          description="One of the provider's configured model keys."
          htmlFor="node-model"
        >
          <Select
            id="node-model"
            value={node.base_model?.model_key ?? ""}
            onChange={(e) =>
              updateNode(nodeId, {
                base_model: { model_key: e.target.value || null },
              })
            }
            disabled={!boundProvider}
          >
            <option value="">— Select model —</option>
            {(boundProvider?.models ?? []).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </Select>
        </Field>

        {familySub ? (
          <TaxonomySelect
            sub={familySub}
            value={node.base_model?.family}
            onChange={(v) =>
              updateNode(nodeId, {
                base_model: { family: v as "open_weight" | "closed_weight" },
              })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="node-family"
          />
        ) : null}
      </FieldGroup>

      {/* --- Dimension-level options (advanced, Req 1.3, 1.4, 1.7) --- */}
      <Disclosure summary="Dimension-level options">
        {personaHetSub ? (
          <TaxonomySelect
            sub={personaHetSub}
            value={artifact.participants.persona_heterogeneity}
            onChange={(v) =>
              updateParticipants({
                persona_heterogeneity: v as "homogeneous" | "heterogeneous",
              })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="persona-het"
          />
        ) : null}
        {personaAssignSub ? (
          <TaxonomySelect
            sub={personaAssignSub}
            value={artifact.participants.persona_assignment}
            onChange={(v) =>
              updateParticipants({
                persona_assignment: v as "unspecified" | "manual" | "automatic",
              })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="persona-assign"
          />
        ) : null}
        {baseModelHetSub ? (
          <TaxonomySelect
            sub={baseModelHetSub}
            value={artifact.participants.base_model_heterogeneity}
            onChange={(v) =>
              updateParticipants({
                base_model_heterogeneity: v as "homogeneous" | "heterogeneous",
              })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="model-het"
          />
        ) : null}
      </Disclosure>
    </div>
  );
}

/**
 * A persona-template picker (Req 1.9). Selecting a pattern fills the node's
 * persona attribute fields from the pattern's first field-set and records the
 * `template_ref`; the fields remain fully editable afterward (Req 1.10).
 */
function PersonaTemplatePicker({
  nodeId,
  patterns,
  currentRef,
}: {
  nodeId: string;
  patterns: ReturnType<typeof useTaxonomy>["taxonomy"]["templates"]["persona_patterns"];
  currentRef: string | null;
}) {
  const updateNode = useDesignerStore((s) => s.updateNode);
  const byKey = useMemo(
    () => new Map(patterns.map((p) => [p.key, p])),
    [patterns],
  );

  const apply = (key: string) => {
    if (!key) {
      updateNode(nodeId, { persona: { template_ref: null } });
      return;
    }
    const pattern = byKey.get(key);
    const first = pattern?.personas[0];
    updateNode(nodeId, {
      persona: {
        template_ref: key,
        background: first?.background ?? null,
        personality: first?.personality ?? null,
        stance: first?.stance ?? null,
      },
    });
  };

  return (
    <Field
      label="Persona template"
      description="Prefill from a predefined persona pattern; all fields stay editable."
      htmlFor="persona-template"
    >
      <Select
        id="persona-template"
        value={currentRef ?? ""}
        onChange={(e) => apply(e.target.value)}
      >
        <option value="">— No template —</option>
        {patterns.map((p) => (
          <option key={p.key} value={p.key} title={p.description}>
            {p.label}
          </option>
        ))}
      </Select>
    </Field>
  );
}
