import { describe, expect, it } from "vitest";
import {
  caseFollowUpsPath,
  caseImpactAssessmentsPath,
  closureAllowed,
  closureCheckPath,
  closureCriteria,
  closureHeadline,
  findByRef,
  followUpActionBody,
  followUpActionProblem,
  followUpActions,
  followUpAssignee,
  followUpCapaText,
  followUpQmsReferencePath,
  followUpCounts,
  followUpDecisionText,
  followUpListPath,
  followUpOverdue,
  followUpPath,
  followUpStatusView,
  followUpTypeLabel,
  impactBody,
  impactCanComplete,
  impactCompletePath,
  impactConclusionView,
  impactProblem,
  impactStatusView,
  impactTriggerLabel,
} from "./afterDecision";
import { capaQmsText } from "./effectiveness";

const UUID = "0b6f8f9e-1111-4222-8333-444455556666";
const NOTE = "Seal supplier changed and verified.";

describe("follow-up actions", () => {
  it("builds the follow-up addresses", () => {
    expect(caseFollowUpsPath(UUID)).toBe(`/api/v1/investigations/${UUID}/follow-ups`);
    expect(followUpPath(UUID)).toBe(`/api/v1/follow-ups/${UUID}`);
    expect(followUpPath(UUID, "capa")).toBe(`/api/v1/follow-ups/${UUID}/capa`);
    expect(followUpListPath("mine", "OPEN", 0, 5)).toBe("/api/v1/follow-ups?box=mine&status=OPEN&page=1&page_size=5");
    expect(followUpListPath()).toBe("/api/v1/follow-ups?box=mine&page=1&page_size=20");
  });

  it("reads a follow-up's kind, status and holder in words", () => {
    expect(followUpTypeLabel({ action_type: "FIELD_ACTION_REVIEW_REQUIRED" })).toBe("Field action review required");
    expect(followUpTypeLabel({ action_type: "X", action_label: "Supplier audit" })).toBe("Supplier audit");
    expect(followUpTypeLabel({})).toBe("Follow-up");
    expect(followUpStatusView({ status: "IN_PROGRESS" })).toEqual({ label: "In progress", tone: "warning" });
    expect(followUpStatusView({ status: "DONE" }).tone).toBe("good");
    expect(followUpAssignee({ assignee: { id: UUID, name: "Ana Silva" } })).toBe("Ana Silva");
    expect(followUpAssignee({ assignee: null, assigned_role: "INVESTIGATOR" })).toBe("Quality Investigator (role)");
    expect(followUpAssignee({ assigned_role: "X", assigned_role_label: "Site lead" })).toBe("Site lead (role)");
    expect(followUpAssignee({ assignee: UUID })).toBe("Unassigned");
  });

  it("flags an open follow-up past its due date, never a finished one", () => {
    expect(followUpOverdue({ due_at: "2020-01-01T00:00:00Z", status: "OPEN" })).toBe(true);
    expect(followUpOverdue({ due_at: "2020-01-01T00:00:00Z", status: "DONE" })).toBe(false);
    expect(followUpOverdue({ due_at: null, overdue: true, status: "IN_PROGRESS" })).toBe(true);
    expect(followUpOverdue({ due_at: "2999-01-01T00:00:00Z", status: "OPEN" })).toBe(false);
    expect(
      followUpCounts([
        { id: "1", status: "OPEN", due_at: "2020-01-01T00:00:00Z" },
        { id: "2", status: "IN_PROGRESS" },
        { id: "3", status: "CANCELLED", due_at: "2020-01-01T00:00:00Z" },
      ]),
    ).toEqual({ open: 2, overdue: 1 });
  });

  it("offers only what the server allows, in a fixed order", () => {
    expect(followUpActions({ actions: { can_cancel: true, can_start: true, can_create_capa: true } })).toEqual([
      "start",
      "capa",
      "cancel",
    ]);
    expect(followUpActions({ actions: null })).toEqual([]);
  });

  it("checks and builds each action's body", () => {
    expect(followUpActionProblem("start", { text: "" })).toBeNull();
    expect(followUpActionBody("start", { text: "" })).toBeUndefined();
    expect(followUpActionProblem("complete", { text: "done" })).toMatch(/at least 10/);
    expect(followUpActionBody("complete", { text: `  ${NOTE}  ` })).toEqual({ note: NOTE });
    expect(followUpActionProblem("cancel", { text: "" })).toMatch(/reason/);
    expect(followUpActionBody("cancel", { text: "Superseded by CAPA-12." })).toEqual({
      reason: "Superseded by CAPA-12.",
    });
    expect(followUpActionProblem("capa", { text: "Fix seal", dueDay: "nope" })).toMatch(/valid due date/);
    expect(followUpActionProblem("capa", { text: "Fix seal" })).toBeNull();
    expect(followUpActionBody("capa", { text: " Fix seal " })).toEqual({ title: "Fix seal" });
    expect(followUpActionBody("capa", { text: "Fix seal", dueDay: "2026-12-01" })).toEqual({
      title: "Fix seal",
      due_at: expect.stringMatching(/^2026-12-0[12]T/),
    });
  });

  it("names the decision and the CAPA by their business IDs", () => {
    expect(followUpDecisionText({ decision: { business_id: "DEC000004", outcome: "ACCEPT_CONCLUSION" } })).toBe(
      "DEC000004 · Accept the conclusion",
    );
    expect(followUpDecisionText({ decision: null })).toBe("—");
    expect(followUpCapaText({ capa: { business_id: "CAPA000002", capa_identifier: "CAPA-INV1-1" } })).toBe(
      "CAPA000002 (CAPA-INV1-1) · To raise in your QMS",
    );
    expect(
      followUpCapaText({
        capa: { business_id: "CAPA000002", capa_identifier: "CAPA-INV1-1", qms_reference: "QMS-77" },
      }),
    ).toBe("CAPA000002 (CAPA-INV1-1) · QMS reference QMS-77");
    expect(followUpCapaText({ capa: null })).toBeNull();
  });

  it("sends the CAPA's QMS reference when given (J22)", () => {
    expect(followUpActionBody("capa", { text: "Fix seal", qmsReference: " CAPA-0450 " })).toEqual({
      title: "Fix seal",
      qms_reference: "CAPA-0450",
    });
    expect(followUpQmsReferencePath(UUID)).toBe(`/api/v1/follow-ups/${UUID}/capa/qms-reference`);
    // Wherever the CAPA shows: the Records CAPA list and the effectiveness board read the same words.
    expect(capaQmsText({ qms_reference: "CAPA-0450", source_system: "MDARIX" })).toBe("QMS reference CAPA-0450");
    expect(capaQmsText({ qms_reference: null, source_system: "MDARIX" })).toBe("To raise in your QMS");
    expect(capaQmsText({ source_system: "TRACKWISE" })).toBeNull();
  });

  it("finds the record a task names, by id or business ID", () => {
    const rows = [
      { id: UUID, business_id: "FUP000001" },
      { id: "other", business_id: "FUP000002" },
    ];
    expect(findByRef(rows, UUID)?.business_id).toBe("FUP000001");
    expect(findByRef(rows, "fup000002")?.id).toBe("other");
    expect(findByRef(rows, "FUP000009")).toBeNull();
    expect(findByRef(rows, null)).toBeNull();
  });
});

