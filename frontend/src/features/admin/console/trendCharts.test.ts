import { describe, expect, it } from "vitest";
import { changeText, halfOverHalf } from "./trendCharts";

describe("dashboard trends", () => {
  it("compares the last half of a period with the half before it", () => {
    expect(halfOverHalf([1, 1, 2, 2])).toBe(100);
    expect(halfOverHalf([4, 4, 2, 2])).toBe(-50);
    expect(halfOverHalf([0, 0, 0, 0])).toBe(0);
    // Nothing before, something now: there is no percentage to show.
    expect(halfOverHalf([0, 0, 3, 1])).toBeNull();
  });

  it("states large changes as a multiple and growth from nothing as new", () => {
    expect(changeText(12)).toBe("12%");
    expect(changeText(-40)).toBe("40%");
    expect(changeText(1491)).toBe("16×");
    expect(changeText(null, true)).toBe("New");
    expect(changeText(null)).toBe("");
  });
});
