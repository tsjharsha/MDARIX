// Pure rules for Records › Effectiveness checks: what the board asks the server for, how a CAPA's check stands, how
// the complaint recurrence reads, and what a plan and a signed result send and when they may be sent. The server
// (/api/v1/capas/.../effectiveness, backend/app/capa_effectiveness) decides every action; a person signs the result.
import type { Tone } from "../admin/console/dashboardModel";
import { collapsed } from "./complaintReview";
import { timeLeft } from "../../app/dates";

export const RECORDS_TABS = ["Effectiveness checks", "Risk file input"] as const;
export type RecordsTab = (typeof RECORDS_TABS)[number];

/** The effectiveness board's regulatory basis (catalog ids): corrective action, verified to be effective. */
export const EFFECTIVENESS_BASIS: readonly string[] = ["ISO13485_8_5_2"];

export const EFFECTIVENESS_LIMITS = {
  criteriaMin: 10,
  criteriaMax: 2000,
  summaryMin: 10,
  summaryMax: 4000,
  reasonMin: 10,
  dueSoonDays: 14,
};

export type EffectivenessState = "OVERDUE" | "DUE_SOON" | "NOT_PLANNED" | "NOT_EFFECTIVE" | "SCHEDULED" | "EFFECTIVE";

export type CheckRound = {
  id: string;
  round: number;
  status: "PLANNED" | "EFFECTIVE" | "NOT_EFFECTIVE";
  criteria: string;
  planned_on: string;
  measured_from: string;
  plan_version: number;
  planned_by: string;
  planned_at: string | null;
  result_summary: string | null;
  evidence: Partial<Recurrence>;
  signed_by: string | null;
  signer_role: string | null;
  signed_at: string | null;
  content_fingerprint: string | null;
};

export type CapaItem = {
  capa: {
    id: string;
    business_id: string | null;
    capa_identifier: string | null;
    title: string;
    status: string | null;
    action_type: string | null;
    source_system: string | null;
    qms_reference?: string | null;
    opened_on: string | null;
    due_on: string | null;
    closed: boolean;
    product_id: string | null;
    product_name: string | null;
    investigation: { id: string; business_id: string | null } | null;
  };
  state: EffectivenessState;
  planned_on: string | null;
  plan_source: "MDARIX" | "SOURCE_SYSTEM" | null;
  days_left: number | null;
  closed_without_check: boolean;
  check: CheckRound | null;
};

export type Recurrence = {
  available: boolean;
  reason?: string;
  product_id: string | null;
  problem_codes: string[];
  measured_from?: string;
  measured_to?: string;
  before?: { complaints: number; days: number; per_30_days: number };
  since?: { complaints: number; days: number; per_30_days: number };
  direction?: "FEWER" | "SAME" | "MORE" | "NONE";
  too_early?: boolean;
  note?: string;
};

export type CapaDetail = CapaItem & {
  excluded: boolean;
  rounds: CheckRound[];
  recurrence: Recurrence;
  suggestion: { criteria: string; planned_on: string; measured_from: string };
  can_plan: boolean;
  can_sign: boolean;
};

export type BoardSummary = {
  capas: number;
  not_planned: number;
  closed_without_check: number;
  overdue: number;
  due_soon: number;
  scheduled: number;
  effective: number;
  not_effective: number;
  date_from_source: number;
};

export type Board = {
  summary: BoardSummary;
  show: BoardShow;
  total: number;
  page: number;
  page_size: number;
  pages: number;
  truncated: boolean;
  items: CapaItem[];
};

export const BOARD_SHOWS = [
  { value: "attention", label: "Needs attention" },
  { value: "scheduled", label: "Scheduled" },
  { value: "done", label: "Signed" },
  { value: "all", label: "All" },
] as const;
export type BoardShow = (typeof BOARD_SHOWS)[number]["value"];

export function boardPath(show: BoardShow, page: number, pageSize = 25) {
  return `/api/v1/capas/effectiveness?${new URLSearchParams({ show, page: String(page), page_size: String(pageSize) })}`;
}

export const capaPath = (id: string) => `/api/v1/capas/${encodeURIComponent(id)}/effectiveness`;

