/**
 * Input editor helpers (task 11.10) — the pure rules behind the designer's
 * Input panel, shared by the store and the tests.
 *
 * The instance input lives in `artifact.input_spec` (backend `InputSpec`):
 *   - `template`: text with `{{placeholder}}` tags (backend `PLACEHOLDER_PATTERN`);
 *   - `placeholders`: the tags the template references, kept in sync on edit;
 *   - `ad_hoc_fields`: a `{ key, label }` per placeholder, the label shown in
 *     the run launcher's single-input form (defaults to the key).
 *
 * The engine resolves the template per run and appends "Task: <resolved>" to
 * the system prompt of every entry participant (the Start connectors); judges
 * see the same "Task: ..." line at the top of their decision context. An empty
 * template still runs, but nobody receives a task, so the designer and the run
 * launcher flag it.
 */
import { placeholdersFromTemplate, resolveTemplate } from "@/features/executions/inputSpec";

import type { AdHocFieldArtifact, InputSpecArtifact, MADArtifact } from "./artifact";

/** The starter input of a NEW configuration: one `{{input}}` field labelled "Input". */
export const STARTER_INPUT_SPEC: Readonly<Required<
  Pick<InputSpecArtifact, "template" | "placeholders" | "ad_hoc_fields">
>> = Object.freeze({
  template: "{{input}}",
  placeholders: ["input"],
  ad_hoc_fields: [{ key: "input", label: "Input" }],
});

/** A fresh, mutable copy of {@link STARTER_INPUT_SPEC}. */
export function starterInputSpec(): Required<
  Pick<InputSpecArtifact, "template" | "placeholders" | "ad_hoc_fields">
> {
  return {
    template: STARTER_INPUT_SPEC.template,
    placeholders: [...STARTER_INPUT_SPEC.placeholders],
    ad_hoc_fields: STARTER_INPUT_SPEC.ad_hoc_fields.map((f) => ({ ...f })),
  };
}

/** The artifact's template string ("" when absent or malformed). */
export function inputTemplate(artifact: Pick<MADArtifact, "input_spec"> | null): string {
  const t = artifact?.input_spec?.template;
  return typeof t === "string" ? t : "";
}

/** True when the template is empty/whitespace: runs would carry no task. */
export function isInputTemplateEmpty(
  artifact: Pick<MADArtifact, "input_spec"> | null,
): boolean {
  return inputTemplate(artifact).trim() === "";
}

/** The stored labels keyed by placeholder (defensive against bad entries). */
function labelMap(spec: InputSpecArtifact | undefined): Map<string, string> {
  const labels = new Map<string, string>();
  for (const f of Array.isArray(spec?.ad_hoc_fields) ? spec.ad_hoc_fields : []) {
    if (f && typeof f.key === "string") {
      labels.set(f.key, typeof f.label === "string" ? f.label : f.key);
    }
  }
  return labels;
}

/** One field per placeholder, in template order (label defaults to the key). */
export function fieldsFor(
  placeholders: string[],
  labels: Map<string, string>,
): AdHocFieldArtifact[] {
  return placeholders.map((key) => ({ key, label: labels.get(key) || key }));
}

/**
 * The spec after editing the template: `placeholders` re-detected from the
 * new text; `ad_hoc_fields` keep the label of every surviving placeholder,
 * default new ones to their key, and drop labels of removed placeholders.
 * Unknown spec fields are preserved.
 */
export function withTemplate(
  spec: InputSpecArtifact | undefined,
  template: string,
): InputSpecArtifact {
  const placeholders = placeholdersFromTemplate(template);
  return {
    ...(spec ?? {}),
    template,
    placeholders,
    ad_hoc_fields: fieldsFor(placeholders, labelMap(spec)),
  };
}

/**
 * The spec with `key`'s label set. The label is stored as typed (an empty one
 * is kept so the field can be cleared while editing; readers such as the run
 * launcher fall back to the key). Only placeholders the template references
 * get a label; the field list stays in placeholder order.
 */
export function withPlaceholderLabel(
  spec: InputSpecArtifact | undefined,
  key: string,
  label: string,
): InputSpecArtifact {
  const placeholders = placeholdersFromTemplate(
    typeof spec?.template === "string" ? spec.template : "",
  );
  const labels = labelMap(spec);
  return {
    ...(spec ?? {}),
    placeholders,
    ad_hoc_fields: placeholders.map((k) => ({
      key: k,
      label: k === key ? label : labels.get(k) || k,
    })),
  };
}

/** The panel's editable view: one row per detected placeholder. */
export function placeholderRows(spec: InputSpecArtifact | undefined): AdHocFieldArtifact[] {
  const template = typeof spec?.template === "string" ? spec.template : "";
  const labels = labelMap(spec);
  return placeholdersFromTemplate(template).map((key) => ({
    key,
    label: labels.has(key) ? (labels.get(key) as string) : key,
  }));
}

/**
 * What the entry participants receive for a run with `samples` as the field
 * values (the engine's lenient resolution: unknown tags stay verbatim).
 */
export function previewInput(template: string, samples: Record<string, string>): string {
  return resolveTemplate(template, samples);
}
