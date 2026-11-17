// E3 + W6: the decision record and the decision-and-impact summary (backend/app/human_decision/summary.py), and
// G-06: the flagship signal in the trend check's own number.
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DecisionSummaryView } from "./sections/DecisionSummary";
import { FlagshipView, SUMMARY_LINE } from "./sections/OneStory";
import {
  NOT_RECORDED,
  decisionSummaryPath,
  firstSentence,
  headline,
  mfaText,
  reviewText,
  type DecisionSummary,
} from "./decisionSummary";
import { signalWhy, summaryPlace, type FlagshipRun } from "./oneStory";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { SAMPLE_SOURCE } from "./complaintList";

const reads = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const data = (path && reads.data[path.split("?")[0]]) ?? null;
    return { state: data ? "ready" : "loading", data, reload: () => undefined };
  },
}));
vi.mock("./useAiStatus", () => ({ useAiReady: () => null, useAiBanner: () => null }));

const api = () =>
  ({
    session: { allowed_menu: ["home"], business_permissions: [] },
    work: { products: [], setInvestigationId: vi.fn(), refreshProducts: vi.fn() },
    open: vi.fn(),
    notify: vi.fn(),
    startStory: vi.fn(),
    navigation: "new",
    isTrial: true,
    dataSource: SAMPLE_SOURCE,
  }) as unknown as WorkspaceApi;
const render = (node: ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={api()}>{node}</WorkspaceContext.Provider>);

const QUESTION = "Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?";
const RATIONALE = "The NovaSense sensors accepted under reduced inspection explain the pressure alarms.";
const SIGNED: DecisionSummary = {
  investigation: { id: "inv-1", ref: "SAMPLE-INV-001", question: QUESTION },
  decision: {
    id: "d-1",
    ref: "DEC000001",
    status: "SIGNED",
    status_label: "Signed",
    superseded_by: null,
    outcome: "ACCEPT_CONCLUSION",
    outcome_label: "Accept the conclusion",
    conclusion: "The NovaSense pressure sensors fitted from Rev B are the most likely cause. Contain lots 003 and 004.",
    rationale: RATIONALE,
    conditions: null,
    root_cause_category_label: "Material",
    root_cause_attribution_label: "Device related",
    brief_ref: "DBV000001",
    brief_version: 1,
    effective_on: "2026-11-17",
    review_on: "2027-02-15",
  },
  owner: { name: "Asha Rao", role_label: "Decision Maker", authority_recorded: true },
  signature: {
    ref: "SIG000001",
    name: "Asha Rao",
    role_label: "Decision Maker",
    signed_at: "2026-11-17T10:00:00+00:00",
    meaning: "I approve this decision.",
    mfa_verified: true,
    verification: "VALID",
  },
  evidence: {
    supporting: [
      { ref: "EVD000001", title: "Supplier change record (Sample)" },
      { ref: "EVD000002", title: "Incoming inspection results, lots 003-004 (Sample)" },
    ],
    contradicting: [],
    fingerprint: "abc",
  },
  ai: {
    statement: "No AI was used.",
    in_brief: [],
    proposals: [
      { ref: "AIX000001", label: "Investigation analysis", recorded: true, reviews: { ACCEPTED: 1, NOT_REVIEWED: 1 } },
    ],
  },
  hypotheses: {
    accepted: [{ ref: "HYP000001", statement: "The NovaSense sensors read high." }],
    leading: { ref: "HYP000001", statement: "The NovaSense sensors read high.", origin: "HUMAN" },
    rejected: [],
    alternatives: [
      {
        ref: "HYP000002",
        statement: "Ward alarm limits were changed.",
        origin: "HUMAN",
        status_label: "Weakly supported",
      },
    ],
  },
  affects: {
    product: { ref: "SAMPLE-ORBIT-300", name: "OrbitCare 300 Infusion Pump (Sample)" },
    versions: ["Rev B"],
    lots: ["SAMPLE-LOT-003", "SAMPLE-LOT-004"],
    markets: ["US", "GB"],
    complaints: 14,
    risks: [
      { ref: "SAMPLE-RSK-01", description: "False pressure alarm.", status: "active" },
      { ref: "SAMPLE-RSK-02", description: "Missed occlusion.", status: "active" },
    ],
  },
  follow_ups: [
    {
      id: "f-1",
      action_type: "RISK_REASSESSMENT_REQUIRED",
      title: "Reassess SAMPLE-RSK-01",
      status: "OPEN",
      due_at: "2026-12-07T00:00:00+00:00",
    },
  ],
  capas: [
    {
      id: "c-2",
      ref: "SAMPLE-CAPA-02",
      title: "Restore incoming inspection",
      status: "open",
      due_at: null,
      check: { round: 1, status: "PLANNED", planned_on: "2027-02-15", signed_at: null, result_summary: null },
    },
  ],
  next: [
    {
      what: "Reassess SAMPLE-RSK-01",
      ref: "FUP000001",
      kind: "RISK_REASSESSMENT_REQUIRED",
      due: "2026-12-07",
      who: null,
    },
    {
      what: "Effectiveness check of SAMPLE-CAPA-02 (round 1)",
      ref: "SAMPLE-CAPA-02",
      kind: "EFFECTIVENESS_CHECK",
      due: "2027-02-15",
      who: null,
    },
  ],
  worked: {
    state: "TOO_EARLY",
    text: "Too early: the effectiveness check is planned for 2027-02-15. Only a signed check says an action worked.",
    on: "2027-02-15",
  },
};

