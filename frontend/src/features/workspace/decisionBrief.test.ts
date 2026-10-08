import { describe, expect, it } from "vitest";
import {
  actionLines,
  aiDisclosure,
  aiDraftUnedited,
  briefContext,
  briefControls,
  briefLine,
  briefLines,
  briefListPath,
  briefPath,
  briefReview,
  briefReviewBody,
  briefReviewProblem,
  briefStatusView,
  briefTiles,
  briefVersionPath,
  compareBriefs,
  defaultComparison,
  narrativeBody,
  narrativeChanged,
  narrativeFormFrom,
  narrativeGaps,
  narrativeProblem,
  scorecard,
  scorecardHeadline,
  shortHash,
  submitBody,
  summaryCase,
  type BriefVersion,
} from "./decisionBrief";

const UUID = "0b6f8f9e-1111-4222-8333-444455556666";

const v1: BriefVersion = {
  id: "v-1",
  business_id: "DBV000001",
  version: 1,
  status: "RETURNED",
  narrative: {
    problem_statement: "Occlusion alarms rose after release B.",
    proposed_conclusion: "Seal hardness drift is the leading explanation.",
    recommended_actions: ["Test lot KS-5521"],
    author_notes: "",
  },
  content: {
    established_facts: [
      { statement: "12 complaints in scope", epistemic_type: "DERIVED_OBSERVATION", origin: "SYSTEM" },
    ],
    leading_hypothesis: { business_id: "HYP000003", statement: "Seal hardness drift" },
    unknowns: { open: [{ statement: "Lot test data" }], accepted_limitations: [] },
    context: { evidence_set_hash: "sha256:aaaaaaaaaaaaaaaaaaaa", scope_version: 2 },
  },
  content_hash: "1111111111111111",
};

const v2: BriefVersion = {
  ...v1,
  id: "v-2",
  business_id: "DBV000002",
  version: 2,
  status: "DRAFT",
  narrative: {
    ...v1.narrative,
    recommended_actions: ["Test lot KS-5521", "Review supplier change SC-14"],
  },
  content: {
    ...v1.content,
    unknowns: { open: [], accepted_limitations: [{ statement: "Lot test data unavailable" }] },
    context: { evidence_set_hash: "sha256:bbbbbbbbbbbbbbbbbbbb", scope_version: 2 },
  },
  content_hash: "2222222222222222",
};

describe("brief status and hashes", () => {
  it("reads each status by its label", () => {
    expect(briefStatusView({ status: "APPROVED_FOR_DECISION" })).toEqual({
      label: "Approved for decision",
      tone: "good",
    });
    expect(briefStatusView({ status: "UNDER_REVIEW", status_label: "In review" }).label).toBe("In review");
    expect(briefStatusView({ status: "NEW_STATE" }).tone).toBe("neutral");
  });

  it("shortens a hash for comparing at a glance", () => {
    expect(shortHash("sha256:0123456789abcdef0123")).toBe("0123456789ab…");
    expect(shortHash("abc")).toBe("abc");
    expect(shortHash(null)).toBe("—");
    expect(shortHash("")).toBe("—");
  });

  it("addresses the brief and its versions", () => {
    expect(briefPath("i 1")).toBe("/api/v1/investigations/i%201/decision-brief");
    expect(briefPath("i1", "draft/refresh")).toBe("/api/v1/investigations/i1/decision-brief/draft/refresh");
    expect(briefVersionPath("i1", 3, "start-review")).toBe(
      "/api/v1/investigations/i1/decision-brief/versions/3/start-review",
    );
    expect(briefListPath("RETURNED", 2, 10)).toBe("/api/v1/decision-briefs?status=RETURNED&page=2&page_size=10");
  });
});

describe("what the person may do", () => {
  it("shows only what the server allows", () => {
    expect(briefControls(null)).toEqual({
      compose: false,
      edit: false,
      submit: false,
      startReview: false,
      review: false,
    });
    expect(briefControls({ current: null, actions: { can_compose: true, can_edit: true } })).toMatchObject({
      compose: true,
      edit: false,
    });
    const author = briefControls({ current: v2, actions: { can_edit: true, can_submit: true } });
    expect(author).toMatchObject({ edit: true, submit: true, startReview: false, review: false });
  });

  it("offers the review form only while the version is under review", () => {
    const reviewing = { ...v2, status: "UNDER_REVIEW" };
    expect(briefControls({ current: reviewing, actions: { can_review: true } }).review).toBe(true);
    expect(briefControls({ current: v2, actions: { can_review: true } }).review).toBe(false);
  });
});

