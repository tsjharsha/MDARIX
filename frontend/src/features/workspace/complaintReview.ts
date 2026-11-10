// Pure rules for Complaints (the second look and the backlog board): what each list asks the server for, how reasons,
// complaint signs and backlog states read, where a description's matched words are, and what a decision or a change of
// the settings sends and when it may be sent. The server (/api/v1/complaints, backend/app/complaint_review) finds the
// records and decides every action; these only shape what the person sees and what is sent.
import type { Slice, Tone } from "../admin/console/dashboardModel";
import type { TrustSummary } from "./trust";

export const COMPLAINTS_TABS = [
  // Before every other queue: the events flagged or escalated for triage, then the calls and urgent intakes with their
  // first-contact check (intake.ts, T-G19, T-G32).
  "Triage",
  "First contact",
  // How each complaint is resolved: routine first (disposition.ts, T-G36).
  "Dispositions",
  "Second look",
  "Backlog",
  "Reportability",
  // The report worksheets, the second person's approval and the submission record (authorityReports.ts, T-G2c, T-G2b).
  "Reports",
  // Every question to a reporter, distributor, hospital or service partner, with its attempts (communications.ts,
  // T-G30).
  "Communications",
  // Every complaint, filtered by product, version, lot, problem code, country or status (complaintList.ts).
  "Complaint list",
  "Review settings",
  "Reporting windows",
  // The organization's own versions of each market's guide (decisionGuides.ts, T-G15).
  "Decision guides",
] as const;
export type ComplaintsTab = (typeof COMPLAINTS_TABS)[number];

/** The server's limits (backend/app/complaint_review/rules.py). */
export const REVIEW_LIMITS = {
  reasonMin: 10,
  reasonMax: 2000,
  targetDays: [1, 365] as const,
  wordsMax: 100,
  wordMaxLength: 60,
};
export const PAGE_SIZE = 25;

export type ReviewReason = { code: string; label: string; count?: number };
/** `value`: a problem code's own text (PROBLEM_CODE), shown with its IMDRF term (0.10.70). */
export type ComplaintSign = { code: string; label: string; value?: string | null };
export type SecondLookDecision = {
  decision: "CONFIRMED" | "DISMISSED" | string;
  reason: string;
  decided_by: string;
  decided_at: string | null;
};

/** A complaint record as both boards list it. */
export type ReviewRecord = {
  id: string;
  business_id: string | null;
  complaint_identifier: string | null;
  product_id: string | null;
  product_name: string | null;
  version: string | null;
  status: string | null;
  complaint_type: string | null;
  problem_code: string | null;
  severity: string | null;
  description: string | null;
  received_date: string | null;
  patient_involved: boolean | null;
  serious_injury: boolean | null;
  death: boolean | null;
  malfunction: boolean | null;
};

export type SecondLookItem = ReviewRecord & {
  reasons: ReviewReason[];
  signs: ComplaintSign[];
  words: string[];
  score: number;
  decision: SecondLookDecision | null;
  // The latest AI explanation of the record, when someone asked for one (Phase 6).
  explanation?: SecondLookExplanation | null;
};

/** A quote the AI took word for word from one of the record's fields (checked by the server). */
export type ExplanationQuote = { field: string; label: string; text: string };
export type ExplanationSentence = { text: string; quotes: ExplanationQuote[]; fields?: string[] };

/**
 * The AI's explanation of why a flagged record may meet the complaint definition: at most three sentences, each quoting
 * the record's own words (backend/app/complaint_review/explain.py). ``author: "RULES"`` with no sentences when AI is
 * off, unavailable or over budget, with why in ``ai``.
 */
export type SecondLookExplanation = {
  author: "AI" | "RULES";
  sentences: ExplanationSentence[];
  ai: {
    status: string;
    reason?: string | null;
    message?: string | null;
    provider?: string | null;
    model?: string | null;
    ai_execution_id?: string;
    explained_at?: string | null;
    dropped?: Array<{ text: string; reason: string }>;
    trust?: TrustSummary | null;
    label?: string;
  };
};

