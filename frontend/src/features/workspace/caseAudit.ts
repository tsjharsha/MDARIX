// Pure rules for a case's trust and audit view (Phase 7): the case timeline (categories, origins, titles, actors, the
// record each event names and where it opens, the filters as a query), the replay of what was known at a moment
// (known then / arrived later, the evidence fingerprint then and now), the AI runs of the case (labels, guardrails,
// human review) and the integrity checks (signatures, the audit chain, brief fingerprints). The server owns every
// record and every check; these only shape what the person sees. AI events never read as a person's act.
import { titleCase, type Tone } from "../admin/console/dashboardModel";
import { safeText } from "../../app/displayId";
import { roleLabel } from "../../app/roles";
import type { WorkspaceSection } from "./workspaceContext";
import { decisionTab } from "./decisionTabs";
import { intelligenceTab } from "./intelligence";
import { reviewsTab } from "./reviews";
import { signalsTab } from "./signals";
import { hashState, verificationChecks, type HistoryRow, type VerificationCheck } from "./humanDecision";

const code = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

const list = (value: unknown): unknown[] => {
  if (Array.isArray(value)) return value;
  const row = record(value);
  for (const key of ["items", "results", "records"]) if (Array.isArray(row[key])) return row[key] as unknown[];
  return [];
};

const idText = (value: unknown): string | null => {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return typeof value === "string" && value.trim() ? value.trim() : null;
};

const numberOf = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return null;
};

/** A role as words: the server's label as it is, a role code ("APPROVER") as its known label. */
const roleText = (value: unknown): string | null => {
  const text = safeText(value);
  if (!text) return null;
  return /^[A-Z][A-Z0-9_]*$/.test(text) ? roleLabel(text) : text;
};

/** A server code ("DECISION_SIGNED") as a sentence ("Decision signed"); any other text as it is. */
export function sentence(value: unknown): string | null {
  const text = safeText(value);
  if (!text) return null;
  // Only a code is turned into words: upper case, or joined by "_" / "." / ":"; text with spaces stays as it is.
  if (!/^[A-Za-z0-9_.:-]+$/.test(text) || (!/[_.:]/.test(text) && text !== text.toUpperCase())) return text;
  const words = text
    .replace(/[_.:-]+/g, " ")
    .trim()
    .toLowerCase();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : null;
}

// ---------------------------------------------------------------------------------------------------------------
// Addresses (prefix /api/v1/investigations/{id}/trust)

export type TrustPart = "timeline" | "replay" | "ai-runs" | "integrity" | "export";

