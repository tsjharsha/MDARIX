import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { SettingsSection } from "./sections/Settings";
import { TRIAL_AI_TAB } from "./sections/TrialAi";
import { aiStatusBanner } from "./intelligence";
import { ConsentNotice } from "../shared/ConsentBanner";

// Hero review 2 (17 Nov 2026), front-end fix pass 3: the findings are named by their review IDs.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

const api = (permissions: string[], isTrial = false) =>
  ({
    session: { allowed_menu: ["home"], business_permissions: permissions, routine_path: true },
    work: {},
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial,
  }) as unknown as WorkspaceApi;

const render = (value: WorkspaceApi, node: React.ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

const AI_SETTINGS = "/api/v1/admin/ai-settings";
const trialSettings = {
  ai_processing_allowed: false,
  monthly_token_budget: 50000,
  tokens_used: 0,
  requests: 0,
  refused: 0,
  month: "2026-11",
  models: [{ provider: "someprovider", model: "vendor/model-id-1" }],
  provider_name: "someprovider",
  masking: true,
  free_trial: true,
  trial_chain_on: true,
  features: [],
  release_gate: { ready: false, met: 1, total: 4, enforced: false, bars: [], message: "Gate message" },
};

describe("F1: the trial owner switches AI on in Settings", () => {
  it("offers the AI tab only when the server answers the AI settings for a free trial", () => {
    delete resources.data[AI_SETTINGS];
    expect(render(api(["signal.triage"], true), <SettingsSection />)).not.toContain(TRIAL_AI_TAB);
    resources.data[AI_SETTINGS] = trialSettings;
    expect(render(api(["signal.triage"], true), <SettingsSection />)).toContain(TRIAL_AI_TAB);
    expect(render(api(["signal.triage"], false), <SettingsSection />)).not.toContain(TRIAL_AI_TAB);
    resources.data[AI_SETTINGS] = { ...trialSettings, can_change: false };
    expect(render(api(["signal.triage"], true), <SettingsSection />)).not.toContain(TRIAL_AI_TAB);
  });

  it("shows the switch without the pilot gate, the provider or the model id", () => {
    resources.data[AI_SETTINGS] = trialSettings;
    const html = render(api(["signal.triage"], true), <SettingsSection tab={TRIAL_AI_TAB} />);
    expect(html).toContain("Turn AI on");
    expect(html).not.toContain("AI release gate");
    expect(html).not.toContain("someprovider");
    expect(html).not.toContain("model-id-1");
  });

  it("keeps the switch off while the trial's AI services are not set up", () => {
    resources.data[AI_SETTINGS] = { ...trialSettings, trial_chain_on: false };
    const html = render(api(["signal.triage"], true), <SettingsSection tab={TRIAL_AI_TAB} />);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Turn AI on/);
    expect(html).toContain("still setting up the trial&#x27;s AI services");
  });
});

describe("F-A1: the trial AI-off line says why", () => {
  it("says the organization has not switched AI on yet once the trial's services are ready", () => {
    const banner = aiStatusBanner({ enabled: false, reason_code: "AI_DISABLED", trial: true, sample_data_only: true })!;
    expect(banner.title).toBe("AI is not switched on for your organization yet");
    expect(banner.message).toContain("Settings › AI on the sample data");
  });

  it("names the account when only the person's AI is off, and keeps the old line with no services", () => {
    const user = aiStatusBanner({
      enabled: false,
      reason_code: "USER_AI_INACTIVE",
      trial: true,
      sample_data_only: true,
    })!;
    expect(user.title).toBe("AI is not switched on for your account");
    const none = aiStatusBanner({ enabled: false, reason_code: "PROVIDER_UNAVAILABLE", trial: true })!;
    expect(none.title).toBe("AI is off for free trials");
  });
});

describe("F-H4: the privacy notice is one line", () => {
  it("says the essentials on one line and keeps the rest in a Read more fold", () => {
    const html = renderToStaticMarkup(<ConsentNotice onAccept={() => undefined} onDismiss={() => undefined} />);
    expect(html).toContain("please enter no patient-identifiable information");
    expect(html).toMatch(/<details class="consent-more"><summary>Read more<\/summary>.*not certified for/);
    expect(html).toContain("Acknowledge");
  });
});
