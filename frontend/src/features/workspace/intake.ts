// The first contact, urgent intake and triage, and duplicates (0.10.57; T-G32, T-G19, T-G20): the API's shapes and
// the plain helpers the screens use (backend/app/intake/router.py decides; nothing here decides an outcome).

import type { Tone } from "../admin/console/dashboardModel";
import { deadlineLabel, timeLeft, type DueLike } from "../../app/dates";

export const INTAKE = "/api/v1/intake";
export const TRIAGE = "/api/v1/triage";
export const REASON_MIN = 10;

export type Answer = "YES" | "NO" | "UNKNOWN" | "NOT_APPLICABLE" | "NOT_STATED";
export type Outcome =
  "COMPLAINT" | "BOTH" | "SERVICE_ONLY" | "INQUIRY" | "PENDING" | "PENDING_CONFIRM" | "NOT_A_COMPLAINT";
/** One of the six classifications the Case check offers (spec 4.4), with why it is disabled (null: it may be signed). */
export type Choice = {
  code: Outcome;
  label: string;
  suggested: boolean;
  escalates: boolean;
  disabled_reason: string | null;
};
/** What was said later, and by whom (IN-17). */
export type Addendum = {
  id: string;
  kind: string;
  said_by_role: string;
  said_at: string | null;
  text: string;
  masked: boolean;
  added_by: string | null;
  added_at: string | null;
};
export type Answers = Record<string, { answer: Answer | null; note: string }>;
export type Flag = { code: string; label: string; question?: string; words?: string[] };

export type Guide = {
  version: string;
  questions: { id: string; text: string; not_stated: boolean; free_text: boolean }[];
  answers: { code: Answer; label: string }[];
  note: string;
  outcomes: { code: Outcome; label: string }[];
  table: { row: number; answers: string; outcome: string }[];
  requests: { code: string; label: string }[];
  use_environments: { code: string; label: string }[];
  user_types: { code: string; label: string }[];
  harm_words: { version: string; words: string[] };
  fault_words: { version: string; words: string[] };
  levels: { code: string; label: string }[];
  // 0.10.93 (B2): S-1 issue categories, ID-1 identifiers (labels, which allow Not sure, sources), the Case states.
  issue_categories?: { code: string; label: string }[];
  // Spec 4.2 (B2): how it came in, and the patients involved.
  channels?: { code: string; label: string }[];
  patients?: { code: string; label: string }[];
  identifiers?: {
    keys: { code: string; label: string }[];
    not_sure: string[];
    sources: { code: string; label: string }[];
  };
  states?: { code: string; label: string }[];
  /** The time zones a call's times are entered in (current names), and old names with their current one. */
  zones?: string[];
  zone_aliases?: Record<string, string>;
  starter_mark: string;
};

export type Task = {
  id: string;
  type: string;
  title: string;
  status: string;
  open: boolean;
  due_at: string | null;
  overdue: boolean;
  outcome: string | null;
  details: Record<string, unknown>;
};

export type CheckVersion = {
  id: string;
  version: number;
  classification: Outcome | null;
  classification_label: string | null;
  override_reason: string | null;
  reason: string | null;
  signed_by: string | null;
  signed_at: string | null;
  superseded: boolean;
  review_outcome: "AGREED" | "RECLASSIFIED" | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  same_person: boolean;
};

export type Side = {
  kind: "INTAKE" | "COMPLAINT";
  id: string;
  ref: string;
  source: string;
  product_name: string | null;
  words: string;
  event_at: string | null;
  awareness_at: string;
  awareness_source: string | null;
};
export type Duplicate = { left: Side; right: Side; reasons: string[] };

export type LinkView = {
  id: string;
  state: "LINKED" | "DISMISSED" | "UNLINKED";
  other: { kind: string; id: string; ref: string };
  reason: string;
  decided_by: string;
  decided_at: string;
  awareness_before: string | null;
  awareness_after: string | null;
  conflict: boolean;
  undo_reason: string | null;
  undone_at: string | null;
};