describe("the author's narrative", () => {
  it("round-trips the narrative through the form", () => {
    const form = narrativeFormFrom(v2.narrative);
    expect(form.actions).toBe("Test lot KS-5521\nReview supplier change SC-14");
    expect(narrativeBody(form)).toEqual({
      problem_statement: "Occlusion alarms rose after release B.",
      proposed_conclusion: "Seal hardness drift is the leading explanation.",
      recommended_actions: ["Test lot KS-5521", "Review supplier change SC-14"],
      author_notes: "",
    });
    expect(narrativeChanged(form, v2.narrative)).toBe(false);
    expect(narrativeChanged({ ...form, notes: "New note" }, v2.narrative)).toBe(true);
  });

  it("reads one action per line, without bullets or empty lines", () => {
    expect(actionLines("- First\n\n  * Second  \n• Third")).toEqual(["First", "Second", "Third"]);
  });

  it("only refuses to save what is too long", () => {
    const form = narrativeFormFrom(null);
    expect(narrativeProblem(form)).toBeNull();
    expect(narrativeProblem({ ...form, proposedConclusion: "x".repeat(5001) })).toMatch(/5000/);
    expect(
      narrativeProblem({ ...form, actions: Array.from({ length: 21 }, (_, i) => `Action ${i}`).join("\n") }),
    ).toMatch(/at most 20/);
  });

  it("flags an AI draft left word for word as the proposed conclusion", () => {
    const narrative = { ai_draft_used: true, ai_draft_text: "Seal  hardness drift explains the alarms." };
    expect(aiDraftUnedited({ proposedConclusion: "seal hardness drift explains the alarms." }, narrative)).toBe(true);
    expect(
      aiDraftUnedited({ proposedConclusion: "Seal hardness drift may explain part of the rise." }, narrative),
    ).toBe(false);
    expect(aiDraftUnedited({ proposedConclusion: "" }, { ai_draft_text: null })).toBe(false);
  });

  it("lists what the narrative still lacks before submitting", () => {
    expect(narrativeGaps(narrativeFormFrom(null), null)).toHaveLength(3);
    expect(narrativeGaps(narrativeFormFrom(v2.narrative), v2.narrative)).toEqual([]);
  });
});

describe("the readiness scorecard", () => {
  const groups = scorecard(
    [
      { key: "scope", label: "Scope recorded", result: "PASS" },
      { key: "risk_review", label: "Risk review", result: "PENDING", rationale: "Requested, not completed" },
      { key: "regulatory_review", label: "Regulatory review", result: "NOT_REQUIRED" },
      { key: "ai", label: "AI disclosure", result: "NOT_AVAILABLE" },
      { key: "evidence", label: "Evidence reviewed", result: "PASS" },
    ],
    [
      { key: "evidence", label: "Evidence reviewed", rationale: "3 records not reviewed" },
      { key: "unknowns", label: "Open unknowns", rationale: "2 open" },
    ],
  );

  it("groups Blocked, Pending, Pass, Not required, and a blocking check always reads Blocked", () => {
    expect(groups.map((group) => [group.label, group.checks.map((check) => check.key)])).toEqual([
      ["Blocked", ["evidence", "unknowns"]],
      ["Pending", ["risk_review", "ai"]],
      ["Pass", ["scope"]],
      ["Not required", ["regulatory_review"]],
    ]);
    expect(groups[0].checks[1].rationale).toBe("2 open");
  });

  it("counts, never a percentage", () => {
    const headline = scorecardHeadline(groups);
    expect(headline).toBe("2 blocked · 2 pending · 1 pass · 1 not required");
    expect(headline).not.toMatch(/%/);
    expect(scorecardHeadline([])).toBe("No readiness checks reported yet.");
  });
});

describe("the quality reviewer's actions", () => {
  it("needs a comment for everything except accepting for decision", () => {
    expect(briefReviewProblem("", "")).toMatch(/Choose/);
    expect(briefReviewProblem("ACCEPT_FOR_DECISION", "")).toBeNull();
    expect(briefReviewProblem("RETURN_FOR_EVIDENCE", "")).toMatch(/at least 10/);
    expect(briefReviewProblem("RETURN_FOR_EVIDENCE", "Lot KS-5521 has no test data.")).toBeNull();
    expect(briefReviewBody("ACCEPT_FOR_DECISION", "  ")).toEqual({ action: "ACCEPT_FOR_DECISION" });
    expect(briefReviewBody("ESCALATE", " Why ")).toEqual({ action: "ESCALATE", comment: "Why" });
    expect(submitBody(" ")).toEqual({});
    expect(submitBody(" Ready ")).toEqual({ comment: "Ready" });
  });
});

