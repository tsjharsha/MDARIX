import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { TeamPanel, TEAM_PATH } from "./sections/TrialTeam";
import { SupportHistoryView, durationText, supportDecisions } from "./sections/TrialSupportAccess";
import { TenantPicker } from "../admin/areas/common";
import { RequestAccess } from "../admin/areas/SecurityArea";
import {
  TrialsOverviewView,
  supportDraft,
  supportStateText,
  type TrialSupportState,
  type TrialTableControls,
} from "../admin/customers/TrialsOverview";
import {
  ExportView,
  SupportWorkspaceView,
  bannerText,
  recordType,
  type WorkspaceSummary,
} from "../admin/customers/SupportWorkspace";
import type { TrialItem, TrialOverview } from "../admin/customers/trials";
import type { SupportGrant } from "../customer-admin/supportAccessModel";

// Free trial support access (0.10.39, NEW-1): the trial owner decides in Getting started › Team; Platform Admin asks
// from Customers & Tenants › Trials and reads what was granted in the read-only workspace.

// Hoisted with vi.mock below, which answers the screens' requests with them.
const { AREAS, waiting } = vi.hoisted(() => {
  const AREAS = [
    { code: "CONFIGURATION", label: "Configuration: products and versions" },
    { code: "AUDIT", label: "Audit trail: everything people and systems did" },
    { code: "PEOPLE", label: "People: the user directory" },
    { code: "RECORDS", label: "Quality records: complaints, investigations, decisions and data imports, to read" },
    { code: "DATA_EXPORT", label: "A full export: a copy of every record" },
  ];
  const waiting = {
    id: "g1",
    status: "AWAITING_CUSTOMER",
    person: "Ravi Support",
    reason: "Ticket 77: import question",
    areas: [AREAS[3]],
    write: false,
    starts_at: "2026-10-20T10:00:00+00:00",
    expires_at: "2026-10-20T14:00:00+00:00",
    uses: 0,
    can_approve: true,
    can_deny: true,
    can_revoke: true,
  } satisfies SupportGrant;
  return { AREAS, waiting };
});

vi.mock("../customer-admin/shared", async (original) => {
  const actual = await original<typeof import("../customer-admin/shared")>();
  const answers: Record<string, unknown> = {
    "/api/v1/trial/team": {
      can_invite: true,
      can_manage: true,
      limit: 3,
      seats_used: 1,
      members: [{ id: "u1", display_name: "Asha Rao", email: "asha@orbit.example", status: "ACTIVE", is_owner: true }],
    },
    "/api/v1/trial/support-access": { items: [waiting], awaiting_decision: 1 },
    "/api/v1/platform-admin/customer-admin-tenants": {
      items: [
        { id: "t1", tenant_key: "ACME", display_name: "Acme Care", tenant_name: "Acme Care" },
        { id: "t2", tenant_key: "TRIAL_ORBIT", display_name: "Orbit Medical Devices", is_trial: true },
      ],
    },
    "/api/v1/admin/identity/users": [
      {
        id: "p1",
        email: "ravi@mdarix.example",
        display_name: "Ravi Support",
        role: "PLATFORM_ADMIN",
        status: "ACTIVE",
      },
    ],
  };
  return {
    ...actual,
    useResource: (path: string | null) => ({ state: "ready", data: path ? answers[path] : null, reload: () => {} }),
  };
});

const trial = (id: string, name: string): TrialItem => ({
  tenant_id: id,
  tenant_key: `TRIAL_${id}`,
  name,
  owner: { id: `o-${id}`, email: `owner@${id}.example`, name: "Asha Rao", status: "ACTIVE" },
  people: [],
  starts_at: "2026-10-01T00:00:00+00:00",
  expires_at: "2026-10-31T00:00:00+00:00",
  data_deleted_at: "2026-11-30T00:00:00+00:00",
  state: "ACTIVE",
  days_left: 11,
  users: { used: 1, limit: 3 },
  rows: { used: 0, limit: 5000 },
  story: { acted: [], acted_count: 0, total: 9, next: null, counts: {}, last_activity: null },
  feedback: null,
});

const overview = (items: TrialItem[]): TrialOverview => ({
  summary: { trials: 3, active: 3, ending_soon: 0, acted: 0, engaged: 0, own_data: 0, feedback: 0, chapters: {} },
  chapters: [],
  engaged_chapters: 4,
  items,
  attention: [],
  page: 1,
  page_size: 50,
  total: items.length,
  pages: 1,
});

