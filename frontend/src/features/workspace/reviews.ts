// Pure rules for a case's risk and regulatory reviews (Phase 5): how a review, its status and its outcome read, which
// outcomes each kind of review offers, what the review policy says, what each action sends, and how the review's
// context reads. The server owns every review and decides every action; reviewers decide the outcome, MDARIX only
// gathers the context.
import { titleCase, type Tone } from "../admin/console/dashboardModel";
import { safeText } from "../../app/displayId";
import { textProblem } from "./intelligence";

export const REVIEW_TYPES = ["RISK", "REGULATORY"] as const;
export type ReviewType = (typeof REVIEW_TYPES)[number];

export const REVIEW_TYPE_LABEL: Record<ReviewType, string> = {
  RISK: "Risk review",
  REGULATORY: "Regulatory review",
};

export const REVIEW_STATUSES = ["REQUESTED", "IN_PROGRESS", "COMPLETED", "CANCELLED", "SUPERSEDED"] as const;
export type ReviewStatus = (typeof REVIEW_STATUSES)[number];

export const REVIEW_STATUS: Record<ReviewStatus, { label: string; tone: Tone }> = {
  REQUESTED: { label: "Requested", tone: "warning" },
  IN_PROGRESS: { label: "In progress", tone: "warning" },
  COMPLETED: { label: "Completed", tone: "good" },
  CANCELLED: { label: "Cancelled", tone: "neutral" },
  SUPERSEDED: { label: "Superseded", tone: "neutral" },
};

/** The outcomes a reviewer may record, per kind of review, in the order they are offered. */
export const REVIEW_OUTCOMES: Record<ReviewType, ReadonlyArray<{ value: string; label: string; tone: Tone }>> = {
  RISK: [
    { value: "NO_CHANGE_REQUIRED", label: "No change to the risk file required", tone: "neutral" },
    { value: "RISK_FILE_REASSESSMENT_REQUIRED", label: "Risk file reassessment required", tone: "warning" },
    { value: "RISK_CONTROL_REVIEW_REQUIRED", label: "Risk control review required", tone: "warning" },
    { value: "ADDITIONAL_EVIDENCE_REQUIRED", label: "Additional evidence required", tone: "warning" },
    { value: "ESCALATE_SAFETY_CONCERN", label: "Escalate a safety concern", tone: "critical" },
  ],
  REGULATORY: [
    { value: "NO_REPORTABILITY_CONCERN_IDENTIFIED", label: "No reportability concern identified", tone: "neutral" },
    { value: "REPORTABILITY_ASSESSMENT_COMPLETE", label: "Reportability assessment complete", tone: "neutral" },
    { value: "REPORTING_REQUIRED", label: "Reporting required", tone: "serious" },
    { value: "TREND_REPORTING_REVIEW_REQUIRED", label: "Trend reporting review required", tone: "warning" },
    { value: "ADDITIONAL_EVIDENCE_REQUIRED", label: "Additional evidence required", tone: "warning" },
    { value: "ESCALATE_REGULATORY", label: "Escalate a regulatory concern", tone: "critical" },
  ],
};

export const RATIONALE_MIN = 20;
export const RATIONALE_MAX = 5000;
export const REVIEW_REASON_MIN = 10;
export const REVIEW_REASON_MAX = 1000;
export const REQUEST_REASON_MAX = 2000;

export type ReviewActions = { can_start?: boolean; can_complete?: boolean; can_recuse?: boolean; can_cancel?: boolean };

export type Review = {
  id: string;
  business_id?: string | null;
  review_type?: string | null;
  review_type_label?: string | null;
  status?: string | null;
  status_label?: string | null;
  required_by_policy?: boolean | null;
  policy_reasons?: unknown;
  requested_by_name?: string | null;
  request_reason?: string | null;
  reviewer?: { id?: string | null; name?: string | null } | null;
  reviewer_role_label?: string | null;
  outcome?: string | null;
  outcome_label?: string | null;
  rationale?: string | null;
  assessed?: { risk_ids?: unknown; markets?: unknown; notes?: unknown; findings?: unknown } | null;
  scope_version?: number | null;
  due_at?: string | null;
  overdue?: boolean | null;
  completed_at?: string | null;
  superseded_reason?: string | null;
  investigation?: {
    id?: string | null;
    business_id?: string | null;
    /** The reference people read (SAMPLE-INV-001), UX1. */
    identifier?: string | null;
    question?: string | null;
    workflow_state?: string | null;
    product?: { id?: string | null; business_id?: string | null; name?: string | null } | null;
  } | null;
  created_at?: string | null;
  actions?: ReviewActions | null;
};

