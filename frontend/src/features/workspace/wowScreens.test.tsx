import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { worksheetMeter } from "./authorityReports";
import { legalLanes } from "./sections/ComplaintPage";
import { TrendPerUnit } from "./sections/TrendCheck";
import { Bars, ClockLanes } from "./sections/WowCharts";
import type { EventView } from "./oversight";
import type { TrendItem } from "./signalAi";

// Quality plan stage 8 (8.5): the wow screens' charts carry their numbers in words, never colour alone.

describe("the wow screens", () => {
  it("draws one legal clock per market, from awareness to its deadline, with the time left in words", () => {
    const due = (market: string, title: string, at: string, hours: number) => ({
      key: `${market}-${title}`,
      category: "REPORTING",
      category_label: "Reporting",
      title,
      market,
      due_at: at,
      state: "LATER" as const,
      state_label: "Later",
      hours_left: hours,
      opens: { section: "Complaints" },
    });
    const view = {
      event: { awareness_at: "2026-11-01T09:00:00Z" },
      work: {
        due: [
          due("US", "United States (FDA): 30-day report", "2026-12-01T04:59:00Z", 700),
          due("US", "A later US item", "2026-12-20T04:59:00Z", 900),
          due("IN", "India (CDSCO)", "2026-11-03T18:29:00Z", 30),
        ],
        markets: ["US", "IN"],
      },
    } as unknown as EventView;
    const lanes = legalLanes(view);
    expect(lanes.map((lane) => lane.stateText)).toEqual(["29 days left", "30 hours left"]);
    const html = renderToStaticMarkup(<ClockLanes lanes={lanes} now={new Date("2026-11-02T09:00:00Z")} />);
    expect(html).toContain("United States (FDA): 30-day report");
    expect(html).toContain("legal deadline");
  });

  it("shows the trend per unit against the earlier average, the rise named in words", () => {
    const item = (name: string, recent: number, expected: number, result: TrendItem["result"]) =>
      ({
        key: name,
        name,
        recent,
        recent_days: 30,
        expected,
        p_value: 0.01,
        ratio: recent / expected,
        result,
        label: "",
        basis: "UNITS",
      }) as unknown as TrendItem;
    const html = renderToStaticMarkup(
      <TrendPerUnit items={[item("Rev A", 3, 0.99, "STEADY"), item("Rev B", 9, 0.96, "SIGNIFICANT")]} />,
    );
    expect(html.indexOf("Rev B")).toBeLessThan(html.indexOf("Rev A"));
    expect(html).toContain("9 in the last 30 days");
    expect(html).toContain("the earlier average predicts 0.96 for its units in the field");
    expect(html).toContain("Significant rise");
    expect(html).toContain("Table view");
  });

  it("puts every bar's number in words", () => {
    const html = renderToStaticMarkup(
      <Bars
        label="Lots"
        rows={[{ key: "a", label: "LOT-003", value: 60, valueText: "60 per 1,000 units", flag: "has complaints" }]}
      />,
    );
    expect(html).toContain("60 per 1,000 units");
    expect(html).toContain("has complaints");
  });

  it("counts the worksheet's fields filled from the records and the missing ones", () => {
    const field = (status: string) => ({ status }) as never;
    expect(
      worksheetMeter([
        { code: "A", title: "A", note: null, fields: [field("FROM_RECORD"), field("CONFIRMED"), field("MUST_HAVE")] },
        { code: "B", title: "B", note: null, fields: [field("ENTERED"), field("MAY_BE_UNKNOWN")] },
      ]),
    ).toEqual({ total: 5, fromRecords: 2, entered: 1, missing: 1 });
  });
});
