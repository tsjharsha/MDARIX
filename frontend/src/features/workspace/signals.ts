// Pure rules for signal triage (Signals › Signal inbox, a signal's detail, Detection rules, the dashboard's "Signal
// triage"): which filters a list reads, how statuses, priorities and due dates read, what each triage action sends and
// when it may be sent, and how a link names a signal. The server (/api/v1/triage) owns every signal and decides every
// action; these only shape what the person sees and what is sent.
import { titleCase, type Tone } from "../admin/console/dashboardModel";
import { isUuid, safeText } from "../../app/displayId";
import { nextSort, type SortState } from "../../app/tableSort";
import type { WorkspaceSection } from "./workspaceContext";

export const SIGNAL_STATUSES = [
  "NEW",
  "TRIAGE",
  "MONITOR",
  "NO_ACTION",
  "DUPLICATE",
  "MERGED",
  "INVESTIGATION_REQUIRED",
  "ESCALATED",
  "INVESTIGATION_OPEN",
  "DECISION_RECORDED",
  "CLOSED",
] as const;
export type SignalStatus = (typeof SIGNAL_STATUSES)[number];

/** Statuses in which a signal is still being worked (the server's OPEN_SIGNAL_STATUSES). */
export const OPEN_SIGNAL_STATUSES: readonly SignalStatus[] = [
  "NEW",
  "TRIAGE",
  "MONITOR",
  "INVESTIGATION_REQUIRED",
  "ESCALATED",
  "INVESTIGATION_OPEN",
];

export const SIGNAL_PRIORITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
export type SignalPriority = (typeof SIGNAL_PRIORITIES)[number];

export const SIGNAL_ORIGINS = ["MANUAL", "THRESHOLD_RULE", "AI_SUGGESTED", "IMPORT"] as const;
export type SignalOrigin = (typeof SIGNAL_ORIGINS)[number];

export const DISPOSITIONS = ["INVESTIGATION_REQUIRED", "ESCALATED", "MONITOR", "NO_ACTION", "DUPLICATE"] as const;
export type Disposition = (typeof DISPOSITIONS)[number];

export type SignalRef = { id: string; business_id?: string | null };

export type SignalSummary = {
  id: string;
  business_id?: string | null;
  title?: string | null;
  origin?: SignalOrigin | string | null;
  origin_label?: string | null;
  rule_code?: string | null;
  product?: { id: string; business_id?: string | null; name?: string | null } | null;
  product_version?: { id: string; business_id?: string | null; version_identifier?: string | null } | null;
  problem_key?: string | null;
  complaint_count?: number | null;
  recent_complaints_7d?: number | null;
  first_event_at?: string | null;
  last_event_at?: string | null;
  highest_severity?: string | null;
  serious_harm?: boolean | null;
  suggested_priority?: SignalPriority | string | null;
  confirmed_priority?: SignalPriority | string | null;
  priority?: SignalPriority | string | null;
  status?: SignalStatus | string | null;
  status_label?: string | null;
  owner?: { id: string; name?: string | null } | null;
  due_at?: string | null;
  overdue?: boolean | null;
  age_days?: number | null;
  canonical?: SignalRef | null;
  investigations?: Array<SignalRef & { status?: string | null }> | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type SignalComplaint = {
  id: string;
  business_id?: string | null;
  complaint_identifier?: string | null;
  description?: string | null;
  severity?: string | null;
  serious_injury?: boolean | null;
  death?: boolean | null;
  malfunction?: boolean | null;
  country?: string | null;
  status?: string | null;
  event_timestamp?: string | null;
  product_version?: { business_id?: string | null; version_identifier?: string | null } | null;
  added_how?: string | null;
};

export type SignalEvent = {
  event_type: string;
  actor_name?: string | null;
  actor_role?: string | null;
  from_status?: string | null;
  to_status?: string | null;
  reason?: string | null;
  details?: Record<string, unknown> | null;
  created_at?: string | null;
};

export type SignalActions = {
  can_start?: boolean;
  can_set_priority?: boolean;
  can_disposition?: boolean;
  can_merge?: boolean;
  can_add_complaints?: boolean;
  can_create_investigation?: boolean;
  /** One click from the signal to its case (POST .../open-case), before or after triage. */
  can_open_case?: boolean;
};

export type VersionSplitRow = {
  product_version_business_id?: string | null;
  version_identifier?: string | null;
  count: number;
};

export type SignalDetail = SignalSummary & {
  description?: string | null;
  rule?: { code?: string | null; version?: number | string | null; parameters?: Record<string, unknown> | null } | null;
  priority_reason?: string | null;
  disposition?: {
    reason?: string | null;
    by_name?: string | null;
    at?: string | null;
    monitor_review_date?: string | null;
    monitor_trigger?: string | null;
  } | null;
  complaints?: SignalComplaint[] | null;
  version_split?: VersionSplitRow[] | null;
  related?: {
    changes?: Array<Record<string, unknown>> | null;
    open_capas?: Array<Record<string, unknown>> | null;
    open_investigations?: Array<Record<string, unknown>> | null;
  } | null;
  merged_from?: Array<SignalRef & { status?: string | null }> | null;
  events?: SignalEvent[] | null;
  actions?: SignalActions | null;
};

export type SignalList = {
  items: SignalSummary[];
  total: number;
  page: number;
  page_size: number;
  counts_by_status?: Partial<Record<string, number>> | null;
};

export type TriageSummary = {
  counts?: Partial<
    Record<
      | "new"
      | "triage"
      | "escalated"
      | "investigation_required"
      | "monitor"
      | "monitor_review_due"
      | "unowned"
      | "overdue",
      number
    >
  > | null;
  by_priority?: Partial<Record<SignalPriority, number>> | null;
};

export type DetectionRule = {
  rule_code: string;
  label?: string | null;
  description?: string | null;
  enabled: boolean;
  min_complaints: number;
  window_days: number;
  version?: number | null;
  updated_by_name?: string | null;
  updated_at?: string | null;
  last_run_at?: string | null;
  defaults?: { min_complaints?: number | null; window_days?: number | null } | null;
};

export type RuleRunResult = {
  created?: Array<SignalRef | string> | number | null;
  updated?: Array<SignalRef | string> | number | null;
  monitor_reopened?: Array<SignalRef | string> | number | null;
};

// Critical first when sorted descending (the same order as a task's priority in tasks.ts).
const PRIORITY_RANK: Record<string, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };
const priorityRank = (priority: unknown) => PRIORITY_RANK[String(priority ?? "").toUpperCase()] ?? 0;

