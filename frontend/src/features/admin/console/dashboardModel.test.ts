import { describe, expect, it } from "vitest";
import {
  attentionItems,
  dailyCounts,
  expiryBuckets,
  healthSignals,
  planMix,
  runOutcomes,
  tenantStatusSlices,
  worstTone,
} from "./dashboardModel";

describe("platform admin dashboard model", () => {
  it("groups tenants by lifecycle status in a stable order with status tones", () => {
    const slices = tenantStatusSlices([
      { status: "SUSPENDED" },
      { status: "ACTIVE" },
      { status: "active" },
      { status: "PROVISIONING" },
      { status: null },
    ]);
    expect(slices.map((slice) => [slice.label, slice.count, slice.tone])).toEqual([
      ["Active", 2, "good"],
      ["Provisioning", 1, "neutral"],
      ["Suspended", 1, "serious"],
      ["Unknown", 1, "neutral"],
    ]);
  });

  it("places each subscription in exactly one expiry window", () => {
    const buckets = expiryBuckets([
      { tenant_id: "a", status: "EXPIRED", days_remaining: 12 },
      { tenant_id: "b", status: "ACTIVE", days_remaining: 3 },
      { tenant_id: "c", status: "ACTIVE", days_remaining: 30 },
      { tenant_id: "d", status: "ACTIVE", days_remaining: 61 },
      { tenant_id: "e", status: "ACTIVE", days_remaining: 400 },
    ]);
    expect(buckets.map((bucket) => bucket.count)).toEqual([1, 1, 1, 1, 1]);
  });

  it("counts events per UTC day and keeps empty days at zero", () => {
    const series = dailyCounts(
      ["2026-09-30T10:00:00Z", "2026-09-30T23:59:00Z", "2026-09-28T01:00:00Z", "2026-08-01T00:00:00Z", null, "bad"],
      3,
      new Date("2026-09-30T12:00:00Z"),
    );
    expect(series.map((day) => [day.date, day.count])).toEqual([
      ["2026-09-28", 1],
      ["2026-09-29", 0],
      ["2026-09-30", 2],
    ]);
  });

  it("reports run success rate over finished runs only", () => {
    expect(runOutcomes([{ status: "SUCCEEDED" }, { status: "FAILED" }, { status: "RUNNING" }])).toEqual({
      total: 3,
      succeeded: 1,
      failed: 1,
      inProgress: 1,
      successRate: 50,
    });
    expect(runOutcomes([]).successRate).toBeNull();
  });

  it("never reports a missing source as healthy", () => {
    const signals = healthSignals({});
    expect(signals.every((signal) => signal.value === null && signal.tone === "neutral")).toBe(true);
    const live = healthSignals({
      health: { metrics: { connector_failures: 2, mapping_issues: 0 } },
      operations: { metrics: { outbox_dead_lettered: 0, outbox_pending: 0 }, worker: { heartbeat: "NOT_REPORTED" } },
    });
    expect(live.find((signal) => signal.key === "connectors")?.tone).toBe("critical");
    expect(live.find((signal) => signal.key === "mappings")?.tone).toBe("good");
    expect(live.find((signal) => signal.key === "worker")?.tone).toBe("neutral");
  });

  it("ranks attention items by severity", () => {
    const items = attentionItems(
      [
        { id: "t1", name: "Acme", status: "SUSPENDED" },
        { id: "t2", name: "Beta", status: "ACTIVE", seat_usage: 12, seat_cap: 10 },
      ],
      [
        { tenant_id: "t2", status: "ACTIVE", days_remaining: 5 },
        { tenant_id: "t2", status: "ACTIVE", days_remaining: 80 },
      ],
      [{ code: "CONNECTOR_FAILURES", label: "Failed connectors", count: 1, severity: "HIGH" }],
    );
    expect(items.map((item) => item.tone)).toEqual(["critical", "serious", "serious", "warning"]);
    expect(items.some((item) => item.title.includes("80 days"))).toBe(false);
  });

  it("summarises plan mix and the worst tone", () => {
    expect(
      planMix([{ plan_name: "Pro" }, { plan_code: "PRO_X" }, { plan_name: "Pro" }, {}]).map((s) => s.count),
    ).toEqual([2, 1, 1]);
    expect(worstTone(["good", "warning", "neutral"])).toBe("warning");
    expect(worstTone([])).toBe("good");
  });
});
