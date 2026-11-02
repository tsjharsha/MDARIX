import { describe, expect, it } from "vitest";
import { ApiError } from "../../app/apiClient";
import {
  approvalError,
  approvalRequest,
  authoringSections,
  checkFindings,
  claimSections,
  draftOutcome,
  draftRequest,
  type DraftForm,
} from "./regulatoryModel";

const form = (overrides: Partial<DraftForm> = {}): DraftForm => ({
  template: "GSPR",
  identifier: "",
  title: "",
  investigationId: "",
  claims: "",
  sections: {},
  ...overrides,
});

describe("draft request", () => {
  it("sends only what the person entered, with the optional investigation", () => {
    expect(draftRequest(form())).toEqual({
      document_type: "GSPR",
      claims: [],
      citations: [],
      authoring_sections: {},
      change_reason: "Regulatory copilot draft",
    });
    const body = draftRequest(
      form({
        identifier: " GSPR-1 ",
        title: "Pump",
        investigationId: "case-1",
        claims: "First claim\n\n  Second claim ",
        sections: { device_scope: " Infusion pump ", labeling: "not a GSPR section", risk_controls: "  " },
      }),
    );
    expect(body).toMatchObject({ document_identifier: "GSPR-1", title: "Pump", investigation_id: "case-1" });
    expect(body.claims).toEqual([
      { claim_id: "claim-1", text: "First claim" },
      { claim_id: "claim-2", text: "Second claim" },
    ]);
    // Only the template's own, non-empty sections reach the model.
    expect(body.authoring_sections).toEqual({ device_scope: "Infusion pump" });
  });
});

describe("how a draft was written", () => {
  it("says plainly when the AI wrote it and when it is the layout only, with the server's reason", () => {
    expect(draftOutcome({ status: "AI_DRAFTED", user_message: "Review every section." })).toEqual({
      aiDrafted: true,
      title: "Drafted by AI from your records",
      message: "Review every section.",
    });
    const rules = draftOutcome({ status: "RULES_ONLY", user_message: "AI is switched off for your organization." });
    expect(rules.aiDrafted).toBe(false);
    expect(rules.title).toMatch(/Rules only/);
    expect(rules.message).toBe("AI is switched off for your organization.");
    expect(draftOutcome(undefined).aiDrafted).toBe(false);
  });

  it("separates the template's sections from the author's claims and explains the checks", () => {
    const sections = [{ section_id: "device_scope" }, { claim_id: "claim-1", text: "x" }];
    expect(authoringSections(sections)).toHaveLength(1);
    expect(claimSections(sections)).toHaveLength(1);
    expect(
      checkFindings({ unverified_citations: ["EV-9"], causal_or_decision_wording: ["caused by"], notes: ["n"] }),
    ).toEqual([
      "Cites records that were not in its sources: EV-9",
      "Causal or decision wording to rewrite: caused by",
      "n",
    ]);
    expect(checkFindings(undefined)).toEqual([]);
  });
});

describe("approval", () => {
  it("re-authenticates with the password and sends a code only when one was typed", () => {
    expect(approvalRequest(3, " Reviewed ", "pw", "")).toEqual({
      status: "APPROVED",
      expected_lock_version: 3,
      reason: "Reviewed",
      password: "pw",
    });
    expect(approvalRequest(3, "Reviewed", "pw", "123 456").mfa_code).toBe("123456");
  });

  it("explains every refusal code the server gives, with the reference", () => {
    for (const code of [
      "REAUTHENTICATION_REQUIRED",
      "INVALID_REAUTHENTICATION",
      "SIGNATURE_MFA_NOT_SET_UP",
      "SIGNATURE_CODE_INVALID",
      "ADMINISTRATOR_CANNOT_SIGN",
      "SIGNATURE_TEMPORARILY_LOCKED",
    ]) {
      const message = approvalError(new ApiError("raw server text", 403, code));
      expect(message).not.toBe("raw server text");
      expect(message.length).toBeGreaterThan(20);
    }
    expect(approvalError(new ApiError("x", 429, "SIGNATURE_TEMPORARILY_LOCKED", "req-7"))).toMatch(
      /locked for 15 minutes.*\(reference req-7\)$/,
    );
    expect(approvalError(new ApiError("Something else", 409, "OTHER"))).toBe("Something else");
  });
});
