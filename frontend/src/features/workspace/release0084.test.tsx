// 0.10.84: the independent rating's defects on the combined D1 + D2 build, each with the test that fails before.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { legalClocks } from "./home";
import type { OversightItem } from "./oversight";
import { OVERSIGHT } from "./oversight";
import { HomeSection, HomeStory } from "./sections/Home";
import { ComplaintPage, clockPrefix } from "./sections/ComplaintPage";
import { ONE_STORY_PATH, type StoryRun } from "./oneStory";
import { eventPath } from "./oversight";
import { IMPORTED_SOURCE } from "./complaintList";
import { rv11 } from "../../test/rv11";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const value = (path && resources.data[path.split("?")[0]]) ?? null;
    return { state: "ready", data: value, reload: () => undefined };
  },
}));

const api = (overrides: Partial<WorkspaceApi> = {}) =>
  ({
    session: { user_id: "u1", business_permissions: ["records.write"] },
    work: { products: [], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    persona: "admin",
    ...overrides,
  }) as unknown as WorkspaceApi;

const render = (node: ReactNode, value: WorkspaceApi = api()) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

const item = (overrides: Partial<OversightItem>): OversightItem =>
  ({
    key: "obligation:1",
    category: "OBLIGATION",
    category_label: "Authority report",
    title: "FDA 3500A: draft",
    ref: "SAMPLE-RV-11",
    complaint_id: "c-rv11",
    market: "US",
    product: null,
    owner: null,
    queue: null,
    away: null,
    due_at: "2026-12-02T18:29:59Z",
    due_label: "Wed 2 Dec 2026, 23:59 IST",
    state: "RUNNING",
    state_label: "Running",
    hours_left: 700,
    escalated_to: [],
    alerts: true,
    opens: null,
    ...overrides,
  }) as OversightItem;

// An approval task names the category OBLIGATION and gets the complaint's market (oversight/service.py), but its due
// date is the approver's target, not the legal deadline.
const approval = item({
  key: "task:t1",
  title: "Approve the US report for SAMPLE-RV-11",
  due_at: "2026-11-04T18:29:59Z",
  due_label: "Wed 4 Nov 2026, 23:59 IST",
  hours_left: 30,
});

describe("H1: Home's legal clocks are the legal deadlines only", () => {
  it("leaves an approval task out of the legal clocks", () => {
    expect(legalClocks([approval, item({})]).map((row) => row.key)).toEqual(["obligation:1"]);
  });

  it("shows the report's own deadline on the Regulatory Leader's Home, never the approval's due date", () => {
    resources.data[OVERSIGHT] = { items: [approval, item({})] };
    const html = render(<HomeSection heading={{ current: null }} />, api({ persona: "regulatory" }));
    const clocks = html.slice(html.indexOf('id="home-clocks"'));
    expect(clocks).toContain("Due Wed 2 Dec 2026, 23:59 IST");
    expect(clocks).not.toContain("Wed 4 Nov");
  });
});

const LABELS = ["The call", "Triage", "Tree", "Decide", "Form", "Fill", "Approval", "Submit", "Records", "Trends"];
const storyRun = (overrides: Partial<StoryRun> = {}): StoryRun => ({
  run: "yours",
  complaint: {
    id: "c-fic",
    ref: "FIC-2001",
    description: "The pump over-infused.",
    product_id: "p-fic",
    serious_injury: true,
    death: false,
  },
  market: "US",
  market_label: "United States (FDA)",
  conclusion: "REPORTABLE",
  report_id: "r1",
  report_stage: "APPROVAL",
  needs: [],
  steps: LABELS.map((label, index) => ({ key: label, label, done: index < 6, skipped: false })),
  current: 6,
  finished: false,
  ...overrides,
});

/** FIC-2001's page while its report waits for approval: the approval task is due first, the legal deadline later. */
const pendingApproval = () => {
  const view = rv11();
  const legal = { ...view.work!.due[0], key: "obligation:o1", category: "OBLIGATION", title: "FDA 3500A: approval" };
  legal.due_at = "2026-12-02T04:59:59Z";
  legal.due_label = "Tue 1 Dec 2026, 23:59 EST";
  const task = { ...legal, key: "task:t1", title: "Approve the US report for FIC-2001" };
  task.due_at = "2026-11-04T18:29:59Z";
  task.due_label = "Wed 4 Nov 2026, 23:59 IST";
  task.hours_left = 30;
  view.event.ref = "FIC-2001";
  view.work!.due = [task, legal];
  return view;
};

describe("H2: the Your data hero and the complaint header read the legal deadline, not an approval's due date", () => {
  it("says the legal deadline in the Your data hero on Home", () => {
    resources.data[ONE_STORY_PATH] = { sample: null, yours: storyRun() };
    resources.data[eventPath("FIC-2001")] = pendingApproval();
    const html = render(<HomeStory />, api({ dataSource: IMPORTED_SOURCE }));
    expect(html).toContain("Its clock ends Tue 1 Dec.");
    expect(html).not.toContain("Wed 4 Nov");
  });

  it("names the legal deadline in the complaint page's one clock line", () => {
    resources.data[ONE_STORY_PATH] = { sample: null, yours: null };
    resources.data[eventPath("FIC-2001")] = pendingApproval();
    const html = render(<ComplaintPage tab="Summary?ref=FIC-2001" />);
    const header = html.slice(html.indexOf('class="uw-cp-chips"'), html.indexOf("uw-hl-fields"));
    expect(header).toContain("due Tue 1 Dec");
    expect(header).not.toContain("Wed 4 Nov");
  });
});

describe("H3: once the country is known, the header names that market's clock", () => {
  it("says the market, not 'Shortest possible', while only the awareness date is still asked", () => {
    const due = rv11().work!.due[0];
    expect(clockPrefix({ ...due, key: "watch:c:facts", market: null })).toBe("Shortest possible");
    expect(clockPrefix({ ...due, key: "watch:c:facts", market: "US" })).toBe("United States");
  });
});

describe("M1: the story is read again after every saved change", () => {
  it("tells the story's readers when send saves a change", async () => {
    const { onSaved, send } = await vi.importActual<typeof import("../customer-admin/shared")>(
      "../customer-admin/shared",
    );
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    vi.stubGlobal("window", Object.assign(new EventTarget(), { setTimeout, clearTimeout, location: { pathname: "/app" } }));
    try {
      const heard = vi.fn();
      const stop = onSaved(heard);
      await send("/api/v1/triage/COMPLAINT/c1/record", "POST", { severity: "LOW" });
      expect(heard).toHaveBeenCalledTimes(1);
      stop();
      await send("/api/v1/triage/COMPLAINT/c1/record", "POST", { severity: "LOW" });
      expect(heard).toHaveBeenCalledTimes(1);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("M2: a complaint waiting for its country never says 'No market to assess'", () => {
  it("says the decision path waits for the incident country", () => {
    const view = rv11();
    view.event.ref = "FIC-2001";
    view.event.market = null;
    view.work!.markets = [];
    view.event.needs = [
      { fact: "COUNTRY", label: "Incident country", given: null, message: "Not in your file.", rule: "Every market" },
    ];
    resources.data[ONE_STORY_PATH] = { sample: null, yours: null };
    resources.data[eventPath("FIC-2001")] = view;
    const html = render(<ComplaintPage tab="Summary?ref=FIC-2001" />);
    expect(html).not.toContain("No market to assess");
    expect(html).toContain("Waits for the incident country, asked above");
  });
});
