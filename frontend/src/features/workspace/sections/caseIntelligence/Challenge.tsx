/** B5a: the investigation challenge (Part of CaseIntelligence.tsx) and the brief's Challenge and Sources sections. */
import { useState } from "react";
import { Empty, Panel, ToneBadge } from "../../../admin/console/charts";
import { Drawer, formatDate, useResource } from "../../../customer-admin/shared";
import { useCan } from "../../workspaceContext";
import {
  ANSWER_MAX,
  SIDES,
  actionable,
  adoptBody,
  answerLine,
  answerProblem,
  blockingQuestions,
  briefChallenge,
  challengePath,
  draftHeading,
  draftState,
  originLabel,
  questionHeading,
  reasonProblem,
  recordSource,
  type ChallengeDraft,
  type ChallengeFact,
  type ChallengeQuestion,
  type ChallengeRecord,
  type ChallengeView as ChallengeData,
} from "../../challenge";
import { SourceLink } from "../Documents";
import { DrawerActions, DrawerError, Problem, ReasonField, useSend } from "./shared";

function Records({ records, caseId }: { records: ChallengeRecord[]; caseId: string }) {
  if (!records.length) return null;
  return (
    <span className="uw-doc-sources">
      {records.slice(0, 12).map((record) => (
        <SourceLink key={`${record.type}-${record.id}`} source={recordSource(record, caseId)} />
      ))}
      {records.length > 12 && <small className="ac-muted"> and {records.length - 12} more</small>}
    </span>
  );
}

