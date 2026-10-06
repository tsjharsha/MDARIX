import { describe, expect, it } from "vitest";
import { ROLE_LABELS, WORKFLOW_ROLE_CODES, roleLabel, roleLabels, rolesSummary } from "./roles";

describe("role labels", () => {
  it("prefers the server's label, then the known label for the code", () => {
    expect(roleLabel("INVESTIGATOR", "Quality Investigator (EU)")).toBe("Quality Investigator (EU)");
    expect(roleLabel("INVESTIGATOR")).toBe("Quality Investigator");
    expect(roleLabel("triage_lead")).toBe("PMS / Signal Triage Lead");
    expect(roleLabel("APPROVER", "  ")).toBe("Authorized Decision Maker");
  });

  it("never shows a raw code, and keeps an organization's own role name as it is", () => {
    expect(roleLabel("QA_LEAD")).toBe("Qa Lead");
    expect(roleLabel("Site quality lead")).toBe("Site quality lead");
    expect(roleLabel(null)).toBe("");
  });

  it("names every Phase 1 role", () => {
    for (const code of [...WORKFLOW_ROLE_CODES, "VIEWER", "CUSTOMER_ADMIN", "PLATFORM_ADMIN"])
      expect(ROLE_LABELS[code]).toBeTruthy();
    expect(ROLE_LABELS.LEADER).toBe("Leader (Quality Manager)");
    expect(ROLE_LABELS.REVIEWER).toBe("Quality Reviewer");
  });
});

describe("the roles a person holds", () => {
  it("lists every role's label in the server's order, without repeats", () => {
    const session = {
      active_role: "INVESTIGATOR",
      roles: [
        { code: "INVESTIGATOR", label: "Quality Investigator", source: "account" },
        { code: "RISK_REVIEWER", label: "Risk Reviewer", source: "additional" },
        { code: "INVESTIGATOR", label: "Quality Investigator", source: "additional" },
      ],
    };
    expect(roleLabels(session)).toEqual(["Quality Investigator", "Risk Reviewer"]);
    expect(rolesSummary(session)).toBe("Quality Investigator + Risk Reviewer");
  });

  it("falls back to the active role's label for an older session, and says when there is none", () => {
    expect(rolesSummary({ active_role: "APPROVER" })).toBe("Authorized Decision Maker");
    expect(rolesSummary({ active_role: "APPROVER", roles: [] })).toBe("Authorized Decision Maker");
    expect(rolesSummary({})).toBe("No active role");
    expect(rolesSummary(null)).toBe("No active role");
  });
});
