import { formatDay } from "../../app/dates";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import {
  availableFieldKeys,
  fieldLabel,
  formatFieldValue,
  loadSelection,
  moveField,
  resolveSelection,
  saveSelection,
} from "./columnModel";

const UUID_1 = "6f1c2a9e-4b3d-4c8a-9f2e-1a2b3c4d5e6f";
const UUID_2 = "7a2d3b0f-5c4e-4d9b-8a3f-2b3c4d5e6f70";

const CUSTOMERS = [
  {
    id: UUID_1,
    business_id: "CUST000001",
    plan_id: UUID_2,
    name: "Apex",
    customer_identifier: "CUS0001",
    country: "IN",
    created_at: "2026-09-01T10:00:00Z",
    tenant_count: 2,
    regions: ["EU", "IN"],
    tenants: [{ id: "t1" }],
    password_hash: "x",
    can_suspend: true,
    lock_version: 3,
    actions: ["VIEW"],
    _internal: 1,
    notes: null,
  },
  {
    id: UUID_2,
    business_id: "CUST000002",
    name: "Beacon",
    customer_identifier: "CUS0002",
    country: null,
    notes: "VIP",
  },
];

describe("fields a list can offer", () => {
  it("offers plain fields and lists of plain values, never nested records, secrets, internal keys or UUIDs", () => {
    expect(availableFieldKeys(CUSTOMERS, ["name"])).toEqual([
      "business_id",
      "customer_identifier",
      "country",
      "created_at",
      "tenant_count",
      "regions",
      "notes",
    ]);
  });

  it("never offers a field that holds UUIDs, but keeps business IDs and readable keys", () => {
    const rows = [
      {
        id: UUID_1,
        tenant_id: UUID_2,
        tenant_business_id: "TEN000003",
        actor: UUID_2,
        source_id: "QMS-7",
        member_ids: [UUID_1],
        notes: "x",
      },
    ];
    expect(availableFieldKeys(rows)).toEqual(["tenant_business_id", "source_id", "notes"]);
  });

  it("names fields in words", () => {
    expect(fieldLabel("business_id")).toBe("ID");
    expect(fieldLabel("tenant_business_id")).toBe("Tenant ID");
    expect(fieldLabel("customer_identifier")).toBe("Customer identifier");
    expect(fieldLabel("created_at")).toBe("Created");
    expect(fieldLabel("tenant_id")).toBe("Tenant ID");
    expect(fieldLabel("source_ip")).toBe("Source IP");
  });

  it("shows values as a reader expects", () => {
    expect(formatFieldValue(null)).toBe("—");
    expect(formatFieldValue(UUID_1)).toBe("—");
    expect(formatFieldValue("CMP000002")).toBe("CMP000002");
    expect(formatFieldValue(true)).toBe("Yes");
    expect(formatFieldValue(["EU", "IN"])).toBe("EU, IN");
    expect(formatFieldValue("READY_FOR_APPROVAL")).toBe("Ready for approval");
    expect(formatFieldValue(42)).toBe("42");
    // Dates name the month (app/dates.ts), so day and month cannot be confused.
    expect(formatFieldValue("2026-09-01")).toBe(formatDay("2026-09-01"));
    expect(formatFieldValue("2026-09-01")).toMatch(/Sep|Aug/);
  });
});

describe("the chosen fields", () => {
  // The unit tests run without a browser: a small in-memory localStorage stands in for it.
  beforeAll(() => {
    const store = new Map<string, string>();
    const localStorage = {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
      removeItem: (key: string) => void store.delete(key),
      clear: () => store.clear(),
    };
    (globalThis as any).window ??= { localStorage };
  });
  afterEach(() => window.localStorage.clear());

  it("starts from the defaults and keeps a saved choice only for fields still available", () => {
    expect(resolveSelection(["a", "b"], ["a", "b", "c"], null)).toEqual(["a", "b"]);
    expect(resolveSelection(["a", "b"], ["a", "b", "c"], ["c", "a"])).toEqual(["c", "a"]);
    expect(resolveSelection(["a", "b"], ["a", "b"], ["gone"])).toEqual(["a", "b"]);
  });

  it("moves a field up or down, never past the ends", () => {
    expect(moveField(["a", "b", "c"], "c", -1)).toEqual(["a", "c", "b"]);
    expect(moveField(["a", "b", "c"], "a", -1)).toEqual(["a", "b", "c"]);
  });

  it("remembers the choice per list, and forgets it on reset", () => {
    saveSelection("admin:Customers", ["name", "country"]);
    expect(loadSelection("admin:Customers")).toEqual(["name", "country"]);
    expect(loadSelection("admin:Tenants")).toBeNull();
    saveSelection("admin:Customers", null);
    expect(loadSelection("admin:Customers")).toBeNull();
  });
});