export type ReviewDetail = Review & { context?: Record<string, unknown> | null };

export type ReviewPolicyPart = { required?: boolean | null; reasons?: unknown };
export type ReviewPolicy = { risk?: ReviewPolicyPart | null; regulatory?: ReviewPolicyPart | null };
export type CaseReviews = { items?: Review[] | null; policy?: ReviewPolicy | null };

export type ReviewSummaryCounts = Partial<
  Record<"risk_queue" | "regulatory_queue" | "mine_open" | "due_soon" | "overdue" | "completed_30d", number>
>;
export type ReviewSummary = {
  roles?: { risk?: unknown; regulatory?: unknown } | null;
  counts?: ReviewSummaryCounts | null;
  mine?: Review[] | null;
  queue?: Review[] | null;
};

const code = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

// ---------------------------------------------------------------------------------------------------------------
// Addresses

const enc = encodeURIComponent;
export const caseReviewsPath = (investigationId: string) => `/api/v1/investigations/${enc(investigationId)}/reviews`;
export const reviewPolicyPath = (investigationId: string) => `${caseReviewsPath(investigationId)}/policy`;
export type ReviewActionKey = "start" | "complete" | "recuse" | "cancel";
export const reviewPath = (reviewId: string, action?: ReviewActionKey) =>
  `/api/v1/case-reviews/${enc(reviewId)}${action ? `/${action}` : ""}`;
export const REVIEW_SUMMARY_PATH = "/api/v1/case-reviews/summary";

export function reviewListPath(options: {
  type?: ReviewType | "";
  box?: "mine" | "queue" | "all";
  status?: string;
  page?: number;
  pageSize?: number;
}): string {
  const params = new URLSearchParams();
  if (options.type) params.set("type", options.type);
  params.set("box", options.box ?? "mine");
  if (options.status) params.set("status", options.status);
  params.set("page", String(Math.max(1, options.page ?? 1)));
  params.set("page_size", String(options.pageSize ?? 50));
  return `/api/v1/case-reviews?${params}`;
}

// ---------------------------------------------------------------------------------------------------------------
// The Investigations tab that opens one review: "Reviews?review=<id>"

export const REVIEWS_TAB = "Reviews";
// A review reference as it may travel in a tab name; anything else is ignored.
const REVIEW_REF = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

/** The Investigations tab name that opens the Reviews tab, on one review when it is named. */
export function reviewsTab(review?: string | null): string {
  const ref = String(review ?? "").trim();
  return REVIEW_REF.test(ref) ? `${REVIEWS_TAB}?${new URLSearchParams({ review: ref })}` : REVIEWS_TAB;
}

/** The review a tab name passed to Investigations asks to open (see reviewsTab), or null. */
export function parseReviewsTab(value: string | null | undefined): string | null {
  const text = String(value ?? "");
  const mark = text.indexOf("?");
  if (mark < 0 || text.slice(0, mark) !== REVIEWS_TAB) return null;
  const ref = (new URLSearchParams(text.slice(mark + 1)).get("review") ?? "").trim();
  return REVIEW_REF.test(ref) ? ref : null;
}

// ---------------------------------------------------------------------------------------------------------------
// How a review reads

export function reviewType(review: Pick<Review, "review_type"> | null | undefined): ReviewType | null {
  const value = code(review?.review_type);
  return (REVIEW_TYPES as readonly string[]).includes(value) ? (value as ReviewType) : null;
}

export function reviewTypeLabel(review: Pick<Review, "review_type" | "review_type_label"> | null | undefined) {
  const type = reviewType(review);
  return safeText(review?.review_type_label) ?? (type ? REVIEW_TYPE_LABEL[type] : "Review");
}

export function reviewStatus(review: Pick<Review, "status"> | null | undefined): ReviewStatus | null {
  const value = code(review?.status);
  return (REVIEW_STATUSES as readonly string[]).includes(value) ? (value as ReviewStatus) : null;
}

export function reviewStatusView(review: Pick<Review, "status" | "status_label"> | null | undefined) {
  const status = reviewStatus(review);
  return {
    label:
      safeText(review?.status_label) ??
      (status ? REVIEW_STATUS[status].label : titleCase(String(review?.status ?? "Unknown"))),
    tone: status ? REVIEW_STATUS[status].tone : ("neutral" as Tone),
  };
}

