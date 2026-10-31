import { describe, expect, it } from "vitest";
import { ApiError } from "../../app/apiClient";
import {
  acknowledgementRequired,
  caseDecisionPath,
  credentialsProblem,
  decisionDraftBody,
  decisionFormProblems,
  decisionHistory,
  decisionRecordPath,
  decisionRef,
  decisionTiles,
  decisionsQueuePath,
  emptyDecisionForm,
  emptyFollowUp,
  failedChecks,
  followUpOptions,
  hashState,
  isCaseDecision,
  outcomeLabel,
  outcomeOptions,
  outcomeRules,
  queueRow,
  recentDecision,
  requiredReviewLabels,
  returnBody,
  returnProblem,
  reviewerLine,
  signBody,
  signErrorView,
  signatureMeaning,
  signedDecisionRef,
  sortQueue,
  verificationChecks,
  verificationHeadline,
  verificationView,
  type DecisionForm,
} from "./humanDecision";

const UUID = "0b6f8f9e-1111-4222-8333-444455556666";
const OTHER = "9d1c2b3a-1111-4222-8333-444455556666";
const RATIONALE = "The evidence in the brief supports the proposed conclusion.";
const context = { briefVersionId: UUID, briefContentHash: "sha256:abc123", supersedesDecisionId: null };

// Attributed by default: the attribution's own rule has its own test below.
const form = (change: Partial<DecisionForm> = {}): DecisionForm => ({
  ...emptyDecisionForm(),
  attribution: "DEVICE_RELATED",
  ...change,
});

describe("addresses", () => {
  it("builds the decision addresses", () => {
    expect(decisionsQueuePath(0, 20)).toBe("/api/v1/decisions/queue?page=1&page_size=20");
    // A column heading's sort orders the whole queue on the server.
    expect(decisionsQueuePath(2, 20, { key: "awaitingSince", direction: "descending" })).toBe(
      "/api/v1/decisions/queue?page=2&page_size=20&sort=awaitingSince&order=desc",
    );
    expect(caseDecisionPath(UUID)).toBe(`/api/v1/investigations/${UUID}/decision`);
    expect(caseDecisionPath(UUID, "sign")).toBe(`/api/v1/investigations/${UUID}/decision/sign`);
    expect(caseDecisionPath(UUID, "return")).toBe(`/api/v1/investigations/${UUID}/decision/return`);
    expect(decisionRecordPath(UUID)).toBe(`/api/v1/decisions/${UUID}/record`);
  });
});

describe("outcomes and their rules", () => {
  it("offers the server's outcomes with its words, else the four known ones", () => {
    expect(outcomeOptions(null).map((item) => item.code)).toEqual([
      "ACCEPT_CONCLUSION",
      "ACCEPT_WITH_CONDITIONS",
      "REJECT_CONCLUSION",
      "CLOSE_NO_FURTHER_ACTION",
    ]);
    expect(outcomeOptions([{ code: "ACCEPT_CONCLUSION", label: "Accept", description: "As written." }])).toEqual([
      { code: "ACCEPT_CONCLUSION", label: "Accept", description: "As written." },
    ]);
    expect(outcomeOptions([{ code: "REJECT_CONCLUSION" }])[0].label).toBe("Reject the conclusion");
    // The words the signature will carry come from the server, so the form shows exactly what is stored.
    const meaning =
      "I, Asha Rao, Leader (Quality Manager), have reviewed Decision Brief DBV000001 version 1 and decide";
    expect(outcomeOptions([{ code: "ACCEPT_CONCLUSION", signature_meaning: meaning }])[0].signatureMeaning).toBe(
      meaning,
    );
    expect(followUpOptions(undefined)).toHaveLength(5);
    expect(followUpOptions([{ code: "CAPA_REQUIRED" }])).toEqual([{ code: "CAPA_REQUIRED", label: "CAPA required" }]);
  });

  it("asks for conditions only to accept with conditions, and follow-ups only to accept", () => {
    expect(outcomeRules("ACCEPT_CONCLUSION")).toEqual({ conditions: false, followUps: true });
    expect(outcomeRules("ACCEPT_WITH_CONDITIONS")).toEqual({ conditions: true, followUps: true });
    expect(outcomeRules("REJECT_CONCLUSION")).toEqual({ conditions: false, followUps: false });
    expect(outcomeRules("CLOSE_NO_FURTHER_ACTION")).toEqual({ conditions: false, followUps: false });
    expect(outcomeRules("")).toEqual({ conditions: false, followUps: false });
  });

  it("labels outcomes, never as a raw code", () => {
    expect(outcomeLabel("ACCEPT_WITH_CONDITIONS")).toBe("Accept with conditions");
    expect(outcomeLabel("SOMETHING_NEW")).toBe("Something New");
    expect(outcomeLabel("ACCEPT_CONCLUSION", "Accepted")).toBe("Accepted");
    expect(outcomeLabel(null)).toBe("—");
  });
});

