import { describe, expect, it } from "vitest";
import { compareValues, nextSort, sortRows } from "./tableSort";

const byId = (ids: string[], direction: "ascending" | "descending") =>
  sortRows(
    ids.map((id) => ({ business_id: id })),
    { key: "business_id", direction },
    (row, key) => row[key as "business_id"],
  ).map((row) => row.business_id);

describe("click-to-sort", () => {
  it("sorts business IDs by their number (CMP000002 before CMP000010)", () => {
    expect(byId(["CMP000010", "CMP000002", "CMP000100", "CMP000001"], "ascending")).toEqual([
      "CMP000001",
      "CMP000002",
      "CMP000010",
      "CMP000100",
    ]);
    expect(byId(["CMP000010", "CMP000002", "CMP000100"], "descending")).toEqual([
      "CMP000100",
      "CMP000010",
      "CMP000002",
    ]);
    expect(compareValues("CUST000002", "CUST000010")).toBeLessThan(0);
  });

  it("keeps rows without an ID last in either direction", () => {
    expect(byId(["CMP000002", "—", "CMP000001"], "ascending")).toEqual(["CMP000001", "CMP000002", "—"]);
    expect(byId(["CMP000002", "—", "CMP000001"], "descending")).toEqual(["CMP000002", "CMP000001", "—"]);
  });

  it("cycles ascending, descending, then the server's order", () => {
    const first = nextSort(null, "business_id");
    expect(first).toEqual({ key: "business_id", direction: "ascending" });
    const second = nextSort(first, "business_id");
    expect(second).toEqual({ key: "business_id", direction: "descending" });
    expect(nextSort(second, "business_id")).toBeNull();
  });
});
