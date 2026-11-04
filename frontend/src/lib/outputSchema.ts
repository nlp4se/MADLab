/**
 * The agreement `output_schema`, normalized like the backend (task 11.13).
 *
 * Mirrors `backend/mad/output_schema.py`: the schema may be bare
 * (`{type, properties}`), the OpenAI envelope (`{name, description, schema}`),
 * or a whole `response_format` (`{type: "json_schema", json_schema: {...}}`).
 * `innerSchema` returns the JSON schema proper, used for label lookup in the
 * execution views and for the designer's strictness warning.
 */

type PlainObject = Record<string, unknown>;

function isPlainObject(value: unknown): value is PlainObject {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

/** A `{name?, description?, schema: {...}}` wrapper rather than a schema. */
function isEnvelope(value: PlainObject): boolean {
  return isPlainObject(value["schema"]) && !("properties" in value) && !("type" in value);
}

/** The wrapper level holding `schema` (envelope or response_format), if any. */
function envelopeOf(schema: PlainObject): PlainObject | null {
  let value = schema;
  if (value["type"] === "json_schema" && isPlainObject(value["json_schema"])) {
    value = value["json_schema"];
  }
  return isEnvelope(value) ? value : null;
}

/** Unwrap the provider envelope / response_format to the JSON schema proper. */
export function innerSchema(schema: unknown): PlainObject | null {
  if (!isPlainObject(schema)) return null;
  const envelope = envelopeOf(schema);
  if (envelope) return envelope["schema"] as PlainObject;
  if (schema["type"] === "json_schema" && isPlainObject(schema["json_schema"])) {
    return schema["json_schema"];
  }
  return schema;
}

function isObjectSchema(schema: PlainObject): boolean {
  const kind = schema["type"];
  return (
    kind === "object" ||
    (Array.isArray(kind) && kind.includes("object")) ||
    "properties" in schema
  );
}

export interface SchemaStrictness {
  /** The object schema has properties but no `required` list (or an empty one). */
  missingRequired: boolean;
  /** The object schema does not set `additionalProperties: false`. */
  allowsExtra: boolean;
}

/**
 * Strictness gaps of the (unwrapped) output schema's root object, or `null`
 * when there is nothing to flag (no schema, not an object schema, or strict).
 */
export function schemaStrictness(schema: unknown): SchemaStrictness | null {
  const inner = innerSchema(schema);
  if (!inner || !isObjectSchema(inner)) return null;
  const required = inner["required"];
  const missingRequired = !Array.isArray(required) || required.length === 0;
  const allowsExtra = inner["additionalProperties"] !== false;
  return missingRequired || allowsExtra ? { missingRequired, allowsExtra } : null;
}

/** Close one schema (and its nested object schemas) — returns a copy. */
function strictCopy(schema: unknown): unknown {
  if (Array.isArray(schema)) return schema.map(strictCopy);
  if (!isPlainObject(schema)) return schema;
  const out: PlainObject = { ...schema };
  const props = isPlainObject(schema["properties"]) ? schema["properties"] : null;
  if (props) {
    out["properties"] = Object.fromEntries(
      Object.entries(props).map(([k, v]) => [k, strictCopy(v)]),
    );
  }
  for (const key of ["items", "anyOf", "oneOf", "allOf"]) {
    if (key in schema) out[key] = strictCopy(schema[key]);
  }
  if (isObjectSchema(schema)) {
    out["required"] = Object.keys(props ?? {});
    out["additionalProperties"] = false;
  }
  return out;
}

/**
 * "Make strict": every object schema requires all its properties and sets
 * `additionalProperties: false`. The envelope (name, description, ...) is
 * kept as-is around the updated inner schema.
 */
export function makeSchemaStrict(schema: PlainObject): PlainObject {
  const envelope = envelopeOf(schema);
  if (!envelope) {
    if (schema["type"] === "json_schema" && isPlainObject(schema["json_schema"])) {
      return { ...schema, json_schema: strictCopy(schema["json_schema"]) };
    }
    return strictCopy(schema) as PlainObject;
  }
  const strictEnvelope = { ...envelope, schema: strictCopy(envelope["schema"]) };
  return envelope === schema ? strictEnvelope : { ...schema, json_schema: strictEnvelope };
}