describe("the brief for the decision maker", () => {
  it("asks for an acknowledgement when the brief lists open unknowns or accepted limitations", () => {
    expect(acknowledgementRequired({ unknowns: { open: [{ statement: "Lot 7 not tested" }] } })).toBe(true);
    expect(acknowledgementRequired({ unknowns: { accepted_limitations: ["No field data"] } })).toBe(true);
    expect(acknowledgementRequired({ unknowns: { open: [], accepted_limitations: [] } })).toBe(false);
    expect(acknowledgementRequired(null)).toBe(false);
  });

  it("says whether the brief still matches its fingerprint", () => {
    expect(hashState({ hash_verified: true }).label).toBe("Verified");
    expect(hashState({ hash_verified: false }).tone).toBe("critical");
    expect(hashState({}).key).toBe("unchecked");
  });

  it("reads a reviewer line without codes or UUIDs", () => {
    // A quality review action is one plain sentence, never "Quality · Start Review" (UX-21).
    expect(
      reviewerLine({ kind: "QUALITY_REVIEW", name: "Ana Silva", role: "REVIEWER", action: "ACCEPT_FOR_DECISION" }),
    ).toMatchObject({ kind: "Accepted for decision", name: "Ana Silva", action: null });
    expect(reviewerLine({ kind: "QUALITY", action: "START_REVIEW", label: "Quality review started" })).toMatchObject({
      kind: "Quality review started",
      action: null,
    });
    expect(reviewerLine({ kind: "RISK", action: "COMPLETED", outcome: "NO_NEW_RISK" })).toMatchObject({
      kind: "Risk review",
      action: "No new risk",
    });
    expect(reviewerLine({ name: UUID }).name).toBeNull();
  });
});

describe("the decision form", () => {
  const ready = { acknowledgementRequired: false, supersedes: false };

  it("names what is still missing", () => {
    expect(decisionFormProblems(form(), ready)).toEqual([
      "Choose an outcome.",
      expect.stringMatching(/rationale of at least 20/),
    ]);
    expect(decisionFormProblems(form({ outcome: "ACCEPT_CONCLUSION", rationale: RATIONALE }), ready)).toEqual([]);
  });

  it("requires the root-cause attribution, and a reason for undetermined", () => {
    const signed = form({ outcome: "ACCEPT_CONCLUSION", rationale: RATIONALE });
    expect(decisionFormProblems({ ...signed, attribution: "" }, ready)).toEqual(["Choose the root-cause attribution."]);
    expect(decisionFormProblems({ ...signed, attribution: "UNDETERMINED" }, ready)[0]).toMatch(/Undetermined/);
    expect(
      decisionFormProblems({ ...signed, attribution: "UNDETERMINED", attributionReason: "Device not returned" }, ready),
    ).toEqual([]);
  });

  it("requires conditions, the acknowledgement and the supersede reason when they apply", () => {
    const conditional = form({ outcome: "ACCEPT_WITH_CONDITIONS", rationale: RATIONALE });
    expect(decisionFormProblems(conditional, ready).join(" ")).toMatch(/conditions/);
    expect(decisionFormProblems({ ...conditional, conditions: "Complete CAPA by Q1." }, ready)).toEqual([]);
    const plain = form({ outcome: "REJECT_CONCLUSION", rationale: RATIONALE });
    expect(decisionFormProblems(plain, { acknowledgementRequired: true, supersedes: false })[0]).toMatch(/Acknowledge/);
    expect(
      decisionFormProblems({ ...plain, acknowledged: true }, { acknowledgementRequired: true, supersedes: false }),
    ).toEqual([]);
    expect(decisionFormProblems(plain, { acknowledgementRequired: false, supersedes: true })[0]).toMatch(/supersedes/);
    expect(
      decisionFormProblems(
        { ...plain, supersedeReason: "New field data changes the picture." },
        { acknowledgementRequired: false, supersedes: true },
      ),
    ).toEqual([]);
  });

  it("checks a chosen follow-up's title and due date", () => {
    const followUps = { CAPA_REQUIRED: { ...emptyFollowUp(), selected: true, dueDay: "not a day" } };
    expect(
      decisionFormProblems(form({ outcome: "ACCEPT_CONCLUSION", rationale: RATIONALE, followUps }), ready)[0],
    ).toMatch(/valid due date/);
  });
});

