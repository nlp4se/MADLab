import { useMemo } from "react";
import { Link2 } from "lucide-react";

import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useTaxonomy } from "@/taxonomy/TaxonomyContext";
import type { BaseModelArtifact, PersonaArtifact } from "../artifact";
import { useDesignerStore } from "../designerStore";
import type { ModelFields, PersonaFields } from "../participantScope";
import { useProvidersQuery } from "../useProviders";
import { Field, TaxonomySelect } from "./fields";

/**
 * Editors shared by the debate-level (`ParticipantsDimensionPanel`) and the
 * node-level (`ParticipantsPanel`) Participants inspectors (task 11.6). Both
 * levels render the SAME fields; only the write target differs (one node vs.
 * every governed node), so the editors take a value + `onChange` patch.
 *
 * `idPrefix` keeps element ids unique per level ("" on the node keeps the
 * historical `node-provider` / `persona-stance` ids).
 */

type PersonaKey = "background" | "personality" | "stance";

/** Persona template picker + background/personality/stance (Req 1.2, 1.9, 1.10). */
export function PersonaEditor({
  value,
  onChange,
  idPrefix = "",
  disabled = false,
}: {
  value: PersonaArtifact | undefined;
  onChange: (patch: Partial<PersonaFields>) => void;
  idPrefix?: string;
  disabled?: boolean;
}) {
  const { getSubDimension, taxonomy } = useTaxonomy();
  const personaAttrsSub = getSubDimension("participants", "persona_attributes");
  const patterns = taxonomy.templates.persona_patterns;
  const byKey = useMemo(() => new Map(patterns.map((p) => [p.key, p])), [patterns]);

  // Selecting a pattern fills the attributes from its first field-set and
  // records `template_ref`; the fields stay editable afterwards (Req 1.10).
  const applyTemplate = (key: string) => {
    if (!key) {
      onChange({ template_ref: null });
      return;
    }
    const first = byKey.get(key)?.personas[0];
    onChange({
      template_ref: key,
      background: first?.background ?? null,
      personality: first?.personality ?? null,
      stance: first?.stance ?? null,
    });
  };

  return (
    <>
      <Field
        label="Persona template"
        description="Prefill from a predefined persona pattern; all fields stay editable."
        htmlFor={`${idPrefix}persona-template`}
      >
        <Select
          id={`${idPrefix}persona-template`}
          value={value?.template_ref ?? ""}
          onChange={(e) => applyTemplate(e.target.value)}
          disabled={disabled}
        >
          <option value="">— No template —</option>
          {patterns.map((p) => (
            <option key={p.key} value={p.key} title={p.description}>
              {p.label}
            </option>
          ))}
        </Select>
      </Field>
      {personaAttrsSub?.values.map((attr) => (
        <Field
          key={attr.key}
          label={attr.label}
          description={attr.description}
          htmlFor={`${idPrefix}persona-${attr.key}`}
        >
          <Textarea
            id={`${idPrefix}persona-${attr.key}`}
            rows={2}
            disabled={disabled}
            value={(value?.[attr.key as PersonaKey] as string | null | undefined) ?? ""}
            onChange={(e) => onChange({ [attr.key]: e.target.value || null })}
          />
        </Field>
      ))}
    </>
  );
}

/** Provider + model + family binding (Req 1.8, 8.6). */
export function ModelEditor({
  value,
  onChange,
  idPrefix = "node-",
  disabled = false,
}: {
  value: BaseModelArtifact | undefined;
  onChange: (patch: Partial<ModelFields>) => void;
  idPrefix?: string;
  disabled?: boolean;
}) {
  const { getSubDimension, isUnderDevelopment } = useTaxonomy();
  const familySub = getSubDimension("participants", "base_model_family");
  const providersQuery = useProvidersQuery();
  const providers = providersQuery.data ?? [];
  const boundProvider = providers.find(
    (p) => String(p.id) === String(value?.provider_id),
  );

  return (
    <>
      <Field
        label="Provider"
        description="A provider configured in the Providers view."
        htmlFor={`${idPrefix}provider`}
      >
        <Select
          id={`${idPrefix}provider`}
          value={value?.provider_id ?? ""}
          disabled={disabled}
          onChange={(e) =>
            onChange({ provider_id: e.target.value || null, model_key: null })
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
        htmlFor={`${idPrefix}model`}
      >
        <Select
          id={`${idPrefix}model`}
          value={value?.model_key ?? ""}
          onChange={(e) => onChange({ model_key: e.target.value || null })}
          disabled={disabled || !boundProvider}
        >
          <option value="">— Select model —</option>
          {/* Keep an unknown stored key visible rather than showing a blank. */}
          {value?.model_key && !boundProvider?.models.includes(value.model_key) ? (
            <option value={value.model_key}>{value.model_key}</option>
          ) : null}
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
          value={value?.family}
          onChange={(v) => onChange({ family: v as "open_weight" | "closed_weight" })}
          isUnderDevelopment={isUnderDevelopment}
          id={`${idPrefix}family`}
          disabled={disabled}
        />
      ) : null}
    </>
  );
}

/**
 * Read-only marker for a node value governed at debate level: a short reason
 * plus a "Shared: edit in debate settings" link that clears the selection (so
 * the inspector shows the debate-level Participants settings).
 */
export function SharedFromDebate({ what, testId }: { what: string; testId?: string }) {
  const setSelection = useDesignerStore((s) => s.setSelection);
  return (
    <div
      className="flex flex-wrap items-center gap-1.5 rounded-md border border-dashed bg-muted/40 px-2.5 py-1.5 text-xs text-muted-foreground"
      data-testid={testId}
    >
      <span>The {what} is shared by the debate.</span>
      <button
        type="button"
        className="inline-flex items-center gap-1 font-medium text-primary underline-offset-2 hover:underline"
        onClick={() => setSelection(null)}
      >
        <Link2 className="size-3" aria-hidden />
        Shared: edit in debate settings
      </button>
    </div>
  );
}