const code = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[ -]/g, "_");

// ---------------------------------------------------------------------------------------------------------------
// Tabs and links

/** Signals' tabs in order. Detection rules is shown only to people who triage signals. */
export const SIGNALS_TABS = [
  "Signal inbox",
  "Product complaints",
  "Complaint list",
  "Recent complaints",
  "Trends",
  // Each product version against its own history (signalAi.ts): a check beside the count rule.
  "Trend check",
  "Detection rules",
] as const;
export type SignalsTab = (typeof SIGNALS_TABS)[number];

// Former tab names still open the tab that replaced them (links, bookmarks).
const LEGACY_SIGNALS_TABS: Record<string, SignalsTab> = { "All signals": "Recent complaints" };

/** The status filter of the inbox: the open group (default), every status, or one status. */
export type StatusFilter = "OPEN" | "ALL" | SignalStatus;
export type SignalSort = "priority" | "due_at" | "created_at" | "complaint_count" | "last_event_at";
export const SIGNAL_SORTS: ReadonlyArray<{ value: SignalSort; label: string }> = [
  { value: "priority", label: "Priority" },
  { value: "due_at", label: "Due date" },
  { value: "last_event_at", label: "Latest complaint" },
  { value: "complaint_count", label: "Complaints" },
  { value: "created_at", label: "Created" },
];
/** The inbox columns whose heading sorts every page (the server's sort keys; GET /api/v1/triage/signals). */
export const SIGNAL_COLUMN_SORTS = [
  "business_id",
  "title",
  "product",
  "problem_key",
  "complaint_count",
  "highest_severity",
  "priority",
  "status",
  "owner",
  "due_at",
  "age_days",
] as const;
export type SignalSortKey = SignalSort | (typeof SIGNAL_COLUMN_SORTS)[number];

export type SignalFilters = {
  status: StatusFilter;
  priorities: SignalPriority[];
  productId: string;
  origin: string;
  owner: "" | "me" | "unassigned";
  q: string;
  /** "Sort by" (each in its natural direction), or the column a heading sorts by when `order` is set. */
  sort: SignalSortKey;
  /** Set by a column heading: that column ascending or descending. Empty: the "Sort by" choice. */
  order: "" | "asc" | "desc";
  /** Only signals past their due date (from the dashboard's Overdue count). */
  overdue: boolean;
  /** Only monitored signals whose review date has come (from the dashboard's "Monitor review due"). */
  reviewDue: boolean;
};

export const DEFAULT_SIGNAL_FILTERS: SignalFilters = {
  status: "OPEN",
  priorities: [],
  productId: "",
  origin: "",
  owner: "",
  q: "",
  sort: "priority",
  order: "",
  overdue: false,
  reviewDue: false,
};

// The column a "Sort by" choice orders and its direction (Created: newest first, the youngest age first).
const NATURAL_SORT: Partial<Record<SignalSort, NonNullable<SortState>>> = {
  priority: { key: "priority", direction: "descending" },
  due_at: { key: "due_at", direction: "ascending" },
  complaint_count: { key: "complaint_count", direction: "descending" },
  created_at: { key: "age_days", direction: "ascending" },
};

/** The heading the inbox shows as sorted: the one a heading click chose, else the "Sort by" choice's column. */
export function signalTableSort(filters: Pick<SignalFilters, "sort" | "order">): SortState {
  if (filters.order) return { key: filters.sort, direction: filters.order === "asc" ? "ascending" : "descending" };
  return NATURAL_SORT[filters.sort as SignalSort] ?? null;
}

/**
 * The sort after a click on a column heading: ascending, descending, then back to the usual order ("Sort by"
 * Priority). A click on the column "Sort by" already orders turns it the other way round first.
 */