export const explainPath = (complaintId: string) =>
  `/api/v1/complaints/${encodeURIComponent(complaintId)}/second-look/explain`;

const EXPLANATION_REASONS: Record<string, string> = {
  PROVIDER_NOT_CONFIGURED: "No AI provider is set up yet, so the reasons above come from the rules.",
  NOTHING_TO_EXPLAIN: "The record has no description or harm flags for AI to explain.",
  NOTHING_KEPT: "AI wrote nothing that passed the checks (every quote must be the record's own words).",
  UNREADABLE: "AI's reply could not be read; the reasons above come from the rules.",
};

/** Why there is no AI explanation, in plain words; null when there is one. */
export function explanationNote(explanation: SecondLookExplanation | null | undefined): string | null {
  if (!explanation || explanation.author === "AI") return null;
  const ai = explanation.ai ?? { status: "" };
  return (
    ai.message ??
    EXPLANATION_REASONS[ai.reason ?? ""] ??
    EXPLANATION_REASONS[ai.status] ??
    "AI is not available right now; the reasons above come from the rules."
  );
}

export type SecondLookSummary = {
  to_review: number;
  with_harm: number;
  confirmed: number;
  dismissed: number;
  by_reason: Record<string, number>;
};

export type SecondLookList = {
  summary: SecondLookSummary;
  state: "open" | "decided";
  total: number;
  page: number;
  page_size: number;
  pages: number;
  truncated: boolean;
  items: SecondLookItem[];
};

export type BacklogState = "PAST_TARGET" | "DUE_SOON" | "ON_TRACK";

export type BacklogItem = ReviewRecord & {
  age_days: number | null;
  days_past_target: number;
  state: BacklogState;
  band: string;
  confirmed_on_second_look: boolean;
};

export type BacklogSummary = {
  target_days: number;
  open_unlinked: number;
  past_target: number;
  due_soon: number;
  on_track: number;
  oldest_days: number | null;
  bands: Array<{ band: string; count: number }>;
};

export type BacklogList = {
  summary: BacklogSummary;
  show: "all" | "past_target" | "due_soon";
  total: number;
  page: number;
  page_size: number;
  pages: number;
  truncated: boolean;
  items: BacklogItem[];
};

export type ReviewSettings = {
  backlog_target_days: number;
  second_look_words: string[];
  custom_words: boolean;
  default_words: string[];
  version: number;
  updated_by_name: string | null;
  updated_at: string | null;
};

const count = (value: number, noun: string, plural = `${noun}s`) =>
  `${value.toLocaleString()} ${value === 1 ? noun : plural}`;

/** Spaces collapsed and the ends trimmed: what the server keeps of a reason. */
export const collapsed = (value: string) => value.replace(/\s+/g, " ").trim();

// Lists ------------------------------------------------------------------------------------------------------------

export function secondLookPath(
  state: "open" | "decided" | "dismissed",
  productId: string,
  page: number,
  pageSize = PAGE_SIZE,
) {
  const params = new URLSearchParams({ state, page: String(page), page_size: String(pageSize) });
  if (productId) params.set("product_id", productId);
  return `/api/v1/complaints/second-look?${params}`;
}

export const BACKLOG_SHOWS = [
  { value: "all", label: "All open" },
  { value: "past_target", label: "Past target" },
  { value: "due_soon", label: "Due soon" },
] as const;
export type BacklogShow = (typeof BACKLOG_SHOWS)[number]["value"];

export function backlogPath(show: BacklogShow, productId: string, page: number, pageSize = PAGE_SIZE) {
  const params = new URLSearchParams({ show, page: String(page), page_size: String(pageSize) });
  if (productId) params.set("product_id", productId);
  return `/api/v1/complaints/backlog?${params}`;
}

