import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { InsightsBody } from "./sections/TrialInsights";
import {
  applyFilters,
  breakdown,
  filterText,
  headlineOf,
  monthSeries,
  numericColumns,
  toggleFilter,
  trendOf,
  trendSummary,
  type InsightFilters,
  type InsightRecord,
  type Insights,
} from "./trialInsights";

const record = (
  id: string,
  month: string,
  version: string,
  lot: string | null,
  extra: Partial<InsightRecord> = {},
): InsightRecord => ({
  id,
  ref: `SRC-${id}`,
  version,
  lot,
  code: null,
  country: null,
  month,
  harm: false,
  malfunction: false,
  status: "open",
  ...extra,
});

// Ten complaints, April to October 2026 (June without any): one a month on Rev A before, then Rev B rises in August to
// October from lots L-3 and L-4. Problem codes and countries are on a few only, as in the sample.
const RECORDS: InsightRecord[] = [
  record("CMP001", "2026-04", "PV1", "L-1"),
  record("CMP002", "2026-05", "PV1", "L-1"),
  record("CMP003", "2026-07", "PV1", "L-2", { code: "NFF", country: "US" }),
  record("CMP004", "2026-08", "PV2", "L-3"),
  record("CMP005", "2026-08", "PV2", "L-3", { harm: true, malfunction: true, code: "NO_ALARM", country: "US" }),
  record("CMP006", "2026-09", "PV2", "L-3"),
  record("CMP007", "2026-09", "PV2", "L-4", { malfunction: true, country: "France" }),
  record("CMP008", "2026-09", "PV2", "L-4"),
  record("CMP009", "2026-10", "PV2", "L-3"),
  record("CMP010", "2026-10", "PV1", null),
];
const LABELS = { PV1: "OrbitCare 300 Rev A", PV2: "OrbitCare 300 Rev B" };

const INSIGHTS: Insights = {
  scope: "sample data",
  total_complaints: RECORDS.length,
  by_product: [],
  by_version: [],
  by_lot: [],
  findings: ["60% of complaints (6 of 10) concern OrbitCare 300 Rev B."],
  suggested_questions: ["What changed in OrbitCare 300 Rev B?", "Where are complaints coming from?"],
  note: "Counts and patterns from your records. They point to where to look; people decide what they mean.",
  records: RECORDS,
  version_labels: LABELS,
  questions: [
    {
      key: "version",
      question: "What changed in OrbitCare 300 Rev B?",
      answer: {
        summary: "OrbitCare 300: Rev B has 6 complaints, 2.0 per month since its first complaint in Aug 2026.",
        table: {
          columns: ["Version", "Released", "Complaints", "Per month", "Top lots"],
          rows: [
            ["Rev B", "2 Aug 2026", 6, "2.0", "L-3 (4), L-4 (2)"],
            ["Rev A", "—", 4, "—", "L-1 (2)"],
          ],
        },
        bars: null,
        facts: ["Rev B lists 1 component: Pressure Sensor: NovaSense since 28 Jul 2026."],
        ids: ["CMP004", "CMP005"],
        ids_total: 6,
        cases: [],
        basis: "Complaints by version.",
        missing: ["No change record is linked to OrbitCare 300 or its components."],
      },
    },
    {
      key: "origin",
      question: "Where are complaints coming from?",
      answer: {
        summary: "US has the most complaints (2 of 3 with a country; 2 countries in all).",
        table: null,
        bars: [{ label: "US", count: 2 }],
        facts: [],
        ids: [],
        ids_total: 0,
        cases: [{ id: "case-1", business_id: "INV000001", product_id: "product-1" }],
        basis: "The country and reporter type of each complaint.",
        missing: ["7 complaints have no country.", "No complaint records a reporter type."],
      },
    },
  ],
};

const noop = () => undefined;
const render = (
  props: Partial<{ insights: Insights; filters: InsightFilters; tab: "version" | "lot" | "code" | "country" }> & {
    expanded?: string | null;
    still?: boolean;
    onAsk?: ((question: string) => void) | null;
  } = {},
) =>
  renderToStaticMarkup(
    <InsightsBody
      insights={props.insights ?? INSIGHTS}
      filters={props.filters ?? {}}
      onFilter={noop}
      onClear={noop}
      tab={props.tab ?? "version"}
      onTab={noop}
      expanded={props.expanded ?? null}
      onExpand={noop}
      still={props.still ?? true}
      onOpenComplaints={noop}
      onOpenCase={noop}
      onAsk={props.onAsk === undefined ? noop : props.onAsk}
    />,
  );

// The text of one headline tile: its label, then its value.
const tile = (html: string, label: string) =>
  html.match(new RegExp(`<span class="ac-stat-label">${label}</span><strong class="ac-stat-value">([^<]*)<`))?.[1];

