import { describe, expect, it } from "vitest";

import { providerColor, roleColor } from "./nodeStyle";

describe("nodeStyle — role colours", () => {
  it("gives known roles distinct colours", () => {
    const debater = roleColor("debater").solid;
    const judge = roleColor("judge").solid;
    const summarizer = roleColor("summarizer").solid;
    expect(new Set([debater, judge, summarizer]).size).toBe(3);
  });

  it("strips the custom: prefix and is stable for custom roles", () => {
    const a = roleColor("custom:moderator").solid;
    const b = roleColor("custom:moderator").solid;
    expect(a).toBe(b); // deterministic
    expect(a).toMatch(/^#/);
  });

  it("is case-insensitive", () => {
    expect(roleColor("Judge").solid).toBe(roleColor("judge").solid);
  });
});

describe("nodeStyle — provider colours", () => {
  it("gives known providers distinct colours", () => {
    const openai = providerColor("openai").solid;
    const anthropic = providerColor("anthropic").solid;
    const ollama = providerColor("ollama").solid;
    expect(new Set([openai, anthropic, ollama]).size).toBe(3);
  });

  it("loosely matches a display name to a known provider", () => {
    expect(providerColor("OpenAI (prod)").solid).toBe(
      providerColor("openai").solid,
    );
  });

  it("falls back to a stable colour for an unknown provider", () => {
    const a = providerColor("some-local-thing").solid;
    const b = providerColor("some-local-thing").solid;
    expect(a).toBe(b);
    expect(a).toMatch(/^#/);
  });
});
