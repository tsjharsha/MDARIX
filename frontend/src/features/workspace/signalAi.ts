// Pure rules for Phase 4 (Signals and AI): the trend check (Signals › Trend check, a signal's insight), the signal
// summary (from the records, or written by AI and checked), the one click from a signal to its case, and the case's
// one AI run. The server (/api/v1/triage/..., /api/v1/investigations/{id}/ai-run) computes and decides; these only
// shape what the person sees and what is sent.
import type { Tone } from "../admin/console/dashboardModel";
import type { TrustSummary } from "./trust";

export type TrendResult = "SIGNIFICANT" | "ELEVATED" | "STEADY" | "TOO_FEW" | "SHORT_HISTORY";
export type TrendGroup = "version" | "problem" | "type";

export type TrendItem = {
  key: string;
  product: { id: string; business_id: string | null; name: string | null };
  product_version: { id: string; business_id: string | null; version_identifier: string | null } | null;
  problem: string | null;
  name: string;
  recent: number;
  recent_days: number;
  history: number;
  history_days: number;
  expected: number;
  p_value: number | null;
  ratio: number | null;
  result: TrendResult;
  label: string;
  sentence: string;
  recent_complaints: Array<{ id: string; business_id: string | null }>;
  open_signals: Array<{ id: string; business_id: string | null; status: string }>;
  // md43: what the expected number follows (units in the field from lot quantities, or calendar days), and what the
  // group is compared with (its own history, or the version it replaced when it is too young for its own).
  basis?: "UNITS" | "TIME";
  baseline?: "OWN_HISTORY" | "PREVIOUS_VERSION";
  baseline_name?: string | null;
};

export type TrendBoard = {
  grouping: TrendGroup;
  recent_days: number;
  history_days: number;
  min_complaints: number;
  summary: {
    groups: number;
    complaints_counted: number;
    significant: number;
    elevated: number;
    steady: number;
    too_few: number;
    short_history: number;
  };
  truncated: boolean;
  note: string;
  // How many groups were counted per unit in the field, and how many by calendar days.
  basis?: { units: number; time: number };
  items: TrendItem[];
};

export const TREND_GROUPS: ReadonlyArray<{ value: TrendGroup; label: string }> = [
  { value: "version", label: "By version" },
  { value: "problem", label: "By problem code" },
  { value: "type", label: "By complaint type" },
];

export function trendPath(group: TrendGroup, productId = "") {
  const params = new URLSearchParams({ group });
  if (productId) params.set("product_id", productId);
  return `/api/v1/triage/trends?${params}`;
}

export const TREND_RESULT: Record<TrendResult, { label: string; tone: Tone }> = {
  SIGNIFICANT: { label: "Significant rise", tone: "critical" },
  ELEVATED: { label: "Higher than usual", tone: "warning" },
  STEADY: { label: "In line with history", tone: "good" },
  TOO_FEW: { label: "Too few to assess", tone: "neutral" },
  SHORT_HISTORY: { label: "History too short", tone: "neutral" },
};

/** What a group was compared with: its own history, or the version it replaced (a version too young for its own). */
export function trendBaselineText(item: Pick<TrendItem, "baseline" | "baseline_name" | "history" | "history_days">) {
  if (item.baseline === "PREVIOUS_VERSION")
    return `${item.baseline_name ?? "The previous version"}: ${item.history} in the ${item.history_days} days before this version's release`;
  return `Own history: ${item.history} in ${item.history_days} days`;
}

/** What the expected number follows: units in the field (lot quantities) or calendar days. */
export const trendBasisText = (item: Pick<TrendItem, "basis">) =>
  item.basis === "UNITS" ? "Per unit in the field" : "Per calendar day";

/** The result's label, saying "the previous version" when that is what the group was compared with. */
export function trendResultLabel(item: Pick<TrendItem, "result" | "baseline">): string {
  const label = trendResultOf(item.result).label;
  return item.baseline === "PREVIOUS_VERSION" && item.result === "STEADY" ? "In line with the previous version" : label;
}

export const trendResultOf = (result: string | null | undefined) =>
  TREND_RESULT[(result ?? "") as TrendResult] ?? { label: "—", tone: "neutral" as Tone };

/** "p 0.004", "p < 0.001", or "—" when the group was not assessed. */
export function pValueText(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  if (value < 0.001) return "p < 0.001";
  return `p ${value.toFixed(3)}`;
}

