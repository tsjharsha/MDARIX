// 0.10.85, round D3 "Polish to 9.5": what shows on screen, each with the test that fails before.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Table } from "../customer-admin/shared";
import { ColumnScopeProvider } from "../tables/ColumnChooser";
import { workColumns } from "./sections/ComplaintList";

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