export function nextSignalSort(
  filters: Pick<SignalFilters, "sort" | "order">,
  key: string,
): Pick<SignalFilters, "sort" | "order"> {
  const current = signalTableSort(filters);
  if (!filters.order && current?.key === key)
    return { sort: key as SignalSortKey, order: current.direction === "ascending" ? "desc" : "asc" };
  const next = nextSort(current, key);
  if (!next) return { sort: DEFAULT_SIGNAL_FILTERS.sort, order: "" };
  return { sort: next.key as SignalSortKey, order: next.direction === "ascending" ? "asc" : "desc" };
}

const isStatusFilter = (value: string): value is StatusFilter =>
  value === "OPEN" || value === "ALL" || (SIGNAL_STATUSES as readonly string[]).includes(value);
const isPriority = (value: string): value is SignalPriority => (SIGNAL_PRIORITIES as readonly string[]).includes(value);
const isSort = (value: string): value is SignalSort => SIGNAL_SORTS.some((item) => item.value === value);

/** The statuses a status filter stands for (empty for every status). */
export function statusesFor(filter: StatusFilter): readonly SignalStatus[] {
  if (filter === "ALL") return [];
  if (filter === "OPEN") return OPEN_SIGNAL_STATUSES;
  return [filter];
}

/**
 * One page of the inbox (GET /api/v1/triage/signals). Several statuses or priorities are sent comma-separated; empty
 * filters are left out.
 */
export function signalListPath(filters: Partial<SignalFilters>, page = 1, pageSize = 50): string {
  const value = { ...DEFAULT_SIGNAL_FILTERS, ...filters };
  const params = new URLSearchParams();
  const statuses = statusesFor(value.status);
  if (statuses.length) params.set("status", statuses.join(","));
  if (value.priorities.length) params.set("priority", value.priorities.join(","));
  if (value.productId) params.set("product_id", value.productId);
  if (value.origin) params.set("origin", value.origin);
  if (value.owner) params.set("owner", value.owner);
  if (value.q.trim()) params.set("q", value.q.trim());
  if (value.overdue) params.set("overdue", "true");
  if (value.reviewDue) params.set("review_due", "true");
  params.set("sort", value.sort);
  if (value.order) params.set("order", value.order);
  params.set("page", String(Math.max(1, page)));
  params.set("page_size", String(pageSize));
  return `/api/v1/triage/signals?${params}`;
}

/** Where Signals should open: a tab, the inbox's filters, and a signal to show. */
export type SignalsTarget = { tab?: SignalsTab; filters?: Partial<SignalFilters>; signal?: string | null };

/**
 * The tab name `open("Signals", tab)` takes to reach a target: "Signal inbox?priority=HIGH,CRITICAL" or
 * "Signal inbox?signal=SIG000023". A plain tab name when there is nothing more to say.
 */
export function signalsTab(target: SignalsTarget): string {
  const tab = target.tab ?? "Signal inbox";
  const params = new URLSearchParams();
  const filters = target.filters ?? {};
  if (filters.status && filters.status !== DEFAULT_SIGNAL_FILTERS.status) params.set("status", filters.status);
  if (filters.priorities?.length) params.set("priority", filters.priorities.join(","));
  if (filters.productId) params.set("product_id", filters.productId);
  if (filters.origin) params.set("origin", filters.origin);
  if (filters.owner) params.set("owner", filters.owner);
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  if (filters.sort && filters.sort !== DEFAULT_SIGNAL_FILTERS.sort) params.set("sort", filters.sort);
  if (filters.overdue) params.set("overdue", "1");
  if (filters.reviewDue) params.set("review_due", "1");
  const signal = signalRefText(target.signal);
  if (signal) params.set("signal", signal);
  const rest = params.toString();
  return rest ? `${tab}?${rest}` : tab;
}

/** What a tab name passed to Signals asks for (see signalsTab); unknown names open the Signal inbox. */
export function parseSignalsTab(value: string | null | undefined): {
  tab: SignalsTab;
  filters: SignalFilters;
  signal: string | null;
} {
  const text = String(value ?? "");
  const mark = text.indexOf("?");
  const name = mark >= 0 ? text.slice(0, mark) : text;
  const params = new URLSearchParams(mark >= 0 ? text.slice(mark + 1) : "");
  const tab: SignalsTab = (SIGNALS_TABS as readonly string[]).includes(name)
    ? (name as SignalsTab)
    : (LEGACY_SIGNALS_TABS[name] ?? "Signal inbox");
  const status = code(params.get("status"));
  const sort = String(params.get("sort") ?? "");
  const owner = String(params.get("owner") ?? "");
  const filters: SignalFilters = {
    ...DEFAULT_SIGNAL_FILTERS,
    status: isStatusFilter(status) ? status : DEFAULT_SIGNAL_FILTERS.status,
    priorities: String(params.get("priority") ?? "")
      .split(",")
      .map(code)
      .filter(isPriority),
    productId: params.get("product_id") ?? "",
    origin: (SIGNAL_ORIGINS as readonly string[]).includes(code(params.get("origin")))
      ? code(params.get("origin"))
      : "",
    owner: owner === "me" || owner === "unassigned" ? owner : "",
    q: params.get("q") ?? "",
    sort: isSort(sort) ? sort : DEFAULT_SIGNAL_FILTERS.sort,
    overdue: params.has("overdue"),
    reviewDue: params.has("review_due"),
  };
  return { tab, filters, signal: signalRefText(params.get("signal")) };
}