/** A review still awaiting its reviewer's outcome. */
export const isOpenReview = (review: Pick<Review, "status"> | null | undefined) => {
  const status = reviewStatus(review);
  return status === "REQUESTED" || status === "IN_PROGRESS";
};

/** The outcomes a reviewer may record for this kind of review; none for an unknown kind. */
export const outcomesFor = (type: ReviewType | null) => (type ? REVIEW_OUTCOMES[type] : []);

/** The outcome as people read it: the server's label, else the known label for its type, else a readable code. */
export function outcomeView(review: Pick<Review, "outcome" | "outcome_label" | "review_type"> | null | undefined) {
  const value = code(review?.outcome);
  if (!value) return null;
  const known = outcomesFor(reviewType(review)).find((item) => item.value === value);
  return {
    label: safeText(review?.outcome_label) ?? known?.label ?? titleCase(value),
    tone: known?.tone ?? ("neutral" as Tone),
  };
}

/** The reviewer: the person, else the role queue the review waits in, else "Not assigned yet". */
export function reviewerText(review: Pick<Review, "reviewer" | "reviewer_role_label"> | null | undefined): string {
  const person = safeText(review?.reviewer?.name);
  const role = safeText(review?.reviewer_role_label);
  if (person) return role ? `${person} (${role})` : person;
  return role ? `${role} queue` : "Not assigned yet";
}

/** The policy's reasons, as written text (never an object or a code). */
export const reasonsOf = (value: unknown): string[] =>
  Array.isArray(value)
    ? value
        .map((item) =>
          typeof item === "string"
            ? item.trim()
            : (safeText((item as Record<string, unknown>)?.label) ??
              safeText((item as Record<string, unknown>)?.reason) ??
              ""),
        )
        .filter(Boolean)
    : [];

export type PolicyRow = { type: ReviewType; label: string; required: boolean | null; reasons: string[]; text: string };

/** What the review policy says for each kind of review, with its reasons. */
export function policyRows(policy: ReviewPolicy | null | undefined): PolicyRow[] {
  return REVIEW_TYPES.map((type) => {
    const part = type === "RISK" ? policy?.risk : policy?.regulatory;
    const required = typeof part?.required === "boolean" ? part.required : null;
    return {
      type,
      label: REVIEW_TYPE_LABEL[type],
      required,
      reasons: reasonsOf(part?.reasons),
      text:
        required === null
          ? "The policy did not say whether this review is required."
          : required
            ? "Required by your organization's review policy."
            : "Not required by the policy. It can still be requested.",
    };
  });
}

/** The open review of one kind on the case (requested or in progress), if any. */
export const openReviewOf = (reviews: Review[] | null | undefined, type: ReviewType) =>
  (reviews ?? []).find((review) => reviewType(review) === type && isOpenReview(review)) ?? null;

/** Reviews newest first (by when they were requested), the open ones first. */
export function sortReviews(reviews: Review[] | null | undefined): Review[] {
  const time = (review: Review) => {
    const value = review.created_at ? Date.parse(review.created_at) : Number.NaN;
    return Number.isNaN(value) ? 0 : value;
  };
  return [...(reviews ?? [])].sort((a, b) => Number(isOpenReview(b)) - Number(isOpenReview(a)) || time(b) - time(a));
}

// ---------------------------------------------------------------------------------------------------------------
// Actions: request, complete, recuse, cancel

/** Why a request for a review cannot be sent yet (its optional reason is too long), or null. */
export const requestReviewProblem = (reason: string) =>
  textProblem(reason, "a reason", { min: 0, max: REQUEST_REASON_MAX, required: false });

/** The body of POST /investigations/{id}/reviews; `dueAt` is the ISO due date, or null for none. */
export function requestReviewBody(type: ReviewType, reason: string, dueAt: string | null) {
  const text = reason.trim();
  return { review_type: type, ...(text ? { reason: text } : {}), ...(dueAt ? { due_at: dueAt } : {}) };
}

/** One finding of a risk review (T-G1aR): a risk in the risk file (did its control work?) or a new failure mode. */
export type Finding = { control: string; reason: string; ownerId: string; dueDay: string };
export type NewHazard = { description: string; ownerId: string; dueDay: string };
export const CONTROL_ANSWERS = [
  { value: "YES", label: "Yes, it worked" },
  { value: "NO", label: "No, it did not work" },
  { value: "NOT_ASSESSABLE", label: "Not assessable" },
] as const;
export const EMPTY_FINDING: Finding = { control: "", reason: "", ownerId: "", dueDay: "" };