export const trustPath = (investigationId: string, part: TrustPart) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/trust/${part}`;

export type ExportFormat = "json" | "csv";

export const trustExportPath = (investigationId: string, format: ExportFormat) =>
  `${trustPath(investigationId, "export")}?${new URLSearchParams({ format })}`;

/** The name a downloaded audit trail gets when the server does not name it. */
export function trustExportName(caseLabel: string | null | undefined, format: ExportFormat): string {
  const base = String(caseLabel ?? "")
    .trim()
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .replace(/^[-.]+|-+$/g, "");
  return `${base || "case"}-audit-trail.${format}`;
}

// ---------------------------------------------------------------------------------------------------------------
// The tabs of Trust & Audit, and a link to them for one case

export const TRUST_TABS = [
  "Case timeline",
  "Replay",
  "AI runs",
  "Integrity",
  "AI assurance",
  "Audit trail",
  "Data limitations",
] as const;
export type TrustTab = (typeof TRUST_TABS)[number];

/** The tabs that belong to one case (they ask for a case when none is chosen). */
export const CASE_TRUST_TABS: readonly TrustTab[] = ["Case timeline", "Replay", "AI runs", "Integrity"];

const isTrustTab = (value: unknown): value is TrustTab =>
  typeof value === "string" && (TRUST_TABS as readonly string[]).includes(value);

// A reference as it may travel in a tab name; anything else is ignored.
const REF = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const ref = (value: unknown) => {
  const text = typeof value === "string" ? value.trim() : "";
  return REF.test(text) ? text : null;
};

/**
 * The tab name `open("Trust & Audit", tab)` takes: "Case timeline", or "Case timeline?case=…&label=INV000147" for a
 * case the context bar may not hold (opened from a decision). The label is the case's business ID, shown as is.
 */
export function trustTab(target: { tab?: TrustTab; caseId?: string | null; caseLabel?: string | null } = {}): string {
  const tab = target.tab ?? "Case timeline";
  const params = new URLSearchParams();
  const caseId = ref(target.caseId);
  const label = ref(target.caseLabel);
  if (caseId) params.set("case", caseId);
  if (caseId && label) params.set("label", label);
  const query = params.toString();
  return query ? `${tab}?${query}` : tab;
}

/** What a tab name passed to Trust & Audit asks for (see trustTab); an unknown name asks for no tab. */
export function parseTrustTab(value: string | null | undefined): {
  tab: TrustTab | null;
  caseId: string | null;
  caseLabel: string | null;
} {
  const text = String(value ?? "");
  const mark = text.indexOf("?");
  const name = mark >= 0 ? text.slice(0, mark) : text;
  const params = new URLSearchParams(mark >= 0 ? text.slice(mark + 1) : "");
  const caseId = ref(params.get("case"));
  return {
    tab: isTrustTab(name) ? name : null,
    caseId,
    caseLabel: caseId ? ref(params.get("label")) : null,
  };
}

/** The tab Trust & Audit opens on: the one asked for, else the case timeline when a case is chosen. */
export function initialTrustTab(requested: TrustTab | null | undefined, hasCase: boolean): TrustTab {
  if (requested) return requested;
  return hasCase ? "Case timeline" : "AI assurance";
}

// ---------------------------------------------------------------------------------------------------------------
// The case timeline (GET …/trust/timeline), read defensively

export const TIMELINE_CATEGORIES = [
  "SIGNAL",
  "CASE",
  "SCOPE",
  "TASK",
  "EVIDENCE",
  "REQUEST",
  "INTELLIGENCE",
  "AI",
  "REVIEW",
  "BRIEF",
  "DECISION",
  "SIGNATURE",
  "FOLLOW_UP",
  "IMPACT",
  "AUDIT",
] as const;
export type TimelineCategory = (typeof TIMELINE_CATEGORIES)[number];

export const CATEGORY_LABELS: Record<TimelineCategory, string> = {
  SIGNAL: "Signal",
  CASE: "Case",
  SCOPE: "Scope",
  TASK: "Task",
  EVIDENCE: "Evidence",
  REQUEST: "Evidence request",
  INTELLIGENCE: "Intelligence",
  AI: "AI",
  REVIEW: "Review",
  BRIEF: "Decision Brief",
  DECISION: "Decision",
  SIGNATURE: "Signature",
  FOLLOW_UP: "Follow-up",
  IMPACT: "Impact assessment",
  AUDIT: "Audit",
};

const isCategory = (value: string): value is TimelineCategory =>
  (TIMELINE_CATEGORIES as readonly string[]).includes(value);

export function categoryLabel(value: unknown): string {
  const category = code(value);
  if (isCategory(category)) return CATEGORY_LABELS[category];
  return category ? titleCase(category) : "Other";
}

/** The class that colours a category badge (the badge always shows its label too, never colour alone). */
export function categoryClass(value: unknown): string {
  const category = code(value);
  return isCategory(category) ? `ta-cat-${category.toLowerCase().replace(/_/g, "-")}` : "ta-cat-other";
}

export type TimelineActor = { name?: string | null; role_label?: string | null } | null;
export type TimelineObject = { type?: string | null; id?: string | null; business_id?: string | null } | null;

export type TimelineEvent = {
  at?: string | null;
  category?: string | null;
  event?: string | null;
  title?: string | null;
  actor?: TimelineActor;
  object?: TimelineObject;
  reason?: string | null;
  details?: unknown;
  origin?: string | null;
};

export type TimelineResponse = {
  items?: TimelineEvent[] | null;
  total?: number | null;
  categories?: Record<string, number> | null;
};

export type EventOrigin = "HUMAN" | "AI" | "SYSTEM";

export const ORIGIN_COPY: Record<EventOrigin, { label: string; help: string; style: "person" | "ai" | "system" }> = {
  HUMAN: { label: "Person", help: "Done by a person in your organization.", style: "person" },
  AI: {
    label: "AI",
    help: "Produced by AI. It is not a person's act and never a decision or a signature.",
    style: "ai",
  },
  SYSTEM: { label: "System", help: "Done automatically by MDARIX.", style: "system" },
};

const ORIGIN_ALIASES: Record<string, EventOrigin> = {
  HUMAN: "HUMAN",
  PERSON: "HUMAN",
  USER: "HUMAN",
  MANUAL: "HUMAN",
  AI: "AI",
  MODEL: "AI",
  LANGUAGE_MODEL: "AI",
  SYSTEM: "SYSTEM",
  RULES: "SYSTEM",
  MDARIX: "SYSTEM",
  DETERMINISTIC: "SYSTEM",
};

/** Who made an event: a person, AI or MDARIX itself. An AI event without an origin is still AI. */
export function eventOrigin(event: Pick<TimelineEvent, "origin" | "category"> | null | undefined): EventOrigin | null {
  const origin = ORIGIN_ALIASES[code(event?.origin)];
  if (origin) return origin;
  return code(event?.category) === "AI" ? "AI" : null;
}

export function originView(event: Pick<TimelineEvent, "origin" | "category"> | null | undefined) {
  const origin = eventOrigin(event);
  if (!origin) return { code: null, label: "Origin not recorded", help: "The record does not say.", style: "unknown" };
  return { code: origin, ...ORIGIN_COPY[origin] };
}

/** The event's plain title: the server's, else its event code as words, else "<Category> event". */
export function eventTitle(event: Pick<TimelineEvent, "title" | "event" | "category"> | null | undefined): string {
  return safeText(event?.title) ?? sentence(event?.event) ?? `${categoryLabel(event?.category)} event`;
}

/** Who acted and in which role; AI and MDARIX are named as such when no person is recorded. */
export function eventActor(event: Pick<TimelineEvent, "actor" | "origin" | "category"> | null | undefined): {
  name: string;
  role: string | null;
} {
  const actor = record(event?.actor);
  const name = safeText(actor.name);
  const role = roleText(actor.role_label);
  if (name) return { name, role };
  const origin = eventOrigin(event);
  return { name: origin === "AI" ? "AI" : origin === "SYSTEM" ? "MDARIX" : "Not recorded", role };
}

/** Where a linked record opens: the signed decision record (a drawer), or a section and tab of the workspace. */
export type ObjectTarget =
  { kind: "decision"; id: string } | { kind: "section"; section: WorkspaceSection; tab?: string };

const OBJECT_TYPES: Record<string, string> = {
  DECISION: "Decision",
  SIGNAL: "Signal",
  REVIEW: "Review",
  RISK_REVIEW: "Risk review",
  REGULATORY_REVIEW: "Regulatory review",
  CASE_REVIEW: "Review",
  BRIEF: "Decision Brief",
  DECISION_BRIEF: "Decision Brief",
  BRIEF_VERSION: "Decision Brief",
  DECISION_BRIEF_VERSION: "Decision Brief",
  TASK: "Task",
  FOLLOW_UP: "Follow-up",
  DECISION_FOLLOW_UP: "Follow-up",
  IMPACT: "Impact assessment",
  IMPACT_ASSESSMENT: "Impact assessment",
  REQUEST: "Evidence request",
  EVIDENCE_REQUEST: "Evidence request",
  EVIDENCE: "Evidence",
  EVIDENCE_ITEM: "Evidence",
  CASE_EVIDENCE: "Evidence",
  HYPOTHESIS: "Hypothesis",
  UNKNOWN: "Unknown",
  SCOPE: "Scope",
  SCOPE_VERSION: "Scope",
  CASE: "Case",
  INVESTIGATION: "Case",
  SIGNATURE: "Signature",
  AI_RUN: "AI run",
  AI_EXECUTION: "AI run",
  COMPLAINT: "Complaint",
};

export function objectTypeLabel(value: unknown): string {
  const type = code(value);
  return OBJECT_TYPES[type] ?? (type ? titleCase(type) : "Record");
}

/** Where a record named by an event opens, or null when no screen shows it. */
export function objectTarget(object: TimelineObject | undefined): ObjectTarget | null {
  const row = record(object);
  const type = code(row.type);
  const id = idText(row.id);
  const business = safeText(row.business_id);
  const reference = id ?? business;
  switch (type) {
    case "DECISION":
      return id ? { kind: "decision", id } : null;
    case "SIGNAL": {
      const signal = business ?? id;
      return signal ? { kind: "section", section: "Signals", tab: signalsTab({ signal }) } : null;
    }
    case "REVIEW":
    case "RISK_REVIEW":
    case "REGULATORY_REVIEW":
    case "CASE_REVIEW":
      return { kind: "section", section: "Investigations", tab: reviewsTab(reference) };
    case "BRIEF":
    case "DECISION_BRIEF":
    case "BRIEF_VERSION":
    case "DECISION_BRIEF_VERSION":
      return { kind: "section", section: "Investigations", tab: "Decision Brief" };
    case "TASK":
      return { kind: "section", section: "My Work" };
    case "FOLLOW_UP":
    case "DECISION_FOLLOW_UP":
      return { kind: "section", section: "Investigations", tab: decisionTab({ followUp: reference }) };
    case "IMPACT":
    case "IMPACT_ASSESSMENT":
      return { kind: "section", section: "Investigations", tab: decisionTab({ assessment: reference }) };
    case "REQUEST":
    case "EVIDENCE_REQUEST":
      return reference && REF.test(reference)
        ? {
            kind: "section",
            section: "My Work",
            tab: `Evidence requests?${new URLSearchParams({ request: reference })}`,
          }
        : { kind: "section", section: "My Work", tab: "Evidence requests" };
    case "EVIDENCE":
    case "EVIDENCE_ITEM":
    case "CASE_EVIDENCE":
      return { kind: "section", section: "Evidence", tab: "Case evidence" };
    case "HYPOTHESIS":
      return { kind: "section", section: "Investigations", tab: intelligenceTab("Hypotheses") };
    case "UNKNOWN":
      return { kind: "section", section: "Investigations", tab: intelligenceTab("Unknowns") };
    case "SCOPE":
    case "SCOPE_VERSION":
      return { kind: "section", section: "Investigations", tab: "Scope" };
    case "CASE":
    case "INVESTIGATION":
      return { kind: "section", section: "Investigations", tab: "Workspace" };
    default:
      return null;
  }
}

/** The record an event names: its business ID (never a UUID), its kind, and where it opens. */
export function eventObject(event: Pick<TimelineEvent, "object"> | null | undefined): {
  label: string;
  typeLabel: string;
  target: ObjectTarget | null;
} | null {
  const row = record(event?.object);
  if (!Object.keys(row).length) return null;
  const typeLabel = objectTypeLabel(row.type);
  const business = safeText(row.business_id);
  if (!business && !idText(row.id)) return null;
  return { label: business ?? typeLabel, typeLabel, target: objectTarget(row) };
}

/** Whether an event matches a search: its title, code, category, actor, role, record ID or reason. */
export function eventMatches(event: TimelineEvent, query: string): boolean {
  const wanted = query.trim().toLowerCase();
  if (!wanted) return true;
  const actor = eventActor(event);
  const object = eventObject(event);
  return [
    eventTitle(event),
    safeText(event.event),
    categoryLabel(event.category),
    actor.name,
    actor.role,
    object?.label,
    object?.typeLabel,
    safeText(event.reason),
    originView(event).label,
  ].some((value) => typeof value === "string" && value.toLowerCase().includes(wanted));
}

export type TimelineFilters = { categories: string[]; actor: string; since: string; until: string; search: string };

export const EMPTY_TIMELINE_FILTERS: TimelineFilters = { categories: [], actor: "", since: "", until: "", search: "" };

export const TIMELINE_PAGE_SIZE = 50;

const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** The date range's problem, if any: an unreadable day, or a start after the end. */
export function dateRangeProblem(filters: Pick<TimelineFilters, "since" | "until">): string | null {
  const since = filters.since.trim();
  const until = filters.until.trim();
  if ((since && !DAY.test(since)) || (until && !DAY.test(until))) return "Enter the dates as day, month and year.";
  if (since && until && since > until) return "The start date is after the end date.";
  return null;
}

/**
 * The timeline query for filters and a page: the chosen categories (types), the actor, and the days as whole UTC days
 * (from the start of the first day to the end of the last). Search is applied to the page shown, not sent.
 */
export function timelineQuery(filters: TimelineFilters, page = 1, pageSize = TIMELINE_PAGE_SIZE): string {
  const params = new URLSearchParams();
  const types = filters.categories.map(code).filter(Boolean);
  if (types.length) params.set("types", [...new Set(types)].join(","));
  if (filters.actor.trim()) params.set("actor", filters.actor.trim());
  if (DAY.test(filters.since.trim())) params.set("since", `${filters.since.trim()}T00:00:00Z`);
  if (DAY.test(filters.until.trim())) params.set("until", `${filters.until.trim()}T23:59:59Z`);
  params.set("page", String(Math.max(1, Math.floor(page) || 1)));
  params.set("page_size", String(pageSize));
  return params.toString();
}

export const timelinePath = (investigationId: string, filters: TimelineFilters, page = 1) =>
  `${trustPath(investigationId, "timeline")}?${timelineQuery(filters, page)}`;

/** A category chip turned on or off. */
export function toggleCategory(selected: string[], category: string): string[] {
  const value = code(category);
  return selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value];
}

export type CategoryChip = { code: string; label: string; count: number | null; selected: boolean };

/**
 * The category chips: each category with events (in the timeline's order, unknown ones after), with its count, and
 * any chosen category even when it has none. Without counts every known category is offered.
 */
export function categoryChips(counts: unknown, selected: string[]): CategoryChip[] {
  const given = record(counts);
  const known = Object.keys(given).length > 0;
  const tally = new Map<string, number>();
  for (const [key, value] of Object.entries(given)) {
    const count = numberOf(value);
    if (count !== null) tally.set(code(key), (tally.get(code(key)) ?? 0) + count);
  }
  const order = [...TIMELINE_CATEGORIES, ...[...tally.keys()].filter((key) => !isCategory(key)).sort()];
  return order
    .filter((key) => !known || (tally.get(key) ?? 0) > 0 || selected.includes(key))
    .map((key) => ({
      code: key,
      label: categoryLabel(key),
      count: known ? (tally.get(key) ?? 0) : null,
      selected: selected.includes(key),
    }));
}

/**
 * The counts the chips show. The server counts only the events that match the filters, categories included; so a
 * chosen category shows its current count and the others keep the count from before any category was chosen, and
 * every chip stays available to add.
 */
export function chipCounts(
  base: Record<string, number> | null | undefined,
  current: Record<string, number> | null | undefined,
  selected: string[],
): Record<string, number> | null {
  if (!selected.length) return current ?? base ?? null;
  if (!base && !current) return null;
  const result: Record<string, number> = {};
  for (const [key, value] of Object.entries(base ?? {})) result[code(key)] = value;
  for (const key of selected) result[code(key)] = numberOf(record(current)[key]) ?? 0;
  return result;
}

/** The people seen so far (for the actor filter), sorted, without repeats. */
export function actorOptions(previous: readonly string[], events: readonly TimelineEvent[]): string[] {
  const names = new Set(previous);
  for (const event of events) {
    const name = safeText(record(event?.actor).name);
    if (name) names.add(name);
  }
  return [...names].sort((a, b) => a.localeCompare(b));
}

export const pageCount = (total: unknown, pageSize = TIMELINE_PAGE_SIZE) => {
  const count = numberOf(total) ?? 0;
  return Math.max(1, Math.ceil(count / pageSize));
};

// ---------------------------------------------------------------------------------------------------------------
// Replay (GET …/trust/replay), read defensively

export type ReplayResponse = {
  as_known_at?: string | null;
  decision?: {
    business_id?: string | null;
    outcome?: string | null;
    outcome_label?: string | null;
    decided_at?: string | null;
    signer?: unknown;
  } | null;
  snapshot?: Record<string, unknown> | null;
  complaints?: unknown;
  evidence?: unknown;
  hypotheses?: unknown;
  unknowns?: unknown;
  reviews?: unknown;
  brief?: Record<string, unknown> | null;
  integrity?: {
    evidence_set_hash_then?: string | null;
    evidence_set_hash_now?: string | null;
    changed_since?: boolean | null;
  } | null;
  limitations?: unknown;
};

/** The replay address: as known when a decision was signed, or at a moment (an ISO time). Null without either. */
export function replayPath(
  investigationId: string,
  target: { decisionId?: string | null; asKnownAt?: string | null },
): string | null {
  const params = new URLSearchParams();
  const decision = idText(target.decisionId);
  const moment = idText(target.asKnownAt);
  if (decision) params.set("decision_id", decision);
  else if (moment) params.set("as_known_at", moment);
  else return null;
  return `${trustPath(investigationId, "replay")}?${params}`;
}

/**
 * Records split into what was known at the moment and what arrived later: from `{known_then, arrived_later}`, or
 * from a plain list whose items say `arrived_later: true` (or `known_then: false`).
 */
export function knownSplit(value: unknown): { knownThen: unknown[]; arrivedLater: unknown[] } {
  if (Array.isArray(value)) {
    const later = (item: unknown) => record(item).arrived_later === true || record(item).known_then === false;
    return { knownThen: value.filter((item) => !later(item)), arrivedLater: value.filter(later) };
  }
  const row = record(value);
  return { knownThen: list(row.known_then ?? row.known), arrivedLater: list(row.arrived_later ?? row.later) };
}

const ITEM_TEXT_KEYS = [
  "title",
  "label",
  "statement",
  "name",
  "summary",
  "description",
  "question",
  "text",
  "review_type_label",
];
// The status a replayed record had then, as the server labels it.
const ITEM_STATUS_KEYS = ["status_label", "human_status_label", "review_status_label", "outcome_label"];

/** How a replayed record reads: its business ID, else its own words, else "Recorded item". */
export function replayItem(item: unknown): {
  label: string;
  detail: string | null;
  status: string | null;
  at: string | null;
} {
  if (typeof item === "string" || typeof item === "number")
    return { label: String(item), detail: null, status: null, at: null };
  const row = record(item);
  const text = ITEM_TEXT_KEYS.map((key) => safeText(row[key])).find(Boolean) ?? null;
  const business = safeText(row.business_id);
  const at =
    safeText(row.known_at) ?? safeText(row.received_at) ?? safeText(row.recorded_at) ?? safeText(row.created_at);
  const status =
    ITEM_STATUS_KEYS.map((key) => safeText(row[key])).find(Boolean) ??
    sentence(row.status) ??
    sentence(row.severity) ??
    null;
  if (business) return { label: business, detail: text, status, at };
  return { label: text ?? "Recorded item", detail: null, status, at };
}

export const replayList = (value: unknown): unknown[] => list(value);

/** Whether the evidence set changed since the moment replayed, with both fingerprints. */
export function replayIntegrity(integrity: ReplayResponse["integrity"] | unknown): {
  state: "changed" | "unchanged" | "unknown";
  tone: Tone;
  headline: string;
  then: string | null;
  now: string | null;
} {
  const row = record(integrity);
  const then = idText(row.evidence_set_hash_then);
  const now = idText(row.evidence_set_hash_now);
  const changed =
    typeof row.changed_since === "boolean" ? row.changed_since : then && now ? then !== now : (null as boolean | null);
  if (changed === true)
    return {
      state: "changed",
      tone: "warning",
      headline: "Yes, the evidence set changed since then. What arrived later is listed separately below.",
      then,
      now,
    };
  if (changed === false)
    return { state: "unchanged", tone: "good", headline: "No, the evidence set is unchanged since then.", then, now };
  return {
    state: "unknown",
    tone: "neutral",
    headline: "Not checked: no evidence fingerprint was recorded for that moment.",
    then,
    now,
  };
}

/** The signer of a replayed decision as words (a name, or a name and role). */
export function signerText(value: unknown): string | null {
  if (typeof value === "string") return safeText(value);
  const row = record(value);
  const name = safeText(row.name) ?? safeText(row.signer_name);
  const role = roleText(row.role_label) ?? roleText(row.role);
  if (!name) return role;
  return role ? `${name} (${role})` : name;
}

/** A replay decision choice: every decision of the case, the current one first, superseded ones marked. */
export function replayDecisionOptions(history: readonly HistoryRow[]): Array<{ id: string; label: string }> {
  return history
    .filter((row) => !!row.id)
    .map((row) => ({
      id: String(row.id),
      label: `${row.businessId} · ${row.outcome}${row.current ? " · current" : row.status === "Superseded" ? " · superseded" : ""}`,
    }));
}

const pad = (value: number) => String(value).padStart(2, "0");

/** An ISO time as the value of a date-time field (local time, to the minute); empty when unreadable. */
export function localInputValue(iso: string | null | undefined): string {
  const time = Date.parse(String(iso ?? ""));
  if (Number.isNaN(time)) return "";
  const date = new Date(time);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** A date-time field's value (local time) as an ISO time, or null when it is not a full date and time. */
export function isoFromLocalInput(value: string | null | undefined): string | null {
  const text = String(value ?? "").trim();
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(text)) return null;
  const time = new Date(text).getTime();
  return Number.isNaN(time) ? null : new Date(time).toISOString();
}

// ---------------------------------------------------------------------------------------------------------------
// AI runs (GET …/trust/ai-runs), read defensively

export type AiRun = {
  business_id?: string | null;
  kind?: string | null;
  kind_label?: string | null;
  provider?: string | null;
  model?: string | null;
  model_version?: string | null;
  prompt_version?: string | null;
  prompt_template_version?: string | null;
  orchestration_version?: string | null;
  context_hash?: string | null;
  status?: string | null;
  guardrails?: unknown;
  execution_timestamp?: string | null;
  duration?: unknown;
  duration_ms?: unknown;
  started_at?: string | null;
  finished_at?: string | null;
  tokens?: unknown;
  input_tokens?: unknown;
  output_tokens?: unknown;
  cost?: unknown;
  estimated_cost?: unknown;
  human_review?: { status?: string | null; by?: string | null; at?: string | null } | null;
  used_in_signed_decision?: boolean | null;
};

export type AiRunsResponse = { items?: AiRun[] | null; counts?: Record<string, number> | null };

export function aiRunKindLabel(run: Pick<AiRun, "kind" | "kind_label"> | null | undefined): string {
  const kind = code(run?.kind);
  if (kind === "ASK") return "Ask MDARIX question";
  return safeText(run?.kind_label) ?? sentence(kind) ?? "AI run";
}

const RUN_STATUS: Record<string, { label: string; tone: Tone }> = {
  SUCCEEDED: { label: "Completed", tone: "good" },
  SUCCESS: { label: "Completed", tone: "good" },
  COMPLETED: { label: "Completed", tone: "good" },
  OK: { label: "Completed", tone: "good" },
  VALID: { label: "Completed", tone: "good" },
  PASSED: { label: "Completed", tone: "good" },
  FAILED: { label: "Failed", tone: "critical" },
  ERROR: { label: "Failed", tone: "critical" },
  BLOCKED: { label: "Blocked by a guardrail", tone: "serious" },
  REFUSED: { label: "Blocked by a guardrail", tone: "serious" },
  REJECTED: { label: "Blocked by a guardrail", tone: "serious" },
  RUNNING: { label: "Running", tone: "warning" },
  PENDING: { label: "Waiting", tone: "warning" },
  QUEUED: { label: "Waiting", tone: "warning" },
  FALLBACK: { label: "Rules used instead", tone: "warning" },
};

export function aiRunStatus(status: unknown): { label: string; tone: Tone } {
  const value = code(status);
  return RUN_STATUS[value] ?? { label: value ? titleCase(value) : "Not recorded", tone: "neutral" };
}

export type GuardrailItem = { key: string; label: string; ok: boolean | null; detail: string | null };

const PASS = ["PASS", "PASSED", "OK", "TRUE", "ENFORCED", "VALID", "SATISFIED", "ENABLED", "ON"];
const FAIL = ["FAIL", "FAILED", "BLOCKED", "VIOLATED", "FALSE", "INVALID", "TRIGGERED", "REJECTED"];

const passState = (value: unknown): boolean | null => {
  if (typeof value === "boolean") return value;
  const text = code(value);
  if (PASS.includes(text)) return true;
  if (FAIL.includes(text)) return false;
  return null;
};

/**
 * The summary form of a run's guardrails ({checks, passed, failed: [names], rejected_items, dropped_statements,
 * error}), or null when the value is not in that form.
 */
export function guardrailReport(
  value: unknown,
): { checks: number; passed: number; failed: string[]; extras: string[]; error: string | null } | null {
  const row = record(value);
  if (!Array.isArray(row.failed) || numberOf(row.checks) === null) return null;
  const failed = row.failed.map((name) => sentence(name) ?? String(name)).filter(Boolean);
  const rejected = numberOf(row.rejected_items) ?? 0;
  const dropped = numberOf(row.dropped_statements) ?? 0;
  const error = safeText(row.error);
  const extras = [
    rejected ? `${rejected} ${rejected === 1 ? "item" : "items"} rejected` : null,
    dropped ? `${dropped} ${dropped === 1 ? "statement" : "statements"} dropped` : null,
    error ? `Error: ${error}` : null,
  ].filter((item): item is string => !!item);
  return { checks: numberOf(row.checks) ?? 0, passed: numberOf(row.passed) ?? 0, failed, extras, error };
}

/** The guardrails of a run, from a list ({name, status|passed, detail}) or an object ({name: status}). */
export function guardrailItems(value: unknown): GuardrailItem[] {
  const report = guardrailReport(value);
  if (report)
    return [
      ...report.failed.map((name, index) => ({ key: `failed-${index}`, label: name, ok: false, detail: null })),
      ...(report.passed > 0
        ? [
            {
              key: "passed",
              label: `${report.passed} ${report.passed === 1 ? "check" : "checks"} passed`,
              ok: true,
              detail: null,
            },
          ]
        : []),
      ...report.extras.map((text, index) => ({ key: `extra-${index}`, label: text, ok: null, detail: null })),
    ];
  if (Array.isArray(value))
    return value.map((item, index) => {
      if (typeof item === "string")
        return { key: `${item}-${index}`, label: sentence(item) ?? item, ok: null, detail: null };
      const row = record(item);
      const name = safeText(row.name) ?? safeText(row.key) ?? safeText(row.code) ?? `guardrail-${index + 1}`;
      const ok = passState(row.passed ?? row.ok ?? row.status ?? row.result);
      return {
        key: `${name}-${index}`,
        label: safeText(row.label) ?? sentence(name) ?? name,
        ok,
        detail: safeText(row.detail) ?? safeText(row.message) ?? safeText(row.reason),
      };
    });
  return Object.entries(record(value)).map(([name, raw]) => {
    const row = record(raw);
    const nested = Object.keys(row).length > 0;
    const ok = passState(nested ? (row.passed ?? row.ok ?? row.status ?? row.result) : raw);
    return {
      key: name,
      label: sentence(name) ?? name,
      ok,
      detail: nested
        ? (safeText(row.detail) ?? safeText(row.message))
        : ok === null && safeText(raw)
          ? sentence(raw)
          : null,
    };
  });
}

/** One line for the guardrails of a run: all passed, which failed, or not reported. */
export function guardrailSummary(value: unknown): { text: string; tone: Tone } {
  const report = guardrailReport(value);
  if (report) {
    const extras = report.extras.length ? ` · ${report.extras.join(" · ")}` : "";
    if (report.failed.length)
      return {
        text: `${report.failed.length} of ${Math.max(report.checks, report.failed.length)} failed: ${report.failed.join(", ")}${extras}`,
        tone: "critical",
      };
    if (report.checks > 0)
      return { text: `All ${report.checks} passed${extras}`, tone: report.extras.length ? "warning" : "good" };
    return report.extras.length
      ? { text: report.extras.join(" · "), tone: "warning" }
      : { text: "Not reported", tone: "neutral" };
  }
  const items = guardrailItems(value);
  if (!items.length) return { text: "Not reported", tone: "neutral" };
  const failed = items.filter((item) => item.ok === false);
  if (failed.length)
    return {
      text: `${failed.length} of ${items.length} failed: ${failed.map((item) => item.label).join(", ")}`,
      tone: "critical",
    };
  const passed = items.filter((item) => item.ok === true).length;
  if (passed === items.length) return { text: `All ${items.length} passed`, tone: "good" };
  return { text: `${passed} of ${items.length} passed, ${items.length - passed} not reported`, tone: "warning" };
}

/** The model as people read it: "model · version 2025-01" (and its provider when known). */
export function aiModelText(run: Pick<AiRun, "model" | "model_version" | "provider"> | null | undefined): string {
  const model = safeText(run?.model);
  const version = safeText(run?.model_version);
  const provider = safeText(run?.provider);
  const name = model ? (version ? `${model} · version ${version}` : model) : version ? `version ${version}` : null;
  if (!name) return provider ?? "Not recorded";
  return provider ? `${name} (${provider})` : name;
}

/** The prompt and orchestration versions of a run, as one line. */
export function aiVersionText(
  run: Pick<AiRun, "prompt_version" | "prompt_template_version" | "orchestration_version"> | null | undefined,
): string {
  const prompt = safeText(run?.prompt_version) ?? safeText(run?.prompt_template_version);
  const orchestration = safeText(run?.orchestration_version);
  const parts = [prompt ? `Prompt ${prompt}` : null, orchestration ? `Orchestration ${orchestration}` : null].filter(
    Boolean,
  );
  return parts.length ? parts.join(" · ") : "Not recorded";
}

/** A run's duration (milliseconds when a number) as words; null when not recorded. */
export function durationText(value: unknown): string | null {
  const ms = numberOf(value);
  if (ms === null) return safeText(value);
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  return seconds < 60 ? `${seconds.toFixed(1)} s` : `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}

