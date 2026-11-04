import { describe, expect, it } from "vitest";

import { innerSchema, makeSchemaStrict, schemaStrictness } from "./outputSchema";

/** Config 8 / execution 3's output_schema: the envelope, not strict. */
const INNER = {
  type: "object",
  properties: { class: { type: "string", enum: ["F", "NF"] } },
};
const ENVELOPE = {
  name: "requirements-schema",
  description: "A schema for classifying requirements into categories",
  schema: INNER,
};

describe("innerSchema (mirrors mad.output_schema)", () => {
  it("unwraps bare, envelope, and response_format shapes", () => {
    expect(innerSchema(INNER)).toBe(INNER);
    expect(innerSchema(ENVELOPE)).toBe(INNER);
    expect(innerSchema({ type: "json_schema", json_schema: ENVELOPE })).toBe(INNER);
    expect(innerSchema(null)).toBeNull();
  });
});

describe("schemaStrictness", () => {
  it("flags a missing required list and open objects", () => {
    expect(schemaStrictness(ENVELOPE)).toEqual({ missingRequired: true, allowsExtra: true });
    expect(schemaStrictness({ ...INNER, required: ["class"] })).toEqual({
      missingRequired: false,
      allowsExtra: true,
    });
    expect(
      schemaStrictness({ ...INNER, required: ["class"], additionalProperties: false }),
    ).toBeNull();
    expect(schemaStrictness(null)).toBeNull();
  });
});

describe("makeSchemaStrict", () => {
  it("closes the inner schema and keeps the envelope", () => {
    const strict = makeSchemaStrict(ENVELOPE);
    expect(strict).toEqual({
      ...ENVELOPE,
      schema: { ...INNER, required: ["class"], additionalProperties: false },
    });
    expect(schemaStrictness(strict)).toBeNull();
    // The input is not mutated.
    expect(ENVELOPE.schema).toBe(INNER);
    expect("required" in INNER).toBe(false);
  });

  it("closes nested objects and works on bare and response_format schemas", () => {
    const bare = {
      type: "object",
      properties: { meta: { type: "object", properties: { why: { type: "string" } } } },
    };
    expect(makeSchemaStrict(bare)).toEqual({
      type: "object",
      properties: {
        meta: {
          type: "object",
          properties: { why: { type: "string" } },
          required: ["why"],
          additionalProperties: false,
        },
      },
      required: ["meta"],
      additionalProperties: false,
    });
    const rf = makeSchemaStrict({ type: "json_schema", json_schema: ENVELOPE });
    expect(innerSchema(rf)).toMatchObject({ required: ["class"], additionalProperties: false });
    expect((rf.json_schema as Record<string, unknown>).name).toBe("requirements-schema");
  });
});
