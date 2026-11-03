import { useRef, useState, type ReactNode } from "react";
import { Lock } from "lucide-react";
import { errorText, send, useResource } from "../../customer-admin/shared";
import { questionNumber } from "../../../app/labels";
import { useCan, useTabParam, useWorkspace } from "../workspaceContext";
import {
  ANSWER_LABELS,
  CONCLUSION_LABELS,
  assessmentPath,
  type Answer,
  type AssessmentDetail,
  type MarketItem,
  type Question,
  type Suggestion,
} from "../marketAssessment";
import {
  foldedRuns,
  groupQuestions,
  criterion,
  questionState,
  runLabel,
  treeAnswers as draftAnswers,
  treeFormOf,
  whyChips,
  type QuestionGroup,
  type TreeForm,
} from "../treeAnswer";
import { ReportingFacts } from "./ReportingFacts";
import { InlineError } from "./boardParts";
import { TREE_NAMES, type TreeMarket, type TreePath, type Trees } from "../decisionTrees";
import { FormCard, SignCard } from "./TreeSign";
import "./decide.css";

/** Whether the signed-in person's real role may answer and sign (regulatory review or approval), never the persona. */
export function useCanDecide() {
  const review = useCan("regulatory.review");
  const approve = useCan("regulatory.approve");
  return review || approve;
}

/** The complaint the tree opens on: the one asked for, else the first with nothing signed yet, else the first. */
export function firstComplaint(trees: Pick<Trees, "complaints">, asked: string | null): string | null {
  if (asked) return asked;
  return (trees.complaints.find((item) => !item.signed.length) ?? trees.complaints[0])?.id ?? null;
}

/**
 * The Decision trees tab's Answer mode (0.10.83, D2.1-D2.3): pick a complaint, then answer each question of a market's
 * tree in place. Facts the record states arrive as one line to confirm; judgements are never pre-filled; questions
 * earlier answers make unnecessary fold away; the outcome updates as the answers are saved. Signing is the rail's.
 */
export function TreeAnswer({ trees }: { trees: Trees }) {
  const { open } = useWorkspace();
  const [complaintParam, setComplaint] = useTabParam("complaint", "replace");
  const [marketParam, setMarket] = useTabParam("market", "replace");
  const complaintId = firstComplaint(trees, complaintParam);
  const detail = useResource<AssessmentDetail>(complaintId ? assessmentPath(complaintId) : null);
  const paths = useResource<Trees>(
    complaintId ? `/api/v1/decision-trees?complaint_id=${encodeURIComponent(complaintId)}` : null,
  );
  const data = detail.data?.complaint.id === complaintId ? detail.data : null;
  const shown = data?.markets ?? [];
  const item =
    shown.find((entry) => entry.market === marketParam) ?? shown.find((entry) => entry.preselected) ?? shown[0];
  const listed = trees.complaints.find((entry) => entry.id === complaintId);
  const ref = data ? (data.complaint.complaint_identifier ?? data.complaint.business_id) : (listed?.ref ?? null);
  const reload = () => {
    detail.reload();
    paths.reload();
  };
  if (!trees.complaints.length && !complaintParam)
    return (
      <section className="uw-card uw-card-pad dt-empty">
        <h2>No complaint waits for a decision</h2>
        <p className="ac-muted">
          A complaint that reports a death, a serious injury or a malfunction comes here to be answered.
        </p>
      </section>
    );
  return (
    <div className="dt-answer">
      <section className="uw-card dt-picker" aria-label="The complaint">
        <label className="dt-pick">
          <span>Complaint</span>
          <select value={complaintId ?? ""} onChange={(event) => setComplaint(event.target.value)}>
            {!listed && complaintId && <option value={complaintId}>{ref ?? "This complaint"}</option>}
            {trees.complaints.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.ref} · {shortText(entry.description)}
              </option>
            ))}
          </select>
        </label>
        {data?.complaint.description && <blockquote className="dt-quote">“{data.complaint.description}”</blockquote>}
        {ref && (
          <button
            type="button"
            className="ac-link dt-open"
            onClick={() => open("Complaint", `Summary?ref=${encodeURIComponent(ref)}`)}
          >
            Open the complaint
          </button>
        )}
      </section>
      {detail.state === "error" && <InlineError text={errorText(detail.error, "The questions could not be read.")} />}
      {data && <ReportingFacts complaintId={data.complaint.id} needs={data.complaint.needs} onSaved={reload} />}
      {data && (
        <div className="dt-markets" role="group" aria-label="Market">
          {trees.markets.map((tree) => {
            const entry = shown.find((one) => one.market === tree.market);
            return (
              <button
                key={tree.market}
                type="button"
                className={entry && entry.market === item?.market ? "dt-mkt is-on" : "dt-mkt"}
                aria-pressed={!!entry && entry.market === item?.market}
                disabled={!entry}
                title={entry ? undefined : "Not in your reporting windows"}
                onClick={() => setMarket(tree.market)}
              >
                {TREE_NAMES[tree.market] ?? tree.label}
                {entry?.preselected ? <small> · event's country</small> : null}
              </button>
            );
          })}
        </div>
      )}
      {data && !shown.length && (
        <p className="ac-muted">
          No market is enabled yet: enter your reporting windows (Settings › Reporting windows) for the markets you
          report to.
        </p>
      )}
      {data && item && (
        <MarketTree
          key={`${data.complaint.id}-${item.market}`}
          detail={data}
          item={item}
          tree={trees.markets.find((tree) => tree.market === item.market) ?? null}
          trees={trees.markets}
          path={paths.data?.paths?.[item.market] ?? null}
          onSigned={reload}
        />
      )}
    </div>
  );
}

