import { describe, expect, it } from "vitest";
import { matchingComplaints, reasonHint, withRequestedComplaint } from "./Investigations";

const complaints = Array.from({ length: 120 }, (_, index) => ({
  id: `c-${index}`,
  business_id: `CMP${String(index + 1).padStart(6, "0")}`,
  complaint_identifier: `ACD-CMP-${String(index).padStart(3, "0")}`,
  description: index === 99 ? "Occlusion alarm during infusion" : "Battery drains overnight",
}));

describe("open-investigation complaint picker", () => {
  it("shows 50 at a time and finds the others by search", () => {
    expect(matchingComplaints(complaints, "", []).shown).toHaveLength(50);
    expect(matchingComplaints(complaints, "", []).total).toBe(120);
    const found = matchingComplaints(complaints, "occlusion", []);
    expect(found.total).toBe(1);
    expect(found.shown[0].complaint_identifier).toBe("ACD-CMP-099");
    expect(matchingComplaints(complaints, "acd-cmp-110", []).shown.map((row) => row.id)).toEqual(["c-110"]);
  });

  it("finds a complaint by its MDARIX ID", () => {
    expect(matchingComplaints(complaints, "cmp000111", []).shown.map((row) => row.id)).toEqual(["c-110"]);
  });

  it("keeps ticked complaints in view while searching for others", () => {
    const found = matchingComplaints(complaints, "occlusion", ["c-5"]);
    expect(found.shown.map((row) => row.id)).toEqual(["c-5", "c-99"]);
  });
});

describe("complaint an investigation was requested for", () => {
  const requested = {
    id: "c-200",
    business_id: "CMP000201",
    complaint_identifier: "ACD-CMP-200",
    description: "Pump stops mid-infusion",
  };

  it("is offered first when the selected version's list does not hold it", () => {
    const offered = withRequestedComplaint(complaints, requested);
    expect(offered).toHaveLength(121);
    expect(offered[0]).toMatchObject({ id: "c-200", business_id: "CMP000201" });
  });

  it("is not repeated when the list already holds it, and nothing changes without a request", () => {
    expect(withRequestedComplaint(complaints, { ...requested, id: "c-7" })).toBe(complaints);
    expect(withRequestedComplaint(complaints, null)).toBe(complaints);
  });

  it("stays in view, ticked, while the picker shows another page or a search", () => {
    const offered = withRequestedComplaint(complaints, { ...requested, id: "c-110" });
    expect(matchingComplaints(offered, "", ["c-110"]).shown.map((row) => row.id)).toContain("c-110");
    expect(matchingComplaints(offered, "occlusion", ["c-110"]).shown.map((row) => row.id)).toEqual(["c-110", "c-99"]);
    const extra = withRequestedComplaint(complaints, requested);
    expect(matchingComplaints(extra, "occlusion", ["c-200"]).shown.map((row) => row.id)).toEqual(["c-200", "c-99"]);
  });
});

describe("manage-case reason", () => {
  it("says how many characters are still needed before the change buttons work", () => {
    expect(reasonHint("short")).toBe("Write a reason of at least 10 characters to enable the changes below (5 more).");
    expect(reasonHint("  long enough reason ")).toBe("The reason is recorded with the change.");
  });
});