beforeEach(() => {
  reads.data = {};
});

describe("Decision and impact summary", () => {
  it("shows exactly what was recorded: the decision, evidence, signer with MFA, what it affects, next and too early", () => {
    reads.data[decisionSummaryPath("inv-1")] = SIGNED;
    const html = render(<DecisionSummaryView investigationId="inv-1" recordOpen />);
    expect(html).toContain(
      "Accept the conclusion: The NovaSense pressure sensors fitted from Rev B are the most likely cause",
    );
    expect(html).toContain("Asha Rao");
    expect(html).toContain("Password and authenticator code");
    expect(html).toContain("Supplier change record (Sample)");
    expect(html).toContain("SAMPLE-LOT-003, SAMPLE-LOT-004");
    expect(html).toContain("US, GB");
    expect(html).toContain("SAMPLE-RSK-01, SAMPLE-RSK-02");
    expect(html).toContain("Reassess SAMPLE-RSK-01");
    expect(html).toContain("Too early");
    expect(html).not.toMatch(/it worked|proven|eliminated/i);
    // The formal record: the question, the rationale, the AI proposal's reviews, the hypotheses, the dates.
    expect(html).toContain(QUESTION);
    expect(html).toContain(RATIONALE);
    expect(html).toContain("1 accepted, 1 not reviewed by a person");
    expect(html).toContain("None used in the signed brief.");
    expect(html).toContain("Ward alarm limits were changed.");
    expect(html).toContain("None rejected by a person");
    expect(html).toContain("verified by the server");
    expect(html).toContain("approval authority on record");
    expect(html).toContain("effectiveness check planned for");
  });

  it('says "Not recorded" where nothing was recorded, never filling it in', () => {
    reads.data[decisionSummaryPath("inv-2")] = {
      ...SIGNED,
      decision: { ...SIGNED.decision!, review_on: null, conclusion: null, rationale: null },
      owner: { name: null, role_label: null, authority_recorded: false },
      signature: null,
      evidence: { supporting: [], contradicting: [], fingerprint: null },
      hypotheses: { accepted: [], leading: null, rejected: [], alternatives: [] },
      affects: { product: null, versions: [], lots: [], markets: [], complaints: null, risks: [] },
      follow_ups: [],
      capas: [],
      next: [],
      worked: {
        state: "NOT_PLANNED",
        text: "No CAPA or effectiveness check is recorded on this investigation yet.",
        on: null,
      },
    } satisfies DecisionSummary;
    const html = render(<DecisionSummaryView investigationId="inv-2" recordOpen />);
    expect(html).toContain('<h2 id="uw-dsum-title">Accept the conclusion</h2>');
    expect(html.match(/Not recorded/g)?.length).toBeGreaterThanOrEqual(8);
    expect(html).toContain("approval authority: not recorded");
    expect(html).toContain("review not recorded yet");
    expect(html).toContain("No check planned");
    expect(html).toContain("Nothing open");
    expect(html).not.toContain("Asha Rao");
  });

  it("shows nothing before a decision is signed", () => {
    reads.data[decisionSummaryPath("inv-3")] = { investigation: SIGNED.investigation, decision: null };
    expect(render(<DecisionSummaryView investigationId="inv-3" />)).toBe("");
  });

  it("words: MFA, reviews, the headline", () => {
    expect([mfaText(true), mfaText(false), mfaText(null)]).toEqual([
      "Password and authenticator code",
      "Password only",
      NOT_RECORDED,
    ]);
    expect(reviewText({ REJECTED: 1, ACCEPTED: 2 })).toBe("2 accepted, 1 rejected");
    expect(reviewText({})).toBe("not reviewed");
    expect(firstSentence("Sensors read 4.5% high. Contain the lots.")).toBe("Sensors read 4.5% high");
    expect(headline({ ...SIGNED.decision!, conclusion: null, outcome_label: null })).toBe(NOT_RECORDED);
  });
});