export type IntakeItem = {
  id: string;
  reference: string;
  kind: "CONTACT" | "URGENT" | "SERVICE_RECORD";
  kind_label: string;
  reporter_words: string;
  /** B7: "May not be English" (the harm-word check reads English only), and an imported old call's note. */
  language_note?: string | null;
  backlog_note?: string | null;
  reporter_type: string | null;
  reporter_site: string | null;
  country: string | null;
  product_name: string | null;
  /** PV-1 F2: no product was chosen; it is the lot's product. */
  product_from_lot?: boolean;
  lot: string | null;
  requested_label: string | null;
  times: Record<string, { at: string | null; zone: string | null }>;
  awareness: { at: string; source: string; source_label: string | null; unresolved: boolean; label: string | null };
  flags: Flag[];
  flagged: boolean;
  qms_ref: string | null;
  service_ticket: string | null;
  /** B6a G18b: why the Case was entered more than 24 h after awareness. */
  late_entry_reason?: string | null;
  sample: boolean;
  created_by: string | null;
  created_at: string;
  version: number;
  answers: Answers;
  unknowns: string | null;
  suggestion: Outcome | null;
  suggestion_label: string | null;
  outcome_row: number | null;
  draft: boolean;
  signed: CheckVersion | null;
  check_due_at: string | null;
  tasks: Task[];
  qms_task: (Task & { state: "OPEN" | "AWAITING_IMPORT" | "CLOSED" | "NOT_NEEDED"; label: string }) | null;
  history?: CheckVersion[];
  links?: LinkView[];
  duplicates?: Duplicate[];
  fault_words?: string[];
  harm_words?: string[];
  // 0.10.93 (B2): the stored state, the identifiers (ID-1, S-3), what is missing and the header (A3).
  status?: string;
  status_label?: string | null;
  identifiers?: Identifiers;
  issue_category_label?: string | null;
  resolution_summary?: string | null;
  missing?: { code: string; label: string }[];
  header?: CaseHeader;
  not_in_master?: string[];
  // Spec 4.4/4.5: what was said later, the six classifications, the provisional clock and the escalation's choices.
  addenda?: Addendum[];
  choices?: Choice[] | null;
  clock?: Deadline | null;
  /** B6a P1: ``wording_only``, found by similar wording alone: offered, never pre-selected. */
  likely_complaints?: { id: string; ref: string; reasons: string[]; same_day?: boolean; wording_only?: boolean }[];
  /** Spec 9.3: signed a complaint before 0.10.93 and never escalated: "Signed before 0.10.93: escalate". */
  escalate_signed?: boolean;
  complaint_id?: string | null;
  complaint_ref?: string | null;
  row_version?: number;
};
export type Deadline = {
  market: string;
  label: string;
  /** The event's own market first; the others only "if also reportable"; a signed conclusion replaces its market's. */
  role: "OWN" | "IF_ALSO" | "SIGNED" | "NO_COUNTRY" | "OWN_NO_WINDOW";
  role_label: string;
  own: boolean;
  not_reportable: boolean;
  tier: string;
  tier_label: string;
  days: number | null;
  day_basis: "CALENDAR" | "WORK" | null;
  basis: string;
  /** Check 3a: until triage answers it, the earliest possible report, "2 days unless a public health threat is ruled out". */
  earliest_note?: string | null;
  due_date: string | null;
  due_at: string | null;
  due_zone: string | null;
  /** "Mon 30 Nov 2026, 23:59 IST": the end of the deadline in the time zone that binds. */
  due_label: string | null;
  days_left: number | null;
  state: "OVERDUE" | "DUE_SOON" | "RUNNING" | null;
};
export type TriageRecordView = {
  severity: string | null;
  severity_label: string | null;
  public_health_threat: boolean;
  remedial_action: boolean;
  event_owner_name: string | null;
  triage_owner_name: string | null;
  backup_owner_name: string | null;
  immediate_action: string | null;
  no_action_reason: string | null;
  awareness_confirmed_at: string | null;
  escalated_by: string | null;
  escalation_reason: string | null;
  completed_by: string | null;
  completed_at: string | null;
  // 0.10.93 (B2, T-D9): the triage done in the QMS, and who confirmed it here.
  source_system?: string | null;
  qms_triaged_at?: string | null;
  qms_owner_text?: string | null;
  confirmed_by?: string | null;
  confirmed_at?: string | null;
  // 0.10.93 (B2): owners by id (the form starts from them), versions, two speeds, containment, the threat exclusion.
  event_owner?: string | null;
  triage_owner?: string | null;
  backup_owner?: string | null;
  version?: number;
  speed?: TriageSpeed | null;
  potential_severity?: string | null;
  containment?: { choices: string[]; text: string } | null;
  threat_excluded_at?: string | null;
};
export type TriageSpeed = "FAST" | "ROUTINE";
/** The facts triage decides on (backend intake/triage_rules.py ``facts``). */
export type TriageFacts = Record<
  "urgent" | "death" | "serious_injury" | "harm" | "harm_unknown" | "malfunction" | "serious_potential" | "threat",
  boolean
