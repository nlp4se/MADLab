import { describe, expect, it } from "vitest";

import { defaultFamily, effectiveFamily, isMixedKind } from "./providerFamily";
import { PROVIDER_KINDS } from "./types";

describe("provider kind -> family (task 11.9)", () => {
  it("fixed kinds always map to one family, ignoring a stored value", () => {
    for (const kind of ["openai", "anthropic", "gemini"] as const) {
      expect(isMixedKind(kind)).toBe(false);
      expect(effectiveFamily(kind, "open_weight")).toBe("closed_weight");
    }
    for (const kind of ["ollama", "vllm", "deepseek"] as const) {
      expect(isMixedKind(kind)).toBe(false);
      expect(effectiveFamily(kind, "closed_weight")).toBe("open_weight");
    }
  });

  it("mixed kinds use the stored value, else their default", () => {
    expect(isMixedKind("mistral")).toBe(true);
    expect(isMixedKind("openai_compatible")).toBe(true);
    expect(defaultFamily("mistral")).toBe("closed_weight");
    expect(defaultFamily("openai_compatible")).toBe("open_weight");
    expect(effectiveFamily("mistral", "open_weight")).toBe("open_weight");
    expect(effectiveFamily("openai_compatible", null)).toBe("open_weight");
  });

  it("covers every supported kind", () => {
    for (const kind of PROVIDER_KINDS) {
      expect(["open_weight", "closed_weight"]).toContain(defaultFamily(kind));
    }
  });
});
