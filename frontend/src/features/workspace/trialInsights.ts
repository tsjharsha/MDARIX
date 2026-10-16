// Pure rules for Getting started › Automatic insights: the panel's data (GET /api/v1/trial/insights), the filters a
// click on a bar sets, and the headline numbers, monthly trend and breakdowns recomputed for the filtered complaints.
// The server (backend/app/trial/insight_questions.py) computes the unfiltered numbers and answers the questions; these
// rules count the same way (the same months, the last 3 against the ones before) so a filter never changes the method.

export type InsightRecord = {
  /** The complaint's MDARIX ID, and its number in the source system. */
  id: string;
  ref: string | null;
  /** The version's MDARIX ID; its readable name is in `version_labels`. */
  version: string | null;
  lot: string | null;
  code: string | null;
  country: string | null;
  /** YYYY-MM. */
  month: string | null;
  harm: boolean;
  malfunction: boolean;
  status: string | null;
};

export type InsightTable = { columns: string[]; rows: (string | number)[][] };

export type InsightAnswer = {
  summary: string;
  table: InsightTable | null;
  bars: { label: string; count: number }[] | null;
  facts: string[];
  ids: string[];
  ids_total: number;
  cases: { id: string; business_id: string; product_id: string }[];
  basis: string;
  missing: string[];
};

export type InsightQuestion = { key: string; question: string; answer: InsightAnswer };

export type Insights = {
  scope: string;
  total_complaints: number;
  by_product: { product_id: string; name: string; complaints: number }[];
  by_version: { product_id: string | null; version: string; complaints: number }[];
  by_lot: { lot_id: string; complaints: number }[];
  by_month?: { month: string; complaints: number }[];
  findings: string[];
  suggested_questions: string[];
  note: string;
  // Added in 0.10.12; an older server leaves them out and the panel shows its findings only.
  records?: InsightRecord[];
  version_labels?: Record<string, string>;
  questions?: InsightQuestion[];
};

export const RECENT_MONTHS = 3;

export const FACETS = ["version", "lot", "code", "country"] as const;
export type Facet = (typeof FACETS)[number];
export const FACET_TABS: Record<Facet, string> = {
  version: "By version",
  lot: "By lot",
  code: "By problem code",
  country: "By country",
};
/** What a facet is called on a filter chip and in sentences ("no problem code", "records a problem code"). */
export const FACET_NAMES: Record<Facet, string> = {
  version: "Version",
  lot: "Lot",
  code: "Problem code",
  country: "Country",
};

/** At most one value per facet: filters on different tabs combine, a second bar on the same tab replaces the first. */
export type InsightFilters = Partial<Record<Facet, string>>;

/** A click on a bar: the value becomes the facet's filter, or, clicked again, is cleared. */
export function toggleFilter(filters: InsightFilters, facet: Facet, value: string): InsightFilters {
  const next = { ...filters };
  if (next[facet] === value) delete next[facet];
  else next[facet] = value;
  return next;
}

export function clearFilter(filters: InsightFilters, facet: Facet): InsightFilters {
  const next = { ...filters };
  delete next[facet];
  return next;
}

export const activeFilters = (filters: InsightFilters) =>
  FACETS.filter((facet) => filters[facet] !== undefined).map((facet) => ({ facet, value: filters[facet] as string }));

export function applyFilters(records: InsightRecord[], filters: InsightFilters): InsightRecord[] {
  const active = activeFilters(filters);
  return active.length
    ? records.filter((record) => active.every(({ facet, value }) => record[facet] === value))
    : records;
}

/** What a filter value reads as: a version by its product name and version, the rest as recorded. */
export const valueLabel = (facet: Facet, value: string, labels: Record<string, string> = {}) =>
  facet === "version" ? (labels[value] ?? value) : value;

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-08" as "Aug 2026" (fixed names, so it reads the same in every browser). */
export const monthLabel = (month: string) =>
  `${MONTH_NAMES[Number(month.slice(5, 7)) - 1] ?? "?"} ${month.slice(0, 4)}`;

/** Every month from the first to the last given, so a month without complaints counts as a zero. */
export function monthSeries(months: (string | null)[]): string[] {
  const known = months.filter((month): month is string => !!month).sort();
  if (!known.length) return [];
  const last = known[known.length - 1];
  let year = Number(known[0].slice(0, 4));
  let month = Number(known[0].slice(5, 7));
  const series: string[] = [];
  for (let key = known[0]; key <= last;) {
    series.push(key);
    [year, month] = month === 12 ? [year + 1, 1] : [year, month + 1];
    key = `${year}-${String(month).padStart(2, "0")}`;
  }
  return series;
}

