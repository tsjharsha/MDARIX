import type { FactNeed } from "./sections/ReportingFacts";
// Pure rules for the per-market seriousness and causation assessment (Complaints › Reportability): what the screen
// reads (/api/v1/complaints/{id}/market-assessments, backend/app/reportability/assessment_router.py), what a draft and
// a signature send, and when they may be sent. The server decides the suggestion and refuses what it must; these
// checks only say early what it would refuse. A person answers and signs; MDARIX never answers and never submits.
import type { Tone } from "../admin/console/dashboardModel";
import type { RulesUsed } from "./ruleRegister";
import { collapsed } from "./complaintReview";
import { marketLabel, questionNumber } from "../../app/labels";

export const ASSESSMENT_LIMITS = { reasonMin: 10, rationaleMax: 2000, referenceMax: 120 };

export type Market = "US" | "EU_NI" | "GB" | "IN" | "CA";
export type Answer = "YES" | "NO" | "UNKNOWN" | "NOT_APPLICABLE";
export const ANSWERS: readonly Answer[] = ["YES", "NO", "UNKNOWN", "NOT_APPLICABLE"];
export const ANSWER_LABELS: Record<Answer, string> = {
  YES: "Yes",
  NO: "No",
  UNKNOWN: "Unknown",
  NOT_APPLICABLE: "Not applicable",
};
export type Suggestion = "REPORTABLE" | "PENDING_INFORMATION" | "NOT_REPORTABLE";
export type Conclusion = "REPORTABLE" | "NOT_REPORTABLE";
export type MarketState = "NOT_STARTED" | "DRAFT" | Conclusion;

export const CONCLUSION_LABELS: Record<Suggestion, string> = {
  REPORTABLE: "Reportable",
  PENDING_INFORMATION: "Pending information",
  NOT_REPORTABLE: "Not reportable",
};
// The tab and chip names: the label map's words where the code would read as a code ("EU/NI", 0.10.72).
export const MARKET_SHORT: Record<Market, string> = {
  US: "US",
  EU_NI: marketLabel("EU_NI"),
  GB: "GB",
  IN: "India",
  CA: "Canada",
};

export type Question = {
  id: string;
  text: string;
  definition: string;
  clause: string;
  basis: string[];
  serious: boolean;
  note: string | null;
  starter: boolean;
  /** The organization's own extra question (T-G15): recorded and printed, never required, never in the conclusion. */
  extra?: boolean;
  /** The organization's explanation and examples beside the locked wording (0.10.64). */
  explanation?: string | null;
  examples?: string | null;
};

export type QuestionSet = {
  market: Market;
  market_label: string;
  version: string;
  title: string;
  note: string | null;
  starter_mark: string;
  questions: Question[];
};

/** origin (0.10.72, B1): a suggestion from the complaint's record the person confirmed or corrected, or entered. */
export type AnswerOrigin = "CONFIRMED" | "CORRECTED" | "ENTERED";
export type AnswerEntry = {
  answer: Answer | null;
  rationale: string;
  evidence: string[];
  origin?: AnswerOrigin;
  suggested?: Answer;
  source?: string;
  /** Sent when the person pressed Confirm on the record's suggestion. */
  confirmed?: boolean;
};
/** A factual answer the complaint's record states, with its source ("From the complaint record: …"). */
export type Suggestion_ = { answer: Answer; source: string; evidence: string };

