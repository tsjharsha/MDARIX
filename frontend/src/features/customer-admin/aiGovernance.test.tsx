import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import {
  AI_GOVERNANCE_PATH,
  PLATFORM_AI_GOVERNANCE_PATH,
  agreementShare,
  type AiGovernance as Data,
} from "./aiGovernance";
import { AiGovernance, PlatformAiGovernanceView } from "./sections/AiGovernance";
import { NOT_LOCKED, lockedAiLines, type LockedAi } from "../workspace/decisionSummary";
import { briefPage } from "../workspace/investigationBrief";
import { WorkspaceContext, type WorkspaceApi } from "../workspace/workspaceContext";
import { SettingsSection } from "../workspace/sections/Settings";
import { TRIAL_AI_GOVERNANCE_TAB } from "../workspace/sections/TrialAi";
import type { BriefVersion } from "../workspace/decisionBrief";
import type { DecisionSummary } from "../workspace/decisionSummary";

// E1: AI governance on one screen, and U7: the AI record locked into a signed decision.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("./shared", async (original) => ({
  ...(await original<typeof import("./shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

const STATEMENT = "MDARIX never trains models on your data. AI proposals are never decisions.";
const RECORDED = "Recorded with the sample · no model was called";
const providers = {
  approved: [
    {
      name: "groq",
      kind: "AI model provider",
      terms: "https://console.groq.com/docs/legal/services-agreement",
      checked_on: "2026-11-17",
      region: "USA",
      trains_on_data: "No",
      why: "Commercial use allowed and no training on the data.",
      in_trial_chain: true,
    },
  ],
  not_used: [{ name: "Paid-plan AI providers", why: "None approved yet." }],
  trial_chain: ["groq"],
};
const governance: Data = {
  statement: STATEMENT,
  recorded_label: RECORDED,
  providers,
  controls: {
    organization_on: false,
    free_trial: true,
    trial_chain_on: true,
    features: [{ key: "ask", label: "Ask MDARIX", enabled: false }],
    people: [{ name: "Asha Rao", ai: "Active" }],
  },
  outputs: {
    live: 1,
    recorded: 1,
    items: [
      {
        id: "1",
        ref: "AIX-0001",
        what: "Hypotheses",
        at: "2026-11-17T10:00:00+00:00",
        provider: "sample-recorded",
        model: "pre-recorded sample answer (no model called)",
        prompt_version: "Observations (sample)",
        sources: 3,
        reviews: { ACCEPTED: 1, REJECTED: 1 },
        recorded: true,
      },
    ],
  },
  calls: { total: 0, by_outcome: {}, items: [] },
  agreement: {
    live: { ACCEPTED: 3, EDITED: 1, REJECTED: 0 },
    recorded: { ACCEPTED: 1, EDITED: 0, REJECTED: 1 },
    disagreements: [
      {
        subject_type: "evidence_observation",
        ref: null,
        decision: "REJECTED",
        reason: "The lot 004 figure is not in the inspection record.",
        reviewer: "Asha Rao",
        at: "2026-11-17T10:05:00+00:00",
        recorded: true,
      },
    ],
  },
};

describe("AI governance screen", () => {
  it("shows the register, the switches, the outputs and every disagreement in plain words", () => {
    resources.data[AI_GOVERNANCE_PATH] = governance;
    const html = renderToStaticMarkup(<AiGovernance />);
    expect(html).toContain(STATEMENT);
    expect(html).toContain("groq");
    expect(html).toContain("Not used");
    expect(html).toContain("Paid-plan AI providers");
    expect(html).toContain("Asha Rao: Active");
    expect(html).toContain("The lot 004 figure is not in the inspection record.");
    expect(html).toContain("Observations (sample)");
    expect(html).toContain("1 accepted, 1 rejected");
    // Live and recorded are counted apart: 75% of the live reviews accepted as proposed.
    expect(html).toContain("75%");
    expect(html).toContain(RECORDED);
    expect(html).not.toMatch(/validated|certified|explainable/i);
  });

  it("gives no agreement share when nothing was reviewed", () => {
    expect(agreementShare({ ACCEPTED: 0, EDITED: 0, REJECTED: 0 })).toBeNull();
    expect(agreementShare({ ACCEPTED: 1, EDITED: 1, REJECTED: 0 })).toBe(50);
  });

  it("shows the platform administrator counts per organization, without record content", () => {
    resources.data[PLATFORM_AI_GOVERNANCE_PATH] = {
      statement: STATEMENT,
      recorded_label: RECORDED,
      providers,
      organizations: [
        {
          tenant_id: "t1",
          organization: "OrbitCare Trial",
          organization_on: false,
          live: 2,
          recorded: 1,
          calls: 4,
          ACCEPTED: 1,
          EDITED: 0,
          REJECTED: 1,
        },
      ],
    };
    const html = renderToStaticMarkup(<PlatformAiGovernanceView />);
    expect(html).toContain("OrbitCare Trial");
    expect(html).toContain("1 accepted, 1 rejected");
    expect(html).toContain(`${RECORDED}: counted apart from live outputs.`);
  });

  it("is a Settings tab for the person who started the trial only", () => {
    const api = (isTrial: boolean) =>
      ({
        session: { allowed_menu: ["home"], business_permissions: ["signal.triage"], routine_path: true },
        work: {},
        open: vi.fn(),
        notify: vi.fn(),
        navigation: "new",
        isTrial,
      }) as unknown as WorkspaceApi;
    const render = (value: WorkspaceApi) =>
      renderToStaticMarkup(
        <WorkspaceContext.Provider value={value}>
          <SettingsSection tab={TRIAL_AI_GOVERNANCE_TAB} />
        </WorkspaceContext.Provider>,
      );
    delete resources.data["/api/v1/admin/ai-settings"];
    expect(render(api(true))).not.toContain(TRIAL_AI_GOVERNANCE_TAB);
    resources.data["/api/v1/admin/ai-settings"] = { free_trial: true, features: [], models: [] };
    expect(render(api(true))).toContain(STATEMENT);
  });
});

const locked: LockedAi = {
  ref: "AIX-0001",
  what: "Hypotheses",
  provider: "groq",
  model: "llama-test",
  model_version: "1",
  prompt_version: "hypotheses-v3",
  at: "2026-11-17T10:00:00+00:00",
  sources: ["SAMPLE-EV-001", "SAMPLE-EV-002"],
  recorded: false,
  in_signed_brief: true,
  verdicts: [
    { about: "The result as a whole", state: "EDITED", reason: "Too broad a claim.", reviewer: "Asha Rao", at: null },
  ],
};

describe("U7: the AI record locked at signing", () => {
  it("names the model, prompt version, sources and each verdict with its reason", () => {
    expect(lockedAiLines([locked])).toEqual([
      "AIX-0001: Hypotheses · groq · llama-test (1) · prompt hypotheses-v3 · sources: SAMPLE-EV-001, SAMPLE-EV-002 · in the signed brief",
      "Edited by Asha Rao: Too broad a claim. (The result as a whole)",
    ]);
  });

  it("says Not recorded when the decision was signed before the record was kept, and never guesses", () => {
    expect(lockedAiLines(null)).toEqual([NOT_LOCKED]);
    expect(lockedAiLines(undefined)).toEqual([NOT_LOCKED]);
    expect(lockedAiLines([])).toEqual(["No AI output on this investigation when the decision was signed."]);
    expect(lockedAiLines([{ ...locked, prompt_version: null, sources: [] }])[0]).toContain(
      "prompt Not recorded · sources: Not recorded",
    );
  });

  it("is a part of the Investigation Brief once the decision is signed", () => {
    const version = { version: 1, content: {}, narrative: {} } as unknown as BriefVersion;
    const summary = {
      investigation: { id: "c", ref: "SAMPLE-INV-001", question: null },
      decision: { outcome_label: "Accepted the conclusion", conclusion: null },
      ai: { statement: null, in_brief: [], proposals: [], locked: [locked] },
    } as unknown as DecisionSummary;
    const part = briefPage(version, summary, null).find((item) => item.key === "ai");
    expect(part?.lines[0]).toContain("llama-test");
    const before = briefPage(version, { ...summary, decision: null }, null).find((item) => item.key === "ai");
    expect(before?.lines).toEqual([]);
  });
});
