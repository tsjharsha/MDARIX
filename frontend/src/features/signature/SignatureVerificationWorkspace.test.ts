import { describe, expect, it } from "vitest";
import {
  decisionLabel,
  signedDecisionLabel,
  signedVersionText,
  signerLabel,
  verificationSummary,
} from "./SignatureVerificationWorkspace";

const people = [{ id: "u-2", display_name: "Asha Rao" }];

describe("signature verification labels", () => {
  it("names the signer: by name and role, also when it is you, else the role when the name is not available", () => {
    // The report's name, also for the signed-in signer (DEV-024): "Meera Iyer (Leader)", not "You (Leader)".
    expect(signerLabel("u-1", "LEADER", people, "u-1", "Meera Iyer")).toBe("Meera Iyer (Leader)");
    expect(signerLabel("u-2", "APPROVER", [], "u-1", "Asha Rao")).toBe("Asha Rao (Approver)");
    expect(signerLabel("u-2", "APPROVER", people, "u-2")).toBe("Asha Rao (Approver)");
    // Without a name anywhere: "You" for the signed-in signer, else the role.
    expect(signerLabel("u-1", "APPROVER", people, "u-1")).toBe("You (Approver)");
    expect(signerLabel("u-1", "APPROVER", people, "u-1", " ")).toBe("You (Approver)");
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

  it("names the signed version in words, never its fingerprint (0.10.43)", () => {
    const hash = "9f2c4be1d0a7c3e5f6a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0";
    // A decision on a brief: the report names the brief version.
    expect(signedVersionText({ version_label: "Decision Brief DBV000012 version 2", object_version: hash })).toBe(
      "Decision Brief DBV000012 version 2",
    );
    // Without the label (the brief is no longer there), still never the hash.
    expect(signedVersionText({ version_label: null, object_version: hash })).toBe("Not available");
    expect(signedVersionText({ object_version: hash })).not.toContain(hash.slice(0, 8));
    // An older approval: its version is the moment the decision was last changed, shown as a date.
    const legacy = signedVersionText({ object_version: "2026-10-21T08:30:00+00:00" });
    expect(legacy.startsWith("The decision as of ")).toBe(true);
    expect(legacy).toContain("2026");
    expect(legacy).not.toContain("T08:30:00");
    expect(signedVersionText({})).toBe("Not available");
  });
});
