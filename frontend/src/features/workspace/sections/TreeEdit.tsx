import { useState } from "react";
import { Lock, Pencil, Plus, ShieldCheck } from "lucide-react";
import { errorText, send, useResource } from "../../customer-admin/shared";
import { formatDay } from "../../../app/dates";
import { questionNumber } from "../../../app/labels";
import { useTabParam } from "../workspaceContext";
import {
  GUIDES,
  NEW_EXTRA,
  REASON_MIN,
  questionForm,
  saveBody,
  type GuideList,
  type GuideVersion,
  type QuestionForm,
} from "../decisionGuides";
import { TREE_NAMES, type Trees } from "../decisionTrees";
import { collapsed } from "../complaintReview";
import { InlineError } from "./boardParts";
import { useCanDecide } from "./TreeAnswer";
import { formName } from "./TreeSign";
import { StarterNote } from "../../shared/Basis";

/** One change between the version in use and the one prepared: what it is, and its text before and after. */
export type GuideChange = { label: string; before: string; after: string };

/** Only what changed (0.10.83, D2.6): the organization's explanation and examples beside each locked question, and
 * its extra questions added, reworded or removed. The regulation's wording never changes, so it is never listed. */
export function guideChanges(before: GuideVersion | null, after: GuideVersion): GuideChange[] {
  const old = new Map((before?.question_set.questions ?? []).map((question) => [question.id, question]));
  const now = after.question_set.questions;
  const out: GuideChange[] = [];
  for (const question of now) {
    const was = old.get(question.id);
    const number = question.extra ? "Extra question" : `Q${questionNumber(question.id)}`;
    if (question.extra && !was) {
      out.push({
        label: `${number} · added, never changes the conclusion`,
        before: "Not in the version in use",
        after: question.text,
      });
      continue;
    }
    if (question.extra && was && was.text !== question.text)
      out.push({ label: `${number} · reworded`, before: was.text, after: question.text });
    for (const key of ["explanation", "examples"] as const)
      if ((was?.[key] ?? "") !== (question[key] ?? ""))
        out.push({
          label: `${number} · your ${key}`,
          before: was?.[key] || "None",
          after: question[key] || "None",
        });
  }
  for (const question of before?.question_set.questions ?? [])
    if (question.extra && !now.some((other) => other.id === question.id))
      out.push({ label: "Extra question · removed", before: question.text, after: "Removed" });
  return out;
}

/**
 * "Edit this tree" on the Decision trees tab (0.10.83, D2.6), in place of Settings › Reportability guides as the place
 * to edit (its route still works): the questions as read-only rows with a pencil, a text box only on the row being
 * edited, the regulation's text and clause always locked; extra questions that never change the conclusion; one
 * button that tests the version against the worked complaints and sends it for approval; and, for the approver, only
 * what changed with password and authenticator code. Past answers keep the version they were given under.
 */
export function TreeEdit({ trees }: { trees: Trees }) {
  const [marketParam, setMarket] = useTabParam("market", "replace");
  const list = useResource<GuideList>(GUIDES);
  const guides = list.data?.markets ?? [];
  const guide = guides.find((entry) => entry.market === marketParam) ?? guides[0];
  const inUse = useResource<GuideVersion>(guide ? `${GUIDES}/${guide.market}/versions/${guide.current.version}` : null);
  const open = useResource<GuideVersion>(
    guide?.open ? `${GUIDES}/${guide.market}/versions/${guide.open.version}` : null,
  );
  const tree = trees.markets.find((entry) => entry.market === guide?.market) ?? null;
  // Kept here, so it outlives the version's screen it reloads (an approval publishes a new version).
  const [done, setDone] = useState("");
  const reload = () => {
    list.reload();
    inUse.reload();
    open.reload();
  };
  return (
    <div className="dt-answer">
      <div className="dt-markets" role="group" aria-label="Market">
        {guides.map((entry) => (
          <button
            key={entry.market}
            type="button"
            className={entry.market === guide?.market ? "dt-mkt is-on" : "dt-mkt"}
            aria-pressed={entry.market === guide?.market}
            onClick={() => {
              setDone("");
              setMarket(entry.market);
            }}
          >
            {TREE_NAMES[entry.market] ?? entry.label}
          </button>
        ))}
      </div>
      {list.state === "error" && <InlineError text={errorText(list.error, "The trees could not be read.")} />}
      {guide && inUse.data?.version === guide.current.version && (!guide.open || open.data) && (
        <EditBody
          key={`${guide.market}-${inUse.data.version}-${guide.open?.version ?? 0}-${open.data?.state ?? ""}`}
          inUse={inUse.data}
          open={guide.open ? open.data! : null}
          enabled={guide.enabled}
          form={tree?.form ?? null}
          onChanged={reload}
          done={done}
          setDone={setDone}
        />
      )}
    </div>
  );
}

