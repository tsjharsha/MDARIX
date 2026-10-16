// Pure rules for the human decision on a case (Phase 6): the approvals queue and its order, how the brief reads for the
// decision maker, which outcome needs conditions, follow-ups or an acknowledgement, the body of a signature (built at
// the moment of signing; the password and authenticator code are never kept), the meaning of a signature in words, the
// signed record's verification checks and the decision history. The server owns every decision and refuses what it
// does not allow; these only shape what the person sees. AI text is never presented as the decision.
import { titleCase, type Tone } from "../admin/console/dashboardModel";
import { safeText } from "../../app/displayId";
import { sortParams, type SortState } from "../../app/tableSort";
import { ApiError, describeError } from "../../app/apiClient";
import { actionsOf, briefLines, shortHash } from "./decisionBrief";
import { textProblem } from "./intelligence";
import { dueAtFromDay } from "./caseWorkflow";
import { dueState, priorityRank } from "./tasks";

export const APPROVALS_TAB = "Approvals";

const code = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

const record = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;

const idText = (value: unknown): string | null => {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return typeof value === "string" && value.trim() ? value.trim() : null;
};

// ---------------------------------------------------------------------------------------------------------------
// Addresses

export const DECISIONS_SUMMARY_PATH = "/api/v1/decisions/summary";

export function decisionsQueuePath(page = 1, pageSize = 20, sort: SortState = null): string {
  const params = new URLSearchParams({
    page: String(Math.max(1, page)),
    page_size: String(pageSize),
    ...sortParams(sort),
  });
  return `/api/v1/decisions/queue?${params}`;
}

/** The approvals queue's columns (queueRow keys) the server sorts across every page (GET /api/v1/decisions/queue). */
export const QUEUE_SORTS = ["caseId", "product", "brief", "priority", "dueAt", "awaitingSince", "reviews"] as const;

