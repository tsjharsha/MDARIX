import { describe, expect, it } from "vitest";
import { columnSortValue, idColumn, matches, referenceIdColumn, sourceIdColumn } from "./shared";

const UUID = "6f1c2a9e-4b3d-4c8a-9f2e-1a2b3c4d5e6f";
const complaint = { id: UUID, business_id: "CMP000010", complaint_identifier: "ACD-CMP-0001" };

describe("ID columns", () => {
  it("shows and sorts by the MDARIX ID, labelled for the object", () => {
    const column = idColumn("Complaint ID", "complaint_identifier");
    expect(column.label).toBe("Complaint ID");
    expect(column.render(complaint)).toBe("CMP000010");
    expect(columnSortValue(column, complaint)).toBe("CMP000010");
  });

  it("falls back to the named source number, else a dash, never the UUID", () => {
    expect(idColumn("Complaint ID", "complaint_identifier").render({ id: UUID, complaint_identifier: "ACD-1" })).toBe(
      "ACD-1",
    );
    expect(idColumn("User ID").render({ id: UUID, display_name: "Asha" })).toBe("—");
  });

  it("shows the customer system's number as the Source ID", () => {
    const column = sourceIdColumn("complaint_identifier");
    expect(column.label).toBe("Source ID");
    expect(column.render(complaint)).toBe("ACD-CMP-0001");
    expect(column.render({ complaint_identifier: UUID })).toBe("—");
  });

  it("shows a referenced record by its <role>_business_id", () => {
    const column = referenceIdColumn("Subscription ID", "subscription");
    expect(column.render({ subscription_id: UUID, subscription_business_id: "SUB000004" })).toBe("SUB000004");
    expect(column.render({ subscription_id: UUID })).toBe("—");
  });
});

describe("search", () => {
  it("finds a record by its MDARIX ID", () => {
    expect(matches(complaint, "cmp000010")).toBe(true);
    expect(matches(complaint, "acd-cmp")).toBe(true);
    expect(matches(complaint, "CMP000011")).toBe(false);
  });
});