describe("Automatic insights: the numbers", () => {
  it("counts every month from the first to the last, a month without complaints as zero", () => {
    const series = monthSeries(RECORDS.map((item) => item.month));
    expect(series).toEqual(["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]);
    expect(monthSeries(["2025-11", null, "2026-02"])).toEqual(["2025-11", "2025-12", "2026-01", "2026-02"]);
    const trend = trendOf(RECORDS, series);
    expect(trend.months.map((item) => item.complaints)).toEqual([1, 1, 0, 1, 2, 3, 2]);
    expect(trend.months.filter((item) => item.recent).map((item) => item.month)).toEqual([
      "2026-08",
      "2026-09",
      "2026-10",
    ]);
    expect(trend.recentAverage).toBeCloseTo(7 / 3);
    expect(trend.earlierAverage).toBe(0.75);
    expect(trendSummary(trend)).toBe(
      "10 complaints from Apr 2026 to Oct 2026: the last 3 months average 2.3 per month, against 0.8 per month before.",
    );
  });

  it("computes the headline: harm, malfunctions, the top version's share and the recent rate", () => {
    const series = monthSeries(RECORDS.map((item) => item.month));
    const headline = headlineOf(RECORDS, series, LABELS);
    expect(headline).toMatchObject({ total: 10, harm: 1, malfunction: 2 });
    expect(headline.topVersion).toEqual({ label: "OrbitCare 300 Rev B", share: 60, complaints: 6 });
    expect(headline.rate?.direction).toBe("up");
    // Fewer than four months: nothing to compare the recent months with.
    expect(headlineOf(RECORDS.slice(5), monthSeries(["2026-09", "2026-10"]), LABELS).rate).toBeNull();
  });

  it("combines filters across tabs, replaces one on the same tab and clears one clicked again", () => {
    let filters = toggleFilter({}, "version", "PV2");
    filters = toggleFilter(filters, "lot", "L-3");
    expect(applyFilters(RECORDS, filters).map((item) => item.id)).toEqual(["CMP004", "CMP005", "CMP006", "CMP009"]);
    expect(filterText(filters, LABELS)).toBe("OrbitCare 300 Rev B and lot L-3");
    filters = toggleFilter(filters, "lot", "L-4");
    expect(applyFilters(RECORDS, filters).map((item) => item.id)).toEqual(["CMP007", "CMP008"]);
    filters = toggleFilter(filters, "lot", "L-4");
    expect(filters).toEqual({ version: "PV2" });
  });

  it("counts the complaints that leave a facet empty apart from the bars", () => {
    expect(breakdown(RECORDS, "code")).toEqual({
      items: [
        { key: "NFF", label: "NFF", count: 1 },
        { key: "NO_ALARM", label: "NO_ALARM", count: 1 },
      ],
      unrecorded: 8,
    });
    expect(breakdown(RECORDS, "version", LABELS).items[0]).toEqual({
      key: "PV2",
      label: "OrbitCare 300 Rev B",
      count: 6,
    });
  });
});

describe("Automatic insights: the panel", () => {
  it("shows the headline numbers, the trend and clickable bars", () => {
    const html = render();
    expect(tile(html, "Complaints")).toBe("10");
    expect(tile(html, "With harm")).toBe("1");
    expect(tile(html, "Malfunctions")).toBe("2");
    expect(tile(html, "Top version")).toBe("60%");
    expect(tile(html, "Recent rate")).toBe("2.3");
    expect(html).toContain("OrbitCare 300 Rev B, 6 complaints");
    expect(html).toContain("0.8 before (up)");
    expect(html).toContain('role="img" aria-label="10 complaints from Apr 2026 to Oct 2026');
    expect(html).toContain("Average before: 0.8 per month");
    expect(html.match(/class="uw-ins-month is-recent"/g)).toHaveLength(3);
    expect(html).toContain("Show table");
    // Every breakdown bar is a button that says whether it is the filter.
    expect(html.match(/<button type="button" aria-pressed="false"/g)).toHaveLength(2);
    expect(html).toContain('role="tablist" aria-label="Complaints by"');
    expect(html).toContain("All 10 complaints. Click a bar to see only its complaints");
    expect(html).toContain("Open these complaints");
    expect(html).toContain(INSIGHTS.note);
  });

  it("filters the whole panel by the bar clicked, with a chip to clear it", () => {
    // A click on the Rev B bar calls onFilter("version", "PV2"), which sets this filter.
    const filters = toggleFilter({}, "version", "PV2");
    const html = render({ filters });
    expect(tile(html, "Complaints")).toBe("6");
    expect(tile(html, "With harm")).toBe("1");
    expect(tile(html, "Share of all")).toBe("60%");
    expect(html).toContain("Showing 6 complaints of 10:");
    expect(html).toContain("Version: OrbitCare 300 Rev B");
    expect(html).toContain('aria-label="Clear the filter OrbitCare 300 Rev B"');
    expect(html).toContain("Clear all");
    expect(html).toContain('aria-pressed="true" class="is-on"');
    expect(html).toContain("List the 6 complaints");
    expect(html).toContain("CMP004 (SRC-CMP004)");
    // The other tabs count only the filtered complaints: the lot tab holds L-3 and L-4.
    const lots = render({ filters, tab: "lot" });
    expect(lots).toContain("L-3");
    expect(lots).not.toContain(">L-1<");
    expect(lots).toContain("the filter above does not change them");
  });

  it("opens a question onto its answer, with what it used and what the records lack", () => {
    const closed = render();
    expect(closed).toContain('aria-expanded="false" aria-controls="uw-ins-answer-version"');
    expect(closed).toContain('id="uw-ins-answer-version" class="uw-ins-answer" hidden=""');
    const open = render({ expanded: "version" });
    expect(open).toContain('aria-expanded="true" aria-controls="uw-ins-answer-version"');
    expect(open).not.toContain('id="uw-ins-answer-version" class="uw-ins-answer" hidden=""');
    expect(open).toContain("Rev B has 6 complaints, 2.0 per month since its first complaint in Aug 2026.");
    expect(open).toContain("Complaints used:</b> CMP004, CMP005 and 4 more");
    expect(open).toContain("Based on:</b> Complaints by version.");
    expect(open).toContain("Not in the records");
    expect(open).toContain("No change record is linked to OrbitCare 300 or its components.");
    expect(open).toContain("Answered from all 10 complaints by fixed rules, not by AI");
    const origin = render({ expanded: "origin" });
    expect(origin).toContain("INV000001");
    expect(origin).toContain("No complaint records a reporter type.");
  });

  it("right-aligns every numeric column of an answer's table, its heading and its cells alike", () => {
    const table = INSIGHTS.questions![0].answer.table!;
    expect(numericColumns(table)).toEqual([false, false, true, true, false]);
    expect(
      numericColumns({
        columns: ["Lot", "Quantity", "Per 1,000 units"],
        rows: [
          ["L-1", "1,250", "37.8"],
          ["L-2", "—", "—"],
        ],
      }),
    ).toEqual([false, true, true]);
    expect(numericColumns({ columns: ["Quantity"], rows: [["—"]] })).toEqual([false]);
    const open = render({ expanded: "version" });
    expect(open).toContain('<th scope="col">Released</th><th scope="col" class="num">Complaints</th>');
    expect(open).toContain('<th scope="col" class="num">Per month</th><th scope="col">Top lots</th>');
    expect(open).toContain(
      '<td>2 Aug 2026</td><td class="num">6</td><td class="num">2.0</td><td>L-3 (4), L-4 (2)</td>',
    );
    expect(open).toContain('<td class="num">4</td><td class="num">—</td>');
  });

  it("offers Ask MDARIX to look further only while AI answers", () => {
    expect(render({ expanded: "version" })).toContain("Ask MDARIX to look further");
    const withoutAi = render({ expanded: "version", onAsk: null });
    expect(withoutAi).not.toContain("Ask MDARIX to look further");
    expect(withoutAi).toContain("Based on:</b> Complaints by version.");
  });

  it("says plainly when a tab has nothing recorded", () => {
    const html = render({ filters: { version: "PV1" }, tab: "code" });
    // Rev A: CMP001-003 and CMP010; only CMP003 has a problem code.
    expect(html).toContain("NFF");
    expect(html).toContain("3 complaints have no problem code.");
    const none = render({ filters: { lot: "L-4" }, tab: "code" });
    expect(none).toContain("No complaint in this filter records a problem code.");
  });

  it("shows every number at its end state without motion, and animates otherwise", () => {
    const still = render({ still: true });
    expect(still).toContain('class="uw-ins is-still"');
    expect(tile(still, "Complaints")).toBe("10");
    const moving = render({ still: false });
    expect(moving).toContain('class="uw-ins"');
    expect(moving).not.toContain("is-still");
  });

  it("keeps the empty state, and shows the findings alone from a server without the new fields", () => {
    expect(render({ insights: { ...INSIGHTS, total_complaints: 0, records: [] } })).toContain("No complaints yet");
    const older = render({ insights: { ...INSIGHTS, records: undefined, questions: undefined } });
    expect(older).toContain(INSIGHTS.findings[0]);
    expect(older).not.toContain("Complaints per month");
  });
});

describe("Automatic insights: a version filter", () => {
  it("shows the version's share of all complaints, and a version new in the recent months as new, not as a rise", () => {
    const series = monthSeries(RECORDS.map((item) => item.month));
    const rate = headlineOf(applyFilters(RECORDS, { version: "PV2" }), series, LABELS).rate;
    expect(rate).toMatchObject({ direction: "new", since: "2026-08", earlier: 0 });
    const html = render({ filters: { version: "PV2" } });
    expect(tile(html, "Share of all")).toBe("60%");
    expect(tile(html, "Top version")).toBeUndefined();
    expect(html).toContain("OrbitCare 300 Rev B: 6 of all 10 complaints");
    expect(html).toContain("none before Aug 2026");
    expect(html).not.toContain("0.0 before");
  });
});
