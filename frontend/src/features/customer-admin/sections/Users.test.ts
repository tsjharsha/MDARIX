import { describe, expect, it } from "vitest";
import { invitationNotice, personExportName } from "./Users";

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
      "Invitation created. Email delivery: Not Configured.",
    );
  });

  it("names a person's export after their User ID, never the UUID", () => {
    expect(personExportName({ business_id: "USR000042" })).toBe("mdarix-person-USR000042.json");
    expect(personExportName({ business_id: null })).toBe("mdarix-person-export.json");
  });
});