describe("G-06 and the flagship's way to the summary", () => {
  it("says the rise in the trend check's own number, and no number without a trend row", () => {
    const rows = [
      { product: { id: "p-orbit" }, ratio: 9.31 },
      { product: { id: "p-orbit" }, ratio: 1.2 },
      { product: { id: "other" }, ratio: 20 },
    ];
    expect(signalWhy(rows, "p-orbit")).toBe(
      "Pressure-alarm complaints on one pump are at 9.3× the earlier average after Rev B. A rise like this starts an investigation.",
    );
    expect(signalWhy([], "p-orbit")).not.toMatch(/\d|sevenfold/);
  });

  const run = (current: number): FlagshipRun =>
    ({
      run: "flagship",
      product: {
        id: "p-orbit",
        ref: "SAMPLE-ORBIT-300",
        name: "OrbitCare 300",
        label: "OrbitCare 300",
        version: "Rev B",
        version_state: "KNOWN",
        unverified: 0,
      },
      investigation: { id: "inv-1", ref: "SAMPLE-INV-001", question: QUESTION },
      change: null,
      capa: {
        id: "capa-2",
        ref: "SAMPLE-CAPA-02",
        title: "Restore incoming inspection",
        check_planned: false,
        check_status: null,
      },
      branch: null,
      ai_proposals: 1,
      mfa_verified: true,
      steps: Array.from({ length: 7 }, (_, index) => ({
        key: `k${index}`,
        label: `S${index}`,
        done: index < current,
        skipped: false,
      })),
      current,
      finished: current >= 7,
    }) as FlagshipRun;
  const story = (flagship: FlagshipRun) => ({ sample: null, yours: null, flagship }) as never;

  it("links steps 7 and the finished card to the summary once the decision is signed, never before", () => {
    expect(render(<FlagshipView story={story(run(6))} run={run(6)} />)).toContain(SUMMARY_LINE);
    expect(render(<FlagshipView story={story(run(7))} run={run(7)} />)).toContain(SUMMARY_LINE);
    expect(render(<FlagshipView story={story(run(5))} run={run(5)} />)).not.toContain(SUMMARY_LINE);
    expect(summaryPlace(run(6))).toEqual({
      section: "Investigations",
      tab: "Decisions & actions?part=summary",
      caseId: "inv-1",
      productId: "p-orbit",
    });
  });
});
