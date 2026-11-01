// Pure rules for a case's Decision Brief (Phase 5): how a brief version and its status read, what its author and a
// quality reviewer may do, the author's narrative and its checks, the readiness scorecard (Pass, Blocked, Pending,
// Not required; never a percentage), comparing two versions, and the composed sections read defensively. The brief
// gives a decision maker context; it never decides. The server owns every version and refuses what it does not allow.
import { titleCase, type Tone } from "../admin/console/dashboardModel";
import { safeText } from "../../app/displayId";
import { textProblem } from "./intelligence";

export const BRIEF_TAB = "Decision Brief";

export const BRIEF_STATUSES = [
  "DRAFT",
  "READY_FOR_REVIEW",
  "UNDER_REVIEW",
  "RETURNED",
  "APPROVED_FOR_DECISION",
  "SUPERSEDED",
] as const;
export type BriefStatus = (typeof BRIEF_STATUSES)[number];

export const BRIEF_STATUS: Record<BriefStatus, { label: string; tone: Tone }> = {
  DRAFT: { label: "Draft", tone: "neutral" },
  READY_FOR_REVIEW: { label: "Ready for review", tone: "warning" },
  UNDER_REVIEW: { label: "Under review", tone: "warning" },
  RETURNED: { label: "Returned", tone: "serious" },
  APPROVED_FOR_DECISION: { label: "Approved for decision", tone: "good" },
  SUPERSEDED: { label: "Superseded", tone: "neutral" },
};

export type BriefNarrative = {
  problem_statement?: string | null;
  proposed_conclusion?: string | null;
  recommended_actions?: unknown;
  author_notes?: string | null;
  ai_draft_used?: boolean | null;
  ai_draft_text?: string | null;
};

export type BriefReviewAction = {
  action?: string | null;
  action_label?: string | null;
  comment?: string | null;
  actor_name?: string | null;
  actor_role?: string | null;
  created_at?: string | null;
};

export type BriefCheck = {
  key?: string | null;
  label?: string | null;
  result?: string | null;
  rationale?: string | null;
};

export type BriefVersion = {
  id: string;
  business_id?: string | null;
  version: number;
  status?: string | null;
  status_label?: string | null;
  title?: string | null;
  content?: Record<string, unknown> | null;
  narrative?: BriefNarrative | null;
  readiness?: { checks?: BriefCheck[] | null } | null;
  content_hash?: string | null;
  scope_version?: number | null;
  created_by_name?: string | null;
  submitted_by_name?: string | null;
  submitted_at?: string | null;
  reviewed_by_name?: string | null;
  reviewed_at?: string | null;
  review_actions?: BriefReviewAction[] | null;
};

export type BriefVersionRow = Pick<
  BriefVersion,
  | "id"
  | "business_id"
  | "version"
  | "status"
  | "status_label"
  | "submitted_at"
  | "reviewed_at"
  | "content_hash"
  | "created_by_name"
>;

export type BriefActions = {
  can_compose?: boolean;
  can_edit?: boolean;
  can_submit?: boolean;
  can_start_review?: boolean;
  can_review?: boolean;
};

export type BriefBlocking = { key?: string | null; label?: string | null; rationale?: string | null };

export type BriefState = {
  current?: BriefVersion | null;
  versions?: BriefVersionRow[] | null;
  gate?: { can_submit?: boolean | null; blocking?: BriefBlocking[] | null } | null;
  actions?: BriefActions | null;
  /** Live, not part of a version: open and overdue requests to external contacts on the case's complaints (T-G30). */
  communications?: {
    open: number;
    overdue: number;
    unresolved: number;
    items: Array<{
      id: string;
      ref: string | null;
      party: string | null;
      subject: string;
      reply_due_on: string | null;
      overdue: boolean;
    }>;
  } | null;
};

const code = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

const record = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;

// ---------------------------------------------------------------------------------------------------------------
// Addresses (prefix /api/v1/investigations/{id}/decision-brief)