export const caseDecisionPath = (investigationId: string, action?: "sign" | "return") =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/decision${action ? `/${action}` : ""}`;

export const decisionRecordPath = (decisionId: string) => `/api/v1/decisions/${encodeURIComponent(decisionId)}/record`;

// ---------------------------------------------------------------------------------------------------------------
// Outcomes and follow-up actions

export const DECISION_OUTCOMES = [
  "ACCEPT_CONCLUSION",
  "ACCEPT_WITH_CONDITIONS",
  "REJECT_CONCLUSION",
  "CLOSE_NO_FURTHER_ACTION",
] as const;
export type DecisionOutcome = (typeof DECISION_OUTCOMES)[number];

export const OUTCOME_COPY: Record<DecisionOutcome, { label: string; description: string; tone: Tone }> = {
  ACCEPT_CONCLUSION: {
    label: "Accept the conclusion",
    description: "The proposed conclusion is accepted as written. You may require follow-up actions.",
    tone: "good",
  },
  ACCEPT_WITH_CONDITIONS: {
    label: "Accept with conditions",
    description: "The proposed conclusion is accepted on the conditions you state. You may require follow-up actions.",
    tone: "warning",
  },
  REJECT_CONCLUSION: {
    label: "Reject the conclusion",
    description: "The proposed conclusion is not accepted. Your rationale is recorded with your signature.",
    tone: "critical",
  },
  CLOSE_NO_FURTHER_ACTION: {
    label: "Close with no further action",
    description: "No action is needed beyond recording this decision.",
    tone: "neutral",
  },
};

export const FOLLOW_UP_ACTIONS = [
  "CAPA_REQUIRED",
  "PRODUCT_CHANGE_REQUIRED",
  "FIELD_ACTION_REVIEW_REQUIRED",
  "RISK_REASSESSMENT_REQUIRED",
  "REGULATORY_ACTION_REQUIRED",
] as const;
export type FollowUpAction = (typeof FOLLOW_UP_ACTIONS)[number];

export const FOLLOW_UP_ACTION_LABELS: Record<FollowUpAction, string> = {
  CAPA_REQUIRED: "CAPA required",
  PRODUCT_CHANGE_REQUIRED: "Product change required",
  FIELD_ACTION_REVIEW_REQUIRED: "Field action review required",
  RISK_REASSESSMENT_REQUIRED: "Risk reassessment required",
  REGULATORY_ACTION_REQUIRED: "Regulatory action required",
};

export type OutcomeOption = { code: string; label: string; description: string | null };
export type FollowUpOption = { code: string; label: string };

/** The outcomes offered: the server's list (with its words) when it sends one, else the four known outcomes. */
export function outcomeOptions(server: unknown): OutcomeOption[] {
  const listed = Array.isArray(server)
    ? server
        .map((item): OutcomeOption | null => {
          const row = record(item);
          const value = code(row?.code);
          if (!value) return null;
          const known = OUTCOME_COPY[value as DecisionOutcome];
          return {
            code: value,
            label: safeText(row?.label) ?? known?.label ?? titleCase(value),
            description: safeText(row?.description) ?? known?.description ?? null,
          };
        })
        .filter((item): item is OutcomeOption => !!item)
    : [];
  if (listed.length) return listed;
  return DECISION_OUTCOMES.map((value) => ({
    code: value,
    label: OUTCOME_COPY[value].label,
    description: OUTCOME_COPY[value].description,
  }));
}

/** The follow-up actions offered: the server's list when it sends one, else the five known actions. */
export function followUpOptions(server: unknown): FollowUpOption[] {
  const listed = Array.isArray(server)
    ? server
        .map((item): FollowUpOption | null => {
          const row = record(item);
          const value = code(row?.code);
          if (!value) return null;
          return {
            code: value,
            label: safeText(row?.label) ?? FOLLOW_UP_ACTION_LABELS[value as FollowUpAction] ?? titleCase(value),
          };
        })
        .filter((item): item is FollowUpOption => !!item)
    : [];
  if (listed.length) return listed;
  return FOLLOW_UP_ACTIONS.map((value) => ({ code: value, label: FOLLOW_UP_ACTION_LABELS[value] }));
}

/**
 * An outcome as people read it: the server's label, the known label, a code made readable, or words already written
 * for people as they are; "—" without one.
 */
export function outcomeLabel(value: unknown, label?: unknown): string {
  const given = safeText(label);
  if (given) return given;
  const raw = safeText(value);
  if (!raw) return "—";
  const outcome = code(raw);
  const known = OUTCOME_COPY[outcome as DecisionOutcome];
  if (known) return known.label;
  return /^[A-Z0-9_\s-]+$/.test(raw) ? titleCase(outcome) : raw;
}

export function outcomeTone(value: unknown): Tone {
  return OUTCOME_COPY[code(value) as DecisionOutcome]?.tone ?? "neutral";
}

/** What an outcome asks for: written conditions (accept with conditions) and follow-up actions (either accept). */
export function outcomeRules(outcome: unknown): { conditions: boolean; followUps: boolean } {
  const value = code(outcome);
  return {
    conditions: value === "ACCEPT_WITH_CONDITIONS",
    followUps: value === "ACCEPT_CONCLUSION" || value === "ACCEPT_WITH_CONDITIONS",
  };
}

// ---------------------------------------------------------------------------------------------------------------
// The decision context (GET /api/v1/investigations/{id}/decision), read defensively

export type DecisionRef = { id?: string | null; business_id?: string | null } | string | null;

export type CaseDecisionRow = {
  id?: string | null;
  business_id?: string | null;
  outcome?: string | null;
  outcome_label?: string | null;
  status?: string | null;
  status_label?: string | null;
  conditions?: string | null;
  rationale?: string | null;
  decided_at?: string | null;
  signed_at?: string | null;
  signer_name?: string | null;
  signer_role?: string | null;
  is_current?: boolean | null;
  supersedes?: DecisionRef;
  superseded_by?: DecisionRef;
  supersedes_decision_id?: string | null;
  superseded_by_decision_id?: string | null;
  brief?: { business_id?: string | null; version?: number | string | null } | null;
};

export type DecisionBrief = {
  id?: string | null;
  business_id?: string | null;
  version?: number | string | null;
  status?: string | null;
  status_label?: string | null;
  content_hash?: string | null;
  hash_verified?: boolean | null;
  approved_at?: string | null;
  quality_reviewer_name?: string | null;
  narrative?: { problem_statement?: string | null; proposed_conclusion?: string | null; recommended_actions?: unknown };
  established_facts?: unknown;
  contradictions?: unknown;
  unknowns?: { open?: unknown; accepted_limitations?: unknown } | null;
  risk_review?: unknown;
  regulatory_review?: unknown;
  ai_assistance?: unknown;
  readiness?: { checks?: unknown } | null;
};

export type DecisionReviewer = {
  kind?: string | null;
  kind_label?: string | null;
  name?: string | null;
  role?: string | null;
  action?: string | null;
  outcome?: string | null;
  outcome_label?: string | null;
  comment?: string | null;
  at?: string | null;
};

export type DecisionContextActions = { can_sign?: boolean | null; can_return?: boolean | null; reason?: string | null };

export type CaseDecisionContext = {
  investigation?: {
    id?: string | null;
    business_id?: string | null;
    question?: string | null;
    workflow_state?: string | null;
  } | null;
  brief?: DecisionBrief | null;
  reviewers?: DecisionReviewer[] | null;
  decisions?: CaseDecisionRow[] | null;
  current_decision?: CaseDecisionRow | null;
  outcomes?: unknown;
  follow_up_options?: unknown;
  actions?: DecisionContextActions | null;
  signature_meaning?: string | null;
};

/** Whether the brief still matches its fingerprint as the server checked it: verified, not matching, or not checked. */
export function hashState(brief: Pick<DecisionBrief, "hash_verified" | "content_hash"> | null | undefined) {
  if (brief?.hash_verified === true) return { key: "verified", label: "Verified", tone: "good" as Tone };
  if (brief?.hash_verified === false)
    return { key: "mismatch", label: "Does not match its fingerprint", tone: "critical" as Tone };
  return { key: "unchecked", label: "Not checked", tone: "neutral" as Tone };
}

/** The brief's open unknowns and accepted limitations, as lines. */
export function residualUnknowns(brief: Pick<DecisionBrief, "unknowns"> | null | undefined) {
  const unknowns = record(brief?.unknowns) ?? {};
  return { open: briefLines(unknowns.open), limitations: briefLines(unknowns.accepted_limitations) };
}

/** Whether the decision maker must acknowledge residual unknowns: the brief lists open unknowns or limitations. */
export function acknowledgementRequired(brief: Pick<DecisionBrief, "unknowns"> | null | undefined): boolean {
  const residual = residualUnknowns(brief);
  return residual.open.length + residual.limitations.length > 0;
}

/** The recommended actions of the brief's narrative as a list. */
export const recommendedActions = (brief: Pick<DecisionBrief, "narrative"> | null | undefined) =>
  actionsOf(brief?.narrative?.recommended_actions);

/** One reviewer line: who did what (as people read it), when and with which comment. */
export function reviewerLine(reviewer: DecisionReviewer | null | undefined) {
  const row = reviewer ?? {};
  const action = safeText(row.outcome_label) ?? safeText(row.outcome) ?? safeText(row.action);
  return {
    kind: safeText(row.kind_label) ?? (safeText(row.kind) ? titleCase(String(row.kind)) : "Review"),
    name: safeText(row.name),
    role: safeText(row.role),
    action: action ? (/^[A-Z0-9_]+$/.test(action) ? titleCase(action) : action) : null,
    comment: safeText(row.comment),
    at: safeText(row.at),
  };
}

/** A reference to another decision (an object or a plain ID): its id to open and its business ID to show. */
export function decisionRef(value: unknown, fallbackId?: unknown): { id: string | null; label: string } | null {
  const row = record(value);
  const id = idText(row?.id) ?? (typeof value === "string" ? idText(value) : null) ?? idText(fallbackId);
  const business = safeText(row?.business_id) ?? (typeof value === "string" ? safeText(value) : null);
  if (!id && !business) return null;
  return { id: id ?? business, label: business ?? "Decision" };
}

export type HistoryRow = {
  key: string;
  id: string | null;
  businessId: string;
  outcome: string;
  outcomeTone: Tone;
  status: string;
  statusTone: Tone;
  current: boolean;
  decidedAt: string | null;
  signer: string | null;
  signerRole: string | null;
  supersedes: { id: string | null; label: string } | null;
  supersededBy: { id: string | null; label: string } | null;
};

const decidedAt = (row: CaseDecisionRow) => safeText(row.decided_at) ?? safeText(row.signed_at);

/**
 * Every decision of the case, newest first: the current one, and those it superseded (each with links to the decision
 * that replaced it and the one it replaced).
 */
export function decisionHistory(
  decisions: CaseDecisionRow[] | null | undefined,
  current?: CaseDecisionRow | null,
): HistoryRow[] {
  const list = [...(decisions ?? [])];
  if (current && !list.some((row) => (current.id && row.id === current.id) || row === current)) list.unshift(current);
  const currentId = idText(current?.id);
  return list
    .map((row, index) => {
      const supersededBy = decisionRef(row.superseded_by, row.superseded_by_decision_id);
      const status = code(row.status);
      const isCurrent =
        status !== "SUPERSEDED" && (row.is_current === true || (!!currentId && idText(row.id) === currentId));
      const superseded = !isCurrent && (!!supersededBy || status === "SUPERSEDED");
      return {
        index,
        time: Date.parse(decidedAt(row) ?? "") || 0,
        row: {
          key: `${idText(row.id) ?? safeText(row.business_id) ?? "decision"}:${index}`,
          id: idText(row.id) ?? safeText(row.business_id),
          businessId: safeText(row.business_id) ?? "Decision",
          outcome: outcomeLabel(row.outcome, row.outcome_label),
          outcomeTone: outcomeTone(row.outcome),
          status: isCurrent
            ? "Current"
            : superseded
              ? "Superseded"
              : (safeText(row.status_label) ?? (status ? titleCase(status) : "Recorded")),
          statusTone: (isCurrent ? "good" : "neutral") as Tone,
          current: isCurrent,
          decidedAt: decidedAt(row),
          signer: safeText(row.signer_name),
          signerRole: safeText(row.signer_role),
          supersedes: decisionRef(row.supersedes, row.supersedes_decision_id),
          supersededBy,
        },
      };
    })
    .sort((a, b) => Number(b.row.current) - Number(a.row.current) || b.time - a.time || a.index - b.index)
    .map((item) => item.row);
}

// ---------------------------------------------------------------------------------------------------------------
// The decision form

export const RATIONALE_MIN = 20;
export const RATIONALE_MAX = 5000;
export const CONDITIONS_MIN = 10;
export const CONDITIONS_MAX = 5000;
export const SUPERSEDE_REASON_MIN = 10;
export const SUPERSEDE_REASON_MAX = 5000;
export const RETURN_COMMENT_MIN = 10;
export const RETURN_COMMENT_MAX = 5000;
export const FOLLOW_UP_TITLE_MAX = 300;

export type FollowUpChoice = {
  selected: boolean;
  title: string;
  assigneeUserId: string;
  assignedRole: string;
  /** YYYY-MM-DD from a date field; empty for none. */
  dueDay: string;
};

export type DecisionForm = {
  outcome: string;
  rationale: string;
  conditions: string;
  followUps: Record<string, FollowUpChoice>;
  acknowledged: boolean;
  supersedeReason: string;
};

export const emptyFollowUp = (): FollowUpChoice => ({
  selected: false,
  title: "",
  assigneeUserId: "",
  assignedRole: "",
  dueDay: "",
});

/**
 * Which follow-up actions a recommended action of the brief names, by its words (most specific first); none when no
 * word clearly applies. The decision maker still confirms each one before signing.
 */
const FOLLOW_UP_WORDS: ReadonlyArray<[FollowUpAction, RegExp]> = [
  [
    "REGULATORY_ACTION_REQUIRED",
    /\b(mdr|vigilance|regulator\w*|fda|notified body|competent authority|report(ing)? to)\b/i,
  ],
  [
    "FIELD_ACTION_REVIEW_REQUIRED",
    /\b(recall|field (action|safety|correction)|fsca|fsn|advisory notice|customer notification|quarantine|contain\w*)\b/i,
  ],
  ["RISK_REASSESSMENT_REQUIRED", /\b(risk (file|assessment|analysis|management|reassess\w*)|fmea|hazard analysis)\b/i],
  [
    "PRODUCT_CHANGE_REQUIRED",
    /\b(design change|product change|firmware|software update|engineering change|change request|redesign|tool(ing)? change|specification change)\b/i,
  ],
  [
    "CAPA_REQUIRED",
    // Named outright (CAPA, corrective, preventive, root cause), or a corrective action in other words: restoring or
    // tightening a quality control (inspection, sampling, a process or procedure, training, the supplier's controls)
    // removes the cause found, so it is done under a CAPA. Containing lots alone is a field action review.
    new RegExp(
      [
        String.raw`\b(capa|scar|corrective|preventive|prevent (recurrence|reoccurrence)|root cause)\b`,
        String.raw`\b(restore|reinstate|re-?establish|tighten|increase|strengthen|revise|retrain|re-?validate|re-?qualify)\b.*\b(inspection|sampling|acceptance|process|procedure|controls?|supplier|training|work instruction|sop|validation|qualification)\b`,
      ].join("|"),
      "i",
    ),
  ],
];

export function followUpTypesOf(action: string): FollowUpAction[] {
  return FOLLOW_UP_WORDS.filter(([, words]) => words.test(action)).map(([code]) => code);
}

/** The follow-ups the brief's recommended actions name, ticked, with the actions as their titles. */
export function followUpsFromActions(actions: readonly string[]): Record<string, FollowUpChoice> {
  const found: Record<string, FollowUpChoice> = {};
  for (const action of actions) {
    const text = action.replace(/\s+/g, " ").trim();
    if (!text) continue;
    for (const code of followUpTypesOf(text)) {
      const current = found[code];
      const title = current?.title ? `${current.title}; ${text}` : text;
      found[code] = { ...emptyFollowUp(), selected: true, title: title.slice(0, FOLLOW_UP_TITLE_MAX) };
    }
  }
  return found;
}

export const emptyDecisionForm = (): DecisionForm => ({
  outcome: "",
  rationale: "",
  conditions: "",
  followUps: {},
  acknowledged: false,
  supersedeReason: "",
});

const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** The follow-ups chosen, in the order offered (only for an outcome that takes them). */
export function chosenFollowUps(form: DecisionForm, order: readonly string[] = FOLLOW_UP_ACTIONS) {
  if (!outcomeRules(form.outcome).followUps) return [];
  const keys = [...order, ...Object.keys(form.followUps).filter((key) => !order.includes(key))];
  return keys
    .filter((key) => form.followUps[key]?.selected)
    .map((key) => ({ actionType: key, choice: form.followUps[key] }));
}

/**
 * What still stops the decision from being signed (the server checks the same rules): an outcome, conditions for
 * an acceptance with conditions, the acknowledgement of residual unknowns, the rationale, and the reason a new decision
 * supersedes the current one. Empty when the form is complete.
 */
export function decisionFormProblems(
  form: DecisionForm,
  context: { acknowledgementRequired: boolean; supersedes: boolean },
): string[] {
  const problems: string[] = [];
  if (!code(form.outcome)) problems.push("Choose an outcome.");
  if (outcomeRules(form.outcome).conditions) {
    const problem = textProblem(form.conditions, "the conditions", { min: CONDITIONS_MIN, max: CONDITIONS_MAX });
    if (problem) problems.push(problem);
  }
  for (const { actionType, choice } of chosenFollowUps(form)) {
    const label = FOLLOW_UP_ACTION_LABELS[actionType as FollowUpAction] ?? titleCase(actionType);
    if (choice.title.trim().length > FOLLOW_UP_TITLE_MAX)
      problems.push(`Keep the title of "${label}" to ${FOLLOW_UP_TITLE_MAX} characters.`);
    if (choice.dueDay.trim() && !(DAY.test(choice.dueDay.trim()) && dueAtFromDay(choice.dueDay)))
      problems.push(`Choose a valid due date for "${label}".`);
  }
  if (context.acknowledgementRequired && !form.acknowledged)
    problems.push("Acknowledge the open unknowns and accepted limitations the brief lists.");
  const rationale = textProblem(form.rationale, "your rationale", { min: RATIONALE_MIN, max: RATIONALE_MAX });
  if (rationale) problems.push(rationale);
  if (context.supersedes) {
    const reason = textProblem(form.supersedeReason, "why this decision supersedes the current one", {
      min: SUPERSEDE_REASON_MIN,
      max: SUPERSEDE_REASON_MAX,
    });
    if (reason) problems.push(reason);
  }
  return problems;
}

export type SignContext = {
  briefVersionId: string;
  briefContentHash: string;
  /** The current decision a new one supersedes; null when the case has none. */
  supersedesDecisionId?: string | null;
};

/**
 * The decision part of a signature request, without any secret: the outcome, rationale, conditions and follow-ups
 * that apply to it, the acknowledgement, and what it supersedes.
 */
export function decisionDraftBody(form: DecisionForm, context: SignContext) {
  const outcome = code(form.outcome);
  const rules = outcomeRules(outcome);
  const supersedes = idText(context.supersedesDecisionId);
  const conditions = form.conditions.trim();
  return {
    brief_version_id: context.briefVersionId,
    brief_content_hash: context.briefContentHash,
    outcome,
    rationale: form.rationale.trim(),
    ...(rules.conditions && conditions ? { conditions } : {}),
    ...(rules.followUps
      ? {
          follow_ups: chosenFollowUps(form).map(({ actionType, choice }) => {
            const title = choice.title.trim();
            const due = choice.dueDay.trim() ? dueAtFromDay(choice.dueDay) : null;
            return {
              action_type: actionType,
              ...(title ? { title } : {}),
              ...(choice.assigneeUserId ? { assignee_user_id: choice.assigneeUserId } : {}),
              ...(!choice.assigneeUserId && choice.assignedRole ? { assigned_role: choice.assignedRole } : {}),
              ...(due ? { due_at: due } : {}),
            };
          }),
        }
      : {}),
    residual_unknowns_acknowledged: form.acknowledged === true,
    ...(supersedes ? { supersedes_decision_id: supersedes, supersede_reason: form.supersedeReason.trim() } : {}),
  };
}

/**
 * The full body of POST /decision/sign, built only at the moment of signing. The password and code are copied into
 * this one request body and nowhere else; the caller clears its fields once the call has returned.
 */
export function signBody(
  form: DecisionForm,
  context: SignContext,
  credentials: { password: string; mfaCode?: string },
) {
  const mfa = (credentials.mfaCode ?? "").replace(/\D/g, "");
  return {
    ...decisionDraftBody(form, context),
    password: credentials.password,
    ...(mfa ? { mfa_code: mfa } : {}),
  };
}

/** The decision a signature request returned (a decision row, or a record holding one): what opens its record. */
export function signedDecisionRef(result: unknown): { ref: string | null; label: string } {
  const row = record(result) ?? {};
  const decision = record(row.decision) ?? row;
  const business = safeText(decision.business_id);
  return { ref: idText(decision.id) ?? business, label: business ?? "The decision" };
}

/** Why the sign step cannot be sent yet: the password (and a 6-digit code when one is typed). */
export function credentialsProblem(credentials: { password: string; mfaCode?: string }): string | null {
  if (!credentials.password) return "Enter your password to sign.";
  const mfa = (credentials.mfaCode ?? "").trim();
  if (mfa && !/^\d{6}$/.test(mfa)) return "Enter the 6-digit code from your authenticator app.";
  return null;
}

/** The body of POST /decision/return: the brief version and the comment (not a signature). */
export const returnBody = (briefVersionId: string, comment: string) => ({
  brief_version_id: briefVersionId,
  comment: comment.trim(),
});

export const returnProblem = (comment: string) =>
  textProblem(comment, "a comment for the investigator", { min: RETURN_COMMENT_MIN, max: RETURN_COMMENT_MAX });

/**
 * What the signature means, in one sentence shown before signing: who signs, as which role, the outcome, and exactly
 * which brief version (by its ID, version and fingerprint) it applies to.
 */
export function signatureMeaning(input: {
  signer?: string | null;
  role?: string | null;
  outcome: string;
  caseId?: string | null;
  briefId?: string | null;
  version?: number | string | null;
  contentHash?: string | null;
}): string {
  const who = safeText(input.signer) ?? "I";
  const role = safeText(input.role);
  const brief = [
    safeText(input.briefId) ?? "the Decision Brief",
    input.version !== null && input.version !== undefined && String(input.version).trim()
      ? `version ${input.version}`
      : null,
  ]
    .filter(Boolean)
    .join(" ");
  const fingerprint = input.contentHash ? ` (fingerprint ${shortHash(input.contentHash)})` : "";
  const subject = who === "I" ? "I" : `I, ${who}${role ? `, ${role}` : ""},`;
  const kase = safeText(input.caseId);
  return (
    `${subject} have reviewed ${brief}${fingerprint}${kase ? ` for ${kase}` : ""} and decide: ` +
    `${outcomeLabel(input.outcome)}. My signature applies to this decision and this brief version only.`
  );
}

/**
 * What to tell the person when signing was refused, and what to do next: reload the view (the brief changed or a
 * decision was signed meanwhile) or stay on the sign step. The server's own message is shown for a wrong password or
 * code; the password is never part of a message.
 */
export function signErrorView(error: unknown): { text: string; reload: boolean; credentials: boolean } {
  const known = error instanceof ApiError ? error.code : undefined;
  const status = error instanceof ApiError ? error.status : 0;
  const reloads: Record<string, string> = {
    STALE_BRIEF:
      "The brief changed since you opened it. The current version has been loaded: review it before you sign.",
    BRIEF_TAMPERED:
      "The brief no longer matches its fingerprint, so it cannot be signed. Report this to your quality lead.",
    SUPERSEDE_REQUIRED:
      "A decision was signed on this case meanwhile. Review it: a new decision must supersede it, with a reason.",
  };
  const refusals: Record<string, string> = {
    SOD_DENIED: "You prepared or reviewed this brief, so another authorized decision maker must sign.",
    ADMINISTRATOR_CANNOT_SIGN: "Administrators never sign decisions. An authorized decision maker must sign.",
    APPROVAL_AUTHORITY_DENIED: "Your role has no authority to sign this decision. Ask an authorized decision maker.",
    DENIED_NOT_ENTITLED: "Controlled signatures are not enabled for your organization.",
    MFA_ENROLLMENT_REQUIRED: "Signing needs an authenticator app. Set it up under My Account first.",
    SIGNATURE_TEMPORARILY_LOCKED: "Too many failed attempts. Signing is locked for your account for a while.",
  };
  if (known && reloads[known]) return { text: reloads[known], reload: true, credentials: false };
  if (known && refusals[known]) return { text: refusals[known], reload: false, credentials: false };
  // A wrong password or code (401, or 403 about the second factor): the server's own words.
  const credentials = status === 401 || known === "MFA_REQUIRED" || known === "INVALID_REAUTHENTICATION";
  return { text: describeError(error, "The decision was not signed."), reload: false, credentials };
}

// ---------------------------------------------------------------------------------------------------------------
// The approvals queue (GET /api/v1/decisions/queue) and the summary (GET /api/v1/decisions/summary)

export type DecisionQueueItem = {
  investigation?: {
    id?: string | null;
    business_id?: string | null;
    question?: string | null;
    priority?: string | null;
    due_at?: string | null;
    overdue?: boolean | null;
    product_id?: string | null;
    product?: { id?: string | null; business_id?: string | null; name?: string | null } | null;
  } | null;
  brief?: {
    id?: string | null;
    business_id?: string | null;
    version?: number | string | null;
    content_hash?: string | null;
    approved_at?: string | null;
    quality_reviewer_name?: string | null;
  } | null;
  critical?: boolean | null;
  required_reviews?: unknown;
  awaiting_since?: string | null;
  actions?: { can_decide?: boolean | null; reason?: string | null } | null;
};

export type QueueRow = {
  key: string;
  investigationId: string | null;
  productId: string | null;
  caseId: string;
  question: string | null;
  product: string | null;
  priority: string | null;
  dueAt: string | null;
  overdue: boolean;
  briefId: string | null;
  version: string | null;
  approvedAt: string | null;
  qualityReviewer: string | null;
  critical: boolean;
  requiredReviews: string[];
  awaitingSince: string | null;
  canDecide: boolean;
  reason: string | null;
};

/** The reviews a case needs (strings, or objects with a label or kind and a status), as short labels. */
export function requiredReviewLabels(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === "string") return safeText(item) ? titleCase(code(item)) : null;
      const row = record(item);
      if (!row) return null;
      const name =
        safeText(row.label) ?? safeText(row.kind_label) ?? (safeText(row.kind) ? titleCase(code(row.kind)) : null);
      const status = safeText(row.status_label) ?? (safeText(row.status) ? titleCase(code(row.status)) : null);
      return name ? (status ? `${name}: ${status}` : name) : null;
    })
    .filter((item): item is string => !!item);
}

/** One row of the queue (or of the summary's awaiting list), whether the case is nested or flat. */
export function queueRow(value: DecisionQueueItem | Record<string, unknown> | null | undefined, index = 0): QueueRow {
  const item = (value ?? {}) as Record<string, unknown>;
  const investigation = record(item.investigation) ?? {};
  const product = record(investigation.product) ?? {};
  const brief = record(item.brief) ?? {};
  const actions = record(item.actions) ?? {};
  // The investigation's UUID is the technical key the context uses; it is never shown.
  const id = idText(investigation.id) ?? idText(item.investigation_id);
  const version = brief.version ?? item.version;
  const dueAt = safeText(investigation.due_at) ?? safeText(item.due_at);
  return {
    key: `${index}:${id ?? ""}`,
    investigationId: id,
    productId: idText(product.id) ?? idText(investigation.product_id) ?? idText(item.product_id),
    caseId:
      safeText(investigation.business_id) ??
      safeText(item.investigation_business_id) ??
      safeText(item.case_business_id) ??
      "Case",
    question: safeText(investigation.question) ?? safeText(item.question),
    product: safeText(product.name) ?? safeText(product.business_id),
    priority: safeText(investigation.priority) ?? safeText(item.priority),
    dueAt,
    overdue:
      investigation.overdue === true ||
      dueState({ due_at: dueAt, overdue: null, status: null, completed_at: null }) === "overdue",
    briefId: safeText(brief.business_id) ?? safeText(item.brief_business_id),
    version: typeof version === "number" || typeof version === "string" ? String(version) : null,
    approvedAt: safeText(brief.approved_at),
    qualityReviewer: safeText(brief.quality_reviewer_name),
    critical: item.critical === true,
    requiredReviews: requiredReviewLabels(item.required_reviews),
    awaitingSince: safeText(item.awaiting_since) ?? safeText(brief.approved_at),
    canDecide: actions.can_decide !== false,
    reason: safeText(actions.reason),
  };
}

const timeOf = (value: string | null, missing: number) => {
  const time = value ? Date.parse(value) : Number.NaN;
  return Number.isNaN(time) ? missing : time;
};

/** The queue in the order to decide it: critical, then overdue, then priority, then nearest due, then longest waiting. */
export function sortQueue(rows: QueueRow[]): QueueRow[] {
  return rows
    .map((row, index) => ({ row, index }))
    .sort(
      (a, b) =>
        Number(b.row.critical) - Number(a.row.critical) ||
        Number(b.row.overdue) - Number(a.row.overdue) ||
        priorityRank(b.row.priority) - priorityRank(a.row.priority) ||
        timeOf(a.row.dueAt, Number.POSITIVE_INFINITY) - timeOf(b.row.dueAt, Number.POSITIVE_INFINITY) ||
        timeOf(a.row.awaitingSince, Number.POSITIVE_INFINITY) - timeOf(b.row.awaitingSince, Number.POSITIVE_INFINITY) ||
        a.index - b.index,
    )
    .map((item) => item.row);
}

export type DecisionSummaryCounts = Partial<
  Record<
    | "awaiting_signature"
    | "critical"
    | "due_soon"
    | "overdue"
    | "signed_30d"
    | "returned_30d"
    | "follow_ups_open"
    | "follow_ups_overdue"
    | "impact_assessments_open",
    number
  >
>;

export type DecisionSummary = {
  counts?: DecisionSummaryCounts | null;
  awaiting?: unknown;
  recent?: unknown;
};

export type DecisionTile = { key: keyof DecisionSummaryCounts; label: string; value: number | null; urgent?: boolean };

/** The count tiles of the decision maker's summary; a count the server did not send reads as unknown. */
export function decisionTiles(summary: DecisionSummary | null | undefined): DecisionTile[] {
  const counts = summary?.counts ?? {};
  const value = (key: keyof DecisionSummaryCounts) => {
    const count = counts[key];
    return typeof count === "number" && Number.isFinite(count) ? count : null;
  };
  return [
    { key: "awaiting_signature", label: "Awaiting signature", value: value("awaiting_signature") },
    { key: "critical", label: "Critical", value: value("critical"), urgent: true },
    { key: "due_soon", label: "Due soon", value: value("due_soon") },
    { key: "overdue", label: "Overdue", value: value("overdue"), urgent: true },
    { key: "signed_30d", label: "Signed · 30 days", value: value("signed_30d") },
    { key: "returned_30d", label: "Returned · 30 days", value: value("returned_30d") },
    { key: "follow_ups_open", label: "Follow-ups open", value: value("follow_ups_open") },
    { key: "follow_ups_overdue", label: "Follow-ups overdue", value: value("follow_ups_overdue"), urgent: true },
    {
      key: "impact_assessments_open",
      label: "Impact assessments open",
      value: value("impact_assessments_open"),
      urgent: true,
    },
  ];
}

export type RecentDecision = {
  key: string;
  /** What opens the signed record: the decision's id, else its business ID. */
  ref: string | null;
  decisionId: string;
  caseId: string | null;
  outcome: string;
  outcomeTone: Tone;
  decidedAt: string | null;
  signer: string | null;
};

/** One recently signed decision of the summary, nested or flat. */
export function recentDecision(value: unknown, index = 0): RecentDecision {
  const row = record(value) ?? {};
  const decision = record(row.decision) ?? {};
  const investigation = record(row.investigation) ?? {};
  const business =
    safeText(decision.business_id) ?? safeText(row.decision_business_id) ?? safeText(row.business_id) ?? null;
  const ref = idText(decision.id) ?? idText(row.decision_id) ?? idText(row.id) ?? business;
  const outcome = decision.outcome ?? row.outcome;
  return {
    key: `${index}:${ref ?? ""}`,
    ref,
    decisionId: business ?? "Decision",
    caseId:
      safeText(investigation.business_id) ?? safeText(row.case_business_id) ?? safeText(row.investigation_business_id),
    outcome: outcomeLabel(outcome, decision.outcome_label ?? row.outcome_label),
    outcomeTone: outcomeTone(outcome),
    decidedAt: safeText(decision.decided_at) ?? safeText(row.decided_at) ?? safeText(row.signed_at),
    signer: safeText(row.signer_name) ?? safeText(decision.signer_name),
  };
}

// ---------------------------------------------------------------------------------------------------------------
// The signed record (GET /api/v1/decisions/{id}/record) and its verification

export const VERIFICATION_STATUS: Record<string, { label: string; tone: Tone }> = {
  VALID: { label: "Valid", tone: "good" },
  INVALID: { label: "Invalid", tone: "critical" },
  NOT_SIGNED: { label: "Not signed", tone: "neutral" },
};

/** The verification's overall result; anything unknown reads as a problem, never as valid. */
export function verificationView(status: unknown): { label: string; tone: Tone } {
  const value = code(status);
  return VERIFICATION_STATUS[value] ?? { label: value ? titleCase(value) : "Not verified", tone: "warning" };
}

const CHECK_LABELS: Record<string, string> = {
  SIGNATURE_PRESENT: "The decision carries a signature",
  SIGNATURE_FINGERPRINT: "The signature fingerprint matches the signed decision",
  SIGNATURE_HASH: "The signature fingerprint matches the signed decision",
  DECISION_HASH: "The decision is unchanged since it was signed",
  DECISION_UNCHANGED: "The decision is unchanged since it was signed",
  BRIEF_HASH: "The brief still matches the content that was signed",
  BRIEF_CONTENT_HASH: "The brief still matches the content that was signed",
  BRIEF_UNCHANGED: "The brief still matches the content that was signed",
  SNAPSHOT: "The evidence snapshot is intact",
  SNAPSHOT_HASH: "The evidence snapshot is intact",
  EVIDENCE_SNAPSHOT: "The evidence snapshot is intact",
  SIGNER_AUTHORITY: "The signer held approval authority when signing",
  SEGREGATION_OF_DUTIES: "The signer did not write or submit the brief",
  SIGNER_NOT_AUTHOR: "The signer did not write or submit the brief",
};

export type VerificationCheck = { key: string; label: string; ok: boolean; detail: string | null };

/** The verification checks, each as words, with whether it passed; a check without a clear pass counts as failed. */
export function verificationChecks(value: unknown): VerificationCheck[] {
  if (!Array.isArray(value)) return [];
  return value.map((item, index) => {
    const row = record(item) ?? {};
    const key = safeText(row.key) ?? `check-${index}`;
    return {
      key,
      label: safeText(row.label) ?? CHECK_LABELS[code(key)] ?? titleCase(code(key)),
      ok: row.ok === true,
      detail: safeText(row.detail),
    };
  });
}

/** The checks that failed (what makes a record Invalid). */
export const failedChecks = (checks: VerificationCheck[]) => checks.filter((check) => !check.ok);

/** "Valid", or "Invalid: <the failed checks>" for a summary line. */
export function verificationHeadline(status: unknown, checks: VerificationCheck[]): string {
  const view = verificationView(status);
  const failed = failedChecks(checks);
  if (code(status) === "INVALID" && failed.length)
    return `${view.label}: ${failed.map((check) => check.label).join("; ")}`;
  return view.label;
}

/**
 * Whether a decision of the decision list (or its verification report) is a signed case decision of Phase 6, whose
 * full signed record can be opened.
 */
export function isCaseDecision(decision: Record<string, unknown> | null | undefined, report?: unknown): boolean {
  const row = decision ?? {};
  const kinds = [row.kind, row.decision_kind, row.decision_type, row.object_type].map(code);
  if (kinds.includes("CASE_DECISION")) return true;
  if ((DECISION_OUTCOMES as readonly string[]).includes(code(row.outcome))) return true;
  if (idText(row.brief_version_id)) return true;
  const signatures = record(report)?.signatures;
  return (
    Array.isArray(signatures) &&
    signatures.some((item) => {
      const sig = record(item) ?? {};
      return [sig.object_type, sig.signature_type, sig.kind].map(code).includes("CASE_DECISION");
    })
  );
}
