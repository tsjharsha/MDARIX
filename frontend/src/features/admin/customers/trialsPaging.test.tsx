import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TrialsOverviewView, type TrialTableControls } from "./TrialsOverview";
import { attentionList, retentionText, trialBadgeOf, trialsPath, type TrialItem, type TrialOverview } from "./trials";
import { invitationProblem, keptBecause, trialRequestsPath } from "../TrialRequestsWorkspace";

const trial = (number: number, overrides: Partial<TrialItem> = {}): TrialItem => ({
  tenant_id: `t-${number}`,
  tenant_key: `TRIAL_ORG_${number}`,
  name: `Org ${number}`,
  owner: { email: `owner${number}@example.invalid`, name: `Owner ${number}`, status: "ACTIVE" },
  starts_at: "2026-10-01T00:00:00+00:00",
  expires_at: "2026-10-31T00:00:00+00:00",
  data_deleted_at: "2026-11-30T00:00:00+00:00",
  state: "ACTIVE",
  days_left: 15,
  users: { used: 1, limit: 3 },
  rows: { used: 0, limit: 5000 },
  story: { acted: [], acted_count: 0, total: 9, next: "HIDDEN_COMPLAINTS", counts: {}, last_activity: null },
  feedback: null,
  ...overrides,
});

const overview = (overrides: Partial<TrialOverview> = {}): TrialOverview => ({
  summary: {
    trials: 320,
    active: 290,
    ending_soon: 12,
    acted: 100,
    engaged: 20,
    own_data: 8,
    feedback: 5,
    demo_requested: 3,
    chapters: {},
  },
  chapters: [{ code: "HIDDEN_COMPLAINTS", number: 1, title: "Recover complaints" }],
  engaged_chapters: 4,
  items: Array.from({ length: 50 }, (_, index) => trial(51 + index)),
  attention: [trial(7, { name: "Urgent Devices", state: "ENDING_SOON", days_left: 2 })],
  page: 2,
  page_size: 50,
  total: 320,
  pages: 7,
  ...overrides,
});

const controls: TrialTableControls = {
  page: 2,
  onPage: () => undefined,
  state: "",
  onState: () => undefined,
  query: "",
  onQuery: () => undefined,
  sort: null,
  onSort: () => undefined,
};

const render = (data: TrialOverview, table = controls) =>
  renderToStaticMarkup(
    <TrialsOverviewView
      overview={{ state: "ready", data, reload: () => undefined }}
      onOpenTenant={() => undefined}
      table={table}
    />,
  );

describe("the trials overview, one page at a time", () => {
  it("asks the server for one page, its order, state and search", () => {
    expect(trialsPath({ page: 1, sort: null, state: "", q: "" })).toBe("/api/v1/platform-admin/trials?page=1");
    expect(
      trialsPath({ page: 3, sort: { key: "name", direction: "descending" }, state: "ENDING_SOON", q: " acme " }),
    ).toBe("/api/v1/platform-admin/trials?page=3&sort=name&order=desc&state=ENDING_SOON&q=acme");
  });

  it("shows the page it was sent, the pager for every trial and the figures for all of them", () => {
    const html = render(overview());
    expect(html).toContain("Page 2 of 7");
    expect(html).toContain("320 trials");
    expect(html.match(/Open tenant/g)).toHaveLength(50);
    expect(html).toContain("Org 51");
    expect(html).toContain("Org 100");
    expect(html).not.toContain("Org 101");
    expect(html).toContain("320 holding data in all");
    // Previous and Next both work on a middle page.
    expect(html).not.toMatch(/<button[^>]*disabled[^>]*>Previous/);
    expect(html).not.toMatch(/<button[^>]*disabled[^>]*>Next/);
    // Search and the trial-state filter sit above the table.
    expect(html).toContain('aria-label="Search organization, tenant or owner email"');
    expect(html).toContain('aria-label="Trial state"');
  });

  it("names who needs attention from every trial, not from the page shown", () => {
    const html = render(overview());
    expect(html).toContain("Urgent Devices");
    expect(html).toContain("2 days left");
    const data = overview();
    expect(attentionList(data, 4).map((item) => item.name)).toEqual(["Urgent Devices"]);
    // An answer without the list (an older server) falls back to the trials it sent, ended ones left out.
    const older = overview({ attention: undefined, items: [trial(1, { state: "ENDED" }), trial(2)] });
    expect(attentionList(older, 4).map((item) => item.name)).toEqual(["Org 2"]);
  });

  it("says when a search finds nothing, and shows one page without page buttons to press", () => {
    const html = render(overview({ items: [], attention: [], total: 0, pages: 1, page: 1 }), {
      ...controls,
      page: 1,
      query: "nothing",
    });
    expect(html).toContain("No matching trials");
    expect(html).toContain("Page 1 of 1");
    expect(html).toMatch(/<button[^>]*disabled[^>]*>Previous/);
    expect(html).toMatch(/<button[^>]*disabled[^>]*>Next/);
  });
});

