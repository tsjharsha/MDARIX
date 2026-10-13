import { describe, expect, it } from "vitest";
import { ApiError } from "../../../app/apiClient";
import {
  CUSTOMER_FIELD_GROUPS,
  SECTIONS,
  TENANT_FIELD_GROUPS,
  blockedByCustomer,
  changeErrorText,
  changedFields,
  customerGivesAccess,
  displayCode,
  customerStatusResult,
  formFrom,
  formProblems,
  isVersionConflict,
  lifecycleAction,
  lifecycleStatusLabel,
  presentGroups,
  reasonReady,
  statusAction,
  customerStatusAction,
  tenantStatusAction,
  statusTone,
  tenantActivationBlock,
  tenantOptionLabel,
  tenantsLosingAccess,
  titleCase,
} from "./model";

describe("Customers & Tenants model", () => {
  it("has five sections instead of fourteen", () => {
    expect(SECTIONS).toEqual(["Customers", "Tenants", "Trials", "Feedback"]);
  });

  it("offers only the standing change that is valid", () => {
    expect(lifecycleAction("ACTIVE")).toBe("SUSPENDED");
    expect(lifecycleAction("suspended")).toBe("ACTIVE");
    // A new customer is activated; terminated or archived ones have no one-click change.
    expect(lifecycleAction("PROVISIONED")).toBe("ACTIVE");
    expect(lifecycleAction("TERMINATED")).toBeNull();
    expect(lifecycleAction("ARCHIVED")).toBeNull();
    expect(lifecycleAction(undefined)).toBeNull();
  });

  it("names the status change Activate, Deactivate or Reactivate", () => {
    for (const status of ["DRAFT", "PENDING_APPROVAL", "PROVISIONING", "PROVISIONED", "PENDING_CUSTOMER_ACTIVATION"])
      expect(statusAction(status)).toEqual({ target: "ACTIVE", verb: "Activate" });
    expect(statusAction("ACTIVE")).toEqual({ target: "SUSPENDED", verb: "Deactivate" });
    expect(statusAction("EXPIRING_SOON")).toEqual({ target: "SUSPENDED", verb: "Deactivate" });
    expect(statusAction("SUSPENDED")).toEqual({ target: "ACTIVE", verb: "Reactivate" });
    expect(statusAction("EXPIRED")).toEqual({ target: "ACTIVE", verb: "Reactivate" });
    expect(statusAction("PURGING")).toBeNull();
    expect(statusAction("")).toBeNull();
  });

  it("calls a suspended customer or tenant inactive on these screens", () => {
    expect(lifecycleStatusLabel("SUSPENDED")).toBe("Inactive");
    expect(lifecycleStatusLabel("suspended")).toBe("Inactive");
    expect(lifecycleStatusLabel("PENDING_CUSTOMER_ACTIVATION")).toBe("Pending customer activation");
    expect(lifecycleStatusLabel(null)).toBe("Unknown");
  });

  it("lets a customer's own status gate its tenants", () => {
    expect(customerGivesAccess("ACTIVE")).toBe(true);
    expect(customerGivesAccess("EXPIRING_SOON")).toBe(true);
    expect(customerGivesAccess("SUSPENDED")).toBe(false);
    expect(customerGivesAccess("PROVISIONED")).toBe(false);
    expect(blockedByCustomer({ effective_access: "BLOCKED_BY_CUSTOMER" })).toBe(true);
    expect(blockedByCustomer({ effective_access: "BLOCKED" })).toBe(false);
    expect(blockedByCustomer(undefined)).toBe(false);
  });

  it("explains why a tenant cannot be activated under an inactive customer", () => {
    expect(tenantActivationBlock("Apex", "SUSPENDED")).toBe(
      "Its customer Apex is inactive; reactivate the customer first.",
    );
    expect(tenantActivationBlock("Apex", "PROVISIONED")).toBe(
      "Its customer Apex is not active yet; activate the customer first.",
    );
    expect(tenantActivationBlock("Apex", "ACTIVE")).toBeNull();
    // Without the customer's status the server decides.
    expect(tenantActivationBlock("Apex", undefined)).toBeNull();
  });

  it("counts the tenants a deactivation would close and names the ones it reached", () => {
    expect(tenantsLosingAccess([{ status: "ACTIVE" }, { status: "SUSPENDED" }, { status: "EXPIRING_SOON" }])).toBe(2);
    expect(
      customerStatusResult("Apex", "Deactivate", [
        { tenant_id: "1", name: "Apex EU", effective_access: "BLOCKED_BY_CUSTOMER" },
        { tenant_id: "2", name: "Apex US", effective_access: "BLOCKED_BY_CUSTOMER" },
      ]),
    ).toBe("Apex is inactive. Nobody can sign in to Apex EU, Apex US.");
    expect(
      customerStatusResult("Apex", "Reactivate", [
        { tenant_id: "1", name: "Apex EU", effective_access: "ACTIVE" },
        { tenant_id: "2", name: "Apex US", effective_access: "BLOCKED" },
      ]),
    ).toBe("Apex is active again. 1 of 2 tenants can be used again: Apex EU, Apex US.");
    expect(customerStatusResult("Apex", "Activate")).toBe("Apex is active. It has no tenants.");
  });

  it("colours a status by what it means for access", () => {
    expect(statusTone("ACTIVE")).toBe("good");
    expect(statusTone("INVITED")).toBe("warning");
    expect(statusTone("SUSPENDED")).toBe("critical");
    expect(statusTone("something-new")).toBe("neutral");
    expect(titleCase("CUSTOMER_ADMIN_ADDED")).toBe("Customer admin added");
  });

  it("keeps the spelling of known names and reads event names as words", () => {
    expect(displayCode("oidc")).toBe("OIDC");
    expect(displayCode("SAML")).toBe("SAML");
    expect(displayCode("openai")).toBe("OpenAI");
    expect(displayCode("TRACKWISE")).toBe("TrackWise");
    expect(displayCode("tenant.created")).toBe("Tenant created");
    expect(displayCode("PROVIDER_RECORD_RECEIVED")).toBe("Provider record received");
    expect(displayCode("rest_api")).toBe("REST API");
    expect(displayCode("MappingConfiguration")).toBe("Mapping configuration");
    expect(displayCode("Veeva Vault QMS")).toBe("Veeva Vault QMS");
    expect(displayCode(null)).toBe("");
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

describe("editing details", () => {
  const customer = {
    legal_name: "Apex Pharma Ltd",
    display_name: "Apex",
    trading_name: null,
    customer_type: "PHARMA",
    country: "UK",
    primary_business_contact: { name: "Ann", email: "ann@apex.example", phone: null },
    billing_contact: null,
    lock_version: 3,
  };

  it("sends nothing until a field changes", () => {
    const form = formFrom(customer, CUSTOMER_FIELD_GROUPS);
    expect(form.legal_name).toBe("Apex Pharma Ltd");
    expect(form["primary_business_contact.email"]).toBe("ann@apex.example");
    expect(changedFields(customer, form, CUSTOMER_FIELD_GROUPS)).toEqual({});
    // Spaces alone are not a change.
    expect(changedFields(customer, { ...form, display_name: " Apex " }, CUSTOMER_FIELD_GROUPS)).toEqual({});
  });

  it("sends only changed fields, an emptied optional field as null and a contact whole", () => {
    const form = formFrom(customer, CUSTOMER_FIELD_GROUPS);
    expect(
      changedFields(
        customer,
        { ...form, display_name: "Apex Group ", trading_name: "", "primary_business_contact.phone": "+44 1" },
        CUSTOMER_FIELD_GROUPS,
      ),
    ).toEqual({
      display_name: "Apex Group",
      primary_business_contact: { name: "Ann", email: "ann@apex.example", phone: "+44 1" },
    });
    expect(
      changedFields(
        customer,
        { ...form, "primary_business_contact.name": "", "primary_business_contact.email": "" },
        CUSTOMER_FIELD_GROUPS,
      ),
    ).toEqual({ primary_business_contact: null });
    expect(
      changedFields({ ...customer, trading_name: "Apex" }, { ...form, trading_name: "" }, CUSTOMER_FIELD_GROUPS),
    ).toEqual({ trading_name: null });
  });

  it("refuses an empty required field, a bad email and a contact without a name or email", () => {
    const form = formFrom(customer, CUSTOMER_FIELD_GROUPS);
    expect(formProblems(form, CUSTOMER_FIELD_GROUPS)).toEqual([]);
    expect(formProblems({ ...form, legal_name: " " }, CUSTOMER_FIELD_GROUPS)).toEqual(["Legal name is required."]);
    expect(formProblems({ ...form, "primary_business_contact.email": "not-an-email" }, CUSTOMER_FIELD_GROUPS)).toEqual([
      "Business contact email is not an email.",
    ]);
    expect(formProblems({ ...form, "billing_contact.phone": "+44 2" }, CUSTOMER_FIELD_GROUPS)).toEqual([
      "The billing contact needs a name and an email.",
    ]);
  });

  it("edits the tenant fields the server returns", () => {
    const tenant = { display_name: "Apex EU", name: "apex-eu", tenant_type: "STANDARD", primary_region: "EU" };
    const groups = presentGroups(tenant, TENANT_FIELD_GROUPS);
    expect(groups.map((group) => group.title)).toEqual(["Tenant", "Regions"]);
    expect(groups.flatMap((group) => group.fields.map((field) => field.key))).toEqual([
      "display_name",
      "name",
      "tenant_type",
      "primary_region",
    ]);
    const form = formFrom(tenant, groups);
    expect(changedFields(tenant, { ...form, tenant_type: "ENTERPRISE" }, groups)).toEqual({
      tenant_type: "ENTERPRISE",
    });
  });

  it("needs a reason of 10 to 1000 characters", () => {
    expect(reasonReady("too short")).toBe(false);
    expect(reasonReady("  Renewal update  ")).toBe(true);
    expect(reasonReady("x".repeat(1001))).toBe(false);
  });

  it("explains a failed change in plain words", () => {
    const fallback = "The details were not saved.";
    const conflict = new ApiError("Tenant changed", 409, "STALE_RECORD");
    expect(isVersionConflict(conflict)).toBe(true);
    expect(changeErrorText(conflict, "customer", fallback)).toBe(
      "Someone else changed this customer; reload to see their changes.",
    );
    expect(changeErrorText(new ApiError("x", 422, "NO_CHANGES"), "tenant", fallback)).toBe(
      "Nothing was changed. Edit a field before saving.",
    );
    expect(changeErrorText(new ApiError("x", 409, "OPERATOR_PROTECTED"), "customer", fallback)).toBe(
      "The MDARIX operator organization can't be deactivated.",
    );
    expect(isVersionConflict(new ApiError("x", 409, "CUSTOMER_NOT_ACTIVE"))).toBe(false);
    expect(
      changeErrorText(
        new ApiError("Cannot move ACTIVE to ACTIVE", 409, "INVALID_LIFECYCLE_TRANSITION"),
        "tenant",
        fallback,
      ),
    ).toBe("Cannot move ACTIVE to ACTIVE");
    // A wrong password keeps the server's own words.
    expect(
      changeErrorText(
        new ApiError("Current password is required", 403, "INVALID_REAUTHENTICATION"),
        "tenant",
        fallback,
      ),
    ).toBe("Current password is required");
  });
});

describe("status changes per record", () => {
  it("never offers to deactivate the MDARIX operator organization", () => {
    expect(customerStatusAction("ACTIVE", true)).toBeNull();
    expect(customerStatusAction("ACTIVE", false)).toEqual({ target: "SUSPENDED", verb: "Deactivate" });
    expect(customerStatusAction("SUSPENDED", true)).toEqual({ target: "ACTIVE", verb: "Reactivate" });
  });
  it("activates a tenant only once provisioning has finished", () => {
    for (const status of ["DRAFT", "PENDING_APPROVAL", "PROVISIONING"]) expect(tenantStatusAction(status)).toBeNull();
    for (const status of ["PROVISIONED", "PENDING_CUSTOMER_ACTIVATION"])
      expect(tenantStatusAction(status)).toEqual({ target: "ACTIVE", verb: "Activate" });
    expect(tenantStatusAction("SUSPENDED")).toEqual({ target: "ACTIVE", verb: "Reactivate" });
    expect(tenantStatusAction("ACTIVE")).toEqual({ target: "SUSPENDED", verb: "Deactivate" });
  });
});
