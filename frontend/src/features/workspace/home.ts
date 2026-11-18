// Home per persona (0.10.73, Release C part C1): the 60-second test. Pure rules: which of the organization's dated
// items a persona's Home counts and lists (the server's /api/v1/oversight, every item with its owner and deadline),
// the three numbers, the next actions most urgent first, and the legal clocks. No DOM, so the tests check them.
import type { OversightItem } from "./oversight";
import { IMPORTED_SOURCE, SAMPLE_SOURCE } from "./complaintList";

/** The oversight categories each persona's Home is about; null: every category. */
export const PERSONA_CATEGORIES: Readonly<Record<string, readonly string[] | null>> = {
  admin: null,
  quality: null,
  executive: null,
  regulatory: ["REPORTING", "OBLIGATION"],
  handler: ["TRIAGE", "COMMUNICATION"],
  investigator: ["TASK", "CAPA"],
  risk: ["TASK"],
  decision: ["OBLIGATION", "GUIDE", "TASK", "CAPA"],
};

/** The line under each persona's greeting (the approved design's). */
export const PERSONA_GREETING: Readonly<Record<string, string>> = {
  admin: "Everything in your workspace, in one place.",
  quality: "What Quality must decide this week.",
  regulatory: "Which reports are due, in which market, and by when.",
  servicedesk: "Calls to log and check, handed on to the complaint handler.",
  handler: "Calls to check and complaints to triage.",
  investigator: "Your investigations and what blocks each decision.",
  risk: "Risk reviews requested from you.",
  decision: "Decisions and approvals waiting for your signature.",
  executive: "What needs attention today, in one minute.",
};

const WEEK_MS = 7 * 24 * 3_600_000;

/** "Due this week", one definition everywhere (0.10.81, navigation M1): the complaints of the Complaints list view
 * of that name (a deadline or target in the next seven days, not yet past), read from the server's own list. */
export const DUE_WEEK_PATH = "/api/v1/complaints?view=due-week&page=1&page_size=1";
export const DUE_WEEK_VIEW = "Due this week";
/** "Overdue" (0.10.82, D1.6): the complaints of the list view of that name, a deadline or target already past. */
export const OVERDUE_PATH = "/api/v1/complaints?view=overdue&page=1&page_size=1";
export const OVERDUE_VIEW = "Overdue";

/** The items a persona's Home is about. */
export function personaItems(items: readonly OversightItem[], persona: string): OversightItem[] {
  const categories = PERSONA_CATEGORIES[persona] ?? null;
  return categories ? items.filter((item) => categories.includes(item.category)) : [...items];
}

const dueMs = (item: Pick<OversightItem, "due_at">) => {
  const value = Date.parse(item.due_at);
  return Number.isFinite(value) ? value : Number.POSITIVE_INFINITY;
};

/** Overdue (the server's state) and due this week (not overdue, due within seven days of now). */
export function homeCounts(items: readonly OversightItem[], now = new Date()): { overdue: number; week: number } {
  const overdue = items.filter((item) => item.state === "OVERDUE").length;
  const week = items.filter((item) => item.state !== "OVERDUE" && dueMs(item) - now.getTime() <= WEEK_MS).length;
  return { overdue, week };
}

/** The next actions, most urgent first: overdue, then by deadline. ``lead``: a complaint whose items win a tie and are
 * always listed (the most urgent complaint Home's hero names, 0.10.84, M5). */
export function nextActions(items: readonly OversightItem[], limit = 5, lead: string | null = null): OversightItem[] {
  const first = (item: OversightItem) => Number(!!lead && item.complaint_id === lead);
  const sorted = [...items].sort(
    (a, b) =>
      Number(b.state === "OVERDUE") - Number(a.state === "OVERDUE") || dueMs(a) - dueMs(b) || first(b) - first(a),
  );
  const shown = sorted.slice(0, limit);
  const led = sorted.find((item) => first(item));
  if (!led || shown.includes(led)) return shown;
  return [...shown.slice(0, limit - 1), led];
}

/** shortcut: the sample's records are known by their SAMPLE- references, as the server's sweep knows them; a source per
 * item if that ever changes. */
export const isSampleRef = (ref: string | null | undefined) => (ref ?? "").startsWith("SAMPLE-");

/** Whether a record belongs to the data the Sample · Your data switch shows (0.10.84, M5): on your data none of the
 * sample's; on the sample none of your imported complaints'; everything with no choice made (a pilot). */
export function inData(ref: string | null | undefined, source: string | undefined, complaint = true): boolean {
  if (source === IMPORTED_SOURCE) return !isSampleRef(ref);
  if (source === SAMPLE_SOURCE) return isSampleRef(ref) || !complaint;
  return true;
}

/** A tile's list read for the data shown: the complaint list's own source filter. */
export const withSource = (path: string, source: string | undefined) =>
  source ? `${path}&${new URLSearchParams({ source_system: source })}` : path;

/** A real legal deadline: a market's reporting clock or report obligation, never a workflow task filed under that
 * category (an approval task's due date is the organization's own target, 0.10.84, H1). */
export const isLegalDeadline = (item: Pick<OversightItem, "key" | "category">) =>
  (item.category === "REPORTING" || item.category === "OBLIGATION") && !item.key.startsWith("task:");

/** The legal clocks: reporting deadlines and report obligations of a market, soonest first. */
export function legalClocks(items: readonly OversightItem[], limit = 4): OversightItem[] {
  return nextActions(
    items.filter((item) => !!item.market && isLegalDeadline(item)),
    limit,
  );
}

/** How much of a 30-day window a clock has used: full once overdue, at least a sliver so the lane shows. */
export function laneShare(item: Pick<OversightItem, "state" | "hours_left">): number {
  if (item.state === "OVERDUE") return 100;
  const used = 100 - (Math.max(0, item.hours_left) / (30 * 24)) * 100;
  return Math.round(Math.min(100, Math.max(4, used)));
}

/** "Good morning", "Good afternoon" or "Good evening", by the hour where the person is. */
export function greeting(now = new Date()): string {
  const hour = now.getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

/** "3 items" or "1 item". */
export const itemsText = (count: number) => `${count} ${count === 1 ? "item" : "items"}`;
