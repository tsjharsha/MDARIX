import { describe, expect, it } from "vitest";
import {
  bandLabel,
  heroGeometry,
  heroHeadline,
  monotoneSegments,
  niceScale,
  peakText,
  tickEvery,
  timesText,
  versusText,
} from "./trendHero";
import { monthSeries, trendOf, type InsightRecord } from "./trialInsights";

const SERIES = monthSeries(["2026-04", "2026-10"]);

// Records giving each month of SERIES the count given, April to October 2026.
const recordsOf = (counts: number[], series = SERIES): InsightRecord[] =>
  counts.flatMap((count, index) =>
    Array.from({ length: count }, (_item, n) => ({
      id: `CMP-${index}-${n}`,
      ref: null,
      version: "PV1",
      lot: null,
      code: null,
      country: null,
      month: series[index],
      harm: false,
      malfunction: false,
      status: "open",
    })),
  );

// The sample's months: 3.0 a month before August, 8.3 since, the peak in September.
const SAMPLE = trendOf(recordsOf([1, 3, 3, 5, 7, 12, 6]), SERIES);
// Rev B alone: nothing before August.
const REV_B = trendOf(recordsOf([0, 0, 0, 0, 5, 9, 3]), SERIES);

describe("Hero trend: the headline", () => {
  it("leads with the recent rate against the months before", () => {
    const headline = heroHeadline(SAMPLE);
    expect(headline).toMatchObject({ decimals: 1, unit: "a month now", direction: "up", since: "2026-08" });
    expect(headline.value).toBeCloseTo(25 / 3);
    expect(headline.detail).toBe("up from 3.0 before · 2.8×");
  });

  it("says none before for a series that starts in the recent months, and how much lower for a fall", () => {
    expect(heroHeadline(REV_B)).toMatchObject({ direction: "new", detail: "none before Aug 2026" });
    const down = trendOf(recordsOf([6, 6, 6, 6, 3, 3, 3]), SERIES);
    expect(heroHeadline(down)).toMatchObject({ direction: "down", detail: "down from 6.0 before · 50% lower" });
    const flat = trendOf(recordsOf([2, 2, 2, 2, 2, 2, 2]), SERIES);
    expect(heroHeadline(flat).detail).toBe("the same as before (2.0 a month)");
  });

  it("shows the total and the months it spans with fewer than four months", () => {
    const two = monthSeries(["2026-09", "2026-10"]);
    const headline = heroHeadline(trendOf(recordsOf([4, 2], two), two));
    expect(headline).toEqual({
      value: 6,
      decimals: 0,
      unit: "complaints",
      detail: "Sep 2026 to Oct 2026",
      direction: null,
      since: "",
    });
    const one = ["2026-10"];
    expect(heroHeadline(trendOf(recordsOf([1], one), one))).toMatchObject({ unit: "complaint", detail: "In Oct 2026" });
  });

  it("writes ratios and each month against the earlier average plainly", () => {
    expect(timesText(4)).toBe("4×");
    expect(timesText(25 / 9)).toBe("2.8×");
    expect(versusText(12, SAMPLE)).toBe("+9.0 against the earlier average (3.0)");
    expect(versusText(1, SAMPLE)).toBe("−2.0 against the earlier average (3.0)");
    expect(versusText(3, SAMPLE)).toBe("At the earlier average (3.0)");
    expect(versusText(5, REV_B)).toBe("None a month before Aug '26");
  });
});