export type CompleteForm = {
  outcome: string;
  rationale: string;
  riskIds: string[];
  markets: string[];
  notes: string;
  findings: Record<string, Finding>;
  newHazards: NewHazard[];
};
export const EMPTY_COMPLETE: CompleteForm = {
  outcome: "",
  rationale: "",
  riskIds: [],
  markets: [],
  notes: "",
  findings: {},
  newHazards: [],
};
export const NOTES_MAX = 5000;

/** Why the outcome cannot be recorded yet, or null when it can. The reviewer always chooses the outcome. */
export function completeProblem(type: ReviewType | null, form: CompleteForm): string | null {
  if (!form.outcome) return "Choose the outcome of your review.";
  if (!outcomesFor(type).some((item) => item.value === form.outcome))
    return "Choose one of the outcomes offered for this review.";
  const rationale = textProblem(form.rationale, "your rationale", { min: RATIONALE_MIN, max: RATIONALE_MAX });
  if (rationale) return rationale;
  if (form.notes.trim().length > NOTES_MAX) return `Keep the notes to ${NOTES_MAX} characters.`;
  if (type === "RISK") {
    for (const id of form.riskIds) {
      const finding = form.findings[id] ?? EMPTY_FINDING;
      if (!finding.control) return "For each risk you assessed, say whether its risk control worked.";
      if (finding.reason.trim().length < 10) return "Give the reason for each risk-control answer (10 characters).";
      if (finding.control === "NO" && (!finding.ownerId || !finding.dueDay))
        return "A risk control that did not work needs a risk file update with an owner and a due date.";
    }
    for (const hazard of form.newHazards) {
      if (hazard.description.trim().length < 10) return "Describe the new failure mode or hazard (10 characters).";
      if (!hazard.ownerId || !hazard.dueDay) return "A risk file update needs an owner and a due date.";
    }
  }
  return null;
}

/** The body of POST /case-reviews/{id}/complete: only the assessed parts that were filled in. */
export function completeBody(form: CompleteForm) {
  const notes = form.notes.trim();
  const update = (ownerId: string, dueDay: string) => (ownerId ? { owner_user_id: ownerId, due_on: dueDay } : {});
  const findings = [
    ...form.riskIds.map((id) => {
      const finding = form.findings[id] ?? EMPTY_FINDING;
      return {
        risk_id: id,
        control_worked: finding.control,
        reason: finding.reason.trim(),
        ...(finding.control === "NO" ? update(finding.ownerId, finding.dueDay) : {}),
      };
    }),
    ...form.newHazards.map((hazard) => ({
      description: hazard.description.trim(),
      ...update(hazard.ownerId, hazard.dueDay),
    })),
  ];
  const assessed = {
    ...(form.riskIds.length ? { risk_ids: [...form.riskIds] } : {}),
    ...(form.markets.length ? { markets: [...form.markets] } : {}),
    ...(notes ? { notes } : {}),
    ...(findings.length ? { findings } : {}),
  };
  return { outcome: form.outcome, rationale: form.rationale.trim(), assessed };
}

/** Why a recusal or a cancellation cannot be sent yet (its reason, 10 to 1000 characters), or null. */
export const reviewReasonProblem = (reason: string) =>
  textProblem(reason, "a reason", { min: REVIEW_REASON_MIN, max: REVIEW_REASON_MAX });

export const reviewReasonBody = (reason: string) => ({ reason: reason.trim() });

/** Add or remove one value of a multi-select. */
export const toggled = (values: string[], value: string, on: boolean) =>
  on ? (values.includes(value) ? values : [...values, value]) : values.filter((item) => item !== value);

// ---------------------------------------------------------------------------------------------------------------
// The review's context (GET /case-reviews/{id} `context`), read defensively: any part may be missing.

export type ContextItem = { key: string; id: string | null; label: string; detail: string | null };

const record = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;

const firstText = (row: Record<string, unknown>, keys: string[]) => {
  for (const key of keys) {
    const text = safeText(row[key]);
    if (text) return text;
  }
  return null;
};

const TEXT_KEYS = ["statement", "title", "name", "description", "label", "text", "summary", "question"];

