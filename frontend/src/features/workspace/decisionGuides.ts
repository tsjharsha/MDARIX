// Pure rules for Complaints › Decision guides (T-G15): the organization's own versions of each market's guide on
// MDARIX's starter engine. The server (/api/v1/decision-guides, backend/app/decision_guides) checks every edit, runs
// the test cases and decides whether a version can be published; these only shape what the person sees and sends.
import type { Tone } from "../admin/console/dashboardModel";
import { questionNumber } from "../../app/labels";
import type { Market, Question, QuestionSet } from "./marketAssessment";
import type { ApprovalStanding } from "./authorityReports";

export const GUIDES = "/api/v1/decision-guides";
export const GUIDES_TAB = "Decision guides";
export const REASON_MIN = 10;
export const TEXT_MIN = 5;

export type GuideState = "DRAFT" | "AWAITING_APPROVAL" | "PUBLISHED" | "SUPERSEDED" | "DISCARDED";
export type Expected = "REPORTABLE" | "NOT_REPORTABLE" | "PENDING_INFORMATION";

export type VersionSummary = {
  version: number;
  code: string;
  state: GuideState;
  state_label: string;
  starter: boolean;
  approved_by: string | null;
  published_at: string | null;
  sample: boolean;
};

export type GuideMarket = {
  market: Market;
  label: string;
  enabled: boolean;
  current: VersionSummary & { title: string; questions: number; extra_questions: number; tests: number };
  open: (VersionSummary & { problems: string[]; editors: string[] }) | null;
  history: VersionSummary[];
};

export type GuideList = {
  markets: GuideMarket[];
  core_rule: string;
  never_decides: string;
  scale_note: string;
  starter_mark: string;
  practice_label: string | null;
};

/** A worked complaint of the test matrix. */
export type TestCase = {
  id: string;
  name: string;
  answers: Record<string, string>;
  expected: Expected;
  expected_report_type: string | null;
  /** MDARIX's starter row: in every version's matrix, never removed. */
  starter?: boolean;
};

export type TestResult = {
  id: string;
  name: string;
  expected: Expected;
  expected_report_type: string | null;
  actual: Expected;
  actual_report_type: string | null;
  passed: boolean;
};

export type Signature = {
  signer_name: string;
  signer_role: string;
  signed_at: string | null;
  meaning: string;
  record_business_id: string | null;
  record_id: string;
  content_fingerprint: string;
};

export type GuideVersion = VersionSummary & {
  id?: string;
  market: Market;
  market_label: string;
  title: string;
  based_on: string | null;
  question_set: QuestionSet;
  test_cases: TestCase[];
  test_results: {
    results: TestResult[];
    passed: number;
    failed: number;
    current: boolean;
    run_at: string | null;
    run_by: string;
  } | null;
  problems: string[];
  /** The matrix run again for the approver: the worked complaints whose answer changed. Any blocks the approval. */
  matrix_changed?: string[];
  change_reason: string | null;
  editors: string[];
  you_edited?: boolean;
  /** This person sent it for approval: they may withdraw it (J13). */
  you_asked?: boolean;
  /** Who approves it, while it waits (J13); the form is shown only when ``may_approve``. */
  approval?: ApprovalStanding | null;
  requested_by: string | null;
  requested_at: string | null;
  approved_at: string | null;
  signature: Signature | null;
  editable: boolean;
  catalog: Array<{ id: string; short: string; title: string }>;
  answer_labels: Record<string, string>;
  expected_labels: Record<Expected, string>;
  report_types: Array<{ code: string; label: string }>;
  core_rule: string;
  matrix_rule?: string;
  never_decides: string;
  scale_note: string;
  starter_mark: string;
  practice_label: string | null;
};

/** A question as the editor holds it (the server's QuestionIn). */
export type QuestionForm = {
  id: string;
  text: string;
  definition: string;
  note: string;
  clause: string;
  basis: string[];
  extra: boolean;
  /** The organization's own text beside a core question's locked wording. */
  explanation: string;
  examples: string;
};

export const questionForm = (question: Question): QuestionForm => ({
  id: question.id,
  text: question.text,
  definition: question.definition ?? "",
  note: question.note ?? "",
  clause: question.clause ?? "",
  basis: [...(question.basis ?? [])],
  extra: !!question.extra,
  explanation: question.explanation ?? "",
  examples: question.examples ?? "",
});

export const NEW_EXTRA: QuestionForm = {
  id: "",
  text: "",
  definition: "",
  note: "",
  clause: "",
  basis: [],
  extra: true,
  explanation: "",
  examples: "",
};

export function stateTone(state: GuideState): Tone {
  if (state === "PUBLISHED") return "good";
  if (state === "AWAITING_APPROVAL") return "warning";
  if (state === "DRAFT") return "neutral";
  return "neutral";
}

/** The mark beside a question: the organization's wording or its extra question; starter text gets none (the page's
 * footnote says it once, G-17). */
export function questionMark(question: Pick<Question, "starter" | "extra">): string | null {
  if (question.extra) return "Your extra question: does not change the conclusion";
  return question.starter ? null : "Your wording";
}

/** Move an extra question up or down among the extra questions (the core questions keep their order). */
export function moveExtra(questions: QuestionForm[], index: number, by: -1 | 1): QuestionForm[] {
  const target = index + by;
  if (!questions[index]?.extra || !questions[target]?.extra) return questions;
  const next = [...questions];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

/** What still blocks saving the draft in the browser (the server checks everything again). */
export function editProblem(questions: QuestionForm[]): string | null {
  for (const question of questions) {
    if (question.text.trim().length < TEXT_MIN)
      return `Question ${question.id || "new"}: write the question in at least ${TEXT_MIN} characters`;
  }
  return null;
}

/** "US1 Yes, US3 Yes" for a test's answers; a missing answer is Unknown, never No. */
export function answersText(
  test: Pick<TestCase, "answers">,
  labels: Record<string, string>,
  order: string[] = [],
): string {
  // In the guide's question order (the stored answers come back in no particular order).
  const rank = (id: string) => (order.includes(id) ? order.indexOf(id) : order.length);
  const given = Object.entries(test.answers).sort(([a], [b]) => rank(a) - rank(b));
  return given.length
    ? given.map(([id, answer]) => `${questionNumber(id)} ${labels[answer] ?? answer}`).join(", ")
    : "none (all Unknown)";
}

export function outcomeText(
  expected: string,
  reportType: string | null | undefined,
  labels: Record<string, string>,
  types: Array<{ code: string; label: string }>,
): string {
  const type = reportType ? types.find((item) => item.code === reportType)?.label : null;
  return `${labels[expected] ?? expected}${type ? ` (${type})` : ""}`;
}

/** The body of PUT /api/v1/decision-guides/{market}/versions/{n}. A core question sends only the organization's own
 * text: its wording is locked, and the server refuses a change to it. */
export function saveBody(questions: QuestionForm[], tests: TestCase[]) {
  return {
    questions: questions.map(({ id, text, definition, note, clause, basis, extra, explanation, examples }) =>
      extra ? { id, text, definition, note, clause, basis } : { id, explanation, examples },
    ),
    test_cases: tests.map(({ name, answers, expected, expected_report_type }) => ({
      name,
      answers,
      expected,
      expected_report_type,
    })),
  };
}
