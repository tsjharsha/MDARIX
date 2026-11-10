import { renderToStaticMarkup } from "react-dom/server";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { briefNextStep } from "./decisionBrief";
import { awaitsBriefReview } from "./humanDecision";

// The panels read their data with useResource; here each address answers with fixed data (no request is made).
const answers = new Map<string, unknown>();
vi.mock("../customer-admin/shared", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({ state: "ready", data: answers.get(path ?? "") ?? null, reload: () => {} }),
}));

const { CaseDecisionPanel, newDecisionLabel } = await import("./sections/CaseDecision");
const { BriefNextStepBar, CaseDecisionBriefPanel } = await import("./sections/CaseDecisionBrief");

const CASE = "11111111-1111-4111-8111-111111111111";
const DECISION = `/api/v1/investigations/${CASE}/decision`;
const BRIEF = `/api/v1/investigations/${CASE}/decision-brief`;

function render(element: ReactElement): string {
  const workspace = {
    session: { feature_set: "mvp", business_permissions: ["records.write", "decision.sign"] },
    open: vi.fn(),
    notify: vi.fn(),
    work: { investigations: [], investigationId: CASE },
  } as unknown as WorkspaceApi;
  return renderToStaticMarkup(<WorkspaceContext.Provider value={workspace}>{element}</WorkspaceContext.Provider>);
}

const version = (status: string) => ({
  id: "22222222-2222-4222-8222-222222222222",
  business_id: "DBV000001",
  version: 1,
  status,
  content_hash: "sha256:abc",
  review_actions: [],
});

function decisionContext(status: string, reason: string | null) {
  answers.set(DECISION, {
    investigation: { business_id: "INV000001", question: "Why did pressure-alarm complaints rise?" },
    brief: version(status),
    actions: { can_sign: reason === null, can_return: false, reason },
    decisions: [],
    reviewers: [],
    outcomes: [],
  });
}

describe("from the Decision tab to the brief's review", () => {
  it("offers the review while no version of the brief is accepted for decision", () => {
    expect(awaitsBriefReview(version("READY_FOR_REVIEW"))).toBe(true);
    expect(awaitsBriefReview(version("UNDER_REVIEW"))).toBe(true);
    expect(awaitsBriefReview(version("APPROVED_FOR_DECISION"))).toBe(false);
    expect(awaitsBriefReview(null)).toBe(false);

    decisionContext("READY_FOR_REVIEW", "No version of the brief is approved for decision yet");
    const html = render(<CaseDecisionPanel investigationId={CASE} caseLabel="INV000001" onReviewBrief={() => {}} />);
    expect(html).toContain("No version of the brief is approved for decision yet");
    expect(html).toContain("Review the brief first");
    // Without a way to the brief (a screen that does not hold the case), the reason alone is shown.
    expect(render(<CaseDecisionPanel investigationId={CASE} caseLabel="INV000001" />)).not.toContain(
      "Review the brief first",
    );
  });

  it("does not send someone to the review once the brief is accepted and only their role stops them", () => {
    decisionContext("APPROVED_FOR_DECISION", "You wrote or submitted this brief, so another person must sign");
    const html = render(<CaseDecisionPanel investigationId={CASE} caseLabel="INV000001" onReviewBrief={() => {}} />);
    expect(html).toContain("another person must sign");
    expect(html).not.toContain("Review the brief first");
  });
});

describe("after the decision is signed", () => {
  it("shows the signed decision and offers a new one only as a collapsed, secondary action", () => {
    decisionContext("APPROVED_FOR_DECISION", null);
    const open = render(<CaseDecisionPanel investigationId={CASE} caseLabel="INV000001" />);
    // Not decided yet: the form itself.
    expect(open).toContain("Continue to sign");
    answers.set(DECISION, {
      ...(answers.get(DECISION) as object),
      current_decision: {
        id: "d1",
        business_id: "DEC000001",
        outcome: "ACCEPT_CONCLUSION",
        signer_name: "Priya Raman",
      },
    });
    const decided = render(<CaseDecisionPanel investigationId={CASE} caseLabel="INV000001" />);
    expect(decided).toContain("DEC000001");
    expect(decided).toContain("View the signed record");
    expect(decided).toContain("Record a new decision (supersedes DEC000001)");
    expect(decided).not.toContain("Continue to sign");
    expect(decided).not.toContain("Why this decision supersedes the current one");
    expect(newDecisionLabel(null)).toBe("Record a new decision");
  });
});