describe("impact assessments", () => {
  it("builds the addresses and the body", () => {
    expect(caseImpactAssessmentsPath(UUID)).toBe(`/api/v1/investigations/${UUID}/impact-assessments`);
    expect(impactCompletePath(UUID)).toBe(`/api/v1/impact-assessments/${UUID}/complete`);
    expect(impactBody("NO_IMPACT", "  The new test confirms the original finding.  ")).toEqual({
      conclusion: "NO_IMPACT",
      rationale: "The new test confirms the original finding.",
    });
  });

  it("asks for a conclusion and a rationale of at least 20 characters", () => {
    expect(impactProblem("", "The new test confirms the original finding.")).toBe("Choose your conclusion.");
    expect(impactProblem("MATERIAL_IMPACT", "Too short")).toMatch(/at least 20/);
    expect(impactProblem("MATERIAL_IMPACT", "The new lot data contradicts the conclusion.")).toBeNull();
  });

  it("reads an assessment in words", () => {
    expect(impactTriggerLabel({ trigger: "EVIDENCE_LINKED" })).toBe("Evidence linked after the decision");
    expect(impactTriggerLabel({ trigger: "OTHER_THING" })).toBe("Other Thing");
    expect(impactTriggerLabel({ trigger: "X", trigger_label: "Field report" })).toBe("Field report");
    expect(impactStatusView({ status: "OPEN" })).toEqual({ label: "To assess", tone: "warning" });
    expect(impactConclusionView({ conclusion: "MATERIAL_IMPACT" })?.tone).toBe("critical");
    expect(impactConclusionView({ conclusion: null })).toBeNull();
  });

  it("offers the assessment only while it is open and the server allows it", () => {
    expect(impactCanComplete({ status: "OPEN", actions: { can_complete: true } })).toBe(true);
    expect(impactCanComplete({ status: "COMPLETED", actions: { can_complete: true } })).toBe(false);
    expect(impactCanComplete({ status: "OPEN", actions: null })).toBe(false);
  });
});

describe("closure criteria", () => {
  const check = {
    can_close: false,
    applies: true,
    criteria: [
      { key: "decision_signed", label: "A decision is signed", result: "PASS" },
      { key: "capa", label: "CAPA follow-ups", result: "NOT_REQUIRED" },
      { key: "follow_ups_done", label: "Follow-ups completed", result: "BLOCKED", rationale: "FUP000002 is open" },
      { key: "impact", result: "PENDING" },
    ],
  };

  it("lists Blocked first, then Pass and Not required; anything unclear blocks", () => {
    expect(closureCriteria(check).map((row) => [row.key, row.result])).toEqual([
      ["follow_ups_done", "BLOCKED"],
      ["impact", "BLOCKED"],
      ["decision_signed", "PASS"],
      ["capa", "NOT_REQUIRED"],
    ]);
    expect(closureCriteria(check)[1].label).toBe("Impact");
    expect(closureHeadline(closureCriteria(check))).toBe("2 blocked · 1 pass · 1 not required");
    expect(closureHeadline([])).toBe("No closure criteria reported.");
  });

  it("allows closing only when nothing blocks it, and leaves the decision to the server otherwise", () => {
    expect(closureAllowed(check)).toBe(false);
    expect(closureAllowed({ can_close: true, criteria: [{ key: "a", result: "PASS" }] })).toBe(true);
    expect(closureAllowed({ can_close: true, criteria: [{ key: "a", result: "BLOCKED" }] })).toBe(false);
    expect(closureAllowed({ applies: false, can_close: false })).toBe(true);
    expect(closureAllowed(null)).toBe(true);
    expect(closureCheckPath(UUID)).toBe(`/api/v1/investigations/${UUID}/closure-check`);
  });
});