const shortText = (text: string | null | undefined) =>
  !text ? "" : text.length > 60 ? `${text.slice(0, 59).trimEnd()}…` : text;

/** One market's tree for one complaint: the questions in place, and the outcome and Sign card beside them. */
export function MarketTree({
  detail,
  item,
  tree,
  trees,
  path,
  onSigned,
}: {
  detail: AssessmentDetail;
  item: MarketItem;
  tree: TreeMarket | null;
  trees: TreeMarket[];
  path: TreePath | null;
  onSigned: () => void;
}) {
  const canDecide = useCanDecide();
  const groups = groupQuestions(item.question_set.questions);
  const [form, setForm] = useState<TreeForm>(() => treeFormOf(item, groups));
  const [latest, setLatest] = useState<MarketItem>(item);
  const [harm, setHarm] = useState(() => ({
    level: (item.draft ?? item.current)?.harm_level ?? detail.severity_level ?? "",
    reason: (item.draft ?? item.current)?.harm_level_reason ?? "",
    disagreement: item.draft?.scale_disagreement_reason ?? "",
  }));
  const [changing, setChanging] = useState<string | null>(null);
  const [error, setError] = useState("");
  const refs = useRef({ form, harm, latest });
  refs.current = { form, harm, latest };
  const queue = useRef<Promise<MarketItem | null>>(Promise.resolve(null));
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const signed = !!latest.current && !latest.draft;
  const folded: Record<string, string> = signed
    ? Object.fromEntries((path?.nodes ?? []).filter((node) => node.not_asked).map((node) => [node.id, node.not_asked!]))
    : (latest.evaluation?.not_asked ?? {});
  const editable = canDecide && !signed;

  /** Save the draft (one at a time, in order); the server's evaluation comes back with it. */
  const save = (): Promise<MarketItem | null> => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    queue.current = queue.current.then(async () => {
      const now = refs.current;
      try {
        const out = await send<AssessmentDetail>(assessmentPath(detail.complaint.id, item.market), "PUT", {
          answers: draftAnswers(groups, now.latest, now.form, now.latest.evaluation?.not_asked ?? {}),
          harm_level: now.harm.level || null,
          harm_code: now.latest.draft?.harm_code ?? null,
          harm_level_reason: now.harm.reason,
          scale_disagreement_reason: now.harm.disagreement,
        });
        const next = out.markets.find((entry) => entry.market === item.market) ?? null;
        if (next) setLatest(next);
        setError("");
        return next;
      } catch (reason) {
        setError(errorText(reason, "The answer was not saved."));
        return null;
      }
    });
    return queue.current;
  };
  const answer = (id: string, value: Answer | null) => {
    const next = { ...refs.current.form, answers: { ...refs.current.form.answers, [id]: value } };
    refs.current.form = next;
    setForm(next);
    setChanging(null);
    void save();
  };
  const later = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => void save(), 700);
  };
  const reason = (key: string, text: string) => {
    const next = { ...refs.current.form, reasons: { ...refs.current.form.reasons, [key]: text } };
    refs.current.form = next;
    setForm(next);
    later();
  };
  const setHarmNow = (next: typeof harm) => {
    refs.current.harm = next;
    setHarm(next);
    later();
  };

  const outcome: Suggestion | null = signed
    ? (latest.current?.conclusion ?? null)
    : latest.draft
      ? (latest.evaluation?.suggested ?? null)
      : null;
  const chips = whyChips(item.question_set.questions, form, folded, outcome);
  const runs = foldedRuns(item.question_set.questions, folded);
  const flat = item.question_set.questions;
  const signedAnswers = latest.current?.answers ?? {};
  let mini = false;

  return (
    <div className="dt-rec">
      <section className="uw-card dt-tree" aria-label={`The ${item.label} questions`}>
        <div className="dt-tree-head">
          <h2>{item.question_set.title}</h2>
          <span className="ac-muted">
            {tree?.version_label ?? item.question_set.version}
            {item.question_set_current === false ? " · started on an earlier version: it keeps that one" : ""}
          </span>
        </div>
        <ol className="dt-qs">
          {groups.map((group, index) => {
            const all = group.questions.every((question) => folded[question.id]);
            if (all) {
              const run = runs.find((entry) => entry.ids.includes(group.questions[0].id));
              if (!run || run.first !== group.questions[0].id) return null;
              return (
                <li key={group.key} className="dt-fold">
                  <span className="dt-n is-off" aria-hidden="true">
                    {questionNumber(run.first).replace(/[a-z]$/, "")}
                  </span>
                  <span>
                    <b>{runLabel(run.ids)}</b>
                    {` ${run.why.replace(/^Not (asked|needed): /, (all) => all.toLowerCase())}`}
                  </span>
                </li>
              );
            }
            const node = (
              <GroupCard
                key={group.key}
                group={group}
                item={latest}
                form={form}
                folded={folded}
                editable={editable}
                signed={signed}
                signedAnswers={signedAnswers}
                changing={changing}
                onChange={setChanging}
                onAnswer={answer}
                onReason={(text) => reason(group.key, text)}
                onBlur={() => void save()}
                notes={item.record_notes ?? {}}
              />
            );
            if (mini || index > 1 || group.questions[0].extra) return node;
            mini = true;
            // The phone's outcome bar sits below the first question, never over it (the approved design).
            return [
              node,
              <li key="mini" className="dt-mini" aria-hidden={signed ? undefined : "true"}>
                <span>{miniText(outcome, latest, signed)}</span>
                <a href="#dt-outcome" className={signed || !outcome ? "ac-link" : "ac-primary dt-mini-sign"}>
                  {signed || !outcome ? "See the outcome" : "Sign"}
                </a>
              </li>,
            ];
          })}
        </ol>
        <InlineError text={error} />
      </section>
      <aside className="dt-rail" aria-label="Outcome">
        <SignCard
          detail={detail}
          item={latest}
          tree={tree}
          path={path}
          outcome={outcome}
          chips={chips}
          signed={signed}
          canDecide={canDecide}
          groups={groups}
          form={form}
          folded={folded}
          harm={harm}
          onHarm={setHarmNow}
          flush={save}
          onSigned={(next) => {
            setLatest(next);
            onSigned();
          }}
          flat={flat}
        />
        <FormCard
          item={latest}
          tree={tree}
          trees={trees}
          outcome={outcome}
          signed={signed}
          path={path}
          enabled={detail.enabled_markets}
        />
      </aside>
    </div>
  );
}

