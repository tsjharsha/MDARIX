import { describe, expect, it } from "vitest";
import {
  EMPTY_COMPLETE,
  REGULATORY_NOTE,
  assessableMarkets,
  assessableRisks,
  completeBody,
  completeProblem,
  contextItem,
  isOpenReview,
  openReviewOf,
  outcomeView,
  outcomesFor,
  parseReviewsTab,
  policyRows,
  regulatoryContext,
  requestReviewBody,
  reviewListPath,
  reviewPath,
  reviewReasonProblem,
  reviewStatusView,
  reviewTiles,
  reviewTypeLabel,
  reviewerText,
  reviewsTab,
  riskContext,
  sortReviews,
  toggled,
  type Review,
} from "./reviews";

const UUID = "0b6f8f9e-1111-4222-8333-444455556666";

describe("how a review reads", () => {
  it("names its type and status, never a raw code", () => {
    expect(reviewTypeLabel({ review_type: "RISK" })).toBe("Risk review");
    expect(reviewTypeLabel({ review_type: "regulatory" })).toBe("Regulatory review");
    expect(reviewTypeLabel({ review_type: "RISK", review_type_label: "Risk file review" })).toBe("Risk file review");
    expect(reviewStatusView({ status: "IN_PROGRESS" })).toEqual({ label: "In progress", tone: "warning" });
    expect(reviewStatusView({ status: "COMPLETED", status_label: "Done" }).label).toBe("Done");
    expect(reviewStatusView({ status: "SOMETHING_NEW" })).toEqual({ label: "Something New", tone: "neutral" });
  });

  it("counts only requested and in-progress reviews as open", () => {
    expect(isOpenReview({ status: "REQUESTED" })).toBe(true);
    expect(isOpenReview({ status: "IN_PROGRESS" })).toBe(true);
    for (const status of ["COMPLETED", "CANCELLED", "SUPERSEDED", undefined])
      expect(isOpenReview({ status })).toBe(false);
  });

  it("offers each kind of review its own outcomes", () => {
    expect(outcomesFor("RISK").map((item) => item.value)).toEqual([
      "NO_CHANGE_REQUIRED",
      "RISK_FILE_REASSESSMENT_REQUIRED",
      "RISK_CONTROL_REVIEW_REQUIRED",
      "ADDITIONAL_EVIDENCE_REQUIRED",
      "ESCALATE_SAFETY_CONCERN",
    ]);
    expect(outcomesFor("REGULATORY").map((item) => item.value)).toEqual([
      "NO_REPORTABILITY_CONCERN_IDENTIFIED",
      "REPORTABILITY_ASSESSMENT_COMPLETE",
      "REPORTING_REQUIRED",
      "TREND_REPORTING_REVIEW_REQUIRED",
      "ADDITIONAL_EVIDENCE_REQUIRED",
      "ESCALATE_REGULATORY",
    ]);
    expect(outcomesFor(null)).toEqual([]);
  });

  it("reads an outcome by its label, the server's first", () => {
    expect(outcomeView({ review_type: "RISK", outcome: "ESCALATE_SAFETY_CONCERN" })).toEqual({
      label: "Escalate a safety concern",
      tone: "critical",
    });
    expect(
      outcomeView({ review_type: "REGULATORY", outcome: "REPORTING_REQUIRED", outcome_label: "Report" })?.label,
    ).toBe("Report");
    expect(outcomeView({ review_type: "RISK", outcome: null })).toBeNull();
  });

  it("names the reviewer, else the queue it waits in, never a UUID", () => {
    expect(reviewerText({ reviewer: { id: UUID, name: "Ana Risk" }, reviewer_role_label: "Risk Reviewer" })).toBe(
      "Ana Risk (Risk Reviewer)",
    );
    expect(reviewerText({ reviewer: null, reviewer_role_label: "Risk Reviewer" })).toBe("Risk Reviewer queue");
    expect(reviewerText({ reviewer: { id: UUID, name: UUID } })).toBe("Not assigned yet");
  });
});

