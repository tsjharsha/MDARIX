// Pure rules for a case's next steps (Phase 5), which replace the investigator's old decision options: which steps
// the server offers, which small form each step opens, what it checks and what it sends. A next step moves the work
// on; it never decides the case. Escalation for a quality review goes through the Decision Brief.
import { titleCase } from "../admin/console/dashboardModel";
import { safeText } from "../../app/displayId";
import { dueAtFromDay } from "./caseWorkflow";
import {
  EMPTY_NEW_REQUEST,
  REQUEST_TITLE_MAX,
  newRequestProblem,
  requestedItems,
  type NewRequestForm,
} from "./evidenceWorkflow";
import { textProblem } from "./intelligence";

export type NextStepOption = {
  action: string;
  label: string;
  description: string | null;
  available: boolean;
  reason: string | null;
};

/** Which form a step opens: a reason only, a review request, an evidence or test request, a change review, the brief. */
export type NextStepForm = "reason" | "review" | "request" | "change" | "brief";

export const NEXT_STEP_FORM: Record<string, NextStepForm> = {
  CONTINUE_INVESTIGATION: "reason",
  NO_DECISION_YET: "reason",
  REQUEST_RISK_REVIEW: "review",
  REQUEST_REGULATORY_REVIEW: "review",
  REQUEST_ADDITIONAL_EVIDENCE: "request",
  REQUEST_ADDITIONAL_TESTING: "request",
  REVIEW_SUPPLIER_CHANGE: "change",
  REVIEW_PRODUCT_CHANGE: "change",
  ESCALATE_FOR_QUALITY_REVIEW: "brief",
};

/** The form a step opens; an action this screen does not know asks for a reason only. */
export const nextStepForm = (action: string): NextStepForm => NEXT_STEP_FORM[action] ?? "reason";

export const nextStepOptionsPath = (investigationId: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/next-steps/options`;
export const nextStepsPath = (investigationId: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/next-steps`;

const code = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

/** The options the server offers (a list, or an object holding `items` or `options`), each with a readable label. */
export function nextStepOptions(value: unknown): NextStepOption[] {
  const list = Array.isArray(value)
    ? value
    : Array.isArray((value as { items?: unknown })?.items)
      ? (value as { items: unknown[] }).items
      : Array.isArray((value as { options?: unknown })?.options)
        ? (value as { options: unknown[] }).options
        : [];
  return list
    .map((item) => {
      const row = (item ?? {}) as Record<string, unknown>;
      const action = code(row.action);
      if (!action) return null;
      return {
        action,
        label: safeText(row.label) ?? titleCase(action),
        description: safeText(row.description),
        available: row.available !== false,
        reason: safeText(row.reason),
      };
    })
    .filter((item): item is NextStepOption => !!item);
}

export const NEXT_STEP_REASON_MIN = 10;
export const NEXT_STEP_REASON_MAX = 2000;

export type ChangeForm = {
  mode: "none" | "person" | "role";
  assigneeUserId: string;
  assignedRole: string;
  title: string;
};
export const EMPTY_CHANGE: ChangeForm = { mode: "none", assigneeUserId: "", assignedRole: "", title: "" };

export type NextStepInput = {
  reason: string;
  /** The evidence or test request, with the fields of the New request drawer (always to a colleague or role). */
  request: NewRequestForm;
  change: ChangeForm;
};

export const emptyNextStep = (): NextStepInput => ({
  reason: "",
  request: { ...EMPTY_NEW_REQUEST, kind: "INTERNAL" },
  change: { ...EMPTY_CHANGE },
});

/** Why the step cannot be recorded yet, or null when it can. `today` is the local day (YYYY-MM-DD). */
export function nextStepProblem(action: string, input: NextStepInput, today: string): string | null {
  const form = nextStepForm(action);
  if (form === "brief") return "Escalation for a quality review goes through the Decision Brief.";
  const reason = textProblem(input.reason, "a reason", { min: NEXT_STEP_REASON_MIN, max: NEXT_STEP_REASON_MAX });
  if (reason) return reason;
  if (form === "request") return newRequestProblem({ ...input.request, kind: "INTERNAL", rationale: "" }, today);
  if (form === "change") {
    if (input.change.mode === "person" && !input.change.assigneeUserId) return "Choose the person to assign it to.";
    if (input.change.mode === "role" && !input.change.assignedRole) return "Choose the role queue to assign it to.";
    if (input.change.title.trim().length > REQUEST_TITLE_MAX)
      return `Keep the title to ${REQUEST_TITLE_MAX} characters.`;
  }
  return null;
}

/** The body of POST /investigations/{id}/next-steps: the action, the reason, and the details its form collected. */
export function nextStepBody(action: string, input: NextStepInput) {
  const form = nextStepForm(action);
  const reason = input.reason.trim();
  if (form === "request") {
    const request = input.request;
    const due = request.dueDay ? dueAtFromDay(request.dueDay) : null;
    return {
      action,
      reason,
      details: {
        title: request.title.trim(),
        requested_items: requestedItems(request.items),
        ...(request.recipientMode === "person"
          ? { recipient_user_id: request.recipientUserId }
          : { recipient_role: request.recipientRole }),
        ...(due ? { due_at: due } : {}),
        ...(request.priority ? { priority: request.priority } : {}),
        ...(request.unknownId ? { unknown_id: request.unknownId } : {}),
      },
    };
  }
  if (form === "change") {
    const change = input.change;
    const title = change.title.trim();
    const details = {
      ...(change.mode === "person" && change.assigneeUserId ? { assignee_user_id: change.assigneeUserId } : {}),
      ...(change.mode === "role" && change.assignedRole ? { assigned_role: change.assignedRole } : {}),
      ...(title ? { title } : {}),
    };
    return Object.keys(details).length ? { action, reason, details } : { action, reason };
  }
  return { action, reason };
}

/** "Recorded: REV000003." from the step's result, naming what it created by business ID (never a UUID). */
export function nextStepResultText(label: string, response: unknown): string {
  const result = ((response as { result?: unknown } | null)?.result ?? null) as Record<string, unknown> | null;
  const nested = ["review", "request", "evidence_request", "task"]
    .map((key) => result?.[key] as Record<string, unknown> | undefined)
    .find((item) => item && typeof item === "object");
  const id =
    safeText(result?.business_id) ?? safeText(nested?.business_id) ?? safeText(result?.task_business_id) ?? null;
  return id ? `${label} recorded: ${id}.` : `${label} recorded.`;
}
