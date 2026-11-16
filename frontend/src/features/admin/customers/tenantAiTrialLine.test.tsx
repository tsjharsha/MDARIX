import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

// Hero front end (WHIF): a free trial whose AI is on never reads "AI stays off".
const resources = vi.hoisted(() => ({ data: null as unknown }));
vi.mock("../../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../../customer-admin/shared")>()),
  useResource: () => ({ state: "ready", data: resources.data, reload: () => undefined }),
}));

const { TenantAiSettings } = await import("./TenantPages");

const render = (on: boolean) => {
  resources.data = {
    ai_processing_allowed: on,
    monthly_token_budget: 100000,
    budget_is_default: true,
    tokens_used: 0,
    requests: 0,
    refused: 0,
    month: "2026-11",
    models: [],
    provider_name: null,
    masking: true,
    free_trial: true,
  };
  return renderToStaticMarkup(<TenantAiSettings tenantId="t-1" name="OrbitCare" onMessage={() => undefined} />);
};

describe("a free trial's AI line on the tenant page", () => {
  it("says the trial's AI is off only while it is off", () => {
    expect(render(false)).toContain("Free trial: AI is off unless MDARIX switches it on for this trial");
    const on = render(true);
    expect(on).not.toContain("AI is off");
    expect(on).not.toContain("stays off");
  });
});
