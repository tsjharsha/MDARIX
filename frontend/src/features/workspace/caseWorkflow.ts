// Pure rules for a case's workflow (Phase 3): how its state and priority read, which state changes a person is
// offered, how the case stepper and the readiness checklist read, and the person's own case summary. The server owns
// the workflow and refuses any change it does not allow; these only shape what the person sees.
import { titleCase, type Tone } from "../admin/console/dashboardModel";
import { safeText } from "../../app/displayId";
import type { WorkspaceSection } from "./workspaceContext";
import { dueState, priorityRank, reasonProblem, type DueState } from "./tasks";
import type { IntelligenceView } from "./intelligence";

export const WORKFLOW_STATES = [
  "OPEN",
  "IN_PROGRESS",
  "ON_HOLD",
  "BRIEF_IN_REVIEW",
  "READY_FOR_DECISION",
  "DECIDED",
  "CLOSED",
  "CANCELLED",
] as const;
export type WorkflowState = (typeof WORKFLOW_STATES)[number];

export const WORKFLOW_STATE_LABELS: Record<WorkflowState, string> = {
  OPEN: "Open",
  IN_PROGRESS: "In progress",
  ON_HOLD: "On hold",
  BRIEF_IN_REVIEW: "Brief in review",
  READY_FOR_DECISION: "Ready for decision",
  DECIDED: "Decided",
  CLOSED: "Closed",
  CANCELLED: "Cancelled",
};

const STATE_TONES: Record<WorkflowState, Tone> = {
  OPEN: "neutral",
  IN_PROGRESS: "warning",
  ON_HOLD: "serious",
  BRIEF_IN_REVIEW: "warning",
  READY_FOR_DECISION: "good",
  DECIDED: "good",
  CLOSED: "good",
  CANCELLED: "neutral",
};

/** States in which a case's work is over: no due date is chased and no state change is offered. */
const FINISHED_STATES: readonly string[] = ["DECIDED", "CLOSED", "CANCELLED"];

export const CASE_PRIORITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
export type CasePriority = (typeof CASE_PRIORITIES)[number];

/** The fields a case row carries about its workflow (lists, PATCH responses, the person's summary). */
export type CaseWorkflowFields = {
  status?: unknown;
  workflow_state?: unknown;
  workflow_state_label?: unknown;
  priority?: unknown;
  due_at?: unknown;
  overdue?: unknown;
};

const code = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

/** The case's workflow state code, or null when the response carries none (an older server). */
export function caseState(row: CaseWorkflowFields | null | undefined): WorkflowState | null {
  const value = code(row?.workflow_state);
  return (WORKFLOW_STATES as readonly string[]).includes(value) ? (value as WorkflowState) : null;
}

/**
 * The case's state as people read it: the server's label, else the known label for its workflow state; null when the
 * row carries no workflow state at all (then the caller shows its plain status as before).
 */
export function caseStateLabel(row: CaseWorkflowFields | null | undefined): string | null {
  const label = safeText(row?.workflow_state_label);
  if (label) return label;
  const state = caseState(row);
  if (state) return WORKFLOW_STATE_LABELS[state];
  const raw = safeText(row?.workflow_state);
  return raw ? titleCase(raw) : null;
}

/** The text a case list shows for its state: the workflow state's label, else its plain status ("open"), else "—". */
export function caseStatusText(row: CaseWorkflowFields | null | undefined, fallback = "—"): string {
  return caseStateLabel(row) ?? safeText(row?.status) ?? fallback;
}

export function caseStateTone(row: CaseWorkflowFields | null | undefined): Tone {
  const state = caseState(row);
  if (state) return STATE_TONES[state];
  return /^closed$/i.test(String(row?.status ?? "").trim()) ? "good" : "warning";
}

/** A state change offered on the case header. */
export type CaseTransition = {
  to: "IN_PROGRESS" | "ON_HOLD" | "CANCELLED";
  label: string;
  /** What the person is asked to explain before it is sent (kept in the audit trail). */
  prompt: string;
  danger?: boolean;
};

const START: CaseTransition = { to: "IN_PROGRESS", label: "Start work", prompt: "Why does work start now?" };
const RESUME: CaseTransition = { to: "IN_PROGRESS", label: "Resume", prompt: "Why can work resume?" };
const HOLD: CaseTransition = { to: "ON_HOLD", label: "Put on hold", prompt: "Why is the case put on hold?" };
const CANCEL: CaseTransition = {
  to: "CANCELLED",
  label: "Cancel case",
  prompt: "Why is the case cancelled?",
  danger: true,
};

