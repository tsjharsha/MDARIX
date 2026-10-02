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

const CUSTOMERS = [
  {
    id: "1",
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
  { id: "2", name: "Beacon", customer_identifier: "CUS0002", country: null, notes: "VIP" },
];

describe("fields a list can offer", () => {
  it("offers plain fields and lists of plain values, never nested records, secrets or internal keys", () => {
    expect(availableFieldKeys(CUSTOMERS, ["name"])).toEqual([
      "id",
      "customer_identifier",
      "country",
      "created_at",
      "tenant_count",
      "regions",
      "notes",
    ]);
  });

  it("names fields in words", () => {
    expect(fieldLabel("customer_identifier")).toBe("Customer identifier");
    expect(fieldLabel("created_at")).toBe("Created");
    expect(fieldLabel("tenant_id")).toBe("Tenant ID");
    expect(fieldLabel("source_ip")).toBe("Source IP");
  });

  it("shows values as a reader expects", () => {
    expect(formatFieldValue(null)).toBe("—");
    expect(formatFieldValue(true)).toBe("Yes");
    expect(formatFieldValue(["EU", "IN"])).toBe("EU, IN");
    expect(formatFieldValue("READY_FOR_APPROVAL")).toBe("Ready for approval");
    expect(formatFieldValue(42)).toBe("42");
    expect(formatFieldValue("2026-09-01")).toBe(new Date("2026-09-01").toLocaleDateString());
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
