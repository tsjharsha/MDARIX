// 0.10.85, round D3 "Polish to 9.5": what shows on screen, each with the test that fails before.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Table } from "../customer-admin/shared";
import { ColumnScopeProvider } from "../tables/ColumnChooser";
import { workColumns } from "./sections/ComplaintList";
import { deadlineLabel, formatDateTime, formatDay, setDisplayZone, zoneName, zoneless } from "../../app/dates";
import userWorkspace from "./UserWorkspace.tsx?raw";
import hybridShell from "./HybridShell.tsx?raw";
import { recordHits } from "./HybridShell";
import home from "./sections/Home.tsx?raw";

const stubWindow = () =>
  vi.stubGlobal("window", {
    location: { pathname: "/app/complaints", search: "", hash: "", origin: "https://mdarix.test" },
    localStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
    sessionStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
    dispatchEvent: () => true,
  });

describe("D3.1 the complaint list", () => {
  beforeEach(stubWindow);
  afterEach(() => vi.unstubAllGlobals());
  const row = (extra: Record<string, unknown>) => ({
    id: "c1",
    complaint_identifier: "SAMPLE-RV-08",
    description: "The pump free-flowed briefly.",
    product_name: "OrbitCare 300",
    version: "Rev B",
    lot: "LOT-005",
    country: "United States",
    problem_code: "FREE_FLOW_DOOR",
    work: {
      owner_name: "Asha Menon",
      stage: "Report",
      next: null,
      markets: ["US"],
      due: [
        {
          key: "t",
          category: "TRIAGE",
          title: "Triage target",
          market: null,
          due_at: new Date(Date.now() + 20 * 3_600_000).toISOString(),
          state: "RUNNING",
          hours_left: 20,
        },
        {
          key: "w",
          category: "REPORTING",
          title: "US 30-day",
          market: "US",
          due_at: new Date(Date.now() + 600 * 3_600_000).toISOString(),
          state: "RUNNING",
          hours_left: 600,
        },
      ],
    },
    ...extra,
  });
  const html = (rows: any[], links: any = {}) =>
    renderToStaticMarkup(
      <ColumnScopeProvider scope="test">
        <Table
          caption="All open complaints"
          rows={rows}
          rowKey={(item: any) => String(item.id)}
          empty={{ title: "", detail: "" }}
          onRowClick={() => undefined}
          chooserUnderMore
          className="uw-clist"
          columns={workColumns(links, () => undefined)}
        />
      </ColumnScopeProvider>,
    );

  it("leads with the legal clock, names the IMDRF term (never the raw code) and the incident country", () => {
    const links = {
      FREE_FLOW_DOOR: [{ release: "2025", annex: "A", code: "A140502", term: "Free or Unrestricted Flow" }],
    };
    const out = html([row({}), row({ id: "c2", country: null, problem_code: "OWN_CODE" })], links);
    expect(out).toContain("Free or Unrestricted Flow");
    expect(out).toContain("No IMDRF term yet");
    expect(out.replace(/title="[^"]*"/g, "")).not.toMatch(/FREE_FLOW_DOOR|OWN_CODE/);
    expect(out).toContain("United States");
    expect(out).toContain("Asked at the tree");
    // The legal clock (25 days), not the nearer triage target, is the row's clock.
    expect(out).toMatch(/ms-chip-deadline[^>]*>.*\d+ days left/);
    expect(out).not.toMatch(/ms-chip-deadline[^>]*>[^<]*<[^>]*>[^<]*\d+ h left/);
  });

  it("has one action per row, opens on a row click, and keeps the column choice under More", () => {
    const out = html([row({})]);
    expect(out.match(/<tr class="is-clickable"/g)).toHaveLength(1);
    expect(out.match(/<tbody>.*<\/tbody>/s)![0].match(/<button/g)).toHaveLength(1);
    expect(out).toMatch(/<details class="tc-more"><summary>More<\/summary>/);
    expect(out).toContain("uw-clist");
  });
});

describe("D3.1 an overdue target beside the legal clock", () => {
  it("says why the row is first", () => {
    const row = {
      id: "c1",
      complaint_identifier: "SAMPLE-RV-08",
      work: {
        owner_name: null,
        stage: "Triage",
        next: null,
        markets: [],
        due: [
          {
            key: "r",
            category: "REQUEST",
            category_label: "Reply due",
            title: "Reply",
            market: null,
            due_at: new Date(Date.now() - 48 * 3_600_000).toISOString(),
            state: "OVERDUE",
            hours_left: -48,
          },
          {
            key: "w",
            category: "REPORTING",
            category_label: "Reporting",
            title: "US",
            market: "US",
            due_at: new Date(Date.now() + 600 * 3_600_000).toISOString(),
            state: "RUNNING",
            hours_left: 600,
          },
        ],
      },
    };
    const html = renderToStaticMarkup(<>{workColumns({}, () => undefined)[0].render(row)}</>);
    expect(html).toMatch(/\d+ days left/);
    expect(html).toMatch(/Reply due: 2 days overdue/);
  });
});

describe("D3.6 the organization's time zone, named once", () => {
  afterEach(() => setDisplayZone(null));
  it("reads every time in the organization's zone and drops the zone from each deadline label", () => {
    setDisplayZone("America/New_York");
    // 09:00 UTC is 04:00 in New York (EST, November), whatever the browser's zone.
    expect(formatDateTime("2026-11-20T09:00:00Z")).toBe("20 Nov 2026, 04:00");
    expect(zoneName(new Date("2026-11-20T09:00:00Z"))).toBe("Eastern Standard Time");
    expect(deadlineLabel({ due_label: "Mon 30 Nov 2026, 23:59 EST" })).toBe("Mon 30 Nov 2026, 23:59");
    expect(zoneless("Wed 2 Dec 2026, 23:59 GMT+5:30")).toBe("Wed 2 Dec 2026, 23:59");
    // A calendar date stays its day.
    expect(formatDay("2026-11-20")).toBe("20 Nov 2026");
  });
  it("keeps the label's zone where the page does not name one (the classic navigation)", () => {
    setDisplayZone(null);
    expect(deadlineLabel({ due_label: "Mon 30 Nov 2026, 23:59 IST" })).toBe("Mon 30 Nov 2026, 23:59 IST");
  });
  it("names the zone in every new-navigation page head", () => {
    expect(userWorkspace).toContain("Times are in {zoneName()}, your organization's time zone.");
    expect(userWorkspace).toContain('"/api/v1/oversight/settings"');
  });
});

// Read as a file: the test run does not load stylesheets (as releaseC2074.test.tsx does).
const fs = await import(/* @vite-ignore */ ["node", "fs"].join(":"));
const css: string = fs.readFileSync(new URL("./workspace.css", import.meta.url), "utf8");

describe("D3.7 the phone keeps where you are and what each number means", () => {
  it("scrolls the current tab into view, and gives each Home tile one short line on a phone", () => {
    expect(hybridShell).toMatch(/querySelector<HTMLElement>\("\[aria-current='page'\]"\)\s*\?\.scrollIntoView/);
    expect(home).toContain('className="uw-home-short"');
    const sheet = css.replace(/\r\n/g, "\n");
    expect(sheet).toContain(".uw-home-stat .uw-home-short {\n    display: block;");
    expect(sheet).not.toContain(".uw-home-stat span {\n    display: none;");
  });
});

describe("D3.8 accessibility on the new navigation", () => {
  const read = (path: string) => fs.readFileSync(new URL(path, import.meta.url), "utf8").replace(/\r\n/g, "\n");
  it("gives every focusable column grip its value, and every tree question a fieldset and a skip link", () => {
    expect(read("../tables/useColumnControls.tsx")).toContain(
      "aria-valuenow={widths && width ? width : MIN_COLUMN_WIDTH}",
    );
    const tree = read("./sections/TreeAnswer.tsx");
    expect(tree).toContain('<fieldset className="dt-fieldset" aria-labelledby={`qt-${first.id}`}>');
    expect(tree).not.toContain('role="group"\n      aria-labelledby');
    expect(tree).toContain('href="#dt-questions"');
    expect(tree).toContain('id="dt-questions"');
  });
  it("keeps text at 12 px or more, chips and dots at 4.5:1, and phone targets at 44 px", () => {
    const sheet = read("./workspace.css");
    expect(sheet).toContain('main[data-navigation="new"] small {\n  font-size: max(var(--ms-fs-12), 0.8em);');
    expect(sheet).toMatch(/main\[data-navigation="new"\]\s*:is\(\.ac-primary[^{]*\{\s*min-height: 44px;/);
    expect(read("../customer-admin/customer-admin.css")).toMatch(
      /\.ca-chips button\.selected \{[^}]*color: var\(--ms-teal-dark\)/,
    );
    expect(read("./sections/qualityLoop.css")).toContain("background: #d18f12;");
  });
  it("says why a main button is disabled", () => {
    expect(read("./sections/TreeEdit.tsx")).toContain('title={!password ? "Enter your password first" : undefined}');
    expect(read("./sections/Reports.tsx")).toContain("title={problem || undefined}");
    expect(read("./sections/Triage.tsx")).toContain("title={problem || undefined}");
  });
});

describe("D3.11 search finds every record", () => {
  it("finds an investigation by its reference or question and a trend by its title, each opening its page", () => {
    const go = vi.fn((place: { section: string; tab?: string }) => () => place);
    const hits = recordHits(
      [
        { record_type: "product", id: "p", name: "OrbitCare 300" },
        {
          record_type: "investigation",
          id: "i",
          investigation_identifier: "SAMPLE-INV-001",
          investigation_question: "Why did pressure alarms rise?",
        },
      ],
      [{ id: "s", business_id: "SIG000001", title: "6 complaints: pressure alarm on OrbitCare 300" }],
      go,
    );
    expect(hits.map((hit) => [hit.kind, hit.title])).toEqual([
      ["Investigation", "SAMPLE-INV-001"],
      ["Trend", "6 complaints: pressure alarm on OrbitCare 300"],
    ]);
    expect(go).toHaveBeenCalledWith({ section: "Trends", tab: "Trends to review?signal=SIG000001" });
    expect(hybridShell).toContain("/api/v1/triage/signals?q=${term}&page_size=5");
  });
});
