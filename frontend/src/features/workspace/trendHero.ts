// Pure rules for the hero trend card on Getting started › Automatic insights (sections/TrendHero.tsx): the headline,
// and the chart's geometry for a given width (the points, the monotone curve, the band over the last three months, the
// earlier average, the peak callout, the month ticks) with the words on it. No DOM, so the tests check them directly.
import { RECENT_MONTHS, monthLabel, rateText, type Trend } from "./trialInsights";

/** "2026-08" as "Aug '26", for the ticks and labels on the chart. */
export const shortMonth = (month: string) => monthLabel(month).replace(" 20", " '");

/** A ratio as "4×" or "2.8×": one decimal, none for a whole number. */
export const timesText = (ratio: number) => `${Number(ratio.toFixed(1))}×`;

const complaints = (count: number) => `${count.toLocaleString()} ${count === 1 ? "complaint" : "complaints"}`;

export type Direction = "up" | "down" | "flat" | "new";

export type HeroHeadline = {
  /** The large number: the recent rate a month, or with fewer than four months the total. */
  value: number;
  /** One decimal for a rate, none for a total. */
  decimals: 0 | 1;
  unit: string;
  detail: string;
  /** Null with fewer than four months: nothing before the recent months to compare them with. */
  direction: Direction | null;
  /** The first of the recent months ("" without them). */
  since: string;
};

/** The card's headline, counted the way `headlineOf` counts the Recent rate tile. */
export function heroHeadline(trend: Trend): HeroHeadline {
  const total = trend.months.reduce((sum, item) => sum + item.complaints, 0);
  const since = trend.months.find((item) => item.recent)?.month ?? "";
  if (trend.recentAverage === null || trend.earlierAverage === null) {
    const first = trend.months[0]?.month;
    const last = trend.months[trend.months.length - 1]?.month;
    const detail = !first
      ? "No complaint records a month"
      : first === last
        ? `In ${monthLabel(first)}`
        : `${monthLabel(first)} to ${monthLabel(last)}`;
    return {
      value: total,
      decimals: 0,
      unit: total === 1 ? "complaint" : "complaints",
      detail,
      direction: null,
      since,
    };
  }
  const recent = trend.recentAverage;
  const earlier = trend.earlierAverage;
  const direction: Direction =
    earlier === 0 && recent > 0 ? "new" : recent > earlier ? "up" : recent < earlier ? "down" : "flat";
  const detail =
    direction === "new"
      ? `none before ${monthLabel(since)}`
      : direction === "up"
        ? `up from ${rateText(earlier)} before · ${timesText(recent / earlier)}`
        : direction === "down"
          ? recent === 0
            ? `down from ${rateText(earlier)} before · none since ${monthLabel(since)}`
            : `down from ${rateText(earlier)} before · ${Math.round(100 * (1 - recent / earlier))}% lower`
          : `the same as before (${rateText(earlier)} a month)`;
  return { value: recent, decimals: 1, unit: "a month now", detail, direction, since };
}

/** One month against the earlier average, for its tooltip (null with nothing to compare it with). */
export function versusText(count: number, trend: Trend): string | null {
  const earlier = trend.earlierAverage;
  if (earlier === null) return null;
  const since = trend.months.find((item) => item.recent)?.month ?? "";
  if (earlier === 0) return `None a month before ${shortMonth(since)}`;
  const difference = count - earlier;
  if (Math.abs(difference) < 0.05) return `At the earlier average (${rateText(earlier)})`;
  return `${difference > 0 ? "+" : "−"}${rateText(Math.abs(difference))} against the earlier average (${rateText(earlier)})`;
}

// Text is not measured in the DOM (the geometry is computed before paint and in tests): a generous width per character
// of the app's sans at a given size, so a label that fits here fits on screen.
export const textWidth = (text: string, size: number) => Math.ceil(text.length * size * 0.6);

