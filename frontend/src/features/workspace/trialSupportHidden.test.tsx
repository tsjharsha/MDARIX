import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { TRIAL_SUPPORT_ACCESS_ENABLED } from "../../app/featureSet";
import { TeamPanel, TEAM_PATH } from "./sections/TrialTeam";
import { TenantPicker } from "../admin/areas/common";

// Every resource answers at once, as the server would: the trial's team (the viewer is its owner), a support request
// waiting for them, and the tenants a Platform Admin can pick (one of them a free trial).
vi.mock("../customer-admin/shared", async (original) => {
  const actual = await original<typeof import("../customer-admin/shared")>();
  const answers: Record<string, unknown> = {
    "/api/v1/trial/team": {
      can_invite: true,
      can_manage: true,
      limit: 3,
      seats_used: 1,
      members: [
        { id: "u1", display_name: "Taylor Quality", email: "t@example.invalid", status: "ACTIVE", is_owner: true },
      ],
    },
    "/api/v1/trial/support-access": { items: [], awaiting_decision: 1 },
    "/api/v1/platform-admin/customer-admin-tenants": {
      items: [
        { id: "t1", tenant_key: "ORBIT", display_name: "Orbit Medical", tenant_name: "Orbit Medical" },
        { id: "t2", tenant_key: "TRIAL_ACME", display_name: "Acme Trial", tenant_name: "Acme Trial", is_trial: true },
      ],
    },
  };
  return {
    ...actual,
    useResource: (path: string | null) => ({ state: "ready", data: path ? answers[path] : null, reload: () => {} }),
  };
});

describe("support access for free trials waits for after the launch", () => {
  it("is switched off in one place", () => {
    expect(TRIAL_SUPPORT_ACCESS_ENABLED).toBe(false);
  });

  it("does not show Support access in the trial owner's Team tab", () => {
    expect(TEAM_PATH).toBe("/api/v1/trial/team");
    const markup = renderToStaticMarkup(<TeamPanel onChanged={() => undefined} />);
    expect(markup).toContain("Taylor Quality");
    expect(markup).not.toContain("Support access");
  });

  it("leaves the trials out of a tenant picker that asks for it, and only that one", () => {
    const without = renderToStaticMarkup(<TenantPicker value="" onChange={() => undefined} withoutTrials />);
    expect(without).toContain("Orbit Medical");
    expect(without).not.toContain("Acme Trial");
    const every = renderToStaticMarkup(<TenantPicker value="" onChange={() => undefined} />);
    expect(every).toContain("Acme Trial");
  });
});