export type Version = {
  id: string;
  market: Market;
  version: number;
  question_set: string;
  question_set_current: boolean;
  answers: Record<string, AnswerEntry>;
  harm_level: string | null;
  harm_code: string | null;
  harm_level_reason: string | null;
  scale_version: string;
  scale_disagreement_reason: string | null;
  suggested_conclusion: Suggestion;
  conclusion: Conclusion | null;
  override_reason: string | null;
  /** Why a re-signed conclusion changed (OD-4, 0.10.88); null on a first signature. */
  change_reason?: string | null;
  report_type: string | null;
  report_type_label: string | null;
  window_name: string | null;
  due_on: string | null;
  filing_reference: string | null;
  filed_on: string | null;
  signed_record_id: string | null;
  content_fingerprint: string | null;
  signed_by: string | null;
  signed_at: string | null;
  superseded: boolean;
  /** B4/B9: the rules (floor) the version was decided under; null before the rule register. */
  floor_code?: string | null;
  /** B9: the organization's role the signed conclusion was decided in (MANUFACTURER, IMPORTER, USER_FACILITY). */
  role?: string;
  /** B9 step 20: a signed Canada foreign report's latest corrective-action decision day (its own audited entry). */
  decision_day?: { day: string; by: string; at: string; reason: string | null } | null;
  /** B9 step 20: the due date counted from awareness until that day is entered (provisional), then from that day. */
  due_provisional?: boolean;
  due_now?: string | null;
  sample: boolean;
  created_by: string;
  saved_at: string | null;
};

export type TrainingDocument = {
  code: string;
  title: string;
  version: string;
  statement: string;
  state: "CURRENT" | "OUT_OF_DATE" | "MISSING";
  held_version: string | null;
  trained_at: string | null;
  method: string | null;
};

export type MarketClock = {
  window: string;
  due_date: string;
  due_at?: string;
  due_zone?: string;
  due_label?: string;
  days_left: number;
  state: "OVERDUE" | "DUE_SOON" | "RUNNING";
  source: "WINDOW" | "REGULATION";
};

export type MarketItem = {
  market: Market;
  label: string;
  enabled: boolean;
  preselected: boolean;
  required: boolean;
  question_set: QuestionSet;
  /** The factual answers the complaint's record states (never a judgement question), to confirm or correct. */
  suggestions?: Record<string, Suggestion_>;
  /** 0.10.83 (D2): beside a judgement question (serious injury), what the record says, never its answer. */
  record_notes?: Record<string, string>;
  /** False when a draft keeps a guide version older than the one in use now (T-G15). */
  question_set_current?: boolean;
  threshold: { level: string; label: string };
  current: Version | null;
  draft: Version | null;
  evaluation: {
    suggested: Suggestion;
    report_type: string | null;
    notes: string[];
    /** 0.10.83 (D2): the questions earlier answers make unnecessary, with why; not required to sign. */
    not_asked?: Record<string, string>;
  } | null;
  disagreement: string | null;
  history: Version[];
  clock: MarketClock | null;
  training: TrainingDocument[];
  trained_colleagues: string[];
  /** B4: the rules in force at the event, today's, and those decided; null while the rule register is off. */
  rules_used?: RulesUsed | null;
};

export type ScaleLevel = {
  code: string;
  label: string;
  terms: Array<{ code: string; label: string }>;
  thresholds: Array<{ market: Market; label: string }>;
};

export type Scale = {
  version: string;
  starter_mark: string;
  protected_note: string;
  levels: ScaleLevel[];
  terms: Array<{ code: string; label: string; level: string; protected: boolean }>;
};

export type LegacyDecision = {
  decision: "REPORTED" | "NOT_REPORTABLE";
  rationale: string;
  report_reference: string | null;
  reported_on: string | null;
  decided_by: string;
  decided_at: string | null;
  note: string;
};

export type AssessmentDetail = {
  complaint: {
    id: string;
    business_id: string | null;
    complaint_identifier: string | null;
    product_name: string | null;
    version: string | null;
    country: string | null;
    description: string | null;
    severity: string | null;
    aware_date: string | null;
    /** 0.10.81: the facts a reporting step needs and the record does not give; no conclusion is signed without them. */
    needs?: FactNeed[];
  };
  on_watch: boolean;
  enabled_markets: Market[];
  preselected: Market | null;
  markets: MarketItem[];
  scale: Scale;
  severity: string | null;
  severity_level: string | null;
  /** Where the starting harm level came from: "Your QMS severity" or "The triage record" (stage 8). */
  severity_source?: string | null;
  starter_mark: string;
  practice_label: string | null;
  /** The practice-training rule binds free-trial organizations only (owner decision 6, 31 Oct 2026). */
  training_required: boolean;
  legacy_decision: LegacyDecision | null;
  /** B9b: the countries outside the five markets assessed on this complaint (readable while the switch is off). */
  other_countries?: OtherCountryItem[];
  /** B9b: the "Other country" picker is offered (MDARIX_B9B_OTHER on). */
  other_countries_on?: boolean;
};

