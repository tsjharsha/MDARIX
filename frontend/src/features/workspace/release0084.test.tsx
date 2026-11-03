// 0.10.84: the independent rating's defects on the combined D1 + D2 build, each with the test that fails before.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { DUE_WEEK_PATH, OVERDUE_PATH, legalClocks, nextActions, withSource } from "./home";
import type { OversightItem } from "./oversight";
import { OVERSIGHT } from "./oversight";
import { HomeSection, HomeStory } from "./sections/Home";
import { TrendBars } from "./sections/OneStory";
import type { TrendItem } from "./signalAi";
import { ComplaintPage, clockPrefix } from "./sections/ComplaintPage";
import { ONE_STORY_PATH, stepPlace, type StoryRun } from "./oneStory";
import { NewRecordsSection } from "./sections/Records";
import { eventPath } from "./oversight";
import { IMPORTED_SOURCE, SAMPLE_SOURCE } from "./complaintList";
import { rv11 } from "../../test/rv11";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const value = (path && resources.data[path.split("?")[0]]) ?? null;
    return { state: "ready", data: value, reload: () => undefined };
  },
}));

// Each test sets the server's answers it needs.
beforeEach(() => {
  resources.data = {};
});

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
    resources.data[eventPath("FIC-2001")] = pendingApproval();
    const story = { state: "ready" as const, data: { sample: null, yours: storyRun() }, reload: () => undefined };
    const html = render(<HomeStory story={story} />, api({ dataSource: IMPORTED_SOURCE }));
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
    const { onSaved, send } =
      await vi.importActual<typeof import("../customer-admin/shared")>("../customer-admin/shared");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 200 })),
    );
    vi.stubGlobal(
      "window",
      Object.assign(new EventTarget(), { setTimeout, clearTimeout, location: { pathname: "/app" } }),
    );
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

describe("M3: the finale says the trend check's own verdict, with its own numbers", () => {
  const pulse = {
    key: "pulse",
    name: "PulseWatch 410 Rev A",
    product: { id: "p", business_id: null, name: "PulseWatch 410" },
    recent: 3,
    expected: 0.99,
    ratio: 3.03,
    p_value: 0.0757,
    p_adjusted: 0.0757,
    groups_tested: 1,
    result: "STEADY",
  } as unknown as TrendItem;

  it("never sets 'in line' beside 3 observed against 0.99 expected without saying why", () => {
    const html = renderToStaticMarkup(<TrendBars row={pulse} />);
    expect(html).toContain("PulseWatch 410 Rev A: in line with history");
    expect(html).toContain("3 against 1.0 expected (3.0× expected) · p 0.076: within chance, not a rise");
    // The bars carry the trend check's numbers: 1.0 expected, as Trends shows it, not 0.99.
    expect(html).toContain(">1.0<");
    expect(html).not.toContain("0.99");
  });
});

describe("M4: step 9 opens the finished record in Records, and Your data's step 10 your own trend", () => {
  it("opens Records on the story's record, and Trends on the story's own product", () => {
    expect(stepPlace(storyRun(), 8)).toEqual({ section: "Records", tab: "Decision records?complaint=FIC-2001" });
    const yours = storyRun({ complaint: { ...storyRun().complaint, product_ref: "FIC-NEB-20" } });
    expect(stepPlace(yours, 9)).toEqual({ section: "Trends", tab: "Trend check?product=FIC-NEB-20" });
    // Never the sample's OrbitCare rise on your data.
    expect(stepPlace(storyRun(), 9).tab).not.toContain("SAMPLE-ORBIT-300");
  });

  it("leads Records with what the story finished: the signed conclusion, the report and who signed", () => {
    const view = rv11();
    view.related = [
      {
        key: "assessments",
        label: "Market assessments",
        count: 1,
        lines: ["United States (FDA): reportable, signed 2026-11-03"],
      },
      {
        key: "reports",
        label: "Authority reports",
        count: 1,
        lines: ["United States (FDA) · FDA 3500A · submitted"],
        items: [{ id: "r1", ref: "US" }],
      },
      { key: "decisions", label: "Decision records", count: 1, lines: ["Report approved 2026-11-03 by Rahul Iyer"] },
    ];
    resources.data[eventPath("SAMPLE-RV-11")] = view;
    resources.data["/api/v1/oversight/latest-signed"] = { record: null };
    const html = render(
      <NewRecordsSection tab="Decision records?complaint=SAMPLE-RV-11" />,
      api({ session: { user_id: "u1", business_permissions: ["data.export"] } as never }),
    );
    expect(html).toContain("The record you just finished");
    expect(html).toContain("SAMPLE-RV-11 · ready for an inspector");
    expect(html).toContain("United States (FDA): reportable, signed 2026-11-03");
    expect(html).toContain("Report approved 2026-11-03 by Rahul Iyer");
    expect(html).toContain("Download the decision record (PDF)");
    expect(html).toContain("Open the report");
  });
});

