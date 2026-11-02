import { PracticeApproval } from "./PracticeApproval";
import { useState } from "react";
import { DecideAndSign } from "./common";
import { questionNumber } from "../../../app/labels";
import {
  ArrowDown,
  ArrowUp,
  BookOpenCheck,
  CheckCircle2,
  Download,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
  XCircle,
} from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Drawer, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { downloadFile } from "../../reports/download";
import { useCan } from "../workspaceContext";
import { Hero, InlineError } from "./boardParts";
import { OwnText } from "./MarketAssessment";
import {
  GUIDES,
  NEW_EXTRA,
  REASON_MIN,
  answersText,
  editProblem,
  moveExtra,
  outcomeText,
  questionForm,
  questionMark,
  saveBody,
  stateTone,
  type Expected,
  type GuideList,
  type GuideMarket,
  type GuideVersion,
  type QuestionForm,
  type TestCase,
} from "../decisionGuides";

function useCanEdit() {
  const review = useCan("regulatory.review");
  const approve = useCan("regulatory.approve");
  return review || approve;
}

/**
 * Complaints › Decision guides: each market's guide in versions. Version 1 is MDARIX's starter; the organization
 * makes its own from it: the regulation's wording stays locked and it adds its explanation and examples beside it, adds
 * its own questions and worked complaints, runs the test matrix, and a second person approves before the version is
 * used. The guide points to a conclusion; a person decides and signs.
 */