describe("the trial request queue, one page at a time", () => {
  it("asks for one status, page, order and search", () => {
    expect(trialRequestsPath({ status: "PENDING_REVIEW", page: 1, sort: null, q: "" })).toBe(
      "/api/v1/platform-admin/trial-requests?status=PENDING_REVIEW&page=1",
    );
    expect(
      trialRequestsPath({ status: "APPROVED", page: 2, sort: { key: "organization", direction: "ascending" }, q: "x" }),
    ).toBe("/api/v1/platform-admin/trial-requests?status=APPROVED&page=2&sort=organization&order=asc&q=x");
  });
});

describe("an invitation that did not go out", () => {
  it("is named on the approved request until its owner activates", () => {
    expect(invitationProblem({ status: "APPROVED", owner_status: "INVITED", invitation_delivery: "FAILED" })).toBe(
      "Invitation not delivered",
    );
    expect(invitationProblem({ status: "APPROVED", owner_status: "INVITED", invitation_delivery: "SENT" })).toBeNull();
    expect(invitationProblem({ status: "APPROVED", owner_status: "ACTIVE", invitation_delivery: "FAILED" })).toBeNull();
    expect(invitationProblem({ status: "APPROVED", owner_status: "INVITED", invitation_delivery: null })).toBeNull();
  });
});

describe("trial data held for an MVP request", () => {
  const day = (value: string) => value.slice(0, 10);
  const plan = {
    delete_after: "2027-01-18T00:00:00+00:00",
    original_delete_after: "2026-11-19T00:00:00+00:00",
    held_for_mvp_request: true,
    hold_until: "2027-01-18T00:00:00+00:00",
    mvp_request: { id: "r1", status: "CONTACTED" },
  };

  it("says when the data goes, or that the MVP request holds it", () => {
    expect(retentionText(plan, day)).toBe(
      "Data held for its MVP request (would have been deleted 2026-11-19); deleted 2027-01-18 at the latest",
    );
    expect(
      retentionText({ ...plan, held_for_mvp_request: false, delete_after: "2026-12-03T00:00:00+00:00" }, day),
    ).toBe("Data deleted 2026-12-03");
    expect(retentionText(null, day, "2026-11-19T00:00:00+00:00")).toBe("Data deleted 2026-11-19");
    expect(retentionText(null, day)).toBeNull();
    expect(trialBadgeOf({ state: "ENDED", retention: plan }).label).toBe("Ended, data held for its MVP request");
    expect(trialBadgeOf({ state: "ENDED", retention: null }).label).toBe("Ended, data kept 30 days");
  });

  it("keeps a held trial out of the deletion run's list", () => {
    expect(keptBecause({ legal_hold: true })).toBe("under a legal hold");
    expect(keptBecause({ held_for_mvp_request: true })).toBe("held for its MVP request");
    expect(keptBecause({ held_for_mvp_request: true, hold_until: "2027-01-18T12:00:00+00:00" })).toMatch(
      /^held for its MVP request until .+ at the latest$/,
    );
    expect(keptBecause({})).toBeNull();
  });
});
