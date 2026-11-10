// The list views of the new navigation (0.10.74, Release C part C2; the approved design's LIST_VIEWS): one "List view"
// choice per list, the persona's own views first. Pure rules, so the tests check each persona's views.
//
// A list view is either a filter of the one complaint list, read on the server (GET /api/v1/complaints?view=, six
// columns, one row action, cards on a phone), or one of stage 7's work queues, which keep their own screen (the triage
// list, the second look's decisions, the reporting and communications logs).

/** The complaint list views the server filters (backend/app/oversight/router.py LIST_VIEWS), with what each holds. */
export const SERVER_VIEWS: Readonly<Record<string, { code: string; detail: string }>> = {
  "All open complaints": {
    code: "open",
    detail: "Every complaint not closed in your QMS. Overdue first, then the nearest legal deadline.",
  },
  Overdue: { code: "overdue", detail: "A deadline or target already past. Then the nearest legal deadline first." },
  "Due this week": {
    code: "due-week",
    detail: "A deadline or target in the next seven days. The nearest legal deadline first.",
  },
  "Legal clocks this week": {
    code: "legal-week",
    detail: "A reporting deadline in the next seven days, or already past. Overdue first.",
  },
  "Reportability: decision needed": {
    code: "reportability",
    detail: "A market with no signed conclusion yet. Overdue first, then the nearest legal deadline.",
  },
  "Waiting for the reporter": {
    code: "waiting-reporter",
    detail: "A question still open with the reporter or a partner. Overdue first, then the nearest legal deadline.",
  },
  "Waiting for my approval": {
    code: "my-approval",
    detail: "An authority report sent for approval that you did not prepare (in a trial, your own too, as practice).",
  },
  "Signed this month": {
    code: "signed-month",
    detail:
      "A conclusion, disposition, report approval or ready to close signed this month. The nearest legal deadline first.",
  },
};

/** Stage 7's views (0.10.68): work queues with their own screens. */
export const QUEUE_VIEWS = [
  "To triage",
  "Calls to check",
  "Due soon",
  "Past target",
  "Imported backlog",
  "Second look",
  "Reporting",
  "Authority reports",
  "Communications",
  "Investigations",
  "Dismissed",
  "All complaints",
] as const;

/** Every complaint list view, in the order "More views" lists them. */
export const COMPLAINT_LIST_VIEWS: readonly string[] = [...Object.keys(SERVER_VIEWS), ...QUEUE_VIEWS];

/** Each persona's own views, first in the choice (the approved design's LIST_VIEWS). */
export const PERSONA_LIST_VIEWS: Readonly<Record<string, readonly string[]>> = {
  admin: ["All open complaints", "Due this week", "Second look", "Reporting", "Waiting for the reporter"],
  quality: ["All open complaints", "Due this week", "Past target", "Second look"],
  regulatory: ["Reportability: decision needed", "Authority reports", "Legal clocks this week"],
  handler: ["To triage", "Calls to check", "Second look", "Waiting for the reporter"],
  decision: ["Waiting for my approval", "Signed this month"],
};

/**
 * The views a persona is offered: its own first, then every other one under "More views" (the persona narrows the
 * first choice, never what the person may open). A persona without its own (one whose tabs hold no complaint list,
 * reaching it by a link) gets Admin's.
 */
export function listViewsFor(persona: string | undefined): { mine: readonly string[]; more: string[] } {
  const mine = PERSONA_LIST_VIEWS[persona ?? ""] ?? PERSONA_LIST_VIEWS.admin;
  return { mine, more: COMPLAINT_LIST_VIEWS.filter((view) => !mine.includes(view)) };
}

/** The investigation list's views (the Investigations tab), filtered on the screen from the list it reads. */
export const INVESTIGATION_VIEWS = ["Open investigations", "Assigned to me", "All investigations"] as const;
export type InvestigationView = (typeof INVESTIGATION_VIEWS)[number];

const CLOSED_CASE = /^(closed|cancelled|canceled)$/i;

/** Whether an investigation belongs in a view (``me``: the signed-in person's id). */
export function inInvestigationView(
  row: { status?: unknown; workflow_state?: unknown; owner_ref?: unknown },
  view: InvestigationView,
  me: string | null | undefined,
): boolean {
  const closed = CLOSED_CASE.test(String(row.workflow_state ?? "")) || CLOSED_CASE.test(String(row.status ?? ""));
  if (view === "Open investigations") return !closed;
  if (view === "Assigned to me") return !closed && !!me && String(row.owner_ref ?? "") === me;
  return true;
}
