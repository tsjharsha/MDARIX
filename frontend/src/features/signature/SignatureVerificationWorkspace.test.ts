import { describe, expect, it } from "vitest";
import { decisionLabel, signedDecisionLabel, signerLabel, verificationSummary } from "./SignatureVerificationWorkspace";

const people = [{ id: "u-2", display_name: "Asha Rao" }];

describe("signature verification labels", () => {
  it("names the signer: you, a colleague by name, or the role when the name is not available", () => {
    expect(signerLabel("u-1", "APPROVER", people, "u-1")).toBe("You (Approver)");
    expect(signerLabel("u-2", "APPROVER", people, "u-1")).toBe("Asha Rao (Approver)");
    expect(signerLabel("u-9", "LEADER", people, "u-1")).toBe("A colleague with the Leader role");
    expect(signerLabel("u-9", undefined, [], undefined)).toBe("A colleague in your organization");
  });

  it("describes a decision by its Decision ID, never its UUID", () => {
    const label = decisionLabel({
      id: "0d3c1a2b-0000-0000-0000-000000000000",
      decision_identifier: "DEC-0004",
      selected_action: "NO_DECISION_YET",
      decision_status: "REQUIRES_REVIEW",
    });
    expect(label).toBe("DEC-0004 · No Decision Yet · Requires Review");
    expect(decisionLabel({ id: "0d3c1a2b-0000-0000-0000-000000000000", business_id: "DEC000007" })).toBe("DEC000007");
    expect(decisionLabel({ id: "0d3c1a2b-0000-0000-0000-000000000000" })).toBe("Decision");
    // A decision on a case's brief, as the decision screen lists it (the list the MVP and free trials use).
    expect(
      decisionLabel({
        id: "0d3c1a2b-0000-0000-0000-000000000000",
        business_id: "DEC000002",
        outcome_label: "Accept the conclusion with conditions",
        decision_status: "SIGNED",
        decision_status_label: "Signed",
      }),
    ).toBe("DEC000002 · Accept the conclusion with conditions · Signed");
  });

  it("names the signed decision in words, never by its code", () => {
    expect(signedDecisionLabel("ACCEPT_COND")).toBe("Accept with conditions");
    expect(signedDecisionLabel("CLOSE_NFA")).toBe("Close with no further action");
    expect(signedDecisionLabel("approve")).toBe("Approved");
    expect(signedDecisionLabel(undefined)).toBe("Signature");
  });

  it("shows a signature that no longer matches as a problem, never as merely unsigned", () => {
    expect(verificationSummary("VALID")).toEqual({ label: "All signatures valid", tone: "good" });
    expect(verificationSummary("INVALID").tone).toBe("problem");
    expect(verificationSummary("INVALID").label).toMatch(/^Invalid/);
    expect(verificationSummary("NOT_SIGNED")).toEqual({ label: "Not signed", tone: "neutral" });
    expect(verificationSummary(undefined).tone).toBe("neutral");
  });
});
