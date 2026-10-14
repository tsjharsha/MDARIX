import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { TrustBadge } from "./sections/TrustBadge";
import { RunView } from "./sections/CaseAiRun";
import { ExplainWithAi, SecondLookCard } from "./sections/Complaints";
import { trustIssues, trustOf, trustSentence, type TrustSummary } from "./trust";
import { runHeadline, runProgress, runTrust, type CaseAiRun } from "./signalAi";
import { explanationNote, type SecondLookExplanation, type SecondLookItem } from "./complaintReview";
import { AiReleaseGate, gateBlocksSwitchOn, type ReleaseGate } from "../customer-admin/sections/AiReleaseGate";

const passed: TrustSummary = {
  id: "r1",
  status: "PASS",
  label: "Trust check passed",
  policy: "MDARIX_AI_TRUST_POLICY_R1_V2",
  author: "AI",
  checks: [
    { check: "EVIDENCE_GROUNDING", status: "PASS", message: "All 2 cited sources exist in this case's evidence." },
    { check: "PROVENANCE", status: "PASS", message: "Written by anthropic claude-sonnet-5-5." },
  ],
  limitations: ["A passed trust check means the output is grounded and worded within policy, not that it is true."],
};
const blocked: TrustSummary = {
  ...passed,
  status: "BLOCKED",
  label: "Trust check blocked",
  checks: [
    { check: "CERTAINTY_WORDING", status: "WARNING", message: "1 statement asserts certainty." },
    { check: "EVIDENCE_GROUNDING", status: "BLOCKED", message: "Cites 1 source that does not exist: EV-404." },
  ],
};

function workspace(permissions: string[]): WorkspaceApi {
  return {
    session: { allowed_menu: ["products", "investigations"], business_permissions: permissions },
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [], requestOpenInvestigation: vi.fn() },
  } as unknown as WorkspaceApi;
}
const render = (node: ReactNode, permissions: string[] = []) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace(permissions)}>{node}</WorkspaceContext.Provider>);

describe("the automatic trust check", () => {
  it("reads a check from the server and refuses anything else", () => {
    expect(trustOf(passed)?.status).toBe("PASS");
    expect(trustOf({ status: "PASS_WITH_LIMITATIONS" })?.label).toBe("Trust check passed with limitations");
    expect(trustOf({ status: "MAYBE" })).toBeNull();
    expect(trustOf(null)).toBeNull();
    expect(trustOf("PASS")).toBeNull();
  });

  it("puts the blocking check first and names it in one line", () => {
    expect(trustIssues(blocked).map((check) => check.check)).toEqual(["EVIDENCE_GROUNDING", "CERTAINTY_WORDING"]);
    expect(trustSentence(blocked)).toBe("Trust check blocked: Cites 1 source that does not exist: EV-404.");
    expect(trustSentence(passed)).toBe("Trust check passed");
    expect(trustIssues(null)).toEqual([]);
  });

  it("shows a badge that opens its checks, and nothing without a check", () => {
    const markup = renderToStaticMarkup(<TrustBadge trust={blocked} />);
    expect(markup).toContain("Trust check blocked");
    expect(markup).toContain('aria-expanded="false"');
    expect(markup).toContain("tone-critical");
    expect(markup).toContain("Cites 1 source that does not exist: EV-404. Show the checks");
    expect(renderToStaticMarkup(<TrustBadge trust={null} />)).toBe("");
  });
});

const run = (overrides: Partial<CaseAiRun> = {}): CaseAiRun => ({
  id: "run-1",
  status: "COMPLETED",
  trigger: "AUTO",
  as_of: null,
  requested_at: null,
  started_at: null,
  finished_at: null,
  error: null,
  steps: [
    { step: "ANALYSIS", label: "Analysis of the evidence", status: "DONE", author: "AI", trust: passed },
    { step: "HYPOTHESES", label: "Competing explanations", status: "DONE", author: "AI", trust: blocked },
    {
      step: "FAILURE_CHAINS",
      label: "Possible failure chains",
      status: "SKIPPED",
      notice: "Not run in this edition: the automatic chains were a fixed template, not an analysis.",
    },
    { step: "BRIEF", label: "Investigation brief", status: "DONE", author: "RULES", trust: null },
  ],
  ...overrides,
});

describe("the case AI run with its trust checks", () => {
  it("counts checked and blocked results, and leaves a skipped step out of the progress", () => {
    expect(runTrust(run())).toEqual({ checked: 2, blocked: 1, limited: 0 });
    expect(runProgress(run())).toEqual({ done: 3, total: 3 });
    expect(runHeadline(run())).toMatchObject({
      title: "AI analysis ready: 1 result blocked by the trust check",
      tone: "warning",
    });
    const clean = run({ steps: run().steps.filter((step) => step.trust !== blocked) });
    expect(runHeadline(clean).title).toBe("AI analysis ready: judge each explanation below");
    expect(runHeadline(clean).detail).toContain("1 result checked automatically for sources, wording and provenance.");
  });

  it("shows each step's trust check and why a step did not run", () => {
    const markup = renderToStaticMarkup(
      <RunView run={run()} running={false} canRun busy={false} error="" onRun={vi.fn()} />,
    );
    expect(markup).toContain("Trust check passed");
    expect(markup).toContain("Trust check blocked");
    expect(markup).toContain("Not run in this edition: a fixed template, not an analysis");
    expect(markup).toContain("is-skipped");
  });
});

