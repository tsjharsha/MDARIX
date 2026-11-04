// 0.10.87, the owner-approved duplication review: each trial page of the new navigation says each thing once. One
// describe per page, named with the review's rows.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { HomeSection } from "./sections/Home";
import { ComplaintViews, InvestigationList } from "./sections/ComplaintViews";
import { Panel } from "../admin/console/charts";
import { TrendsSection } from "./sections/Trends";
import { TrendCheck, TrendHeroes } from "./sections/TrendCheck";
import type { TrendBoard, TrendItem } from "./signalAi";
import { SAMPLE_SOURCE } from "./complaintList";
import { YourData } from "./sections/YourData";
import records from "./sections/Records.tsx?raw";
import settings from "./sections/Settings.tsx?raw";
import account from "./sections/Account.tsx?raw";
import caseSections from "./sections/CaseSections.tsx?raw";
import investigations from "./sections/Investigations.tsx?raw";
import { ComplaintPage } from "./sections/ComplaintPage";
import { ONE_STORY_PATH } from "./oneStory";
import { eventPath } from "./oversight";
import { rv11 } from "../../test/rv11";
import { DecisionTreesSection } from "./sections/DecisionTrees";
import { practiceWarning } from "./sections/Reports";

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
    session: {
      user_id: "u1",
      display_name: "Asha Quality",
      business_permissions: ["records.write"],
      current_tenant: { tenant_name: "Medisynth Devices" },
    },
    work: { products: [], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    persona: "admin",
    personaTabs: ["home", "complaints", "trees", "reports", "investigations", "trends", "records", "team"],
    ...overrides,
  }) as unknown as WorkspaceApi;
const render = (node: ReactNode, value: WorkspaceApi = api()) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

beforeEach(() => {
  resources.data = {};
});

describe("Home (rows 15-17)", () => {
  const rise = {
    key: "orbit",
    name: "OrbitCare 300 Rev B",
    product: { id: "o", business_id: "PRD-1", identifier: "SAMPLE-ORBIT-300", name: "OrbitCare" },
    recent: 9,
    expected: 0.97,
    ratio: 9.3,
    result: "SIGNIFICANT",
  };

  it("names the organization and the data on the top bar only, and the rising product once, in the Trends card", () => {
    resources.data["/api/v1/triage/trends"] = { items: [rise] };
    const html = render(<HomeSection heading={{ current: null }} />);
    const date = html.slice(html.indexOf('class="uw-home-date"'), html.indexOf("</header>"));
    expect(date).toContain("times in");
    expect(date).not.toContain("Medisynth Devices");
    expect(html).not.toContain("Home · sample data");
    expect(html).not.toContain('class="uw-viewing"');
    expect(html).toContain("Products rising against their history");
    expect(html.split("OrbitCare 300 Rev B").length - 1).toBe(1);
    // Outside a trial the persona eyebrow stays.
    expect(render(<HomeSection heading={{ current: null }} />, api({ isTrial: false }))).toContain("Viewing as");
  });
});

describe("Complaints (rows 3, 19, 20)", () => {
  it("has no import button in a trial, no second Complaints eyebrow, and a count for a title", () => {
    resources.data["/api/v1/complaints"] = { total: 12, items: [] };
    const html = render(<ComplaintViews />);
    expect(html).not.toContain("Import your data");
    expect(html).not.toContain('<p class="ac-eyebrow">Complaints</p>');
    expect(html).toContain("<h2>12 complaints</h2>");
  });

  it("lists another tab's own list as a view only for a persona without that tab", () => {
    const admin = render(<ComplaintViews />);
    expect(admin).not.toContain(">Authority reports<");
    expect(admin).not.toContain(">Investigations<");
    const handler = render(<ComplaintViews />, api({ persona: "handler", personaTabs: ["home", "complaints"] }));
    expect(handler).toContain(">Authority reports<");
    expect(handler).toContain(">Investigations<");
  });
});

describe("A complaint (rows 21-23)", () => {
  it("names its reference once, keeps the service line to the service, and says missing facts are not recorded", () => {
    const view = rv11();
    view.service = {
      reference: "SVC-1",
      status: "COMPLETE",
      header: "Service complete · Quality assessment open",
    } as never;
    view.event.needs = [
      { fact: "COUNTRY", label: "Incident country", given: null, message: "", rule: "" },
      { fact: "AWARENESS_DATE", label: "Awareness date", given: null, message: "", rule: "" },
    ];
    resources.data[ONE_STORY_PATH] = { sample: null, yours: null };
    resources.data[eventPath(view.event.ref)] = view;
    const html = render(<ComplaintPage tab={`Summary?ref=${view.event.ref}`} />);
    const crumbs = html.slice(html.indexOf('class="uw-crumbs"'), html.indexOf("</nav>"));
    expect(crumbs).not.toContain(view.event.ref);
    expect(html).toContain("<strong>Service complete · Quality assessment open</strong></p>");
    expect(html).not.toContain("Quality owner:");
    expect(html).not.toContain("asked below");
    expect(html).not.toContain("asked above");
    expect(html).toContain("asked in Details");
  });
});

describe("Decision trees (row 26)", () => {
  it("does not repeat the page's question while the trees load", () => {
    const html = render(<DecisionTreesSection />);
    expect(html).toContain("Reading the trees…");
    expect(html).not.toContain("Is it reportable, and by when?");
  });
});

