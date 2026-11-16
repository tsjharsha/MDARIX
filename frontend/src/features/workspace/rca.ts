// RCA tools (backend/app/rca/): fishbone, 5 Whys, the Pareto of confirmed causes, the version at the event date and
// the investigation overview. No AI anywhere: MDARIX structures the investigation; a person finds and signs the cause.
import { safeText } from "../../app/displayId";
import type { Tone } from "../admin/console/dashboardModel";
import { contradictionView, type IntelligenceView } from "./intelligence";

export const rcaPath = (investigationId: string, part: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/rca/${part}`;

export const PARETO_GROUPS = [
  { code: "category", label: "Cause category" },
  { code: "attribution", label: "Attribution" },
  { code: "product", label: "Product" },
  { code: "version", label: "Version" },
  { code: "problem_code", label: "Problem code" },
] as const;

export function paretoPath(group: string, filters: { productId?: string; from?: string; to?: string } = {}): string {
  const query = new URLSearchParams({ group_by: group });
  if (filters.productId) query.set("product_id", filters.productId);
  if (filters.from) query.set("date_from", filters.from);
  if (filters.to) query.set("date_to", filters.to);
  return `/api/v1/rca/pareto?${query.toString()}`;
}

/** The seven fishbone categories (RCA-D3); Software shows only for software products. */
export const CAUSE_CATEGORIES = [
  { code: "PEOPLE", label: "People" },
  { code: "PROCESS", label: "Process" },
  { code: "METHOD", label: "Method" },
  { code: "MATERIAL", label: "Material" },
  { code: "MACHINE", label: "Machine" },
  { code: "ENVIRONMENT", label: "Environment" },
  { code: "SOFTWARE", label: "Software" },
] as const;
export const NOT_DETERMINED = "NOT_DETERMINED";
export const ACCEPTING_OUTCOMES = ["ACCEPT_CONCLUSION", "ACCEPT_WITH_CONDITIONS"];

export const categoryLabel = (code: unknown): string =>
  code === NOT_DETERMINED
    ? "Not determined"
    : (CAUSE_CATEGORIES.find((item) => item.code === code)?.label ?? "Not categorised");

export type RiskRef = { id: string; identifier?: string | null; description?: string | null };
export type FishboneCause = {
  id: string;
  business_id?: string | null;
  statement: string;
  origin?: string | null;
  cause_category?: string | null;
  human_status?: string | null;
  human_status_label?: string | null;
  ruled_out: boolean;
  ruled_out_reason?: string | null;
  evidence_for: number;
  evidence_against: number;
  failure_mode?: { id: string; identifier?: string | null; name?: string | null; risks: RiskRef[] } | null;
  confirmed_in?: {
    id: string;
    business_id?: string | null;
    decision_identifier?: string | null;
    signed_by_name?: string | null;
    signed_at?: string | null;
  } | null;
  fmea_prompt?: string | null;
  can_change?: boolean;
};
export type Fishbone = {
  categories: { code: string; label: string; causes: FishboneCause[] }[];
  all_categories?: { code: string; label: string }[];
  uncategorised: FishboneCause[];
  failure_modes: { id: string; identifier?: string | null; name?: string | null }[];
  actions?: { can_add?: boolean };
  note?: string;
};

/** How a cause reads on its card: its judgement, ruled out or named in a signed decision. */
export function causeState(cause: FishboneCause): { label: string; tone: Tone } {
  if (cause.confirmed_in) {
    const decision = safeText(cause.confirmed_in.decision_identifier) ?? safeText(cause.confirmed_in.business_id);
    return { label: `Named as root cause in decision ${decision ?? ""}`.trim(), tone: "good" };
  }
  if (cause.ruled_out)
    return { label: `Ruled out: ${safeText(cause.human_status_label) ?? "contradicted"}`, tone: "neutral" };
  return { label: safeText(cause.human_status_label) ?? "Proposed", tone: "warning" };
}

export const QUICK_ADD_MIN = 10;
// The validator's own phrases (hypothesis_engine/validator.py): a possible cause is never written as a finding.
const CLAIMS = ["is the root cause", "proven root cause", "established cause", "caused all", "% probability"];

export function quickAddProblem(statement: string, category: string): string | null {
  const text = statement.replace(/\s+/g, " ").trim();
  if (text.length < QUICK_ADD_MIN) return `Describe the possible cause in at least ${QUICK_ADD_MIN} characters.`;
  const claim = CLAIMS.find((phrase) => text.toLowerCase().includes(phrase));
  if (claim) return `A possible cause is not yet a finding: remove “${claim}”.`;
  if (!CAUSE_CATEGORIES.some((item) => item.code === category)) return "Choose a category.";
  return null;
}

// ------------------------------------------------------------------------------------------------------ 5 Whys

export const WHYS_MIN = 2;
export const WHYS_MAX = 7;

export function whysProblem(problem: string, whys: readonly string[]): string | null {
  if (problem.trim().length < 3) return "Describe the problem (the first step).";
  const filled = whys.map((why) => why.trim()).filter(Boolean);
  if (filled.length < WHYS_MIN) return `Answer at least ${WHYS_MIN} whys.`;
  if (filled.length > WHYS_MAX) return `A 5 Whys has at most ${WHYS_MAX} whys.`;
  if (filled.some((why) => why.length < 3)) return "Write each why in at least 3 characters.";
  return null;
}

export const whysBody = (problem: string, whys: readonly string[]) => ({
  problem: problem.trim(),
  whys: whys
    .map((why) => why.trim())
    .filter(Boolean)
    .map((text) => ({ text, state: "UNKNOWN" })),
});

// ------------------------------------------------------------------------------------------------------ Pareto

export type ParetoBar = {
  label: string;
  count: number;
  share: number;
  cumulative_share: number;
  confirmed: boolean;
  complaints: { id: string; business_id?: string | null }[];
  decisions: { id: string; business_id?: string | null }[];
  investigations?: number;
};
export type Pareto = {
  group_by: string;
  total: number;
  bars: ParetoBar[];
  mark: number;
  note?: string;
  products?: { id: string; name: string }[];
};

/** The bars with their width against the largest, and the one where the cumulative share first reaches the mark. */
export function paretoRows(data: Pareto | null | undefined) {
  const bars = data?.bars ?? [];
  const largest = Math.max(1, ...bars.map((bar) => bar.count));
  const mark = data?.mark ?? 80;
  const markIndex = bars.findIndex((bar) => bar.confirmed && bar.cumulative_share >= mark);
  return bars.map((bar, index) => ({
    ...bar,
    width: Math.round((100 * bar.count) / largest),
    reachesMark: index === markIndex,
  }));
}

// ------------------------------------------------------------------------------------------------ the overview

export type OverviewLine = {
  key: string;
  tag: string;
  tone: Tone;
  text: string;
  detail?: string | null;
  /** The record the line comes from, and the view that opens it. */
  record: string;
  view: IntelligenceView;
};

const FACT_KINDS: Record<string, string> = { FACT: "Verified fact", SOURCE_ASSERTION: "Source assertion" };

/** One read-only list of the case's intelligence (spec Part C 2): facts with their source, hypotheses with evidence for
 * and against and their category, open contradictions, open unknowns and the 5 Whys, each with the record it is. */
export function overviewLines(input: {
  hypotheses?: unknown[];
  contradictions?: unknown[];
  unknowns?: unknown[];
  observations?: unknown[];
  whys?: unknown[];
}): OverviewLine[] {
  const lines: OverviewLine[] = [];
  for (const raw of input.observations ?? []) {
    const row = (raw ?? {}) as Record<string, any>;
    const tag = FACT_KINDS[String(row.epistemic_type ?? "")];
    if (!tag) continue;
    const evidence = row.evidence ?? {};
    lines.push({
      key: `obs-${row.id}`,
      tag,
      tone: "good",
      text: String(row.statement ?? ""),
      detail: safeText(evidence.title) ? `Source: ${evidence.title}` : null,
      record: safeText(evidence.business_id) ?? "Observation",
      view: "Observations",
    });
  }
  for (const raw of input.hypotheses ?? []) {
    const row = (raw ?? {}) as Record<string, any>;
    const supporting = (row.evidence?.supporting ?? []).filter((item: any) => !item.retracted).length;
    const against = (row.evidence?.contradicting ?? []).filter((item: any) => !item.retracted).length;
    lines.push({
      key: `hyp-${row.id}`,
      tag: "Hypothesis",
      tone: "warning",
      text: String(row.statement ?? ""),
      detail: [
        row.cause_category ? categoryLabel(row.cause_category) : null,
        `${supporting} for · ${against} against`,
        safeText(row.human_status_label),
      ]
        .filter(Boolean)
        .join(" · "),
      record: safeText(row.business_id) ?? "Hypothesis",
      view: "Hypotheses",
    });
  }
  input.contradictions?.forEach((raw, index) => {
    const row = contradictionView(raw, index);
    lines.push({
      key: `con-${row.key}`,
      tag: "Contradiction",
      tone: "critical",
      text: `${row.evidence ?? "Evidence"} contradicts ${row.hypothesis ?? "a hypothesis"}`,
      detail: row.rationale,
      record: row.evidence ?? row.hypothesis ?? "Contradiction",
      view: "Contradictions",
    });
  });
  for (const raw of input.unknowns ?? []) {
    const row = (raw ?? {}) as Record<string, any>;
    if (!["open", "in_progress"].includes(String(row.status ?? "").toLowerCase())) continue;
    lines.push({
      key: `unk-${row.id}`,
      tag: "Unknown",
      tone: "serious",
      text: String(row.description ?? ""),
      detail: safeText(row.evidence_needed) ? `Would show it: ${row.evidence_needed}` : null,
      record: safeText(row.business_id) ?? "Unknown",
      view: "Unknowns",
    });
  }
  for (const raw of input.whys ?? []) {
    const row = (raw ?? {}) as Record<string, any>;
    const nodes = (row.nodes ?? []) as { label?: string }[];
    lines.push({
      key: `why-${row.id}`,
      tag: "5 Whys",
      tone: "neutral",
      text: nodes.map((node) => node.label).join(" → "),
      detail: `${Math.max(0, nodes.length - 1)} whys · the last why is not a root cause`,
      record: safeText(row.business_id) ?? "5 Whys",
      view: "5 Whys",
    });
  }
  return lines.filter((line) => line.text.trim());
}

// --------------------------------------------------------------------------------------- the cause at signing

export type CauseForm = { rootCauseCategory: string; rootCauseReason: string; rootCauseHypotheses: string[] };

export function causeProblem(form: CauseForm, outcome: string, on: boolean): string | null {
  if (!on) return null;
  if (form.rootCauseHypotheses.length && !form.rootCauseCategory)
    return "Choose the category of the causes you ticked.";
  if (!form.rootCauseCategory && ACCEPTING_OUTCOMES.includes(outcome))
    return "Accepting the conclusion: choose the cause category, or Not determined with a reason.";
  if (form.rootCauseCategory === NOT_DETERMINED) {
    if (form.rootCauseHypotheses.length) return "Not determined: untick the hypotheses, or choose their category.";
    if (form.rootCauseReason.trim().length < 10)
      return "Not determined: say in at least 10 characters why the cause cannot be determined.";
  }
  return null;
}

/** The cause fields of the signing request; nothing when none was chosen (nothing is pre-ticked). */
export function causeBody(form: CauseForm) {
  if (!form.rootCauseCategory && !form.rootCauseHypotheses.length) return {};
  return {
    root_cause_category: form.rootCauseCategory || null,
    root_cause_hypothesis_ids: form.rootCauseHypotheses,
    ...(form.rootCauseCategory === NOT_DETERMINED ? { root_cause_reason: form.rootCauseReason.trim() } : {}),
  };
}

// ------------------------------------------------------------------------------------ the version at the event

export type EventVersion = {
  complaint: { id: string; business_id?: string | null; identifier?: string | null };
  anchor_date?: string | null;
  anchor_label: string;
  lot?: { identifier?: string | null } | null;
  version?: { version_identifier: string; released_at?: string | null } | null;
  version_label: string;
  candidate_versions: { version_identifier: string }[];
  components: { identifier: string; name: string; revision?: string | null }[];
  flags: { code: string; label: string }[];
};
