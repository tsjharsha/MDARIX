// Pure rules for answering a market's tree on the Decision trees tab (0.10.83, D2): the questions in groups, which
// answers are facts from the record and which are the person's judgement, what still stands before Sign, and the "Why"
// chips of the outcome. The server (backend/app/reportability) evaluates the answers, folds the questions earlier
// answers make unnecessary and refuses what it must; these only shape the screen and the draft it sends.
import { collapsed } from "./complaintReview";
import {
  ANSWER_LABELS,
  ASSESSMENT_LIMITS,
  type Answer,
  type AnswerEntry,
  type MarketItem,
  type Question,
  type Suggestion,
} from "./marketAssessment";
import { questionNumber } from "../../app/labels";

/** Questions shown together: a definition's criteria ("Serious injury, part (a) … (c)") share one card and one reason. */
export type QuestionGroup = { key: string; title: string | null; questions: Question[] };

const CRITERION = /^(.*?),\s*(?:part|criterion)\s*\(([a-z])\):\s*(.*)$/i;

/** "Serious injury, part (a): is it life-threatening?" -> the group title and the row's own words. */
export function criterion(text: string): { group: string; letter: string; rest: string } | null {
  const found = CRITERION.exec(text);
  return found ? { group: found[1], letter: found[2].toLowerCase(), rest: found[3] } : null;
}

export function groupQuestions(questions: readonly Question[]): QuestionGroup[] {
  const groups: QuestionGroup[] = [];
  for (const question of questions) {
    const part = question.extra ? null : criterion(question.text);
    const last = groups[groups.length - 1];
    if (part && last?.title === part.group) last.questions.push(question);
    else groups.push({ key: question.id, title: part?.group ?? null, questions: [question] });
  }
  return groups;
}

/** What the person has given on the screen: each answer, and one reason per group. */
export type TreeForm = { answers: Record<string, Answer | null>; reasons: Record<string, string> };

/** The form as a saved draft (or the signed version) left it: answers, and each group's reason. */
export function treeFormOf(item: MarketItem, groups: QuestionGroup[]): TreeForm {
  const from = item.draft ?? item.current;
  const saved = from?.answers ?? {};
  const answers: Record<string, Answer | null> = {};
  const reasons: Record<string, string> = {};
  for (const group of groups) {
    for (const question of group.questions) {
      const entry = saved[question.id];
      if (entry?.answer) answers[question.id] = entry.answer;
      const offer = item.suggestions?.[question.id];
      // A confirmed fact's rationale is its source; the group's reason is the person's own.
      if (!reasons[group.key] && entry?.rationale && !(offer && entry.rationale === offer.source))
        reasons[group.key] = entry.rationale;
    }
  }
  return { answers, reasons };
}

/** A question's place on the screen, from the record's suggestion, the person's answer and the server's folding. */
export type QuestionState = {
  fact: { answer: Answer; source: string; evidence: string } | null;
  answer: Answer | null;
  /** A fact from the record still waiting for its one-click Confirm. */
  toConfirm: boolean;
  /** A fact the person changed from the record's answer: it needs a reason. */
  changed: boolean;
  /** A question earlier answers make unnecessary, with why (the server's ``not_asked``). */
  folded: string | null;
  needsReason: boolean;
};

export function questionState(
  question: Question,
  item: MarketItem,
  form: TreeForm,
  folded: Record<string, string>,
): QuestionState {
  const fact = item.suggestions?.[question.id] ?? null;
  const answer = form.answers[question.id] ?? null;
  const changed = !!fact && !!answer && answer !== fact.answer;
  const skip = folded[question.id] ?? null;
  return {
    fact,
    answer,
    toConfirm: !!fact && !answer && !skip,
    changed,
    folded: skip,
    needsReason: !question.extra && !skip && !!answer && (!fact || changed),
  };
}

/** The draft's answers as the server keeps them: a confirmed fact cites its source, the rest carry the group's reason. */
export function treeAnswers(
  groups: QuestionGroup[],
  item: MarketItem,
  form: TreeForm,
  folded: Record<string, string>,
): Record<string, AnswerEntry> {
  const out: Record<string, AnswerEntry> = {};
  for (const group of groups) {
    for (const question of group.questions) {
      const state = questionState(question, item, form, folded);
      if (!state.answer) continue;
      const confirmed = !!state.fact && !state.changed;
      out[question.id] = {
        answer: state.answer,
        rationale: confirmed ? state.fact!.source : collapsed(form.reasons[group.key] ?? ""),
        evidence: state.fact ? [state.fact.evidence] : [],
        confirmed,
      };
    }
  }
  return out;
}