describe("the signature request", () => {
  it("sends only what the outcome takes, without any secret in the decision part", () => {
    const followUps = {
      RISK_REASSESSMENT_REQUIRED: { ...emptyFollowUp(), selected: true },
      CAPA_REQUIRED: {
        selected: true,
        title: "  Fix the seal  ",
        assigneeUserId: OTHER,
        assignedRole: "INVESTIGATOR",
        dueDay: "2026-11-30",
      },
      PRODUCT_CHANGE_REQUIRED: { ...emptyFollowUp(), selected: false, title: "ignored" },
    };
    const draft = decisionDraftBody(
      form({
        outcome: "ACCEPT_WITH_CONDITIONS",
        rationale: `  ${RATIONALE}  `,
        conditions: " Complete CAPA by Q1. ",
        followUps,
        acknowledged: true,
      }),
      context,
    );
    expect(draft).toMatchObject({
      brief_version_id: UUID,
      brief_content_hash: "sha256:abc123",
      outcome: "ACCEPT_WITH_CONDITIONS",
      rationale: RATIONALE,
      conditions: "Complete CAPA by Q1.",
      residual_unknowns_acknowledged: true,
    });
    expect(draft.follow_ups).toEqual([
      {
        action_type: "CAPA_REQUIRED",
        title: "Fix the seal",
        assignee_user_id: OTHER,
        due_at: expect.stringMatching(/^2026-1[12]-/),
      },
      { action_type: "RISK_REASSESSMENT_REQUIRED" },
    ]);
    expect(draft).not.toHaveProperty("password");
    expect(draft).not.toHaveProperty("mfa_code");
    expect(draft).not.toHaveProperty("supersedes_decision_id");
  });

  it("drops conditions and follow-ups for an outcome that does not take them", () => {
    const draft = decisionDraftBody(
      form({
        outcome: "REJECT_CONCLUSION",
        rationale: RATIONALE,
        conditions: "left over",
        followUps: { CAPA_REQUIRED: { ...emptyFollowUp(), selected: true } },
      }),
      context,
    );
    expect(draft).not.toHaveProperty("conditions");
    expect(draft).not.toHaveProperty("follow_ups");
    expect(draft.residual_unknowns_acknowledged).toBe(false);
  });

  it("names the decision it supersedes, with the reason", () => {
    const draft = decisionDraftBody(
      form({ outcome: "ACCEPT_CONCLUSION", rationale: RATIONALE, supersedeReason: " New data " }),
      {
        ...context,
        supersedesDecisionId: OTHER,
      },
    );
    expect(draft).toMatchObject({ supersedes_decision_id: OTHER, supersede_reason: "New data" });
  });

  it("adds the password and code to this one body only, and never changes the form", () => {
    const filled = form({ outcome: "CLOSE_NO_FURTHER_ACTION", rationale: RATIONALE });
    const before = JSON.stringify(filled);
    const body = signBody(filled, context, { password: "s3cret!", mfaCode: "12 34 56" });
    expect(body).toMatchObject({ password: "s3cret!", mfa_code: "123456", outcome: "CLOSE_NO_FURTHER_ACTION" });
    expect(JSON.stringify(filled)).toBe(before);
    expect(JSON.stringify(filled)).not.toContain("s3cret!");
    expect(signBody(filled, context, { password: "x" })).not.toHaveProperty("mfa_code");
  });

  it("checks the credentials before sending", () => {
    expect(credentialsProblem({ password: "" })).toMatch(/password/);
    expect(credentialsProblem({ password: "x", mfaCode: "12" })).toMatch(/6-digit/);
    expect(credentialsProblem({ password: "x", mfaCode: "123456" })).toBeNull();
    expect(credentialsProblem({ password: "x" })).toBeNull();
  });

  it("says what a signature means before signing", () => {
    const text = signatureMeaning({
      signer: "Ana Silva",
      role: "Authorized Decision Maker",
      outcome: "ACCEPT_CONCLUSION",
      caseId: "INV000147",
      briefId: "DBV000002",
      version: 3,
      contentHash: "sha256:0123456789abcdef0123",
    });
    expect(text).toBe(
      "I, Ana Silva, Authorized Decision Maker, have reviewed DBV000002 version 3 (fingerprint 0123456789ab…) for " +
        "INV000147 and decide: Accept the conclusion. My signature applies to this decision and this brief version only.",
    );
    expect(signatureMeaning({ outcome: "Reject the conclusion" })).toMatch(/^I have reviewed the Decision Brief and/);
  });

  it("turns refusals into what to do next, never echoing a password", () => {
    const stale = signErrorView(new ApiError("Stale", 409, "STALE_BRIEF"));
    expect(stale.reload).toBe(true);
    expect(signErrorView(new ApiError("x", 409, "SUPERSEDE_REQUIRED")).reload).toBe(true);
    expect(signErrorView(new ApiError("x", 409, "BRIEF_TAMPERED")).text).toMatch(/fingerprint/);
    expect(signErrorView(new ApiError("x", 403, "SOD_DENIED")).text).toMatch(/another authorized decision maker/);
    expect(signErrorView(new ApiError("x", 403, "ADMINISTRATOR_CANNOT_SIGN")).text).toMatch(/Administrators never/);
    const wrong = signErrorView(new ApiError("The password is not correct.", 401, "INVALID_REAUTHENTICATION"));
    expect(wrong).toEqual({ text: "The password is not correct.", reload: false, credentials: true });
    expect(signErrorView(new Error("boom")).text).toBe("boom");
  });

  it("finds the signed decision a signature request returned", () => {
    expect(signedDecisionRef({ id: UUID, business_id: "DEC000004" })).toEqual({ ref: UUID, label: "DEC000004" });
    expect(signedDecisionRef({ decision: { id: UUID, business_id: "DEC000004" } })).toEqual({
      ref: UUID,
      label: "DEC000004",
    });
    expect(signedDecisionRef(null)).toEqual({ ref: null, label: "The decision" });
  });

  it("returns a brief with a comment, without a signature", () => {
    expect(returnBody(UUID, "  Needs the lot 7 test results.  ")).toEqual({
      brief_version_id: UUID,
      comment: "Needs the lot 7 test results.",
    });
    expect(returnProblem("short")).toMatch(/at least 10/);
    expect(returnProblem("Needs the lot 7 test results.")).toBeNull();
  });
});