/** Below this chart width the chart is compact: shorter, shorter labels, fewer month ticks. */
export const COMPACT_BELOW = 520;
const LABEL_SIZE = 11;
const CALLOUT_SIZE = 12;
// Rows above the plot: the band's label (0-24), then the peak callout (30-56); the plot starts below them, so neither
// can sit on the curve. The month ticks sit in the last 28 px.
const BAND_ROW = 17;
const CALLOUT_TOP = 30;
const CALLOUT_HEIGHT = 26;
const PLOT_TOP = 70;
const TICK_BAND = 28;
const LEFT = 34;
const RIGHT = 12;

/** A round top for the y-axis and its ticks (whole complaints, at most five ticks). */
export function niceScale(max: number): { top: number; ticks: number[] } {
  const value = Math.max(1, max);
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step =
    [0.1, 0.2, 0.5, 1, 2, 5, 10]
      .map((unit) => Number((unit * magnitude).toPrecision(2)))
      .filter((unit) => unit >= 1)
      .find((unit) => value / unit <= 4) ?? 10 * magnitude;
  const top = Math.ceil(value / step) * step;
  const ticks: number[] = [];
  for (let tick = 0; tick <= top; tick += step) ticks.push(tick);
  return { top, ticks };
}

export type Point = { x: number; y: number; month: string; complaints: number; recent: boolean };
/** A cubic segment from one point to the next; its x moves linearly with t (control points at the thirds). */
type Segment = { x0: number; y0: number; c1: number; c2: number; x1: number; y1: number };

/**
 * A monotone cubic through the points (Fritsch-Carlson tangents, as d3's curveMonotoneX): it never rises above the
 * higher or dips below the lower of two neighbouring points, so the curve never goes under zero or over the peak.
 */
export function monotoneSegments(points: { x: number; y: number }[]): Segment[] {
  const n = points.length;
  if (n < 2) return [];
  const slopes = points.slice(1).map((point, index) => (point.y - points[index].y) / (point.x - points[index].x));
  const tangents = points.map((_point, index) => {
    if (index === 0 || index === n - 1) return NaN;
    const [before, after] = [slopes[index - 1], slopes[index]];
    if (before * after <= 0) return 0;
    const h0 = points[index].x - points[index - 1].x;
    const h1 = points[index + 1].x - points[index].x;
    const mean = (before * h1 + after * h0) / (h0 + h1);
    return Math.sign(before) * Math.min(Math.abs(before), Math.abs(after), 0.5 * Math.abs(mean)) * 2;
  });
  // The ends: the one-sided tangent d3 uses, from the end slope and its neighbour's tangent.
  tangents[0] = n === 2 ? slopes[0] : (3 * slopes[0] - tangents[1]) / 2;
  tangents[n - 1] = n === 2 ? slopes[0] : (3 * slopes[n - 2] - tangents[n - 2]) / 2;
  return slopes.map((_slope, index) => {
    const [from, to] = [points[index], points[index + 1]];
    const third = (to.x - from.x) / 3;
    return {
      x0: from.x,
      y0: from.y,
      c1: from.y + tangents[index] * third,
      c2: to.y - tangents[index + 1] * third,
      x1: to.x,
      y1: to.y,
    };
  });
}

const f = (value: number) => Number(value.toFixed(2));

export function curvePath(points: { x: number; y: number }[]): string {
  if (!points.length) return "";
  const segments = monotoneSegments(points);
  return [
    `M${f(points[0].x)},${f(points[0].y)}`,
    ...segments.map(
      (s) =>
        `C${f(s.x0 + (s.x1 - s.x0) / 3)},${f(s.c1)} ${f(s.x1 - (s.x1 - s.x0) / 3)},${f(s.c2)} ${f(s.x1)},${f(s.y1)}`,
    ),
  ].join(" ");
}

/** The curve's y at x (the points' own y outside them). */
function curveY(points: Point[], segments: Segment[], x: number): number {
  if (!points.length) return Infinity;
  if (x <= points[0].x) return points[0].y;
  if (x >= points[points.length - 1].x) return points[points.length - 1].y;
  const s = segments.find((segment) => x <= segment.x1) ?? segments[segments.length - 1];
  const t = (x - s.x0) / (s.x1 - s.x0);
  const u = 1 - t;
  return u * u * u * s.y0 + 3 * u * u * t * s.c1 + 3 * u * t * t * s.c2 + t * t * t * s.y1;
}

