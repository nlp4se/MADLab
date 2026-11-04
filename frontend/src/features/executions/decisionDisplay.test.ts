import { describe, expect, it } from "vitest";

import {
  decisionDisplay,
  humanizeKey,
  innerSchema,
  outputSchemaFromSnapshot,
  singleEnumProperty,
  structuredMessageBody,
} from "./decisionDisplay";
import { EXEC3_DECISION, EXEC3_SCHEMA } from "./decisionFixtures";

describe("decisionDisplay", () => {
  it("shows a short string as the label with no body", () => {
    expect(decisionDisplay("NFR")).toEqual({ label: "NFR", labelKey: null, body: null });
    expect(decisionDisplay(3).label).toBe("3");
    expect(decisionDisplay(true).label).toBe("true");
  });

  it("uses the (wrapped) schema's enum property as the label", () => {
    expect(decisionDisplay({ class: "F" }, EXEC3_SCHEMA)).toEqual({
      label: "F",
      labelKey: "class",
      body: null,
    });
  });

  it("falls back to a known label key and lists the other fields (execution 3)", () => {
    const view = decisionDisplay(EXEC3_DECISION, EXEC3_SCHEMA);
    expect(view.label).toBe("Functional");
    expect(view.labelKey).toBe("final_classification");
    expect(view.body?.kind).toBe("fields");
    if (view.body?.kind !== "fields") throw new Error("expected fields");
    expect(view.body.fields.map((f) => f.label)).toEqual([
      "Requirement",
      "Debaters arguments",
      "Moderator evaluation",
    ]);
    const args = view.body.fields[1].value;
    expect(args.kind).toBe("list");
    if (args.kind === "list") expect(args.items).toHaveLength(2);
  });

  it("prefers the schema enum property over known keys, keys match case-insensitively", () => {
    const schema = {
      type: "object",
      properties: { category: { enum: ["F", "NF"] }, reason: { type: "string" } },
    };
    const obj = { reason: "Because.", Answer: "maybe", category: "NF" };
    expect(decisionDisplay(obj, schema).label).toBe("NF");
    expect(decisionDisplay(obj).label).toBe("maybe");
    expect(decisionDisplay(obj).labelKey).toBe("Answer");
  });

  it("has no label for a multi-field object without one", () => {
    const view = decisionDisplay({ summary: "A long summary.", risks: ["a", "b"] });
    expect(view.label).toBeNull();
    expect(view.body?.kind).toBe("fields");
  });

  it("puts long text into the body, not the label", () => {
    const text = "This requirement constrains how the system behaves rather than what it does.";
    expect(decisionDisplay(text)).toEqual({
      label: null,
      labelKey: null,
      body: { kind: "text", text },
    });
    // A long value under a label key is not a label either.
    expect(decisionDisplay({ decision: text, a: 1 }).label).toBeNull();
  });

  it("parses a JSON-object string (e.g. an undecided raw judge reply)", () => {
    expect(decisionDisplay('{"class": "MAYBE"}', EXEC3_SCHEMA).label).toBe("MAYBE");
  });

  it("returns nothing for an empty decision", () => {
    expect(decisionDisplay(null)).toEqual({ label: null, labelKey: null, body: null });
    expect(decisionDisplay("  ").label).toBeNull();
  });
});

describe("schema helpers", () => {
  it("unwraps the provider envelope and finds the enum property", () => {
    expect(innerSchema(EXEC3_SCHEMA)).toEqual(EXEC3_SCHEMA.schema);
    expect(singleEnumProperty(EXEC3_SCHEMA)).toBe("class");
    expect(singleEnumProperty({ type: "object", properties: { a: {}, b: {} } })).toBeNull();
    expect(singleEnumProperty({ type: "object", properties: { only: {} } })).toBe("only");
  });

  it("reads the output schema from a config snapshot", () => {
    expect(outputSchemaFromSnapshot({ agreement: { output_schema: EXEC3_SCHEMA } })).toBe(
      EXEC3_SCHEMA,
    );
    expect(outputSchemaFromSnapshot({ agreement: {} })).toBeNull();
    expect(outputSchemaFromSnapshot(null)).toBeNull();
  });

  it("humanizes keys", () => {
    expect(humanizeKey("debaters_arguments")).toBe("Debaters arguments");
    expect(humanizeKey("final-classification")).toBe("Final classification");
  });
});

describe("structuredMessageBody", () => {
  it("renders a JSON-only reply as fields and leaves prose alone", () => {
    expect(structuredMessageBody(JSON.stringify(EXEC3_DECISION), EXEC3_DECISION)?.kind).toBe(
      "fields",
    );
    expect(structuredMessageBody("The verdict is NFR.", { label: "NFR" })).toBeNull();
    expect(structuredMessageBody("{}", null)).toBeNull();
  });
});