describe("the approvals queue", () => {
  const item = (change: Record<string, unknown>, investigation: Record<string, unknown> = {}) => ({
    investigation: { id: UUID, business_id: "INV000147", question: "Why?", ...investigation },
    brief: { id: OTHER, business_id: "DBV000002", version: 2, approved_at: "2026-10-01T10:00:00Z" },
    ...change,
  });

  it("reads a queue row with business IDs, never UUIDs", () => {
    const row = queueRow(
      item(
        { critical: true, required_reviews: ["RISK_REVIEW", { kind: "REGULATORY_REVIEW", status: "COMPLETED" }] },
        { product: { id: OTHER, business_id: "PRD000001", name: "Pump" }, priority: "HIGH" },
      ),
    );
    expect(row).toMatchObject({
      investigationId: UUID,
      productId: OTHER,
      caseId: "INV000147",
      product: "Pump",
      briefId: "DBV000002",
      version: "2",
      critical: true,
      requiredReviews: ["Risk Review", "Regulatory Review: Completed"],
      awaitingSince: "2026-10-01T10:00:00Z",
      canDecide: true,
    });
    expect(queueRow({ actions: { can_decide: false, reason: "You reviewed this brief." } }).reason).toBe(
      "You reviewed this brief.",
    );
    expect(requiredReviewLabels(null)).toEqual([]);
  });

  it("puts critical first, then overdue, priority, nearest due and longest waiting", () => {
    const rows = [
      queueRow(item({ awaiting_since: "2026-10-03T00:00:00Z" }, { business_id: "INV1", priority: "LOW" })),
      queueRow(item({}, { business_id: "INV2", priority: "LOW", due_at: "2020-01-01T00:00:00Z" })),
      queueRow(item({ critical: true }, { business_id: "INV3", priority: "LOW" })),
      queueRow(item({}, { business_id: "INV4", priority: "CRITICAL" })),
      queueRow(item({ awaiting_since: "2026-09-01T00:00:00Z" }, { business_id: "INV5", priority: "LOW" })),
    ];
    expect(sortQueue(rows).map((row) => row.caseId)).toEqual(["INV3", "INV2", "INV4", "INV5", "INV1"]);
  });

  it("reads the summary tiles and recent decisions", () => {
    const tiles = decisionTiles({ counts: { awaiting_signature: 3, overdue: 1 } });
    expect(tiles.find((tile) => tile.key === "awaiting_signature")?.value).toBe(3);
    expect(tiles.find((tile) => tile.key === "critical")?.value).toBeNull();
    expect(tiles.find((tile) => tile.key === "overdue")?.urgent).toBe(true);
    expect(
      recentDecision({
        decision_id: UUID,
        decision_business_id: "DEC000004",
        case_business_id: "INV000147",
        outcome: "REJECT_CONCLUSION",
        decided_at: "2026-10-02T10:00:00Z",
        signer_name: "Ana Silva",
      }),
    ).toMatchObject({
      ref: UUID,
      decisionId: "DEC000004",
      caseId: "INV000147",
      outcome: "Reject the conclusion",
      outcomeTone: "critical",
      signer: "Ana Silva",
    });
    expect(recentDecision({ business_id: "DEC000005" }).ref).toBe("DEC000005");
  });
});

