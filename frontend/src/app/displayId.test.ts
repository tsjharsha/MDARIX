import { describe, expect, it } from "vitest";
import { businessId, displayId, hideUuid, isUuid, referenceId, safeText, sourceId } from "./displayId";

const UUID = "6f1c2a9e-4b3d-4c8a-9f2e-1a2b3c4d5e6f";

describe("identifiers people see", () => {
  it("recognises a UUID in any case and with stray spaces, and nothing else", () => {
    expect(isUuid(UUID)).toBe(true);
    expect(isUuid(` ${UUID.toUpperCase()} `)).toBe(true);
    expect(isUuid("CMP000001")).toBe(false);
    expect(isUuid("6f1c2a9e")).toBe(false);
    expect(isUuid(42)).toBe(false);
    expect(isUuid(null)).toBe(false);
  });

  it("shows the MDARIX ID first", () => {
    expect(displayId({ id: UUID, business_id: "CMP000012", complaint_identifier: "ACD-CMP-0001" })).toBe("CMP000012");
    expect(businessId({ id: UUID, business_id: "CUST000001" })).toBe("CUST000001");
  });

  it("falls back to the source number, then the name, never the UUID", () => {
    expect(displayId({ id: UUID, complaint_identifier: "ACD-CMP-0001" }, "complaint_identifier")).toBe("ACD-CMP-0001");
    expect(displayId({ id: UUID, name: "Infusion pump" })).toBe("Infusion pump");
    expect(displayId({ id: UUID })).toBe("—");
    expect(displayId({ id: UUID }, undefined, "Investigation")).toBe("Investigation");
    expect(displayId(null)).toBe("—");
    // A UUID in a business_id or name field is still never shown.
    expect(displayId({ business_id: UUID, name: UUID, title: "Battery drain" })).toBe("Battery drain");
  });

  it("uses the named source field only when asked, so a parent's identifier is never shown as the record's", () => {
    expect(businessId({ id: UUID, customer_identifier: "CUST-414E" })).toBeNull();
    expect(businessId({ id: UUID, tenant_key: "acme-prod" }, "tenant_key")).toBe("acme-prod");
  });

  it("finds an imported record's own number", () => {
    expect(sourceId({ id: UUID, investigation_identifier: "INV-7" })).toBe("INV-7");
    expect(sourceId({ id: UUID, source_reference: "QMS-12" })).toBe("QMS-12");
    expect(sourceId({ id: UUID, lot_identifier: UUID })).toBeNull();
    expect(sourceId({ lot_identifier: "LOT-9", site_identifier: "S-1" }, "site_identifier")).toBe("S-1");
  });

  it("shows a referenced record by its <role>_business_id, then the given fallbacks", () => {
    const row = { investigation_id: UUID, investigation_business_id: "INV000003" };
    expect(referenceId(row, "investigation")).toBe("INV000003");
    expect(referenceId({ customer_id: UUID }, "customer", UUID, "CUST-414E")).toBe("CUST-414E");
    expect(referenceId({ tenant_id: UUID }, "tenant", UUID)).toBe("—");
  });

  it("puts a dash where a stray UUID would have been shown", () => {
    expect(hideUuid(UUID)).toBe("—");
    expect(hideUuid(UUID, "Former user")).toBe("Former user");
    expect(hideUuid("USR000004")).toBe("USR000004");
    expect(safeText("  ")).toBeNull();
    expect(safeText(0)).toBe("0");
  });
});
