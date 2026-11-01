// Pure rules for Complaints › Reportability and Complaints › Reporting windows: what the watch asks the server for,
// how clocks, states and missing answers read, how an earlier single decision reads, and what a change of the windows
// sends and when it may be sent (the per-market assessment is in marketAssessment.ts). The server (/api/v1/complaints/reportability, backend/app/reportability) keeps the clocks;
// a person decides; MDARIX never submits a report.
import type { Tone } from "../admin/console/dashboardModel";
import { collapsed } from "./complaintReview";
import { timeLeft, type DueLike } from "../../app/dates";
import type { MarketSummary } from "./marketAssessment";

export const REPORT_LIMITS = {
  reasonMin: 10,
  reasonMax: 4000,
  referenceMax: 120,
  windowsMax: 20,
  nameMin: 3,
  nameMax: 100,
  marketsMax: 100,
  marketMaxLength: 60,
  noteMax: 300,
  days: [1, 365] as const,
  lookback: [30, 3650] as const,
};

export type Trigger = "DEATH" | "SERIOUS_INJURY" | "MALFUNCTION";
export const TRIGGERS: readonly Trigger[] = ["DEATH", "SERIOUS_INJURY", "MALFUNCTION"];
export const TRIGGER_LABELS: Record<Trigger, string> = {
  DEATH: "Death",
  SERIOUS_INJURY: "Serious injury",
  MALFUNCTION: "Malfunction",
};
export type DayBasis = "CALENDAR" | "WORK";

export type ReportingWindow = {
  name: string;
  markets: string[];
  triggers: Trigger[];
  days: number;
  day_basis: DayBasis;
  note: string | null;
  /** The window's regulatory basis as catalog ids (features/shared/standards.ts), kept from its template. */
  basis: string[];
};

export type ReportabilitySettings = {
  windows: ReportingWindow[];
  lookback_days: number;
  configured: boolean;
  templates: ReportingWindow[];
  version: number;
  updated_by_name: string | null;
  updated_at: string | null;
};

export type Clock = {
  window: string;
  days: number;
  day_basis: DayBasis;
  due_date: string;
  /** The end of the deadline (UTC), its time zone, and "Mon 30 Nov 2026, 23:59 IST" (reportability/deadlines.py). */
  due_at?: string;
  due_zone?: string;
  due_label?: string;
  /** The market whose counting rule the clock follows (its country's), when known. */
  market?: string | null;
  state: "OVERDUE" | "DUE_SOON" | "RUNNING";
  days_left: number;
  triggers: Trigger[];
  /** The basis of the window the clock counts against (catalog ids). */
  basis?: string[];
};

export type WatchState = "OVERDUE" | "DUE_SOON" | "IN_REVIEW" | "RUNNING" | "NO_WINDOW" | "FOLLOW_UP" | "DECIDED";

/** A single decision recorded before per-market assessment (release 0.10.52): kept and shown as it was. */
export type ReportabilityDecision = {
  single_decision?: boolean;
  decision: "REPORTED" | "NOT_REPORTABLE";
  rationale: string;
  report_reference: string | null;
  reported_on: string | null;
  window: string | null;
  due_on: string | null;
  on_time: boolean | null;
  decided_by: string;
  decided_at: string | null;
};

export type WatchItem = {
  id: string;
  business_id: string | null;
  complaint_identifier: string | null;
  product_id: string | null;
  product_name: string | null;
  version: string | null;
  status: string | null;
  description: string | null;
  country: string | null;
  received_date: string | null;
  patient_involved: boolean | null;
  serious_injury: boolean | null;
  death: boolean | null;
  malfunction: boolean | null;
  aware_date: string | null;
  /** When the organization became aware (the day shown is the reader's, as on triage). */
  aware_at?: string | null;
  aware_source: "AWARENESS_DATE" | "RECEIVED_DATE" | "RECORDED_DATE" | "LINKED_SOURCE" | null;
  days_since_aware: number | null;
  triggers: Trigger[];
  clocks: Clock[];
  binding: Clock | null;
  follow_ups: Array<{ code: string; label: string }>;
  case: {
    case: { id: string; business_id: string | null };
    review: { business_id: string | null; status: string; outcome: string | null } | null;
  } | null;
  settled_by_case: boolean;
  in_review: boolean;
  state: WatchState;
  decision: ReportabilityDecision | null;
  /** Each market the complaint must be assessed for, with its state and clock. */
  markets: MarketSummary[];
};

