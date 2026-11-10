// B5a: the investigation challenge (backend/app/case_challenge/router.py) and the brief's Challenge and Sources
// sections (case_challenge/brief.py). Drafts are explanations drafted by rule from the case's records, to test, never
// findings: a person adopts (ticking the facts that become record summaries) or dismisses each with a reason. Material
// questions block "Submit for review" until answered or marked not applicable. The server owns every rule.
import type { Tone } from "../admin/console/dashboardModel";
import type { Source } from "./documents";

export type ChallengeRecord = { type: string; id: string; ref: string };
export type ChallengeFact = { text: string; records: ChallengeRecord[] };
export type DraftAction = { state?: string; reason?: string | null; hypothesis?: string | null };
export type ChallengeDraft = {
  rule: string;
  rule_version: number;
  key: string;
  title: string;
  statement: string;
  duplicate_of?: string | null;
  for: ChallengeFact[];
  against: ChallengeFact[];
  missing: ChallengeFact[];
  action?: DraftAction | null;
};
export type ChallengeAnswer = { text: string; not_applicable?: boolean; answered_by?: string; answered_at?: string };
export type ChallengeQuestion = {
  rule: string;
  rule_version: number;
  key: string;
  text: string;
  material: boolean;
  records?: ChallengeRecord[];
  answer?: ChallengeAnswer | null;
};
export type ChallengeView = {
  notice?: string;
  summary?: { complaints: number; no_version: number; no_lot: number; outside: number; changes: number };
  drafts: ChallengeDraft[];
  questions: ChallengeQuestion[];
  blocking: string[];
  answers_editable?: boolean;
};
export type SourceGroup = { count: number; items: Array<{ id: string; ref: string; origin?: string | null }> };
export type BriefSources = {
  as_of?: string;
  count: number;
  summary: string;
  groups: Record<string, SourceGroup>;
  rules: Array<{ rule: string; version: number; name: string }>;
};

export const REASON_MIN = 10;
export const ANSWER_MIN = 10;
export const ANSWER_MAX = 4000;
export const SIDES = ["for", "against"] as const;
export type Side = (typeof SIDES)[number];

export const challengePath = (investigationId: string, path = "") =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/challenge${path ? `/${path}` : ""}`;

/** "Drafted by rule H-2 (version 1)": every draft says where it came from. */
export const draftHeading = (draft: Pick<ChallengeDraft, "rule" | "rule_version">) =>
  `Drafted by rule ${draft.rule} (version ${draft.rule_version})`;

export const questionHeading = (item: Pick<ChallengeQuestion, "rule" | "rule_version">) =>
  `Question from rule ${item.rule} (version ${item.rule_version})`;

/** What a person did with a draft. */
export function draftState(action: DraftAction | null | undefined): { label: string; tone: Tone } {
  if (action?.state === "ADOPTED") return { label: `Adopted as ${action.hypothesis ?? "a hypothesis"}`, tone: "good" };
  if (action?.state === "DISMISSED") return { label: "Dismissed", tone: "neutral" };
  return { label: "Not acted on", tone: "warning" };
}

/** "H-0" lists what is missing; it is not an explanation, so it cannot be adopted or dismissed. */
export const actionable = (draft: ChallengeDraft) => draft.rule !== "H-0" && draft.action?.state !== "ADOPTED";

/** A cited record as a document source, so it opens where MDARIX shows it (documents.ts sourceTarget). */
export const recordSource = (record: ChallengeRecord, caseId: string): Source => ({
  type: record.type ? record.type[0].toUpperCase() + record.type.slice(1) : "Record",
  id: record.id,
  ref: record.ref,
  case: caseId,
});

/** The adopt request: the ticked facts are "for:0", "against:2"… */
export function adoptBody(key: string, ticked: Iterable<string>) {
  const facts = [...ticked].map((item) => {
    const [side, index] = item.split(":");
    return { side, index: Number(index) };
  });
  return { key, facts };
}

export const reasonProblem = (reason: string) =>
  reason.trim().length >= REASON_MIN ? null : `Give the reason in at least ${REASON_MIN} characters.`;

export const answerProblem = (text: string) =>
  text.trim().length >= ANSWER_MIN
    ? text.length > ANSWER_MAX
      ? `Keep the answer under ${ANSWER_MAX} characters.`
      : null
    : `Write at least ${ANSWER_MIN} characters.`;

/** The material questions still blocking "Submit for review", in the order the server lists them. */
export const blockingQuestions = (view: Pick<ChallengeView, "questions" | "blocking">) =>
  view.blocking.map((key) => view.questions.find((item) => item.key === key)).filter(Boolean) as ChallengeQuestion[];

/** "Answer: …", "Not applicable: …" or "Not answered". */
export function answerLine(answer: ChallengeAnswer | null | undefined): string {
  if (!answer?.text) return "Not answered";
  return `${answer.not_applicable ? "Not applicable" : "Answer"}: ${answer.text}`;
}

// Each Sources group: its heading and the record type it holds (case_challenge/brief.py GROUPS).
const GROUPS: Record<string, [string, string]> = {
  complaints: ["Complaints", "complaint"],
  lots: ["Lots", "lot"],
  versions: ["Versions", "version"],
  components: ["Components", "component"],
  suppliers: ["Suppliers", "supplier"],
  changes: ["Changes", "change"],
  evidence: ["Evidence", "evidence"],
  hypotheses: ["Hypotheses", "hypothesis"],
  open_questions: ["Open questions", "unknown"],
  signals: ["Signals", "signal"],
};

/** The brief's Challenge and Sources, or null for a brief composed before B5 (it keeps the content it was signed with). */
export function briefChallenge(content: Record<string, any>): {
  drafts: ChallengeDraft[];
  questions: ChallengeQuestion[];
  notice?: string;
  sources: BriefSources | null;
  groups: Array<{ name: string; label: string; kind: string; count: number; items: SourceGroup["items"] }>;
} | null {
  const challenge = content?.challenge;
  if (!challenge || typeof challenge !== "object") return null;
  const sources = (content.sources ?? null) as BriefSources | null;
  return {
    drafts: Array.isArray(challenge.drafts) ? challenge.drafts : [],
    questions: Array.isArray(challenge.questions) ? challenge.questions : [],
    notice: challenge.notice,
    sources,
    groups: Object.entries(sources?.groups ?? {}).map(([name, group]) => ({
      name,
      label: GROUPS[name]?.[0] ?? name,
      kind: GROUPS[name]?.[1] ?? name,
      count: group.count,
      items: group.items ?? [],
    })),
  };
}

const ORIGINS: Record<string, string> = {
  SAMPLE: "Sample",
  IMPORTED: "Your import",
  MDARIX: "Created in MDARIX",
  EXTERNAL: "From your system",
};

/** Where a cited record came from (product360/origin.py kinds). */
export const originLabel = (origin: string | null | undefined) => ORIGINS[origin ?? "MDARIX"] ?? String(origin);