export const briefPath = (investigationId: string, path = "") =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/decision-brief${path ? `/${path}` : ""}`;
export const briefVersionPath = (investigationId: string, version: number, action?: "start-review" | "review") =>
  briefPath(investigationId, `versions/${encodeURIComponent(String(version))}${action ? `/${action}` : ""}`);
export const BRIEF_SUMMARY_PATH = "/api/v1/decision-briefs/summary";

export function briefListPath(status = "", page = 1, pageSize = 20): string {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("page", String(Math.max(1, page)));
  params.set("page_size", String(pageSize));
  return `/api/v1/decision-briefs?${params}`;
}

// ---------------------------------------------------------------------------------------------------------------
// Status, hashes and the version list

export function briefStatus(version: Pick<BriefVersion, "status"> | null | undefined): BriefStatus | null {
  const value = code(version?.status);
  return (BRIEF_STATUSES as readonly string[]).includes(value) ? (value as BriefStatus) : null;
}

export function briefStatusView(version: Pick<BriefVersion, "status" | "status_label"> | null | undefined) {
  const status = briefStatus(version);
  return {
    label:
      safeText(version?.status_label) ??
      (status ? BRIEF_STATUS[status].label : titleCase(String(version?.status ?? "Unknown"))),
    tone: status ? BRIEF_STATUS[status].tone : ("neutral" as Tone),
  };
}

/** The first characters of a hash for people to compare at a glance ("sha256:" left out); "—" without one. */
export function shortHash(value: unknown, length = 12): string {
  if (typeof value !== "string" || !value.trim()) return "—";
  const text = value.trim().replace(/^sha256:/i, "");
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

/** Versions newest first. */
export const versionsNewestFirst = (versions: BriefVersionRow[] | null | undefined) =>
  [...(versions ?? [])].sort((a, b) => Number(b.version) - Number(a.version));

/** The two versions a comparison starts with: the latest and the one before it; null with fewer than two. */
export function defaultComparison(versions: BriefVersionRow[] | null | undefined): [number, number] | null {
  const sorted = versionsNewestFirst(versions);
  return sorted.length >= 2 ? [Number(sorted[1].version), Number(sorted[0].version)] : null;
}

// ---------------------------------------------------------------------------------------------------------------
// What the person may do (the server's `actions` flags, never guessed)

export type BriefControls = {
  compose: boolean;
  edit: boolean;
  submit: boolean;
  startReview: boolean;
  review: boolean;
};

/**
 * The controls shown: each only when the server allows it. The brief's author never gets review controls (the server
 * refuses them with SOD_DENIED); someone who may review never gets the author's controls on the same screen state.
 */
export function briefControls(state: BriefState | null | undefined): BriefControls {
  const actions = state?.actions ?? {};
  const status = briefStatus(state?.current);
  return {
    compose: actions.can_compose === true,
    edit: actions.can_edit === true && !!state?.current,
    submit: actions.can_submit === true && !!state?.current,
    startReview: actions.can_start_review === true && !!state?.current,
    review: actions.can_review === true && !!state?.current && (status === null || status === "UNDER_REVIEW"),
  };
}

/**
 * The step the top of the Decision Brief tab offers this person, so reviewing never starts at the end of a long page:
 * start the quality review, record it, or, right after they accepted the brief for decision here (``acceptedHere``),
 * go and sign the decision. An accepted version stays accepted after the decision is signed, so "sign" is offered only
 * then.
 */
export type BriefNextStep = "START_REVIEW" | "RECORD_REVIEW" | "SIGN";

export function briefNextStep(
  controls: Pick<BriefControls, "startReview" | "review">,
  current: Pick<BriefVersion, "status"> | null | undefined,
  acceptedHere = false,
): BriefNextStep | null {
  if (!current) return null;
  if (briefStatus(current) === "APPROVED_FOR_DECISION") return acceptedHere ? "SIGN" : null;
  if (controls.startReview) return "START_REVIEW";
  if (controls.review) return "RECORD_REVIEW";
  return null;
}

// ---------------------------------------------------------------------------------------------------------------
// The author's narrative

export const NARRATIVE_TEXT_MAX = 5000;
export const NARRATIVE_MIN = 20;
export const ACTION_MAX = 1000;
export const ACTIONS_MAX = 20;

export type NarrativeForm = {
  problemStatement: string;
  proposedConclusion: string;
  /** One recommended action per line. */
  actions: string;
  notes: string;
};

/** The recommended actions as a list: written text only, trimmed, without empty lines. */
export const actionsOf = (value: unknown): string[] =>
  Array.isArray(value)
    ? value
        .map((item) =>
          typeof item === "string" ? item.trim() : (safeText((item as Record<string, unknown>)?.text) ?? ""),
        )
        .filter(Boolean)
    : typeof value === "string"
      ? actionLines(value)
      : [];

export const actionLines = (text: string) =>
  text
    .split("\n")
    .map((line) => line.replace(/^\s*[-*•]\s*/, "").trim())
    .filter(Boolean);

export function narrativeFormFrom(narrative: BriefNarrative | null | undefined): NarrativeForm {
  return {
    problemStatement: String(narrative?.problem_statement ?? ""),
    proposedConclusion: String(narrative?.proposed_conclusion ?? ""),
    actions: actionsOf(narrative?.recommended_actions).join("\n"),
    notes: String(narrative?.author_notes ?? ""),
  };
}

/** The body of PUT /decision-brief/draft. */
export function narrativeBody(form: NarrativeForm) {
  return {
    problem_statement: form.problemStatement.trim(),
    proposed_conclusion: form.proposedConclusion.trim(),
    recommended_actions: actionLines(form.actions),
    author_notes: form.notes.trim(),
  };
}

/** Why the narrative cannot be saved (only length limits; a draft may be incomplete), or null. */
export function narrativeProblem(form: NarrativeForm): string | null {
  if (form.problemStatement.trim().length > NARRATIVE_TEXT_MAX)
    return `Keep the problem statement to ${NARRATIVE_TEXT_MAX} characters.`;
  if (form.proposedConclusion.trim().length > NARRATIVE_TEXT_MAX)
    return `Keep the proposed conclusion to ${NARRATIVE_TEXT_MAX} characters.`;
  const actions = actionLines(form.actions);
  if (actions.length > ACTIONS_MAX) return `List at most ${ACTIONS_MAX} recommended actions.`;
  if (actions.some((item) => item.length > ACTION_MAX))
    return `Keep each recommended action to ${ACTION_MAX} characters.`;
  if (form.notes.trim().length > NARRATIVE_TEXT_MAX) return `Keep the notes to ${NARRATIVE_TEXT_MAX} characters.`;
  return null;
}

/** Whether the form differs from the saved narrative (then it must be saved before submitting). */
export function narrativeChanged(form: NarrativeForm, narrative: BriefNarrative | null | undefined): boolean {
  const saved = narrativeBody(narrativeFormFrom(narrative));
  const now = narrativeBody(form);
  return (
    saved.problem_statement !== now.problem_statement ||
    saved.proposed_conclusion !== now.proposed_conclusion ||
    saved.author_notes !== now.author_notes ||
    saved.recommended_actions.join("\n") !== now.recommended_actions.join("\n")
  );
}

const squash = (value: unknown) =>
  String(value ?? "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();

/**
 * Whether the proposed conclusion is still the AI draft word for word. The AI draft is a starting point the author
 * must make their own: a brief is never submitted with AI text standing as its conclusion.
 */
export function aiDraftUnedited(
  form: Pick<NarrativeForm, "proposedConclusion">,
  narrative: BriefNarrative | null | undefined,
) {
  const draft = squash(narrative?.ai_draft_text);
  return !!draft && squash(form.proposedConclusion) === draft;
}

/** What the narrative still lacks before the brief is submitted (the server's readiness checks decide). */
export function narrativeGaps(form: NarrativeForm, narrative: BriefNarrative | null | undefined): string[] {
  const gaps: string[] = [];
  if (form.problemStatement.trim().length < NARRATIVE_MIN)
    gaps.push(`Write the problem statement (at least ${NARRATIVE_MIN} characters).`);
  if (form.proposedConclusion.trim().length < NARRATIVE_MIN)
    gaps.push(`Write the proposed conclusion in your own words (at least ${NARRATIVE_MIN} characters).`);
  if (!actionLines(form.actions).length) gaps.push("List at least one recommended action.");
  if (aiDraftUnedited(form, narrative))
    gaps.push("The proposed conclusion is still the AI draft word for word. Edit it into your own conclusion.");
  return gaps;
}

// ---------------------------------------------------------------------------------------------------------------
// The readiness scorecard: Pass, Blocked, Pending, Not required (never a percentage)

export const SCORE_RESULTS = ["BLOCKED", "PENDING", "PASS", "NOT_REQUIRED"] as const;
export type ScoreResult = (typeof SCORE_RESULTS)[number];

export const SCORE: Record<ScoreResult, { label: string; tone: Tone }> = {
  BLOCKED: { label: "Blocked", tone: "critical" },
  PENDING: { label: "Pending", tone: "warning" },
  PASS: { label: "Pass", tone: "good" },
  NOT_REQUIRED: { label: "Not required", tone: "neutral" },
};

export type ScoreCheck = { key: string; label: string; result: ScoreResult; rationale: string | null };
export type ScoreGroup = { result: ScoreResult; label: string; tone: Tone; checks: ScoreCheck[] };

const scoreOf = (value: unknown): ScoreResult => {
  const result = code(value);
  if (result === "PASS" || result === "PASSED") return "PASS";
  if (result === "BLOCKED" || result === "FAIL" || result === "FAILED") return "BLOCKED";
  if (result === "NOT_REQUIRED" || result === "NOT_APPLICABLE") return "NOT_REQUIRED";
  // Anything else (pending, not available yet, unknown) is work still open, never a pass.
  return "PENDING";
};

/** The checks a version reports: its own readiness, else the composed content's. */
// Checks about the brief itself and the decision after it: a brief's own scorecard, recorded while it was written,
// cannot show them truthfully ("No brief generated yet" on the brief), and its submission ignores them.
const NOT_ON_THE_BRIEF = new Set(["brief_ready", "decision"]);

export function briefChecks(version: Pick<BriefVersion, "readiness" | "content"> | null | undefined): BriefCheck[] {
  const own = version?.readiness?.checks;
  const content = record(record(version?.content)?.readiness)?.checks;
  const checks = Array.isArray(own) ? own : Array.isArray(content) ? (content as BriefCheck[]) : [];
  return checks.filter((check) => !NOT_ON_THE_BRIEF.has(String(check.key ?? "")));
}

/**
 * The scorecard: the version's checks, plus any check the submit gate names as blocking that the version does not
 * list (a blocking check always reads Blocked), grouped Blocked, Pending, Pass, Not required; empty groups left out.
 */
export function scorecard(checks: BriefCheck[] | null | undefined, blocking?: BriefBlocking[] | null): ScoreGroup[] {
  const blocked = new Map(
    (blocking ?? []).map((item, index) => [String(item.key ?? `blocking-${index}`).toLowerCase(), item]),
  );
  const listed: ScoreCheck[] = (checks ?? []).map((check, index) => {
    const key = String(check.key ?? `check-${index}`);
    const gate = blocked.get(key.toLowerCase());
    return {
      key,
      label: safeText(check.label) ?? titleCase(key),
      result: gate ? "BLOCKED" : scoreOf(check.result),
      rationale: safeText(check.rationale) ?? safeText(gate?.rationale),
    };
  });
  const extra: ScoreCheck[] = [...blocked.entries()]
    .filter(([key]) => !listed.some((check) => check.key.toLowerCase() === key))
    .map(([key, item]) => ({
      key,
      label: safeText(item.label) ?? titleCase(key),
      result: "BLOCKED" as const,
      rationale: safeText(item.rationale),
    }));
  const all = [...listed, ...extra];
  return SCORE_RESULTS.map((result) => ({
    result,
    label: SCORE[result].label,
    tone: SCORE[result].tone,
    checks: all.filter((check) => check.result === result),
  })).filter((group) => group.checks.length > 0);
}

/** "2 blocked · 1 pending · 5 pass · 1 not required": counts only, never a percentage. */
export function scorecardHeadline(groups: ScoreGroup[]): string {
  if (!groups.length) return "No readiness checks reported yet.";
  return groups.map((group) => `${group.checks.length} ${group.label.toLowerCase()}`).join(" · ");
}

// ---------------------------------------------------------------------------------------------------------------
// The quality reviewer's actions

export const BRIEF_REVIEW_ACTIONS = [
  { value: "ACCEPT_FOR_DECISION", label: "Accept for decision", commentRequired: false },
  { value: "RETURN_FOR_EVIDENCE", label: "Return for more evidence", commentRequired: true },
  { value: "RETURN_FOR_ANALYSIS", label: "Return for more analysis", commentRequired: true },
  { value: "RETURN_FOR_RISK_REVIEW", label: "Return for a risk review", commentRequired: true },
  { value: "RETURN_FOR_REGULATORY_REVIEW", label: "Return for a regulatory review", commentRequired: true },
  { value: "REJECT_PROPOSED_CONCLUSION", label: "Reject the proposed conclusion", commentRequired: true },
  { value: "ESCALATE", label: "Escalate", commentRequired: true },
] as const;
export type BriefReviewActionCode = (typeof BRIEF_REVIEW_ACTIONS)[number]["value"];

export const COMMENT_MIN = 10;
export const COMMENT_MAX = 5000;

export const briefReviewActionLabel = (action: Pick<BriefReviewAction, "action" | "action_label">) =>
  safeText(action.action_label) ??
  BRIEF_REVIEW_ACTIONS.find((item) => item.value === code(action.action))?.label ??
  titleCase(String(action.action ?? "Review"));

// What a review did, as the sentence the toast shows after it (UX-21): "Decision Brief DBV000001 accepted for
// decision.", never "DBV000001: accept for decision recorded.".
const REVIEW_DONE: Record<string, string> = {
  ACCEPT_FOR_DECISION: "accepted for decision. Next: sign the decision on the Decision tab.",
  RETURN_FOR_EVIDENCE: "returned to its author for more evidence.",
  RETURN_FOR_ANALYSIS: "returned to its author for more analysis.",
  RETURN_FOR_RISK_REVIEW: "returned to its author for a risk review.",
  RETURN_FOR_REGULATORY_REVIEW: "returned to its author for a regulatory review.",
  REJECT_PROPOSED_CONCLUSION: "returned to its author. Its proposed conclusion was rejected.",
  ESCALATE: "escalated. A leader takes it from the task list.",
};

/** The toast after a quality review action on a brief version, named by its MDARIX ID when it has one. */
export function briefReviewDoneMessage(action: string, businessId: unknown): string {
  const id = safeText(businessId);
  const brief = id ? `Decision Brief ${id}` : "The Decision Brief";
  return `${brief} ${REVIEW_DONE[action] ?? "was reviewed. Your review is recorded."}`;
}

/** Why the review action cannot be sent yet, or null: a comment is required for everything except accepting. */
export function briefReviewProblem(action: string, comment: string): string | null {
  const known = BRIEF_REVIEW_ACTIONS.find((item) => item.value === action);
  if (!known) return "Choose what to do with this brief.";
  return textProblem(comment, "a comment", {
    min: known.commentRequired ? COMMENT_MIN : 0,
    max: COMMENT_MAX,
    required: known.commentRequired,
  });
}

export function briefReviewBody(action: string, comment: string) {
  const text = comment.trim();
  return { action, ...(text ? { comment: text } : {}) };
}

/** The submit body: an optional comment for the reviewer. */
export const submitBody = (comment: string) => (comment.trim() ? { comment: comment.trim() } : {});

// ---------------------------------------------------------------------------------------------------------------
// The composed sections, read defensively

export type BriefLine = {
  key: string;
  id: string | null;
  label: string;
  detail: string | null;
  kind: string | null;
  origin: string | null;
  evidence: string | null;
};

const TEXT_KEYS = [
  "statement",
  "title",
  "name",
  "description",
  "label",
  "text",
  "summary",
  "question",
  "chain_statement",
];

const firstText = (row: Record<string, unknown>, keys: string[]) => {
  for (const key of keys) {
    const text = safeText(row[key]);
    if (text) return text;
  }
  return null;
};

/** One listed record as a line: its business ID, its text, its kind and origin, and the evidence it rests on. */
export function briefLine(value: unknown, index = 0): BriefLine | null {
  if (typeof value === "string" || typeof value === "number") {
    const text = safeText(value);
    return text
      ? { key: `${index}:${text}`, id: null, label: text, detail: null, kind: null, origin: null, evidence: null }
      : null;
  }
  const row = record(value);
  if (!row) return null;
  const text = firstText(row, TEXT_KEYS);
  const business = safeText(row.business_id);
  const label = text ?? business;
  if (!label) return null;
  const evidence = record(row.evidence);
  const status = firstText(row, ["human_status_label", "status_label", "judgement_label", "reliability_label"]);
  return {
    key: typeof row.id === "string" && row.id.trim() ? row.id.trim() : `${index}:${label}`,
    id: text && business ? business : null,
    label,
    detail: status ?? (safeText(row.human_status) ? titleCase(String(row.human_status)) : null),
    kind: safeText(row.epistemic_type) ?? safeText(row.statement_kind) ?? safeText(row.kind),
    origin: safeText(row.origin),
    evidence:
      safeText(row.evidence_business_id) ??
      safeText(evidence?.business_id) ??
      (Array.isArray(row.evidence_business_ids)
        ? (row.evidence_business_ids as unknown[])
            .map((item) => safeText(item))
            .filter(Boolean)
            .join(", ") || null
        : null),
  };
}

/** A list in the content as lines (a list, or an object holding `items`). */
export function briefLines(value: unknown): BriefLine[] {
  const list = Array.isArray(value)
    ? value
    : Array.isArray(record(value)?.items)
      ? (record(value)?.items as unknown[])
      : [];
  return list.map((item, index) => briefLine(item, index)).filter((item): item is BriefLine => !!item);
}

/** Counts as label and number ("Reviewed: 7"), from an object of counts. */
export function briefCounts(value: unknown): Array<{ key: string; label: string; count: number }> {
  return Object.entries(record(value) ?? {})
    .filter(([, count]) => typeof count === "number" && Number.isFinite(count))
    .map(([key, count]) => ({ key, label: titleCase(key), count: count as number }));
}

export type BriefReviewSummary = {
  id: string | null;
  status: string | null;
  outcome: string | null;
  rationale: string | null;
  reviewer: string | null;
  completedAt: string | null;
};

/** The risk or regulatory review the brief refers to, or null when the brief carries none. */
export function briefReview(value: unknown): BriefReviewSummary | null {
  const row = record(value);
  if (!row) return null;
  const summary = {
    id: safeText(row.business_id),
    status: safeText(row.status_label) ?? (safeText(row.status) ? titleCase(String(row.status)) : null),
    outcome: safeText(row.outcome_label) ?? (safeText(row.outcome) ? titleCase(String(row.outcome)) : null),
    rationale: safeText(row.rationale),
    reviewer: safeText(row.reviewer_name) ?? safeText(record(row.reviewer)?.name),
    completedAt: safeText(row.completed_at),
  };
  return Object.values(summary).some(Boolean) ? summary : null;
}

export type AiDisclosure = {
  executions: Array<{
    key: string;
    id: string;
    kind: string | null;
    provider: string | null;
    model: string | null;
    at: string | null;
  }>;
  statement: string | null;
};

/** What AI contributed to the brief: each execution by its business ID, and the disclosure statement. */
export function aiDisclosure(content: Record<string, unknown> | null | undefined): AiDisclosure {
  const ai = record(content?.ai_assistance);
  const executions = (Array.isArray(ai?.executions) ? (ai?.executions as unknown[]) : []).map((value, index) => {
    const row = record(value) ?? {};
    return {
      key: `${index}`,
      id: safeText(row.business_id) ?? "AI run",
      kind: safeText(row.kind_label) ?? (safeText(row.kind) ? titleCase(String(row.kind)) : null),
      provider: safeText(row.provider),
      model: safeText(row.model),
      at: safeText(row.created_at),
    };
  });
  return { executions, statement: safeText(ai?.statement) };
}

/** When and on what the brief was composed: as-of date, scope version, evidence-set fingerprint, composed at. */
export function briefContext(content: Record<string, unknown> | null | undefined) {
  const context = record(content?.context) ?? {};
  return {
    asOf: safeText(context.as_of),
    scopeVersion:
      typeof context.scope_version === "number" || typeof context.scope_version === "string"
        ? String(context.scope_version)
        : null,
    evidenceSetHash: typeof context.evidence_set_hash === "string" ? context.evidence_set_hash : null,
    composedAt: safeText(context.composed_at),
  };
}

// ---------------------------------------------------------------------------------------------------------------
// Comparing two versions

export type CompareRow = {
  key: string;
  label: string;
  left: string[];
  right: string[];
  added: string[];
  removed: string[];
  same: boolean;
};

const one = (value: unknown) => {
  const text = safeText(value);
  return text ? [text] : [];
};

/** Each comparable part of a version: the narrative, a summary of the composed content, and its fingerprints. */
export function briefParts(
  version: BriefVersion | null | undefined,
): Array<{ key: string; label: string; items: string[] }> {
  const narrative = version?.narrative ?? {};
  const content = record(version?.content) ?? {};
  const unknowns = record(content.unknowns) ?? {};
  const leading = briefLine(content.leading_hypothesis);
  const count = (label: string, value: unknown) => [`${label}: ${briefLines(value).length}`];
  const review = (value: unknown) => {
    const summary = briefReview(value);
    return summary ? [[summary.id, summary.outcome ?? summary.status].filter(Boolean).join(" · ")] : ["None"];
  };
  const groups = scorecard(briefChecks(version));
  const context = briefContext(content);
  return [
    { key: "status", label: "Status", items: [briefStatusView(version).label] },
    { key: "problem", label: "Problem statement", items: one(narrative.problem_statement) },
    { key: "conclusion", label: "Proposed conclusion", items: one(narrative.proposed_conclusion) },
    { key: "actions", label: "Recommended actions", items: actionsOf(narrative.recommended_actions) },
    { key: "notes", label: "Author notes", items: one(narrative.author_notes) },
    // Not "Established facts": each statement carries its own kind, often a source assertion (UX-21).
    { key: "facts", label: "What the evidence says", items: count("Statements", content.established_facts) },
    {
      key: "evidence",
      label: "Evidence",
      items: [
        ...briefCounts(record(content.evidence_inventory)?.counts).map((item) => `${item.label}: ${item.count}`),
        ...count("Supporting", content.supporting_evidence),
        ...count("Contradicting", content.contradicting_evidence),
      ],
    },
    {
      key: "hypotheses",
      label: "Hypotheses",
      items: [
        `Leading: ${leading ? [leading.id, leading.label].filter(Boolean).join(" · ") : "None"}`,
        ...count("Alternatives", content.alternative_hypotheses),
      ],
    },
    {
      key: "unknowns",
      label: "Unknowns",
      items: [...count("Open", unknowns.open), ...count("Accepted limitations", unknowns.accepted_limitations)],
    },
    { key: "chains", label: "Failure chains", items: count("Chains", content.failure_chains) },
    { key: "risk", label: "Risk review", items: review(content.risk_review) },
    { key: "regulatory", label: "Regulatory review", items: review(content.regulatory_review) },
    { key: "ai", label: "AI assistance", items: [`AI runs: ${aiDisclosure(content).executions.length}`] },
    { key: "readiness", label: "Readiness", items: [scorecardHeadline(groups)] },
    { key: "scope", label: "Scope version", items: one(version?.scope_version ?? context.scopeVersion) },
    { key: "hash", label: "Brief fingerprint", items: [shortHash(version?.content_hash)] },
    { key: "fingerprint", label: "Evidence fingerprint", items: [shortHash(context.evidenceSetHash)] },
  ];
}

/** Two versions part by part, with what was added and removed in each part. */
export function compareBriefs(
  left: BriefVersion | null | undefined,
  right: BriefVersion | null | undefined,
): CompareRow[] {
  const before = briefParts(left);
  const after = briefParts(right);
  return before.map((part, index) => {
    const next = after[index]?.items ?? [];
    const added = next.filter((item) => !part.items.includes(item));
    const removed = part.items.filter((item) => !next.includes(item));
    return {
      key: part.key,
      label: part.label,
      left: part.items,
      right: next,
      added,
      removed,
      same: !added.length && !removed.length,
    };
  });
}

// ---------------------------------------------------------------------------------------------------------------
// Dashboard: the quality reviewer's summary

export type BriefSummaryCounts = Partial<
  Record<
    "awaiting_review" | "under_review_by_me" | "returned_open" | "resubmitted" | "blocked_cases" | "overdue_cases",
    number
  >
>;

export type BriefSummary = {
  counts?: BriefSummaryCounts | null;
  awaiting?: Array<Record<string, unknown>> | null;
  blocked?: Array<Record<string, unknown>> | null;
};

export type BriefTile = { key: keyof BriefSummaryCounts; label: string; value: number | null; urgent?: boolean };

export function briefTiles(summary: BriefSummary | null | undefined): BriefTile[] {
  const counts = summary?.counts ?? {};
  const value = (key: keyof BriefSummaryCounts) => {
    const count = counts[key];
    return typeof count === "number" && Number.isFinite(count) ? count : null;
  };
  return [
    { key: "awaiting_review", label: "Awaiting review", value: value("awaiting_review") },
    { key: "under_review_by_me", label: "Under review by me", value: value("under_review_by_me") },
    { key: "returned_open", label: "Returned", value: value("returned_open") },
    { key: "resubmitted", label: "Resubmitted", value: value("resubmitted") },
    { key: "blocked_cases", label: "Blocked cases", value: value("blocked_cases") },
    { key: "overdue_cases", label: "Overdue cases", value: value("overdue_cases"), urgent: true },
  ];
}

export type SummaryCase = {
  key: string;
  investigationId: string | null;
  productId: string | null;
  caseId: string;
  question: string | null;
  briefId: string | null;
  version: string | null;
  submittedBy: string | null;
  submittedAt: string | null;
  priority: string | null;
  blocking: string[];
};

/** A row of the summary's awaiting or blocked list, whether the case is nested or flat. */
export function summaryCase(row: Record<string, unknown> | null | undefined, index = 0): SummaryCase {
  const item = row ?? {};
  const investigation = record(item.investigation) ?? {};
  const brief = record(item.brief) ?? {};
  // The investigation's UUID is the technical key the context uses; it is never shown.
  const rawId = typeof investigation.id === "string" ? investigation.id : item.investigation_id;
  const id = typeof rawId === "string" && rawId.trim() ? rawId.trim() : null;
  const productId =
    (typeof investigation.product_id === "string" && investigation.product_id) ||
    (typeof record(investigation.product)?.id === "string" && (record(investigation.product)?.id as string)) ||
    (typeof item.product_id === "string" && item.product_id) ||
    null;
  const blocking = Array.isArray(item.blocking)
    ? (item.blocking as unknown[])
        .map((entry) => (typeof entry === "string" ? safeText(entry) : safeText(record(entry)?.label)))
        .filter((entry): entry is string => !!entry)
    : [];
  const version = item.version ?? brief.version;
  return {
    key: `${index}:${id ?? ""}`,
    investigationId: id,
    productId,
    caseId:
      safeText(investigation.business_id) ??
      safeText(item.investigation_business_id) ??
      safeText(item.business_id) ??
      "Case",
    question: safeText(investigation.question) ?? safeText(item.question),
    briefId: safeText(item.brief_business_id) ?? safeText(brief.business_id),
    version: typeof version === "number" || typeof version === "string" ? String(version) : null,
    submittedBy: safeText(item.submitted_by_name),
    submittedAt: safeText(item.submitted_at),
    priority: safeText(item.priority) ?? safeText(investigation.priority),
    blocking,
  };
}
