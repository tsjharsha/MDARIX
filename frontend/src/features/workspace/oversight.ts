// Reminders and escalation (T-G25), the oversight view (T-G9) and the event's closure (T-G28): types, paths and the
// pure rules the screens use. The server (/api/v1/oversight, backend/app/oversight) reads every dated item from its
// own record; an alert never closes or changes the item.
import type { Tone } from "../admin/console/dashboardModel";
import type { Opens as LinkOpens } from "../../app/linkTable";
import { timeLeft, type DueLike } from "../../app/dates";

export const OVERSIGHT = "/api/v1/oversight";
export const ALERTS = `${OVERSIGHT}/alerts`;
export const OVERSIGHT_TAB = "Oversight";
export const READINESS_TABS = ["Inspection checks", OVERSIGHT_TAB] as const;
export type ReadinessTab = (typeof READINESS_TABS)[number];

export type ItemState = "OVERDUE" | "DUE_SOON" | "LATER";
export type Opens = LinkOpens | null;

export type Alert = {
  id: string;
  ids: string[];
  tier: "REMINDER" | "ESCALATION";
  tier_label: string;
  reason: string;
  reason_label: string;
  category: string;
  category_label: string;
  title: string;
  ref: string | null;
  owner: string | null;
  due_at: string;
  /** "Sat 28 Nov 2026, 23:59 IST": a legal deadline in the time zone it ends in; anything else in the organization's. */
  due_label?: string;
  state: ItemState;
  state_label: string;
  hours_left: number;
  read: boolean;
  opens: Opens;
};

export type Absence = {
  id: string;
  user_id: string;
  user_name: string;
  backup_id: string;
  backup_name: string;
  starts_on: string;
  ends_on: string;
  note: string | null;
  sample: boolean;
};

export type Person = { id: string; name: string };

export type AlertList = {
  items: Alert[];
  unread: number;
  escalations: number;
  absences: Absence[];
  people: Person[];
  never: string;
};

export type OversightItem = {
  key: string;
  category: string;
  category_label: string;
  title: string;
  ref: string | null;
  complaint_id: string | null;
  market: string | null;
  product: string | null;
  owner: string | null;
  queue: string | null;
  away: { backup: string } | null;
  due_at: string;
  /** "Sat 28 Nov 2026, 23:59 IST": a legal deadline in the time zone it ends in; anything else in the organization's. */
  due_label?: string;
  state: ItemState;
  state_label: string;
  hours_left: number;
  escalated_to: string[];
  alerts: boolean;
  opens: Opens;
};

export type EventState = "NOT_READY" | "READY_TO_SIGN" | "NOT_FILED" | "FILED" | "CLOSED_BEFORE_READY" | "CLOSED";

export type EventRow = {
  complaint_id: string;
  ref: string;
  product: string | null;
  market: string | null;
  owner_id: string | null;
  owner_name: string | null;
  stage: string;
  blocked: number;
  next: string | null;
  state: EventState;
  state_label: string;
  sample: boolean;
};

export type OversightSettings = {
  time_zone: string;
  work_days: number[];
  holidays: Array<{ date: string; name: string }>;
  reminder_hours: number;
  escalation_role: string;
  escalation_role_label: string;
  updated_at: string | null;
  roles?: Array<{ code: string; label: string }>;
  weekdays?: string[];
  zones?: string[];
  range?: [number, number];
};

export type Oversight = {
  as_of: string;
  items: OversightItem[];
  total: number;
  counts: Record<string, { label: string; overdue: number; due_soon: number }>;
  overdue: number;
  due_soon: number;
  filters: { products: string[]; markets: string[]; categories: Array<{ code: string; label: string }> };
  events: EventRow[];
  event_counts: Record<EventState, number>;
  away: Absence[];
  settings: OversightSettings;
  staffing: string | null;
  never: string;
};

export type CheckItem = {
  code: string;
  label: string;
  result: "PASS" | "BLOCKED" | "NOT_REQUIRED" | "INFO";
  result_label: string;
  detail: string;
  opens: Opens;
  /** What to do next, for an open item ("Sign the United States (FDA) market assessment"). */
  action?: string | null;
};

