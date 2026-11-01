// Pure rules for what follows a signed decision (Phase 6): the follow-up actions the decision maker required (start,
// complete, cancel, raise a CAPA), the impact assessments of evidence that arrived after the decision (no impact, or a
// material impact that reopens the case; the signed decision itself is never changed), and the closure criteria shown
// before a case is closed. The server owns all of it and refuses what it does not allow.
import { titleCase, type Tone } from "../admin/console/dashboardModel";
import { safeText } from "../../app/displayId";
import { roleLabel } from "../../app/roles";
import { dueAtFromDay } from "./caseWorkflow";
import { textProblem } from "./intelligence";
import { FOLLOW_UP_ACTION_LABELS, outcomeLabel, type FollowUpAction } from "./humanDecision";
import { capaQmsText } from "./effectiveness";
import { dueState } from "./tasks";

const code = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

// ---------------------------------------------------------------------------------------------------------------
// Follow-up actions

export type FollowUpActions = {
  can_start?: boolean | null;
  can_complete?: boolean | null;
  can_cancel?: boolean | null;
  can_create_capa?: boolean | null;
  can_set_qms_reference?: boolean | null;
};

export type FollowUp = {
  id: string;
  business_id?: string | null;
  action_type?: string | null;
  action_label?: string | null;
  title?: string | null;
  status?: string | null;
  status_label?: string | null;
  assignee?: { id?: string | null; name?: string | null } | string | null;
  assigned_role?: string | null;
  assigned_role_label?: string | null;
  due_at?: string | null;
  overdue?: boolean | null;
  decision?: { id?: string | null; business_id?: string | null; outcome?: string | null } | null;
  investigation?: { id?: string | null; business_id?: string | null; product_id?: string | null } | null;
  capa?: { business_id?: string | null; capa_identifier?: string | null; qms_reference?: string | null } | null;
  completion_note?: string | null;
  completed_by_name?: string | null;
  completed_at?: string | null;
  actions?: FollowUpActions | null;
};

export type FollowUpList = { items?: FollowUp[] | null; total?: number | null; page?: number; page_size?: number };

export const FOLLOW_UP_STATUS: Record<string, { label: string; tone: Tone }> = {
  OPEN: { label: "Open", tone: "warning" },
  IN_PROGRESS: { label: "In progress", tone: "warning" },
  DONE: { label: "Done", tone: "good" },
  CANCELLED: { label: "Cancelled", tone: "neutral" },
};

