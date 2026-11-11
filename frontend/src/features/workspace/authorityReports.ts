// Pure rules for Complaints › Reports (T-G2c, T-G2b): the report worksheets in each authority's field order and the
// obligation lifecycle with its submission record. The server (/api/v1/reports, backend/app/authority_reports)
// drafts every field from the records and decides every step; these only shape what the person sees and what is
// sent. MDARIX never submits: the person submits in the authority's route and records it here.
import type { Tone } from "../admin/console/dashboardModel";
import { deadlineLabel, timeLeft, type DueLike } from "../../app/dates";

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
  | "COMPLETE"
  | "CANCELLED";

/** The report's status path on the new navigation (0.10.75, Release C part C3; the server's rules.STAGES). */
export type ReportStage = "CREATED" | "COMPLETE" | "APPROVAL" | "APPROVED" | "SUBMITTED" | "ACKNOWLEDGED";
export type StageStep = { code: ReportStage; label: string; state: "DONE" | "CURRENT" | "LATER" };
/** The mandatory-fields meter: the form's must-have fields, how many have a value, and the empty ones. */
export type Mandatory = { total: number; filled: number; missing?: string[] };

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
  due_at?: string | null;
  due_label?: string | null;
  assessment: string | null;
  can_start: boolean;
  sample: boolean;
  /** 0.10.75: a started report's place on the status path (null when cancelled or not started). */
  stage?: ReportStage | null;
  stage_label?: string;
  mandatory?: Mandatory;
  /** A US follow-up's number in its chain: "Follow-up #n" (0.10.96, B3). */
  follow_up?: number | null;
  submitted_at?: string | null;
  /** The Reports tab's list views it belongs to ("open", "my-approval", "submitted-month"). */
  views?: string[];
};

export type ReportList = {
  items: ReportListItem[];
  forms: { market: string; title: string; version: string; starter?: boolean }[];
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
  /** The form's fixed list for this field (0.10.76), as printed; absent: free text. */
  options?: string[] | null;
  note: string | null;
  by: string | null;
  at: string | null;
  /** A code field's IMDRF annex (0.10.77); absent: not a code field. */
  code_annex?: string | null;
  /** The code the approved mapping suggests, waiting for a person (status SUGGESTED). */
  suggestion?: string | null;
  /** What the mapping suggested before the person changed it. */
  suggested?: string | null;
  /** 0.10.81: what the field takes (TEXT, DATE, DATE_RANGE, IMDRF_CODE, LIST_CODE), and why a value typed before does
   * not fit it (flagged, counted as missing, never deleted). */
  kind?: string;
  problem?: string | null;
  /** 0.10.92 (A5): what is asked for beside the field (CONTACT_EMAIL: the eMDR's contact office e-mail). */
  ask?: "CONTACT_EMAIL" | null;
  /** 0.10.83 (D2.7): who knows it (the product, the organization, or this event), and whether it is entered once
   * for every report (``once_key`` groups fields entered together). */
  scope?: "PRODUCT" | "ORGANIZATION" | "EVENT";
  once?: boolean;
  once_key?: string;
};

export type WorksheetSection = { code: string; title: string; note: string | null; fields: WorksheetField[] };

/**
 * Who approves a waiting snapshot or guide version, from the server before anyone types a password (J13): the form is
 * shown only when ``may_approve``; ``same_person`` is the trial's practice approval of one's own work (working alone);
 * ``message`` says why not and names the colleagues who may (``approvers``).
 */
export type ApprovalStanding = {
  may_approve: boolean;
  same_person: boolean;
  approvers: string[];
  message: string | null;
  role?: string | null;
};