>;
export type TriageItem = {
  key: string;
  kind: "INTAKE" | "COMPLAINT" | "QUARANTINE";
  id: string;
  ref: string;
  identifier?: string | null;
  /** The MDARIX ID, shown only as "also known as" in the drawer when `ref` is the customer's own. */
  business_id?: string | null;
  source: string;
  intake_kind: string | null;
  product_name: string | null;
  lot: string | null;
  words: string;
  problems: string[] | null;
  classification: Outcome | null;
  suggestion: Outcome | null;
  sample: boolean;
  flags: Flag[];
  tier: "THREAT" | "FLAGGED" | "UNFLAGGED";
  tier_label: string;
  linked: { kind: string; id: string; ref: string }[];
  awareness: {
    at: string;
    /** 0.10.81 (U-06): a day given without a time, shown as a date. */
    date_only?: boolean;
    source: string;
    source_label: string;
    linked_ref: string | null;
    unresolved: boolean;
    label: string | null;
  };
  available_at: string;
  delay: { hours: number; text: string };
  triage_clock: { from: string; target_hours: number; due_at: string; hours_left: number; state: string };
  deadlines: Deadline[];
  conflict: { link: string; before: string | null; after: string | null }[];
  record: TriageRecordView | null;
  // 0.10.93 (B2, spec 3.4 and 4.7): the speed and why, the facts, the floor, the acknowledgement (A1), the routine card.
  speed?: TriageSpeed;
  speed_label?: string;
  speed_why?: string;
  facts?: TriageFacts;
  severity_floor?: string | null;
  floor_note?: string | null;
  acknowledgement?: {
    required: boolean;
    done: boolean;
    due_at: string;
    overdue: boolean;
    acknowledged_by: string | null;
  };
  /** T-D9: a triage imported from the QMS on a flagged record, waiting for a person ("From your QMS: confirm"). */
  qms_to_confirm?: boolean;
  /** OD-12 + 3a: an old flagged import, Imported backlog work: off "To triage", the backlog target, no market clock. */
  backlog?: boolean;
  backlog_note?: string | null;
  routine_prefill?: {
    severity: string;
    harm_now_label: string;
    containment: string[];
    no_action_reason: string;
    triage_owner: string | null;
  } | null;
};
/** GET /intake/triage/backlog (OD-12, TR-21): the "Imported backlog" view. */
export type ImportedBacklogList = {
  summary: { total: number; flagged?: number; overdue: number; backlog_days: number; target_days: number };
  page: number;
  pages: number;
  truncated: boolean;
  items: {
    kind: "COMPLAINT";
    id: string;
    ref: string;
    identifier: string | null;
    product_name: string | null;
    words: string | null;
    awareness_at: string;
    imported_at: string;
    due_at: string;
    overdue: boolean;
    /** Owner, 10 Nov (OD-12 + 3a): an old flagged import keeps its flags, listed first, with the QMS note. */
    flags?: Flag[];
    note?: string | null;
    /** Section Q decision 2: an old flagged import whose QMS triage waits for a person ("Confirm QMS triage"). */
    qms_to_confirm?: boolean;
  }[];
};
export type TriageList = {
  items: TriageItem[];
  summary: { open: number; done: number; conflicts: number };
  /** B6a run 4, a paged read (``limit``): the list's items (backlog apart), those past the triage target, the asked one. */
  total?: number;
  overdue?: number;
  wanted?: TriageItem | null;
  people: { id: string; name: string }[];
  enabled_markets: string[];
  starter_mark: string;
  now: string;
};

