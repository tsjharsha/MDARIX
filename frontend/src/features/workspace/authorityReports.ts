// Pure rules for Complaints › Reports (T-G2c, T-G2b): the report worksheets in each authority's field order and the
// obligation lifecycle with its submission record. The server (/api/v1/reports, backend/app/authority_reports)
// drafts every field from the records and decides every step; these only shape what the person sees and what is
// sent. MDARIX never submits: the person submits in the authority's route and records it here.
import type { Tone } from "../admin/console/dashboardModel";

export const REPORTS = "/api/v1/reports";
export const REPORTS_TAB = "Reports";
export const REASON_MIN = 10;
export const FILE_MAX = 2 * 1024 * 1024;

export type ObligationState =
  | "NOT_STARTED"
  | "NO_WORKSHEET"
  | "DRAFT"
  | "CORRECTION_REQUIRED"
  | "APPROVED"
  | "SUBMITTED_PENDING"
  | "ACCEPTED"
  | "SUBMITTED_NO_ACK"
  | "FOLLOW_UP_DUE"
  | "COMPLETE";

export type ReportListItem = {
  id: string | null;
  kind: "INITIAL" | "RESPONSE";
  complaint_id: string;
  complaint_ref: string;
  complaint_identifier: string;
  description: string;
  market: string;
  market_label: string;
  form_title: string | null;
  form_version: string | null;
  state: ObligationState;
  state_label: string;
  next_step: string;
  due_on: string | null;
  provisional: boolean;
  days_left: number | null;
  overdue: boolean;
  assessment: string | null;
  can_start: boolean;
  sample: boolean;
};

export type ReportList = {
  items: ReportListItem[];
  forms: { market: string; title: string; version: string }[];
  never_submits: string;
  starter_mark: string;
  practice_label: string | null;
};

export type FieldSource = { type: string; ref: string | null; label: string; id: string | null };

export type WorksheetField = {
  id: string;
  number: string;
  label: string;
  value: string | null;
  status: string;
  status_label: string;
  source: FieldSource | null;
  personal: "PATIENT" | "REPORTER" | null;
  missing_class: string;
  editable?: boolean;
  note: string | null;
  by: string | null;
  at: string | null;
};

export type WorksheetSection = { code: string; title: string; note: string | null; fields: WorksheetField[] };

export type Snapshot = {
  id: string;
  version: number;
  state: "PENDING" | "APPROVED" | "SUPERSEDED";
  form_version: string;
  content_fingerprint: string;
  requested_by: string;
  requested_at: string;
  approved_by: string | null;
  approved_at: string | null;
  preparers: string[];
  sample: boolean;
};

export type Evidence = {
  id: string;
  kind: string;
  kind_label: string;
  outcome: "CONTENT" | "RECEIPT" | "ACCEPTED" | "REJECTED";
  note: string | null;
  file_name: string | null;
  size: number | null;
  sha256: string | null;
  received_at: string;
  recorded_by: string;
};

export type Submission = {
  id: string;
  attempt: number;
  route: string;
  route_label: string;
  submitted_at: string;
  content_note: string | null;
  differences: { field: string; classification: string; reason: string | null }[];
  authority_reference: string | null;
  result: "PENDING" | "ACCEPTED" | "REJECTED" | "NO_ACK_EXPECTED";
  late: boolean;
  follow_up: { row: number; at: string; late: boolean } | null;
  recorded_by: string;
  evidence: Evidence[];
  receipt_only: boolean;
  sample: boolean;
};

export type Route = {
  code: string;
  label: string;
  note: string;
  acknowledgement_expected: boolean;
  evidence: { kind: string; label: string; outcomes: string[] }[];
};

