import { describe, expect, it } from "vitest";

import {
  DIMENSION_ORDER,
  DIMENSION_THEMES,
  getDimensionTheme,
} from "./dimensions";

describe("dimension theming tokens", () => {
  it("defines all three dimensions in paper order", () => {
    expect(DIMENSION_ORDER).toEqual([
      "participants",
      "interaction",
      "agreement",
    ]);
  });

  it("maps each dimension to its own badge variant and classes", () => {
    for (const key of DIMENSION_ORDER) {
      const theme = getDimensionTheme(key);
      expect(theme.key).toBe(key);
      expect(theme.badgeVariant).toBe(key);
      expect(theme.classes.text).toContain(key);
      expect(theme.label.length).toBeGreaterThan(0);
    }
  });

  it("gives each dimension a distinct icon identity", () => {
    const icons = DIMENSION_ORDER.map((k) => DIMENSION_THEMES[k].icon);
    expect(new Set(icons).size).toBe(3);
  });
});