// The second look ----------------------------------------------------------------------------------------------------

/** Harm outranks everything: a death or a serious injury is critical, a patient or a malfunction serious. */
export function signTone(code: string): Tone {
  if (code === "DEATH" || code === "SERIOUS_INJURY") return "critical";
  if (code === "PATIENT_INVOLVED" || code === "MALFUNCTION") return "serious";
  if (code === "SEVERITY") return "warning";
  return "neutral";
}

const TONE_RANK: Record<Tone, number> = { critical: 4, serious: 3, warning: 2, neutral: 1, good: 0 };

/** The most serious tone among a record's signs (the colour of its card's edge); neutral without signs. */
export function recordTone(signs: readonly ComplaintSign[]): Tone {
  return signs.reduce<Tone>((worst, sign) => {
    const tone = signTone(sign.code);
    return TONE_RANK[tone] > TONE_RANK[worst] ? tone : worst;
  }, "neutral");
}

/** Why records are on the second look, in plain words, for the summary. */
export const REASON_NAMES: Record<string, string> = {
  CANCELLED: "Cancelled or rejected",
  INQUIRY: "Logged as an inquiry or service record",
  NFF_RECURRING: "Recurring No Fault Found or User Error",
};

export function reasonSlices(byReason: Record<string, number> | null | undefined): Slice[] {
  return Object.keys(REASON_NAMES).map((code) => ({
    key: code,
    label: REASON_NAMES[code],
    count: Number(byReason?.[code] ?? 0),
    tone: "neutral" as const,
  }));
}

export function secondLookHeadline(summary: SecondLookSummary | null | undefined): {
  title: string;
  detail: string;
  tone: Tone;
} {
  const open = summary?.to_review ?? 0;
  const harm = summary?.with_harm ?? 0;
  if (!open)
    return {
      title: "Nothing waits for a second look",
      detail:
        "No cancelled record or inquiry carries a sign of a complaint, and no No Fault Found or User Error code recurs. MDARIX checks again as records arrive.",
      tone: "good",
    };
  return {
    title: `${count(open, "record")} may be ${open === 1 ? "a hidden complaint" : "hidden complaints"}`,
    detail: harm
      ? `${count(harm, "record")} ${harm === 1 ? "reports" : "report"} a death or a serious injury. Start there: the list is most serious first.`
      : "Each one shows why it was flagged.",
    tone: harm ? "critical" : "warning",
  };
}

export const DECISION_TEXT: Record<"CONFIRMED" | "DISMISSED", { action: string; badge: string; tone: Tone }> = {
  CONFIRMED: { action: "It is a complaint", badge: "Confirmed complaint", tone: "warning" },
  DISMISSED: { action: "Not a complaint", badge: "Dismissed", tone: "neutral" },
};

export function decisionText(decision: string | null | undefined) {
  return decision === "CONFIRMED" || decision === "DISMISSED" ? DECISION_TEXT[decision] : null;
}

export function decisionProblem(reason: string): string | null {
  const text = collapsed(reason);
  if (text.length < REVIEW_LIMITS.reasonMin) return `Say in at least ${REVIEW_LIMITS.reasonMin} characters why`;
  if (text.length > REVIEW_LIMITS.reasonMax) return `Keep the reason under ${REVIEW_LIMITS.reasonMax} characters`;
  return null;
}

export function decisionBody(decision: "CONFIRMED" | "DISMISSED", reason: string) {
  return { decision, reason: collapsed(reason) };
}

/** The decision the person can change a decided record to: the other one. */
export const otherDecision = (decision: string | null | undefined): "CONFIRMED" | "DISMISSED" =>
  decision === "CONFIRMED" ? "DISMISSED" : "CONFIRMED";

/**
 * The one ID a complaint shows (stage 5, J18): the customer's own reference (SAMPLE-RV-01, the imported complaint
 * number), else its MDARIX ID. The other ID is said only under "Also known as" (sections/common.tsx AlsoKnownAs).
 */