describe("M5: Home follows the Sample · Your data switch, and lists the complaint its hero names", () => {
  const fic = (ref: string, id: string) =>
    item({
      key: `triage:COMPLAINT:${id}`,
      category: "TRIAGE",
      title: "Triage not done yet (urgent)",
      ref,
      complaint_id: id,
      market: null,
      due_at: "2026-11-04T10:00:00Z",
      due_label: "Wed 4 Nov 2026, 15:30 IST",
      hours_left: 20,
    });
  const items = [
    item({ key: "obligation:s1", ref: "SAMPLE-RV-08", state: "OVERDUE", due_at: "2026-11-01T18:29:59Z" }),
    fic("FIC-2002", "c2"),
    fic("FIC-2003", "c3"),
    fic("FIC-2004", "c4"),
    fic("FIC-2005", "c5"),
    fic("FIC-2006", "c6"),
    fic("FIC-2001", "c-fic"),
  ];
  const trends = [
    {
      key: "orbit",
      name: "OrbitCare 300 Rev B",
      product: { id: "o", business_id: "PRD-1", identifier: "SAMPLE-ORBIT-300", name: "OrbitCare" },
      recent: 9,
      expected: 0.97,
      ratio: 9.3,
      result: "SIGNIFICANT",
    },
    {
      key: "neb",
      name: "FIC-NEB-20 Rev A",
      product: { id: "n", business_id: "PRD-9", identifier: "FIC-NEB-20", name: "FIC-NEB-20" },
      recent: 6,
      expected: 1.0,
      ratio: 6.0,
      result: "SIGNIFICANT",
    },
  ];

  it("lists the hero's complaint first among those due at the same time, and always lists it", () => {
    expect(nextActions(items, 5).map((row) => row.ref)).not.toContain("FIC-2001");
    const led = nextActions(items, 5, "c-fic").map((row) => row.ref);
    expect(led[0]).toBe("SAMPLE-RV-08");
    expect(led[1]).toBe("FIC-2001");
  });

  it("counts, lists and trends your data only on Your data", () => {
    resources.data[OVERSIGHT] = { items };
    resources.data["/api/v1/triage/trends"] = { items: trends };
    resources.data[ONE_STORY_PATH] = { sample: null, yours: storyRun({ current: 0 }) };
    const html = render(<HomeSection heading={{ current: null }} />, api({ dataSource: IMPORTED_SOURCE }));
    const next = html.slice(html.indexOf('id="home-next"'), html.indexOf("uw-home-side"));
    expect(next).not.toContain("SAMPLE-RV-08");
    expect(next).toContain("FIC-2001");
    expect(html).toContain("FIC-NEB-20 Rev A is rising");
    expect(html).not.toContain("OrbitCare");
  });

  it("reads the tiles' counts from the complaint lists of the data shown", () => {
    expect(withSource(OVERDUE_PATH, IMPORTED_SOURCE)).toBe(`${OVERDUE_PATH}&source_system=TRIAL_UPLOAD`);
    expect(withSource(DUE_WEEK_PATH, SAMPLE_SOURCE)).toBe(`${DUE_WEEK_PATH}&source_system=MDARIX_SAMPLE`);
    expect(withSource(OVERDUE_PATH, "")).toBe(OVERDUE_PATH);
  });

  it("keeps the sample's records on the sample, and drops your imported complaints there", () => {
    resources.data[OVERSIGHT] = { items };
    resources.data["/api/v1/triage/trends"] = { items: trends };
    const html = render(<HomeSection heading={{ current: null }} />, api({ dataSource: SAMPLE_SOURCE }));
    const next = html.slice(html.indexOf('id="home-next"'), html.indexOf("uw-home-side"));
    expect(next).toContain("SAMPLE-RV-08");
    expect(next).not.toContain("FIC-200");
    expect(html).toContain("OrbitCare 300 Rev B is rising");
  });
});