describe("the signed record", () => {
  it("reads the verification and names the checks that failed", () => {
    expect(verificationView("VALID")).toEqual({ label: "Valid", tone: "good" });
    expect(verificationView("INVALID").tone).toBe("critical");
    expect(verificationView("SOMETHING").tone).toBe("warning");
    const checks = verificationChecks([
      { key: "signature_fingerprint", ok: true },
      { key: "brief_hash", ok: false, detail: "Hash differs" },
      { key: "custom_check", label: "Our own check", ok: "yes" },
    ]);
    expect(checks.map((check) => check.label)).toEqual([
      "The signature fingerprint matches the signed decision",
      "The brief still matches the content that was signed",
      "Our own check",
    ]);
    expect(failedChecks(checks).map((check) => check.key)).toEqual(["brief_hash", "custom_check"]);
    expect(verificationHeadline("INVALID", checks)).toBe(
      "Invalid: The brief still matches the content that was signed; Our own check",
    );
    expect(verificationHeadline("VALID", [])).toBe("Valid");
    expect(verificationChecks(null)).toEqual([]);
  });

  it("links supersede references by id, shown by business ID", () => {
    expect(decisionRef({ id: UUID, business_id: "DEC000003" })).toEqual({ id: UUID, label: "DEC000003" });
    expect(decisionRef(null, UUID)).toEqual({ id: UUID, label: "Decision" });
    expect(decisionRef("DEC000003")).toEqual({ id: "DEC000003", label: "DEC000003" });
    expect(decisionRef(null)).toBeNull();
  });

  it("lists the decision history current first, then superseded newest first", () => {
    const rows = decisionHistory(
      [
        {
          id: OTHER,
          business_id: "DEC000003",
          outcome: "ACCEPT_CONCLUSION",
          status: "SUPERSEDED",
          decided_at: "2026-09-01T00:00:00Z",
          superseded_by: { id: UUID, business_id: "DEC000004" },
        },
        {
          id: UUID,
          business_id: "DEC000004",
          outcome: "REJECT_CONCLUSION",
          decided_at: "2026-10-01T00:00:00Z",
          supersedes: { id: OTHER, business_id: "DEC000003" },
        },
      ],
      { id: UUID, business_id: "DEC000004" },
    );
    expect(rows.map((row) => [row.businessId, row.status])).toEqual([
      ["DEC000004", "Current"],
      ["DEC000003", "Superseded"],
    ]);
    expect(rows[0].supersedes).toEqual({ id: OTHER, label: "DEC000003" });
    expect(rows[1].supersededBy).toEqual({ id: UUID, label: "DEC000004" });
    expect(decisionHistory(null, null)).toEqual([]);
  });

  it("recognises a signed case decision in the decision list or its verification report", () => {
    expect(isCaseDecision({ outcome: "ACCEPT_CONCLUSION" })).toBe(true);
    expect(isCaseDecision({ brief_version_id: UUID })).toBe(true);
    expect(isCaseDecision({ kind: "case_decision" })).toBe(true);
    expect(isCaseDecision({ selected_action: "NO_DECISION_YET" })).toBe(false);
    expect(isCaseDecision({}, { signatures: [{ object_type: "CASE_DECISION" }] })).toBe(true);
    expect(isCaseDecision(null, null)).toBe(false);
  });
});