export const recordId = (record: Pick<ReviewRecord, "business_id" | "complaint_identifier">) =>
  record.complaint_identifier?.trim() || record.business_id || "Complaint";

/** A record as a drawer, a toast or a button names it: the same one ID (0.10.70; it showed "CMP000029 (SAMPLE-RV-01)"). */
export const recordName = recordId;

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * The description cut into plain and matched parts, so the words that put it on the second look can be marked. A word
 * matches as the server matches it (backend rules.matched_words): whole words, any case, and a phrase across spaces or
 * separators ("shortness-of-breath").
 */
export function highlightParts(text: string | null | undefined, words: readonly string[]) {
  const source = text ?? "";
  const patterns = [...new Set(words.map((word) => collapsed(word.toLowerCase())).filter(Boolean))]
    .sort((a, b) => b.length - a.length)
    .map((word) => word.split(" ").map(escapeRegExp).join("[\\s_\\-/.:;,]+"));
  if (!source || !patterns.length) return source ? [{ text: source, match: false }] : [];
  // The letter or digit before a word is matched as a group rather than looked behind, which older browsers lack.
  const pattern = new RegExp(`(^|[^\\p{L}\\p{N}])(${patterns.join("|")})(?![\\p{L}\\p{N}])`, "giu");
  const parts: Array<{ text: string; match: boolean }> = [];
  let last = 0;
  for (const found of source.matchAll(pattern)) {
    const start = (found.index ?? 0) + found[1].length;
    if (start > last) parts.push({ text: source.slice(last, start), match: false });
    parts.push({ text: found[2], match: true });
    last = start + found[2].length;
  }
  if (last < source.length) parts.push({ text: source.slice(last), match: false });
  return parts;
}

// The backlog board ------------------------------------------------------------------------------------------------

export const BACKLOG_STATE: Record<BacklogState, { label: string; tone: Tone }> = {
  PAST_TARGET: { label: "Past target", tone: "critical" },
  DUE_SOON: { label: "Due soon", tone: "warning" },
  ON_TRACK: { label: "On track", tone: "good" },
};

export function backlogStateOf(state: string | null | undefined) {
  return BACKLOG_STATE[(state ?? "") as BacklogState] ?? { label: "—", tone: "neutral" as Tone };
}

/** "40 days · 10 past target", "26 days · 4 left", "Received today". */
export function backlogAgeText(age: number | null | undefined, target: number): string {
  if (typeof age !== "number" || !Number.isFinite(age) || age < 0) return "Date not recorded";
  const days = age === 0 ? "Received today" : count(age, "day");
  if (age > target) return `${days} · ${count(age - target, "day")} past target`;
  const left = target - age;
  return `${days} · ${left === 0 ? "due today" : `${count(left, "day")} left`}`;
}

/** How far a complaint has come towards its target, 0 to 100 (past the target: full). */
export function targetShare(age: number | null | undefined, target: number): number {
  if (typeof age !== "number" || !Number.isFinite(age) || target <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((age / target) * 100)));
}

function bandBounds(band: string): [number, number] {
  const range = /^(\d+)\s*-\s*(\d+)$/.exec(band);
  if (range) return [Number(range[1]), Number(range[2])];
  const open = /^(\d+)\+$/.exec(band);
  return open ? [Number(open[1]) + 1, Number.POSITIVE_INFINITY] : [0, Number.POSITIVE_INFINITY];
}

/** The age bands, toned against the target: all inside it good, all past it critical, across it a warning. */
export function bandSlices(bands: BacklogSummary["bands"] | null | undefined, target: number): Slice[] {
  return (bands ?? []).map(({ band, count: value }) => {
    const [low, high] = bandBounds(band);
    const tone: Tone = low > target ? "critical" : high <= target ? "good" : "warning";
    return { key: band, label: `${band.replace("-", "–")} days`, count: value, tone };
  });
}

