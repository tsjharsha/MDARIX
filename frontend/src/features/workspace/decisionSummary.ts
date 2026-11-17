/** E3 + W6: the decision record and the decision-and-impact summary of a signed investigation decision
 * (backend/app/human_decision/summary.py). Everything shown is what was recorded; a part with no record says
 * "Not recorded", and nothing says an action worked before a signed effectiveness check. */
import type { FollowUp } from "./afterDecision";

export type SummaryRef = { ref: string | null; title?: string | null };
export type SummaryHypothesis = {
  ref: string | null;
  statement: string | null;
  origin?: string | null;
  status_label?: string | null;
};
export type SummaryNext = {
  what: string;
  ref: string | null;
  kind: string | null;
  due: string | null;
  who: string | null;
};
export type SummaryCheck = {
  round: number;
  status: string;
  planned_on: string | null;
  signed_at: string | null;
  result_summary: string | null;
  /** What the check measures, as planned (W1c). */
  criteria?: string | null;
};
export type SummaryCapa = {
  id: string;
  ref: string;
  title: string;
  status: string | null;
  due_at: string | null;
  check: SummaryCheck | null;
};
export type Worked = {
  state: "EFFECTIVE" | "NOT_EFFECTIVE" | "TOO_EARLY" | "NOT_PLANNED";
  text: string;
  on: string | null;
};
export type DecisionSummary = {
  investigation: { id: string; ref: string | null; question: string | null };
  decision: {
    id: string;
    ref: string | null;
    status: string;
    status_label: string | null;
    superseded_by: { id: string; business_id: string | null } | null;
    outcome: string | null;
    outcome_label: string | null;
    conclusion: string | null;
    rationale: string | null;
    conditions: string | null;
    root_cause_category_label: string | null;
    root_cause_attribution_label: string | null;
    brief_ref: string | null;
    brief_version: number | null;
    effective_on: string | null;
    review_on: string | null;
  } | null;
  owner?: { name: string | null; role_label: string | null; authority_recorded: boolean };
  signature?: {
    ref: string | null;
    name: string | null;
    role_label: string | null;
    signed_at: string | null;
    meaning: string | null;
    mfa_verified: boolean | null;
    verification: string | null;
  } | null;
  evidence?: { supporting: SummaryRef[]; contradicting: SummaryRef[]; fingerprint: string | null };
  ai?: {
    statement: string | null;
    in_brief: string[];
    proposals: Array<{ ref: string | null; label: string | null; recorded: boolean; reviews: Record<string, number> }>;
    /** U7: the AI results as locked into the signed snapshot; null for a decision signed before it was kept. */
    locked?: LockedAi[] | null;
  };
  hypotheses?: {
    accepted: SummaryHypothesis[];
    leading: SummaryHypothesis | null;
    rejected: SummaryHypothesis[];
    alternatives: SummaryHypothesis[];
  };
  affects?: {
    product: { ref: string | null; name: string | null } | null;
    versions: Array<string | null>;
    lots: Array<string | null>;
    markets: string[];
    complaints: number | null;
    risks: Array<{ ref: string; description: string; status: string | null }>;
  };
  follow_ups?: FollowUp[];
  capas?: SummaryCapa[];
  next?: SummaryNext[];
  worked?: Worked;
  /** Before a decision is signed: the product's risk file (W1c; once signed it is in `affects.risks`). */
  risks?: Array<{ ref: string; description: string; status: string | null }>;
};

export const NOT_RECORDED = "Not recorded";

export type LockedAi = {
  ref: string | null;
  what: string | null;
  provider: string | null;
  model: string | null;
  model_version: string | null;
  prompt_version: string | null;
  at: string | null;
  sources: string[];
  recorded: boolean;
  in_signed_brief: boolean;
  verdicts: Array<{ about: string; state: string; reason: string | null; reviewer: string | null; at: string | null }>;
};

const VERDICT_WORDS: Record<string, string> = {
  ACCEPTED: "Accepted",
  EDITED: "Edited",
  REJECTED: "Rejected",
  NOT_REVIEWED: "Not reviewed",
};
export const NOT_LOCKED = "Not recorded at signing: this decision was signed before MDARIX kept the AI record with it.";

/** U7: each AI output as it stood when the decision was signed (model, prompt version, sources), then each reviewer
 * verdict with its reason. Pure; "Not recorded" wherever the record has nothing. */
export function lockedAiLines(locked: LockedAi[] | null | undefined): string[] {
  if (!locked) return [NOT_LOCKED];
  if (!locked.length) return ["No AI output on this investigation when the decision was signed."];
  return locked.flatMap((item) => [
    [
      `${item.ref ?? NOT_RECORDED}: ${item.what ?? "AI output"}`,
      `${item.provider ?? NOT_RECORDED} · ${item.model ?? NOT_RECORDED}${item.model_version ? ` (${item.model_version})` : ""}`,
      `prompt ${item.prompt_version ?? NOT_RECORDED}`,
      `sources: ${item.sources.length ? item.sources.join(", ") : NOT_RECORDED}`,
      ...(item.recorded ? ["recorded with the sample, no model was called"] : []),
      ...(item.in_signed_brief ? ["in the signed brief"] : []),
    ].join(" · "),
    ...item.verdicts.map(
      (verdict) =>
        `${VERDICT_WORDS[verdict.state] ?? verdict.state}${verdict.reviewer ? ` by ${verdict.reviewer}` : ""}${
          verdict.reason ? `: ${verdict.reason}` : ""
        } (${verdict.about})`,
    ),
  ]);
}

export const decisionSummaryPath = (investigationId: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/decision/summary`;
export const decisionSummaryByIdPath = (decisionId: string) =>
  `/api/v1/decisions/${encodeURIComponent(decisionId)}/summary`;

/** How the signature was given, from the signing's audit event; null when the event does not say. */
export const mfaText = (value: boolean | null | undefined) =>
  value === true ? "Password and authenticator code" : value === false ? "Password only" : NOT_RECORDED;

const REVIEW_WORDS: Array<[string, string]> = [
  ["ACCEPTED", "accepted"],
  ["EDITED", "edited"],
  ["REJECTED", "rejected"],
  ["NOT_REVIEWED", "not reviewed"],
];

/** "1 accepted, 1 not reviewed": a person's latest review of each AI output, in a fixed order. */
export const reviewText = (reviews: Record<string, number>) =>
  REVIEW_WORDS.filter(([key]) => reviews[key])
    .map(([key, word]) => `${reviews[key]} ${word}`)
    .join(", ") || "not reviewed";

/** The first sentence of the signed conclusion, for the headline (the full text is in the record). */
export function firstSentence(text: string | null | undefined): string | null {
  const value = (text ?? "").trim();
  if (!value) return null;
  const end = value.search(/[.:;](\s|$)/);
  return end > 0 ? value.slice(0, end) : value;
}

/** "Accepted the conclusion: the NovaSense pressure sensors … are the most likely cause". */
export function headline(decision: NonNullable<DecisionSummary["decision"]>): string {
  const lead = firstSentence(decision.conclusion);
  const outcome = decision.outcome_label ?? NOT_RECORDED;
  return lead ? `${outcome}: ${lead}` : outcome;
}

/** A list in words, or "Not recorded" when the record has none. */
export const listText = (items: Array<string | null | undefined> | undefined) => {
  const values = (items ?? []).filter((item): item is string => !!item);
  return values.length ? values.join(", ") : NOT_RECORDED;
};

export const workedTone = (state: Worked["state"] | undefined) =>
  state === "EFFECTIVE" ? "good" : state === "NOT_EFFECTIVE" ? "critical" : "neutral";
