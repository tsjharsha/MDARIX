import { describe, expect, it } from "vitest";
import { SECTIONS, lifecycleAction, statusTone, tenantOptionLabel, titleCase } from "./model";

describe("Customers & Tenants model", () => {
  it("has five sections instead of fourteen", () => {
    expect(SECTIONS).toEqual(["Customers", "Customer administrators", "Tenants", "Onboarding", "Feedback"]);
  });

  it("offers only the standing change that is valid", () => {
    expect(lifecycleAction("ACTIVE")).toBe("SUSPENDED");
    expect(lifecycleAction("suspended")).toBe("ACTIVE");
    // Provisioning, expired or archived customers have no one-click change (the server would refuse it).
    expect(lifecycleAction("PROVISIONED")).toBeNull();
    expect(lifecycleAction("ARCHIVED")).toBeNull();
    expect(lifecycleAction(undefined)).toBeNull();
  });

  it("colours a status by what it means for access", () => {
    expect(statusTone("ACTIVE")).toBe("good");
    expect(statusTone("INVITED")).toBe("warning");
    expect(statusTone("SUSPENDED")).toBe("critical");
    expect(statusTone("something-new")).toBe("neutral");
    expect(titleCase("CUSTOMER_ADMIN_ADDED")).toBe("Customer admin added");
  });

  it("names a tenant with its customer when tenants of several customers are listed together", () => {
    expect(
      tenantOptionLabel({ id: "1", tenant_key: "APEX-EU", tenant_name: "Europe Production", customer_name: "Apex" }),
    ).toBe("Apex · Europe Production (APEX-EU)");
    // A first tenant named like its customer is not repeated.
    expect(tenantOptionLabel({ id: "2", tenant_key: "APEX", tenant_name: "Apex", customer_name: "Apex" })).toBe(
      "Apex (APEX)",
    );
    expect(tenantOptionLabel({ id: "3", tenant_key: "BEACON", display_name: "Beacon" })).toBe("Beacon (BEACON)");
  });
});