const explanation: SecondLookExplanation = {
  author: "AI",
  sentences: [
    {
      text: "The description alleges a failure during use with harm to a patient.",
      quotes: [{ field: "description", label: "Description", text: "the pump stopped and the patient was choking" }],
      fields: ["description"],
    },
  ],
  ai: {
    status: "COMPLETED",
    provider: "anthropic",
    model: "claude-sonnet-5-5",
    dropped: [{ text: "This is a complaint.", reason: "DECISION_CLAIM" }],
    trust: { status: "PASS", label: "Trust check passed" },
    label: "AI interpretation: written by AI from this record's own words, every quote checked; a person decides",
  },
};

const item = (overrides: Partial<SecondLookItem> = {}): SecondLookItem => ({
  id: "0b6f8f9e-1111-4222-8333-444455556666",
  business_id: "CMP000012",
  complaint_identifier: "SRC-12",
  product_id: "9d1c2b3a-1111-4222-8333-444455556666",
  product_name: "Infusion Pump",
  version: "B",
  status: "Cancelled",
  complaint_type: "Inquiry",
  problem_code: null,
  severity: null,
  description: "Customer says the pump stopped and the patient was choking",
  received_date: "2026-09-01",
  patient_involved: true,
  serious_injury: null,
  death: null,
  malfunction: null,
  reasons: [{ code: "INQUIRY", label: "Logged as an inquiry or service record (Inquiry)" }],
  signs: [{ code: "WORDS", label: "Mentions choking" }],
  words: ["choking"],
  score: 40,
  decision: null,
  ...overrides,
});

describe("the second look's AI explanation", () => {
  it("shows each sentence with the record's own words it quotes, its trust check and what was left out", () => {
    const markup = render(<SecondLookCard item={item({ explanation })} onDecide={vi.fn()} />, ["ai.run"]);
    expect(markup).toContain("The description alleges a failure during use with harm to a patient.");
    expect(markup).toContain("<b>Description:</b> the pump stopped and the patient was choking");
    expect(markup).toContain("a person decides");
    expect(markup).toContain("Trust check passed");
    expect(markup).toContain("1 sentence left out: a quote not in the record, a decision or a stated cause.");
    expect(markup).toContain("Explain again");
  });

  it("offers the explanation only to people allowed to run AI, and says why when there is none", () => {
    expect(render(<ExplainWithAi item={item()} name="CMP000012" />, ["ai.run"])).toContain("Explain with AI");
    expect(render(<ExplainWithAi item={item()} name="CMP000012" />, [])).toBe("");
    // A viewer still sees an explanation someone asked for.
    expect(render(<ExplainWithAi item={item({ explanation })} name="CMP000012" />, [])).toContain(
      "The description alleges",
    );
    expect(explanationNote(explanation)).toBeNull();
    expect(
      explanationNote({
        author: "RULES",
        sentences: [],
        ai: { status: "NO_ANSWER", reason: "PROVIDER_NOT_CONFIGURED" },
      }),
    ).toBe("No AI provider is set up yet, so the reasons above come from the rules.");
    expect(
      explanationNote({
        author: "RULES",
        sentences: [],
        ai: { status: "REFUSED", reason: "GENAI_DISABLED_FOR_ORGANIZATION", message: "AI is switched off." },
      }),
    ).toBe("AI is switched off.");
  });
});

const gate = (overrides: Partial<ReleaseGate> = {}): ReleaseGate => ({
  ready: false,
  met: 1,
  total: 4,
  enforced: true,
  message: "AI stays off for pilots until every bar is met; every feature works from the records meanwhile.",
  bars: [
    {
      code: "PROVIDER_CONTRACTED",
      title: "A contracted AI provider with zero data retention",
      status: "NOT_MET",
      detail: "No AI provider is configured and allowed here.",
      action: "Sign the provider contract (zero data retention), then set MDARIX_GENAI_PROVIDER.",
    },
    {
      code: "TRUST_CHECK_AUTOMATIC",
      title: "Every AI result checked automatically",
      status: "MET",
      detail: "Every AI result is checked as it is saved (policy MDARIX_AI_TRUST_POLICY_R1_V2).",
      action: null,
    },
  ],
  ...overrides,
});

describe("the AI release gate", () => {
  it("lists the bars with what is met, and what to do only for the people who run the server", () => {
    const customer = renderToStaticMarkup(<AiReleaseGate gate={gate()} />);
    expect(customer).toContain("AI release gate: 1 of 4 met");
    expect(customer).toContain("This server will not switch AI on until every bar is met.");
    expect(customer).toContain("Not met");
    expect(customer).not.toContain("MDARIX_GENAI_PROVIDER");
    expect(renderToStaticMarkup(<AiReleaseGate gate={gate()} showActions />)).toContain("MDARIX_GENAI_PROVIDER");
    expect(renderToStaticMarkup(<AiReleaseGate gate={null} />)).toBe("");
  });

  it("blocks switching AI on only where the gate is enforced and not met", () => {
    expect(gateBlocksSwitchOn(gate())).toBe(true);
    expect(gateBlocksSwitchOn(gate({ enforced: false }))).toBe(false);
    expect(gateBlocksSwitchOn(gate({ ready: true }))).toBe(false);
    expect(gateBlocksSwitchOn(undefined)).toBe(false);
  });
});
