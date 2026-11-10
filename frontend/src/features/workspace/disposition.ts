// Pure rules for Complaints › Dispositions (T-G36, T-U13, T-G39): what the board and the decision tree ask the server
// for, which branch each question allows, what a signature sends and when it may be sent. The server
// (/api/v1/complaints/.../disposition, backend/app/complaint_disposition) computes the triggers, the known-issue cases
// and the routine-path offer, checks every rule again and signs; these only shape what the person sees.
import type { Tone } from "../admin/console/dashboardModel";
import type { TrainingDocument } from "./marketAssessment";

export type Branch = "ESCALATED_BY_TRIGGER" | "KNOWN_ISSUE" | "SERVICE_LEVEL" | "ESCALATED_BY_CHOICE";
export const BRANCH_LABELS: Record<Branch, string> = {
  ESCALATED_BY_TRIGGER: "Escalated: trigger met",
  KNOWN_ISSUE: "Known issue, linked to an open investigation",
  SERVICE_LEVEL: "Resolved at service level",
  ESCALATED_BY_CHOICE: "Escalated by choice",
};
export const BRANCH_TONES: Record<Branch, Tone> = {
  ESCALATED_BY_TRIGGER: "critical",
  KNOWN_ISSUE: "neutral",
  SERVICE_LEVEL: "good",
  ESCALATED_BY_CHOICE: "serious",
};
/** The server's limits (backend/app/complaint_disposition/rules.py). */
export const DISPOSITION_LIMITS = { reasonMin: 10, rationaleMin: 20, textMax: 2000, ticketMax: 120 };
/** The corrections that need a service ticket (rules.TICKET_CORRECTIONS). */
export const TICKET_CORRECTIONS = ["PART_REPLACED", "SETTING_CORRECTED"];

export type Trigger = {
  code: string;
  label: string;
  field: string;
  value: string | number;
  record: string;
  fact: string;
};
export type KnownCase = { id: string; ref: string; identifier: string; question: string; match: string[] };
export type ServiceRecord = {
  troubleshooting: string;
  correction_type: string;
  correction: string;
  result: string;
  service_ticket: string;
  no_investigation_rationale: string;
  clause?: string;
};
export type Classification = {
  id: string | null;
  version: number;
  use_environment: string;
  use_environment_text: string | null;
  user_type: string;
  user_type_text: string | null;
  source_values: { use_environment?: string | null; user_type?: string | null };
  state: "PROPOSED" | "CONFIRMED";
  coding_criteria_version: string;
  confirmed_by: string | null;
  confirmed_at: string | null;
};
export type DispositionVersion = {
  id: string;
  version: number;
  branch: Branch;
  branch_label: string;
  triggers: Trigger[];
  answers: Record<string, { answer: string; rationale: string; facts?: string }>;
  service_record: ServiceRecord | null;
  attribution: string | null;
  attribution_label: string | null;
  attribution_reason: string | null;
  investigation_id: string | null;
  investigation_ref: string | null;
  routine_path: boolean;
  hands_on_seconds: number | null;
  change_reason: string | null;
  content_fingerprint: string;
  signed_by: string;
  signed_at: string | null;
  superseded: boolean;
  sample: boolean;
};
export type DispositionComplaint = {
  id: string;
  ref: string;
  complaint_identifier: string;
  product_name: string | null;
  version: string | null;
  lot: string | null;
  description: string | null;
  source: string | null;
  problem_code: string | null;
  country: string | null;
  received_date: string | null;
  awareness_date: string | null;
};
export type DispositionScreen = {
  complaint: DispositionComplaint;
  opened_at: string;
  triggers: Trigger[];
  trigger_codes: string[];
  trigger_rules: { code: string; label: string; definition: string }[];
  candidates: KnownCase[];
  routine: {
    offered: boolean;
    blocked: string[];
    basis: string;
    markets: { market: string; label: string }[];
    target_seconds: number;
  };
  reportability: { on_watch: boolean; settled: boolean; markets: { market: string; label: string; state: string }[] };
  corrections: Record<string, string>;
  attributions: { code: string; label: string; definition: string }[];
  no_investigation_clause: string;
  classification: Classification;
  use_environments: Record<string, string>;
  user_types: Record<string, string>;
  coding_criteria: { version: string; rules: string[] };
  disposition_rules: { version: string; rules: string[] };
  current: DispositionVersion | null;
  history: DispositionVersion[];
  version: number;
  training: TrainingDocument[];
  training_required: boolean;
  /** The server needs the authenticator code with the signature (MDARIX_REQUIRE_MFA_FOR_SIGNATURES). */
  code_required?: boolean;
  trained_colleagues: string[];
  starter_mark: string;
  practice_label: string | null;
};
export type BoardItem = DispositionComplaint & {
  on_watch: boolean;
  routine_offered: boolean;
  triggers: string[];
  known_issue: string[];
  disposition?: DispositionVersion;
};
export type DispositionBoard = {
  summary: { waiting: number; signed: number; by_branch: Record<Branch, number>; routine_target_seconds: number };
  show: "waiting" | "signed";
  total: number;
  page: number;
  pages: number;
  items: BoardItem[];
};

