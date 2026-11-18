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
  pqe: ["TASK", "CAPA"],
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
  pqe: "Your products: what changed, in which versions and lots, and what the complaints say.",
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

/** One count on a persona's Today: what it counts (its definition), where it is read and the records it opens. */
export type TodayTile = {
  key: string;
  title: string;
  /** The definition, under the number. */
  detail: string;
  /** The tile's one line on a phone. */
  short: string;
  tone: "over" | "soon" | "risk";
  path: string;
  /** Follows the Sample · Your data switch (the complaint list's own views do). */
  sourced?: boolean;
  count: (data: any) => number | null;
  opens: { section: string; tab?: string };
};

const listTotal = (data: { total?: number } | null) => (typeof data?.total === "number" ? data.total : null);
const complaintView = (code: string) => `/api/v1/complaints?view=${code}&page=1&page_size=1`;
/** One view of the Cases list, a page of one row: its ``total`` is the view's count (backend/app/intake/cases_list.py). */
const caseView = (view: string) => `/api/v1/intake/cases?view=${view}&q=&page=1&size=1`;

/**
 * The counts on each persona's Today where they differ from Overdue · Due this week · At risk (UX3, Persona Blueprint
 * wave C sketches): each the total of the list it opens, read from that list, with its definition. Personas not listed
 * keep the three shared ones.
 */
export const PERSONA_TILES: Readonly<Record<string, readonly TodayTile[]>> = {
  servicedesk: [
    {
      key: "missing",
      title: "Calls missing facts",
      detail: "Cases whose check needs more information from the caller",
      short: "Ask the caller",
      tone: "over",
      path: caseView("needs_information"),
      count: listTotal,
      opens: { section: "Complaints", tab: "Calls to check" },
    },
    {
      key: "duplicates",
      title: "Possible duplicates",
      detail: "Calls that may be the same event as another, to link or keep apart",
      short: "Link or keep apart",
      tone: "soon",
      path: "/api/v1/intake/duplicates",
      count: (data: { items?: unknown[] } | null) => (Array.isArray(data?.items) ? data.items.length : null),
      opens: { section: "Complaints", tab: "Calls to check" },
    },
    {
      key: "handed",
      title: "Handed over",
      detail: "Cases that became complaints in the last 30 days, now with the complaint handler",
      short: "Last 30 days",
      tone: "risk",
      path: caseView("became_complaints"),
      count: listTotal,
      opens: { section: "Complaints", tab: "Calls to check" },
    },
  ],
  handler: [
    {
      key: "triage",
      title: "To triage",
      detail: "Complaints whose triage is not done yet, most urgent first",
      short: "Most urgent first",
      tone: "over",
      path: "/api/v1/triage?show=open&limit=1",
      count: (data: { summary?: { open?: number } } | null) => data?.summary?.open ?? null,
      opens: { section: "Complaints", tab: "To triage" },
    },
    {
      key: "waiting",
      title: "Waiting for contact",
      detail: "Complaints with a question still open with the reporter or a partner",
      short: "Reporter or partner",
      tone: "soon",
      path: complaintView("waiting-reporter"),
      sourced: true,
      count: listTotal,
      opens: { section: "Complaints", tab: "Waiting for the reporter" },
    },
    {
      key: "reportability",
      title: "Reportability due",
      detail: "Complaints with a market that has no signed reportability conclusion yet",
      short: "No conclusion yet",
      tone: "risk",
      path: complaintView("reportability"),
      sourced: true,
      count: listTotal,
      opens: { section: "Complaints", tab: "Reportability: decision needed" },
    },
  ],
  regulatory: [
    {
      key: "legal",
      title: "Legal clocks this week",
      detail: "Complaints with a reporting deadline in the next seven days, or already past",
      short: "Next 7 days",
      tone: "over",
      path: complaintView("legal-week"),
      sourced: true,
      count: listTotal,
      opens: { section: "Complaints", tab: "Legal clocks this week" },
    },
    {
      key: "reportability",
      title: "Reportability due",
      detail: "Complaints with a market that has no signed reportability conclusion yet",
      short: "No conclusion yet",
      tone: "soon",
      path: complaintView("reportability"),
      sourced: true,
      count: listTotal,
      opens: { section: "Complaints", tab: "Reportability: decision needed" },
    },
    {
      key: "approval",
      title: "Reports awaiting approval",
      detail: "Authority reports sent for approval that you did not prepare",
      short: "Yours to approve",
      tone: "risk",
      path: complaintView("my-approval"),
      sourced: true,
      count: listTotal,
      opens: { section: "Complaints", tab: "Waiting for my approval" },
    },
  ],
  decision: [
    {
      key: "sign",
      title: "Waiting for your signature",
      detail: "Investigation briefs accepted for decision, waiting for a signature",
      short: "Accepted for decision",
      tone: "over",
      path: "/api/v1/decisions/queue?page=1&page_size=1",
      count: listTotal,
      opens: { section: "Approvals" },
    },
    {
      key: "approval",
      title: "Reports awaiting approval",
      detail: "Authority reports sent for approval that you did not prepare",
      short: "Yours to approve",
      tone: "soon",
      path: complaintView("my-approval"),
      sourced: true,
      count: listTotal,
      opens: { section: "Complaints", tab: "Waiting for my approval" },
    },
    {
      key: "overdue",
      title: "Overdue",
      detail: "Complaints past a deadline or target",
      short: "Act on these first",
      tone: "risk",
      path: OVERDUE_PATH,
      sourced: true,
      count: listTotal,
      opens: { section: "Complaints", tab: OVERDUE_VIEW },
    },
  ],
  risk: [
    {
      key: "requested",
      title: "Risk reviews requested",
      detail: "Risk reviews requested from the risk reviewers and not yet taken",
      short: "Start one",
      tone: "over",
      path: "/api/v1/case-reviews?type=RISK&box=queue&page=1&page_size=1",
      count: (data: { total?: number; items?: unknown[] } | null) =>
        typeof data?.total === "number" ? data.total : Array.isArray(data?.items) ? data.items.length : null,
      opens: { section: "Investigations" },
    },
    {
      key: "mine",
      title: "Your risk reviews in progress",
      detail: "Risk reviews you started and have not recorded yet",
      short: "Finish them",
      tone: "soon",
      path: "/api/v1/case-reviews?type=RISK&box=mine&status=IN_PROGRESS&page=1&page_size=1",
      count: (data: { total?: number; items?: unknown[] } | null) =>
        typeof data?.total === "number" ? data.total : Array.isArray(data?.items) ? data.items.length : null,
      opens: { section: "Investigations" },
    },
    {
      key: "rising",
      title: "Versions rising",
      detail: "Product versions whose complaints rise against their history: new evidence on existing risks",
      short: "Check the risk file",
      tone: "risk",
      path: "/api/v1/triage/trends?group=version",
      count: (data: { items?: Array<{ result?: string }> } | null) =>
        Array.isArray(data?.items)
          ? data.items.filter((row) => row.result === "SIGNIFICANT" || row.result === "ELEVATED").length
          : null,
      opens: { section: "Trends", tab: "Trend check" },
    },
  ],
};

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