/** Tokens and cost of a run, when the server reports them; null when it reports neither. */
export function usageText(
  run: Pick<AiRun, "tokens" | "cost" | "input_tokens" | "output_tokens" | "estimated_cost"> | null | undefined,
): string | null {
  const parts: string[] = [];
  const tokenRow = record(run?.tokens);
  const input = numberOf(tokenRow.input) ?? numberOf(run?.input_tokens);
  const output = numberOf(tokenRow.output) ?? numberOf(run?.output_tokens);
  const tokens =
    numberOf(run?.tokens) ??
    numberOf(tokenRow.total) ??
    (input !== null || output !== null ? (input ?? 0) + (output ?? 0) : null);
  if (tokens !== null) parts.push(`${tokens.toLocaleString("en-US")} tokens`);
  const costRow = record(run?.cost);
  const amount = numberOf(run?.cost) ?? numberOf(costRow.amount) ?? numberOf(run?.estimated_cost);
  const currency = safeText(costRow.currency);
  if (amount !== null) parts.push(currency ? `${amount.toFixed(4)} ${currency}` : `cost ${amount.toFixed(4)}`);
  else if (typeof run?.cost === "string" && safeText(run.cost)) parts.push(`cost ${run.cost}`);
  return parts.length ? parts.join(" · ") : null;
}