/** B9b: a country outside the five markets on the complaint (reportability/other_countries.py ``items``). */
export type OtherCountryItem = Pick<
  MarketItem,
  "question_set" | "suggestions" | "record_notes" | "current" | "draft" | "evaluation" | "history" | "clock"
> & {
  market: "OTHER";
  /** "OTHER-AU": the country's address in the assessment routes. */
  key: string;
  country: string;
  country_name: string;
  label: string;
  generic_note: string;
  floor: { code: string; title: string };
  /** The country's Other Regulatory Report, once a Reportable conclusion created it. */
  report?: { id: string; state_label: string } | null;
};

/** A country outside the five markets is addressed "OTHER-<ISO code>" (B9b). */
export const isOtherKey = (market: string) => market.startsWith("OTHER-");

/** A country as the tree screens read a market: no harm scale, no practice training, never the event's preselected
 * market; its key ("OTHER-AU") stands where a market code stands, so the same save and sign paths take it. */
export function otherAsMarket(item: OtherCountryItem): MarketItem {
  return {
    ...item,
    market: item.key as Market,
    enabled: true,
    preselected: false,
    required: false,
    threshold: { level: "", label: "" },
    disagreement: null,
    training: [],
    trained_colleagues: [],
    rules_used: null,
  };
}

/** Every market and country of an assessment, as the tree screens read them. */
export const allMarkets = (detail: AssessmentDetail): MarketItem[] => [
  ...detail.markets,
  ...(detail.other_countries ?? []).map(otherAsMarket),
];

/** One market or country ("OTHER-AU") of an assessment, after a save or a signature. */
export const marketIn = (detail: AssessmentDetail, market: string): MarketItem | undefined =>
  allMarkets(detail).find((entry) => entry.market === market);

/** A market as the watch lists it on a complaint. */
export type MarketSummary = {
  market: Market;
  label: string;
  preselected: boolean;
  state: MarketState;
  suggested: Suggestion | null;
  report_type_label: string | null;
  filed: boolean;
  clock: MarketClock | null;
};

export const assessmentPath = (complaintId: string, market?: Market, tail = "") =>
  `/api/v1/complaints/${encodeURIComponent(complaintId)}/market-assessments${market ? `/${market}${tail}` : ""}`;

/** "US: reportable · filed", "EU/NI: draft (pending information)", "US: not started", with its tone. */
export function marketChip(item: MarketSummary): { label: string; tone: Tone } {
  const name = MARKET_SHORT[item.market] ?? item.market;
  if (item.state === "REPORTABLE")
    return {
      label: `${name}: reportable${item.filed ? " · filed" : " · filing not recorded"}`,
      tone: item.filed ? "good" : "warning",
    };
  if (item.state === "NOT_REPORTABLE") return { label: `${name}: not reportable`, tone: "good" };
  if (item.state === "DRAFT")
    return {
      label: `${name}: draft${item.suggested ? ` (${CONCLUSION_LABELS[item.suggested].toLowerCase()})` : ""}`,
      tone: item.suggested === "PENDING_INFORMATION" ? "warning" : "neutral",
    };
  return { label: `${name}: not assessed`, tone: "serious" };
}

// The form -------------------------------------------------------------------------------------------------------

export type HarmForm = { level: string; term: string; reason: string };
export type AssessmentForm = {
  answers: Record<string, AnswerEntry>;
  harm: HarmForm;
  disagreementReason: string;
};