describe("Hero trend: the chart", () => {
  it("rounds the y-axis to whole complaints with at most five ticks", () => {
    expect(niceScale(12)).toEqual({ top: 15, ticks: [0, 5, 10, 15] });
    expect(niceScale(3)).toEqual({ top: 3, ticks: [0, 1, 2, 3] });
    expect(niceScale(0)).toEqual({ top: 1, ticks: [0, 1] });
    expect(niceScale(40).ticks).toEqual([0, 10, 20, 30, 40]);
  });

  it("places one point per month in the middle of its column, zero on the axis", () => {
    const g = heroGeometry(SAMPLE, 760);
    expect(g.compact).toBe(false);
    expect(g.points).toHaveLength(7);
    expect(g.points[0].x).toBeCloseTo(g.plot.left + g.step / 2);
    expect(g.points[1].x - g.points[0].x).toBeCloseTo(g.step);
    expect(g.points[5]).toMatchObject({ month: "2026-09", complaints: 12, recent: true });
    // 12 of a 15 top: a fifth of the plot below its top.
    expect(g.points[5].y).toBeCloseTo(g.plot.bottom - 0.8 * (g.plot.bottom - g.plot.top));
    expect(heroGeometry(REV_B, 760).points[0].y).toBe(g.plot.bottom);
    expect(g.line.startsWith(`M${g.points[0].x.toFixed(2).replace(/\.?0+$/, "")}`)).toBe(true);
    expect(g.area.endsWith("Z")).toBe(true);
  });

  it("draws a monotone curve that never overshoots its points, so never below zero", () => {
    const g = heroGeometry(REV_B, 760);
    for (const s of monotoneSegments(g.points)) {
      const [low, high] = [Math.min(s.y0, s.y1), Math.max(s.y0, s.y1)];
      expect(s.c1).toBeGreaterThanOrEqual(low - 1e-9);
      expect(s.c1).toBeLessThanOrEqual(high + 1e-9);
      expect(s.c2).toBeGreaterThanOrEqual(low - 1e-9);
      expect(s.c2).toBeLessThanOrEqual(high + 1e-9);
    }
    // Every y in the path lies between the peak and the axis.
    const ys = [...g.line.matchAll(/[\d.]+,([\d.]+)/g)].map((match) => Number(match[1]));
    expect(Math.max(...ys)).toBeLessThanOrEqual(g.plot.bottom);
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(g.points[5].y - 1e-9);
  });

  it("bands the last three months from their first, named for the rise", () => {
    const g = heroGeometry(SAMPLE, 760);
    expect(g.band).toMatchObject({ label: "Rise since Aug '26" });
    expect(g.band!.x).toBeCloseTo(g.plot.left + 4 * g.step);
    expect(g.band!.width).toBeCloseTo(3 * g.step);
    const down = heroGeometry(trendOf(recordsOf([6, 6, 6, 6, 3, 3, 3]), SERIES), 760);
    expect(down.band?.label).toBe("Last 3 months");
    expect(bandLabel("up", "2026-08", 60)).toBe("Since Aug '26");
    // Fewer than four months: no band and no average.
    const two = monthSeries(["2026-09", "2026-10"]);
    const short = heroGeometry(trendOf(recordsOf([4, 2], two), two), 760);
    expect(short.band).toBeNull();
    expect(short.average).toBeNull();
  });

  it("labels the earlier average beside its line, clear of the curve", () => {
    const g = heroGeometry(SAMPLE, 760);
    expect(g.average).toMatchObject({ label: "Average before: 3.0 a month" });
    expect(g.average!.y).toBeCloseTo(g.plot.bottom - 0.2 * (g.plot.bottom - g.plot.top));
    // With nothing before, no line on the axis: the label alone says so.
    const none = heroGeometry(REV_B, 760);
    expect(none.average).toMatchObject({ y: null, label: "None before Aug '26", anchor: "middle" });
    // In the middle of the earlier months, not in the band.
    expect(none.average!.labelX).toBeLessThan(none.band!.x);
    // On a phone the full label would cross the curve: shortened, then placed clear of it.
    expect(heroGeometry(SAMPLE, 326).average).toMatchObject({ label: "Avg before: 3.0", anchor: "end" });
  });

  it("calls out the peak with its multiple of the earlier average, only when there was one", () => {
    const g = heroGeometry(SAMPLE, 760);
    expect(g.peak).toMatchObject({ index: 5, text: "Sep '26: 12 complaints · 4× the earlier average" });
    // The callout sits above the plot, its leader down to the point.
    expect(g.peak!.box.y + g.peak!.box.height).toBeLessThanOrEqual(g.plot.top);
    expect(g.peak!.leader.x).toBeCloseTo(g.points[5].x);
    expect(g.peak!.box.x).toBeGreaterThanOrEqual(0);
    expect(g.peak!.box.x + g.peak!.box.width).toBeLessThanOrEqual(760);
    expect(heroGeometry(REV_B, 760).peak?.text).toBe("Sep '26: 9 complaints");
    expect(peakText("2026-09", 1, null, false)).toBe("Sep '26: 1 complaint");
    expect(heroGeometry(trendOf([], SERIES), 760).peak).toBeNull();
  });

  it("shortens the callout and thins the month ticks on a phone, keeping the latest month", () => {
    const g = heroGeometry(SAMPLE, 326);
    expect(g.compact).toBe(true);
    expect(g.peak?.text).toBe("Sep '26: 12 · 4×");
    expect(g.peak!.box.x + g.peak!.box.width).toBeLessThanOrEqual(326);
    expect(g.xTicks.map((tick) => tick.label)).toEqual(["Apr '26", "Jun '26", "Aug '26", "Oct '26"]);
    // Neighbouring ticks never closer than a label's width.
    const gaps = g.xTicks.slice(1).map((tick, index) => tick.x - g.xTicks[index].x);
    expect(Math.min(...gaps)).toBeGreaterThanOrEqual(50);
    expect(heroGeometry(SAMPLE, 760).xTicks).toHaveLength(7);
    expect(tickEvery(24, 12, true)).toBe(5);
  });
});
