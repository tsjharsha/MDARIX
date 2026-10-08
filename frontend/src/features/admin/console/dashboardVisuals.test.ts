import { describe, expect, it } from "vitest";
import { busyness, cumulative, foldShares, pulseSeconds } from "./dashboardVisuals";

describe("dashboard visuals", () => {
  it("moves busier flows faster, within 1.4 to 6 seconds a crossing", () => {
    expect(pulseSeconds(1)).toBe(1.4);
    expect(pulseSeconds(0)).toBe(6);
    expect(pulseSeconds(5)).toBe(1.4);
    expect(pulseSeconds(0.5)).toBeGreaterThan(1.4);
  });

  it("measures how busy a flow is against the busiest, keeping small flows visible", () => {
    expect(busyness(0, 10)).toBe(0);
    expect(busyness(10, 10)).toBe(1);
    expect(busyness(0.01, 1000)).toBe(0.12);
    expect(busyness(25, 100)).toBeCloseTo(0.5);
  });

  it("keeps at most six slices, largest first, folding the rest into Other", () => {
    const shares = foldShares(
      Array.from({ length: 8 }, (_, index) => ({ key: `k${index}`, label: `L${index}`, count: index + 1 })),
    );
    expect(shares).toHaveLength(6);
    expect(shares[0].count).toBe(8);
    expect(shares[5]).toEqual({ key: "__other", label: "Other", count: 1 + 2 + 3 });
    expect(foldShares([{ key: "a", label: "A", count: 0 }])).toEqual([]);
  });

  it("turns daily additions into a running count that ends at today's total", () => {
    const points = [
      { date: "2026-10-01", label: "Oct 1", primary: 1 },
      { date: "2026-10-02", label: "Oct 2", primary: 0 },
      { date: "2026-10-03", label: "Oct 3", primary: 2 },
    ];
    expect(cumulative(points, 10).map((point) => point.primary)).toEqual([8, 8, 10]);
    expect(cumulative(points, 1).map((point) => point.primary)).toEqual([1, 1, 3]);
  });
});
