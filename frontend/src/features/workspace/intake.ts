// The first contact, urgent intake and triage, and duplicates (0.10.57; T-G32, T-G19, T-G20): the API's shapes and
// the plain helpers the screens use (backend/app/intake/router.py decides; nothing here decides an outcome).

import type { Tone } from "../admin/console/dashboardModel";
import { deadlineLabel, timeLeft, type DueLike } from "../../app/dates";

export const INTAKE = "/api/v1/intake";
export const TRIAGE = "/api/v1/triage";
export const REASON_MIN = 10;

export type Answer = "YES" | "NO" | "UNKNOWN" | "NOT_APPLICABLE" | "NOT_STATED";
export type Outcome = "COMPLAINT" | "BOTH" | "SERVICE_ONLY" | "PENDING" | "PENDING_CONFIRM";
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
  reporter_type: string | null;
  reporter_site: string | null;
  country: string | null;
  product_name: string | null;
  lot: string | null;
  requested_label: string | null;
  times: Record<string, { at: string | null; zone: string | null }>;
  awareness: { at: string; source: string; source_label: string | null; unresolved: boolean; label: string | null };
  flags: Flag[];
  flagged: boolean;
  qms_ref: string | null;
  service_ticket: string | null;
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
  state?: IntakeState;
  history?: CheckVersion[];
  links?: LinkView[];
  duplicates?: Duplicate[];
  fault_words?: string[];
  harm_words?: string[];
};
export type IntakeState = "to_sign" | "pending" | "review" | "service_only" | "complaint";
export type IntakeList = {
  items: IntakeItem[];
  summary: Record<"all" | "flagged" | IntakeState, number>;
  duplicates: number;
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
};
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
};
export type TriageList = {
  items: TriageItem[];
  summary: { open: number; done: number; conflicts: number };
  people: { id: string; name: string }[];
  enabled_markets: string[];
  starter_mark: string;
  now: string;
};

export const OUTCOME_TONES: Record<Outcome, Tone> = {
  COMPLAINT: "serious",
  BOTH: "serious",
  SERVICE_ONLY: "good",
  PENDING: "warning",
  PENDING_CONFIRM: "warning",
};
export const STATE_LABELS: Record<IntakeState, string> = {
  to_sign: "To sign",
  pending: "Pending",
  review: "QA review due",
  service_only: "Service only",
  complaint: "Complaint",
};
export const INTAKE_SHOWS: readonly { value: "all" | IntakeState; label: string }[] = [
  { value: "all", label: "All" },
  { value: "to_sign", label: "To sign" },
  { value: "pending", label: "Pending" },
  { value: "review", label: "QA review due" },
  { value: "complaint", label: "Complaint or both" },
  { value: "service_only", label: "Service only" },
];

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

/** Why the signature cannot go yet, in the server's words, or null. */
export function signProblem(
  item: Pick<IntakeItem, "suggestion">,
  form: { classification: Outcome | ""; override: string; reason: string; password: string },
  missing: string[],
): string | null {
  if (missing.length)
    return `Answer every question first (${missing.map((q) => q.replace("Q", "question ")).join(", ")})`;
  if (!form.classification) return "Choose the classification";
  if (
    (form.classification === "SERVICE_ONLY" || form.classification === "PENDING_CONFIRM") &&
    form.classification !== item.suggestion
  )
    return "That outcome is offered only when the answers give it";
  if (form.classification !== item.suggestion && form.override.trim().length < REASON_MIN)
    return `You override the suggestion: say why in at least ${REASON_MIN} characters`;
  if (form.classification === "SERVICE_ONLY" && form.reason.trim().length < REASON_MIN)
    return `"Service only" needs a written reason of at least ${REASON_MIN} characters`;
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
