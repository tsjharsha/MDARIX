import { describe, expect, it } from "vitest";
import {
  accountRoleText,
  invitationNotice,
  personExportName,
  workflowRoleChoices,
  workflowRolesBody,
  workflowRolesChanged,
  workflowRolesProblem,
} from "./Users";

describe("invitation results", () => {
  it("says plainly when the email was not delivered and what to do next", () => {
    const notice = invitationNotice(
      {
        delivery: "FAILED",
        invitation_status: "NOT_SENT",
        message:
          "The account was created, but the invitation email could not be delivered. Ask MDARIX support for an activation link to pass on to the person.",
      },
      "a@example.com",
    );
    expect(notice.tone).toBe("critical");
    expect(notice.text).toMatch(/Ask MDARIX support for an activation link/);
    expect(invitationNotice({ invitation_status: "NOT_SENT" }, "a@example.com").text).toMatch(/MDARIX support/);
  });

  it("confirms a delivered invitation and names other delivery states", () => {
    expect(invitationNotice({ email_delivery: "SENT" }, "a@example.com")).toEqual({
      tone: "good",
      text: "Invitation sent to a@example.com. They will create their own password.",
    });
    expect(invitationNotice({ email_delivery: "NOT_CONFIGURED" }, "a@example.com").text).toBe(
      "Invitation created. Email delivery: not set up.",
    );
  });

  it("names a person's export after their User ID, never the UUID", () => {
    expect(personExportName({ business_id: "USR000042" })).toBe("mdarix-person-USR000042.json");
    expect(personExportName({ business_id: null })).toBe("mdarix-person-export.json");
  });
});

describe("roles shown to the administrator", () => {
  it("shows the account role's label, never its code", () => {
    expect(accountRoleText({ role: "APPROVER", role_label: "Decision Maker" })).toBe("Decision Maker");
    expect(accountRoleText({ role: "TRIAGE_LEAD" })).toBe("Complaint Handler");
    expect(accountRoleText({ role: "RISK_REVIEWER", role_label: null })).toBe("Risk Reviewer");
    expect(accountRoleText({})).toBe("—");
  });
});

describe("workflow roles", () => {
  const data = {
    user_id: "u1",
    account_role: { code: "INVESTIGATOR", label: "Investigator" },
    additional_roles: [{ code: "RISK_REVIEWER", label: "Risk Reviewer" }],
    available_roles: [
      { code: "INVESTIGATOR", label: "Investigator" },
      { code: "RISK_REVIEWER", label: "Risk Reviewer" },
      { code: "REGULATORY_REVIEWER", label: "Regulatory Reviewer" },
    ],
  };

  it("never offers the account role again", () => {
    expect(workflowRoleChoices(data).map((role) => role.code)).toEqual(["RISK_REVIEWER", "REGULATORY_REVIEWER"]);
    expect(workflowRoleChoices(null)).toEqual([]);
  });

  it("asks for a change and a reason of 10 to 500 characters", () => {
    expect(workflowRolesChanged(["A", "B"], ["B", "A"])).toBe(false);
    expect(workflowRolesChanged(["A"], ["A", "B"])).toBe(true);
    expect(workflowRolesChanged(["A"], [])).toBe(true);
    expect(workflowRolesProblem(["A"], ["A"], "A long enough reason")).toMatch(/Change at least one role/);
    expect(workflowRolesProblem(["A"], [], "too short")).toMatch(/at least 10/);
    expect(workflowRolesProblem(["A"], [], "x".repeat(501))).toMatch(/500/);
    expect(workflowRolesProblem(["A"], ["A", "B"], "Covers risk reviews this quarter")).toBeNull();
  });

  it("sends the complete list of additional roles with the reason", () => {
    expect(workflowRolesBody(["RISK_REVIEWER", "RISK_REVIEWER", "REVIEWER"], "  Covers reviews  ")).toEqual({
      additional_roles: ["RISK_REVIEWER", "REVIEWER"],
      reason: "Covers reviews",
    });
    expect(workflowRolesBody([], "Role no longer needed")).toEqual({
      additional_roles: [],
      reason: "Role no longer needed",
    });
  });
});
