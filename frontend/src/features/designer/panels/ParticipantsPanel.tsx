import { useState } from "react";
import { Boxes, MessageSquareText, Plus, Sparkles, Tag, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useTaxonomy } from "@/taxonomy/TaxonomyContext";
import { useDesignerStore } from "../designerStore";
import { isModelShared, nodePersonaScope, personaMode } from "../participantScope";
import { Field, FieldGroup, TaxonomyMultiSelect, findError } from "./fields";
import { ModelEditor, PersonaEditor, SharedFromDebate } from "./sharedEditors";

const CUSTOM_ROLE_PREFIX = "custom:";

/**
 * Per-node Participants inspector for the selected node (Req 1.*, 6.3).
 *
 * Renders, all data-driven from the taxonomy catalog, the fields of ONE
 * participant:
 *  - name + roles multi-select incl. custom roles (Req 1.5, 1.6)
 *  - persona template + attributes (Req 1.2, 1.9, 1.10)
 *  - instructions: the raw system prompt (always per node)
 *  - base-model binding to a configured provider + model (Req 1.8, 8.6)
 *
 * Scope rule (task 11.6): a setting is edited in exactly one place. When the
 * debate-level Participants settings govern a value (a shared persona for
 * debaters, a shared base model for everyone) the node shows it read-only with
 * a "Shared: edit in debate settings" link; when persona assignment is not
 * `manual` the persona fields are disabled.
 */
export function ParticipantsPanel({ nodeId }: { nodeId: string }) {
  const { getSubDimension, isUnderDevelopment } = useTaxonomy();
  const artifact = useDesignerStore((s) => s.artifact);
  const updateNode = useDesignerStore((s) => s.updateNode);
  const errors = useDesignerStore((s) => s.validationErrors);

  const rolesSub = getSubDimension("participants", "roles");
  const [customRole, setCustomRole] = useState("");

  const node = artifact?.participants.nodes.find((n) => n.id === nodeId);
  if (!node || !artifact) {
    return (
      <p className="p-4 text-sm text-muted-foreground">
        The selected participant no longer exists.
      </p>
    );
  }
  const nodeIndex = artifact.participants.nodes.findIndex((n) => n.id === nodeId);
  const participants = artifact.participants;

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

  const rolesError = findError(errors, `participants.nodes.${nodeIndex}.roles`);

  const personaScope = nodePersonaScope(participants, node);
  const mode = personaMode(participants);
  const modelShared = isModelShared(participants);

  return (
    <div className="space-y-6">
      <Field label="Name" htmlFor="node-label" icon={Tag}>
        <Input
          id="node-label"
          value={node.label}
          onChange={(e) => updateNode(nodeId, { label: e.target.value })}
        />
      </Field>

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
        icon={Sparkles}
      >
        {personaScope === "disabled" ? (
          <p className="text-xs text-muted-foreground" data-testid="node-persona-disabled">
            {mode === "automatic"
              ? "Automatic persona assignment is under development; personas cannot be set by hand."
              : "Persona assignment is Unspecified: set it to Manual in the debate settings to give participants personas."}
          </p>
        ) : null}
        {personaScope === "shared" ? (
          <SharedFromDebate what="debaters' persona" testId="node-persona-shared" />
        ) : null}
        <PersonaEditor
          value={node.persona}
          disabled={personaScope !== "own"}
          onChange={(patch) => updateNode(nodeId, { persona: patch })}
        />
      </FieldGroup>

      {/* --- Instructions (always per node, independent of persona settings) --- */}
      <FieldGroup
        title="Instructions"
        description="This participant's own instructions; always editable, independent of the persona settings."
        tone="prompt"
        icon={MessageSquareText}
      >
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
        icon={Boxes}
      >
        {modelShared ? (
          <SharedFromDebate what="base model" testId="node-model-shared" />
        ) : null}
        <ModelEditor
          value={node.base_model}
          disabled={modelShared}
          onChange={(patch) => updateNode(nodeId, { base_model: patch })}
        />
      </FieldGroup>
    </div>
  );
}