export type ReportDetail = {
  id: string;
  kind: "INITIAL" | "RESPONSE";
  complaint: {
    id: string;
    ref: string;
    complaint_identifier: string;
    product_name: string | null;
    version: string | null;
    country: string | null;
    description: string;
    aware_date: string | null;
    sample: boolean;
  };
  market: string;
  market_label: string;
  form: {
    code: string;
    title: string;
    version: string;
    authority: string;
    source_document: string;
    clauses: { id: string; short: string; title: string }[];
  };
  routes: Route[];
  state: ObligationState;
  state_label: string;
  next_step: string;
  steps: { state: ObligationState; label: string }[];
  deadline: { due_on: string | null; provisional: boolean; days_left: number | null; overdue: boolean };
  assessment: {
    conclusion: string | null;
    report_type_label: string | null;
    signed_by: string | null;
    signed_at: string | null;
    version: number;
  } | null;
  case: string | null;
  sections: WorksheetSection[];
  counts: Record<string, number>;
  status_labels: Record<string, string>;
  editable: boolean;
  snapshots: Snapshot[];
  pending_snapshot: Snapshot | null;
  cannot_approve: string[];
  submissions: Submission[];
  request: { text: string; received_on: string } | null;
  parent_id: string | null;
  responses: { id: string; state: ObligationState; state_label: string; due_on: string | null; request_text: string }[];
  note: string | null;
  follow_up_due_on: string | null;
  starter_mark: string;
  practice_label: string | null;
  never_submits: string;
  sample: boolean;
};

/** The tab name that opens Reports on one complaint ("Reports?complaint=<id>"), and its reading. */
export function reportsTab(complaintId?: string): string {
  return complaintId ? `${REPORTS_TAB}?complaint=${encodeURIComponent(complaintId)}` : REPORTS_TAB;
}

export function parseReportsTab(tab: string | null | undefined): { isReports: boolean; complaintId: string | null } {
  if (!tab || !(tab === REPORTS_TAB || tab.startsWith(`${REPORTS_TAB}?`)))
    return { isReports: false, complaintId: null };
  const params = new URLSearchParams(tab.slice(REPORTS_TAB.length + 1));
  return { isReports: true, complaintId: params.get("complaint") };
}

/** The markets with a worksheet in this release (the server's forms.BY_MARKET). */
export const WORKSHEET_MARKETS = ["US", "IN"];

/** Whether a complaint's markets owe a report with a worksheet: a US or India market reportable, or pending. */
export function owesWorksheet(markets: { market: string; state: string; suggested: string | null }[]): boolean {
  return markets.some(
    (item) =>
      WORKSHEET_MARKETS.includes(item.market) &&
      (item.state === "REPORTABLE" ||
        (item.state === "DRAFT" && (item.suggested === "REPORTABLE" || item.suggested === "PENDING_INFORMATION"))),
  );
}

export function stateTone(state: ObligationState, overdue = false): Tone {
  if (overdue) return "critical";
  if (state === "CORRECTION_REQUIRED") return "critical";
  if (state === "ACCEPTED" || state === "COMPLETE" || state === "SUBMITTED_NO_ACK") return "good";
  if (state === "SUBMITTED_PENDING" || state === "FOLLOW_UP_DUE") return "warning";
  if (state === "APPROVED") return "good";
  return "neutral";
}

/** Each field status's tone: a missing must-have stands out, a patient field outside the sample is neutral. */
export function fieldTone(status: string): Tone {
  if (status === "MUST_HAVE") return "critical";
  if (status === "MAY_BE_UNKNOWN" || status === "FOLLOW_UP") return "warning";
  if (status === "FROM_RECORD" || status === "CONFIRMED" || status === "ENTERED") return "good";
  return "neutral";
}

/** How far along the steps the obligation is (for the stepper): the index of its step, with a draft after a
 * rejection on step 0, an approval-pending snapshot still a draft. */