export function formOf(item: MarketItem, severityLevel: string | null): AssessmentForm {
  const from = item.draft ?? item.current;
  return {
    answers: Object.fromEntries(
      Object.entries(from?.answers ?? {}).map(([key, value]) => [key, { ...value, evidence: [...value.evidence] }]),
    ),
    harm: {
      level: from?.harm_level ?? severityLevel ?? "",
      term: from?.harm_code ?? "",
      reason: from?.harm_level_reason ?? "",
    },
    disagreementReason: from?.scale_disagreement_reason ?? "",
  };
}

export function draftBody(form: AssessmentForm) {
  return {
    answers: Object.fromEntries(
      Object.entries(form.answers).map(([key, entry]) => [
        key,
        { ...entry, confirmed: !!entry.confirmed || entry.origin === "CONFIRMED" },
      ]),
    ),
    harm_level: form.harm.level || null,
    harm_code: form.harm.term || null,
    harm_level_reason: collapsed(form.harm.reason),
    scale_disagreement_reason: collapsed(form.disagreementReason),
  };
}

/** The first question without an answer or without its rationale, for signing (the server's rule). */
export function answersProblem(questions: Question[], form: AssessmentForm): string | null {
  for (const question of questions) {
    if (question.extra) continue;
    const entry = form.answers[question.id];
    if (!entry?.answer) return `Answer or confirm question ${questionNumber(question.id)}`;
    if (collapsed(entry.rationale).length < ASSESSMENT_LIMITS.reasonMin)
      return question.id === "US5" && entry.answer === "NO"
        ? "Question 5 is No: say why a recurrence would not be likely to cause harm"
        : `Question ${questionNumber(question.id)}: give the rationale in at least ${ASSESSMENT_LIMITS.reasonMin} characters`;
  }
  return null;
}

export type SignForm = {
  conclusion: Conclusion | "";
  overrideReason: string;
  password: string;
  code: string;
  /** Why a signed conclusion changes (OD-4, 0.10.88): asked when the market is signed already. */
  changeReason?: string;
};
export const EMPTY_SIGN: SignForm = { conclusion: "", overrideReason: "", password: "", code: "", changeReason: "" };

export function signProblem(
  questions: Question[],
  form: AssessmentForm,
  sign: SignForm,
  suggested: Suggestion | null,
  disagreement: string | null,
  trained: boolean,
  resigning = false,
): string | null {
  const answers = answersProblem(questions, form);
  if (answers) return answers;
  if (!form.harm.level) return "Choose the harm level on the scale";
  if (disagreement && collapsed(form.disagreementReason).length < ASSESSMENT_LIMITS.reasonMin)
    return "An answer disagrees with the scale: give the written reason";
  if (!sign.conclusion) return "Choose the conclusion";
  if (sign.conclusion === "NOT_REPORTABLE" && suggested === "PENDING_INFORMATION")
    return "An Unknown answer could make the event reportable: not reportable cannot be concluded (Unknown is never No)";
  if (sign.conclusion !== suggested && collapsed(sign.overrideReason).length < ASSESSMENT_LIMITS.reasonMin)
    return "You override the suggestion: say why";
  if (resigning && collapsed(sign.changeReason ?? "").length < ASSESSMENT_LIMITS.reasonMin)
    return "This market is signed already: say why the signed conclusion changes";
  if (!trained) return "Record your practice training on the documents above first";
  if (!sign.password) return "Enter your password to sign";
  return null;
}

export const trainingMissing = (item: MarketItem) => item.training.filter((document) => document.state !== "CURRENT");

/** The level a protected term may not go below, and whether the chosen level is below it. */
export function lowered(scale: Scale, harm: HarmForm): boolean {
  const term = scale.terms.find((entry) => entry.code === harm.term);
  if (!term?.protected || !harm.level) return false;
  const rank = (code: string) => scale.levels.findIndex((level) => level.code === code);
  return rank(harm.level) < rank(term.level);
}