const controls: TrialTableControls = {
  page: 1,
  onPage: () => undefined,
  state: "",
  onState: () => undefined,
  query: "",
  onQuery: () => undefined,
  sort: null,
  onSort: () => undefined,
};

const request = (status: string, overrides: Partial<TrialSupportState> = {}): TrialSupportState => ({
  tenant_id: "x",
  request: {
    id: "g",
    status,
    person: "Ravi Support",
    mine: true,
    areas: [AREAS[3]],
    write: false,
    expires_at: "2026-10-20T14:00:00+00:00",
  },
  open_for_me: false,
  ...overrides,
});

const summary = (overrides: Partial<WorkspaceSummary> = {}): WorkspaceSummary => ({
  tenant: { id: "t2", name: "Orbit Medical Devices", tenant_key: "TRIAL_ORBIT", is_trial: true },
  grant: {
    id: "g1",
    areas: [AREAS[3], AREAS[4]],
    write: false,
    starts_at: "2026-10-20T10:00:00+00:00",
    expires_at: "2026-10-20T14:00:00+00:00",
    approved_by: "Asha Rao",
  },
  read_only: true,
  sections: [
    { key: "complaints", title: "Complaints", area: "RECORDS", open: true },
    { key: "investigations", title: "Investigations", area: "RECORDS", open: true },
    { key: "decisions", title: "Decisions", area: "RECORDS", open: true },
    { key: "imports", title: "Data imports", area: "RECORDS", open: true },
    { key: "team", title: "Team", area: "PEOPLE", open: false },
    { key: "audit", title: "Audit trail", area: "AUDIT", open: false },
  ],
  export: { open: true },
  story: [
    { code: "HIDDEN_COMPLAINTS", title: "Recover complaints hidden as cancellations or inquiries", tried: true },
    { code: "YOUR_DATA", title: "See it on your own data", tried: false },
  ],
  ...overrides,
});

describe("the trial owner decides on support access", () => {
  it("shows Support access in the owner's Team tab, with the request's areas, times and decisions", () => {
    expect(TEAM_PATH).toBe("/api/v1/trial/team");
    const markup = renderToStaticMarkup(<TeamPanel onChanged={() => undefined} />);
    expect(markup).toContain("Support access");
    expect(markup).toContain("1 waiting for you");
    expect(markup).toContain("Ravi Support: Quality records");
    expect(markup).toContain("Read only · from");
    expect(markup).toContain("(4 hours)");
    expect(markup).toContain("Why: Ticket 77: import question");
    expect(markup).toContain("Only you decide; your colleagues cannot.");
    for (const label of [">Approve<", ">Deny<", ">History<"]) expect(markup).toContain(label);
    expect(supportDecisions(waiting)).toEqual(["approve", "deny"]);
    expect(supportDecisions({ ...waiting, status: "APPROVED", can_approve: false, can_deny: false })).toEqual([
      "revoke",
    ]);
  });

  it("says how long a request lasts", () => {
    expect(durationText("2026-10-20T10:00:00Z", "2026-10-20T14:00:00Z")).toBe("4 hours");
    expect(durationText("2026-10-20T10:00:00Z", "2026-10-20T11:00:00Z")).toBe("1 hour");
    expect(durationText(null, "2026-10-20T11:00:00Z")).toBe("time not set");
  });

  it("lists a request's history in the words the server gives", () => {
    const markup = renderToStaticMarkup(
      <SupportHistoryView
        source={{ state: "ready" }}
        items={[
          { action: "SUPPORT_ACCESS_CUSTOMER_APPROVED", what: "Access approved", who: "Asha Rao", at: null },
          { action: "SUPPORT_ACCESS_USED", what: "Read the complaints", who: "Ravi Support", at: null },
          { action: "SUPPORT_ACCESS_EXPIRED", what: "Access ended on its own", who: "MDARIX (automatic)", at: null },
        ]}
      />,
    );
    expect(markup).toContain("From your trial&#x27;s audit trail");
    expect(markup).toContain("Read the complaints");
    expect(markup).toContain("Access ended on its own");
  });
});

