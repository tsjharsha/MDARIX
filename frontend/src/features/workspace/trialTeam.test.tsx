import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  TeamView,
  memberActions,
  mfaResetConfirmation,
  removeConfirmation,
  type Team,
  type TeamMember,
} from "./sections/TrialTeam";
import { SupportAccessView, supportConfirmation, supportDecisions } from "./sections/TrialSupportAccess";
import type { SupportGrant } from "../customer-admin/supportAccessModel";

const member = (overrides: Partial<TeamMember> = {}): TeamMember => ({
  id: "u2",
  display_name: "Casey Review",
  email: "casey@example.invalid",
  status: "ACTIVE",
  is_owner: false,
  is_you: false,
  ...overrides,
});

const owner = member({ id: "u1", display_name: "Taylor Quality", email: "taylor@example.invalid", is_owner: true });

const team = (viewerIsOwner: boolean, members: TeamMember[]): Team => ({
  can_invite: viewerIsOwner,
  can_manage: viewerIsOwner,
  limit: 3,
  seats_used: members.length,
  members,
});

const render = (data: Team) =>
  renderToStaticMarkup(
    <TeamView
      team={{ state: "ready", data, reload: () => undefined }}
      busy={false}
      message={null}
      onInvite={async () => true}
      onResend={() => undefined}
      onConfirm={() => undefined}
      onChanged={() => undefined}
    />,
  );

/** The API answers every call with ``{}``; the calls are kept to check the path and body sent. */
function stubApi() {
  const fetchMock = vi.fn(async (_path: string, _init: RequestInit) => new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("window", { setTimeout, clearTimeout, location: { pathname: "/app" } });
  return (index = 0) => ({
    path: fetchMock.mock.calls[index][0] as string,
    method: fetchMock.mock.calls[index][1].method as string,
    body: fetchMock.mock.calls[index][1].body ? JSON.parse(String(fetchMock.mock.calls[index][1].body)) : undefined,
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("the trial owner looks after the team", () => {
  it("offers Remove from trial and Reset MFA for colleagues only, and nothing to a colleague viewer", () => {
    const viewer = { can_invite: true, can_manage: true };
    expect(memberActions({ ...owner, is_you: true }, viewer)).toEqual([]);
    expect(memberActions(member(), viewer)).toEqual(["mfa-reset", "remove"]);
    expect(memberActions(member({ status: "INVITED" }), viewer)).toEqual(["resend", "remove"]);
    expect(memberActions(member(), { can_invite: false, can_manage: false })).toEqual([]);

    const asOwner = render(team(true, [{ ...owner, is_you: true }, member(), member({ id: "u3", status: "INVITED" })]));
    expect(asOwner.match(/Remove from trial/g)).toHaveLength(2);
    expect(asOwner.match(/Reset MFA/g)).toHaveLength(1);
    expect(asOwner).toContain("Resend invitation");
    expect(asOwner).toContain("Lost your own authenticator?");
    const asColleague = render(team(false, [owner, { ...member(), is_you: true }]));
    expect(asColleague).not.toContain("Remove from trial");
    expect(asColleague).not.toContain("Reset MFA");
    expect(asColleague).toContain("The person who started this trial can invite colleagues.");
  });

  it("confirms a removal naming the person, then asks the server to remove them", async () => {
    const call = stubApi();
    const done = vi.fn();
    const request = removeConfirmation(member(), done);
    expect(request.title).toBe("Remove Casey Review from your trial?");
    expect(request.confirmLabel).toBe("Remove from trial");
    expect(request.danger).toBe(true);
    expect(request.body).toContain("Everything they did stays in MDARIX under their name");
    await request.run("", "", false, "");
    expect(call()).toEqual({ path: "/api/v1/trial/team/u2/remove", method: "POST", body: undefined });
    expect(done).toHaveBeenCalledOnce();
    expect(removeConfirmation(member({ status: "INVITED" }), done).title).toBe(
      "Withdraw the invitation to Casey Review?",
    );
  });

  it("resets a colleague's MFA with the reason given", async () => {
    const call = stubApi();
    const done = vi.fn();
    const request = mfaResetConfirmation(member(), done);
    expect(request.confirmLabel).toBe("Reset MFA");
    expect(request.reason).toEqual({ label: "Why is the authenticator being reset?", min: 5 });
    await request.run("Lost their phone", "", false, "");
    expect(call()).toEqual({
      path: "/api/v1/trial/team/u2/mfa-reset",
      method: "POST",
      body: { reason: "Lost their phone" },
    });
    expect(done).toHaveBeenCalledOnce();
  });
});

const grant = (overrides: Partial<SupportGrant> = {}): SupportGrant => ({
  id: "g1",
  status: "AWAITING_CUSTOMER",
  person: "Sam Support",
  reason: "Ticket 4711: the import question",
  areas: [{ code: "CONFIGURATION", label: "Configuration: products and versions" }],
  write: false,
  expires_at: "2099-01-01T10:00:00+00:00",
  uses: 0,
  can_approve: true,
  can_deny: true,
  can_revoke: true,
  ...overrides,
});

describe("the trial owner decides on support access", () => {
  it("offers Approve and Deny while a request waits, and Revoke once it is active", () => {
    expect(supportDecisions(grant())).toEqual(["approve", "deny"]);
    const active = grant({ status: "APPROVED", can_approve: false, can_deny: false });
    expect(supportDecisions(active)).toEqual(["revoke"]);
    expect(
      supportDecisions(grant({ status: "DENIED", can_approve: false, can_deny: false, can_revoke: false })),
    ).toEqual([]);
    const html = renderToStaticMarkup(
      <SupportAccessView grants={[grant(), active]} source={{ state: "ready" }} notice="" onDecide={() => undefined} />,
    );
    expect(html).toContain("1 waiting for you");
    expect(html).toContain("Sam Support: Configuration");
    for (const label of [">Approve<", ">Deny<", ">Revoke<"]) expect(html).toContain(label);
    const empty = renderToStaticMarkup(
      <SupportAccessView grants={[]} source={{ state: "ready" }} notice="" onDecide={() => undefined} />,
    );
    expect(empty).toContain("When MDARIX support asks for access to your trial, the request appears here.");
  });

  it("approves with the owner's authenticator code and a reason, through the trial's own routes", async () => {
    const call = stubApi();
    const done = vi.fn();
    const approve = supportConfirmation("approve", grant(), done);
    expect(approve.mfaCode).toBe(true);
    expect(approve.reason?.min).toBe(10);
    await approve.run("Yes, for ticket 4711", "", false, "123456");
    expect(call()).toEqual({
      path: "/api/v1/trial/support-access/g1/approve",
      method: "POST",
      body: { reason: "Yes, for ticket 4711", mfa_code: "123456" },
    });
    await supportConfirmation("deny", grant(), done).run("Not during our evaluation", "", false, "");
    expect(call(1).path).toBe("/api/v1/trial/support-access/g1/deny");
    const revoke = supportConfirmation("revoke", grant(), done);
    expect(revoke.danger).toBe(true);
    await revoke.run("The question is answered", "", false, "");
    expect(call(2)).toEqual({
      path: "/api/v1/trial/support-access/g1/revoke",
      method: "POST",
      body: { reason: "The question is answered" },
    });
    expect(done).toHaveBeenCalledTimes(3);
  });
});