function Facts({
  title,
  facts,
  caseId,
  empty,
}: {
  title: string;
  facts: ChallengeFact[];
  caseId: string;
  empty: string;
}) {
  return (
    <section className="uw-related" aria-label={title}>
      <h4>
        {title} <span className="ac-tab-count">{facts.length}</span>
      </h4>
      {facts.length ? (
        <ul className="uw-intel-list">
          {facts.map((fact, index) => (
            <li key={index}>
              {fact.text} <Records records={fact.records} caseId={caseId} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="ac-muted">{empty}</p>
      )}
    </section>
  );
}

export function ChallengeView({
  investigationId,
  caseLabel,
  readOnly,
}: {
  investigationId: string;
  caseLabel: string;
  readOnly: boolean;
}) {
  const resource = useResource<ChallengeData>(challengePath(investigationId));
  const canWork = useCan("investigation.work") && !readOnly;
  const [adopting, setAdopting] = useState<ChallengeDraft | null>(null);
  const [dismissing, setDismissing] = useState<ChallengeDraft | null>(null);
  const [answering, setAnswering] = useState<{ item: ChallengeQuestion; notApplicable: boolean } | null>(null);
  const view = resource.data;
  const done = () => {
    setAdopting(null);
    setDismissing(null);
    setAnswering(null);
    resource.reload();
  };
  const blocking = view ? blockingQuestions(view) : [];
  const editable = canWork && view?.answers_editable === true;
  return (
    <Panel eyebrow={caseLabel} title="Challenge" source={resource}>
      <p className="ac-note">
        {view?.notice ??
          "Drafted by rule from your records. Drafts are explanations to test, not findings; you decide."}{" "}
        Drafts are listed in rule order, never ranked.
      </p>
      {view?.summary && (
        <p className="ac-muted">
          Read from {view.summary.complaints} complaints in scope ({view.summary.no_version} without a version,{" "}
          {view.summary.no_lot} without a lot), {view.summary.changes} changes and {view.summary.outside} same-problem
          complaints outside the scope.
        </p>
      )}
      {blocking.length > 0 && (
        <div className="uw-hint tone-warning" role="note" aria-label="Blocking Submit for review">
          <strong>
            Before Submit for review: {blocking.length} material question{blocking.length === 1 ? "" : "s"} to answer or
            mark not applicable.
          </strong>
          <ul>
            {blocking.map((item) => (
              <li key={item.key}>
                {item.rule}: {item.text}
              </li>
            ))}
          </ul>
        </div>
      )}
      <h3>Drafts</h3>
      {view && view.drafts.length ? (
        <ul className="uw-intel-list">
          {view.drafts.map((draft) => {
            const state = draftState(draft.action);
            return (
              <li key={draft.key} className="uw-intel-card">
                <header>
                  <ToneBadge tone="neutral" label={draftHeading(draft)} />
                  {draft.rule !== "H-0" && <ToneBadge tone={state.tone} label={state.label} />}
                </header>
                <p>
                  <strong>{draft.title}</strong>
                </p>
                <p className="uw-intel-statement">{draft.statement}</p>
                {draft.duplicate_of && <p className="uw-hint">You may already have this: {draft.duplicate_of}</p>}
                {draft.action?.state === "DISMISSED" && draft.action.reason && (
                  <p className="uw-intel-reason">Dismissed: {draft.action.reason}</p>
                )}
                <div className="uw-intel-board">
                  {draft.rule !== "H-0" && (
                    <>
                      <Facts title="Records for" facts={draft.for} caseId={investigationId} empty="None found." />
                      <Facts
                        title="Records against"
                        facts={draft.against}
                        caseId={investigationId}
                        empty="None found."
                      />
                    </>
                  )}
                  <Facts title="Missing" facts={draft.missing} caseId={investigationId} empty="Nothing missing." />
                </div>
                {canWork && actionable(draft) && (
                  <div className="ca-action-row">
                    <button type="button" className="ac-primary" onClick={() => setAdopting(draft)}>
                      Adopt as a hypothesis
                    </button>
                    {draft.action?.state !== "DISMISSED" && (
                      <button type="button" className="ac-secondary" onClick={() => setDismissing(draft)}>
                        Dismiss
                      </button>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <Empty title="No drafts" detail="No rule finds an explanation to test in this investigation's records." />
      )}
      <h3>Questions</h3>
      {view && view.questions.length ? (
        <ul className="uw-intel-list">
          {view.questions.map((item) => (
            <li key={item.key} className="uw-intel-card">
              <header>
                <ToneBadge tone="neutral" label={questionHeading(item)} />
                {item.material ? (
                  <ToneBadge
                    tone={item.answer ? "good" : "critical"}
                    label={item.answer ? "Material · answered" : "Material · blocks Submit for review"}
                  />
                ) : (
                  <ToneBadge tone="warning" label="Warning" />
                )}
              </header>
              <p>{item.text}</p>
              <Records records={item.records ?? []} caseId={investigationId} />
              <p className={item.answer ? "uw-intel-reason" : "ac-muted"}>
                {answerLine(item.answer)}
                {item.answer?.answered_at ? ` · ${formatDate(item.answer.answered_at)}` : ""}
              </p>
              {editable && (
                <div className="ca-action-row">
                  <button
                    type="button"
                    className="ac-secondary"
                    onClick={() => setAnswering({ item, notApplicable: false })}
                  >
                    {item.answer ? "Change the answer" : "Answer"}
                  </button>
                  <button type="button" className="ac-link" onClick={() => setAnswering({ item, notApplicable: true })}>
                    Not applicable
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <Empty title="No questions" detail="The rules ask nothing of this investigation's records now." />
      )}
      {canWork && view && view.questions.length > 0 && !view.answers_editable && (
        <p className="uw-hint">
          Answers are kept in the brief draft, so the decision maker's signature covers them: compose the Decision Brief
          (or open its new draft) to answer.
        </p>
      )}
      {adopting && (
        <AdoptDrawer
          investigationId={investigationId}
          draft={adopting}
          onClose={() => setAdopting(null)}
          onDone={done}
        />
      )}
      {dismissing && (
        <DismissDrawer
          investigationId={investigationId}
          draft={dismissing}
          onClose={() => setDismissing(null)}
          onDone={done}
        />
      )}
      {answering && (
        <AnswerDrawer
          investigationId={investigationId}
          item={answering.item}
          notApplicable={answering.notApplicable}
          onClose={() => setAnswering(null)}
          onDone={done}
        />
      )}
    </Panel>
  );
}

function AdoptDrawer({
  investigationId,
  draft,
  onClose,
  onDone,
}: {
  investigationId: string;
  draft: ChallengeDraft;
  onClose: () => void;
  onDone: () => void;
}) {
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const { busy, error, run } = useSend(onDone);
  const toggle = (key: string) =>
    setTicked((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  return (
    <Drawer title={`Adopt ${draft.rule} as a hypothesis`} onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void run(
            challengePath(investigationId, "drafts/adopt"),
            adoptBody(draft.key, ticked),
            "Adopted as a hypothesis you propose.",
            "The draft was not adopted.",
          );
        }}
      >
        <p className="uw-intel-statement">{draft.statement}</p>
        <p className="ac-muted">
          It becomes a hypothesis you propose, marked "{draftHeading(draft)}, adopted". Tick the facts to keep as record
          summaries: each becomes unreviewed evidence linked for or against it, reviewed like any evidence.
        </p>
        {SIDES.map((side) =>
          draft[side].length ? (
            <fieldset key={side} className="ca-field">
              <legend>{side === "for" ? "Records for" : "Records against"}</legend>
              {draft[side].map((fact, index) => (
                <label key={index} className="ca-check">
                  <input
                    type="checkbox"
                    checked={ticked.has(`${side}:${index}`)}
                    onChange={() => toggle(`${side}:${index}`)}
                  />
                  {fact.text}
                </label>
              ))}
            </fieldset>
          ) : null,
        )}
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={false} label="Adopt" />
      </form>
    </Drawer>
  );
}

function DismissDrawer({
  investigationId,
  draft,
  onClose,
  onDone,
}: {
  investigationId: string;
  draft: ChallengeDraft;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);
  const { busy, error, run } = useSend(onDone);
  const problem = reasonProblem(reason);
  return (
    <Drawer title={`Dismiss ${draft.rule}`} onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setTouched(true);
          if (problem) return;
          void run(
            challengePath(investigationId, "drafts/dismiss"),
            { key: draft.key, reason: reason.trim() },
            "Draft dismissed; the reason is kept.",
            "The draft was not dismissed.",
          );
        }}
      >
        <p className="uw-intel-statement">{draft.statement}</p>
        <ReasonField label="Why the records speak against it" value={reason} onChange={setReason} />
        <Problem problem={problem} touched={touched} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={false} label="Dismiss" />
      </form>
    </Drawer>
  );
}

function AnswerDrawer({
  investigationId,
  item,
  notApplicable,
  onClose,
  onDone,
}: {
  investigationId: string;
  item: ChallengeQuestion;
  notApplicable: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const [text, setText] = useState(item.answer?.text ?? "");
  const [touched, setTouched] = useState(false);
  const { busy, error, run } = useSend(onDone);
  const problem = answerProblem(text);
  return (
    <Drawer title={notApplicable ? `Not applicable: ${item.rule}` : `Answer ${item.rule}`} onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setTouched(true);
          if (problem) return;
          void run(
            challengePath(investigationId, "questions/answer"),
            { key: item.key, text: text.trim(), not_applicable: notApplicable },
            "Answer kept in the brief draft.",
            "The answer was not kept.",
          );
        }}
      >
        <p>{item.text}</p>
        <label className="ca-field">
          {notApplicable ? "Why it does not apply" : "Your answer"}
          <textarea
            rows={5}
            maxLength={ANSWER_MAX}
            value={text}
            placeholder="At least 10 characters"
            onChange={(event) => setText(event.target.value)}
          />
        </label>
        <Problem problem={problem} touched={touched} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={false} label="Keep the answer" />
      </form>
    </Drawer>
  );
}

/** The brief's Challenge and Sources sections (none for a brief composed before B5). */
export function BriefChallengeSections({ content, caseId }: { content: Record<string, any>; caseId: string }) {
  const found = briefChallenge(content);
  if (!found) return null;
  return (
    <>
      <section className="uw-related" aria-label="Challenge">
        <h3>
          Challenge <span className="ac-tab-count">{found.drafts.length + found.questions.length}</span>
        </h3>
        {found.notice && <p className="ac-muted">{found.notice}</p>}
        <ul className="uw-intel-list">
          {found.drafts.map((draft) => (
            <li key={draft.key}>
              <strong>{draftHeading(draft)} · </strong>
              {draft.statement} <small className="ac-muted">· {draftState(draft.action).label}</small>
              {draft.action?.state === "DISMISSED" && draft.action.reason && (
                <small className="ac-muted"> ({draft.action.reason})</small>
              )}
            </li>
          ))}
          {found.questions.map((item) => (
            <li key={item.key}>
              <strong>
                {questionHeading(item)}
                {item.material ? ", material" : ""} ·{" "}
              </strong>
              {item.text} <span className="uw-intel-reason">{answerLine(item.answer)}</span>
            </li>
          ))}
        </ul>
        {!found.drafts.length && !found.questions.length && (
          <p className="ac-muted">No draft or question followed from the records.</p>
        )}
      </section>
      {found.sources && (
        <section className="uw-related" aria-label="Sources">
          <details>
            <summary>
              <strong>Sources</strong> · {found.sources.summary}
            </summary>
            {found.groups.map((group) => (
              <div key={group.name}>
                <h4>
                  {group.label} <span className="ac-tab-count">{group.count}</span>
                </h4>
                <p className="uw-doc-sources">
                  {group.items.map((item) => (
                    <SourceLink
                      key={item.id}
                      source={recordSource({ type: group.kind, id: item.id, ref: item.ref }, caseId)}
                    />
                  ))}
                  <small className="ac-muted">
                    {" "}
                    · {[...new Set(group.items.map((item) => originLabel(item.origin)))].join(", ")}
                  </small>
                </p>
              </div>
            ))}
            <p className="ac-muted">
              Rules: {found.sources.rules.map((rule) => `${rule.rule} v${rule.version} ${rule.name}`).join("; ")}
              {found.sources.as_of ? ` · records as of ${formatDate(found.sources.as_of)}` : ""}
            </p>
          </details>
        </section>
      )}
    </>
  );
}