export function DecisionGuides() {
  const list = useResource<GuideList>(GUIDES);
  const [open, setOpen] = useState<{ market: string; version: number } | null>(null);
  const [error, setError] = useState("");
  const canEdit = useCanEdit();
  const markets = list.data?.markets ?? [];
  const own = markets.filter((item) => !item.current.starter);
  const start = async (item: GuideMarket) => {
    setError("");
    try {
      const made = await send<GuideVersion>(`${GUIDES}/${item.market}/drafts`, "POST");
      list.reload();
      setOpen({ market: item.market, version: made.version });
    } catch (reason) {
      setError(errorText(reason, "The new version was not started."));
    }
  };
  return (
    <div className="ac-overview">
      <Hero
        tone={own.length ? "good" : "neutral"}
        icon={<BookOpenCheck size={28} />}
        eyebrow="Decision guides"
        title={
          list.data
            ? own.length
              ? `${own.map((item) => item.current.code).join(", ")} in use`
              : "MDARIX starter guides in use"
            : "Reading the guides…"
        }
        detail="The questions every market assessment asks, with the regulation clause behind each. Make the guide your own: add your explanation and examples beside the regulation's wording, add your questions and worked complaints, test it, and have a colleague approve it."
      />
      <Panel eyebrow="Markets" title="Your guides and their versions" source={list}>
        {list.data && (
          <>
            <p className="uw-ma-starter" role="note">
              {list.data.never_decides}
            </p>
            <p className="ac-muted">
              {list.data.core_rule} {list.data.scale_note}
            </p>
          </>
        )}
        <InlineError text={error} />
        {markets.length ? (
          <ul className="uw-cr-list">
            {markets.map((item) => (
              <li key={item.market} className="uw-cr-card">
                <span className={`uw-cr-rail tone-${item.open ? "warning" : "good"}`} aria-hidden="true" />
                <div className="uw-cr-body">
                  <div className="uw-cr-head">
                    <strong className="uw-cr-id">{item.label}</strong>
                    <span className="uw-cr-meta">
                      In use: {item.current.code}
                      {item.current.starter ? " (MDARIX starter)" : ` · approved by ${item.current.approved_by}`}
                      {item.enabled ? "" : " · market not enabled in your reporting windows"}
                    </span>
                    <ToneBadge tone="good" label={`${item.current.questions} questions, ${item.current.tests} tests`} />
                  </div>
                  {item.open && (
                    <p className="uw-cr-meta">
                      Being prepared: <strong>{item.open.code}</strong>, {item.open.state_label.toLowerCase()}
                      {item.open.problems.length ? ` · ${item.open.problems[0]}` : " · ready to publish"}
                    </p>
                  )}
                  <ol className="uw-dg-history" aria-label={`${item.label} versions`}>
                    {item.history.map((version) => (
                      <li key={version.code}>
                        <button
                          type="button"
                          className="ac-link"
                          onClick={() => setOpen({ market: item.market, version: version.version })}
                        >
                          {version.code}
                        </button>{" "}
                        <ToneBadge tone={stateTone(version.state)} label={version.state_label} />
                        {version.sample ? <span className="uw-cr-meta"> sample</span> : null}
                      </li>
                    ))}
                  </ol>
                  <div className="ca-action-row">
                    {item.open ? (
                      <button
                        type="button"
                        className="ac-primary"
                        onClick={() => setOpen({ market: item.market, version: item.open!.version })}
                      >
                        Open {item.open.code}
                      </button>
                    ) : (
                      canEdit && (
                        <button type="button" className="ac-secondary" onClick={() => void start(item)}>
                          <Plus size={15} aria-hidden="true" /> Start a new version from {item.current.code}
                        </button>
                      )
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <Empty title="No guide to show" detail="Each market's guide appears here." />
        )}
        {list.data && <p className="ac-muted">{list.data.starter_mark}</p>}
      </Panel>
      {open && (
        <GuideDrawer
          market={open.market}
          version={open.version}
          onClose={() => {
            setOpen(null);
            list.reload();
          }}
        />
      )}
    </div>
  );
}

function useRun(onChanged: (view: GuideVersion) => void, failure: string) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (path: string, method: "POST" | "PUT", body?: unknown) => {
    setBusy(true);
    setError("");
    try {
      onChanged(await send<GuideVersion>(path, method, body));
      return true;
    } catch (reason) {
      setError(errorText(reason, failure));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

/** One version: its questions with their clauses, its test cases and results, and its approval. */
export function GuideDrawer({ market, version, onClose }: { market: string; version: number; onClose: () => void }) {
  const resource = useResource<GuideVersion>(`${GUIDES}/${market}/versions/${version}`);
  const [shown, setShown] = useState<GuideVersion | null>(null);
  const view = shown && shown.version === version && shown.market === market ? shown : resource.data;
  const canEdit = useCanEdit();
  if (!view) {
    return (
      <Drawer title="Decision guide" onClose={onClose}>
        <p className="ac-muted">
          {resource.error ? errorText(resource.error, "The guide could not be read.") : "Reading…"}
        </p>
      </Drawer>
    );
  }
  const editing = view.state === "DRAFT" && canEdit;
  return (
    <Drawer title={`${view.market_label}: ${view.code}`} onClose={onClose}>
      <div className="uw-dp uw-dg">
        <div className="uw-cr-decision">
          <ToneBadge tone={stateTone(view.state)} label={view.state_label} />
          <span className="uw-cr-meta">
            {view.starter ? "Written by MDARIX" : `Based on ${view.based_on}`}
            {view.sample ? " · sample" : ""}
          </span>
        </div>
        <p className="uw-hint" role="note">
          {view.never_decides}
        </p>
        <p className="ac-muted">{view.core_rule}</p>
        {view.matrix_rule && <p className="ac-muted">{view.matrix_rule}</p>}
        {view.change_reason && (
          <p>
            <strong>What changed and why:</strong> {view.change_reason}
          </p>
        )}
        <Downloads view={view} />
        {editing ? (
          <Editor key={`${view.code}-${view.state}`} view={view} onChanged={setShown} />
        ) : (
          <>
            <QuestionTable view={view} />
            <TestTable view={view} tests={view.test_cases} />
          </>
        )}
        {view.state === "AWAITING_APPROVAL" && <MatrixCheck view={view} />}
        {view.editable && <Publish view={view} onChanged={setShown} canEdit={canEdit} />}
        <ApprovalRecord view={view} />
        <p className="ac-muted">
          {view.starter_mark} {view.scale_note}
        </p>
      </div>
    </Drawer>
  );
}

function QuestionTable({ view }: { view: GuideVersion }) {
  return (
    <section className="ca-drawer-section" aria-label="Questions">
      <h3>Questions ({view.question_set.questions.length})</h3>
      <div className="uw-dg-scroll">
        <table className="uw-dg-table">
          <thead>
            <tr>
              <th scope="col">No.</th>
              <th scope="col">Question</th>
              <th scope="col">Clause</th>
              <th scope="col">Basis</th>
            </tr>
          </thead>
          <tbody>
            {view.question_set.questions.map((question) => (
              <tr key={question.id} className={question.extra ? "uw-dg-extra" : ""}>
                <th scope="row">{questionNumber(question.id)}</th>
                <td>
                  <strong>{question.text}</strong>
                  {question.note && <p className="uw-hint">{question.note}</p>}
                  <OwnText question={question} />
                  <span className="uw-ma-starter-chip">{questionMark(question)}</span>
                </td>
                <td>{question.clause || <span className="tone-critical">No clause</span>}</td>
                <td>{question.basis.join(", ") || <span className="tone-critical">None</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TestTable({ view, tests }: { view: GuideVersion; tests: TestCase[] }) {
  const results = Object.fromEntries((view.test_results?.results ?? []).map((item) => [item.id, item]));
  const run = view.test_results;
  return (
    <section className="ca-drawer-section" aria-label="Test matrix">
      <h3>
        Test matrix: {tests.length} worked complaints
        {run ? ` · ${run.passed} passed, ${run.failed} failed` : " · not run yet"}
      </h3>
      {run && !run.current && <p className="uw-hint">Changed since the last run: run the test matrix again.</p>}
      {run?.run_at && (
        <p className="ac-muted">
          Run by {run.run_by} {formatDate(run.run_at)}.
        </p>
      )}
      <ul className="uw-dg-tests">
        {tests.map((test) => {
          const result = results[test.id];
          return (
            <li key={test.id} className={result && !result.passed ? "uw-dg-failed" : ""}>
              <strong>
                {result ? (
                  result.passed ? (
                    <CheckCircle2 size={14} className="tone-good" aria-label="Passed" />
                  ) : (
                    <XCircle size={14} className="tone-critical" aria-label="Failed" />
                  )
                ) : null}{" "}
                {test.name}
              </strong>{" "}
              <span className="uw-ma-starter-chip">{test.starter ? "MDARIX starter" : "Your worked complaint"}</span>
              <span className="uw-cr-meta">
                Answers:{" "}
                {answersText(
                  test,
                  view.answer_labels,
                  view.question_set.questions.map((question) => question.id),
                )}{" "}
                · expected{" "}
                {outcomeText(test.expected, test.expected_report_type, view.expected_labels, view.report_types)}
                {result && !result.passed
                  ? ` · the guide points to ${outcomeText(result.actual, result.actual_report_type, view.expected_labels, view.report_types)}`
                  : ""}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Editor({ view, onChanged }: { view: GuideVersion; onChanged: (view: GuideVersion) => void }) {
  const [questions, setQuestions] = useState<QuestionForm[]>(() => view.question_set.questions.map(questionForm));
  const [tests, setTests] = useState<TestCase[]>(() => view.test_cases);
  const action = useRun(onChanged, "The draft was not saved.");
  const problem = editProblem(questions);
  const set = (index: number, patch: Partial<QuestionForm>) =>
    setQuestions((current) => current.map((item, at) => (at === index ? { ...item, ...patch } : item)));
  return (
    <form
      aria-label="Edit the draft"
      onSubmit={(event) => {
        event.preventDefault();
        void action.run(`${GUIDES}/${view.market}/versions/${view.version}`, "PUT", saveBody(questions, tests));
      }}
    >
      <section className="ca-drawer-section" aria-label="Questions">
        <h3>Questions ({questions.length})</h3>
        <p className="ac-muted">
          The questions that drive the conclusion keep the regulation's wording, definition and clause: add your
          explanation and examples beside them. Every extra question needs its regulation clause and its basis before
          the version can be published.
        </p>
        <div className="uw-dg-scroll">
          <table className="uw-dg-table uw-dg-edit">
            <thead>
              <tr>
                <th scope="col">No.</th>
                <th scope="col">Wording</th>
                <th scope="col">Clause</th>
                <th scope="col">Basis</th>
                <th scope="col">
                  <span className="ca-sr-only">Order</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {questions.map((question, index) => (
                <tr key={`${question.id}-${index}`} className={question.extra ? "uw-dg-extra" : ""}>
                  <th scope="row">
                    {question.id ? questionNumber(question.id) : "New"}
                    <span className="uw-cr-meta uw-dg-kind">{question.extra ? "extra" : "core"}</span>
                  </th>
                  {question.extra ? (
                    <>
                      <td>
                        <label className="ca-field">
                          Question
                          <textarea
                            rows={2}
                            value={question.text}
                            onChange={(event) => set(index, { text: event.target.value })}
                          />
                        </label>
                        <label className="ca-field">
                          Definition
                          <textarea
                            rows={2}
                            value={question.definition}
                            onChange={(event) => set(index, { definition: event.target.value })}
                          />
                        </label>
                        <label className="ca-field">
                          Help text
                          <textarea
                            rows={2}
                            value={question.note}
                            onChange={(event) => set(index, { note: event.target.value })}
                          />
                        </label>
                      </td>
                      <td>
                        <label className="ca-field">
                          Clause
                          <textarea
                            rows={2}
                            value={question.clause}
                            onChange={(event) => set(index, { clause: event.target.value })}
                          />
                        </label>
                        {!question.clause.trim() && <span className="tone-critical">No clause yet</span>}
                      </td>
                      <td>
                        <BasisPicker
                          catalog={view.catalog}
                          value={question.basis}
                          onChange={(basis) => set(index, { basis })}
                          label={question.id || "new question"}
                        />
                      </td>
                    </>
                  ) : (
                    <>
                      <td>
                        <strong>{question.text}</strong>
                        <p className="ac-muted">{question.definition}</p>
                        {question.note && <p className="uw-hint">{question.note}</p>}
                        <span className="uw-ma-starter-chip">The regulation's wording: locked</span>
                        <label className="ca-field">
                          Your explanation
                          <textarea
                            rows={2}
                            value={question.explanation}
                            onChange={(event) => set(index, { explanation: event.target.value })}
                          />
                        </label>
                        <label className="ca-field">
                          Your examples
                          <textarea
                            rows={2}
                            value={question.examples}
                            onChange={(event) => set(index, { examples: event.target.value })}
                          />
                        </label>
                      </td>
                      <td>{question.clause}</td>
                      <td>
                        {question.basis
                          .map((id) => view.catalog.find((item) => item.id === id)?.short ?? id)
                          .join(", ")}
                      </td>
                    </>
                  )}
                  <td>
                    {question.extra && (
                      <div className="uw-dg-order">
                        <button
                          type="button"
                          className="ac-link"
                          aria-label={`Move ${question.id || "the new question"} up`}
                          onClick={() => setQuestions((current) => moveExtra(current, index, -1))}
                        >
                          <ArrowUp size={14} aria-hidden="true" />
                        </button>
                        <button
                          type="button"
                          className="ac-link"
                          aria-label={`Move ${question.id || "the new question"} down`}
                          onClick={() => setQuestions((current) => moveExtra(current, index, 1))}
                        >
                          <ArrowDown size={14} aria-hidden="true" />
                        </button>
                        <button
                          type="button"
                          className="ac-link"
                          aria-label={`Remove ${question.id || "the new question"}`}
                          onClick={() => setQuestions((current) => current.filter((_, at) => at !== index))}
                        >
                          <Trash2 size={14} aria-hidden="true" />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button
          type="button"
          className="ac-secondary"
          onClick={() => setQuestions((current) => [...current, NEW_EXTRA])}
        >
          <Plus size={15} aria-hidden="true" /> Add an extra question
        </button>
      </section>
      <TestTable view={view} tests={tests} />
      <TestEditor view={view} onAdd={(test) => setTests((current) => [...current, test])} />
      {tests.some((test) => !test.starter) && (
        <p className="ac-muted">
          To remove one of your worked complaints:{" "}
          {tests
            .filter((test) => !test.starter)
            .map((test) => (
              <button
                key={test.id}
                type="button"
                className="ac-link"
                onClick={() => setTests((current) => current.filter((item) => item !== test))}
              >
                {test.id}{" "}
              </button>
            ))}
        </p>
      )}
      <div className="ca-action-row">
        <button type="submit" className="ac-primary" disabled={action.busy || !!problem}>
          <Save size={15} aria-hidden="true" /> {action.busy ? "Saving…" : "Save the draft"}
        </button>
      </div>
      <InlineError text={problem ?? action.error} />
    </form>
  );
}

function BasisPicker({
  catalog,
  value,
  onChange,
  label,
}: {
  catalog: GuideVersion["catalog"];
  value: string[];
  onChange: (value: string[]) => void;
  label: string;
}) {
  return (
    <div className="uw-dg-basis">
      {value.map((id) => (
        <span key={id} className="uw-basis-chip">
          {catalog.find((item) => item.id === id)?.short ?? id}{" "}
          <button
            type="button"
            className="ac-link"
            aria-label={`Remove ${id} from ${label}`}
            onClick={() => onChange(value.filter((item) => item !== id))}
          >
            ×
          </button>
        </span>
      ))}
      <label className="ca-field">
        Add a basis
        <select value="" onChange={(event) => event.target.value && onChange([...value, event.target.value])}>
          <option value="">Choose…</option>
          {catalog
            .filter((item) => !value.includes(item.id))
            .map((item) => (
              <option key={item.id} value={item.id}>
                {item.short}: {item.title}
              </option>
            ))}
        </select>
      </label>
      {!value.length && <span className="tone-critical">No basis yet</span>}
    </div>
  );
}

function TestEditor({ view, onAdd }: { view: GuideVersion; onAdd: (test: TestCase) => void }) {
  const core = view.question_set.questions.filter((question) => !question.extra);
  const [name, setName] = useState("");
  const [expected, setExpected] = useState<Expected | "">("");
  const [kind, setKind] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [open, setOpen] = useState(false);
  if (!open)
    return (
      <button type="button" className="ac-secondary" onClick={() => setOpen(true)}>
        <Plus size={15} aria-hidden="true" /> Add a worked complaint
      </button>
    );
  const ready = name.trim().length >= 3 && expected;
  return (
    <fieldset className="ca-drawer-section uw-dg-test-editor">
      <legend>New worked complaint</legend>
      <p className="ac-muted">
        Name the complaint in a line, answer the questions as you would for it, and choose what the guide must point to.
        A question left blank is Unknown, never No.
      </p>
      <label className="ca-field">
        Name
        <input value={name} onChange={(event) => setName(event.target.value)} />
      </label>
      <div className="ca-form-grid">
        {core.map((question) => (
          <label key={question.id} className="ca-field">
            {questionNumber(question.id)}. {question.text}
            <select
              value={answers[question.id] ?? ""}
              onChange={(event) => setAnswers({ ...answers, [question.id]: event.target.value })}
            >
              <option value="">Blank (Unknown)</option>
              {Object.entries(view.answer_labels).map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        ))}
        <label className="ca-field">
          The guide must point to
          <select value={expected} onChange={(event) => setExpected(event.target.value as Expected)}>
            <option value="">Choose…</option>
            {Object.entries(view.expected_labels).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {expected === "REPORTABLE" && (
          <label className="ca-field">
            Report type (optional)
            <select value={kind} onChange={(event) => setKind(event.target.value)}>
              <option value="">Any</option>
              {view.report_types.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="ca-action-row">
        <button
          type="button"
          className="ac-secondary"
          disabled={!ready}
          onClick={() => {
            onAdd({
              id: `new-${Date.now()}`,
              name: name.trim(),
              answers: Object.fromEntries(Object.entries(answers).filter(([, value]) => value)),
              expected: expected as Expected,
              expected_report_type: expected === "REPORTABLE" && kind ? kind : null,
            });
            setOpen(false);
            setName("");
            setExpected("");
            setKind("");
            setAnswers({});
          }}
        >
          Add it to the draft
        </button>
      </div>
    </fieldset>
  );
}

function Publish({
  view,
  onChanged,
  canEdit,
}: {
  view: GuideVersion;
  onChanged: (view: GuideVersion) => void;
  canEdit: boolean;
}) {
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const action = useRun(onChanged, "That step was not recorded.");
  const base = `${GUIDES}/${view.market}/versions/${view.version}`;
  // Discarding a draft cannot be undone: it is confirmed here, beside the button, never on the first click (F).
  const [discarding, setDiscarding] = useState(false);
  return (
    <section className="ca-drawer-section" aria-label="Publish">
      <h3>Before it is used</h3>
      {view.problems.length ? (
        <ul className="uw-dg-problems" aria-label="What blocks publication">
          {view.problems.map((problem) => (
            <li key={problem} className="tone-critical">
              {problem}
            </li>
          ))}
        </ul>
      ) : (
        <p className="tone-good">Every question has its clause and every worked complaint in the matrix passes.</p>
      )}
      {canEdit && view.state === "DRAFT" && (
        <>
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-secondary"
              disabled={action.busy || !view.test_cases.length}
              aria-describedby={view.test_cases.length ? undefined : "guide-tests-reason"}
              onClick={() => void action.run(`${base}/tests`, "POST")}
            >
              Run the test matrix
            </button>
            {!view.test_cases.length && (
              <span className="ms-reason" id="guide-tests-reason">
                Add a worked complaint to the matrix first.
              </span>
            )}
            <button
              type="button"
              className="ac-link"
              disabled={action.busy}
              aria-expanded={discarding}
              onClick={() => setDiscarding(true)}
            >
              Discard this draft
            </button>
          </div>
          {discarding && (
            <div className="ms-confirm" role="group" aria-label="Discard this draft">
              <p>
                Discard version {view.version}? Its questions, wording and worked complaints are deleted. This cannot be
                undone.
              </p>
              <div className="ca-action-row">
                <button
                  type="button"
                  className="ca-danger"
                  disabled={action.busy}
                  onClick={() => void action.run(`${base}/discard`, "POST")}
                >
                  Discard the draft
                </button>
                <button type="button" className="ac-secondary" onClick={() => setDiscarding(false)}>
                  Keep it
                </button>
              </div>
            </div>
          )}
          <label className="ca-field">
            What changed and why
            <textarea rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-primary"
              disabled={action.busy || view.problems.length > 0 || reason.trim().length < REASON_MIN}
              onClick={() => void action.run(`${base}/approval-request`, "POST", { change_reason: reason })}
            >
              <ShieldCheck size={15} aria-hidden="true" /> Ask a colleague to approve it
            </button>
          </div>
        </>
      )}
      {view.state === "AWAITING_APPROVAL" && view.approval && !view.approval.may_approve && (
        <div className="uw-rp-approval" role="note" aria-label="Who approves the version">
          <p>
            <strong>{view.code}</strong> sent for approval by {view.requested_by} {formatDate(view.requested_at)}.
          </p>
          <p>{view.approval.message}</p>
        </div>
      )}
      {canEdit && view.you_asked && (
        <div className="ca-action-row">
          <button
            type="button"
            className="ac-secondary"
            disabled={action.busy}
            onClick={() => void action.run(`${base}/withdraw`, "POST")}
          >
            Withdraw it: back to draft
          </button>
        </div>
      )}
      {canEdit && view.state === "AWAITING_APPROVAL" && view.approval?.may_approve !== false && (
        <form
          className="uw-rp-approval"
          aria-label="Approve the version"
          onSubmit={(event) => {
            event.preventDefault();
            void action.run(`${base}/approve`, "POST", { password, mfa_code: code || null });
          }}
        >
          <p>
            <strong>{view.code}</strong> sent for approval by {view.requested_by} {formatDate(view.requested_at)}. Not
            allowed to approve: {view.editors.join(", ")} (who edited it) and administrators.
          </p>
          {view.approval?.same_person && <p className="ac-message tone-warning">{view.approval.message}</p>}
          <div className="ca-form-grid">
            <DecideAndSign />
            <label className="ca-field">
              Your password
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <label className="ca-field">
              Authenticator code
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                value={code}
                onChange={(event) => setCode(event.target.value)}
              />
            </label>
          </div>
          <p className="ac-muted">
            Your approval publishes this version: assessments started from now on use it; ones in progress keep theirs.
          </p>
          <div className="ca-action-row">
            <button
              type="submit"
              className="ac-primary"
              disabled={action.busy || !password || !!view.matrix_changed?.length}
            >
              {action.busy ? "Approving…" : "Approve and publish"}
            </button>
            <PracticeApproval shown={view.approval?.same_person} />
          </div>
        </form>
      )}
      <InlineError text={action.error} />
    </section>
  );
}

/** For the approver: the test matrix run again now. A worked complaint whose answer changed blocks the approval. */
function MatrixCheck({ view }: { view: GuideVersion }) {
  const changed = view.matrix_changed ?? [];
  const rows = view.test_cases.length;
  return (
    <section className="ca-drawer-section" aria-label="Test matrix check">
      <h3>Test matrix, run again now</h3>
      {changed.length ? (
        <>
          <p className="tone-critical">
            {changed.length} of {rows} worked complaints give a different answer now. This version cannot be approved:
            its author changes it and sends it again.
          </p>
          <ul className="uw-dg-problems" aria-label="Worked complaints whose answer changed">
            {changed.map((name) => (
              <li key={name} className="tone-critical">
                {name}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="tone-good">All {rows} worked complaints still give the expected answer.</p>
      )}
    </section>
  );
}

function ApprovalRecord({ view }: { view: GuideVersion }) {
  if (view.starter)
    return (
      <p className="ac-muted">MDARIX's starter guide: your organization adopts it by approving its own version.</p>
    );
  if (!view.signature) return null;
  return (
    <section className="ca-drawer-section" aria-label="Approval">
      <h3>Approval</h3>
      <p>
        Approved by <strong>{view.signature.signer_name}</strong> ({view.signature.signer_role}) on{" "}
        {formatDate(view.signature.signed_at)}.
      </p>
      <p className="ac-muted">Meaning: {view.signature.meaning}</p>
      <p className="ac-muted">
        Signature record {view.signature.record_business_id ?? view.signature.record_id} · checksum{" "}
        {view.signature.content_fingerprint.slice(0, 12)}…
      </p>
    </section>
  );
}

function Downloads({ view }: { view: GuideVersion }) {
  const canExport = useCan("data.export");
  const [error, setError] = useState("");
  if (!canExport) return null;
  const get = async (kind: "pdf" | "docx") => {
    setError("");
    try {
      await downloadFile(`${GUIDES}/${view.market}/versions/${view.version}/guide.${kind}`, {
        fallbackName: `mdarix-guide-${view.code}.${kind}`,
      });
    } catch (reason) {
      setError(errorText(reason, "The file could not be downloaded."));
    }
  };
  return (
    <div className="ca-action-row uw-doc-downloads">
      <button type="button" className="ac-secondary" onClick={() => void get("pdf")}>
        <Download size={15} aria-hidden="true" /> PDF for an audit
      </button>
      <button type="button" className="ac-secondary" onClick={() => void get("docx")}>
        <Download size={15} aria-hidden="true" /> DOCX
      </button>
      <InlineError text={error} />
    </div>
  );
}