export type WatchSummary = {
  configured: boolean;
  windows: number;
  lookback_days: number;
  open: number;
  overdue: number;
  due_soon: number;
  running: number;
  in_review: number;
  follow_up: number;
  no_window: number;
  decided: number;
  decided_in_window: number;
  decided_late: number;
  held_on_second_look: number;
};

export type WatchList = {
  summary: WatchSummary;
  show: WatchShow;
  total: number;
  page: number;
  page_size: number;
  pages: number;
  truncated: boolean;
  items: WatchItem[];
};

export const WATCH_SHOWS = [
  { value: "open", label: "Needs a decision" },
  { value: "overdue", label: "Overdue" },
  { value: "due_soon", label: "Due soon" },
  { value: "follow_up", label: "Missing answers" },
  { value: "decided", label: "Decided" },
] as const;
export type WatchShow = (typeof WATCH_SHOWS)[number]["value"] | "all";

export function watchPath(show: WatchShow, productId: string, page: number, pageSize = 25) {
  const params = new URLSearchParams({ show, page: String(page), page_size: String(pageSize) });
  if (productId) params.set("product_id", productId);
  return `/api/v1/complaints/reportability?${params}`;
}

const plural = (count: number, noun: string) => `${count.toLocaleString()} ${count === 1 ? noun : `${noun}s`}`;

export const WATCH_STATE: Record<WatchState, { label: string; tone: Tone }> = {
  OVERDUE: { label: "Overdue", tone: "critical" },
  DUE_SOON: { label: "Due soon", tone: "warning" },
  IN_REVIEW: { label: "In regulatory review", tone: "neutral" },
  RUNNING: { label: "Clock running", tone: "neutral" },
  NO_WINDOW: { label: "No window applies", tone: "serious" },
  FOLLOW_UP: { label: "Answers missing", tone: "warning" },
  DECIDED: { label: "Decided", tone: "good" },
};

export const watchStateOf = (state: string | null | undefined) =>
  WATCH_STATE[(state ?? "") as WatchState] ?? { label: "—", tone: "neutral" as Tone };

/** "2 days left", "5 h left", "10 days overdue": the app's one helper (app/dates.ts timeLeft), counted to the end of
 * the deadline in its market's time zone, overdue from the clock's state. */
export function clockText(clock: DueLike | null | undefined, now = new Date()): string {
  if (!clock) return "No reporting window applies";
  return timeLeft(clock, now);
}

/** "30 calendar days", "5 work days". */
export const windowLength = (window: Pick<ReportingWindow, "days" | "day_basis">) =>
  `${plural(window.days, window.day_basis === "WORK" ? "work day" : "calendar day")}`;

export const AWARE_SOURCE: Record<string, string> = {
  AWARENESS_DATE: "awareness date",
  RECEIVED_DATE: "received date (no awareness date recorded)",
  RECORDED_DATE: "recorded date (no awareness or received date)",
  LINKED_SOURCE: "earlier linked source (a logged call or intake about the same event)",
};

export function watchHeadline(summary: WatchSummary | null | undefined): { title: string; detail: string; tone: Tone } {
  if (!summary)
    return { title: "Reading your complaints…", detail: "Death, serious injury and malfunction.", tone: "neutral" };
  const setUp = summary.configured
    ? `against your ${plural(summary.windows, "reporting window")}`
    : "without due dates until your reporting windows are entered";
  if (summary.overdue)
    return {
      title: `${plural(summary.overdue, "reporting clock")} overdue`,
      detail: `Record the decision for each: was it reported, and if not, why not. ${plural(summary.open, "complaint")} need a decision, ${setUp}.`,
      tone: "critical",
    };
  if (summary.due_soon)
    return {
      title: `${plural(summary.due_soon, "reporting clock")} due soon`,
      detail: `${plural(summary.open, "complaint")} need a reportability decision, ${setUp}.`,
      tone: "warning",
    };
  if (summary.open)
    return {
      title: `${plural(summary.open, "complaint")} need a reportability decision`,
      detail: `None is due within days, ${setUp}.`,
      tone: summary.follow_up || summary.no_window ? "warning" : "good",
    };
  return {
    title: "Every reportable event has a decision",
    detail: "Complaints reporting a death, a serious injury or a malfunction appear here with their clock.",
    tone: "good",
  };
}

// An earlier single decision ------------------------------------------------------------------------------------

/** "Reported (MDR-…) on 3 Oct 2026" or "Not reportable", with whether it came inside the window. */
export function timelinessOf(decision: ReportabilityDecision | null): { label: string; tone: Tone } | null {
  if (!decision || decision.on_time === null) return null;
  return decision.on_time
    ? { label: "Inside the window", tone: "good" }
    : { label: "After the window", tone: "critical" };
}