// A signal as people quote it (SIG000023) or its id; anything else in an address is ignored.
const SIGNAL_REF = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const signalRefText = (value: unknown): string | null => {
  const text = typeof value === "string" ? value.trim() : "";
  return SIGNAL_REF.test(text) ? text : null;
};

/** The signal a link names (/app/signals?signal=SIG000023), or null when it names none. */
export function signalFromSearch(search: string | null | undefined): string | null {
  return signalRefText(new URLSearchParams(search ?? "").get("signal"));
}

/** The address's query without its signal link (so a reload starts on the inbox, not the old link). */
export function searchWithoutSignal(search: string | null | undefined): string {
  const params = new URLSearchParams(search ?? "");
  params.delete("signal");
  const rest = params.toString();
  return rest ? `?${rest}` : "";
}

/** Where a signal link opens: that signal in Signals, for an address in Signals; any other address as without it. */
export function signalLinkStart(
  view: string | undefined,
  start: [WorkspaceSection, string?],
  signal: string | null,
): [WorkspaceSection, string?] {
  if (!signal || view !== "signals") return start;
  return ["Signals", signalsTab({ signal })];
}

/** Whether a listed signal is the one a link names: by its business ID (any case) or its id. */
export function isSignalRef(signal: Pick<SignalSummary, "id" | "business_id">, ref: string): boolean {
  const wanted = ref.trim().toLowerCase();
  return (
    !!wanted &&
    (String(signal.id).toLowerCase() === wanted || String(signal.business_id ?? "").toLowerCase() === wanted)
  );
}

/** A reference can be read straight by id (GET /api/v1/triage/signals/{id}) only when it is the signal's UUID. */
export const isSignalId = (ref: string) => isUuid(ref);