/** "6 against 1.0 expected (6.0×)". */
export function trendCountText(item: Pick<TrendItem, "recent" | "expected" | "ratio" | "result">): string {
  if (item.result === "SHORT_HISTORY") return `${item.recent} in 30 days`;
  const ratio = typeof item.ratio === "number" ? ` (${item.ratio.toFixed(1)}×)` : "";
  return `${item.recent} against ${item.expected.toFixed(1)} expected${ratio}`;
}

export function trendHeadline(board: TrendBoard | null | undefined): { title: string; detail: string; tone: Tone } {
  if (!board) return { title: "Checking every version against its own history…", detail: "", tone: "neutral" };
  const { significant, elevated, groups, complaints_counted } = board.summary;
  const counted = `${complaints_counted.toLocaleString()} complaints counted across ${groups.toLocaleString()} groups, whatever their status.`;
  if (significant)
    return {
      title: `${significant} ${significant === 1 ? "group" : "groups"} rising significantly against their own history`,
      detail: `${counted} Each needs a person's look: open its signal or raise one.`,
      tone: "critical",
    };
  if (elevated)
    return {
      title: `${elevated} ${elevated === 1 ? "group" : "groups"} higher than usual`,
      detail: `${counted} Not significant yet; worth watching.`,
      tone: "warning",
    };
  return { title: "No version is rising against its own history", detail: counted, tone: "good" };
}

/** Whether a person may raise a signal from a trend group: notable, with recent complaints, no open signal on it. */
export const canRaiseFromTrend = (item: TrendItem) =>
  (item.result === "SIGNIFICANT" || item.result === "ELEVATED") &&
  item.recent_complaints.length > 0 &&
  item.open_signals.length === 0;

/** The manual signal a trend group becomes (POST /api/v1/triage/signals). */
export function signalFromTrend(item: TrendItem) {
  return {
    title: `Trend check: ${item.name}`.slice(0, 300),
    description: item.sentence,
    product_id: item.product.id,
    ...(item.product_version ? { product_version_id: item.product_version.id } : {}),
    complaint_ids: item.recent_complaints.map((complaint) => complaint.id),
    reason: `Raised from the trend check: ${item.label.toLowerCase()} (${pValueText(item.p_value)})`,
  };
}

// The signal summary ------------------------------------------------------------------------------------------------

export type SummarySentence = { text: string; complaints: string[] };

export type SignalSummary = {
  author: "RECORDS" | "AI";
  complaints: number;
  sentences: SummarySentence[];
  records?: SummarySentence[];
  ai?: {
    status: string;
    reason?: string;
    message?: string;
    label?: string;
    model?: string;
    dropped?: Array<{ text: string; reason: string }>;
    trust?: TrustSummary | null;
  };
};

export type SignalInsight = { summary: SignalSummary; trend: TrendItem | null };

export const insightPath = (signalId: string) => `/api/v1/triage/signals/${encodeURIComponent(signalId)}/insight`;
export const summaryPath = (signalId: string) => `/api/v1/triage/signals/${encodeURIComponent(signalId)}/summary`;

const AI_REASONS: Record<string, string> = {
  PROVIDER_NOT_CONFIGURED: "No AI provider is set up yet, so the summary comes from the records.",
  NOT_RUN: "The signal has no complaints to summarize.",
  NOTHING_KEPT: "AI wrote nothing that passed the checks, so the summary comes from the records.",
  UNREADABLE: "AI's reply could not be read, so the summary comes from the records.",
};

/** Why the AI summary is not shown (AI off, over budget, no provider…), in plain words; null when it is shown. */
export function aiSummaryNote(summary: SignalSummary | null | undefined): string | null {
  if (!summary?.ai || summary.ai.status === "COMPLETED") return null;
  return (
    summary.ai.message ??
    AI_REASONS[summary.ai.reason ?? ""] ??
    AI_REASONS[summary.ai.status] ??
    "AI is not available right now, so the summary comes from the records."
  );
}

// One click to a case -----------------------------------------------------------------------------------------------

export const openCasePath = (signalId: string) => `/api/v1/triage/signals/${encodeURIComponent(signalId)}/open-case`;

/** The question the one-click case starts with: the signal's own default, else one from its product and problem. */
export function oneClickQuestion(
  defaultQuestion: string,
  signal: { problem_key?: string | null; product?: { name?: string | null } | null },
): string {
  const question = defaultQuestion.trim();
  if (question.length >= 10) return question;
  const problem =
    signal.problem_key && signal.problem_key !== "UNSPECIFIED"
      ? signal.problem_key.replace(/_/g, " ").toLowerCase()
      : "these complaints";
  const product = signal.product?.name ? ` on ${signal.product.name}` : "";
  return `What explains ${problem}${product}?`;
}