describe("the review policy", () => {
  it("says for each kind whether it is required, and why", () => {
    const rows = policyRows({
      risk: { required: true, reasons: ["Serious injury reported", { label: "Hazard H-12 involved" }] },
      regulatory: { required: false, reasons: [] },
    });
    expect(rows.map((row) => [row.type, row.required])).toEqual([
      ["RISK", true],
      ["REGULATORY", false],
    ]);
    expect(rows[0].reasons).toEqual(["Serious injury reported", "Hazard H-12 involved"]);
    expect(rows[1].text).toMatch(/can still be requested/);
    expect(policyRows(null).every((row) => row.required === null)).toBe(true);
  });

  it("finds the open review of a kind and lists open reviews first, newest first", () => {
    const reviews: Review[] = [
      { id: "a", review_type: "RISK", status: "COMPLETED", created_at: "2026-10-01T10:00:00Z" },
      { id: "b", review_type: "RISK", status: "REQUESTED", created_at: "2026-09-01T10:00:00Z" },
      { id: "c", review_type: "REGULATORY", status: "CANCELLED", created_at: "2026-10-05T10:00:00Z" },
    ];
    expect(openReviewOf(reviews, "RISK")?.id).toBe("b");
    expect(openReviewOf(reviews, "REGULATORY")).toBeNull();
    expect(sortReviews(reviews).map((review) => review.id)).toEqual(["b", "c", "a"]);
  });
});

describe("review actions", () => {
  it("requests a review with only the parts given", () => {
    expect(requestReviewBody("RISK", "  ", null)).toEqual({ review_type: "RISK" });
    expect(requestReviewBody("REGULATORY", " Check EU ", "2026-10-09T21:59:00.000Z")).toEqual({
      review_type: "REGULATORY",
      reason: "Check EU",
      due_at: "2026-10-09T21:59:00.000Z",
    });
  });

  it("asks for an outcome of the review's kind and a rationale of 20 to 5000 characters", () => {
    expect(completeProblem("RISK", EMPTY_COMPLETE)).toMatch(/Choose the outcome/);
    expect(completeProblem("RISK", { ...EMPTY_COMPLETE, outcome: "REPORTING_REQUIRED" })).toMatch(
      /one of the outcomes/,
    );
    expect(
      completeProblem("RISK", { ...EMPTY_COMPLETE, outcome: "NO_CHANGE_REQUIRED", rationale: "Too short" }),
    ).toMatch(/at least 20/);
    const ready = { ...EMPTY_COMPLETE, outcome: "NO_CHANGE_REQUIRED", rationale: "The risk file covers this hazard." };
    expect(completeProblem("RISK", ready)).toBeNull();
    expect(completeProblem("RISK", { ...ready, rationale: "x".repeat(5001) })).toMatch(/5000/);
  });

  it("sends only the assessed parts that were filled in", () => {
    expect(
      completeBody({
        outcome: "NO_CHANGE_REQUIRED",
        rationale: " Reason given here ",
        riskIds: [],
        markets: [],
        notes: " ",
      }),
    ).toEqual({ outcome: "NO_CHANGE_REQUIRED", rationale: "Reason given here", assessed: {} });
    expect(
      completeBody({ outcome: "REPORTING_REQUIRED", rationale: "r", riskIds: ["r-1"], markets: ["DE"], notes: "n" }),
    ).toEqual({
      outcome: "REPORTING_REQUIRED",
      rationale: "r",
      assessed: { risk_ids: ["r-1"], markets: ["DE"], notes: "n" },
    });
  });

  it("asks a reason of 10 to 1000 characters to recuse or cancel", () => {
    expect(reviewReasonProblem("short")).toMatch(/at least 10/);
    expect(reviewReasonProblem("I reviewed the design of this device.")).toBeNull();
    expect(reviewReasonProblem("x".repeat(1001))).toMatch(/1000/);
  });

  it("toggles one value of a multi-select", () => {
    expect(toggled(["a"], "b", true)).toEqual(["a", "b"]);
    expect(toggled(["a", "b"], "a", false)).toEqual(["b"]);
    expect(toggled(["a"], "a", true)).toEqual(["a"]);
  });

  it("addresses reviews and their actions", () => {
    expect(reviewPath("r 1")).toBe("/api/v1/case-reviews/r%201");
    expect(reviewPath("r1", "complete")).toBe("/api/v1/case-reviews/r1/complete");
    expect(reviewListPath({ type: "RISK", box: "queue" })).toBe(
      "/api/v1/case-reviews?type=RISK&box=queue&page=1&page_size=50",
    );
  });
});

