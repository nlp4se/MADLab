import type { ConfigDetail, JsonObject } from "@/api";

/**
 * Helpers for reading the input template out of a configuration artifact.
 *
 * A config's `artifact.input_spec` (see `backend/mad/taxonomy/schema.py`) carries:
 *   - `template`: a prompt string with `{{placeholder}}` tags;
 *   - `placeholders`: the list of placeholder names;
 *   - `ad_hoc_fields`: `{ key, label }` pairs giving a human label for each
 *     placeholder shown in the single-input form.
 *
 * The artifact is transported as a free-form `JsonObject`, so these helpers
 * read it defensively and never throw on a missing or malformed shape.
 */

export interface TemplateField {
  /** The placeholder key (matches a `{{key}}` tag in the template). */
  key: string;
  /** A human-friendly label (from `ad_hoc_fields`, falls back to the key). */
  label: string;
}

/** Extract `{{placeholder}}` tags from a template string, in order, de-duped. */
export function placeholdersFromTemplate(template: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const re = /\{\{\s*([\w.-]+)\s*\}\}/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(template)) !== null) {
    const key = match[1];
    if (!seen.has(key)) {
      seen.add(key);
      out.push(key);
    }
  }
  return out;
}

function asRecord(value: unknown): JsonObject | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : null;
}

/** The raw `input_spec` sub-object from a config artifact, if present. */
function readInputSpec(artifact: JsonObject): JsonObject | null {
  return asRecord(artifact["input_spec"]);
}

/** The template string declared by the config (empty string when absent). */
export function templateString(config: ConfigDetail): string {
  const spec = readInputSpec(config.artifact);
  const template = spec?.["template"];
  return typeof template === "string" ? template : "";
}

/**
 * Derive the ordered list of template fields for the single-input form
 * (Req 10.2). Placeholders come from the explicit `placeholders` list when
 * present, otherwise they are parsed from the template; labels are taken from
 * `ad_hoc_fields` when a matching entry exists.
 */
export function templateFields(config: ConfigDetail): TemplateField[] {
  const spec = readInputSpec(config.artifact);

  const labels = new Map<string, string>();
  const adHoc = spec?.["ad_hoc_fields"];
  if (Array.isArray(adHoc)) {
    for (const entry of adHoc) {
      const rec = asRecord(entry);
      const key = rec?.["key"];
      const label = rec?.["label"];
      if (typeof key === "string") {
        labels.set(key, typeof label === "string" ? label : key);
      }
    }
  }

  let keys: string[] = [];
  const declared = spec?.["placeholders"];
  if (Array.isArray(declared)) {
    keys = declared.filter((k): k is string => typeof k === "string");
  }
  if (keys.length === 0) {
    keys = placeholdersFromTemplate(templateString(config));
  }
  // Fall back to any ad_hoc_field keys not already present.
  for (const key of labels.keys()) {
    if (!keys.includes(key)) keys.push(key);
  }

  return keys.map((key) => ({ key, label: labels.get(key) ?? key }));
}