export const STATE: Record<EffectivenessState, { label: string; tone: Tone }> = {
  OVERDUE: { label: "Check overdue", tone: "critical" },
  DUE_SOON: { label: "Check due soon", tone: "warning" },
  NOT_PLANNED: { label: "No check planned", tone: "serious" },
  NOT_EFFECTIVE: { label: "Not effective", tone: "critical" },
  SCHEDULED: { label: "Scheduled", tone: "neutral" },
  EFFECTIVE: { label: "Effective", tone: "good" },
};

export const stateOf = (state: string | null | undefined) =>
  STATE[(state ?? "") as EffectivenessState] ?? { label: "—", tone: "neutral" as Tone };

const plural = (count: number, noun: string) => `${count.toLocaleString()} ${count === 1 ? noun : `${noun}s`}`;

export const capaRef = (item: Pick<CapaItem, "capa">) => item.capa.business_id || item.capa.capa_identifier || "CAPA";

/**
 * Where a CAPA stands in your QMS (J22), wherever the CAPA shows: "QMS reference CAPA-0450" once known, "To raise in
 * your QMS" for one MDARIX recorded without it yet, or null for a CAPA that came from your QMS (its ID is the QMS's).
 */
export function capaQmsText(capa: { qms_reference?: string | null; source_system?: string | null }): string | null {
  const ref = capa.qms_reference?.trim();
  if (ref) return `QMS reference ${ref}`;
  return capa.source_system === "MDARIX" ? "To raise in your QMS" : null;
}

/**
 * "10 days left", "Due today", "3 days overdue" (app/dates.ts timeLeft), or what the state says. Counted from today where the person is, from
 * the check's day, so a 90-day check reads "90 days left" just after midnight in India too (DEV-020); the server's
 * count (from the UTC date) only when there is no day.
 */
export function dueText(
  item: Pick<CapaItem, "state" | "days_left"> & Partial<Pick<CapaItem, "planned_on">>,
  now = new Date(),
): string {
  if (item.days_left === null) return stateOf(item.state).label;
  return timeLeft({ due_date: item.planned_on, days_left: item.days_left }, now);
}

export function boardHeadline(summary: BoardSummary | null | undefined): { title: string; detail: string; tone: Tone } {
  if (!summary) return { title: "Reading your CAPAs…", detail: "Every CAPA and its check.", tone: "neutral" };
  if (summary.overdue || summary.closed_without_check) {
    const parts = [
      summary.overdue ? `${plural(summary.overdue, "check")} overdue` : "",
      summary.closed_without_check
        ? `${plural(summary.closed_without_check, "CAPA")} closed without an effectiveness check`
        : "",
    ].filter(Boolean);
    return {
      title: parts.join(" · "),
      detail: "An inspector asks how you know each action worked. Plan the missing checks and sign the due ones.",
      tone: "critical",
    };
  }
  if (summary.due_soon || summary.not_planned)
    return {
      title: summary.due_soon
        ? `${plural(summary.due_soon, "check")} due within ${EFFECTIVENESS_LIMITS.dueSoonDays} days`
        : `${plural(summary.not_planned, "CAPA")} without a planned check`,
      detail: `${plural(summary.capas, "CAPA")} in all; ${plural(summary.effective, "check")} signed effective.`,
      tone: "warning",
    };
  return {
    title: summary.capas ? "Every CAPA has its effectiveness check" : "No CAPAs yet",
    detail: summary.capas
      ? `${plural(summary.effective, "check")} signed effective, ${plural(summary.scheduled, "check")} scheduled.`
      : "CAPAs opened from a signed decision or imported from your quality system appear here.",
    tone: "good",
  };
}

/** The recurrence in plain words: "3 complaints in 31 days before (2.9 per 30 days); 1 in 31 days since (1.0 per 30 days)." */
export function recurrenceText(recurrence: Partial<Recurrence> | null | undefined): string {
  if (!recurrence || recurrence.available === false || !recurrence.before || !recurrence.since)
    return recurrence?.reason ?? "Recurrence was not measured";
  const { before, since } = recurrence;
  return (
    `${plural(before.complaints, "complaint")} in ${plural(before.days, "day")} before (${before.per_30_days} per 30 days); ` +
    `${since.complaints.toLocaleString()} in ${plural(since.days, "day")} since (${since.per_30_days} per 30 days).`
  );
}

export const DIRECTION: Record<string, { label: string; tone: Tone }> = {
  FEWER: { label: "Fewer complaints since", tone: "good" },
  SAME: { label: "About the same rate", tone: "warning" },
  MORE: { label: "More complaints since", tone: "critical" },
  NONE: { label: "No complaints before or since", tone: "neutral" },
};

