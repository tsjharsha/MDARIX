import { describe, expect, it } from "vitest";
import { customerAttention, roleMix, seatUsage, userStatusSlices } from "./customerAdminModel";

describe("customer admin overview model", () => {
  it("groups users by status in lifecycle order", () => {
    const slices = userStatusSlices([
      { id: "1", status: "SUSPENDED" },
      { id: "2", status: "ACTIVE" },
      { id: "3", status: "invited" },
      { id: "4", status: "ACTIVE" },
    ]);
    expect(slices.map((slice) => [slice.label, slice.count, slice.tone])).toEqual([
      ["Active", 2, "good"],
      ["Invited", 1, "neutral"],
      ["Suspended", 1, "serious"],
    ]);
  });

  it("ignores offboarded users in the role mix", () => {
    const mix = roleMix([
      { id: "1", role: "VIEWER", status: "ACTIVE" },
      { id: "2", role: "VIEWER", status: "OFFBOARDED" },
      { id: "3", role: "CUSTOMER_ADMIN", status: "ACTIVE" },
    ]);
    expect(mix.map((slice) => [slice.label, slice.count])).toEqual([
      ["Customer Admin", 1],
      ["Viewer", 1],
    ]);
  });

  it("grades seat usage and never invents a limit", () => {
    expect(seatUsage(5, null)).toMatchObject({ limit: null, tone: "neutral" });
    expect(seatUsage(7, 10).tone).toBe("good");
    expect(seatUsage(8, 10).tone).toBe("warning");
    expect(seatUsage(9, 10).tone).toBe("serious");
    expect(seatUsage(11, 10).tone).toBe("critical");
  });

  it("routes each attention item to the section that fixes it, most severe first", () => {
    const items = customerAttention({
      alerts: [{ code: "MAPPING_ISSUES", label: "Mappings to review", count: 2, severity: "MEDIUM" }],
      users: [{ id: "1", status: "SUSPENDED" }],
      failedRuns: 1,
      seats: seatUsage(9, 10),
      daysToExpiry: 90,
    });
    expect(items.map((item) => [item.tone, item.section])).toEqual([
      ["critical", "Integrations"],
      ["serious", "Users"],
      ["serious", "Plan & Subscription"],
      ["warning", "Data Mapping"],
    ]);
  });
});
