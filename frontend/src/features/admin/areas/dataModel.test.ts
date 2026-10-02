import { describe, expect, it } from "vitest";
import { RELEASE_STEPS, changePolicyLabel, mappingRuleCount, nextReleaseAction } from "./dataModel";

describe("data model labels", () => {
  it("names who may change a field", () => {
    expect(changePolicyLabel("PLATFORM_ONLY")).toBe("MDARIX only");
    expect(changePolicyLabel("RESTRICTED")).toBe("Customer, with approval");
    expect(changePolicyLabel("CUSTOMER_OVERRIDE_ALLOWED")).toBe("Customer");
    expect(changePolicyLabel(null)).toBe("—");
  });

  it("counts field rules in every stored shape", () => {
    expect(mappingRuleCount({ rules: [{}, {}] })).toBe(2);
    expect(mappingRuleCount({ _configuration: {}, complaint_number: {}, title: {} })).toBe(2);
    expect(mappingRuleCount({ fields: { a: {}, b: {}, c: {} } })).toBe(3);
    expect(mappingRuleCount(null)).toBe(0);
  });
});

describe("releases", () => {
  it("offers exactly one next step per status, matching the server's transitions", () => {
    expect(nextReleaseAction("DRAFT")?.action).toBe("REQUEST_APPROVAL");
    expect(nextReleaseAction("READY_FOR_APPROVAL")?.action).toBe("APPROVE");
    expect(nextReleaseAction("APPROVED")?.action).toBe("PROMOTE");
    expect(nextReleaseAction("RELEASED")?.action).toBe("ROLLBACK");
    // A rolled-back or unknown mapping has no button, so nothing is offered that the server refuses.
    expect(nextReleaseAction("SUPERSEDED")).toBeNull();
    expect(nextReleaseAction("SOMETHING_ELSE")).toBeNull();
  });

  it("places every status the server uses in one stage", () => {
    const statuses = RELEASE_STEPS.flatMap((step) => [...step.statuses]);
    expect(new Set(statuses).size).toBe(statuses.length);
    for (const status of ["DRAFT", "READY_FOR_APPROVAL", "APPROVED", "RELEASED", "SUPERSEDED"]) {
      expect(statuses).toContain(status);
    }
  });
});