/** Whether a person reviewed the run's output: reviewed (by whom), rejected, or not reviewed. */
export function humanReviewView(review: AiRun["human_review"] | unknown): {
  label: string;
  tone: Tone;
  by: string | null;
  at: string | null;
} {
  const row = record(review);
  const status = code(row.status);
  const by = safeText(row.by);
  const at = safeText(row.at);
  if (["REVIEWED", "ACCEPTED", "APPROVED", "ADOPTED", "CONFIRMED"].includes(status))
    return { label: by ? `Reviewed by ${by}` : "Reviewed by a person", tone: "good", by, at };
  if (["REJECTED", "DISMISSED", "DISCARDED"].includes(status))
    return { label: by ? `Rejected by ${by}` : "Rejected by a person", tone: "serious", by, at };
  if (["EDITED", "MODIFIED", "CORRECTED"].includes(status))
    return { label: by ? `Edited by ${by}` : "Edited by a person", tone: "good", by, at };
  if (!status || ["PENDING", "NOT_REVIEWED", "NONE", "UNREVIEWED"].includes(status))
    return { label: "Not reviewed by a person", tone: "warning", by, at };
  return { label: titleCase(status), tone: "neutral", by, at };
}

/** The run counts as a line ("Completed 3 · Failed 1"); null without counts. */
export function aiRunCountsText(counts: unknown): string | null {
  const parts = Object.entries(record(counts))
    .map(([key, value]) => [key, numberOf(value)] as const)
    .filter(([, value]) => value !== null)
    .map(([key, value]) => `${sentence(code(key)) ?? key} ${value}`);
  return parts.length ? parts.join(" · ") : null;
}