export const dispositionPath = (complaintId: string, tail = "") =>
  `/api/v1/complaints/${encodeURIComponent(complaintId)}/disposition${tail}`;
export const boardPath = (show: "waiting" | "signed", page: number) =>
  `/api/v1/complaints/dispositions?show=${show}&page=${page}`;
export const trendPath = (group: string, filters: Record<string, string>) => {
  const query = new URLSearchParams({ group });
  for (const [key, value] of Object.entries(filters)) if (value) query.set(key, value);
  return `/api/v1/complaints/dispositions/trend?${query.toString()}`;
};

export type DispositionForm = {
  branch: Branch;
  caseId: string;
  rationale: string;
  notKnownReason: string;
  record: ServiceRecord;
  attribution: string;
  attributionReason: string;
  useEnvironment: string;
  useEnvironmentText: string;
  userType: string;
  userTypeText: string;
  changeReason: string;
  password: string;
  code: string;
};

const EMPTY_RECORD: ServiceRecord = {
  troubleshooting: "",
  correction_type: "",
  correction: "",
  result: "",
  service_ticket: "",
  no_investigation_rationale: "",
};

/** The form as the screen opens, in the tree's order: a met trigger escalates; otherwise a matching open
 * investigation is pre-selected as the known issue (the board's "Link to the open investigation"); otherwise service
 * level (the routine path's default). The classification as proposed (Unknown when nothing is proposed, never a guess). */
export function formOf(screen: DispositionScreen): DispositionForm {
  const proposed = screen.classification;
  const known = screen.trigger_codes.length ? undefined : screen.candidates[0];
  return {
    branch: screen.trigger_codes.length ? "ESCALATED_BY_TRIGGER" : known ? "KNOWN_ISSUE" : "SERVICE_LEVEL",
    caseId: known?.id ?? "",
    rationale: "",
    notKnownReason: "",
    record: { ...EMPTY_RECORD },
    attribution: "",
    attributionReason: "",
    useEnvironment: proposed.use_environment,
    useEnvironmentText: proposed.use_environment_text ?? "",
    userType: proposed.user_type,
    userTypeText: proposed.user_type_text ?? "",
    changeReason: "",
    password: "",
    code: "",
  };
}

const short = (value: string, min: number) => value.trim().replace(/\s+/g, " ").length < min;

