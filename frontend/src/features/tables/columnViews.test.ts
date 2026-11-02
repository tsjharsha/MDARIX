import { describe, expect, it } from "vitest";
import { carryOverColumnChoices, columnScopeFor } from "./columnViews";

/** A browser's storage, in memory. */
function storage(entries: Record<string, string>) {
  const map = new Map(Object.entries(entries));
  return {
    map,
    get length() {
      return map.size;
    },
    key: (index: number) => [...map.keys()][index] ?? null,
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
    removeItem: (key: string) => void map.delete(key),
  };
}

describe("saved column choices survive (6.8)", () => {
  it("keeps each screen's lists under a stable view id", () => {
    expect(columnScopeFor("Complaints")).toBe("view:complaints");
    expect(columnScopeFor("My Work")).toBe("view:my-work");
    expect(columnScopeFor("Trust & Audit")).toBe("view:trust-audit");
  });

  it("carries the keys kept under the section's name over to the view id, once", () => {
    const saved = storage({
      "mdarix.columns.workspace:Complaints:Complaint list": '["product","status"]',
      "mdarix.columnLayout.workspace:My Work:Assigned to me": '{"widths":{"title":300}}',
      // A newer choice under the view id wins over the old one.
      "mdarix.columns.workspace:Records:Checks": '["old"]',
      "mdarix.columns.view:records:Checks": '["new"]',
      "mdarix.columns.customer-admin:Users:Users": '["email"]',
      "mdarix.other": "1",
    });
    expect(carryOverColumnChoices(saved)).toBe(3);
    expect(Object.fromEntries(saved.map)).toEqual({
      "mdarix.columns.view:complaints:Complaint list": '["product","status"]',
      "mdarix.columnLayout.view:my-work:Assigned to me": '{"widths":{"title":300}}',
      "mdarix.columns.view:records:Checks": '["new"]',
      "mdarix.columns.customer-admin:Users:Users": '["email"]',
      "mdarix.other": "1",
    });
    expect(carryOverColumnChoices(saved)).toBe(0);
  });

  it("does nothing, and breaks nothing, when storage refuses", () => {
    const refusing = {
      get length(): number {
        throw new Error("SecurityError");
      },
      key: () => null,
      getItem: () => null,
      setItem: () => undefined,
      removeItem: () => undefined,
    };
    expect(carryOverColumnChoices(refusing)).toBe(0);
  });
});