// ---------------------------------------------------------------------------------------------------------------
// Integrity (GET …/trust/integrity), read defensively

export type IntegrityResponse = {
  signatures?: unknown;
  audit_chain?: {
    status?: string | null;
    checked_events?: number | null;
    first_break?: unknown;
    reason?: string | null;
  } | null;
  brief_hashes?: unknown;
};

export type SignatureRow = {
  key: string;
  businessId: string;
  decisionBusinessId: string | null;
  decisionId: string | null;
  valid: boolean | null;
  label: string;
  tone: Tone;
  failed: VerificationCheck[];
};

const checksOf = (value: unknown): VerificationCheck[] => {
  if (Array.isArray(value)) return verificationChecks(value);
  return Object.entries(record(value)).map(([key, raw]) => {
    const row = record(raw);
    const nested = Object.keys(row).length > 0;
    return {
      key,
      label: (nested ? safeText(row.label) : null) ?? verificationChecks([{ key }])[0].label,
      ok: (nested ? passState(row.ok ?? row.passed ?? row.status) : passState(raw)) === true,
      detail: nested ? safeText(row.detail) : null,
    };
  });
};

/**
 * The signature checks: Valid, or Invalid with the checks that failed, and the decision each one signs (its id from
 * the row, else found by business ID among the case's decisions, so its signed record can be opened).
 */