/** Why the signature cannot be sent yet, in the server's words; null when it can. */
export function signProblem(screen: DispositionScreen, form: DispositionForm, trained: boolean): string | null {
  const { reasonMin, rationaleMin } = DISPOSITION_LIMITS;
  const triggered = screen.trigger_codes.length > 0;
  if (triggered && form.branch !== "ESCALATED_BY_TRIGGER") return "A trigger is met: the complaint is escalated.";
  if (form.branch === "KNOWN_ISSUE" && !screen.candidates.some((item) => item.id === form.caseId))
    return "Choose the open investigation this complaint belongs to.";
  if (form.branch !== "SERVICE_LEVEL" && short(form.rationale, reasonMin))
    return `Write your reason in at least ${reasonMin} characters.`;
  if (
    !triggered &&
    screen.candidates.length > 0 &&
    form.branch !== "KNOWN_ISSUE" &&
    short(form.notKnownReason, reasonMin)
  )
    return "An open investigation matches: say why this is not that known issue.";
  if (form.branch === "SERVICE_LEVEL") {
    const record = form.record;
    if (short(record.troubleshooting, reasonMin)) return "Describe the troubleshooting done.";
    if (!record.correction_type) return "Choose the correction.";
    if (short(record.correction, reasonMin)) return "Describe the correction.";
    if (short(record.result, 5)) return "Say what the correction achieved.";
    // B7-D3: a ticket only when service work was done on the device.
    if (TICKET_CORRECTIONS.includes(record.correction_type) && !record.service_ticket.trim())
      return "Give the service ticket reference.";
    if (short(record.no_investigation_rationale, rationaleMin))
      return `Write why no investigation is needed (${screen.no_investigation_clause}).`;
    if (!form.attribution) return "Choose the root-cause attribution.";
    if (form.attribution === "UNDETERMINED" && short(form.attributionReason, reasonMin))
      return "Undetermined: say why the cause cannot be attributed.";
  }
  if (form.useEnvironment === "OTHER" && !form.useEnvironmentText.trim())
    return 'Say what the "other" place of use is.';
  if (form.userType === "OTHER" && !form.userTypeText.trim()) return 'Say what the "other" user is.';
  if (screen.current && short(form.changeReason, reasonMin)) return "Say why the disposition changes.";
  if (!trained) return "Record the practice training first.";
  if (!form.password) return "Enter your password to sign.";
  if (screen.code_required && !/^\d{6}$/.test(form.code.trim()))
    return "Enter the 6-digit code from your authenticator app.";
  return null;
}

/** What the signature sends, with what the person saw (the triggers, the version, when the screen opened). */
export function signBody(screen: DispositionScreen, form: DispositionForm) {
  const service = form.branch === "SERVICE_LEVEL";
  return {
    branch: form.branch,
    case_id: form.branch === "KNOWN_ISSUE" ? form.caseId : null,
    rationale: form.rationale,
    not_known_reason: form.notKnownReason,
    service_record: service ? form.record : null,
    attribution: service ? form.attribution : null,
    attribution_reason: service ? form.attributionReason : "",
    classification: {
      use_environment: form.useEnvironment,
      use_environment_text: form.useEnvironment === "OTHER" ? form.useEnvironmentText : null,
      user_type: form.userType,
      user_type_text: form.userType === "OTHER" ? form.userTypeText : null,
    },
    change_reason: form.changeReason,
    seen_triggers: screen.trigger_codes,
    seen_version: screen.version,
    routine: screen.routine.offered && (form.branch === "SERVICE_LEVEL" || form.branch === "KNOWN_ISSUE"),
    opened_at: screen.opened_at,
    password: form.password,
    mfa_code: form.code || null,
  };
}

export type QuestionState = "taken" | "refused" | "no" | "open";

/** Each question of the decision tree with its state for the branch chosen: the visible flow (F4.2). */
export function treeStates(screen: DispositionScreen, branch: Branch): Record<string, QuestionState> {
  if (screen.trigger_codes.length)
    return { TRIGGER: "taken", KNOWN_ISSUE: "refused", SERVICE_LEVEL: "refused", CHOICE: "refused" };
  const order = ["KNOWN_ISSUE", "SERVICE_LEVEL", "ESCALATED_BY_CHOICE"];
  const at = order.indexOf(branch);
  const state = (index: number): QuestionState => (index < at ? "no" : index === at ? "taken" : "open");
  return { TRIGGER: "no", KNOWN_ISSUE: state(0), SERVICE_LEVEL: state(1), CHOICE: state(2) };
}

/** "4 min 5 s", against the routine path's target. */
export function handsOnText(seconds: number | null | undefined): string | null {
  if (seconds == null) return null;
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes} min ${seconds % 60} s` : `${seconds} s`;
}

/** What the one signature covers, listed on the signing step. */
export function covers(screen: DispositionScreen, branch: Branch): string[] {
  const items = [`The disposition: ${BRANCH_LABELS[branch].toLowerCase()}`, "The classification, confirmed"];
  if (screen.routine.offered && (branch === "SERVICE_LEVEL" || branch === "KNOWN_ISSUE"))
    for (const market of screen.routine.markets) items.push(`${market.label}: not reportable (routine basis)`);
  return items;
}