// The windows ----------------------------------------------------------------------------------------------------

export type WindowForm = {
  key: number;
  name: string;
  markets: string;
  triggers: Trigger[];
  days: string;
  dayBasis: DayBasis;
  note: string;
  /** Kept from the template the window started from; not edited on the form. */
  basis: string[];
};

let nextKey = 1;
export function windowForm(window: ReportingWindow): WindowForm {
  nextKey += 1;
  return {
    key: nextKey,
    name: window.name,
    markets: window.markets.join(", "),
    triggers: [...window.triggers],
    days: String(window.days),
    dayBasis: window.day_basis,
    note: window.note ?? "",
    basis: [...(window.basis ?? [])],
  };
}

export const BLANK_WINDOW: ReportingWindow = {
  name: "",
  markets: [],
  triggers: ["DEATH", "SERIOUS_INJURY"],
  days: 30,
  day_basis: "CALENDAR",
  note: null,
  basis: [],
};

/** The markets typed in (comma or line separated), tidied, without repeats (any case or dots). */
export function marketsOf(text: string): string[] {
  const seen = new Set<string>();
  const found: string[] = [];
  for (const part of text.split(/[\n,;]/)) {
    const market = collapsed(part);
    const key = market.toLowerCase().replace(/\./g, "");
    if (market && !seen.has(key)) {
      seen.add(key);
      found.push(market);
    }
  }
  return found;
}

export function windowOf(form: WindowForm): ReportingWindow {
  return {
    name: collapsed(form.name),
    markets: marketsOf(form.markets),
    triggers: TRIGGERS.filter((trigger) => form.triggers.includes(trigger)),
    days: Number(form.days),
    day_basis: form.dayBasis,
    note: collapsed(form.note) || null,
    basis: form.basis,
  };
}

export function windowsProblem(forms: WindowForm[], lookback: string, reason: string): string | null {
  if (forms.length > REPORT_LIMITS.windowsMax) return `Keep at most ${REPORT_LIMITS.windowsMax} windows`;
  const names = new Set<string>();
  for (const [index, form] of forms.entries()) {
    const label = `Window ${index + 1}`;
    const window = windowOf(form);
    if (window.name.length < REPORT_LIMITS.nameMin || window.name.length > REPORT_LIMITS.nameMax)
      return `${label}: give it a name of ${REPORT_LIMITS.nameMin} to ${REPORT_LIMITS.nameMax} characters`;
    if (names.has(window.name.toLowerCase())) return `${label}: another window is already called "${window.name}"`;
    names.add(window.name.toLowerCase());
    if (window.markets.length > REPORT_LIMITS.marketsMax)
      return `${label}: keep at most ${REPORT_LIMITS.marketsMax} markets`;
    const long = window.markets.find((market) => market.length > REPORT_LIMITS.marketMaxLength);
    if (long) return `${label}: "${long.slice(0, 20)}…" is longer than ${REPORT_LIMITS.marketMaxLength} characters`;
    if (!window.triggers.length) return `${label}: choose what starts its clock`;
    const [low, high] = REPORT_LIMITS.days;
    if (!/^\d+$/.test(form.days.trim()) || window.days < low || window.days > high)
      return `${label}: the window is a whole number of days from ${low} to ${high}`;
    if (window.note && window.note.length > REPORT_LIMITS.noteMax)
      return `${label}: keep the note under ${REPORT_LIMITS.noteMax} characters`;
  }
  const [low, high] = REPORT_LIMITS.lookback;
  const days = Number(lookback);
  if (!/^\d+$/.test(lookback.trim()) || days < low || days > high)
    return `Look back a whole number of days from ${low} to ${high}`;
  if (collapsed(reason).length < REPORT_LIMITS.reasonMin)
    return `Say in at least ${REPORT_LIMITS.reasonMin} characters why (for example the procedure and its revision)`;
  return null;
}

export function windowsChanged(settings: ReportabilitySettings, forms: WindowForm[], lookback: string): boolean {
  if (Number(lookback) !== settings.lookback_days) return true;
  return JSON.stringify(forms.map(windowOf)) !== JSON.stringify(settings.windows);
}

export function windowsBody(forms: WindowForm[], lookback: string, reason: string) {
  return { windows: forms.map(windowOf), lookback_days: Number(lookback), reason: collapsed(reason) };
}