/** One listed record as a line: its business ID and its text, never a UUID. */
export function contextItem(value: unknown, index = 0): ContextItem | null {
  if (typeof value === "string" || typeof value === "number") {
    const text = safeText(value);
    return text ? { key: `${index}:${text}`, id: null, label: text, detail: null } : null;
  }
  const row = record(value);
  if (!row) return null;
  const business = safeText(row.business_id) ?? firstText(row, ["identifier", "code"]);
  const text = firstText(row, TEXT_KEYS);
  const label = [business, text].filter(Boolean).join(" · ");
  if (!label) return null;
  const id = typeof row.id === "string" && row.id.trim() ? row.id.trim() : null;
  const detail =
    firstText(row, ["status_label", "severity_label", "category_label", "kind_label"]) ??
    (safeText(row.status) ? titleCase(String(row.status)) : null);
  return { key: id ?? `${index}:${label}`, id, label, detail };
}

/** The first of `keys` that holds a list, as lines. */
export function contextList(context: unknown, ...keys: string[]): ContextItem[] {
  const row = record(context);
  if (!row) return [];
  for (const key of keys) {
    const value = row[key];
    const list = Array.isArray(value)
      ? value
      : Array.isArray(record(value)?.items)
        ? (record(value)?.items as unknown[])
        : null;
    if (list) return list.map((item, index) => contextItem(item, index)).filter((item): item is ContextItem => !!item);
  }
  return [];
}

const countOf = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (Array.isArray(value)) return value.length;
  const row = record(value);
  if (row && typeof row.count === "number") return row.count;
  return null;
};

export type ContextHypothesis = {
  key: string;
  label: string;
  judgement: string | null;
  supporting: number | null;
  contradicting: number | null;
  origin: string | null;
};

export type RiskContext = {
  risks: ContextItem[];
  hazards: ContextItem[];
  harms: ContextItem[];
  controls: ContextItem[];
  failureModes: ContextItem[];
  hypotheses: ContextHypothesis[];
  contradictions: number | null;
  openUnknowns: ContextItem[];
  failureChains: ContextItem[];
};

/** The risk context: the product's risk file and the case's analysis, as the reviewer needs it. */
export function riskContext(context: unknown): RiskContext {
  const row = record(context) ?? {};
  const risk = record(row.risk_file) ?? record(row.product_risk) ?? row;
  const hypotheses = (Array.isArray(row.hypotheses) ? row.hypotheses : [])
    .map((value, index): ContextHypothesis | null => {
      const item = contextItem(value, index);
      const raw = record(value);
      if (!item) return null;
      const human = record(raw?.human_judgement) ?? record(raw?.judgement);
      const counts = record(raw?.evidence_counts) ?? raw ?? {};
      return {
        key: item.key,
        label: item.label,
        judgement:
          safeText(human?.label) ??
          safeText(human?.status_label) ??
          safeText(raw?.human_status_label) ??
          (safeText(human?.status ?? raw?.human_status) ? titleCase(String(human?.status ?? raw?.human_status)) : null),
        supporting: countOf(counts.supporting ?? counts.supporting_count ?? counts.supports),
        contradicting: countOf(counts.contradicting ?? counts.contradicting_count ?? counts.contradicts),
        origin: safeText(raw?.origin),
      };
    })
    .filter((item): item is ContextHypothesis => !!item);
  return {
    risks: contextList(risk, "risks", "product_risks", "risk_items"),
    hazards: contextList(risk, "hazards"),
    harms: contextList(risk, "harms"),
    controls: contextList(risk, "controls", "risk_controls"),
    failureModes: contextList(risk, "failure_modes"),
    hypotheses,
    contradictions: countOf(row.contradictions_count ?? row.contradictions),
    openUnknowns: contextList(row, "open_unknowns", "unknowns"),
    failureChains: contextList(row, "failure_chains"),
  };
}

export type RegulatoryComplaint = {
  key: string;
  label: string;
  market: string | null;
  eventDate: string | null;
  receivedDate: string | null;
  flags: string[];
};

export type RegulatoryContext = {
  complaints: RegulatoryComplaint[];
  markets: Array<{ market: string; count: number }>;
  earliestAwareness: string | null;
  note: string;
};

/** Said with every regulatory context: people determine reportability and its deadlines, never MDARIX. */
export const REGULATORY_NOTE =
  "MDARIX lists the complaints and dates in scope. Whether anything is reportable, to whom and by when is determined by the reviewer under your procedures; MDARIX does not assess reportability or compute deadlines.";

const FLAGS: Array<{ keys: string[]; label: string }> = [
  { keys: ["death", "is_death", "resulted_in_death"], label: "Death" },
  { keys: ["serious_injury", "is_serious_injury"], label: "Serious injury" },
  { keys: ["malfunction", "is_malfunction"], label: "Malfunction" },
];