/**
 * The state changes offered for a case in a state: Start work (open), Put on hold (in progress), Resume (on hold), and
 * Cancel while the case has not reached its brief. Start, hold and resume need investigation.work; Cancel needs
 * investigation.assign. Nothing is offered for a case without a known workflow state; the server decides either way.
 */
export function caseTransitions(
  row: CaseWorkflowFields | null | undefined,
  can: { work: boolean; assign: boolean },
): CaseTransition[] {
  const state = caseState(row);
  const work: CaseTransition[] =
    state === "OPEN" ? [START] : state === "IN_PROGRESS" ? [HOLD] : state === "ON_HOLD" ? [RESUME] : [];
  const cancellable = state === "OPEN" || state === "IN_PROGRESS" || state === "ON_HOLD";
  return [...(can.work ? work : []), ...(can.assign && cancellable ? [CANCEL] : [])];
}

export const TRANSITION_REASON_MIN = 10;
export const TRANSITION_REASON_MAX = 1000;

/** Why a state change cannot be sent yet (its reason, 10 to 1000 characters), or null when it can. */
export const transitionProblem = (reason: string) => reasonProblem(reason, true);

export const transitionPath = (investigationId: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/transition`;

export const transitionBody = (transition: Pick<CaseTransition, "to">, reason: string) => ({
  to_state: transition.to,
  reason: reason.trim(),
});

export const casePriorityLabel = (priority: unknown) => {
  const value = code(priority);
  return value ? titleCase(value) : "Not set";
};

/** How a case's due date stands; a decided, closed or cancelled case is never overdue. */
export function caseDueState(row: CaseWorkflowFields | null | undefined, now = new Date()): DueState {
  const state = caseState(row);
  if (state && FINISHED_STATES.includes(state)) return "done";
  if (!state && /^closed$/i.test(String(row?.status ?? "").trim())) return "done";
  return dueState(
    {
      due_at: typeof row?.due_at === "string" ? row.due_at : null,
      overdue: row?.overdue === true,
      status: null,
      completed_at: null,
    },
    now,
  );
}

const DAY = /^(\d{4})-(\d{2})-(\d{2})$/;

/** A due day chosen in a date field (YYYY-MM-DD) as the end of that day where the person is, in ISO form. */
export function dueAtFromDay(day: string): string | null {
  const match = DAY.exec(day.trim());
  if (!match) return null;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 23, 59, 0);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/** The local calendar day (YYYY-MM-DD) of a due date, for a date field; "" when there is none. */
export function dayFromDueAt(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "";
  if (DAY.test(value.trim())) return value.trim();
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/**
 * The planning fields of the manage PATCH that actually change: priority, and the due date (null clears it). Null when
 * nothing changed, so the button stays off.
 */
export function planningChange(
  row: CaseWorkflowFields,
  input: { priority: string; dueDay: string },
): { priority?: string; due_at?: string | null } | null {
  const change: { priority?: string; due_at?: string | null } = {};
  const priority = code(input.priority);
  if (priority && (CASE_PRIORITIES as readonly string[]).includes(priority) && priority !== code(row.priority))
    change.priority = priority;
  const before = dayFromDueAt(row.due_at);
  const after = input.dueDay.trim();
  if (after !== before) {
    if (!after) change.due_at = null;
    else {
      const iso = dueAtFromDay(after);
      if (iso) change.due_at = iso;
    }
  }
  return Object.keys(change).length ? change : null;
}

// ---------------------------------------------------------------------------------------------------------------
// The case stepper and readiness checklist (GET /api/v1/investigations/{id}/readiness)

export type StepStatus = "DONE" | "IN_PROGRESS" | "NOT_STARTED" | "BLOCKED" | "NOT_AVAILABLE";
export type CheckResult = "PASS" | "BLOCKED" | "PENDING" | "NOT_REQUIRED" | "NOT_AVAILABLE";

export type ReadinessStep = { key: string; label?: string | null; status?: string | null; detail?: string | null };
export type ReadinessCheck = { key: string; label?: string | null; result?: string | null; rationale?: string | null };
export type CaseReadiness = {
  workflow_state?: string | null;
  steps?: ReadinessStep[] | null;
  checks?: ReadinessCheck[] | null;
};

/**
 * Where a step opens: a section and tab, for the workspace panel the part of it to scroll to, and for the Intelligence
 * tab of Investigations the view to show.
 */
export type StepDestination = { section: WorkspaceSection; tab?: string; anchor?: string; view?: IntelligenceView };

export const CASE_STEPS: ReadonlyArray<{ key: string; label: string; destination: StepDestination }> = [
  {
    key: "overview",
    label: "Overview",
    destination: { section: "Investigations", tab: "Workspace", anchor: "workflow-overview" },
  },
  { key: "scope", label: "Scope", destination: { section: "Investigations", tab: "Scope" } },
  { key: "evidence", label: "Evidence", destination: { section: "Evidence", tab: "Case evidence" } },
  {
    key: "analysis",
    label: "Analysis",
    destination: { section: "Investigations", tab: "Workspace", anchor: "workflow-analysis" },
  },
  // Hypotheses and gaps are judged in the Intelligence tab (AI and hand-made side by side); the AI workspace stays
  // reachable from Analysis and from the Workspace tab.
  {
    key: "hypotheses",
    label: "Hypotheses",
    destination: { section: "Investigations", tab: "Intelligence", view: "Hypotheses" },
  },
  {
    key: "gaps",
    label: "Gaps",
    destination: { section: "Investigations", tab: "Intelligence", view: "Unknowns" },
  },
  {
    key: "risk_regulatory",
    label: "Risk & Regulatory",
    destination: { section: "Intelligence", tab: "Risk & traceability" },
  },
  {
    key: "brief",
    label: "Decision Brief",
    destination: { section: "Investigations", tab: "Workspace", anchor: "workflow-brief" },
  },
  { key: "human_review", label: "Human review", destination: { section: "Decisions", tab: "Decision center" } },
];

export const STEP_STATUS: Record<StepStatus, { label: string; tone: Tone }> = {
  DONE: { label: "Done", tone: "good" },
  IN_PROGRESS: { label: "In progress", tone: "warning" },
  NOT_STARTED: { label: "Not started", tone: "neutral" },
  BLOCKED: { label: "Blocked", tone: "critical" },
  NOT_AVAILABLE: { label: "Not available", tone: "neutral" },
};

export const CHECK_RESULT: Record<CheckResult, { label: string; tone: Tone }> = {
  PASS: { label: "Pass", tone: "good" },
  BLOCKED: { label: "Blocked", tone: "critical" },
  PENDING: { label: "Pending", tone: "warning" },
  NOT_REQUIRED: { label: "Not required", tone: "neutral" },
  // A check the organization cannot record yet (for example risk and regulatory reviews): not work anyone owes.
  NOT_AVAILABLE: { label: "Not available yet", tone: "neutral" },
};

const stepStatusOf = (value: unknown): StepStatus => {
  const status = code(value);
  return status in STEP_STATUS ? (status as StepStatus) : "NOT_AVAILABLE";
};
const checkResultOf = (value: unknown): CheckResult => {
  const result = code(value);
  return result in CHECK_RESULT ? (result as CheckResult) : "PENDING";
};

export type CaseStep = {
  key: string;
  label: string;
  status: StepStatus;
  detail: string | null;
  destination: StepDestination | null;
};

/**
 * The stepper's steps in the case's order (Overview to Human review) with the server's status for each; a step the
 * server did not report reads "Not available", and a step it reports that this screen does not know comes last.
 */
export function caseSteps(readiness: CaseReadiness | null | undefined): CaseStep[] {
  const reported = new Map((readiness?.steps ?? []).map((step) => [String(step.key ?? "").toLowerCase(), step]));
  const known = CASE_STEPS.map((step) => {
    const server = reported.get(step.key);
    return {
      key: step.key,
      label: safeText(server?.label) ?? step.label,
      status: stepStatusOf(server?.status),
      detail: safeText(server?.detail),
      destination: step.destination,
    };
  });
  const extra = (readiness?.steps ?? [])
    .filter((step) => !CASE_STEPS.some((item) => item.key === String(step.key ?? "").toLowerCase()))
    .map((step) => ({
      key: String(step.key),
      label: safeText(step.label) ?? titleCase(String(step.key ?? "Step")),
      status: stepStatusOf(step.status),
      detail: safeText(step.detail),
      destination: null,
    }));
  return [...known, ...extra];
}

export type CaseCheck = { key: string; label: string; result: CheckResult; rationale: string | null };

/** The readiness checklist: Blocked first, then Pending, Pass and Not required, each with its rationale. */
export function readinessChecks(readiness: CaseReadiness | null | undefined): CaseCheck[] {
  const order: CheckResult[] = ["BLOCKED", "PENDING", "PASS", "NOT_REQUIRED", "NOT_AVAILABLE"];
  return (readiness?.checks ?? [])
    .map((check, index) => ({
      index,
      key: String(check.key ?? index),
      label: safeText(check.label) ?? titleCase(String(check.key ?? "Check")),
      result: checkResultOf(check.result),
      rationale: safeText(check.rationale),
    }))
    .sort((a, b) => order.indexOf(a.result) - order.indexOf(b.result) || a.index - b.index)
    .map((check) => ({ key: check.key, label: check.label, result: check.result, rationale: check.rationale }));
}

/** "2 blocked · 1 pending · 5 pass · 1 not required": counts only, never a percentage. */
export function readinessHeadline(checks: CaseCheck[]): string {
  if (!checks.length) return "No readiness checks reported yet.";
  const parts = (["BLOCKED", "PENDING", "PASS", "NOT_REQUIRED", "NOT_AVAILABLE"] as CheckResult[])
    .map((result) => {
      const count = checks.filter((check) => check.result === result).length;
      return count ? `${count} ${CHECK_RESULT[result].label.toLowerCase()}` : "";
    })
    .filter(Boolean);
  return parts.join(" · ");
}

export const readinessPath = (investigationId: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/readiness`;

// ---------------------------------------------------------------------------------------------------------------
// The person's own cases (Dashboard: My investigations)

/** The summary of the cases the person works; kept in one place because its address may still change. */
export const MY_CASES_SUMMARY_PATH = "/api/v1/investigations/mine/summary";

export type MyCase = CaseWorkflowFields & {
  id: string;
  business_id?: string | null;
  question?: string | null;
  product?: { id?: string | null; business_id?: string | null; name?: string | null } | null;
  unreviewed_evidence?: number | null;
  open_requests?: number | null;
  open_unknowns?: number | null;
};

export type MyCaseCounts = Partial<
  Record<
    | "open"
    | "in_progress"
    | "on_hold"
    | "due_soon"
    | "overdue"
    | "unreviewed_evidence"
    | "requests_waiting"
    | "requests_to_review",
    number
  >
>;

export type MyCasesSummary = { cases?: MyCase[] | null; counts?: MyCaseCounts | null };

export type MyCaseTile = {
  key: keyof MyCaseCounts;
  label: string;
  value: number | null;
  urgent?: boolean;
  target: { section: WorkspaceSection; tab?: string };
};

/** The count tiles of "My investigations", each opening where that work is done. */
export function myCaseTiles(summary: MyCasesSummary | null | undefined): MyCaseTile[] {
  const counts = summary?.counts ?? {};
  const value = (key: keyof MyCaseCounts) => {
    const count = counts[key];
    return typeof count === "number" && Number.isFinite(count) ? count : null;
  };
  const cases = { section: "Investigations", tab: "All investigations" } as const;
  const requests = { section: "My Work", tab: "Evidence requests" } as const;
  return [
    { key: "in_progress", label: "In progress", value: value("in_progress"), target: cases },
    { key: "on_hold", label: "On hold", value: value("on_hold"), target: cases },
    { key: "due_soon", label: "Due soon", value: value("due_soon"), target: cases },
    { key: "overdue", label: "Overdue", value: value("overdue"), urgent: true, target: cases },
    {
      key: "unreviewed_evidence",
      label: "Evidence to review",
      value: value("unreviewed_evidence"),
      target: { section: "Evidence", tab: "Case evidence" },
    },
    { key: "requests_waiting", label: "Requests waiting", value: value("requests_waiting"), target: requests },
    {
      key: "requests_to_review",
      label: "Requests to review",
      value: value("requests_to_review"),
      urgent: true,
      target: requests,
    },
  ];
}

/** The person's cases to look at first: overdue, then by priority (critical first), then the nearest due date. */
export function rankMyCases(cases: MyCase[] | null | undefined, now = new Date()): MyCase[] {
  const due = (row: MyCase) => {
    const time = typeof row.due_at === "string" ? Date.parse(row.due_at) : Number.NaN;
    return Number.isNaN(time) ? Number.POSITIVE_INFINITY : time;
  };
  return [...(cases ?? [])]
    .map((row, index) => ({ row, index, overdue: caseDueState(row, now) === "overdue" ? 1 : 0 }))
    .sort(
      (a, b) =>
        b.overdue - a.overdue ||
        priorityRank(b.row.priority) - priorityRank(a.row.priority) ||
        due(a.row) - due(b.row) ||
        a.index - b.index,
    )
    .map((item) => item.row);
}