export type HeroGeometry = {
  width: number;
  height: number;
  compact: boolean;
  plot: { left: number; right: number; top: number; bottom: number };
  /** The width of one month's column: its hit target. */
  step: number;
  points: Point[];
  line: string;
  area: string;
  yTicks: { y: number; label: string }[];
  xTicks: { x: number; label: string }[];
  /** The last three months, behind the curve, with its label at its start. */
  band: { x: number; width: number; label: string; labelX: number; labelY: number } | null;
  /** The earlier months' average; `y` is null when it is zero (the axis itself), so only its label shows. */
  average: {
    y: number | null;
    label: string;
    labelX: number;
    labelY: number;
    anchor: "start" | "middle" | "end";
  } | null;
  /** The highest month, called out above the plot with a leader down to its point. */
  peak: {
    index: number;
    text: string;
    box: { x: number; y: number; width: number; height: number };
    leader: { x: number; y1: number; y2: number };
  } | null;
};

/** Month ticks: every `every`-th month counted back from the last, so the latest month is always labelled. */
export function tickEvery(months: number, step: number, compact: boolean): number {
  const gap = compact ? 50 : 58;
  return Math.max(1, Math.ceil(gap / Math.max(1, step)), months > 12 && compact ? 3 : 1);
}

/** The band's label: the rise named from its first month when complaints went up, else just the window. */
export function bandLabel(direction: Direction | null, since: string, room: number): string {
  if (direction !== "up" && direction !== "new") return `Last ${RECENT_MONTHS} months`;
  const full = `Rise since ${shortMonth(since)}`;
  return textWidth(full, LABEL_SIZE) <= room ? full : `Since ${shortMonth(since)}`;
}

/** The peak callout: "Sep '26: 12 complaints · 4× the earlier average", or on a narrow chart "Sep '26: 12 · 4×". */
export function peakText(month: string, count: number, earlier: number | null, compact: boolean): string {
  const times = earlier ? timesText(count / earlier) : null;
  if (compact) return `${shortMonth(month)}: ${count.toLocaleString()}${times ? ` · ${times}` : ""}`;
  return `${shortMonth(month)}: ${complaints(count)}${times ? ` · ${times} the earlier average` : ""}`;
}

