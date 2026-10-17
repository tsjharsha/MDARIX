import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TrialsOverviewView, trialMfaReset, type TrialTableControls } from "./TrialsOverview";
import type { TrialItem, TrialOverview } from "./trials";

const trial = (overrides: Partial<TrialItem> = {}): TrialItem => ({
  tenant_id: "t-1",
  tenant_key: "TRIAL_ORG_1",
  name: "Org 1",
  owner: { id: "u1", email: "owner@example.invalid", name: "Taylor Quality", status: "ACTIVE" },
  people: [
    { id: "u1", email: "owner@example.invalid", name: "Taylor Quality", status: "ACTIVE" },
    { id: "u2", email: "casey@example.invalid", name: "Casey Review", status: "ACTIVE" },
    { id: "u3", email: "robin@example.invalid", name: "Robin QA", status: "INVITED" },
  ],
  starts_at: "2026-10-01T00:00:00+00:00",
  expires_at: "2026-10-31T00:00:00+00:00",
  data_deleted_at: "2026-11-30T00:00:00+00:00",
  state: "ACTIVE",
  days_left: 15,
  users: { used: 3, limit: 3 },
  rows: { used: 0, limit: 5000 },
  story: { acted: [], acted_count: 0, total: 9, next: null, counts: {}, last_activity: null },
  feedback: null,
  ...overrides,
});

const overview = (items: TrialItem[]): TrialOverview => ({
  summary: { trials: 1, active: 1, ending_soon: 0, acted: 0, engaged: 0, own_data: 0, feedback: 0, chapters: {} },
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

const render = (items: TrialItem[]) =>
  renderToStaticMarkup(
    <TrialsOverviewView
      overview={{ state: "ready", data: overview(items), reload: () => undefined }}
      onOpenTenant={() => undefined}
      table={controls}
    />,
  );

afterEach(() => vi.unstubAllGlobals());

describe("Platform Admin resets a trial user's MFA from the trials overview", () => {
  it("lists the trial's people with Reset MFA for each one who has activated", () => {
    const html = render([trial()]);
    expect(html).toContain("Taylor Quality");
    expect(html).toContain("Casey Review");
    expect(html).toContain("Robin QA");
    // The owner and the active colleague; not the invitation nobody accepted yet.
    expect(html.match(/Reset MFA/g)).toHaveLength(2);
    // An owner who never activated has no MFA to reset, and an older answer without people still shows the owner.
    const waiting = render([
      trial({ owner: { id: "u1", email: "owner@example.invalid", name: null, status: "INVITED" }, people: undefined }),
    ]);
    expect(waiting).toContain("invitation not accepted");
    expect(waiting).not.toContain("Reset MFA");
  });

  it("asks for a reason and confirms before resetting, then calls the Platform Admin reset", async () => {
    const fetchMock = vi.fn(async (_path: string, _init: RequestInit) => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("window", { setTimeout, clearTimeout, location: { pathname: "/platform-admin" } });
    const done = vi.fn();
    const person = trial().owner!;
    const request = trialMfaReset(person, trial(), done);
    expect(request.title).toBe("Reset multi-factor authentication for Taylor Quality?");
    expect(request.confirmLabel).toBe("Reset MFA");
    expect(request.reason?.min).toBe(5);
    expect(request.body).toContain("Org 1");
    await request.run("Lost phone, identity checked by call", "", false, "");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/platform-admin/users/u1/mfa-reset");
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({
      reason: "Lost phone, identity checked by call",
    });
    expect(done).toHaveBeenCalledOnce();
  });
});