export type RecordEntry = {
  kind: string;
  summary: string;
  reason: string | null;
  signer: string;
  signed_at: string | null;
  meaning: string | null;
  record_id: string | null;
  record_ref: string | null;
};

export type EventView = {
  event: {
    complaint_id: string;
    ref: string;
    business_id: string | null;
    product: string | null;
    market: string | null;
    awareness_at: string | null;
    status_in_qms: string;
    owner_id: string | null;
    owner_name: string | null;
    owner_named: boolean;
    sample: boolean;
    /** What happened, as the complaint records it (0.10.68: the complaint page's header). */
    description?: string | null;
    problem_code?: string | null;
    version?: string | null;
    lot?: string | null;
    country?: string | null;
    harm?: "DEATH" | "SERIOUS_INJURY" | "PATIENT_INVOLVED" | null;
  };
  summary: {
    nearest_deadline: { title: string; due_at: string; opens: Opens } | null;
    open_requests: number;
    next_action: { label: string; detail: string; opens: Opens } | null;
  };
  stages: Array<{ code: string; label: string; state: "DONE" | "CURRENT" | "OPEN" | "LATER" | "NOT_NEEDED" }>;
  checklist: CheckItem[];
  blocked: number;
  state: EventState;
  state_label: string;
  changed_since_signed: boolean;
  ready: { state: string; reason: string | null; version: number; signed_by: string; signed_at: string | null } | null;
  decision_record: {
    entries: RecordEntry[];
    sha256: string;
    version: number;
    filed: { reference: string; by: string; at: string | null } | null;
  };
  you_are_owner: boolean;
  people: Person[];
  reason_min: number;
  never_closes: string;
  practice_label: string | null;
  /** The owner, stage, next action and dated items the lists and My work show (0.10.68). */
  work?: {
    owner_name: string | null;
    stage: string;
    next: string | null;
    due: Array<{
      key: string;
      category: string;
      category_label: string;
      title: string;
      market: string | null;
      due_at: string;
      due_label?: string;
      state: ItemState;
      state_label: string;
      hours_left: number;
      opens: Opens;
    }>;
    markets: string[];
  };
  /** Who may sign each step, before the work starts (0.10.68, 7.8). */
  signers?: Record<string, { people: Person[]; you: boolean; second_person: boolean }>;
  /** The linked service work (0.10.71, A5); it never closes or advances the complaint. */
  service?: ServiceWork | null;
  /** Who prepared, who may approve and who approved the event's work (0.10.71, A6). */
  record_people?: { prepared_by: string[]; may_approve: string[]; approved_by: string[]; practice_note: string | null };
  /** The records linked to the complaint, for the page's Related (0.10.74, C2). */
  related?: RelatedGroup[];
};

/** One kind of record linked to a complaint, in plain lines (backend/app/oversight/record_page.py related). */
export type RelatedGroup = {
  key: "communications" | "assessments" | "service" | "investigations" | "reports" | "decisions";
  label: string;
  count: number;
  lines: string[];
  items?: Array<{ id: string; ref: string }>;
};

/** One line of a complaint's Activity: its own audit event, or (from_record) the record's own received time. */
export type ActivityItem = {
  at: string | null;
  title: string;
  who: string | null;
  reason: string | null;
  from_record?: boolean;
};

export type ServiceStatus = "OPEN" | "IN_PROGRESS" | "COMPLETE";
export type ServiceWork = {
  reference: string;
  owner_id: string | null;
  owner_name: string | null;
  status: ServiceStatus;
  status_label: string;
  status_at: string | null;
  /** "Service complete · Quality assessment open" once complete. */
  header: string | null;
};
export const SERVICE_STATUSES: Array<[ServiceStatus, string]> = [
  ["OPEN", "Open"],
  ["IN_PROGRESS", "In progress"],
  ["COMPLETE", "Complete"],
];

export type Filters = { product: string; market: string; category: string; show: "attention" | "all" };
export const NO_FILTERS: Filters = { product: "", market: "", category: "", show: "attention" };