function miniText(outcome: Suggestion | null, item: MarketItem, signed: boolean): string {
  if (!outcome) return "Not decided yet";
  const kind = (signed ? item.current : item.draft)?.report_type_label;
  const days = kind ? /(\d+)[- ](?:calendar-|work-)?day/i.exec(kind) : null;
  return `${CONCLUSION_LABELS[outcome]}${outcome === "REPORTABLE" && days ? ` · ${days[1]} days` : ""}${signed ? " · signed" : ""}`;
}

/** A group's clause: what its criteria's clauses share ("21 CFR 803.3(w)(1)" … "(3)" -> "21 CFR 803.3(w)"). */
export function groupClause(questions: readonly Question[]): string {
  const [first, ...rest] = questions.map((question) => question.clause);
  if (!rest.length) return first;
  let shared = first;
  for (const clause of rest) while (!clause.startsWith(shared)) shared = shared.slice(0, -1);
  const cut = shared.lastIndexOf(")");
  return cut > 0 ? shared.slice(0, cut + 1) : first;
}

const ANSWERS: Answer[] = ["YES", "NO", "UNKNOWN", "NOT_APPLICABLE"];
const EXTRA_ANSWERS: Answer[] = ["YES", "NO", "UNKNOWN"];

/** One question, or one definition's criteria with one reason, on the tree. */
function GroupCard({
  group,
  item,
  form,
  folded,
  editable,
  signed,
  signedAnswers,
  changing,
  onChange,
  onAnswer,
  onReason,
  onBlur,
  notes,
}: {
  group: QuestionGroup;
  item: MarketItem;
  form: TreeForm;
  folded: Record<string, string>;
  editable: boolean;
  signed: boolean;
  signedAnswers: Record<string, { answer: Answer | null; rationale: string }>;
  changing: string | null;
  onChange: (id: string | null) => void;
  onAnswer: (id: string, value: Answer | null) => void;
  onReason: (text: string) => void;
  onBlur: () => void;
  notes: Record<string, string>;
}) {
  const first = group.questions[0];
  const grouped = !!group.title;
  const states = group.questions.map((question) => questionState(question, item, form, folded));
  const wantsReason = states.some((state) => state.needsReason);
  const judgement = !first.extra && states.some((state) => !state.fact);
  const done = signed || states.every((state) => state.folded || (!state.toConfirm && !!state.answer));
  const number = grouped ? questionNumber(first.id).replace(/[a-z]$/, "") : questionNumber(first.id);
  const note = group.questions.map((question) => notes[question.id]).find(Boolean);
  const title = grouped ? group.title : first.extra ? `Extra. ${first.text}` : first.text;
  const signedReason = signed
    ? group.questions.map((question) => signedAnswers[question.id]?.rationale).find(Boolean)
    : null;
  const head = (
    <div className="dt-q-head">
      <span className={`dt-n${done ? " is-done" : ""}`} aria-hidden="true">
        {done ? "✓" : first.extra ? "+" : number}
      </span>
      <div className="dt-q-body">
        <p className="dt-q-text" id={`qt-${first.id}`}>
          <span className="sr-only">{first.extra ? "Extra question" : `Question ${number}`}: </span>
          {title}
        </p>
        <div className="dt-q-meta">
          {first.extra ? (
            <span className="dt-tag">Never changes the conclusion</span>
          ) : judgement && !signed ? (
            <span className="dt-tag is-judge">Your judgement</span>
          ) : null}
          <details className="dt-rule">
            <summary>
              <Lock size={12} aria-hidden="true" /> {groupClause(group.questions)}
            </summary>
            <p>
              {first.definition} <em>The regulation's text, locked.</em>
            </p>
          </details>
          {!grouped && states[0].fact && !signed && (
            <span className="dt-src">
              {states[0].changed
                ? `You changed the record's answer (${ANSWER_LABELS[states[0].fact.answer]}): say why.`
                : states[0].fact.source}
            </span>
          )}
        </div>
        {note && !signed && <p className="dt-note">{note}</p>}
      </div>
    </div>
  );
  return (
    <li
      className={`dt-q${first.extra ? " is-extra" : ""}${done ? " is-done" : ""}${grouped ? " is-group" : ""}`}
      id={grouped ? `g-${first.id}` : `q-${first.id}`}
      role="group"
      aria-labelledby={`qt-${first.id}`}
    >
      {grouped && head}
      {group.questions.map((question, index) => (
        <QuestionRow
          key={question.id}
          question={question}
          head={grouped ? null : head}
          label={grouped ? `(${criterion(question.text)?.letter}) ${criterion(question.text)?.rest}` : null}
          state={states[index]}
          editable={editable}
          signed={signed}
          signedAnswer={signedAnswers[question.id]?.answer ?? null}
          open={changing === question.id}
          onChange={onChange}
          onAnswer={onAnswer}
        />
      ))}
      {signed && signedReason && <p className="dt-reason-text">{signedReason}</p>}
      {!signed && wantsReason && (
        <label className="dt-why">
          <span>Why? One line, kept with your signature</span>
          <input
            value={form.reasons[group.key] ?? ""}
            disabled={!editable}
            maxLength={2000}
            placeholder="What in the record supports this answer"
            onChange={(event) => onReason(event.target.value)}
            onBlur={onBlur}
          />
        </label>
      )}
      {!signed && states.some((state) => state.answer === "UNKNOWN") && (
        <p className="dt-unknown">
          Unknown: a question to the reporter is created. Until it is answered, the shortest deadline the facts do not
          rule out applies.
        </p>
      )}
    </li>
  );
}