export function signatureRows(value: unknown, history: readonly HistoryRow[] = []): SignatureRow[] {
  return list(value).map((item, index) => {
    const row = record(item);
    const status = code(row.status);
    const checks = checksOf(row.checks);
    const failed = checks.filter((check) => !check.ok);
    const valid = status === "VALID" ? true : status === "INVALID" ? false : null;
    const decisionBusinessId = safeText(row.decision_business_id);
    const fromHistory = decisionBusinessId
      ? history.find((entry) => entry.businessId === decisionBusinessId)?.id
      : null;
    return {
      key: `${safeText(row.business_id) ?? "signature"}:${index}`,
      businessId: safeText(row.business_id) ?? "Signature",
      decisionBusinessId,
      decisionId: idText(row.decision_id) ?? fromHistory ?? null,
      valid,
      label: valid === true ? "Valid" : valid === false ? "Invalid" : status ? titleCase(status) : "Not checked",
      tone: valid === true ? "good" : valid === false ? "critical" : "neutral",
      failed,
    };
  });
}

/** Where a break in the audit chain was found, as words. */
function breakText(value: unknown): string | null {
  if (typeof value === "string" || typeof value === "number") return safeText(value);
  const row = record(value);
  const parts = [
    safeText(row.business_id) ?? safeText(row.event_business_id),
    sentence(row.event) ?? sentence(row.action),
    safeText(row.plane) ? `${sentence(row.plane)} records` : null,
    safeText(row.sequence ?? row.seq) ? `event ${row.sequence ?? row.seq}` : null,
    safeText(row.at) ?? safeText(row.created_at),
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

/** The audit chain: Verified (with the events checked), Break found at …, or Not checked with the reason. */
export function auditChainView(chain: IntegrityResponse["audit_chain"] | unknown): {
  state: "verified" | "broken" | "unchecked";
  label: string;
  tone: Tone;
  detail: string | null;
} {
  const row = record(chain);
  const status = code(row.status);
  const checked = numberOf(row.checked_events);
  const where = breakText(row.first_break);
  if (status === "BROKEN" || status === "INVALID" || status === "BREAK" || status === "FAILED" || where)
    return {
      state: "broken",
      label: where ? `Break found at ${where}` : "Break found",
      tone: "critical",
      detail: "An audit event no longer matches the chain. Report this to your administrator.",
    };
  if (["VERIFIED", "VALID", "OK", "INTACT", "PASS"].includes(status))
    return {
      state: "verified",
      label: "Verified",
      tone: "good",
      detail: checked !== null ? `${checked} ${checked === 1 ? "event" : "events"} checked, none changed.` : null,
    };
  return {
    state: "unchecked",
    label: "Not checked",
    tone: "neutral",
    detail: sentence(row.reason) ?? "The audit chain of this case was not checked.",
  };
}

/** The brief versions and whether each still matches the fingerprint taken when it was approved. */
export function briefHashRows(value: unknown): Array<{
  key: string;
  businessId: string;
  version: string | null;
  label: string;
  tone: Tone;
}> {
  return list(value).map((item, index) => {
    const row = record(item);
    const state = hashState({ hash_verified: typeof row.hash_verified === "boolean" ? row.hash_verified : null });
    return {
      key: `${safeText(row.business_id) ?? "brief"}:${safeText(row.version) ?? index}:${index}`,
      businessId: safeText(row.business_id) ?? "Decision Brief",
      version: safeText(row.version),
      label: state.label,
      tone: state.tone,
    };
  });
}

/** One headline for every integrity check of the case. */
export function integrityHeadline(data: IntegrityResponse | null | undefined): { label: string; tone: Tone } {
  const signatures = signatureRows(data?.signatures);
  const chain = auditChainView(data?.audit_chain);
  const briefs = briefHashRows(data?.brief_hashes);
  const problems =
    signatures.filter((row) => row.valid === false).length +
    (chain.state === "broken" ? 1 : 0) +
    briefs.filter((row) => row.tone === "critical").length;
  if (problems)
    return { label: `${problems} integrity ${problems === 1 ? "problem" : "problems"} found`, tone: "critical" };
  const unchecked =
    signatures.filter((row) => row.valid === null).length +
    (chain.state === "unchecked" ? 1 : 0) +
    briefs.filter((row) => row.tone === "neutral").length;
  if (!signatures.length && !briefs.length && chain.state === "unchecked")
    return { label: "Nothing checked yet", tone: "neutral" };
  return unchecked
    ? { label: "No problem found; some checks were not made", tone: "warning" }
    : { label: "Every check passed", tone: "good" };
}