export type Trend = {
  months: { month: string; complaints: number; recent: boolean }[];
  /** Null with fewer than four months: nothing before the recent months to compare them with. */
  recentAverage: number | null;
  earlierAverage: number | null;
};

/** Complaints per month over `series` (all the panel's months, so a filter keeps the same windows). */
export function trendOf(records: InsightRecord[], series: string[]): Trend {
  const counts = new Map<string, number>();
  for (const record of records) if (record.month) counts.set(record.month, (counts.get(record.month) ?? 0) + 1);
  const compared = series.length > RECENT_MONTHS;
  const months = series.map((month, index) => ({
    month,
    complaints: counts.get(month) ?? 0,
    recent: compared && index >= series.length - RECENT_MONTHS,
  }));
  if (!compared) return { months, recentAverage: null, earlierAverage: null };
  const sum = (items: typeof months) => items.reduce((total, item) => total + item.complaints, 0);
  const recent = months.filter((item) => item.recent);
  const earlier = months.filter((item) => !item.recent);
  return { months, recentAverage: sum(recent) / recent.length, earlierAverage: sum(earlier) / earlier.length };
}

export type Headline = {
  total: number;
  harm: number;
  malfunction: number;
  topVersion: { label: string; share: number; complaints: number } | null;
  rate: { recent: number; earlier: number; direction: "up" | "down" | "flat" } | null;
};

export function headlineOf(records: InsightRecord[], series: string[], labels: Record<string, string> = {}): Headline {
  const total = records.length;
  const [top] = breakdown(records, "version", labels).items;
  const trend = trendOf(records, series);
  const rate =
    trend.recentAverage === null || trend.earlierAverage === null
      ? null
      : {
          recent: trend.recentAverage,
          earlier: trend.earlierAverage,
          direction: (trend.recentAverage > trend.earlierAverage
            ? "up"
            : trend.recentAverage < trend.earlierAverage
              ? "down"
              : "flat") as "up" | "down" | "flat",
        };
  return {
    total,
    harm: records.filter((record) => record.harm).length,
    malfunction: records.filter((record) => record.malfunction).length,
    topVersion:
      top && total ? { label: top.label, share: Math.round((100 * top.count) / total), complaints: top.count } : null,
    rate,
  };
}

export type Breakdown = { items: { key: string; label: string; count: number }[]; unrecorded: number };

/** Complaints per value of a facet, most first; complaints that leave it empty are counted apart. */
export function breakdown(records: InsightRecord[], facet: Facet, labels: Record<string, string> = {}): Breakdown {
  const counts = new Map<string, number>();
  let unrecorded = 0;
  for (const record of records) {
    const value = record[facet];
    if (value === null || value === "") unrecorded += 1;
    else counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  const items = [...counts.entries()]
    .map(([key, count]) => ({ key, label: valueLabel(facet, key, labels), count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  return { items, unrecorded };
}

/** "28 complaints have no problem code." for the complaints a tab cannot place. */
export const unrecordedText = (facet: Facet, count: number) =>
  `${count.toLocaleString()} ${count === 1 ? "complaint has" : "complaints have"} no ${FACET_NAMES[facet].toLowerCase()}.`;

export const rateText = (value: number) => (Math.round(value * 10) / 10).toFixed(1);

/** The trend in words, for screen readers and as the chart's text alternative. */
export function trendSummary(trend: Trend): string {
  if (!trend.months.length) return "No complaints by month.";
  const first = monthLabel(trend.months[0].month);
  const last = monthLabel(trend.months[trend.months.length - 1].month);
  const total = trend.months.reduce((sum, item) => sum + item.complaints, 0);
  const span = `${total.toLocaleString()} ${total === 1 ? "complaint" : "complaints"} from ${first} to ${last}`;
  if (trend.recentAverage === null || trend.earlierAverage === null) return `${span}.`;
  return `${span}: the last ${RECENT_MONTHS} months average ${rateText(trend.recentAverage)} per month, against ${rateText(
    trend.earlierAverage,
  )} per month before.`;
}

/** The filters in words: "Rev B and lot L-003". */
export function filterText(filters: InsightFilters, labels: Record<string, string> = {}): string {
  return activeFilters(filters)
    .map(({ facet, value }) => (facet === "lot" ? `lot ${value}` : valueLabel(facet, value, labels)))
    .join(" and ");
}