/** The query string of the oversight list (and its CSV), only the filters that are set. */
export function filterQuery(filters: Filters): string {
  const params = new URLSearchParams();
  if (filters.product) params.set("product", filters.product);
  if (filters.market) params.set("market", filters.market);
  if (filters.category) params.set("category", filters.category);
  if (filters.show === "all") params.set("show", "all");
  const text = params.toString();
  return text ? `?${text}` : "";
}

export const oversightPath = (filters: Filters) => `${OVERSIGHT}${filterQuery(filters)}`;
export const exportPath = (filters: Filters) => `${OVERSIGHT}/export.csv${filterQuery(filters)}`;
export const eventPath = (complaintId: string) => `${OVERSIGHT}/events/${encodeURIComponent(complaintId)}`;

/** A link to one event's closure in the oversight view ("Oversight?event=<id>"). */
export const eventTab = (complaintId: string) => `${OVERSIGHT_TAB}?event=${encodeURIComponent(complaintId)}`;

export function parseReadinessTab(tab: string | null | undefined): { tab: ReadinessTab; event: string | null } {
  if (tab && (tab === OVERSIGHT_TAB || tab.startsWith(`${OVERSIGHT_TAB}?`)))
    return { tab: OVERSIGHT_TAB, event: new URLSearchParams(tab.slice(OVERSIGHT_TAB.length + 1)).get("event") };
  return { tab: "Inspection checks", event: null };
}

export const stateTone = (state: ItemState): Tone =>
  state === "OVERDUE" ? "critical" : state === "DUE_SOON" ? "warning" : "neutral";

export const alertTone = (alert: Pick<Alert, "tier" | "state">): Tone =>
  alert.tier === "ESCALATION" ? "critical" : stateTone(alert.state);

/** "3 h left", "2 days left", "5 h overdue": the app's one helper (app/dates.ts timeLeft), overdue from the state. */
export const hoursText = (item: Pick<DueLike, "state" | "due_at" | "hours_left">) => timeLeft(item);

/** Escalations and overdue items one by one; the items only due soon grouped by category, so a long triage list
 * reads as one line. */
export function groupAlerts(items: Alert[]): {
  urgent: Alert[];
  soon: Array<{ category: string; label: string; items: Alert[] }>;
} {
  const urgent = items.filter((item) => item.tier === "ESCALATION" || item.state === "OVERDUE");
  const soon: Array<{ category: string; label: string; items: Alert[] }> = [];
  for (const item of items) {
    if (urgent.includes(item)) continue;
    const group = soon.find((entry) => entry.category === item.category);
    if (group) group.items.push(item);
    else soon.push({ category: item.category, label: item.category_label, items: [item] });
  }
  return { urgent, soon };
}

export const EVENT_TONES: Record<EventState, Tone> = {
  NOT_READY: "warning",
  READY_TO_SIGN: "good",
  NOT_FILED: "warning",
  FILED: "good",
  CLOSED_BEFORE_READY: "critical",
  CLOSED: "neutral",
};

export const CHECK_TONES: Record<CheckItem["result"], Tone> = {
  PASS: "good",
  BLOCKED: "critical",
  NOT_REQUIRED: "neutral",
  INFO: "warning",
};

/** Why "ready to close" cannot be signed yet, or null. A blocked checklist needs a written reason. */
export function readyProblem(view: Pick<EventView, "you_are_owner" | "blocked" | "reason_min">, reason: string) {
  if (!view.you_are_owner) return "Only the event owner signs: name yourself the owner first.";
  if (view.blocked && reason.trim().length < view.reason_min)
    return `${view.blocked} ${view.blocked === 1 ? "item is" : "items are"} still open: resolve them, or give the reason to sign anyway (at least ${view.reason_min} characters).`;
  return null;
}

/** Why an absence cannot be recorded, or null. */
export function absenceProblem(form: { starts_on: string; ends_on: string; backup_id: string }, today: string) {
  if (!form.backup_id) return "Choose the colleague who covers for you.";
  if (!form.starts_on || !form.ends_on) return "Give the first and the last day.";
  if (form.ends_on < form.starts_on) return "The last day is before the first.";
  if (form.ends_on < today) return "The absence is over already.";
  return null;
}

export const WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
