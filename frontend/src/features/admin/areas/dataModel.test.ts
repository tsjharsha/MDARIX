import { describe, expect, it } from "vitest";
import {
  RELEASE_STEPS,
  changePolicyLabel,
  entityCodeFor,
  mappingRuleCount,
  nextReleaseAction,
  validationMessage,
} from "./dataModel";

const ENTITIES = [
  { entity_id: "PRODUCT_VERSION", entity_name: "Product Version" },
  { entity_id: "COMPLAINT", entity_name: "Complaint" },
];

describe("data model labels", () => {
  it("names who may change a field", () => {
    expect(changePolicyLabel("PLATFORM_ONLY")).toBe("MDARIX only");
    expect(changePolicyLabel("RESTRICTED")).toBe("Customer, with approval");
    expect(changePolicyLabel("CUSTOMER_OVERRIDE_ALLOWED")).toBe("Customer");
    expect(changePolicyLabel(null)).toBe("—");
  });

  it("finds the data-model record for a mapping target written as a code or a name", () => {
    // "ProductVersion" used to be sent as PRODUCTVERSION and was not found.
    expect(entityCodeFor("ProductVersion", ENTITIES)).toBe("PRODUCT_VERSION");
    expect(entityCodeFor("Product Version", ENTITIES)).toBe("PRODUCT_VERSION");
    expect(entityCodeFor("Complaint", ENTITIES)).toBe("COMPLAINT");
    expect(entityCodeFor("Unknown", ENTITIES)).toBe("");
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

  it("explains validation findings in words", () => {
    expect(validationMessage({ code: "PROTECTED_FIELD", target: "tenant_id" })).toMatch(/set by MDARIX/);
    expect(validationMessage({ code: "INVALID_TRANSFORM", transform: "TRIM" })).toMatch(/not an approved/);
  });
});