describe("the brief's review at the top of the Decision Brief tab", () => {
  it("chooses the next step: start, record, or sign right after accepting here", () => {
    const none = { startReview: false, review: false };
    expect(briefNextStep({ startReview: true, review: false }, version("READY_FOR_REVIEW"))).toBe("START_REVIEW");
    expect(briefNextStep({ startReview: false, review: true }, version("UNDER_REVIEW"))).toBe("RECORD_REVIEW");
    expect(briefNextStep(none, version("UNDER_REVIEW"))).toBeNull();
    expect(briefNextStep(none, version("APPROVED_FOR_DECISION"), true)).toBe("SIGN");
    // An accepted version stays accepted after the decision is signed: "sign" is offered only right after accepting.
    expect(briefNextStep(none, version("APPROVED_FOR_DECISION"))).toBeNull();
    expect(briefNextStep({ startReview: true, review: true }, null)).toBeNull();
  });

  it("puts Start review above the brief, not only below it", () => {
    answers.set(BRIEF, { current: version("READY_FOR_REVIEW"), versions: [], actions: { can_start_review: true } });
    const html = render(<CaseDecisionBriefPanel investigationId={CASE} caseLabel="INV000001" />);
    const bar = html.indexOf("This brief is ready for your review");
    expect(bar).toBeGreaterThan(-1);
    expect(html.indexOf("Start review")).toBeGreaterThan(bar);
    expect(html.indexOf("Start review")).toBeLessThan(html.indexOf("Decision Brief · version 1"));
    expect(html).toContain('id="brief-quality-review"');

    answers.set(BRIEF, { current: version("UNDER_REVIEW"), versions: [], actions: { can_review: true } });
    const open = render(<CaseDecisionBriefPanel investigationId={CASE} caseLabel="INV000001" />);
    expect(open.indexOf("Record your review")).toBeLessThan(open.indexOf("Decision Brief · version 1"));

    // A case that is closed offers no review.
    answers.set(BRIEF, { current: version("READY_FOR_REVIEW"), versions: [], actions: { can_start_review: true } });
    expect(render(<CaseDecisionBriefPanel investigationId={CASE} caseLabel="INV000001" readOnly />)).not.toContain(
      "This brief is ready for your review",
    );
  });

  it("shows the scope lines the brief's compose stores", () => {
    const content = {
      scope: {
        version: 2,
        included_count: 3,
        unknown_version_count: 1,
        included: [{ id: "a" }, { id: "b" }, { id: "c" }],
        excluded_count: 1,
        excluded: [{ id: "d", reason: "Duplicate" }],
        product_versions: [{ id: "v" }],
      },
    };
    answers.set(BRIEF, { current: { ...version("APPROVED_FOR_DECISION"), content }, versions: [], actions: {} });
    const html = render(<CaseDecisionBriefPanel investigationId={CASE} caseLabel="INV000001" />);
    expect(html).toContain("Complaints in scope: 3");
    expect(html).toContain("Complaints excluded: 1");
    expect(html).toContain("Complaints with no known version: 1");
    // A brief composed before 0.10.95 stores no lots and shows no Lots line.
    expect(html).not.toContain("Lots:");
  });

  it("shows the lots a new brief's scope stores, each with its product version", () => {
    const content = {
      scope: {
        version: 3,
        lots: [
          { id: "l1", lot_number: "PW-2611", product_version_id: "v1", version_identifier: "Rev A" },
          { id: "l2", lot_number: "PW-2612", product_version_id: null, version_identifier: null },
        ],
      },
    };
    answers.set(BRIEF, { current: { ...version("APPROVED_FOR_DECISION"), content }, versions: [], actions: {} });
    const html = render(<CaseDecisionBriefPanel investigationId={CASE} caseLabel="INV000001" />);
    expect(html).toContain("Lots: PW-2611 (Rev A), PW-2612 (version not known)");
  });

  it("leads from the accepted brief to signing the decision", () => {
    const html = render(
      <BriefNextStepBar
        step="SIGN"
        investigationId={CASE}
        version={version("APPROVED_FOR_DECISION")}
        onDone={() => {}}
        onOpenDecision={() => {}}
      />,
    );
    expect(html).toContain("Accepted for decision");
    expect(html).toContain("Next: sign the decision");
  });
});