describe("the Reviews tab link", () => {
  it("opens one review by its reference, and ignores anything else", () => {
    expect(reviewsTab(UUID)).toBe(`Reviews?review=${UUID}`);
    expect(reviewsTab(null)).toBe("Reviews");
    expect(reviewsTab("bad ref!")).toBe("Reviews");
    expect(parseReviewsTab(`Reviews?review=${UUID}`)).toBe(UUID);
    expect(parseReviewsTab("Reviews")).toBeNull();
    expect(parseReviewsTab("Scope?review=abc")).toBeNull();
    expect(parseReviewsTab("Reviews?review=<script>")).toBeNull();
  });
});

describe("the review context", () => {
  it("reads a listed record by its business ID and text, never its UUID", () => {
    expect(contextItem({ id: UUID, business_id: "RSK000004", title: "Occlusion not detected" })).toMatchObject({
      id: UUID,
      label: "RSK000004 · Occlusion not detected",
    });
    expect(contextItem({ id: UUID })).toBeNull();
    expect(contextItem("Plain text")).toMatchObject({ label: "Plain text", id: null });
  });

  it("reads the risk context defensively", () => {
    const risk = riskContext({
      risks: [{ id: "r-1", business_id: "RSK000001", title: "Under-infusion" }],
      hazards: [{ id: "h-1", business_id: "HAZ000002", name: "Occlusion" }],
      controls: [],
      hypotheses: [
        {
          business_id: "HYP000003",
          statement: "Seal hardness drift",
          human_judgement: { status: "PARTIALLY_SUPPORTED" },
          evidence_counts: { supporting: 2, contradicting: 1 },
          origin: "AI",
        },
      ],
      contradictions_count: 3,
      open_unknowns: [{ business_id: "UNK000001", statement: "Lot KS-5521 test data" }],
    });
    expect(risk.risks).toHaveLength(1);
    expect(risk.hypotheses[0]).toMatchObject({
      label: "HYP000003 · Seal hardness drift",
      judgement: "Partially Supported",
      supporting: 2,
      contradicting: 1,
      origin: "AI",
    });
    expect(risk.contradictions).toBe(3);
    expect(risk.openUnknowns[0].label).toBe("UNK000001 · Lot KS-5521 test data");
    expect(assessableRisks(risk).map((item) => item.id)).toEqual(["r-1", "h-1"]);
    expect(riskContext(null)).toMatchObject({ risks: [], hypotheses: [], contradictions: null });
  });

  it("reads the regulatory context, and always says people determine reportability", () => {
    const regulatory = regulatoryContext({
      complaints: [
        {
          business_id: "CMP000001",
          description: "Alarm",
          country: "DE",
          event_date: "2026-09-01",
          serious_injury: true,
        },
        { business_id: "CMP000002", description: "Leak", market: "US", malfunction: true, death: false },
      ],
      counts_by_market: { DE: 1, US: 1 },
      earliest_awareness_date: "2026-09-02",
    });
    expect(regulatory.complaints.map((item) => [item.market, item.flags])).toEqual([
      ["DE", ["Serious injury"]],
      ["US", ["Malfunction"]],
    ]);
    expect(regulatory.markets).toEqual([
      { market: "DE", count: 1 },
      { market: "US", count: 1 },
    ]);
    expect(regulatory.earliestAwareness).toBe("2026-09-02");
    expect(regulatory.note).toBe(REGULATORY_NOTE);
    expect(assessableMarkets(regulatory)).toEqual(["DE", "US"]);
    expect(
      regulatoryContext({
        counts_by_market: [{ market: "FR", count: 2 }],
        complaints: [{ business_id: "C1", market: "IT" }],
      }).markets,
    ).toEqual([{ market: "FR", count: 2 }]);
    expect(regulatoryContext(undefined)).toMatchObject({ complaints: [], markets: [], earliestAwareness: null });
  });
});

describe("the reviewer's dashboard tiles", () => {
  it("shows a queue only for a role the person holds, and counts as given", () => {
    const tiles = reviewTiles({
      roles: { risk: true, regulatory: false },
      counts: { risk_queue: 2, regulatory_queue: 0, mine_open: 1, overdue: 1, completed_30d: 4 },
    });
    expect(tiles.map((tile) => tile.key)).toEqual(["risk_queue", "mine_open", "due_soon", "overdue", "completed_30d"]);
    expect(tiles.find((tile) => tile.key === "due_soon")?.value).toBeNull();
    expect(reviewTiles({ counts: { regulatory_queue: 3 } }).map((tile) => tile.key)).toContain("regulatory_queue");
  });
});