export function stepIndex(state: ObligationState): number {
  if (state === "DRAFT" || state === "CORRECTION_REQUIRED") return 0;
  if (state === "APPROVED") return 1;
  if (state === "SUBMITTED_PENDING" || state === "SUBMITTED_NO_ACK") return 2;
  if (state === "ACCEPTED" || state === "FOLLOW_UP_DUE") return 3;
  if (state === "COMPLETE") return 4;
  return -1;
}

export function deadlineText(item: { due_on: string | null; days_left: number | null; provisional: boolean }): string {
  if (!item.due_on) return "No deadline yet";
  const left =
    item.days_left === null
      ? ""
      : item.days_left < 0
        ? `, ${-item.days_left} days overdue`
        : item.days_left === 0
          ? ", due today"
          : `, ${item.days_left} days left`;
  return `${item.provisional ? "Provisional deadline" : "Deadline"} ${item.due_on}${left}`;
}

/** The worksheet's summary line: how many fields come from records, were entered or confirmed, and are missing. */
export function summaryLine(counts: Record<string, number>): string {
  const n = (key: string) => counts[key] ?? 0;
  const filled = n("FROM_RECORD") + n("ENTERED") + n("CONFIRMED");
  const parts = [`${filled} filled`];
  if (n("MUST_HAVE")) parts.push(`${n("MUST_HAVE")} must have before submission`);
  const later = n("MAY_BE_UNKNOWN") + n("FOLLOW_UP");
  if (later) parts.push(`${later} may wait`);
  if (n("OUTSIDE")) parts.push(`${n("OUTSIDE")} entered in the authority's route`);
  return parts.join(" · ");
}

export type SubmissionForm = {
  route: string;
  submittedAt: string;
  note: string;
  reference: string;
  matches: boolean;
  differences: { field: string; classification: "MATERIAL" | "NON_MATERIAL"; reason: string }[];
};

export function submissionProblem(form: SubmissionForm, hasFile: boolean): string | null {
  if (!form.route) return "Choose the route you submitted through";
  if (!form.submittedAt) return "Give the time you submitted";
  if (!hasFile && form.note.trim().length < 1) return "Attach the submitted content, or describe it in a note";
  if (!form.matches && !form.differences.length) return "Say whether the content matches the approved snapshot";
  if (form.differences.some((item) => item.classification === "MATERIAL"))
    return "A material difference needs re-approval before submission: reopen the draft";
  if (form.differences.some((item) => item.reason.trim().length < REASON_MIN))
    return `Give each difference's reason in at least ${REASON_MIN} characters`;
  return null;
}

export function submissionBody(form: SubmissionForm, file: FileIn | null) {
  return {
    route: form.route,
    submitted_at: new Date(form.submittedAt).toISOString(),
    content_note: form.note,
    authority_reference: form.reference,
    no_differences: form.matches,
    differences: form.matches ? [] : form.differences,
    file,
  };
}

export type FileIn = { name: string; content_type: string; data: string };

/** A file the person attaches, as the server takes it (base64), or the reason it cannot be attached. */
export async function fileIn(file: File): Promise<FileIn> {
  if (file.size > FILE_MAX) throw new Error(`Attach a file of at most ${FILE_MAX / (1024 * 1024)} MB`);
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let index = 0; index < bytes.length; index += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  }
  return { name: file.name, content_type: file.type || "application/octet-stream", data: btoa(binary) };
}

/** The outcomes a piece of evidence may record on the attempt's route, as people read them. */
export const OUTCOME_LABELS: Record<string, string> = {
  CONTENT: "Submitted content",
  RECEIPT: "Receipt (not acceptance)",
  ACCEPTED: "Accepted",
  REJECTED: "Rejected",
};

export const RESULT_LABELS: Record<Submission["result"], string> = {
  PENDING: "Acceptance pending",
  ACCEPTED: "Accepted",
  REJECTED: "Rejected",
  NO_ACK_EXPECTED: "No acknowledgement expected",
};

/** Local date-time input value for now (the default submission time). */
export function nowLocal(now: Date = new Date()): string {
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}