// The plan and the result ----------------------------------------------------------------------------------------

export type PlanForm = { criteria: string; plannedOn: string; measuredFrom: string; reason: string };

export function planForm(detail: Pick<CapaDetail, "check" | "suggestion">): PlanForm {
  const current = detail.check && detail.check.status === "PLANNED" ? detail.check : null;
  return current
    ? { criteria: current.criteria, plannedOn: current.planned_on, measuredFrom: current.measured_from, reason: "" }
    : {
        criteria: detail.suggestion.criteria,
        plannedOn: detail.suggestion.planned_on,
        measuredFrom: detail.suggestion.measured_from,
        reason: "",
      };
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Whether the form changes a plan already made (then a reason is needed). */
export const replanning = (detail: Pick<CapaDetail, "check">) => detail.check?.status === "PLANNED";

export function planProblem(form: PlanForm, detail: Pick<CapaDetail, "check">): string | null {
  const criteria = collapsed(form.criteria);
  if (criteria.length < EFFECTIVENESS_LIMITS.criteriaMin || criteria.length > EFFECTIVENESS_LIMITS.criteriaMax)
    return `Say in ${EFFECTIVENESS_LIMITS.criteriaMin} to ${EFFECTIVENESS_LIMITS.criteriaMax} characters what will show the action worked`;
  if (!DAY.test(form.plannedOn)) return "Choose the day of the check";
  if (!DAY.test(form.measuredFrom)) return "Choose the day the measurement starts";
  if (form.measuredFrom > form.plannedOn) return "The measurement starts on or before the day of the check";
  if (replanning(detail)) {
    const current = detail.check!;
    if (
      criteria === current.criteria &&
      form.plannedOn === current.planned_on &&
      form.measuredFrom === current.measured_from
    )
      return "This is already the plan";
    if (collapsed(form.reason).length < EFFECTIVENESS_LIMITS.reasonMin)
      return `Say in at least ${EFFECTIVENESS_LIMITS.reasonMin} characters why the plan changes`;
  }
  return null;
}

export function planBody(form: PlanForm, detail: Pick<CapaDetail, "check">) {
  return {
    criteria: collapsed(form.criteria),
    planned_on: form.plannedOn,
    measured_from: form.measuredFrom,
    ...(replanning(detail) ? { reason: collapsed(form.reason) } : {}),
  };
}

export type SignForm = { result: "EFFECTIVE" | "NOT_EFFECTIVE" | ""; summary: string; password: string; code: string };
export const EMPTY_SIGN: SignForm = { result: "", summary: "", password: "", code: "" };

export function signProblem(form: SignForm): string | null {
  if (!form.result) return "Choose whether the action was effective";
  const summary = collapsed(form.summary);
  if (summary.length < EFFECTIVENESS_LIMITS.summaryMin)
    return `Say in at least ${EFFECTIVENESS_LIMITS.summaryMin} characters what you found`;
  if (summary.length > EFFECTIVENESS_LIMITS.summaryMax)
    return `Keep the summary under ${EFFECTIVENESS_LIMITS.summaryMax} characters`;
  if (!form.password) return "Enter your password to sign";
  if (form.code && !/^\d{6,8}$/.test(form.code.trim())) return "The authenticator code is 6 to 8 digits";
  return null;
}

export function signBody(form: SignForm, planVersion: number) {
  return {
    result: form.result,
    summary: collapsed(form.summary),
    plan_version: planVersion,
    password: form.password,
    ...(form.code.trim() ? { mfa_code: form.code.trim() } : {}),
  };
}

/** The tab a link or a task names: "Effectiveness checks?capa=<id>" opens that CAPA's check. */
export function parseRecordsTab(tab: string | undefined): { tab: RecordsTab; capa: string | null } {
  const [name, query] = (tab ?? "").split("?");
  const capa = new URLSearchParams(query ?? "").get("capa");
  return {
    tab: (RECORDS_TABS as readonly string[]).includes(name) ? (name as RecordsTab) : "Effectiveness checks",
    capa: capa && capa.trim() ? capa.trim() : null,
  };
}

export const recordsTab = (capa?: string | null) =>
  capa ? `Effectiveness checks?${new URLSearchParams({ capa })}` : "Effectiveness checks";