// The case AI run ---------------------------------------------------------------------------------------------------

export type RunStepStatus = "PENDING" | "DONE" | "FAILED" | "SKIPPED";
export type CaseAiRunStep = {
  step: string;
  label: string;
  status: RunStepStatus;
  author?: "AI" | "RULES";
  notice?: string | null;
  reason_code?: string | null;
  error?: string;
  seconds?: number;
  // The automatic trust check saved with the step's AI result (trust.ts); null when the step saved no AI result.
  trust?: TrustSummary | null;
};
export type CaseAiRun = {
  id: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "PARTIAL" | "FAILED";
  trigger: "AUTO" | "MANUAL";
  as_of: string | null;
  requested_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  steps: CaseAiRunStep[];
};

export const runPath = (caseId: string) => `/api/v1/investigations/${encodeURIComponent(caseId)}/ai-run`;

export const isRunning = (run: CaseAiRun | null | undefined) => run?.status === "QUEUED" || run?.status === "RUNNING";

export function runProgress(run: CaseAiRun | null | undefined): { done: number; total: number } {
  // A step this edition does not run (SKIPPED) is not counted.
  const steps = (run?.steps ?? []).filter((step) => step.status !== "SKIPPED");
  return { done: steps.filter((step) => step.status === "DONE").length, total: steps.length || 6 };
}

/** The run's trust checks: how many AI results were checked, and how many were blocked or limited. */
export function runTrust(run: CaseAiRun | null | undefined): { checked: number; blocked: number; limited: number } {
  const trusts = (run?.steps ?? []).map((step) => step.trust).filter((trust): trust is TrustSummary => Boolean(trust));
  return {
    checked: trusts.length,
    blocked: trusts.filter((trust) => trust.status === "BLOCKED").length,
    limited: trusts.filter((trust) => trust.status === "PASS_WITH_LIMITATIONS").length,
  };
}

/** Who wrote the run's results: AI for every step, the rules for every step (AI off or unavailable), or both. */
export function runAuthor(run: CaseAiRun | null | undefined): "AI" | "RULES" | "MIXED" | null {
  const authors = new Set((run?.steps ?? []).filter((step) => step.status === "DONE").map((step) => step.author));
  if (!authors.size) return null;
  if (authors.size > 1) return "MIXED";
  return authors.has("AI") ? "AI" : "RULES";
}

export function runHeadline(run: CaseAiRun | null | undefined): { title: string; detail: string; tone: Tone } {
  if (!run)
    return {
      title: "The AI analysis has not run yet",
      detail: "It runs by itself the first time the case opens, for someone allowed to run AI.",
      tone: "neutral",
    };
  const { done, total } = runProgress(run);
  if (isRunning(run))
    return {
      title: `Analysing the case… ${done} of ${total} steps done`,
      detail: "Evidence, competing explanations, challenges, unknowns, failure chains and the investigation brief.",
      tone: "neutral",
    };
  const author = runAuthor(run);
  const by =
    author === "AI"
      ? "Written by AI from the case's evidence, every statement cited."
      : author === "RULES"
        ? "Assembled by the rules from the case's records (AI is off or unavailable)."
        : "Part by AI, part by the rules where AI was unavailable.";
  const trust = runTrust(run);
  const plural = (count: number) => (count === 1 ? "" : "s");
  if (run.status === "COMPLETED" && trust.blocked)
    return {
      title: `AI analysis ready: ${trust.blocked} result${plural(trust.blocked)} blocked by the trust check`,
      detail: `${by} Open the blocked step's trust check and review it against the records before relying on it.`,
      tone: "warning",
    };
  if (run.status === "COMPLETED")
    return {
      title: "AI analysis ready: judge each explanation below",
      detail: trust.checked
        ? `${by} ${trust.checked} result${plural(trust.checked)} checked automatically for sources, wording and provenance.`
        : by,
      tone: "good",
    };
  if (run.status === "PARTIAL")
    return { title: `AI analysis stopped after ${done} of ${total} steps`, detail: run.error ?? by, tone: "warning" };
  return {
    title: "The AI analysis could not run",
    detail: run.error ?? "Start it again, or work the case without it.",
    tone: "critical",
  };
}