export function backlogHeadline(summary: BacklogSummary | null | undefined): {
  title: string;
  detail: string;
  tone: Tone;
} {
  const open = summary?.open_unlinked ?? 0;
  const target = summary?.target_days ?? 30;
  const past = summary?.past_target ?? 0;
  const soon = summary?.due_soon ?? 0;
  if (!open)
    return {
      title: "Every open complaint is in a signal or an investigation",
      detail: "Nothing is waiting unseen. New complaints appear here until they join a signal or an investigation.",
      tone: "good",
    };
  if (past)
    return {
      title: `${count(past, "complaint")} past the ${target}-day target`,
      detail: `${count(open, "open complaint")} ${open === 1 ? "is" : "are"} in no signal and no investigation${soon ? `; ${count(soon, "more")} ${soon === 1 ? "is" : "are"} due within a week` : ""}. Oldest first below.`,
      tone: "critical",
    };
  return {
    title: soon ? `${count(soon, "complaint")} due within a week` : "Every open complaint is within its target",
    detail: `${count(open, "open complaint")} ${open === 1 ? "is" : "are"} in no signal and no investigation, against a ${target}-day target.`,
    tone: soon ? "warning" : "good",
  };
}

// Settings -----------------------------------------------------------------------------------------------------------

export type SettingsForm = { targetDays: string; words: string; useDefaults: boolean; reason: string };

export function settingsForm(settings: ReviewSettings): SettingsForm {
  return {
    targetDays: String(settings.backlog_target_days),
    words: (settings.custom_words ? settings.second_look_words : settings.default_words).join("\n"),
    useDefaults: !settings.custom_words,
    reason: "",
  };
}

/** The word list typed in (one per line or comma separated): trimmed, lower case, without blanks or repeats. */
export function wordsOf(text: string): string[] {
  const seen: string[] = [];
  for (const part of text.split(/[\n,]/)) {
    const word = collapsed(part.toLowerCase());
    if (word && !seen.includes(word)) seen.push(word);
  }
  return seen;
}

const sameList = (a: readonly string[], b: readonly string[]) =>
  a.length === b.length && a.every((value, index) => value === b[index]);

/** The custom word list the form asks for, or null for the defaults (a list equal to the defaults is the defaults). */
function wantedWords(form: SettingsForm, settings: ReviewSettings): string[] | null {
  if (form.useDefaults) return null;
  const words = wordsOf(form.words);
  return sameList(words, settings.default_words) ? null : words;
}

export function settingsChanged(settings: ReviewSettings, form: SettingsForm): boolean {
  if (Number(form.targetDays) !== settings.backlog_target_days) return true;
  const wanted = wantedWords(form, settings);
  const current = settings.custom_words ? settings.second_look_words : null;
  if (wanted === null || current === null) return wanted !== current;
  return !sameList(wanted, current);
}

export function settingsProblem(form: SettingsForm): string | null {
  const days = Number(form.targetDays);
  const [low, high] = REVIEW_LIMITS.targetDays;
  if (!/^\d+$/.test(form.targetDays.trim()) || days < low || days > high)
    return `The target is a whole number of days from ${low} to ${high}`;
  if (!form.useDefaults) {
    const words = wordsOf(form.words);
    if (!words.length) return "Keep at least one word, or use the default words";
    if (words.length > REVIEW_LIMITS.wordsMax) return `Keep at most ${REVIEW_LIMITS.wordsMax} words`;
    const long = words.find((word) => word.length > REVIEW_LIMITS.wordMaxLength);
    if (long) return `"${long.slice(0, 20)}…" is longer than ${REVIEW_LIMITS.wordMaxLength} characters`;
  }
  return decisionProblem(form.reason);
}

export function settingsBody(form: SettingsForm) {
  return {
    backlog_target_days: Number(form.targetDays),
    second_look_words: form.useDefaults ? null : wordsOf(form.words),
    reason: collapsed(form.reason),
  };
}
