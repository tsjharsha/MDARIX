import { describe, expect, it } from "vitest";
import {
  accessText,
  activityText,
  areaNames,
  awaitingCount,
  supportStatus,
  type SupportGrant,
} from "./supportAccessModel";

const grant = (overrides: Partial<SupportGrant> = {}): SupportGrant => ({
  id: "g1",
  status: "AWAITING_CUSTOMER",
  reason: "Ticket 1234: the customer cannot see a product",
  areas: [{ code: "CONFIGURATION", label: "Configuration: products and versions, integrations" }],
  write: false,
  expires_at: "2026-10-11T18:00:00Z",
  uses: 0,
  can_approve: true,
  can_deny: true,
  can_revoke: true,
  ...overrides,
});

describe("support access, as the customer reads it", () => {
  it("says where a grant stands, and that a grant past its end has ended", () => {
    const now = new Date("2026-10-11T12:00:00Z");
    expect(supportStatus(grant(), now)).toEqual({ label: "Waiting for your decision", tone: "warning" });
    expect(supportStatus(grant({ status: "APPROVED" }), now)).toEqual({ label: "Active", tone: "serious" });
    expect(supportStatus(grant({ status: "APPROVED" }), new Date("2026-10-11T19:00:00Z")).label).toBe("Ended");
    expect(supportStatus(grant({ status: "DENIED" }), now).label).toBe("Denied");
    expect(supportStatus(grant({ status: "SOMETHING_NEW" }), now)).toEqual({ label: "SOMETHING_NEW", tone: "neutral" });
  });

  it("names the areas by their short names and says whether changes are allowed", () => {
    expect(areaNames(grant().areas)).toBe("Configuration");
    expect(
      areaNames([
        { code: "AUDIT", label: "Audit trail: everything people did" },
        { code: "PEOPLE", label: "People: the user directory" },
      ]),
    ).toBe("Audit trail, People");
    expect(areaNames([])).toBe("Nothing (deny this request)");
    expect(accessText(false)).toBe("Read only");
    expect(accessText(true)).toBe("Read and change");
  });

  it("tells the story of a grant from its audit events", () => {
    expect(activityText({ action: "SUPPORT_ACCESS_CUSTOMER_APPROVED" })).toBe("Your administrator approved the access");
    expect(activityText({ action: "SUPPORT_ACCESS_USED", area: "AUDIT", write: false })).toBe("Viewed the audit trail");
    expect(activityText({ action: "SUPPORT_ACCESS_USED", area: "CONFIGURATION", write: true })).toBe(
      "Changed configuration",
    );
    expect(activityText({ action: "SUPPORT_ACCESS_USED", area: "UNKNOWN" })).toBe("Viewed your data");
  });

  it("counts the requests that wait for a decision, and shows no badge when none does", () => {
    expect(awaitingCount([grant(), grant({ id: "g2", can_approve: false, can_deny: false })])).toBe(1);
    expect(awaitingCount([grant({ can_approve: false, can_deny: false })])).toBeNull();
  });
});
