import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { ConfigDetail } from "@/api";
import {
  placeholdersFromTemplate,
  resolveTemplate,
  templateFields,
} from "@/features/executions/inputSpec";
import { useDesignerStore, withUiLayout } from "./designerStore";
import {
  isInputTemplateEmpty,
  placeholderRows,
  previewInput,
  starterInputSpec,
  withPlaceholderLabel,
  withTemplate,
} from "./inputEditor";

/**
 * Task 11.10: the input editor's pure rules (placeholder syntax mirroring the
 * backend `PLACEHOLDER_PATTERN`, label sync, preview) and the store actions
 * behind the designer header (name/description) and the Input panel.
 */

describe("placeholder syntax (mirrors backend PLACEHOLDER_PATTERN)", () => {
  it("detects tags in order, de-duplicated, ignoring spaces inside the braces", () => {
    expect(
      placeholdersFromTemplate("A {{a}} B {{ b }} again {{a}} and {{  a  }}"),
    ).toEqual(["a", "b"]);
  });

  it("accepts dots, hyphens, inner spaces and non-ASCII word characters", () => {
    expect(
      placeholdersFromTemplate(
        "{{row.text}} {{user-id}} {{Requirement Text}} {{título}} {{x_1}}",
      ),
    ).toEqual(["row.text", "user-id", "Requirement Text", "título", "x_1"]);
  });

  it("ignores malformed or empty tags", () => {
    expect(placeholdersFromTemplate("{{}} {{ }} {single} {{a/b}} {{a}")).toEqual([]);
  });

  it("resolves known tags and leaves unknown ones verbatim (lenient, like the engine)", () => {
    expect(resolveTemplate("Classify: {{ req }} ({{other}})", { req: "fast" })).toBe(
      "Classify: fast ({{other}})",
    );
    expect(resolveTemplate("", { a: "x" })).toBe("");
  });
});

describe("input spec sync", () => {
  it("re-detects placeholders and keeps surviving labels, defaults new ones, drops removed", () => {
    const spec = {
      template: "{{a}} {{b}}",
      placeholders: ["a", "b"],
      ad_hoc_fields: [
        { key: "a", label: "Alpha" },
        { key: "b", label: "Beta" },
      ],
      extra: 1,
    };
    const next = withTemplate(spec, "{{b}} then {{c}}");
    expect(next.template).toBe("{{b}} then {{c}}");
    expect(next.placeholders).toEqual(["b", "c"]);
    expect(next.ad_hoc_fields).toEqual([
      { key: "b", label: "Beta" },
      { key: "c", label: "c" },
    ]);
    // Unknown spec fields survive.
    expect(next.extra).toBe(1);
  });

  it("sets one placeholder's label, keeping the order and other labels", () => {
    const spec = withTemplate(undefined, "{{x}} {{y}}");
    const next = withPlaceholderLabel(spec, "y", "Why");
    expect(next.ad_hoc_fields).toEqual([
      { key: "x", label: "x" },
      { key: "y", label: "Why" },
    ]);
    expect(placeholderRows(next)).toEqual(next.ad_hoc_fields);
  });

  it("previews with sample values and flags an empty template", () => {
    expect(previewInput("Debate {{topic}}", { topic: "AI" })).toBe("Debate AI");
    expect(isInputTemplateEmpty({ input_spec: { template: "  \n" } })).toBe(true);
    expect(isInputTemplateEmpty({})).toBe(true);
    expect(isInputTemplateEmpty({ input_spec: starterInputSpec() })).toBe(false);
  });
});

function seed(inputSpec?: Record<string, unknown>) {
  useDesignerStore.getState().loadArtifact(8, {
    name: "Original",
    description: "",
    participants: { nodes: [{ id: "a", label: "A", roles: ["debater"] }] },
    interaction: { topology: { structure: "fully_connected", edges: [] } },
    ...(inputSpec ? { input_spec: inputSpec } : {}),
  });
}

describe("designer store: name/description and input edits", () => {
  beforeEach(() => seed({ template: "", placeholders: [], ad_hoc_fields: [] }));
  afterEach(() => useDesignerStore.setState({ artifact: null, layout: {}, selection: null }));

  it("updateMeta trims, marks dirty, and is saved in the artifact", () => {
    expect(useDesignerStore.getState().updateMeta({ name: "  Renamed  " })).toBe(true);
    const s = useDesignerStore.getState();
    expect(s.artifact!.name).toBe("Renamed");
    expect(s.dirty).toBe(true);
    useDesignerStore.getState().updateMeta({ description: "About it" });
    const saved = withUiLayout(
      useDesignerStore.getState().artifact!,
      useDesignerStore.getState().layout,
      {},
    );
    expect(saved.name).toBe("Renamed");
    expect(saved.description).toBe("About it");
  });

  it("updateMeta rejects an empty name without changing anything", () => {
    expect(useDesignerStore.getState().updateMeta({ name: "   " })).toBe(false);
    expect(useDesignerStore.getState().artifact!.name).toBe("Original");
    expect(useDesignerStore.getState().dirty).toBe(false);
  });

  it("an unchanged name is a no-op (stays clean)", () => {
    expect(useDesignerStore.getState().updateMeta({ name: "Original" })).toBe(true);
    expect(useDesignerStore.getState().dirty).toBe(false);
  });

  it("loading never rewrites a stored (even empty) input spec", () => {
    expect(useDesignerStore.getState().artifact!.input_spec).toEqual({
      template: "",
      placeholders: [],
      ad_hoc_fields: [],
    });
    expect(useDesignerStore.getState().dirty).toBe(false);
  });

  it("template/label edits feed the run launcher's fields", () => {
    useDesignerStore.getState().updateInputTemplate("Classify: {{ requirement }}");
    useDesignerStore.getState().updateInputLabel("requirement", "Requirement text");
    const s = useDesignerStore.getState();
    expect(s.dirty).toBe(true);
    expect(s.artifact!.input_spec).toEqual({
      template: "Classify: {{ requirement }}",
      placeholders: ["requirement"],
      ad_hoc_fields: [{ key: "requirement", label: "Requirement text" }],
    });
    const detail = {
      id: 8,
      name: s.artifact!.name,
      artifact: withUiLayout(s.artifact!, s.layout, s.edgeBends),
    } as unknown as ConfigDetail;
    expect(templateFields(detail)).toEqual([
      { key: "requirement", label: "Requirement text" },
    ]);
  });
});