describe("Reports approval (row 33)", () => {
  it("says only who you approve as; the line at the button says a pilot needs a colleague", () => {
    expect(
      practiceWarning(
        "In a pilot a colleague approves this; in the trial you may approve your own practice report as Leader.",
      ),
    ).toBe("You may approve your own practice report as Leader.");
    expect(practiceWarning("Something else.")).toBe("Something else.");
  });
});

describe("Investigations (rows 35-38)", () => {
  it("lists the investigations under the page's one eyebrow", () => {
    resources.data["/api/v1/data-plane/investigations"] = { records: [] };
    expect(render(<InvestigationList />)).not.toContain('<p class="ac-eyebrow">Investigations</p>');
  });

  it("keeps the reference in the investigation's eyebrow, Lot impact in its summary, and no second title in the fold", () => {
    const crumbs = investigations.slice(investigations.indexOf('<nav className="uw-crumbs"'));
    expect(crumbs.slice(0, crumbs.indexOf("</nav>"))).not.toContain("investigation_identifier");
    expect(caseSections).not.toContain("onLotImpact=");
    // A panel without a title has no empty heading.
    const html = renderToStaticMarkup(
      <Panel title="" eyebrow="Investigation progress">
        <p>Steps</p>
      </Panel>,
    );
    expect(html).not.toContain("<h2>");
    expect(html).toContain("Investigation progress");
  });
});

describe("Trends (rows 40, 41)", () => {
  const steady = {
    key: "k",
    product: { id: "p", business_id: null, identifier: "SAMPLE-PULSE-410", name: "PulseWatch 410" },
    product_version: { id: "v", business_id: null, version_identifier: "Rev A" },
    problem: null,
    name: "PulseWatch 410 Rev A",
    recent: 1,
    recent_days: 30,
    history: 6,
    history_days: 180,
    expected: 1.2,
    p_value: 0.6,
    p_adjusted: 0.9,
    groups_tested: 1,
    ratio: 0.8,
    result: "STEADY",
    label: "",
    sentence: "",
    recent_complaints: [],
    open_signals: [],
    basis: "UNITS",
    baseline: "OWN_HISTORY",
  } as unknown as TrendItem;
  const board = {
    grouping: "version",
    recent_days: 30,
    history_days: 180,
    min_complaints: 3,
    summary: {
      groups: 1,
      complaints_counted: 1,
      significant: 0,
      elevated: 0,
      steady: 1,
      too_few: 0,
      short_history: 0,
      groups_tested: 1,
    },
    items: [steady],
  } as unknown as TrendBoard;

  it("offers the Investigations button only to a persona without the Investigations tab", () => {
    expect(render(<TrendsSection />)).not.toContain("> Investigations</button>");
    const executive = render(
      <TrendsSection />,
      api({ persona: "executive", personaTabs: ["home", "trends", "records"] }),
    );
    expect(executive).toContain("Investigations</button>");
  });

  it("says no rise once, and leaves the rise counts and a second Trends eyebrow out of the fold", () => {
    const heroes = render(<TrendHeroes board={board} action={() => null} source={SAMPLE_SOURCE} />);
    // The chip says the verdict; the heading says what it was compared with.
    expect(heroes).toContain('uw-trend-verdict is-steady">No version is rising</span>');
    expect(heroes).toContain("compared with their own history: none rising.");
    resources.data["/api/v1/triage/trends"] = board;
    const page = render(<TrendCheck onOpenSignal={vi.fn()} />);
    expect(page).not.toContain("Significant rise</");
    expect(page).not.toContain("Higher than usual</");
    expect(page).toContain("Groups checked");
    expect(page).not.toContain('<p class="ac-eyebrow">Trends</p>');
  });
});

describe("Records, Import your data, Settings and Account (rows 42, 48, 53)", () => {
  it("says once on Import that each import has a data-quality report, keeping the link to them", () => {
    const fresh = render(<YourData />);
    expect(fresh).toContain("See the data-quality reports");
    expect(fresh).not.toContain("Each import has a data-quality report");
    expect(render(<YourData />, api({ navigation: "classic" }))).toContain("Each import has a data-quality report");
  });

  it("leaves what a record is for to the Records guide, and names each settings panel by its topic", () => {
    expect(records).not.toContain("Ready to hand to a colleague or an inspector.");
    expect(settings).not.toContain('eyebrow="Settings"');
    expect(account).not.toContain('eyebrow="My account"');
  });
});

// Read as a file: the test run does not load stylesheets (as releaseD3085.test.tsx does).
const fs = await import(/* @vite-ignore */ ["node", "fs"].join(":"));
const sheet: string = fs.readFileSync(new URL("./workspace.css", import.meta.url), "utf8").replace(/\r\n/g, "\n");

describe("layout: a long next step wraps inside its card (0.10.87)", () => {
  it("lets the complaint's Next step button wrap, at a 44 px touch height", () => {
    const rule = sheet.slice(sheet.indexOf(".uw-cp-next .ac-primary,\n.uw-cp-next .ac-secondary {"));
    const body = rule.slice(0, rule.indexOf("}"));
    expect(body).toContain("white-space: normal;");
    expect(body).toContain("min-height: 44px;");
    expect(body).toContain("max-width: 100%;");
    expect(sheet).toContain(".uw-cp-next {\n  min-width: 0;\n}");
  });
});

describe("layout: Records never scrolls sideways on a phone (0.10.87)", () => {
  it("lets the all-records grid item shrink, so the phone's one-row tabs scroll inside themselves", () => {
    const rule = sheet.slice(sheet.indexOf(".uw-records-all {"));
    expect(rule.slice(0, rule.indexOf("}"))).toContain("min-width: 0;");
  });
});