/** The chart for a given width in px: every position and label, computed once and drawn as is. */
export function heroGeometry(trend: Trend, width: number): HeroGeometry {
  const compact = width < COMPACT_BELOW;
  const height = compact ? 250 : 290;
  const plot = { left: LEFT, right: width - RIGHT, top: PLOT_TOP, bottom: height - TICK_BAND };
  const n = trend.months.length;
  const step = n ? (plot.right - plot.left) / n : 0;
  const max = Math.max(0, ...trend.months.map((item) => item.complaints), trend.earlierAverage ?? 0);
  const scale = niceScale(max);
  const yOf = (value: number) => plot.bottom - (value / scale.top) * (plot.bottom - plot.top);
  const points: Point[] = trend.months.map((item, index) => ({
    x: plot.left + step * (index + 0.5),
    y: yOf(item.complaints),
    ...item,
  }));
  const segments = monotoneSegments(points);
  const line = curvePath(points);
  const area =
    points.length > 1
      ? `${line} L${f(points[points.length - 1].x)},${f(plot.bottom)} L${f(points[0].x)},${f(plot.bottom)} Z`
      : "";
  const yTicks = scale.ticks.map((tick) => ({ y: f(yOf(tick)), label: tick.toLocaleString() }));
  const every = tickEvery(n, step, compact);
  const xTicks = points
    .filter((_point, index) => (n - 1 - index) % every === 0)
    .map((point) => ({ x: point.x, label: shortMonth(point.month) }));

  const headline = heroHeadline(trend);
  const compared = trend.recentAverage !== null && trend.earlierAverage !== null;
  let band: HeroGeometry["band"] = null;
  if (compared) {
    const x = plot.left + step * (n - RECENT_MONTHS);
    const bandWidth = step * RECENT_MONTHS;
    const label = bandLabel(headline.direction, headline.since, bandWidth - 16);
    // At the band's start; a label wider than the band ends at the plot's edge instead of running off it.
    const labelX = Math.min(x + 10, plot.right - textWidth(label, LABEL_SIZE));
    band = { x, width: bandWidth, label, labelX, labelY: BAND_ROW };
  }

  let average: HeroGeometry["average"] = null;
  if (compared && trend.earlierAverage !== null && band) {
    const earlier = trend.earlierAverage;
    if (earlier === 0) {
      // Nothing before: no line on the axis, the label in the middle of the earlier months, just above them.
      average = {
        y: null,
        label: `None before ${shortMonth(headline.since)}`,
        labelX: f((plot.left + band.x) / 2),
        labelY: f(plot.bottom - 9),
        anchor: "middle",
      };
    } else {
      const y = yOf(earlier);
      // Beside the line wherever the curve leaves room: right end above, below, then the left end; on a narrow
      // chart the label is shortened before it is placed on the curve.
      const labels = [`Average before: ${rateText(earlier)} a month`, `Avg before: ${rateText(earlier)}`];
      const spots = [
        { anchor: "end", x: plot.right - 4, baseline: y - 7 },
        { anchor: "end", x: plot.right - 4, baseline: y + 16 },
        { anchor: "start", x: plot.left + 4, baseline: y - 7 },
        { anchor: "start", x: plot.left + 4, baseline: y + 16 },
      ] as const;
      const clear = (label: string, spot: (typeof spots)[number]) => {
        const w = textWidth(label, LABEL_SIZE);
        const x0 = spot.anchor === "end" ? spot.x - w : spot.x;
        const top = spot.baseline - LABEL_SIZE;
        const bottom = spot.baseline + 3;
        if (top < plot.top || bottom > plot.bottom - 2 || x0 < plot.left) return false;
        for (let x = x0 - 6; x <= x0 + w + 6; x += 3) {
          const curve = curveY(points, segments, x);
          if (curve > top - 7 && curve < bottom + 7) return false;
        }
        return true;
      };
      const tries = (compact ? labels : labels.slice(0, 1)).flatMap((label) => spots.map((spot) => ({ label, spot })));
      const chosen = tries.find((item) => clear(item.label, item.spot)) ?? {
        label: labels[compact ? 1 : 0],
        spot: spots[0],
      };
      average = {
        y: f(y),
        label: chosen.label,
        labelX: chosen.spot.x,
        labelY: f(chosen.spot.baseline),
        anchor: chosen.spot.anchor,
      };
    }
  }

  let peak: HeroGeometry["peak"] = null;
  const highest = Math.max(0, ...trend.months.map((item) => item.complaints));
  if (highest > 0) {
    // The latest month at the highest count: the most recent peak is the one to look at.
    const index = trend.months.map((item) => item.complaints).lastIndexOf(highest);
    const point = points[index];
    const full = peakText(point.month, highest, trend.earlierAverage, false);
    const text =
      !compact && textWidth(full, CALLOUT_SIZE) + 24 <= width - 8
        ? full
        : peakText(point.month, highest, trend.earlierAverage, true);
    const boxWidth = textWidth(text, CALLOUT_SIZE) + 22;
    const x = Math.max(2, Math.min(point.x - boxWidth / 2, width - 2 - boxWidth));
    peak = {
      index,
      text,
      box: { x: f(x), y: CALLOUT_TOP, width: boxWidth, height: CALLOUT_HEIGHT },
      leader: { x: f(point.x), y1: CALLOUT_TOP + CALLOUT_HEIGHT, y2: f(point.y - 8) },
    };
  }

  return { width, height, compact, plot, step, points, line, area, yTicks, xTicks, band, average, peak };
}