function EditBody({
  inUse,
  open,
  enabled,
  form,
  onChanged,
  done,
  setDone,
}: {
  inUse: GuideVersion;
  open: GuideVersion | null;
  enabled: boolean;
  form: { title: string; starter: boolean } | null;
  onChanged: () => void;
  done: string;
  setDone: (text: string) => void;
}) {
  const canEdit = useCanDecide();
  const shown = open ?? inUse;
  const [questions, setQuestions] = useState<QuestionForm[]>(() => shown.question_set.questions.map(questionForm));
  const [editing, setEditing] = useState<string | null>(null);
  const [text, setText] = useState({ explanation: "", examples: "", question: "" });
  const [reason, setReason] = useState(open?.change_reason ?? "");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const awaiting = open?.state === "AWAITING_APPROVAL";
  const approving = awaiting && !!open?.approval?.may_approve;
  const changes = open ? guideChanges(inUse, open) : [];
  const editable = canEdit && !awaiting;
  const run = async (step: () => Promise<unknown>, success = "") => {
    setBusy(true);
    setError("");
    try {
      await step();
      if (success) setDone(success);
      onChanged();
      return true;
    } catch (reason) {
      setError(errorText(reason, "That was not saved."));
      return false;
    } finally {
      setBusy(false);
    }
  };
  /** Save the questions into the version being prepared, starting one from the version in use when there is none. */
  const saveQuestions = (next: QuestionForm[]) =>
    run(async () => {
      const draft = open ?? (await send<GuideVersion>(`${GUIDES}/${inUse.market}/drafts`, "POST"));
      await send(`${GUIDES}/${inUse.market}/versions/${draft.version}`, "PUT", saveBody(next, draft.test_cases));
      setQuestions(next);
      setEditing(null);
    });
  const start = (question: QuestionForm) => {
    setEditing(question.id || "new");
    setText({ explanation: question.explanation, examples: question.examples, question: question.text });
  };
  const testAndSend = () =>
    run(async () => {
      const tested = await send<GuideVersion>(`${GUIDES}/${open!.market}/versions/${open!.version}/tests`, "POST");
      const failed = (tested.test_results?.results ?? []).filter((result) => !result.passed);
      if (failed.length)
        throw new Error(
          `These worked complaints no longer pass: ${failed.map((result) => result.name).join("; ")}. Change the matrix in Settings › Reportability guides.`,
        );
      await send(`${GUIDES}/${open!.market}/versions/${open!.version}/approval-request`, "POST", {
        change_reason: reason,
      });
    }, `Version ${open?.version} is tested and sent for approval.`);
  const approve = () =>
    run(
      () =>
        send(`${GUIDES}/${open!.market}/versions/${open!.version}/approve`, "POST", {
          password,
          mfa_code: code || null,
        }),
      `Version ${open?.version} is approved and in use. Past answers keep the version they were given under.`,
    );
  const status = open
    ? awaiting
      ? `Version ${open.version} waits for approval · version ${inUse.version} in use`
      : `Your version ${open.version} (draft) · version ${inUse.version} in use`
    : `Version ${inUse.version} in use${inUse.approved_by ? ` · approved by ${inUse.approved_by}` : ""}${
        inUse.published_at && !inUse.starter ? ` on ${formatDay(inUse.published_at)}` : ""
      }`;
  return (
    <div className="dt-rec">
      {approving ? (
        <section className="uw-card dt-tree" aria-label="What changes">
          <div className="dt-tree-head">
            <h2>What changes in version {open!.version}</h2>
            <span className="ac-muted">
              {changes.length} change{changes.length === 1 ? "" : "s"} · read-only
            </span>
          </div>
          <p className="ac-muted dt-locked-note">
            Only what changed. The regulation's text and which answers decide the outcome cannot change.
          </p>
          <ul className="dt-diffs">
            {changes.map((change) => (
              <li key={change.label}>
                <b>{change.label}</b>
                <div className="dt-ba">
                  <div className="dt-before">
                    <small>Before</small>
                    {change.before}
                  </div>
                  <div className="dt-after">
                    <small>After</small>
                    {change.after}
                  </div>
                </div>
              </li>
            ))}
          </ul>
          {open?.change_reason && (
            <p className="dt-hint">
              Why, in {open.requested_by ?? "the preparer"}'s words: {open.change_reason}
            </p>
          )}
        </section>
      ) : (
        <section className="uw-card dt-tree" aria-label="The questions">
          <div className="dt-tree-head">
            <h2>{shown.title}</h2>
            <span className="ac-muted">{status}</span>
          </div>
          <ol className="dt-qs dt-edit">
            {questions.map((question) => (
              <li key={question.id} className={`dt-q${question.extra ? " is-extra" : ""}`}>
                <div className="dt-row">
                  <div className="dt-q-head">
                    <span className="dt-n" aria-hidden="true">
                      {question.extra ? "+" : questionNumber(question.id)}
                    </span>
                    <div className="dt-q-body">
                      <p className="dt-q-text">{question.text}</p>
                      <div className="dt-q-meta">
                        {question.extra ? (
                          <span className="dt-tag">Your extra question · never changes the conclusion</span>
                        ) : (
                          <span className="dt-locked">
                            <Lock size={12} aria-hidden="true" /> The regulation's text, locked · {question.clause}
                          </span>
                        )}
                      </div>
                      {editing !== question.id && !question.extra && (
                        <p className={question.explanation ? "dt-own" : "dt-hint"}>
                          {question.explanation || "No explanation of your own yet."}
                          {question.examples ? ` Examples: ${question.examples}` : ""}
                        </p>
                      )}
                    </div>
                  </div>
                  {editable && editing !== question.id && (
                    <div className="dt-act">
                      <button
                        type="button"
                        className="ac-link dt-pencil"
                        aria-label={`Edit ${question.extra ? "this extra question" : `question ${questionNumber(question.id)}'s explanation`}`}
                        onClick={() => start(question)}
                      >
                        <Pencil size={14} aria-hidden="true" />
                      </button>
                    </div>
                  )}
                </div>
                {editing === question.id && (
                  <div className="dt-editbox">
                    {question.extra ? (
                      <label>
                        The extra question
                        <input
                          value={text.question}
                          onChange={(event) => setText({ ...text, question: event.target.value })}
                        />
                      </label>
                    ) : (
                      <>
                        <label>
                          Your explanation, beside the locked text
                          <textarea
                            rows={2}
                            value={text.explanation}
                            onChange={(event) => setText({ ...text, explanation: event.target.value })}
                          />
                        </label>
                        <label>
                          Your examples
                          <input
                            value={text.examples}
                            onChange={(event) => setText({ ...text, examples: event.target.value })}
                          />
                        </label>
                      </>
                    )}
                    <div className="ca-action-row">
                      <button
                        type="button"
                        className="ac-secondary"
                        disabled={busy}
                        onClick={() =>
                          void saveQuestions(
                            questions.map((other) =>
                              other.id !== question.id
                                ? other
                                : question.extra
                                  ? { ...other, text: text.question }
                                  : { ...other, explanation: text.explanation, examples: text.examples },
                            ),
                          )
                        }
                      >
                        Save
                      </button>
                      {question.extra && (
                        <button
                          type="button"
                          className="ac-link"
                          disabled={busy}
                          onClick={() => void saveQuestions(questions.filter((other) => other.id !== question.id))}
                        >
                          Remove it
                        </button>
                      )}
                      <button type="button" className="ac-link" onClick={() => setEditing(null)}>
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ol>
          {editable &&
            (editing === "new" ? (
              <div className="dt-editbox">
                <label>
                  Your extra question (recorded with the answers; never changes the conclusion)
                  <input
                    value={text.question}
                    onChange={(event) => setText({ ...text, question: event.target.value })}
                  />
                </label>
                <div className="ca-action-row">
                  <button
                    type="button"
                    className="ac-secondary"
                    disabled={busy || collapsed(text.question).length < 5}
                    title={
                      collapsed(text.question).length < 5
                        ? "Write the question first (5 characters or more)"
                        : undefined
                    }
                    onClick={() => void saveQuestions([...questions, { ...NEW_EXTRA, text: text.question }])}
                  >
                    Add it
                  </button>
                  <button type="button" className="ac-link" onClick={() => setEditing(null)}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button type="button" className="ac-link dt-add" onClick={() => start(NEW_EXTRA)}>
                <Plus size={14} aria-hidden="true" /> Add an extra question
              </button>
            ))}
        </section>
      )}
      <aside className="dt-rail" aria-label="This version">
        <section className="uw-card dt-outcome is-open">
          <p className="ac-eyebrow">{approving ? `Approve version ${open!.version}` : "This version"}</p>
          {done ? (
            <p className="dt-success">✓ {done}</p>
          ) : approving ? (
            <form
              className="dt-sign"
              onSubmit={(event) => {
                event.preventDefault();
                if (password && !busy) void approve();
              }}
            >
              <p>
                Prepared by {open!.requested_by ?? open!.editors.join(", ")}. {open!.test_results?.passed ?? 0} of{" "}
                {(open!.test_results?.passed ?? 0) + (open!.test_results?.failed ?? 0)} worked complaints pass. You
                confirm with your password and authenticator code.
              </p>
              {open!.approval?.same_person && <p className="ac-message tone-warning">{open!.approval.message}</p>}
              <div className="dt-creds">
                <input
                  type="password"
                  aria-label="Your password"
                  placeholder="Your password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <input
                  inputMode="numeric"
                  aria-label="Authenticator code"
                  placeholder="Authenticator code"
                  autoComplete="one-time-code"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                />
              </div>
              <button
                type="submit"
                className="ac-primary dt-sign-btn"
                disabled={!password || busy}
                title={!password ? "Enter your password first" : undefined}
              >
                <ShieldCheck size={15} aria-hidden="true" /> Approve version {open!.version}
              </button>
            </form>
          ) : (
            <>
              <p className="dt-big dt-big-sm">{status}</p>
              {awaiting ? (
                <p className="ac-muted">
                  {open!.approval?.message ?? "A colleague approves it with their password and authenticator code."}
                </p>
              ) : open && canEdit ? (
                <>
                  <label className="dt-why">
                    <span>What changed and why</span>
                    <input value={reason} onChange={(event) => setReason(event.target.value)} />
                  </label>
                  <button
                    type="button"
                    className="ac-primary dt-sign-btn"
                    disabled={busy || collapsed(reason).length < REASON_MIN || !changes.length}
                    title={
                      !changes.length
                        ? "Change a question first"
                        : collapsed(reason).length < REASON_MIN
                          ? `Give the reason for the change (${REASON_MIN} characters or more)`
                          : undefined
                    }
                    onClick={() => void testAndSend()}
                  >
                    {busy ? "Testing…" : "Test against the worked complaints and send for approval"}
                  </button>
                </>
              ) : (
                <p className="ac-muted">
                  {canEdit
                    ? "Edit a question's explanation with its pencil, or add an extra question."
                    : "Your role reads this tree."}
                </p>
              )}
            </>
          )}
          <InlineError text={error} />
        </section>
        <section className="uw-card uw-card-pad dt-form">
          <h2>Tested before use</h2>
          <p>
            <b>
              {inUse.test_results?.passed ?? 0} of{" "}
              {(inUse.test_results?.passed ?? 0) + (inUse.test_results?.failed ?? 0)} worked complaints pass
            </b>
          </p>
          {form && <p className="ac-muted">A reportable outcome creates the {formName(form.title)}.</p>}
          {!enabled && (
            <p className="ac-muted">Not in your reporting windows: add this market there to assess complaints.</p>
          )}
          <p className="dt-hint">
            The regulation's text and which answers decide the outcome cannot change. Past answers keep the version they
            were given under.
          </p>
        </section>
        {(shown.starter || shown.question_set.questions.some((question) => question.starter) || form?.starter) && (
          <StarterNote />
        )}
      </aside>
    </div>
  );
}