export const caseFollowUpsPath = (investigationId: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/follow-ups`;

export type FollowUpActionKey = "start" | "complete" | "cancel" | "capa";

export const followUpPath = (id: string, action?: FollowUpActionKey) =>
  `/api/v1/follow-ups/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;

/** Where the QMS reference of a follow-up's CAPA is set (J22). */
export const followUpQmsReferencePath = (id: string) => `${followUpPath(id, "capa")}/qms-reference`;
export const QMS_REFERENCE_MAX = 120;

export function followUpListPath(box: "mine" | "all" = "mine", status = "", page = 1, pageSize = 20): string {
  const params = new URLSearchParams({ box });
  if (status) params.set("status", status);
  params.set("page", String(Math.max(1, page)));
  params.set("page_size", String(pageSize));
  return `/api/v1/follow-ups?${params}`;
}

/** The kind of follow-up as people read it ("CAPA required"), never the raw code. */
export function followUpTypeLabel(item: Pick<FollowUp, "action_type" | "action_label"> | null | undefined): string {
  const given = safeText(item?.action_label);
  if (given) return given;
  const value = code(item?.action_type);
  return FOLLOW_UP_ACTION_LABELS[value as FollowUpAction] ?? (value ? titleCase(value) : "Follow-up");
}

export function followUpStatusView(item: Pick<FollowUp, "status" | "status_label"> | null | undefined) {
  const value = code(item?.status);
  const known = FOLLOW_UP_STATUS[value];
  return {
    label: safeText(item?.status_label) ?? known?.label ?? (value ? titleCase(value) : "Unknown"),
    tone: known?.tone ?? ("neutral" as Tone),
  };
}

/** Who holds the follow-up: the person, else the role, else "Unassigned". */
export function followUpAssignee(item: Pick<FollowUp, "assignee" | "assigned_role" | "assigned_role_label">): string {
  const assignee = item.assignee;
  const person = typeof assignee === "string" ? safeText(assignee) : safeText(assignee?.name);
  if (person) return person;
  const role =
    item.assigned_role || item.assigned_role_label ? roleLabel(item.assigned_role, item.assigned_role_label) : "";
  return role ? `${role} (role)` : "Unassigned";
}

/** Whether the follow-up is overdue: as the server says, or past its due date while still open. */
export function followUpOverdue(item: Pick<FollowUp, "due_at" | "overdue" | "status" | "completed_at">): boolean {
  const status = code(item.status);
  if (status === "DONE" || status === "CANCELLED") return false;
  return (
    dueState({ due_at: item.due_at ?? null, overdue: item.overdue ?? null, status: null, completed_at: null }) ===
    "overdue"
  );
}

export const FOLLOW_UP_ACTIONS_SHOWN: ReadonlyArray<{
  key: FollowUpActionKey;
  flag: keyof FollowUpActions;
  label: string;
  needsInput: boolean;
}> = [
  { key: "start", flag: "can_start", label: "Start", needsInput: false },
  { key: "complete", flag: "can_complete", label: "Complete", needsInput: true },
  { key: "capa", flag: "can_create_capa", label: "Record the CAPA to raise in your QMS", needsInput: true },
  { key: "cancel", flag: "can_cancel", label: "Cancel", needsInput: true },
];

/** The actions the server allows on this follow-up right now, in the order they are shown. */
export function followUpActions(item: Pick<FollowUp, "actions"> | null | undefined): FollowUpActionKey[] {
  return FOLLOW_UP_ACTIONS_SHOWN.filter((action) => item?.actions?.[action.flag] === true).map((action) => action.key);
}

export const FOLLOW_UP_NOTE_MIN = 10;
export const FOLLOW_UP_NOTE_MAX = 2000;
export const CAPA_TITLE_MIN = 3;
export const CAPA_TITLE_MAX = 300;

export type FollowUpInput = { text: string; dueDay?: string; qmsReference?: string };

/** Why an action cannot be sent yet, or null: a note to complete, a reason to cancel, a title for the CAPA. */
export function followUpActionProblem(key: FollowUpActionKey, input: FollowUpInput): string | null {
  switch (key) {
    case "start":
      return null;
    case "complete":
      return textProblem(input.text, "a note on what was done", { min: FOLLOW_UP_NOTE_MIN, max: FOLLOW_UP_NOTE_MAX });
    case "cancel":
      return textProblem(input.text, "the reason", { min: FOLLOW_UP_NOTE_MIN, max: FOLLOW_UP_NOTE_MAX });
    case "capa": {
      const title = textProblem(input.text, "the CAPA title", { min: CAPA_TITLE_MIN, max: CAPA_TITLE_MAX });
      if (title) return title;
      if (input.dueDay?.trim() && !dueAtFromDay(input.dueDay)) return "Choose a valid due date.";
      return null;
    }
  }
}

/** The body each action sends (none to start). */
export function followUpActionBody(key: FollowUpActionKey, input: FollowUpInput): Record<string, string> | undefined {
  const text = input.text.trim();
  switch (key) {
    case "start":
      return undefined;
    case "complete":
      return { note: text };
    case "cancel":
      return { reason: text };
    case "capa": {
      const due = input.dueDay?.trim() ? dueAtFromDay(input.dueDay) : null;
      const qms = input.qmsReference?.trim();
      return { title: text, ...(due ? { due_at: due } : {}), ...(qms ? { qms_reference: qms } : {}) };
    }
  }
}

/** Counts of a list of follow-ups: open (not done or cancelled) and overdue. */
export function followUpCounts(items: FollowUp[] | null | undefined): { open: number; overdue: number } {
  const open = (items ?? []).filter((item) => !["DONE", "CANCELLED"].includes(code(item.status)));
  return { open: open.length, overdue: open.filter((item) => followUpOverdue(item)).length };
}

/** "DEC000004 · Accept the conclusion": the decision a follow-up came from. */
export function followUpDecisionText(item: Pick<FollowUp, "decision">): string {
  const id = safeText(item.decision?.business_id);
  const outcome = item.decision?.outcome ? outcomeLabel(item.decision.outcome) : null;
  return [id, outcome].filter(Boolean).join(" · ") || "—";
}

/**
 * The CAPA recorded for a follow-up, by its business ID (and the number MDARIX gave it), then where it stands in your
 * QMS: "CAPA000001 (CAPA-INV000001-1) · To raise in your QMS"; null when none was recorded.
 */
export function followUpCapaText(item: Pick<FollowUp, "capa">): string | null {
  if (!item.capa) return null;
  const id = safeText(item.capa.business_id);
  const source = safeText(item.capa.capa_identifier);
  const name = id && source && source !== id ? `${id} (${source})` : (id ?? source);
  const qms = capaQmsText({ ...item.capa, source_system: "MDARIX" });
  return name ? `${name} · ${qms}` : null;
}

/** The follow-up a tab or task names (by id or business ID) in a list, or null. */
export function findByRef<T extends { id?: string | null; business_id?: string | null }>(
  items: T[] | null | undefined,
  ref: string | null | undefined,
): T | null {
  const wanted = String(ref ?? "").trim();
  if (!wanted) return null;
  return (
    (items ?? []).find(
      (item) =>
        String(item.id ?? "").trim() === wanted ||
        String(item.business_id ?? "")
          .trim()
          .toUpperCase() === wanted.toUpperCase(),
    ) ?? null
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Impact assessments

export type ImpactAssessment = {
  id: string;
  business_id?: string | null;
  trigger?: string | null;
  trigger_label?: string | null;
  evidence?: { business_id?: string | null; title?: string | null } | null;
  decision?: { id?: string | null; business_id?: string | null } | null;
  status?: string | null;
  status_label?: string | null;
  conclusion?: string | null;
  conclusion_label?: string | null;
  rationale?: string | null;
  assessed_by_name?: string | null;
  assessed_role?: string | null;
  assessed_at?: string | null;
  created_at?: string | null;
  actions?: { can_complete?: boolean | null } | null;
};

export const caseImpactAssessmentsPath = (investigationId: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/impact-assessments`;

export const impactCompletePath = (id: string) => `/api/v1/impact-assessments/${encodeURIComponent(id)}/complete`;

export const IMPACT_CONCLUSIONS = [
  {
    value: "NO_IMPACT",
    label: "No impact on the decision",
    description: "The new evidence does not change the signed decision. The case stays as decided.",
    tone: "good" as Tone,
  },
  {
    value: "MATERIAL_IMPACT",
    label: "Material impact",
    description:
      "The new evidence could change the decision. The case reopens so that a new decision can supersede the signed one. The signed decision itself is never changed.",
    tone: "critical" as Tone,
  },
] as const;

export const IMPACT_STATUS: Record<string, { label: string; tone: Tone }> = {
  OPEN: { label: "To assess", tone: "warning" },
  COMPLETED: { label: "Assessed", tone: "good" },
};

export const IMPACT_RATIONALE_MIN = 20;
export const IMPACT_RATIONALE_MAX = 5000;

export function impactStatusView(item: Pick<ImpactAssessment, "status" | "status_label"> | null | undefined) {
  const value = code(item?.status);
  const known = IMPACT_STATUS[value];
  return {
    label: safeText(item?.status_label) ?? known?.label ?? (value ? titleCase(value) : "Unknown"),
    tone: known?.tone ?? ("neutral" as Tone),
  };
}

export function impactConclusionView(item: Pick<ImpactAssessment, "conclusion" | "conclusion_label">) {
  const value = code(item.conclusion);
  const known = IMPACT_CONCLUSIONS.find((option) => option.value === value);
  if (!value && !safeText(item.conclusion_label)) return null;
  return {
    label: safeText(item.conclusion_label) ?? known?.label ?? titleCase(value),
    tone: known?.tone ?? ("neutral" as Tone),
  };
}

/** What prompted the assessment ("Evidence linked after the decision"), never the raw code. */
export function impactTriggerLabel(item: Pick<ImpactAssessment, "trigger" | "trigger_label">): string {
  const given = safeText(item.trigger_label);
  if (given) return given;
  const value = code(item.trigger);
  const known: Record<string, string> = {
    EVIDENCE_LINKED: "Evidence linked after the decision",
    EVIDENCE_REVIEWED: "Evidence reviewed after the decision",
  };
  return known[value] ?? (value ? titleCase(value) : "New evidence");
}

/** Whether the assessment can be recorded from this screen: the server allows it and it is still open. */
export const impactCanComplete = (item: Pick<ImpactAssessment, "actions" | "status">) =>
  item.actions?.can_complete === true && code(item.status) !== "COMPLETED";

export function impactProblem(conclusion: string, rationale: string): string | null {
  if (!IMPACT_CONCLUSIONS.some((option) => option.value === conclusion)) return "Choose your conclusion.";
  return textProblem(rationale, "your rationale", { min: IMPACT_RATIONALE_MIN, max: IMPACT_RATIONALE_MAX });
}

export const impactBody = (conclusion: string, rationale: string) => ({ conclusion, rationale: rationale.trim() });

// ---------------------------------------------------------------------------------------------------------------
// Closure criteria (GET /api/v1/investigations/{id}/closure-check)

export type ClosureCriterion = {
  key?: string | null;
  label?: string | null;
  result?: string | null;
  rationale?: string | null;
};
export type ClosureCheck = {
  can_close?: boolean | null;
  applies?: boolean | null;
  criteria?: ClosureCriterion[] | null;
};

export const closureCheckPath = (investigationId: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/closure-check`;

export type ClosureResult = "BLOCKED" | "PASS" | "NOT_REQUIRED";

export const CLOSURE_RESULT: Record<ClosureResult, { label: string; tone: Tone }> = {
  BLOCKED: { label: "Blocked", tone: "critical" },
  PASS: { label: "Pass", tone: "good" },
  NOT_REQUIRED: { label: "Not required", tone: "neutral" },
};

const closureResultOf = (value: unknown): ClosureResult => {
  const result = code(value);
  if (result === "PASS" || result === "PASSED") return "PASS";
  if (result === "NOT_REQUIRED" || result === "NOT_APPLICABLE") return "NOT_REQUIRED";
  // Anything else (blocked, pending, unknown) stops the case from closing until the server says otherwise.
  return "BLOCKED";
};

export type ClosureRow = { key: string; label: string; result: ClosureResult; rationale: string | null };

/** The criteria, Blocked first, then Pass and Not required, each with its rationale. */
export function closureCriteria(check: ClosureCheck | null | undefined): ClosureRow[] {
  const order: ClosureResult[] = ["BLOCKED", "PASS", "NOT_REQUIRED"];
  return (check?.criteria ?? [])
    .map((item, index) => ({
      index,
      key: String(item.key ?? index),
      label: safeText(item.label) ?? titleCase(code(item.key ?? "Criterion")),
      result: closureResultOf(item.result),
      rationale: safeText(item.rationale),
    }))
    .sort((a, b) => order.indexOf(a.result) - order.indexOf(b.result) || a.index - b.index)
    .map((item) => ({ key: item.key, label: item.label, result: item.result, rationale: item.rationale }));
}

/**
 * Whether Close is offered: always for a case the criteria do not apply to (no signed decision), else only when the
 * server says it can close and no criterion is blocked. Without a check (still loading, unavailable) Close stays
 * offered and the server decides.
 */
export function closureAllowed(check: ClosureCheck | null | undefined): boolean {
  if (!check) return true;
  if (check.applies === false) return true;
  if (check.can_close === false) return false;
  return !closureCriteria(check).some((row) => row.result === "BLOCKED");
}

/** "1 blocked · 3 pass · 1 not required": counts only. */
export function closureHeadline(rows: ClosureRow[]): string {
  if (!rows.length) return "No closure criteria reported.";
  return (["BLOCKED", "PASS", "NOT_REQUIRED"] as ClosureResult[])
    .map((result) => {
      const count = rows.filter((row) => row.result === result).length;
      return count ? `${count} ${CLOSURE_RESULT[result].label.toLowerCase()}` : "";
    })
    .filter(Boolean)
    .join(" · ");
}