describe("the composed sections", () => {
  it("reads a statement with its kind, origin and evidence, never a UUID", () => {
    expect(
      briefLine({
        id: UUID,
        statement: "12 complaints in scope",
        epistemic_type: "FACT",
        origin: "SYSTEM",
        evidence: { business_id: "EVD000004" },
      }),
    ).toMatchObject({
      key: UUID,
      label: "12 complaints in scope",
      kind: "FACT",
      origin: "SYSTEM",
      evidence: "EVD000004",
    });
    expect(briefLine({ id: UUID })).toBeNull();
    expect(briefLines({ items: ["One", { title: "Two" }] }).map((line) => line.label)).toEqual(["One", "Two"]);
    expect(briefLines(null)).toEqual([]);
  });

  it("reads a review summary and the AI disclosure", () => {
    expect(briefReview({ business_id: "REV000003", outcome: "NO_CHANGE_REQUIRED" })).toMatchObject({
      id: "REV000003",
      outcome: "No Change Required",
    });
    expect(briefReview(null)).toBeNull();
    const ai = aiDisclosure({
      ai_assistance: {
        executions: [{ business_id: "AIX000009", kind: "BRIEF_DRAFT", provider: "anthropic", model: "m" }],
        statement: "AI drafted the first conclusion; the author edited it.",
      },
    });
    expect(ai.executions[0]).toMatchObject({ id: "AIX000009", kind: "Brief Draft" });
    expect(ai.statement).toMatch(/author edited/);
    expect(aiDisclosure(null)).toEqual({ executions: [], statement: null });
    expect(briefContext(v1.content).evidenceSetHash).toBe("sha256:aaaaaaaaaaaaaaaaaaaa");
  });
});

describe("comparing two versions", () => {
  it("shows what changed part by part, with the hashes", () => {
    const rows = compareBriefs(v1, v2);
    const row = (key: string) => rows.find((item) => item.key === key)!;
    expect(row("problem").same).toBe(true);
    expect(row("actions").added).toEqual(["Review supplier change SC-14"]);
    expect(row("status")).toMatchObject({ left: ["Returned"], right: ["Draft"] });
    expect(row("unknowns")).toMatchObject({
      removed: ["Open: 1", "Accepted limitations: 0"],
      added: ["Open: 0", "Accepted limitations: 1"],
    });
    expect(row("hash")).toMatchObject({ left: ["111111111111…"], right: ["222222222222…"] });
    expect(row("fingerprint").same).toBe(false);
  });

  it("starts with the latest version and the one before it", () => {
    expect(
      defaultComparison([
        { id: "a", version: 1 },
        { id: "c", version: 3 },
        { id: "b", version: 2 },
      ]),
    ).toEqual([2, 3]);
    expect(defaultComparison([{ id: "a", version: 1 }])).toBeNull();
  });
});

describe("the quality reviewer's dashboard", () => {
  it("reads a summary row, nested or flat", () => {
    expect(
      summaryCase({
        investigation: { id: UUID, business_id: "INV000147", question: "Why?", product_id: "p-1" },
        brief_business_id: "DBV000002",
        version: 2,
        submitted_by_name: "Ina Investigator",
      }),
    ).toMatchObject({
      investigationId: UUID,
      productId: "p-1",
      caseId: "INV000147",
      briefId: "DBV000002",
      version: "2",
      submittedBy: "Ina Investigator",
    });
    expect(
      summaryCase({
        investigation_id: UUID,
        investigation_business_id: "INV000148",
        blocking: ["Scope", { label: "Risk review" }],
      }),
    ).toMatchObject({ investigationId: UUID, caseId: "INV000148", blocking: ["Scope", "Risk review"] });
  });

  it("names every count tile", () => {
    expect(briefTiles({ counts: { awaiting_review: 2 } }).map((tile) => [tile.key, tile.value])).toEqual([
      ["awaiting_review", 2],
      ["under_review_by_me", null],
      ["returned_open", null],
      ["resubmitted", null],
      ["blocked_cases", null],
      ["overdue_cases", null],
    ]);
  });
});