/** The regulatory context: complaints in scope with their market, dates and flags, counts per market, awareness. */
export function regulatoryContext(context: unknown): RegulatoryContext {
  const row = record(context) ?? {};
  const list = Array.isArray(row.complaints)
    ? row.complaints
    : Array.isArray(row.in_scope_complaints)
      ? row.in_scope_complaints
      : [];
  const complaints = list
    .map((value, index): RegulatoryComplaint | null => {
      const item = contextItem(value, index);
      const raw = record(value) ?? {};
      if (!item) return null;
      const flags = record(raw.flags) ?? raw;
      return {
        key: item.key,
        label: item.label,
        market: firstText(raw, ["market", "country", "country_code", "region"]),
        eventDate: firstText(raw, ["event_date", "event_at", "event_timestamp"]),
        receivedDate: firstText(raw, ["received_date", "received_at", "awareness_date"]),
        flags: FLAGS.filter((flag) => flag.keys.some((key) => flags[key] === true)).map((flag) => flag.label),
      };
    })
    .filter((item): item is RegulatoryComplaint => !!item);
  const counts = row.counts_by_market ?? row.market_counts ?? row.by_market ?? row.counts_per_market;
  const markets: Array<{ market: string; count: number }> = Array.isArray(counts)
    ? counts
        .map((item) => {
          const entry = record(item) ?? {};
          const market = firstText(entry, ["market", "country", "label"]);
          const count = countOf(entry.count);
          return market && count !== null ? { market, count } : null;
        })
        .filter((item): item is { market: string; count: number } => !!item)
    : Object.entries(record(counts) ?? {})
        .filter(([market, count]) => safeText(market) && typeof count === "number")
        .map(([market, count]) => ({ market, count: count as number }));
  return {
    complaints,
    markets,
    earliestAwareness: firstText(row, ["earliest_awareness_date", "earliest_awareness", "earliest_received_date"]),
    note: safeText(row.note) ?? REGULATORY_NOTE,
  };
}

/** The risks a risk reviewer may say they assessed: those of the context with an id. */
export const assessableRisks = (context: RiskContext) =>
  [...context.risks, ...context.hazards].filter((item) => item.id);

/** The markets a regulatory reviewer may say they assessed: those counted, else those of the complaints. */
export function assessableMarkets(context: RegulatoryContext): string[] {
  const markets = context.markets.map((item) => item.market);
  for (const complaint of context.complaints)
    if (complaint.market && !markets.includes(complaint.market)) markets.push(complaint.market);
  return markets;
}

// ---------------------------------------------------------------------------------------------------------------
// Dashboard: the reviewer's own summary

export type ReviewTile = { key: keyof ReviewSummaryCounts; label: string; value: number | null; urgent?: boolean };

/** The count tiles of the reviewer's dashboard; a queue tile only for a role the person holds (when said). */
export function reviewTiles(summary: ReviewSummary | null | undefined): ReviewTile[] {
  const counts = summary?.counts ?? {};
  const value = (key: keyof ReviewSummaryCounts) => {
    const count = counts[key];
    return typeof count === "number" && Number.isFinite(count) ? count : null;
  };
  const holds = (role: "risk" | "regulatory") => {
    const flag = summary?.roles?.[role];
    return flag === undefined || flag === null ? value(`${role}_queue`) !== null : Boolean(flag);
  };
  return [
    ...(holds("risk") ? [{ key: "risk_queue" as const, label: "Risk queue", value: value("risk_queue") }] : []),
    ...(holds("regulatory")
      ? [{ key: "regulatory_queue" as const, label: "Regulatory queue", value: value("regulatory_queue") }]
      : []),
    { key: "mine_open", label: "Mine open", value: value("mine_open") },
    { key: "due_soon", label: "Due soon", value: value("due_soon") },
    { key: "overdue", label: "Overdue", value: value("overdue"), urgent: true },
    { key: "completed_30d", label: "Completed · 30 days", value: value("completed_30d") },
  ];
}

/** The case a review belongs to, for the context bar; null without one. */
export function reviewCase(review: Pick<Review, "investigation"> | null | undefined) {
  const id = review?.investigation?.id ? String(review.investigation.id).trim() : "";
  if (!id) return null;
  const product = review?.investigation?.product?.id ? String(review.investigation.product.id).trim() : "";
  return { investigationId: id, productId: product || null };
}