export const OUTCOME_TONES: Record<Outcome, Tone> = {
  COMPLAINT: "serious",
  BOTH: "serious",
  SERVICE_ONLY: "good",
  INQUIRY: "good",
  PENDING: "warning",
  PENDING_CONFIRM: "warning",
  NOT_A_COMPLAINT: "good",
};
/** Every guide question answered (the server refuses to sign otherwise). */
export const unanswered = (answers: Answers, questions: Guide["questions"]) =>
  questions.filter((q) => !q.free_text && !answers[q.id]?.answer).map((q) => q.id);

/** A blank set of answers for the guide's questions 1-9. */
export function blankAnswers(questions: Guide["questions"]): Answers {
  return Object.fromEntries(questions.filter((q) => !q.free_text).map((q) => [q.id, { answer: null, note: "" }]));
}

/** The answers a question may take: Not stated only on questions 4-6. */
export const answerChoices = (guide: Guide, question: Guide["questions"][number]) =>
  guide.answers.filter((item) => item.code !== "NOT_STATED" || question.not_stated);

// The outcomes only the answers give, and those a second person reviews (backend case_rules ANSWER_ONLY, REVIEWED_OUTCOMES).
const ANSWER_ONLY: Outcome[] = ["SERVICE_ONLY", "INQUIRY", "PENDING_CONFIRM", "NOT_A_COMPLAINT"];
const REVIEWED: Partial<Record<Outcome, string>> = {
  SERVICE_ONLY: "Service only",
  INQUIRY: "Inquiry",
  NOT_A_COMPLAINT: "Not a complaint (no deficiency confirmed)",
};

/** Why the signature cannot go yet, in the server's words, or null. */
export function signProblem(
  item: Pick<IntakeItem, "suggestion"> & { choices?: Choice[] | null },
  form: { classification: Outcome | ""; override: string; reason: string; password: string },
  missing: string[],
): string | null {
  if (missing.length)
    return `Answer every question first (${missing.map((q) => q.replace("Q", "question ")).join(", ")})`;
  if (!form.classification) return "Choose the classification";
  const choice = item.choices?.find((entry) => entry.code === form.classification);
  if (choice?.disabled_reason) return choice.disabled_reason;
  if (ANSWER_ONLY.includes(form.classification) && form.classification !== item.suggestion)
    return "That outcome is offered only when the answers give it";
  if (form.classification !== item.suggestion && form.override.trim().length < REASON_MIN)
    return `You override the suggestion: say why in at least ${REASON_MIN} characters`;
  const reviewed = REVIEWED[form.classification];
  if (reviewed && form.reason.trim().length < REASON_MIN)
    return `"${reviewed}" needs a written reason of at least ${REASON_MIN} characters`;
  if (!form.password) return "Enter your password to sign";
  return null;
}

/** "4 h left", "6 h overdue", "3 days left": the app's one helper (app/dates.ts timeLeft), overdue from the state. */
export const hoursText = (clock: Pick<DueLike, "state" | "due_at" | "hours_left">) => timeLeft(clock);

/** A legal deadline with its time zone and the time left: "Sat 7 Nov 2026, 23:59 IST (6 days left)". */
export const deadlineText = (deadline: Deadline) =>
  deadline.not_reportable ? "Concluded not reportable" : `${deadlineLabel(deadline)} (${timeLeft(deadline)})`;

export const clockTone = (state: string): Tone =>
  state === "OVERDUE" ? "critical" : state === "DUE_SOON" ? "warning" : "neutral";

export const tierTone = (tier: TriageItem["tier"]): Tone =>
  tier === "THREAT" ? "critical" : tier === "FLAGGED" ? "serious" : "warning";

/** The body of a link decision between the two sides of a warning. */
export const linkBody = (pair: Duplicate, decision: "LINKED" | "DISMISSED", reason: string) => ({
  left_kind: pair.left.kind,
  left_id: pair.left.id,
  right_kind: pair.right.kind,
  right_id: pair.right.id,
  decision,
  reason: reason.trim(),
});

/** How much earlier a link moved the awareness, in days (0 when it did not). */
export function daysEarlier(before: string | null, after: string | null): number {
  if (!before || !after) return 0;
  return Math.max(0, Math.round((Date.parse(before) - Date.parse(after)) / 86_400_000));
}