export type CheckItem = { ok: boolean; text: string };

/** The short checklist before Sign: every question answered, the record's facts confirmed, a reason for each
 * judgement and each changed fact (named by question), and anything else the server would refuse. */
export function signChecklist(
  groups: QuestionGroup[],
  item: MarketItem,
  form: TreeForm,
  folded: Record<string, string>,
): CheckItem[] {
  let open = 0;
  let confirm = 0;
  const noReason: string[] = [];
  for (const group of groups) {
    let wants = false;
    for (const question of group.questions) {
      if (question.extra) continue;
      const state = questionState(question, item, form, folded);
      if (state.folded) continue;
      if (state.toConfirm) confirm += 1;
      else if (!state.answer) open += 1;
      if (state.needsReason) wants = true;
    }
    if (wants && collapsed(form.reasons[group.key] ?? "").length < ASSESSMENT_LIMITS.reasonMin)
      noReason.push(`Q${questionNumber(group.questions[0].id).replace(group.title ? /[a-z]$/ : /^$/, "")}`);
  }
  return [
    { ok: !open, text: open ? `${open} question${open === 1 ? "" : "s"} to answer` : "Every question answered" },
    {
      ok: !confirm,
      text: confirm
        ? `${confirm} fact${confirm === 1 ? "" : "s"} from the record to confirm`
        : "Facts from the record confirmed",
    },
    {
      ok: !noReason.length,
      text: noReason.length ? `A one-line reason for ${noReason.join(", ")}` : "A reason for each judgement",
    },
  ];
}

/** The answers that lead to the outcome, as "Why" chips: Yes and Unknown for reportable, No and Not applicable for
 * not reportable, Unknown for pending information. */
export function whyChips(
  questions: readonly Question[],
  form: TreeForm,
  folded: Record<string, string>,
  outcome: Suggestion | null,
): { id: string; label: string }[] {
  if (!outcome) return [];
  const wanted: Answer[] =
    outcome === "REPORTABLE"
      ? ["YES", "UNKNOWN"]
      : outcome === "NOT_REPORTABLE"
        ? ["NO", "NOT_APPLICABLE"]
        : ["UNKNOWN"];
  return questions
    .filter((question) => !question.extra && !folded[question.id])
    .filter((question) => wanted.includes(form.answers[question.id] as Answer))
    .map((question) => ({
      id: question.id,
      label: `Q${questionNumber(question.id)} ${ANSWER_LABELS[form.answers[question.id] as Answer]}`,
    }));
}

/** Folded questions next to each other with the same reason read as one grey line ("Q3 not asked: …"). */
export function foldedRuns(
  questions: readonly Question[],
  folded: Record<string, string>,
): { first: string; ids: string[]; why: string }[] {
  const runs: { first: string; ids: string[]; why: string }[] = [];
  for (const question of questions) {
    const why = folded[question.id];
    const last = runs[runs.length - 1];
    if (!why) continue;
    if (last && last.why === why && last.ids[last.ids.length - 1] === previousId(questions, question.id))
      last.ids.push(question.id);
    else runs.push({ first: question.id, ids: [question.id], why });
  }
  return runs;
}

const previousId = (questions: readonly Question[], id: string) =>
  questions[questions.findIndex((question) => question.id === id) - 1]?.id;

/** "Q3", "Q6–Q11": a run of questions by number. */
export const runLabel = (ids: string[]) =>
  ids.length === 1
    ? `Q${questionNumber(ids[0])}`
    : `Q${questionNumber(ids[0])}–Q${questionNumber(ids[ids.length - 1])}`;

/** The outcome the card shows: "pending information" only once every question is answered and an Unknown remains;
 * while questions are still open it is not decided yet (0.10.83, D2.3). */
export function shownOutcome(
  suggested: Suggestion | null,
  groups: QuestionGroup[],
  item: MarketItem,
  form: TreeForm,
  folded: Record<string, string>,
): Suggestion | null {
  if (suggested !== "PENDING_INFORMATION") return suggested;
  const open = groups
    .flatMap((group) => group.questions)
    .some((question) => {
      if (question.extra) return false;
      const state = questionState(question, item, form, folded);
      return !state.folded && !state.answer;
    });
  return open ? null : suggested;
}
