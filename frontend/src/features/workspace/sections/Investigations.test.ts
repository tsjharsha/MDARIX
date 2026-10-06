import { describe, expect, it } from "vitest";
import { matchingComplaints, reasonHint } from "./Investigations";

const complaints = Array.from({ length: 120 }, (_, index) => ({
  id: `c-${index}`,
  complaint_identifier: `CMP-${String(index).padStart(3, "0")}`,
  description: index === 99 ? "Occlusion alarm during infusion" : "Battery drains overnight",
}));

describe("open-investigation complaint picker", () => {
  it("shows 50 at a time and finds the others by search", () => {
    expect(matchingComplaints(complaints, "", []).shown).toHaveLength(50);
    expect(matchingComplaints(complaints, "", []).total).toBe(120);
    const found = matchingComplaints(complaints, "occlusion", []);
    expect(found.total).toBe(1);
    expect(found.shown[0].complaint_identifier).toBe("CMP-099");
    expect(matchingComplaints(complaints, "cmp-110", []).shown.map((row) => row.id)).toEqual(["c-110"]);
  });

  it("keeps ticked complaints in view while searching for others", () => {
    const found = matchingComplaints(complaints, "occlusion", ["c-5"]);
    expect(found.shown.map((row) => row.id)).toEqual(["c-5", "c-99"]);
  });
});

describe("manage-case reason", () => {
  it("says how many characters are still needed before the change buttons work", () => {
    expect(reasonHint("short")).toBe("Write a reason of at least 10 characters to enable the changes below (5 more).");
    expect(reasonHint("  long enough reason ")).toBe("The reason is recorded with the change.");
  });
});