/** What the draft says before approval is asked: who gets the approval task in My Work. */
export function askNote(standing: ApprovalStanding | null | undefined): string {
  if (!standing) return "When ready, ask a colleague to approve it.";
  const names = standing.approvers;
  if (names.length)
    return `When ready, ask for approval: ${names.join(", ")} ${names.length === 1 ? "gets" : "get"} a task in My Work.`;
  if (standing.same_person)
    return "When ready, ask for approval. In a pilot a colleague approves it; working alone in the trial, you approve your own practice report.";
  return "When ready, ask for approval. Nobody else in your organization may approve it yet: an administrator gives a colleague the Regulatory Reviewer, Authorized Decision Maker or Leader role.";
}

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
  /** Approved by its preparer or the conclusion's signer: the trial's practice approval (T-B8). */
  same_person?: boolean;
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
    business_id?: string | null;
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
    /** 0.10.76: a starter form (EU MIR, GB MIR, Health Canada), its report types and the one this report is. */
    starter?: boolean;
    report_types?: string[];
    report_kind?: string | null;
  };
  routes: Route[];
  /** B9 step 8: a US importer's or user facility's recipients, each recorded apart ("Sent to FDA", "... manufacturer"). */
  recipients?: { recipient: string; label: string; route: string; recorded: boolean }[] | null;
  /** B9 step 9: an importer's or user facility's follow-up clock, a labelled starter. */
  follow_up_clock?: string | null;
  state: ObligationState;
  state_label: string;
  next_step: string;
  steps: { state: ObligationState; label: string }[];
  stage?: ReportStage | null;
  stage_label?: string;
  stages?: StageStep[];
  mandatory?: Mandatory;
  approved_snapshot?: Snapshot | null;
  preparers?: string[];
  cancelled_reason?: string | null;
  /** 0.10.81: a submitted report whose market's later signed conclusion says otherwise: what to consider. */
  conclusion_changed?: string | null;
  deadline: DeadlineFields;
  assessment: {
    conclusion: string | null;
    report_type_label: string | null;
    /** B9: the rules (floor) the conclusion was decided under, and a US report's role (IMPORTER, USER_FACILITY). */
    floor_code?: string | null;
    role?: string | null;
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
  pending_snapshot: (Snapshot & { sections?: WorksheetSection[] | null }) | null;
  /** 0.10.83 (D2.8): every signature on the report, with the signer's full name, the moment and its meaning. */
  signatures?: { name: string; at: string | null; meaning: string }[];
  cannot_approve: string[];
  approval?: ApprovalStanding | null;
  submissions: Submission[];
  request: { text: string; received_on: string } | null;
  /** FDA requests recorded on this open follow-up after it was started (0.10.96, owner decision 1 after B3 run 4). */
  fda_requests?: { text: string; received_on: string; due_on: string; h2_ticked: boolean }[];
  parent_id: string | null;
  responses: {
    id: string;
    state: ObligationState;
    state_label: string;
    due_on: string | null;
    request_text: string;
    received_on?: string | null;
    /** A US follow-up's number in its chain (0.10.96, B3). */
    follow_up?: number | null;
  }[];
  /** This report is US follow-up #n of its initial report (0.10.96, B3). */
  follow_up?: number | null;
  /** B9 step 14: an India report's place in its chain (on demand, no legal clock: D15); null for other markets. On the
   * initial report: its follow-ups and final, and whether one can be created now. */
  india_chain?: {
    type: "Initial" | "Follow up" | "Final";
    due_on?: null;
    next_report_on?: string | null;
    items?: { id: string; type: "Follow up" | "Final"; state: ObligationState; due_on?: null }[];
    ended?: boolean;
    can_create?: boolean;
    note: string;
  } | null;
  /** B9 step 11: a Canada report's chain (the Final made when the preliminary is submitted; updates on demand).
   * ``official_form``: Health Canada's form file is in place (until then only the worksheet PDF). */
  canada_chain?: {
    type: string;
    due_on?: string | null;
    next_report_on?: string | null;
    items?: { id: string; type: string; state: ObligationState; due_on?: string | null }[];
    ended?: boolean;
    can_create?: boolean;
    official_form?: boolean;
    note: string;
  } | null;
  note: string | null;
  follow_up_due_on: string | null;
  starter_mark: string;
  practice_label: string | null;
  never_submits: string;
  sample: boolean;
  /** Mapped codes are suggestions a person confirms or changes (the new navigation, 0.10.77). */
  codes_confirmed?: boolean;
  /** A US report: what FDA's eMDR file still needs (blocks it), and the approved values it leaves out. */
  emdr?: {
    missing: string[];
    left_out: string[];
    /** A follow-up: the values its file sends, new or changed since the last report sent (0.10.96, B3). */
    changed?: string[];
  } | null;
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

/** The markets with a worksheet (the server's forms.form_for): the classic navigation keeps the US and India; the
 * new one adds EU / NI, Great Britain and Canada (0.10.76, starters for your consultant to confirm). */
export const WORKSHEET_MARKETS = ["US", "IN"];
export const NEW_WORKSHEET_MARKETS = [...WORKSHEET_MARKETS, "EU_NI", "GB", "CA"];
export const worksheetMarkets = (navigation?: string | null): readonly string[] =>
  navigation === "new" ? NEW_WORKSHEET_MARKETS : WORKSHEET_MARKETS;

/** Whether a complaint's markets owe a report with a worksheet: a market with one reportable, or pending. */
export function owesWorksheet(
  markets: { market: string; state: string; suggested: string | null }[],
  navigation?: string | null,
): boolean {
  return markets.some(
    (item) =>
      worksheetMarkets(navigation).includes(item.market) &&
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
  if (status === "MAY_BE_UNKNOWN" || status === "FOLLOW_UP" || status === "SUGGESTED") return "warning";
  if (["FROM_RECORD", "CONFIRMED", "ENTERED", "CHANGED"].includes(status)) return "good";
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

/** The states in which the obligation's deadline is met (the server's rules.MET). */
export const MET_STATES: readonly ObligationState[] = ["ACCEPTED", "SUBMITTED_NO_ACK", "FOLLOW_UP_DUE", "COMPLETE"];
/** Nothing more is owed: met, or cancelled by a later "not reportable" conclusion (the server's rules.CLOSED). */
export const CLOSED_STATES: readonly ObligationState[] = [...MET_STATES, "CANCELLED"];

/** The Reports tab's list views (0.10.75): each a filter the server marks on the list's items (``views``). */
export const REPORT_VIEWS = {
  "Open reports": { code: "open", detail: "Every report still owed, the nearest deadline first." },
  "Waiting for my approval": {
    code: "my-approval",
    detail: "Sent for approval and not prepared by you (in a trial, your own too, as practice).",
  },
  "Submitted this month": {
    code: "submitted-month",
    detail: "Submitted through the authority's channel since the first of the month.",
  },
} as const;
export type ReportView = keyof typeof REPORT_VIEWS;
export const REPORT_VIEW_NAMES = Object.keys(REPORT_VIEWS) as ReportView[];

/** Where one report opens on the new navigation: the Reports tab, the report named in its address. */
export const reportPlace = (id: string) => ({
  section: "Reports" as const,
  tab: `?${new URLSearchParams({ report: id })}`,
});

/** The reports of a list view: started reports only (a market not yet concluded is not a report). */
export function reportsInView(items: readonly ReportListItem[], view: ReportView): ReportListItem[] {
  return items.filter((item) => item.id && (item.views ?? []).includes(REPORT_VIEWS[view].code));
}

/** A report's deadline on the wire (authority_reports/router.py ``due_fields``). */
export type DeadlineFields = {
  due_on: string | null;
  provisional: boolean;
  days_left: number | null;
  overdue: boolean;
  due_at?: string | null;
  due_zone?: string | null;
  due_label?: string | null;
};

/** A report's deadline for its chip (app/chips.tsx DeadlineChip), or null once it is met or has no day yet. */
export function deadlineDue(item: DeadlineFields, state?: ObligationState): DueLike | null {
  if (!item.due_on || (state && CLOSED_STATES.includes(state))) return null;
  return {
    due_at: item.due_at,
    due_date: item.due_on,
    days_left: item.days_left,
    state: item.overdue ? "OVERDUE" : "RUNNING",
  };
}

/** "Deadline Sat 7 Nov 2026, 23:59 IST · 6 days left": the end with its time zone, and the app's one time-left text
 * (app/dates.ts timeLeft), overdue from the server. */
export function deadlineText(item: DeadlineFields, state?: ObligationState, now = new Date()): string {
  if (!item.due_on) return "No deadline yet";
  const when = deadlineLabel({ due_label: item.due_label, due_date: item.due_on });
  if (state && MET_STATES.includes(state)) return `Deadline ${when}: met by the submission`;
  if (state === "CANCELLED") return "Cancelled: not reportable";
  const left = timeLeft(
    {
      due_at: item.due_at,
      due_date: item.due_on,
      days_left: item.days_left,
      state: item.overdue ? "OVERDUE" : "RUNNING",
    },
    now,
  );
  return `${item.provisional ? "Provisional deadline" : "Deadline"} ${when}${left ? ` · ${left}` : ""}`;
}

/** The worksheet's summary line: how many fields come from records, were entered or confirmed, and are missing. */
/** One count per thing (0.10.72): "from your records" is the record's and the confirmed values, everywhere the
 * worksheet says it (the list's line, the meter, the approval's summary); "entered" is what a person typed. */
export const FROM_RECORDS = ["FROM_RECORD", "CONFIRMED"];
export function filledCounts(counts: Record<string, number>): { fromRecords: number; entered: number } {
  return {
    fromRecords: FROM_RECORDS.reduce((sum, key) => sum + (counts[key] ?? 0), 0),
    entered: counts.ENTERED ?? 0,
  };
}

export function summaryLine(counts: Record<string, number>): string {
  const n = (key: string) => counts[key] ?? 0;
  const { fromRecords, entered } = filledCounts(counts);
  const parts = [`${fromRecords} from your records`];
  if (entered) parts.push(`${entered} entered`);
  if (n("MUST_HAVE")) parts.push(`${n("MUST_HAVE")} must have before submission`);
  const later = n("MAY_BE_UNKNOWN") + n("FOLLOW_UP");
  if (later) parts.push(`${later} may wait`);
  if (n("OUTSIDE")) parts.push(`${n("OUTSIDE")} entered in the authority's route`);
  if (n("FICTIONAL")) parts.push(`${n("FICTIONAL")} fictional (sample only)`);
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

/** A field still to enter before submission. */
export const isMissing = (field: Pick<WorksheetField, "status"> & { missing_class?: string }) =>
  field.status === "MUST_HAVE" || (field.status === "SUGGESTED" && field.missing_class === "MUST_HAVE");

/** The worksheet's meter (wow screen 5): fields filled from the records, entered by a person, missing, and in all. */
export function worksheetMeter(sections: readonly WorksheetSection[]) {
  const fields = sections.flatMap((section) => section.fields);
  const count = (statuses: string[]) => fields.filter((field) => statuses.includes(field.status)).length;
  return {
    total: fields.length,
    fromRecords: count(FROM_RECORDS),
    entered: count(["ENTERED"]),
    missing: fields.filter(isMissing).length,
  };
}
