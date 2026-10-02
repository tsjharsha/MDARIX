import { describe, expect, it } from "vitest";
import { groupGaveUp } from "./Operations";

const item = (id: string, event: string, tenant: string, at: string) => ({
  id,
  event_name: event,
  aggregate_type: "Test",
  attempts: 5,
  last_error: "RuntimeError: delivery failed",
  occurred_at: at,
  dead_lettered_at: at,
  tenant_id: tenant,
  tenant_name: `Tenant ${tenant}`,
});

describe("work that gave up", () => {
  it("groups items of the same kind and tenant, largest group first, with the date range", () => {
    const groups = groupGaveUp([
      item("1", "FAIL", "a", "2026-09-22T10:00:00Z"),
      item("2", "FAIL", "b", "2026-09-26T10:00:00Z"),
      item("3", "FAIL", "a", "2026-09-25T10:00:00Z"),
      item("4", "PROVIDER_RECORD_RECEIVED", "a", "2026-09-28T10:00:00Z"),
    ]);
    expect(groups.map((group) => [group.event_name, group.tenant_name, group.count])).toEqual([
      ["FAIL", "Tenant a", 2],
      ["FAIL", "Tenant b", 1],
      ["PROVIDER_RECORD_RECEIVED", "Tenant a", 1],
    ]);
    expect(groups[0]).toMatchObject({ ids: ["1", "3"], first: "2026-09-22T10:00:00Z", last: "2026-09-25T10:00:00Z" });
  });
});