function QuestionRow({
  question,
  head,
  label,
  state,
  editable,
  signed,
  signedAnswer,
  open,
  onChange,
  onAnswer,
}: {
  question: Question;
  head: ReactNode;
  label: string | null;
  state: ReturnType<typeof questionState>;
  editable: boolean;
  signed: boolean;
  signedAnswer: Answer | null;
  open: boolean;
  onChange: (id: string | null) => void;
  onAnswer: (id: string, value: Answer | null) => void;
}) {
  const number = questionNumber(question.id);
  // A criterion of a group is its own anchor, for the outcome's "Why" chips.
  const anchor = label ? `q-${question.id}` : undefined;
  const lead = head ?? <span className="dt-row-label">{label}</span>;
  const change = editable && (
    <button type="button" className="ac-link dt-change" onClick={() => onChange(open ? null : question.id)}>
      {open ? "Keep it" : "Change"}
    </button>
  );
  let act: ReactNode;
  if (state.folded) act = <span className="ac-muted dt-folded">{state.folded}</span>;
  else if (signed)
    act = <b className="dt-given">{signedAnswer ? `✓ ${ANSWER_LABELS[signedAnswer]}` : "Not answered"}</b>;
  else if (state.fact && !state.changed && !open)
    act = state.toConfirm ? (
      <>
        <button
          type="button"
          className="ac-secondary dt-confirm"
          disabled={!editable}
          onClick={() => onAnswer(question.id, state.fact!.answer)}
        >
          Confirm {ANSWER_LABELS[state.fact.answer]}
        </button>
        {change}
      </>
    ) : (
      <>
        <b className="dt-given">✓ {ANSWER_LABELS[state.fact.answer]}</b>
        {change}
      </>
    );
  else
    act = (
      <>
        <span className="dt-answers" role="group" aria-label={`Answer to question ${number}`}>
          {(question.extra ? EXTRA_ANSWERS : ANSWERS).map((value) => (
            <button
              key={value}
              type="button"
              className="dt-ab"
              aria-pressed={state.answer === value}
              disabled={!editable}
              onClick={() => onAnswer(question.id, value)}
            >
              {ANSWER_LABELS[value]}
            </button>
          ))}
        </span>
        {state.fact && open && change}
      </>
    );
  return (
    <div className={`dt-row${state.folded ? " is-folded" : ""}`} id={anchor}>
      {lead}
      <div className="dt-act">{act}</div>
    </div>
  );
}
