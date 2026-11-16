import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { TrialAiMetricsData } from "./TrialAiMetrics";

const DATA: TrialAiMetricsData = {
  organization_on: true,
  usage: { month: "2026-11-01", tokens_used: 41_000, limit: 50_000, percent: 82, requests: 12, refused: 3 },
  calls: { total: 9, by_outcome: { ANSWERED: 8, FAILED: 1 }, by_feature: { ask: 6, summaries: 3 }, last_at: null },
  chain: [
    { position: 1, name: "freellmapi", state: "RESTING", resting_until: "2026-11-16T10:00:00+00:00" },
    { position: 2, name: "omniroute", state: "READY", resting_until: null },
  ],
  switch_events: [
    {
      action: "TRIAL_USER_AI_ACCESS_CHANGED",
      at: "2026-11-16T09:00:00+00:00",
      actor: "Platform Admin",
      reason: "Trial user asked for no AI",
      old_values: { ai_access: true },
      new_values: { ai_access: false },
      details: { source: "PLATFORM_ADMIN" },
    },
  ],
};

vi.mock("../../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../../customer-admin/shared")>()),
  useResource: () => ({ state: "ready", data: DATA, reload: () => undefined }),
}));

describe("story step 9: a trial's AI metrics for the Platform Administrator", () => {
  it("shows use against the trial limit, the provider chain and each switch change", async () => {
    const { TrialAiMetrics, aiMetricsPath } = await import("./TrialAiMetrics");
    expect(aiMetricsPath("t 1")).toBe("/api/v1/platform-admin/trial-organizations/t%201/ai-metrics");
    const html = renderToStaticMarkup(<TrialAiMetrics tenantId="t-1" />);
    expect(html).toContain("82%");
    expect(html).toContain("of this month&#x27;s AI allowance");
    // Generic provider labels only: internal service names never reach the screen.
    expect(html).toMatch(/Provider 1 · primary[\s\S]*Resting[\s\S]*Provider 2 · fallback[\s\S]*Ready/);
    expect(html).not.toContain("freellmapi");
    expect(html).not.toContain("omniroute");
    // The refused count is labelled as refused; tokens are not shown twice.
    expect(html).toContain("Stopped by the rules");
    expect(html).not.toContain("Answered from rules");
    expect(html).not.toContain("Tokens used");
    expect(html).toContain("A user&#x27;s AI set Inactive");
    expect(html).toContain("Trial user asked for no AI");
    expect(html).toContain("Answered");
  });

  it("puts each switch change in plain words", async () => {
    const { switchChange } = await import("./TrialAiMetrics");
    const base = { at: null, actor: "x", reason: null, old_values: null, details: {} };
    expect(
      switchChange({ ...base, action: "AI_PROCESSING_SETTING_CHANGED", new_values: { ai_processing_allowed: true } }),
    ).toBe("AI for the organization turned on");
    expect(
      switchChange({
        ...base,
        action: "AI_FEATURE_SETTING_CHANGED",
        new_values: { enabled: false },
        details: { feature: "summaries" },
      }),
    ).toBe("Summaries turned off");
    expect(
      switchChange({
        ...base,
        action: "TRIAL_AI_ACCESS_BULK_CHANGED",
        new_values: null,
        details: { value: true, count: 4 },
      }),
    ).toBe("Everyone set Active: 4 changed");
    expect(
      switchChange({
        ...base,
        action: "TRIAL_USER_AI_ACCESS_CHANGED",
        new_values: { ai_access: true },
        details: { user_name: "Priya N." },
      }),
    ).toBe("Priya N.'s AI set Active");
    expect(
      switchChange({
        ...base,
        action: "TRIAL_USER_AI_ACCESS_CHANGED",
        new_values: { ai_access: true },
        details: { user_name: "Priya N." },
      }),
    ).toBe("Priya N.'s AI set Active");
  });
});
