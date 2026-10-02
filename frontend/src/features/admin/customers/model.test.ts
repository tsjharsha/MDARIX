import { describe, expect, it } from "vitest";
import { SECTIONS, lifecycleAction, statusTone, titleCase } from "./model";

describe("Customers & Tenants model", () => {
  it("has four sections instead of fourteen", () => {
    expect(SECTIONS).toEqual(["Customers", "Customer administrators", "Tenants", "Onboarding"]);
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
});
