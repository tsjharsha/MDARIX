import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { TrialOrganizations, trialFromAddress } from "./TrialOrganizations";
import { AiControlCenter } from "../areas/AiControlCenter";
import { TrialAiPanel, aiAccessPath, aiGates } from "./TrialAiPanel";
import { TrialAiMetrics, aiMetricsPath } from "./TrialAiMetrics";
import { eventLabel, sampleKindLabel } from "./TrialDetail";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

// Hero review 2, fix pass 3: a trial's page stands alone (F-T1) and can be opened from the address (F-T5).

describe("F-T1 / F-T5: a trial's own page", () => {
  it("reads the trial from the address", () => {
    expect(trialFromAddress("?trial=t-1")).toBe("t-1");
    expect(trialFromAddress("?x=1")).toBeNull();
    expect(trialFromAddress("")).toBeNull();
  });

  it("leaves out the list's tiles while a trial is open, and shows them on the list", () => {
    const list = renderToStaticMarkup(<TrialOrganizations section="Trials" onSection={() => undefined} />);
    expect(list).toContain("Trials at a glance");
    const page = renderToStaticMarkup(
      <TrialOrganizations section="Trials" onSection={() => undefined} initialTrial="t-1" />,
    );
    expect(page).not.toContain("Trials at a glance");
  });
});

describe("F-X1: the AI Control Center leads with use, not the pilot gate", () => {
  it("names no provider, model id or setting, and folds the gate", () => {
    resources.data["/api/v1/platform-admin/ai/models"] = {
      models: [{ provider: "someprovider", model: "vendor/model-id-1", configured: true }],
      fallbacks: [{ provider: "otherprovider", model: "vendor/model-id-2", configured: true }],
    };
    resources.data["/api/v1/platform-admin/console/ai-activity"] = {
      window_days: 30,
      total: 0,
      failed: 0,
      p95_latency_ms: null,
      by_tenant: [],
      by_model: [],
      by_validation: {},
      latest: [],
    };
    resources.data["/api/v1/ai/release-gate"] = {
      ready: false,
      met: 1,
      total: 4,
      enforced: false,
      message: "Gate",
      bars: [{ code: "P", title: "Provider", status: "NOT_MET", detail: "d", action: "Set MDARIX_GENAI_PROVIDER" }],
    };
    const html = renderToStaticMarkup(<AiControlCenter section="Overview" />);
    for (const hidden of ["someprovider", "otherprovider", "model-id", "MDARIX_GENAI_PROVIDER"])
      expect(html).not.toContain(hidden);
    expect(html).toContain("Configured");
    expect(html).toContain("Backup provider 1");
    expect(html).toMatch(/<details class="ar-gate-fold"><summary>Before AI goes to a pilot · 1 of 4 checks done/);
    expect(html.indexOf("ar-gate-fold")).toBeGreaterThan(html.indexOf("AI runs (30 days)"));
  });
});
describe("F-T2 / F-T3 / F-T4 / F-X5 / F-T7: the trial's AI panel", () => {
  const people = [
    { user_id: "u1", display_name: "Asha Rao (fictional)", active: true },
    { user_id: "u2", display_name: "MDARIX sample author", active: true },
    { user_id: "u3", display_name: "Second person", active: true, system_user: false },
  ];

  it("counts real people with AI that really answers, and says a switch waits for the organization", () => {
    const list = { organization_on: false, trial_chain_on: true, items: people };
    expect(aiGates(list).find((gate) => gate.label === "People")).toEqual({
      label: "People",
      value: "0 of 2 with AI",
      on: false,
    });
    expect(aiGates({ ...list, organization_on: true }).find((gate) => gate.label === "People")?.value).toBe(
      "2 of 2 with AI",
    );
    resources.data[aiAccessPath("t-1")] = list;
    const html = renderToStaticMarkup(
      <TrialAiPanel detail={{ tenant_id: "t-1", ai: { line: "AI is off for free trials" } }} onChanged={() => {}} />,
    );
    expect(html).not.toContain("MDARIX sample author");
    expect(html).toContain("Active · waits for the organization");
    expect(html).toContain("to-switch is-waiting");
    // The server's constant line is not shown above live gates that say otherwise (F-T3).
    expect(html).not.toContain("AI is off for free trials");
  });

  it("names the switch changes and the chain link's reason and check time", () => {
    expect(eventLabel("TRIAL_USER_AI_ACCESS_CHANGED")).toBe("AI switched for a person");
    expect(sampleKindLabel("capas")).toBe("CAPAs");
    resources.data[aiMetricsPath("t-1")] = {
      organization_on: false,
      usage: { month: "2026-11", tokens_used: 0, limit: 10, percent: 0, requests: 0, refused: 0 },
      calls: { total: 0, by_outcome: {}, by_feature: {}, last_at: null },
      chain: [
        {
          position: 1,
          name: "p",
          state: "NOT_USABLE",
          resting_until: null,
          reason: "No answer from the service",
          checked_at: "2026-11-17T03:00:00Z",
        },
      ],
      switch_events: [],
    };
    const html = renderToStaticMarkup(<TrialAiMetrics tenantId="t-1" />);
    expect(html).toContain("No answer from the service · checked");
  });
});
