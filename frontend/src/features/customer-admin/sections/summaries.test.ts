import { describe, expect, it } from "vitest";
import { slicesBy } from "./summaries";

describe("page summaries", () => {
  it("counts rows by a field, largest first, with readable labels", () => {
    const rows = [{ status: "ACTIVE" }, { status: "DRAFT" }, { status: "ACTIVE" }, { status: null }];
    expect(slicesBy(rows, (row) => row.status)).toEqual([
      { key: "ACTIVE", label: "Active", count: 2, tone: "neutral" },
      { key: "DRAFT", label: "Draft", count: 1, tone: "neutral" },
      { key: "Not set", label: "Not set", count: 1, tone: "neutral" },
    ]);
  });

  it("treats values that differ only in case as one group", () => {
    const rows = [{ entity: "Complaint" }, { entity: "COMPLAINT" }, { entity: "Lot" }];
    expect(
      slicesBy(
        rows,
        (row) => row.entity,
        (value) => value,
      ).map(({ label, count }) => [label, count]),
    ).toEqual([
      ["Complaint", 2],
      ["Lot", 1],
    ]);
  });

  it("folds everything beyond the sixth bar into Other", () => {
    const rows = ["A", "B", "C", "D", "E", "F", "G", "G"].map((source) => ({ source }));
    const slices = slicesBy(
      rows,
      (row) => row.source,
      (value) => value,
    );
    expect(slices).toHaveLength(6);
    expect(slices[0]).toMatchObject({ label: "G", count: 2 });
    expect(slices[5]).toMatchObject({ label: "Other", count: 2 });
    expect(slices.reduce((total, slice) => total + slice.count, 0)).toBe(rows.length);
  });
});
