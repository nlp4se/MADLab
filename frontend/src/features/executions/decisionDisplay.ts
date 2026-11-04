import type { JsonObject } from "@/api";
import { innerSchema } from "@/lib/outputSchema";

/**
 * How a final decision (or a structured agent reply) is displayed (task 11.12,
 * Req 3.5, 11.2, 13.3).
 *
 * A decision can be a short label ("NF"), a long free-text verdict, or — with
 * an agreement `output_schema` — a parsed object that may carry many fields
 * (execution 3: `{requirement, debaters_arguments, moderator_evaluation,
 * final_classification}`). `decisionDisplay` splits it into:
 *
 *  - `label`: the short value worth showing as a pill — the schema's single
 *    enum property, else a known label key, else a short scalar; `null` when
 *    there is none;
 *  - `body`: everything else as a readable structure (text paragraph, bullet
 *    list, key/value list), never squeezed into a pill.
 *
 * The label precedence mirrors the backend scorer
 * (`mad.evaluation.transcript_adapter.decision_label`), so the pill shows the
 * label that is evaluated.
 */

/** Keys that conventionally carry a structured decision's label (priority order). */
export const LABEL_KEYS = [
  "class",
  "label",
  "classification",
  "final_classification",
  "decision",
  "answer",
  "verdict",
] as const;

/** Longest string still shown as a pill. */
export const SHORT_LABEL_MAX = 40;

export type DisplayValue =
  | { kind: "text"; text: string }
  | { kind: "list"; items: DisplayValue[] }
  | { kind: "fields"; fields: DisplayField[] };

export interface DisplayField {
  key: string;
  /** Humanized key, e.g. "debaters_arguments" -> "Debaters arguments". */
  label: string;
  value: DisplayValue;
}

export interface DecisionDisplay {
  label: string | null;
  /** The object key the label was taken from (excluded from the body). */
  labelKey: string | null;
  body: DisplayValue | null;
}

type PlainObject = Record<string, unknown>;

function isPlainObject(value: unknown): value is PlainObject {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

/** Parse a string that is a whole JSON object; otherwise `null`. */
function parseJsonObject(value: string): PlainObject | null {
  const text = value.trim();
  if (!text.startsWith("{") || !text.endsWith("}")) return null;
  try {
    const parsed: unknown = JSON.parse(text);
    return isPlainObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/** A value short enough for a pill, as text; `null` otherwise. */
export function shortScalar(value: unknown): string | null {
  if (typeof value === "string") {
    const text = value.trim();
    if (!text || text.length > SHORT_LABEL_MAX || /[\r\n]/.test(text)) return null;
    return text;
  }
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : null;
  if (typeof value === "boolean") return String(value);
  return null;
}

/**
 * Unwrap a provider-style `{name, schema: {...}}` envelope (execution 3 stores
 * the OpenAI `json_schema` wrapper) to the JSON schema proper. Shared with the
 * designer and mirrored by the backend normalizer (task 11.13).
 */
export { innerSchema };

/**
 * The lone enum-constrained property (else the lone property) of an object
 * schema — mirrors the backend `_single_enum_property`.
 */
export function singleEnumProperty(schema: unknown): string | null {
  const inner = innerSchema(schema);
  if (!inner || inner["type"] !== "object") return null;
  const props = inner["properties"];
  if (!isPlainObject(props)) return null;
  const enumProps = Object.entries(props)
    .filter(([, spec]) => isPlainObject(spec) && Array.isArray(spec["enum"]))
    .map(([name]) => name);
  if (enumProps.length === 1) return enumProps[0];
  const names = Object.keys(props);
  return names.length === 1 ? names[0] : null;
}

/** The agreement `output_schema` from an execution's config snapshot. */
export function outputSchemaFromSnapshot(
  snapshot: JsonObject | null | undefined,
): unknown {
  const agreement = isPlainObject(snapshot) ? snapshot["agreement"] : null;
  return isPlainObject(agreement) ? (agreement["output_schema"] ?? null) : null;
}

function labelFromObject(
  obj: PlainObject,
  schema: unknown,
): { label: string; key: string } | null {
  const enumProp = singleEnumProperty(schema);
  if (enumProp != null && enumProp in obj) {
    const label = shortScalar(obj[enumProp]);
    if (label != null) return { label, key: enumProp };
  }
  const byLower = new Map(Object.keys(obj).map((k) => [k.toLowerCase(), k]));
  for (const candidate of LABEL_KEYS) {
    const key = byLower.get(candidate);
    if (key == null) continue;
    const label = shortScalar(obj[key]);
    if (label != null) return { label, key };
  }
  const keys = Object.keys(obj);
  if (keys.length === 1) {
    const label = shortScalar(obj[keys[0]]);
    if (label != null) return { label, key: keys[0] };
  }
  return null;
}

/** "debaters_arguments" -> "Debaters arguments". */
export function humanizeKey(key: string): string {
  const text = key.replace(/[_-]+/g, " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : key;
}

/** Turn any JSON value into a readable display structure. */
export function toDisplayValue(value: unknown): DisplayValue {
  if (value == null) return { kind: "text", text: "—" };
  if (typeof value === "string") return { kind: "text", text: value };
  if (typeof value === "number" || typeof value === "boolean") {
    return { kind: "text", text: String(value) };
  }
  if (Array.isArray(value)) {
    return { kind: "list", items: value.map(toDisplayValue) };
  }
  if (isPlainObject(value)) {
    return {
      kind: "fields",
      fields: Object.entries(value).map(([key, v]) => ({
        key,
        label: humanizeKey(key),
        value: toDisplayValue(v),
      })),
    };
  }
  return { kind: "text", text: String(value) };
}

/**
 * Split a decision value into its pill label and readable body.
 *
 * @param decision the transcript decision's `decision` value
 * @param outputSchema the agreement `output_schema` (optionally wrapped)
 */
export function decisionDisplay(
  decision: unknown,
  outputSchema: unknown = null,
): DecisionDisplay {
  const value =
    typeof decision === "string" ? (parseJsonObject(decision) ?? decision) : decision;

  if (value == null || (typeof value === "string" && !value.trim())) {
    return { label: null, labelKey: null, body: null };
  }

  if (isPlainObject(value)) {
    const found = labelFromObject(value, outputSchema);
    const rest = Object.entries(value).filter(([key]) => key !== found?.key);
    const body =
      rest.length > 0 ? toDisplayValue(Object.fromEntries(rest)) : null;
    return { label: found?.label ?? null, labelKey: found?.key ?? null, body };
  }

  if (Array.isArray(value)) {
    return { label: null, labelKey: null, body: toDisplayValue(value) };
  }

  const label = shortScalar(value);
  if (label != null) return { label, labelKey: null, body: null };
  return { label: null, labelKey: null, body: toDisplayValue(value) };
}

/**
 * Readable body for an agent message whose text is just its structured JSON
 * (e.g. a schema-constrained judge reply). `null` when the message has prose
 * of its own or no structured object, so the text is shown as-is.
 */
export function structuredMessageBody(
  content: string,
  structured: unknown,
): DisplayValue | null {
  if (!isPlainObject(structured) || Object.keys(structured).length === 0) return null;
  if (!content.trim().startsWith("{")) return null;
  return toDisplayValue(structured);
}
