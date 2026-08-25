import { cssToNormalized, normalizedToCss } from "./geometry";
import { describe, expect, it } from "vitest";

describe("evidence locator transforms", () => {
  it("round-trips source-normalized coordinates through the browser overlay", () => {
    const source = [0.125, 0.25, 0.75, 0.875] as const;
    const css = normalizedToCss(source, 1600, 2400);
    expect(cssToNormalized(css, 1600, 2400)).toEqual(source);
  });

  it("rejects invalid regions instead of clamping", () => {
    expect(() => normalizedToCss([0.8, 0.2, 0.1, 0.9], 100, 100)).toThrow(
      "normalized_region_invalid",
    );
  });
});