describe("Platform Admin asks a trial for support access and reads what was granted", () => {
  it("offers the free trials in Request access", () => {
    const every = renderToStaticMarkup(<TenantPicker value="" onChange={() => undefined} />);
    expect(every).toContain("Orbit Medical Devices");
    expect(every).toContain("Acme Care");
  });

  it("puts a request shortcut, the request's state and the read-only workspace on each trial", () => {
    const markup = renderToStaticMarkup(
      <TrialsOverviewView
        overview={{
          state: "ready",
          data: overview([trial("a", "Orbit Medical Devices"), trial("b", "Lumen Diagnostics"), trial("c", "Vega")]),
          reload: () => undefined,
        }}
        onOpenTenant={() => undefined}
        table={controls}
        support={{
          b: request("AWAITING_CUSTOMER", { tenant_id: "b" }),
          c: request("APPROVED", { tenant_id: "c", open_for_me: true, expires_at: "2026-10-20T14:00:00+00:00" }),
        }}
        onRequestSupport={() => undefined}
        onOpenWorkspace={() => undefined}
      />,
    );
    expect(markup).toContain("Support access");
    expect(markup.match(/Request support access/g)).toHaveLength(1); // only the trial without an open request
    expect(markup).toContain("Requested: waiting for the trial owner");
    expect(markup.match(/Open read-only workspace/g)).toHaveLength(1);
    expect(markup).toContain("Open to you until");
    expect(supportStateText(request("PENDING"))).toBe("Requested: waiting for a second MDARIX approval");
    expect(supportStateText(undefined)).toBeNull();
  });

  it("pre-fills the request form with the trial, the asker, the reading areas and a reason", () => {
    const draft = supportDraft({ tenant_id: "t2", name: "Orbit Medical Devices" }, "p1");
    expect(draft).toEqual({
      tenant_id: "t2",
      platform_user_id: "p1",
      areas: ["RECORDS", "PEOPLE", "AUDIT"],
      reason: "Help Orbit Medical Devices with their free trial",
      hours: 4,
    });
    const markup = renderToStaticMarkup(
      <RequestAccess areas={AREAS} initial={draft} onClose={() => undefined} onRequested={() => undefined} />,
    );
    expect(markup).toContain('value="Help Orbit Medical Devices with their free trial"');
    expect(markup).toMatch(/<option value="t2" selected="">/);
    expect(markup).toMatch(/<option value="p1" selected="">/);
    const checked = [...markup.matchAll(/<input type="checkbox"( checked="")?\/>([^<]*)/g)].map((match) => [
      match[2].split(":")[0],
      Boolean(match[1]),
    ]);
    expect(Object.fromEntries(checked)).toEqual({
      Configuration: false,
      "Audit trail": true,
      People: true,
      "Quality records": true,
      "A full export": false,
      "Also allow changes (otherwise read-only)": false,
    });
  });

  it("opens the read-only workspace with its banner, only the granted pages, the story and the export", () => {
    const markup = renderToStaticMarkup(
      <SupportWorkspaceView
        summary={{ state: "ready", data: summary(), reload: () => undefined }}
        backLabel="All trials"
        onBack={() => undefined}
        active="complaints"
        onSection={() => undefined}
      />,
    );
    expect(markup).toContain("MDARIX support, read-only, access granted by Asha Rao until");
    expect(markup).toContain("Nothing here can be changed.");
    for (const tab of ["Complaints", "Investigations", "Decisions", "Data imports"]) expect(markup).toContain(tab);
    expect(markup).toContain("Not granted, so not shown: Team, Audit trail.");
    expect(markup).toContain("Recover complaints hidden as cancellations or inquiries");
    expect(markup).toContain("Not yet");
    expect(recordType("SupportAccessGrant")).toBe("Support access grant");
    expect(recordType("TRIAL_IMPORT")).toBe("Trial import");
    expect(bannerText({ grant: null })).toBe("No active support access. Request it from Customers & Tenants › Trials.");
    const closed = renderToStaticMarkup(
      <SupportWorkspaceView
        summary={{
          state: "ready",
          data: summary({ grant: null, sections: summary().sections.map((item) => ({ ...item, open: false })) }),
          reload: () => undefined,
        }}
        backLabel="All trials"
        onBack={() => undefined}
        active={null}
        onSection={() => undefined}
      />,
    );
    expect(closed).toContain("No active support access.");
    expect(closed).not.toContain('role="tablist"');
  });

  it("exports with a button and downloads a ready export", () => {
    const markup = renderToStaticMarkup(
      <ExportView
        tenantId="t2"
        onExport={() => undefined}
        exports={{
          state: "ready",
          reload: () => undefined,
          data: {
            exports: [
              { id: "e1", status: "READY", reason: "Ticket 77", size_bytes: 2_097_152, created_at: null },
              { id: "e2", status: "REQUESTED", reason: "Ticket 78", created_at: null },
            ],
          },
        }}
      />,
    );
    expect(markup).toContain("Export data");
    expect(markup).toContain('href="/api/v1/platform-admin/tenants/t2/exports/e1/download"');
    expect(markup.match(/>Download</g)).toHaveLength(1);
    expect(markup).toContain("2.0 MB");
  });
});