export const signalPath = (id: string, action?: string) =>
  `/api/v1/triage/signals/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;

// ---------------------------------------------------------------------------------------------------------------
// How a signal reads

const STATUS_TONE: Record<string, Tone> = {
  NEW: "warning",
  TRIAGE: "warning",
  ESCALATED: "critical",
  INVESTIGATION_REQUIRED: "serious",
  INVESTIGATION_OPEN: "neutral",
  MONITOR: "neutral",
  NO_ACTION: "good",
  DUPLICATE: "neutral",
  MERGED: "neutral",
  DECISION_RECORDED: "good",
  CLOSED: "good",
};

const STATUS_LABEL: Record<string, string> = {
  NEW: "New",
  TRIAGE: "In triage",
  MONITOR: "Monitor",
  NO_ACTION: "No action",
  DUPLICATE: "Duplicate",
  MERGED: "Merged",
  INVESTIGATION_REQUIRED: "Investigation required",
  ESCALATED: "Escalated",
  INVESTIGATION_OPEN: "Investigation open",
  DECISION_RECORDED: "Decision recorded",
  CLOSED: "Closed",
};

/** A status as people read it: the server's label when it gives one, else ours, never the raw code. */
export function signalStatusLabel(status: unknown, label?: unknown): string {
  const own = safeText(label);
  if (own) return own;
  const key = code(status);
  if (!key) return "—";
  return STATUS_LABEL[key] ?? titleCase(key);
}

export const signalStatusTone = (status: unknown): Tone => STATUS_TONE[code(status)] ?? "neutral";

/** The label of a status filter chip. */
export const statusFilterLabel = (filter: StatusFilter) =>
  filter === "OPEN" ? "Open" : filter === "ALL" ? "All" : signalStatusLabel(filter);

/** The chips above the inbox: Open, every status the counts name (or that is selected), All; each with its count. */
export function statusChips(
  counts: Partial<Record<string, number>> | null | undefined,
  selected: StatusFilter,
): Array<{ value: StatusFilter; label: string; count: number | null }> {
  const value = (status: string) => {
    const count = counts?.[status] ?? counts?.[status.toLowerCase()];
    return typeof count === "number" && Number.isFinite(count) ? count : null;
  };
  const sum = (statuses: readonly string[]) => {
    if (!counts) return null;
    return statuses.reduce((total, status) => total + (value(status) ?? 0), 0);
  };
  const shown = SIGNAL_STATUSES.filter((status) => (value(status) ?? 0) > 0 || status === selected);
  return [
    { value: "OPEN", label: "Open", count: sum(OPEN_SIGNAL_STATUSES) },
    ...shown.map((status) => ({
      value: status as StatusFilter,
      label: signalStatusLabel(status),
      count: value(status),
    })),
    { value: "ALL", label: "All", count: sum(SIGNAL_STATUSES) },
  ];
}

const ORIGIN_LABEL: Record<string, string> = {
  MANUAL: "Created by a person",
  THRESHOLD_RULE: "Complaint threshold rule",
  AI_SUGGESTED: "Suggested by AI",
  IMPORT: "Imported",
};

export function signalOriginLabel(origin: unknown, label?: unknown): string {
  const own = safeText(label);
  if (own) return own;
  const key = code(origin);
  return key ? (ORIGIN_LABEL[key] ?? titleCase(key)) : "—";
}

export const signalPriorityLabel = (priority: unknown) => (code(priority) ? titleCase(code(priority)) : "—");

/**
 * The signal's priority as it stands: the one a person confirmed, else the suggested one. `changed` when a person
 * confirmed a different priority than the suggestion; `confirmed` false while nobody has confirmed it yet.
 */
export function signalPriority(signal: Pick<SignalSummary, "priority" | "suggested_priority" | "confirmed_priority">): {
  current: string | null;
  suggested: string | null;
  confirmed: string | null;
  isConfirmed: boolean;
  changed: boolean;
} {
  const suggested = code(signal.suggested_priority) || null;
  const confirmed = code(signal.confirmed_priority) || null;
  const current = confirmed ?? (code(signal.priority) || null) ?? suggested;
  return {
    current,
    suggested,
    confirmed,
    isConfirmed: !!confirmed,
    changed: !!confirmed && !!suggested && confirmed !== suggested,
  };
}

/** "Suggested High → confirmed Critical", "Suggested High (not confirmed)", "Confirmed Low". */
export function priorityText(signal: Pick<SignalSummary, "priority" | "suggested_priority" | "confirmed_priority">) {
  const { suggested, confirmed, changed } = signalPriority(signal);
  if (changed) return `Suggested ${signalPriorityLabel(suggested)} → confirmed ${signalPriorityLabel(confirmed)}`;
  if (confirmed) return `Confirmed ${signalPriorityLabel(confirmed)}`;
  if (suggested) return `Suggested ${signalPriorityLabel(suggested)} (not confirmed)`;
  return "Not set";
}

/** The product and version a signal is about, by name and version ("Infusion pump · version B"). */
export function signalProductText(signal: Pick<SignalSummary, "product" | "product_version">): string {
  const product = safeText(signal.product?.name) ?? safeText(signal.product?.business_id) ?? "—";
  const version = safeText(signal.product_version?.version_identifier);
  return version ? `${product} · version ${version}` : product;
}

/** A rule's parameters as people read them: "Min complaints 3 · Window days 30"; "" when there are none. */
export function ruleParametersText(parameters: Record<string, unknown> | null | undefined): string {
  return Object.entries(parameters ?? {})
    .filter(([, value]) => value !== null && value !== undefined && typeof value !== "object" && !isUuid(value))
    .map(([key, value]) => {
      const words = key.replace(/_/g, " ").toLowerCase();
      return `${words.charAt(0).toUpperCase()}${words.slice(1)} ${value}`;
    })
    .join(" · ");
}

/** One related record (a change, an open CAPA, an open case) as a line: its ID, what it is about, its status. */
export function relatedItem(row: Record<string, unknown> | null | undefined): {
  id: string;
  text: string | null;
  status: string | null;
} {
  const record = row ?? {};
  const id =
    safeText(record.business_id) ??
    Object.entries(record)
      .filter(([key]) => key.endsWith("_identifier") || key === "reference")
      .map(([, value]) => safeText(value))
      .find(Boolean) ??
    "—";
  const text =
    ["title", "investigation_question", "description", "summary", "name", "change_type"]
      .map((key) => safeText(record[key]))
      .find(Boolean) ?? null;
  return { id, text, status: safeText(record.status) };
}

const CLOSED_SIGNAL = ["NO_ACTION", "DUPLICATE", "MERGED", "DECISION_RECORDED", "CLOSED"];
const DUE_SOON_HOURS = 48;

export type SignalDueState = "overdue" | "due_soon" | "due" | "none" | "done";

/** How a signal's triage due date stands: overdue (as the server says, or past due), due within two days, or later. */
export function signalDueState(
  signal: Pick<SignalSummary, "due_at" | "overdue" | "status">,
  now = new Date(),
): SignalDueState {
  if (CLOSED_SIGNAL.includes(code(signal.status))) return "done";
  if (signal.overdue === true) return "overdue";
  if (!signal.due_at) return "none";
  const due = new Date(signal.due_at).getTime();
  if (Number.isNaN(due)) return "none";
  if (due < now.getTime()) return "overdue";
  return due - now.getTime() <= DUE_SOON_HOURS * 3_600_000 ? "due_soon" : "due";
}

/** "3 Oct 2026, 14:00 · overdue" for the Due column; "—" when there is no due date. */
export function signalDueText(
  signal: Pick<SignalSummary, "due_at" | "overdue" | "status">,
  format: (value: unknown) => string,
  now = new Date(),
): string {
  const state = signalDueState(signal, now);
  if (!signal.due_at) return state === "overdue" ? "Overdue" : "—";
  const when = format(signal.due_at);
  if (state === "overdue") return `${when} · overdue`;
  if (state === "due_soon") return `${when} · due soon`;
  return when;
}

/** "Today", "1 day", "12 days" for the Age column; "—" when unknown. */
export function ageText(days: unknown): string {
  const value = typeof days === "number" ? days : Number.NaN;
  if (!Number.isFinite(value) || value < 0) return "—";
  const whole = Math.floor(value);
  if (whole === 0) return "Today";
  return `${whole} ${whole === 1 ? "day" : "days"}`;
}

/** The harm a complaint records, most serious first ("Death", "Serious injury", "Malfunction"). */
export function harmFlags(complaint: Pick<SignalComplaint, "death" | "serious_injury" | "malfunction">): string[] {
  return [
    ...(complaint.death ? ["Death"] : []),
    ...(complaint.serious_injury ? ["Serious injury"] : []),
    ...(complaint.malfunction ? ["Malfunction"] : []),
  ];
}

const ADDED_HOW: Record<string, string> = { RULE: "By the rule", MANUAL: "By a person", MERGE: "From a merge" };
export const addedHowLabel = (value: unknown) => {
  const key = code(value);
  return key ? (ADDED_HOW[key] ?? titleCase(key)) : "—";
};

/**
 * The share of a signal's complaints per product version, largest first, as whole percentages that add up to 100
 * (largest remainder), for the version split bars.
 */
export function versionSplit(rows: VersionSplitRow[] | null | undefined): Array<{
  key: string;
  label: string;
  count: number;
  percent: number;
}> {
  const items = (rows ?? [])
    .map((row, index) => ({
      key: safeText(row.product_version_business_id) ?? safeText(row.version_identifier) ?? `version-${index}`,
      label: safeText(row.version_identifier)
        ? `Version ${row.version_identifier}`
        : (safeText(row.product_version_business_id) ?? "Version not recorded"),
      count: Math.max(0, Number(row.count) || 0),
    }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  const total = items.reduce((sum, item) => sum + item.count, 0);
  if (!total) return items.map((item) => ({ ...item, percent: 0 }));
  const exact = items.map((item) => (item.count / total) * 100);
  const floors = exact.map(Math.floor);
  let left = 100 - floors.reduce((sum, value) => sum + value, 0);
  const order = exact
    .map((value, index) => ({ index, remainder: value - Math.floor(value) }))
    .sort((a, b) => b.remainder - a.remainder || a.index - b.index);
  for (const { index } of order) {
    if (left <= 0) break;
    floors[index] += 1;
    left -= 1;
  }
  return items.map((item, index) => ({ ...item, percent: floors[index] }));
}

/** Signals in the order the dashboard shows them: highest priority first, then the earliest due, then the oldest. */
export function rankSignals<
  T extends Pick<SignalSummary, "priority" | "suggested_priority" | "confirmed_priority" | "due_at" | "age_days">,
>(rows: T[]): T[] {
  const due = (row: T) => {
    const time = row.due_at ? new Date(row.due_at).getTime() : Number.NaN;
    return Number.isNaN(time) ? Number.POSITIVE_INFINITY : time;
  };
  return rows
    .map((row, index) => ({ row, index }))
    .sort(
      (a, b) =>
        priorityRank(signalPriority(b.row).current) - priorityRank(signalPriority(a.row).current) ||
        due(a.row) - due(b.row) ||
        (Number(b.row.age_days) || 0) - (Number(a.row.age_days) || 0) ||
        a.index - b.index,
    )
    .map((item) => item.row);
}

/** The dashboard's triage counts, each with the inbox filter it opens. */
export function triageCountTiles(summary: TriageSummary | null | undefined): Array<{
  key: string;
  label: string;
  value: number | null;
  urgent: boolean;
  filters: Partial<SignalFilters>;
}> {
  const counts = summary?.counts ?? null;
  const read = (key: keyof NonNullable<TriageSummary["counts"]>) => {
    const value = counts?.[key];
    return typeof value === "number" && Number.isFinite(value) ? value : counts ? 0 : null;
  };
  return [
    { key: "new", label: "New", value: read("new"), urgent: false, filters: { status: "NEW" } },
    { key: "triage", label: "In triage", value: read("triage"), urgent: false, filters: { status: "TRIAGE" } },
    { key: "escalated", label: "Escalated", value: read("escalated"), urgent: true, filters: { status: "ESCALATED" } },
    {
      key: "investigation_required",
      label: "Investigation required",
      value: read("investigation_required"),
      urgent: false,
      filters: { status: "INVESTIGATION_REQUIRED" },
    },
    {
      key: "monitor_review_due",
      label: "Monitor review due",
      value: read("monitor_review_due"),
      urgent: false,
      filters: { status: "MONITOR", reviewDue: true, sort: "due_at" },
    },
    {
      key: "overdue",
      label: "Overdue",
      value: read("overdue"),
      urgent: true,
      filters: { status: "OPEN", overdue: true, sort: "due_at" },
    },
  ];
}

// ---------------------------------------------------------------------------------------------------------------
// Triage actions: when they may be sent and what they send

export const REASON_MIN = 10;
export const PRIORITY_REASON_MAX = 1000;
export const DISPOSITION_REASON_MAX = 2000;
export const QUESTION_MIN = 10;
export const QUESTION_MAX = 2000;

/** Why a written text cannot be sent yet, or null when it can (the server checks the same limits). */
export function textProblem(value: string, min: number, max: number, what = "a reason", required = true) {
  const text = value.trim();
  if (!text && !required) return null;
  if (text.length < min) return `Give ${what} of at least ${min} characters.`;
  if (text.length > max) return `Keep ${what} to ${max} characters.`;
  return null;
}

/** A reason is needed when the chosen priority differs from the suggested one. */
export const priorityNeedsReason = (suggested: unknown, chosen: unknown) =>
  !!code(chosen) && !!code(suggested) && code(chosen) !== code(suggested);

export function priorityProblem(input: { priority: string; reason: string; suggested?: string | null }) {
  if (!isPriority(code(input.priority))) return "Choose a priority.";
  return textProblem(
    input.reason,
    REASON_MIN,
    PRIORITY_REASON_MAX,
    "a reason",
    priorityNeedsReason(input.suggested, input.priority),
  );
}

export function priorityBody(input: { priority: string; reason: string }) {
  const reason = input.reason.trim();
  return { priority: code(input.priority), ...(reason ? { reason } : {}) };
}

export type DispositionForm = {
  disposition: Disposition | "";
  reason: string;
  canonicalSignalId: string;
  monitorReviewDate: string;
  monitorTrigger: string;
};

export const EMPTY_DISPOSITION: DispositionForm = {
  disposition: "",
  reason: "",
  canonicalSignalId: "",
  monitorReviewDate: "",
  monitorTrigger: "",
};

export const DISPOSITION_LABEL: Record<Disposition, string> = {
  INVESTIGATION_REQUIRED: "Investigation required",
  ESCALATED: "Escalate",
  MONITOR: "Monitor",
  NO_ACTION: "No action needed",
  DUPLICATE: "Duplicate of another signal",
};

export const DISPOSITION_HELP: Record<Disposition, string> = {
  INVESTIGATION_REQUIRED: "A case is needed. Create the investigation from this signal next.",
  ESCALATED: "Raise it to management or the regulatory team now.",
  MONITOR: "Keep watching. Say when to look again and what would reopen it.",
  NO_ACTION: "No further action is needed. Say why.",
  DUPLICATE: "Another signal already covers this problem. Its complaints stay on this record.",
};

const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Why a disposition cannot be recorded yet, or null when it can. `today` is the local calendar day (YYYY-MM-DD). */
export function dispositionProblem(form: DispositionForm, today: string): string | null {
  if (!form.disposition || !(DISPOSITIONS as readonly string[]).includes(form.disposition))
    return "Choose a disposition.";
  if (form.disposition === "DUPLICATE" && !form.canonicalSignalId.trim())
    return "Choose the signal this one duplicates.";
  if (form.disposition === "MONITOR") {
    if (!DAY.test(form.monitorReviewDate)) return "Choose the date to review it again.";
    if (form.monitorReviewDate <= today) return "The review date must be in the future.";
  }
  return textProblem(form.reason, REASON_MIN, DISPOSITION_REASON_MAX);
}

/** The body of POST /{id}/disposition: only the fields the chosen disposition takes. */
export function dispositionBody(form: DispositionForm) {
  const trigger = form.monitorTrigger.trim();
  return {
    disposition: form.disposition,
    reason: form.reason.trim(),
    ...(form.disposition === "DUPLICATE" ? { canonical_signal_id: form.canonicalSignalId } : {}),
    ...(form.disposition === "MONITOR"
      ? { monitor_review_date: form.monitorReviewDate, ...(trigger ? { monitor_trigger: trigger } : {}) }
      : {}),
  };
}

export function mergeProblem(sources: string[], reason: string) {
  if (!sources.length) return "Choose at least one signal to merge into this one.";
  return textProblem(reason, REASON_MIN, DISPOSITION_REASON_MAX);
}

export function addComplaintsProblem(complaints: string[], reason: string) {
  if (!complaints.length) return "Choose at least one complaint.";
  return textProblem(reason, REASON_MIN, DISPOSITION_REASON_MAX);
}

/** The investigation question a new case starts from: the signal's title, as a question. */
export function defaultInvestigationQuestion(signal: Pick<SignalSummary, "title" | "business_id">): string {
  const title = safeText(signal.title);
  if (!title) return "";
  const subject = title.replace(/[.?!\s]+$/, "");
  // "Battery drains early" reads "battery drains early"; an acronym or code ("USB port", "BATTERY_DRAIN") is kept.
  const lower = /^[A-Z][a-z]/.test(subject) ? `${subject.charAt(0).toLowerCase()}${subject.slice(1)}` : subject;
  return `What is the root cause of ${lower}?`;
}

export type InvestigationForm = {
  question: string;
  complaintIds: string[];
  /** A person, or "" to leave the case in the investigators' queue. */
  assigneeUserId: string;
  alsoSignalIds: string[];
  identifier: string;
};

export function investigationProblem(form: InvestigationForm): string | null {
  if (!form.complaintIds.length) return "Keep at least one complaint for the case.";
  return textProblem(form.question, QUESTION_MIN, QUESTION_MAX, "an investigation question");
}

/** The body of POST /{id}/create-investigation; empty optional fields are left out. */
export function investigationBody(form: InvestigationForm) {
  const identifier = form.identifier.trim();
  return {
    investigation_question: form.question.trim(),
    complaint_ids: form.complaintIds,
    ...(form.assigneeUserId ? { assignee_user_id: form.assigneeUserId } : {}),
    ...(form.alsoSignalIds.length ? { also_signal_ids: form.alsoSignalIds } : {}),
    ...(identifier ? { investigation_identifier: identifier } : {}),
  };
}

export type NewSignalForm = {
  title: string;
  description: string;
  productId: string;
  productVersionId: string;
  complaintIds: string[];
  priority: string;
  reason: string;
};

export const EMPTY_NEW_SIGNAL: NewSignalForm = {
  title: "",
  description: "",
  productId: "",
  productVersionId: "",
  complaintIds: [],
  priority: "",
  reason: "",
};

export function newSignalProblem(form: NewSignalForm): string | null {
  if (form.title.trim().length < 3) return "Give the signal a title.";
  if (!form.productId) return "Choose the product.";
  if (!form.complaintIds.length) return "Choose at least one complaint.";
  if (form.priority && !isPriority(code(form.priority))) return "Choose a priority.";
  // A priority set by hand is a judgement: say why.
  if (form.priority) return textProblem(form.reason, REASON_MIN, PRIORITY_REASON_MAX);
  return null;
}

/** The body of POST /api/v1/triage/signals; empty optional fields are left out. */
export function newSignalBody(form: NewSignalForm) {
  const description = form.description.trim();
  const reason = form.reason.trim();
  return {
    title: form.title.trim(),
    product_id: form.productId,
    complaint_ids: form.complaintIds,
    ...(description ? { description } : {}),
    ...(form.productVersionId ? { product_version_id: form.productVersionId } : {}),
    ...(form.priority ? { priority: code(form.priority) } : {}),
    ...(form.priority && reason ? { reason } : {}),
  };
}

// ---------------------------------------------------------------------------------------------------------------
// Detection rules

export const RULE_LIMITS = { minComplaints: [2, 1000], windowDays: [1, 365] } as const;
export const RULE_REASON_MAX = 1000;

export type RuleForm = { enabled: boolean; minComplaints: string; windowDays: string; reason: string };

export const ruleForm = (rule: DetectionRule): RuleForm => ({
  enabled: !!rule.enabled,
  minComplaints: String(rule.min_complaints ?? ""),
  windowDays: String(rule.window_days ?? ""),
  reason: "",
});

const wholeNumber = (value: string) => (/^\d+$/.test(value.trim()) ? Number(value.trim()) : Number.NaN);

export function ruleProblem(form: RuleForm): string | null {
  const min = wholeNumber(form.minComplaints);
  const [minLow, minHigh] = RULE_LIMITS.minComplaints;
  if (!Number.isInteger(min) || min < minLow || min > minHigh)
    return `Minimum complaints must be a whole number from ${minLow} to ${minHigh}.`;
  const days = wholeNumber(form.windowDays);
  const [dayLow, dayHigh] = RULE_LIMITS.windowDays;
  if (!Number.isInteger(days) || days < dayLow || days > dayHigh)
    return `The window must be a whole number of days from ${dayLow} to ${dayHigh}.`;
  return textProblem(form.reason, REASON_MIN, RULE_REASON_MAX);
}

export function ruleChanged(rule: DetectionRule, form: RuleForm): boolean {
  return (
    form.enabled !== !!rule.enabled ||
    wholeNumber(form.minComplaints) !== rule.min_complaints ||
    wholeNumber(form.windowDays) !== rule.window_days
  );
}

export function ruleBody(form: RuleForm) {
  return {
    enabled: form.enabled,
    min_complaints: wholeNumber(form.minComplaints),
    window_days: wholeNumber(form.windowDays),
    reason: form.reason.trim(),
  };
}

/** "Opens a signal when 3 or more complaints about the same problem arrive within 30 days." */
export function ruleSentence(rule: Pick<DetectionRule, "min_complaints" | "window_days">): string {
  const days = rule.window_days === 1 ? "1 day" : `${rule.window_days} days`;
  return `Opens a signal when ${rule.min_complaints} or more complaints about the same product problem arrive within ${days}.`;
}

/** The signal IDs a detection run lists under one heading (or just how many, when it gives a number). */
export function runIds(value: RuleRunResult[keyof RuleRunResult]): { count: number; ids: string[] } {
  if (typeof value === "number") return { count: value, ids: [] };
  const items = Array.isArray(value) ? value : [];
  const ids = items
    .map((item) => (typeof item === "string" ? safeText(item) : (safeText(item?.business_id) ?? null)))
    .filter((item): item is string => !!item);
  return { count: items.length, ids };
}

/** "2 signals created, 1 updated, none reopened." */
export function runSummary(result: RuleRunResult | null | undefined): string {
  if (!result) return "";
  const created = runIds(result.created).count;
  const updated = runIds(result.updated).count;
  const reopened = runIds(result.monitor_reopened).count;
  if (!created && !updated && !reopened) return "Detection ran: no new or changed signals.";
  const part = (count: number, word: string) => (count ? `${count} ${word}` : `none ${word}`);
  return `Detection ran: ${part(created, created === 1 ? "signal created" : "signals created")}, ${part(updated, "updated")}, ${part(reopened, "reopened from monitoring")}.`;
}
