import { describe, expect, it } from "vitest";
import { decisionActionsOf, reviewDispositions } from "./DecisionCenterView";

const all = { can_review: true, can_approve: true, can_sign: true, reason: null };

describe("decision center actions", () => {
  it("offers Approve only to someone the server allows to approve, and never preselects a disposition", () => {
    expect(reviewDispositions(all)).toEqual(["APPROVED", "REJECTED", "REQUIRES_ADDITIONAL_EVIDENCE"]);
    expect(reviewDispositions({ ...all, can_approve: false })).toEqual(["REJECTED", "REQUIRES_ADDITIONAL_EVIDENCE"]);
  });

  it("offers no review to someone who may not review (for example the decision's author)", () => {
    expect(reviewDispositions({ ...all, can_review: false, can_approve: false })).toEqual([]);
  });

  it("offers nothing when the server did not say what the user may do", () => {
    const none = decisionActionsOf({ id: "0d3c1a2b-0000-0000-0000-000000000000" });
    expect(none).toMatchObject({ can_review: false, can_approve: false, can_sign: false });
    expect(decisionActionsOf(null).can_sign).toBe(false);
    expect(decisionActionsOf({ id: "d-1", actions: all })).toBe(all);
  });
});