/** A datetime-local input's value for an ISO time (local), and back. */
export const toLocalInput = (iso: string | null) => {
  if (!iso) return "";
  const date = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(
    date.getMinutes(),
  )}`;
};
export const fromLocalInput = (value: string) => (value ? new Date(value).toISOString() : null);

/**
 * The triage record's awareness field (0.10.84, M7). A day given without a time stays a day: a date field, saved as
 * the server keeps such a day (12:00 UTC), never a time nobody recorded ("05:30 PM" where it is 12:00 UTC). An awareness
 * later than the earliest known is ``later``, so its reason is asked before saving, not after a refusal.
 */
export function awarenessInput(awareness: Pick<TriageItem["awareness"], "at" | "date_only">) {
  const day = !!awareness.date_only;
  const initial = day ? (awareness.at ?? "").slice(0, 10) : toLocalInput(awareness.at);
  const moment = (value: string) => (!value ? null : day ? `${value}T12:00:00.000Z` : fromLocalInput(value));
  const later = (value: string) => {
    const at = moment(value);
    return !!at && !!awareness.at && Date.parse(at) > Date.parse(awareness.at);
  };
  return { type: day ? ("date" as const) : ("datetime-local" as const), day, initial, moment, later };
}

/** "2026-11-02T09:00": the wall clock in ``zone`` at ``now``, for a datetime-local input (J28). */
export function zonedInput(now: Date, zone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "00";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

/** The call's time zone to start with: the browser's, by its current name when the guide lists it, else UTC. */
export function startingZone(guide: Pick<Guide, "zones" | "zone_aliases">, browser: string): string {
  const zone = guide.zone_aliases?.[browser] ?? browser;
  return !guide.zones || guide.zones.includes(zone) ? zone : "UTC";
}

// ------------------------------------------------------------------ triage at two speeds (0.10.93, B2 step 5)
// These mirror backend intake/triage_rules.py so the form asks before saving instead of failing with a 422; the
// server still decides.

export const NOT_KNOWN = "NOT_KNOWN";
/** Containment choices (triage_rules.CONTAINMENT), in the form's order. */
export const CONTAINMENT: readonly { code: string; label: string }[] = [
  { code: "NONE_NEEDED", label: "None needed" },
  { code: "USER_TOLD", label: "User told how to stay safe" },
  { code: "OUT_OF_USE", label: "Device taken out of use" },
  { code: "HOLD_LOT", label: "Hold the lot" },
  { code: "FIELD_ACTION", label: "Consider a field action" },
  { code: "OTHER", label: "Other" },
];

/** The harm scale a triage chooses from: "Not known yet", then the guide's levels (lowest first). */
export const harmScale = (levels: Guide["levels"]) => [{ code: NOT_KNOWN, label: "Not known yet" }, ...levels];

/** A level's place on the scale; "Not known yet" and nothing rank below the lowest level. */
export const harmRank = (levels: Guide["levels"], code: string | null | undefined) =>
  levels.findIndex((level) => level.code === code);

export type TriageForm = {
  severity: string;
  potential: string;
  threat: boolean;
  threatReason: string;
  remedial: boolean;
  remedialReason: string;
  eventOwner: string;
  triageOwner: string;
  backup: string;
  containment: string[];
  text: string;
  aware: string;
  awareNote: string;
  changeReason: string;
  password: string;
  mfa: string;
};

/** The speed the answers give (triage_rules.speed): fast by the facts, or by "Not known yet" or a serious potential. */
export function triageSpeed(item: Pick<TriageItem, "speed">, levels: Guide["levels"], form: TriageForm): TriageSpeed {
  const serious = harmRank(levels, "SERIOUS");
  return item.speed === "FAST" ||
    form.severity === NOT_KNOWN ||
    (serious >= 0 && harmRank(levels, form.potential) >= serious)
    ? "FAST"
    : "ROUTINE";
}

/** A6: a saved fast-track triage made less severe needs a second person (outside the trial) or a signature (trial). */
export function triageDowngrade(
  record: TriageRecordView | null,
  levels: Guide["levels"],
  form: TriageForm,
  speed: TriageSpeed,
) {
  if (!record?.completed_at || record.speed !== "FAST") return false;
  return (
    harmRank(levels, form.severity) < harmRank(levels, record.severity) ||
    harmRank(levels, form.potential) < harmRank(levels, record.potential_severity) ||
    speed === "ROUTINE"
  );
}

/** Why the triage cannot be saved yet, in the server's words, or null (the order the server checks in). */
export function triageProblem(
  item: Pick<TriageItem, "speed" | "facts" | "severity_floor" | "record">,
  levels: Guide["levels"],
  form: TriageForm,
  context: { people: number; needsAwareness: boolean; laterAware: boolean; signs: boolean },
): string | null {
  const floor = item.severity_floor ? harmRank(levels, item.severity_floor) : -1;
  const floorLabel = levels.find((level) => level.code === item.severity_floor)?.label;
  const record = item.record;
  const updating = !!record?.completed_at;
  const lowered = updating && harmRank(levels, form.severity) < harmRank(levels, record?.severity);
  if (!form.severity) return "Choose the harm now: Not known yet or a level on the harm scale";
  if (floor >= 0 && harmRank(levels, form.severity) < floor) return `At least ${floorLabel}: the facts set that floor`;
  if (item.facts?.malfunction && !form.potential)
    return "Harm if it happened again: asked whenever a malfunction is alleged (worst credible)";
  if (item.facts?.death && !form.threat && form.threatReason.trim().length < REASON_MIN)
    return "A death is recorded: answer 'Possible serious public health threat' with a reason";
  if (!form.eventOwner || !form.triageOwner) return "Name the event owner and the triage owner";
  if (triageSpeed(item, levels, form) === "FAST" && context.people >= 2 && !form.backup)
    return "Name a backup: two or more people are active";
  if (!form.containment.length) return "Choose the containment, or None needed";
  if (form.text.trim().length < REASON_MIN)
    return `Say what was done, or why nothing is needed (at least ${REASON_MIN} characters)`;
  if (context.needsAwareness && !form.aware) return "Confirm the awareness time";
  if (context.laterAware && form.awareNote.trim().length < REASON_MIN)
    return `Say why the awareness is later than the earliest known (at least ${REASON_MIN} characters)`;
  if (record?.remedial_action && !form.remedial && form.remedialReason.trim().length < REASON_MIN)
    return "Say why remedial action is no longer thought to be needed";
  if ((updating || lowered) && form.changeReason.trim().length < REASON_MIN)
    return `Say in at least ${REASON_MIN} characters why the triage changes`;
  if (context.signs && !form.password) return "Sign with your password";
  return null;
}

/** The body POST /triage/{kind}/{id}/record takes. "None needed" alone sends the text as the reason for no action. */
export function triageBody(form: TriageForm, record: TriageRecordView | null, awareness: string | null) {
  const none = form.containment.length === 1 && form.containment[0] === "NONE_NEEDED";
  return {
    severity: form.severity,
    potential_severity: form.potential,
    public_health_threat: form.threat,
    threat_reason: form.threat ? "" : form.threatReason.trim(),
    remedial_action: form.remedial,
    remedial_reason: form.remedialReason.trim(),
    event_owner: form.eventOwner,
    triage_owner: form.triageOwner,
    backup_owner: form.backup,
    containment: form.containment,
    immediate_action: none ? "" : form.text.trim(),
    no_action_reason: none ? form.text.trim() : "",
    awareness_confirmed_at: awareness,
    awareness_note: form.awareNote,
    change_reason: form.changeReason.trim(),
    seen_version: record?.version ?? 0,
    password: form.password,
    mfa_code: form.mfa.trim() || null,
  };
}

// ------------------------------------------------------------------ the Case's device identifiers (ID-1, S-3)

/** One identifier's entry as the server keeps it (case_rules.clean_identifiers). */
export type IdentifierEntry = { not_sure: boolean; status: "CONFIRMED" | "UNCONFIRMED"; source: string };
export type Identifiers = Record<string, IdentifierEntry>;
export const NEW_IDENTIFIER: IdentifierEntry = { not_sure: false, status: "UNCONFIRMED", source: "CALLER" };

/** "Acting for you?" (rules.FIRST_KNOWLEDGE_BASES), with the spec's labels. */
export const FIRST_KNOWLEDGE_BASES: readonly [string, string][] = [
  ["ACTS_FOR_MANUFACTURER", "Yes, they act for us"],
  ["PROCEDURE_DEEMS", "Our procedure counts them"],
  ["NOT_ACTING_FOR", "No"],
];

/** The chip an identifier shows: Not sure, Confirmed or Unconfirmed; none while it has no value. */
export function identifierChip(
  entry: IdentifierEntry | undefined,
  given: boolean,
): { label: string; tone: Tone } | null {
  if (entry?.not_sure) return { label: "Not sure", tone: "warning" };
  if (!given) return null;
  return entry?.status === "CONFIRMED"
    ? { label: "Confirmed", tone: "good" }
    : { label: "Unconfirmed", tone: "warning" };
}

/** ID-2: one shipment to the caller's hospital (GET /intake/shipped-to, intake.service.shipped_to). */
export type ShippedItem = {
  site: string;
  consignee: string;
  country: string;
  ship_date: string;
  quantity: number;
  lot: string;
  version: string | null;
  product_id: string | null;
  product_name: string | null;
};
export type ShippedTo = {
  sites: { site: string; consignee: string; country: string }[];
  items: ShippedItem[];
  truncated: boolean;
};
const FROM_SHIPMENT: IdentifierEntry = { not_sure: false, status: "UNCONFIRMED", source: "SHIPMENT_RECORD" };

/** ID-2: choosing a shipment fills the lot, and the product and version it names, each unconfirmed, source: shipment
 * record. The person can still change anything. */
export function shipmentPick(item: ShippedItem, ids: Identifiers): { product?: string; lot: string; ids: Identifiers } {
  const picked: Identifiers = { ...ids, lot: FROM_SHIPMENT };
  if (item.product_id) picked.product = FROM_SHIPMENT;
  if (item.version) picked.version = FROM_SHIPMENT;
  return { ...(item.product_id ? { product: item.product_id } : {}), lot: item.lot, ids: picked };
}

/** A value typed over a shipment pick is no longer from the shipment record: its entry goes back to the default (a
 * "Not sure" the person ticked stays). */
export function typedOver(ids: Identifiers, ...codes: string[]): Identifiers {
  const kept = { ...ids };
  for (const code of codes) if (kept[code]?.source === "SHIPMENT_RECORD" && !kept[code].not_sure) delete kept[code];
  return kept;
}

// ------------------------------------------------------------------ the Cases list (A5) and the Case header (A3)

export type CaseHeader = {
  owner: string | null;
  next_action: string | null;
  due_at: string | null;
  overdue: boolean;
  reason: string | null;
  missing: { code: string; label: string }[];
  escalation: {
    state: "ESCALATED" | "URGENT" | "TRIAGE" | "TRIAGED" | "NONE";
    label: string;
    complaint_id: string | null;
  };
};
export type CaseRow = {
  id: string;
  reference: string;
  kind: IntakeItem["kind"];
  sample: boolean;
  received_at: string;
  words: string;
  product_name: string | null;
  lot: string | null;
  not_in_master: string[];
  status: string;
  status_label: string | null;
  classification_label: string | null;
  suggestion_label: string | null;
  issue_category_label: string | null;
  flagged: boolean;
  complaint_ref: string | null;
  header: CaseHeader;
};
export type CasePage = {
  items: CaseRow[];
  total: number;
  page: number;
  size: number;
  view: string;
  views: { code: string; label: string }[];
  counts: Record<string, number>;
  people: { id: string; name: string }[];
};
/** The views "Which cases" offers first (spec 4.3); the rest (A5) are under More views. */
export const CASE_VIEWS_FIRST = [
  "to_check",
  "waiting_reporter",
  "qa_review",
  "became_complaints",
  "closed",
  "withdrawn",
  "all",
];
/** The address of one page of the Cases list. */
export const casesPath = (view: string, q: string, page: number, size = 25) =>
  `${INTAKE}/cases?view=${encodeURIComponent(view)}&q=${encodeURIComponent(q.trim())}&page=${page}&size=${size}`;
