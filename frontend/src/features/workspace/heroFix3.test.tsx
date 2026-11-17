import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { SettingsSection } from "./sections/Settings";
import { TRIAL_AI_TAB } from "./sections/TrialAi";
import { aiStatusBanner } from "./intelligence";
import { ConsentNotice } from "../shared/ConsentBanner";
import { AuditTab, SignaturesView } from "./sections/AuditTab";
import { EvidencePackCard, LatestSignatures, trainingWords } from "./sections/TrustRecords";
import { NEW_HEADS } from "./UserWorkspace";
import { Tabs } from "../customer-admin/shared";
import { SignupForm, TRIAL_AI_LINE } from "../auth/SignupForm";
import { countOf } from "../admin/console/AdminOverview";
import { MirNeeds } from "./sections/MirFiles";
import type { ReportDetail } from "./authorityReports";

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
    // can_change false (the trial services are not set yet): the tab stays, its switch is off (next test).
    resources.data[AI_SETTINGS] = { ...trialSettings, can_change: false };
    expect(render(api(["signal.triage"], true), <SettingsSection />)).toContain(TRIAL_AI_TAB);
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
    resources.data[AI_SETTINGS] = { ...trialSettings, trial_chain_on: true, can_change: false };
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

describe("F-E1 to F-E6: records an inspector can trust", () => {
  it("asks the inspector's question and shows sub-views as one segmented control", () => {
    expect(NEW_HEADS.Records).toBe("Records an inspector can trust");
    const html = renderToStaticMarkup(
      <Tabs tabs={["A", "B"]} active="A" onChange={() => undefined} label="x" segmented />,
    );
    expect(html).toContain('class="ac-tabs is-segmented"');
  });

  it("shows the organization's audit trail to whoever the server lets read it, and nothing otherwise", () => {
    delete resources.data["/api/v1/admin/audit-history"];
    expect(render(api([]), <AuditTab />)).not.toContain("Everything done in your organization");
    resources.data["/api/v1/admin/audit-history"] = [
      {
        id: "e1",
        created_at: "2026-11-17T02:10:00Z",
        action: "SIGNATURE_APPLIED",
        action_label: "Decision signed",
        actor_name: "Asha Rao (fictional)",
        reason: "Reportable in the US",
      },
    ];
    const html = render(api([]), <AuditTab />);
    expect(html).toContain("Everything done in your organization");
    expect(html).toContain("Decision signed");
    expect(html).toContain("Asha Rao (fictional)");
    expect(html).toContain("Check the audit trail is intact");
  });

  it("opens verification on the latest signed records, with signer, MFA and training", () => {
    delete resources.data["/api/v1/governance/signed-records"];
    expect(render(api([]), <LatestSignatures />)).toBe("");
    resources.data["/api/v1/governance/signed-records"] = {
      items: [
        {
          signature_id: "s1",
          decision_business_id: "DEC000011",
          decision: "REPORTABLE",
          signer_name: "MDARIX sample author",
          meaning: "Approved",
          signed_at: "2026-11-17T02:10:00Z",
          mfa_verified: true,
          training: [{ code: "SOP-01", version: "2", current: true }],
          fingerprint_ok: true,
        },
      ],
    };
    const html = render(api([]), <LatestSignatures />);
    expect(html).toContain("1 signature");
    expect(html).toContain("unchanged since signing · checked");
    expect(html).toContain("MDARIX sample author");
    expect(html).toContain("Authenticator code checked");
    expect(html).toContain("Trained · 1 current document");
    expect(trainingWords([{ code: "SOP-01", current: false }])).toBe("Training out of date: SOP-01");
    const one = renderToStaticMarkup(
      <SignaturesView
        verification={{
          state: "ready",
          data: { verification_status: "VALID", signatures: [{ signature_id: "x", valid: true, mfa_verified: false }] },
        }}
      />,
    );
    expect(one).toContain("No authenticator code");
  });

  it("puts the evidence pack on Records for people who may export", () => {
    expect(render(api([]), <EvidencePackCard />)).toBe("");
    expect(render(api(["data.export"]), <EvidencePackCard />)).toContain("Evidence pack");
  });
});

describe("F-W2, F-X4: first screens read in one glance", () => {
  it("keeps the sign-up lead to the AI line, the rest in the fold", () => {
    const html = renderToStaticMarkup(<SignupForm />);
    expect(html).toContain(`<p class="auth-lead">${TRIAL_AI_LINE}</p>`);
    expect(html).toContain("<li>50 people</li>");
    expect(html.indexOf("5,000 uploaded rows are included")).toBeGreaterThan(html.indexOf("<summary>How it works"));
  });

  it("counts in the right number", () => {
    expect(countOf(1, "customer")).toBe("1 customer");
    expect(countOf(2, "active tenant")).toBe("2 active tenants");
    expect(countOf(1, "person", "people")).toBe("1 person");
    expect(countOf(3, "person", "people")).toBe("3 people");
  });
});

describe("F-M6: a draft MIR says how many fields are left, the schema keys folded", () => {
  it("counts first and folds the keys", () => {
    const detail = {
      stage: "DRAFT",
      form: { code: "GB_MIR" },
      mir: { missing: ["1.2d (1_2D)", "1.2f (1_2F)"], errors: [], snapshot: null },
    } as unknown as ReportDetail;
    const html = renderToStaticMarkup(<MirNeeds detail={detail} />);
    expect(html).toContain("<strong>2 fields left</strong>");
    expect(html.indexOf("<details")).toBeLessThan(html.indexOf("1.2d (1_2D)"));
  });
});
