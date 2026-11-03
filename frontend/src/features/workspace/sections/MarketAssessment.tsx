import { useContext, useId, useState } from "react";
import { AlsoKnownAs, DecideAndSign } from "./common";
import { ComplaintNextStep } from "./ComplaintNextStep";
import { MARKET_QUESTION_WHY } from "../whyAsked";
import { marketLabel, questionNumber, versionWords } from "../../../app/labels";
import { BookOpenCheck, FileWarning, Gauge, PenLine, Save, ShieldCheck } from "lucide-react";
import { ToneBadge } from "../../admin/console/charts";
import { ReportingFacts } from "./ReportingFacts";
import { Drawer, Tabs, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { deadlineLabel, formatDay } from "../../../app/dates";
import { WorkspaceContext, useCan, useWorkspace } from "../workspaceContext";
import { reportsTab, worksheetMarkets } from "../authorityReports";
import { communicationsTab } from "../communications";
import { recordName } from "../complaintReview";
import { clockText } from "../reportability";
import {
  ANSWERS,
  ANSWER_LABELS,
  ASSESSMENT_LIMITS,
  CONCLUSION_LABELS,
  EMPTY_SIGN,
  MARKET_SHORT,
  assessmentPath,
  draftBody,
  formOf,
  lowered,
  signProblem,
  trainingMissing,
  type AnswerEntry,
  type AssessmentDetail,
  type AssessmentForm,
  type Market,
  type MarketItem,
  type Question,
  type Scale,
  type SignForm,
  type Suggestion_,
  type TrainingDocument,
  type Version,
} from "../marketAssessment";
import { InlineError } from "./boardParts";
import { WhyAsked, BasisChips } from "../../shared/Basis";
import { STARTER_LABEL, isStarterVersion } from "../../shared/standards";

/** Whether the signed-in role may save and sign an assessment (regulatory review or approval: the server's rule). */
function useCanAssess() {
  const review = useCan("regulatory.review");
  const approve = useCan("regulatory.approve");
  return review || approve;
}

/** The complaint fields an answer can cite as the evidence it relied on. */
const EVIDENCE = ["Complaint description", "Severity (quality system)", "Patient outcome fields", "Malfunction field"];

/**
 * Complaints › Reportability › Assess per market: each enabled market's starter questions with the clause beside each,
 * the harm-severity scale, the suggestion, and the person's signed conclusion (password and authenticator code, after a
 * practice training acknowledgement on the current version of the questions and the scale, in a free trial only).
 */
export function MarketAssessmentDrawer({
  complaint,
  onClose,
  onChanged,
}: {
  complaint: { id: string; business_id: string | null; complaint_identifier: string | null };
  onClose: () => void;
  onChanged: () => void;
}) {
  const { story } = useWorkspace();
  const detail = useResource<AssessmentDetail>(assessmentPath(complaint.id));
  const data = detail.data;
  const shown = data?.markets ?? [];
  const [market, setMarket] = useState<Market | null>(null);
  const active = shown.find((item) => item.market === market) ?? shown.find((item) => item.preselected) ?? shown[0];
  const labels = shown.map((item) => MARKET_SHORT[item.market]);
  const reload = () => {
    detail.reload();
    onChanged();
  };
  return (
    <Drawer title={`${recordName(complaint)}: assess per market`} onClose={onClose}>
      {detail.state === "error" && <InlineError text="The assessment could not be read." />}
      {data && <AssessmentIntro detail={data} />}
      {data && <ReportingFacts complaintId={complaint.id} needs={data.complaint.needs} onSaved={reload} />}
      {data && !shown.length && (
        <p className="uw-hint">
          No market is enabled: enter your reporting windows (Complaints › Reporting windows) for the markets you report
          to.
        </p>
      )}
      {data && active && (
        <Tabs
          tabs={labels}
          active={MARKET_SHORT[active.market]}
          label="Markets"
          onChange={(label) => setMarket(shown.find((item) => MARKET_SHORT[item.market] === label)?.market ?? null)}
        >
          <MarketPanel key={active.market} detail={data} item={active} onSaved={reload} />
        </Tabs>
      )}
      {data && active && (
        <ComplaintNextStep
          complaintId={complaint.id}
          here="Reportability"
          pending={!active.current}
          refreshKey={shown.map((item) => `${item.current?.version ?? 0}.${item.draft?.version ?? 0}`).join()}
          first={
            alsoIndia(story, shown, active) ? { label: "Assess India (CDSCO) too", run: () => setMarket("IN") } : null
          }
        />
      )}
    </Drawer>
  );
}

function AssessmentIntro({ detail }: { detail: AssessmentDetail }) {
  const legacy = detail.legacy_decision;
  return (
    <section className="ca-drawer-section uw-ma-intro">
      <p>
        {detail.complaint.product_name ?? "No product"}
        {detail.complaint.version ? ` · ${detail.complaint.version}` : ""} ·{" "}
        {detail.complaint.country ?? "Country not recorded"}
        {detail.complaint.aware_date ? ` · aware ${formatDay(detail.complaint.aware_date)}` : ""}
      </p>
      {detail.complaint.description && <q className="uw-cr-text">{detail.complaint.description}</q>}
      <AlsoKnownAs id={detail.complaint.business_id} shown={recordName(detail.complaint)} />
      {/* Only on starter content: an approved guide of the organization is not marked (usability U-11). */}
      {detail.markets.some((item) => isStarterVersion(item.question_set.version)) && (
        <p className="uw-ma-starter" role="note">
          <FileWarning size={15} aria-hidden="true" /> {detail.starter_mark}
        </p>
      )}
      {legacy && (
        <div className="uw-cr-decision">
          <ToneBadge tone="neutral" label={legacy.note} />
          <span className="uw-cr-meta">
            {legacy.decision === "REPORTED"
              ? `Reported${legacy.report_reference ? ` · ${legacy.report_reference}` : ""}`
              : "Not reportable"}{" "}
            · {legacy.decided_by} · {formatDate(legacy.decided_at)}
          </span>
          <q>{legacy.rationale}</q>
        </div>
      )}
      <p className="ac-muted">
        Add any enabled market where your procedure says this event must be assessed. MDARIX does not submit reports. An
        Unknown answer raises a request to the reporter in the complaint's communications log.
      </p>
      <CommunicationsLink complaintId={detail.complaint.id} />
    </section>
  );
}

function CommunicationsLink({ complaintId }: { complaintId: string }) {
  const workspace = useContext(WorkspaceContext);
  if (!workspace) return null;
  return (
    <button
      type="button"
      className="ac-link"
      onClick={() => workspace.open("Complaints", communicationsTab(complaintId))}
    >
      Open the communications log
    </button>
  );
}

/** One market: its signed conclusion, the training, the scale, the questions and the signature (exported for tests). */
export function MarketPanel({
  detail,
  item,
  onSaved,
}: {
  detail: AssessmentDetail;
  item: MarketItem;
  onSaved: () => void;
}) {
  const canDecide = useCanAssess();
  const { notify } = useWorkspace();
  const [form, setForm] = useState<AssessmentForm>(() => formOf(item, detail.severity_level));
  const [sign, setSign] = useState<SignForm>(EMPTY_SIGN);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const name = recordName(detail.complaint);
  const suggested = item.evaluation?.suggested ?? null;
  // The conclusion is never pre-selected (0.10.72, B1): the person chooses it; the suggestion is marked beside it.
  const [rereading, setRereading] = useState(false);
  const missing = trainingMissing(item);
  const questions = item.question_set.questions;
  const problem = signProblem(
    questions,
    form,
    sign,
    suggested,
    item.disagreement,
    !detail.training_required || !missing.length,
  );
  const run = async (step: () => Promise<unknown>, done: string, failed: string) => {
    setBusy(true);
    setError("");
    try {
      await step();
      notify(done);
      onSaved();
      return true;
    } catch (failure) {
      setError(errorText(failure, failed));
      return false;
    } finally {
      setBusy(false);
    }
  };
  const save = () =>
    run(
      () => send(assessmentPath(detail.complaint.id, item.market), "PUT", draftBody(form)),
      `${name}: ${item.label} answers saved.`,
      "The answers were not saved.",
    );
  const signNow = () =>
    run(
      async () => {
        const saved = await send<AssessmentDetail>(
          assessmentPath(detail.complaint.id, item.market),
          "PUT",
          draftBody(form),
        );
        const draft = saved.markets.find((entry) => entry.market === item.market)?.draft;
        if (!draft) throw new Error("The answers were not saved.");
        await send(assessmentPath(detail.complaint.id, item.market, "/sign"), "POST", {
          conclusion: sign.conclusion,
          override_reason: sign.overrideReason,
          version: draft.version,
          saved_at: draft.saved_at,
          password: sign.password,
          mfa_code: sign.code || null,
        });
      },
      `${name}: the ${item.label} conclusion is signed.`,
      "The conclusion was not signed.",
    ).then((signed) => signed && setSign(EMPTY_SIGN));
  return (
    <div className="uw-ma-market">
      <header className="uw-ma-head">
        <h3>{item.question_set.title}</h3>
        <span className="uw-cr-meta">
          Guide: {versionWords(item.question_set.version)} · scale: {versionWords(detail.scale.version)}
          {item.preselected ? " · the event's market" : ""}
          {item.question_set_current === false ? " · started before your current guide version: it keeps this one" : ""}
        </span>
        {!item.preselected && detail.markets.some((other) => other.preselected) && <WhyAssessed />}
        {item.clock && (
          <span
            className={`uw-rw-clock tone-${item.clock.state === "OVERDUE" ? "critical" : item.clock.state === "DUE_SOON" ? "warning" : "neutral"}`}
          >
            <strong>{clockText(item.clock)}</strong> · due {deadlineLabel(item.clock)} · {item.clock.window}
          </span>
        )}
      </header>
      {item.current && <SignedVersion version={item.current} complaintId={detail.complaint.id} onSaved={onSaved} />}
      {canDecide && !missing.length && item.training.length > 0 && !rereading && (
        <p className="uw-cr-meta uw-ma-read">
          You have read: {item.training.map((document) => readWords(document, item.market)).join(", ")} ·{" "}
          <button type="button" className="ac-link" onClick={() => setRereading(true)}>
            Read again
          </button>
        </p>
      )}
      {(missing.length > 0 || rereading) && canDecide && (
        <TrainingPanel
          documents={missing.length ? missing : item.training}
          colleagues={item.trained_colleagues}
          required={detail.training_required}
          onDone={onSaved}
        />
      )}
      <ScalePanel
        scale={detail.scale}
        item={item}
        severity={detail.severity}
        severityLevel={detail.severity_level}
        severitySource={detail.severity_source}
        form={form}
        setForm={setForm}
      />
      {item.question_set.note && <p className="uw-hint">{item.question_set.note}</p>}
      <ol className="uw-ma-questions">
        {questions.map((question) => (
          <QuestionRow
            key={question.id}
            question={question}
            version={item.question_set.version}
            entry={form.answers[question.id]}
            suggestion={item.suggestions?.[question.id]}
            disabled={!canDecide}
            onChange={(entry) => setForm({ ...form, answers: { ...form.answers, [question.id]: entry } })}
          />
        ))}
      </ol>
      {item.evaluation && (
        <section className="ca-drawer-section uw-ma-suggestion" aria-label="Suggested conclusion">
          <h3>
            Suggested: {CONCLUSION_LABELS[item.evaluation.suggested]}
            {item.draft?.report_type_label ? ` · ${item.draft.report_type_label}` : ""}
          </h3>
          <p className="ac-muted">
            From the answers as last saved. The suggestion never signs: you confirm or override it.
          </p>
          {item.evaluation.notes.map((note) => (
            <p key={note} className="uw-hint">
              {note}
            </p>
          ))}
        </section>
      )}
      {item.disagreement && (
        <label className="ca-field">
          {item.disagreement}: your written reason (shown on the signed record and listed on Readiness)
          <textarea
            rows={2}
            maxLength={ASSESSMENT_LIMITS.rationaleMax}
            value={form.disagreementReason}
            onChange={(event) => setForm({ ...form, disagreementReason: event.target.value })}
          />
        </label>
      )}
      {canDecide && (
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" disabled={busy} onClick={() => void save()}>
            <Save size={15} aria-hidden="true" /> {busy ? "Saving…" : "Save answers"}
          </button>
        </div>
      )}
      {canDecide && item.draft && (
        <form
          className="ca-form ca-drawer-section"
          onSubmit={(event) => {
            event.preventDefault();
            if (!problem && !busy) void signNow();
          }}
        >
          <h3>
            <PenLine size={16} aria-hidden="true" /> Sign the {item.label} conclusion
          </h3>
          <fieldset className="ca-field uw-rw-choice">
            <legend>Conclusion</legend>
            {(["REPORTABLE", "NOT_REPORTABLE"] as const).map((value) => (
              <label key={value} className="ca-check">
                <input
                  type="radio"
                  name={`conclusion-${item.market}`}
                  checked={sign.conclusion === value}
                  onChange={() => setSign({ ...sign, conclusion: value })}
                />
                {CONCLUSION_LABELS[value]}
                {suggested === value ? " (the suggestion)" : ""}
              </label>
            ))}
          </fieldset>
          {sign.conclusion && sign.conclusion !== suggested && (
            <label className="ca-field">
              Why you override the suggestion
              <textarea
                rows={2}
                value={sign.overrideReason}
                onChange={(event) => setSign({ ...sign, overrideReason: event.target.value })}
              />
            </label>
          )}
          <div className="ca-form-grid">
            <DecideAndSign
              signs={`${item.label}: ${sign.conclusion ? CONCLUSION_LABELS[sign.conclusion].toLowerCase() : "your conclusion"} for ${
                detail.complaint.complaint_identifier ?? detail.complaint.business_id ?? "this complaint"
              }${sign.conclusion === "REPORTABLE" && item.draft.report_type_label ? `, ${item.draft.report_type_label}` : ""}.`}
              restsOn={[
                `Your answers to ${Object.values(item.draft.answers).filter((entry) => entry.answer).length} of ${questions.length} questions, saved as draft version ${item.draft.version}.`,
                originWords(item.draft.answers),
                `${item.question_set.title} (${versionWords(item.draft.question_set)}), its clauses locked.`,
                item.draft.harm_level
                  ? `Harm level ${item.draft.harm_level.toLowerCase()} on the harm-severity scale.`
                  : null,
                item.clock ? `The ${item.label} clock: due ${deadlineLabel(item.clock)}.` : null,
              ]}
            />
            <label className="ca-field">
              Your password
              <input
                type="password"
                autoComplete="current-password"
                value={sign.password}
                onChange={(event) => setSign({ ...sign, password: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Authenticator code
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                value={sign.code}
                onChange={(event) => setSign({ ...sign, code: event.target.value })}
              />
            </label>
          </div>
          {problem && <p className="uw-hint">{problem}</p>}
          <p className="ac-muted">
            Your signature covers every answer with its rationale and evidence, the harm level and the scale (
            {versionWords(detail.scale.version)}), and the question set ({versionWords(item.question_set.version)}). A
            change later is a new version.
          </p>
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy || !!problem}>
              {busy ? "Signing…" : "Save and sign"}
            </button>
          </div>
        </form>
      )}
      <InlineError text={error} />
      {item.history.length > 0 && (
        <details className="uw-ma-history">
          <summary>Earlier versions ({item.history.length})</summary>
          <ul>
            {item.history.map((version) => (
              <li key={version.id}>
                Version {version.version}: {version.conclusion ? CONCLUSION_LABELS[version.conclusion] : "draft"} ·{" "}
                {version.signed_by ?? version.created_by} · {formatDate(version.signed_at ?? version.saved_at)}
                {version.superseded ? " · superseded" : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function QuestionRow({
  question,
  version,
  entry,
  suggestion,
  disabled,
  onChange,
}: {
  question: Question;
  version: string;
  entry: AnswerEntry | undefined;
  suggestion?: Suggestion_;
  disabled: boolean;
  onChange: (entry: AnswerEntry) => void;
}) {
  const value = entry ?? { answer: null, rationale: "", evidence: [] };
  const [open, setOpen] = useState(false);
  const [evidence, setEvidence] = useState(false);
  // A suggestion from the record waits for Confirm, or the person corrects it with the answers below.
  const [correcting, setCorrecting] = useState(false);
  const definitionId = useId();
  const evidenceId = useId();
  const waiting = !!suggestion && !value.answer && !correcting;
  const confirmed =
    !!suggestion && value.answer === suggestion.answer && (!!value.confirmed || value.origin === "CONFIRMED");
  return (
    <li className="uw-ma-question">
      {/* Not a disabled fieldset: the definition toggle stays usable when the answers are read-only. */}
      <fieldset className="ca-field">
        <legend>
          <strong>{questionNumber(question.id)}.</strong> {question.text}
        </legend>
        <p className="uw-ma-clause">
          <span className="uw-basis-chip">{question.clause}</span> <BasisChips ids={question.basis} label="Basis" />
          {question.extra ? (
            <span className="uw-ma-starter-chip">Your extra question: optional, never changes the suggestion</span>
          ) : question.starter && isStarterVersion(version) ? (
            <span className="uw-ma-starter-chip">{STARTER_LABEL}</span>
          ) : question.starter ? null : (
            <span className="uw-ma-starter-chip">Your wording</span>
          )}
          <button
            type="button"
            className="ac-link uw-ma-definition-toggle"
            aria-expanded={open}
            aria-controls={definitionId}
            onClick={() => setOpen(!open)}
          >
            {open ? "Hide definition" : "Show definition"}
          </button>
        </p>
        <div id={definitionId} hidden={!open}>
          <p className="ac-muted">{question.definition}</p>
          <WhyAsked why={{ why: question.note || MARKET_QUESTION_WHY, basis: [] }} clause={question.clause} />
          <OwnText question={question} />
        </div>
        {suggestion && (waiting || confirmed) ? (
          <div
            className="uw-ma-suggested"
            role="group"
            aria-label={`Question ${questionNumber(question.id)}: from the record`}
          >
            <p>
              <strong>
                {confirmed ? "Confirmed" : "Suggested"}: {ANSWER_LABELS[suggestion.answer]}
              </strong>{" "}
              · {suggestion.source}
            </p>
            {!disabled && (
              <div className="ca-action-row">
                {waiting && (
                  <button
                    type="button"
                    className="ac-secondary"
                    onClick={() =>
                      onChange({
                        answer: suggestion.answer,
                        rationale: suggestion.source,
                        evidence: [suggestion.evidence],
                        confirmed: true,
                      })
                    }
                  >
                    Confirm
                  </button>
                )}
                <button
                  type="button"
                  className="ac-link"
                  onClick={() => {
                    setCorrecting(true);
                    if (confirmed) onChange({ answer: null, rationale: "", evidence: [] });
                  }}
                >
                  Correct it
                </button>
              </div>
            )}
          </div>
        ) : (
          <>
            {suggestion && (
              <p className="uw-cr-meta">
                The record suggested {ANSWER_LABELS[suggestion.answer]} · {suggestion.source}
              </p>
            )}
            <div
              className="uw-ma-answers"
              role="radiogroup"
              aria-label={`Answer to question ${questionNumber(question.id)}`}
            >
              {ANSWERS.map((answer) => (
                <label key={answer} className="ca-check">
                  <input
                    type="radio"
                    disabled={disabled}
                    name={`answer-${question.id}`}
                    checked={value.answer === answer}
                    onChange={() => onChange({ ...value, answer, confirmed: false })}
                  />
                  {ANSWER_LABELS[answer]}
                </label>
              ))}
            </div>
            <label className="ca-field">
              Rationale
              <textarea
                rows={2}
                disabled={disabled}
                maxLength={ASSESSMENT_LIMITS.rationaleMax}
                value={value.rationale}
                onChange={(event) => onChange({ ...value, rationale: event.target.value })}
              />
            </label>
            <button
              type="button"
              className="ac-link"
              aria-expanded={evidence}
              aria-controls={evidenceId}
              onClick={() => setEvidence(!evidence)}
            >
              {evidence
                ? "Hide evidence"
                : `Show evidence${value.evidence.length ? ` (${value.evidence.length})` : ""}`}
            </button>
            <div id={evidenceId} className="uw-ma-evidence" aria-label="Evidence relied on" hidden={!evidence}>
              {EVIDENCE.map((item) => (
                <label key={item} className="ca-check">
                  <input
                    type="checkbox"
                    disabled={disabled}
                    checked={value.evidence.includes(item)}
                    onChange={(event) =>
                      onChange({
                        ...value,
                        evidence: event.target.checked
                          ? [...value.evidence, item]
                          : value.evidence.filter((other) => other !== item),
                      })
                    }
                  />
                  {item}
                </label>
              ))}
            </div>
          </>
        )}
      </fieldset>
    </li>
  );
}

/** "US guide v2", "harm scale v1": what a person has read, in one line (0.10.72, B1). */
export function readWords(document: Pick<TrainingDocument, "code" | "version">, market: Market): string {
  const number = /(\d+)$/.exec(document.version)?.[1] ?? document.version;
  return document.code === "HARM_SCALE" ? `harm scale v${number}` : `${MARKET_SHORT[market]} guide v${number}`;
}

/** How the answers came: "Answers: 5 confirmed from the complaint record, 3 entered." (0.10.72, B1). */
export function originWords(answers: Record<string, AnswerEntry>): string | null {
  const count = (origin: string) => Object.values(answers).filter((entry) => entry.origin === origin).length;
  const parts = [
    count("CONFIRMED") && `${count("CONFIRMED")} confirmed from the complaint record`,
    count("CORRECTED") && `${count("CORRECTED")} corrected from the record's suggestion`,
    count("ENTERED") && `${count("ENTERED")} entered`,
  ].filter(Boolean);
  return parts.length ? `Answers: ${parts.join(", ")}.` : null;
}

/** The harm-severity scale beside the questions: levels, Annex F terms, each market's threshold, the mapped level. */
export function ScalePanel({
  scale,
  item,
  severity,
  severityLevel,
  severitySource,
  form,
  setForm,
}: {
  scale: Scale;
  item: MarketItem;
  severity: string | null;
  severityLevel: string | null;
  severitySource?: string | null;
  form: AssessmentForm;
  setForm: (form: AssessmentForm) => void;
}) {
  const label = (code: string) => scale.levels.find((level) => level.code === code)?.label ?? code;
  const thresholdRank = scale.levels.findIndex((level) => level.code === item.threshold.level);
  const [shown, setShown] = useState(false);
  const levelsId = useId();
  return (
    <section className="ca-drawer-section uw-ma-scale" aria-label="Harm-severity scale">
      <h3>
        <Gauge size={15} aria-hidden="true" /> Harm-severity scale, {versionWords(scale.version)}{" "}
        <span className="uw-ma-starter-chip">{STARTER_LABEL}</span>
      </h3>
      <button
        type="button"
        className="ac-link"
        aria-expanded={shown}
        aria-controls={levelsId}
        onClick={() => setShown(!shown)}
      >
        {shown ? "Hide scale" : "Show scale"}
      </button>
      <ol id={levelsId} className="uw-ma-levels" hidden={!shown}>
        {scale.levels.map((level, index) => (
          <li
            key={level.code}
            className={`${index >= thresholdRank ? "at-threshold" : ""} ${form.harm.level === level.code ? "chosen" : ""}`}
          >
            <strong>{level.label}</strong>
            {index === thresholdRank && (
              <span className="uw-ma-threshold" title={scale.protected_note}>
                {item.threshold.label} threshold
              </span>
            )}
            <span className="uw-cr-meta">{level.terms.map((term) => term.label).join("; ")}</span>
          </li>
        ))}
      </ol>
      <p className="uw-cr-meta">
        {severitySource === "The triage record"
          ? "From the triage record: "
          : `Quality-system severity: ${severity ? `"${severity}"` : "not recorded"} → `}
        {severityLevel ? <strong>{label(severityLevel).toLowerCase()}</strong> : "not mapped: choose a level"}
        {severityLevel &&
        thresholdRank >= 0 &&
        scale.levels.findIndex((level) => level.code === severityLevel) >= thresholdRank
          ? `, at or above the ${item.threshold.label} threshold`
          : ""}
      </p>
      <div className="ca-form-grid">
        <label className="ca-field">
          Harm level
          <select
            value={form.harm.level}
            onChange={(event) => setForm({ ...form, harm: { ...form.harm, level: event.target.value } })}
          >
            <option value="">Choose a level</option>
            {scale.levels.map((level) => (
              <option key={level.code} value={level.code}>
                {level.label}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          Health-impact term (IMDRF Annex F)
          <select
            value={form.harm.term}
            onChange={(event) => setForm({ ...form, harm: { ...form.harm, term: event.target.value } })}
          >
            <option value="">None chosen</option>
            {scale.terms.map((term) => (
              <option key={term.code} value={term.code}>
                {term.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {lowered(scale, form.harm) && <p className="uw-hint">{scale.protected_note}</p>}
      {(form.harm.reason || (severityLevel && form.harm.level && form.harm.level !== severityLevel)) && (
        <label className="ca-field">
          Why this level (it differs from the mapping)
          <input
            value={form.harm.reason}
            onChange={(event) => setForm({ ...form, harm: { ...form.harm, reason: event.target.value } })}
          />
        </label>
      )}
      <p className="ac-note">The scale informs: it never answers a question or changes a conclusion.</p>
    </section>
  );
}

/** The training on what a signature relies on: read each document, then "I have read …, MDARIX starter, version 1". Required to sign in a
 * free trial only (owner decision 6); elsewhere the record can be made but signing does not wait for it. */
export function TrainingPanel({
  documents,
  colleagues,
  required,
  onDone,
  note = "Read the questions and the scale on this page, then confirm each.",
}: {
  documents: TrainingDocument[];
  colleagues: string[];
  required: boolean;
  onDone: () => void;
  note?: string;
}) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const acknowledge = async (document: TrainingDocument) => {
    setBusy(document.code);
    setError("");
    try {
      await send(`/api/v1/signer-training/${encodeURIComponent(document.code)}/acknowledge`, "POST", {
        version: document.version,
        statement: document.statement,
      });
      onDone();
    } catch (failure) {
      setError(errorText(failure, "The acknowledgement was not recorded."));
    } finally {
      setBusy("");
    }
  };
  return (
    <section className="ca-drawer-section uw-ma-training" role="status">
      <h3>
        <BookOpenCheck size={15} aria-hidden="true" />{" "}
        {required ? "Before you sign: practice training on" : "Training record on"}{" "}
        {documents.map((document) => versionWords(document.version)).join(" and ")}
      </h3>
      <p className="ac-muted">
        ISO 13485 clause 6.2: whoever signs is trained on the current version of what the signature relies on. {note}{" "}
        {required
          ? "In a free trial this is a practice record; MDARIX runs no training."
          : "Your organization keeps its own training records; signing here does not wait for this one."}
      </p>
      <ul>
        {documents.map((document) => (
          <li key={document.code}>
            <span>
              {document.title}, {versionWords(document.version)}
              {document.state === "OUT_OF_DATE" ? ` (you hold version ${document.held_version}: out of date)` : ""}
            </span>
            <button type="button" className="ac-secondary" disabled={!!busy} onClick={() => void acknowledge(document)}>
              <ShieldCheck size={15} aria-hidden="true" />{" "}
              {busy === document.code ? "Recording…" : `${document.statement}`}
            </button>
          </li>
        ))}
      </ul>
      {required && (
        <p className="uw-cr-meta">
          {colleagues.length
            ? `Trained colleagues who can sign instead: ${colleagues.join(", ")}.`
            : "No colleague holds a current acknowledgement yet."}
        </p>
      )}
      <InlineError text={error} />
    </section>
  );
}

/** A market's current signed conclusion, with the filing recorded later (exported for tests). */
export function SignedVersion({
  version,
  complaintId,
  onSaved,
}: {
  version: Version;
  complaintId: string;
  onSaved: () => void;
}) {
  const canDecide = useCanAssess();
  const workspace = useContext(WorkspaceContext);
  const [reference, setReference] = useState("");
  const [filedOn, setFiledOn] = useState("");
  const [error, setError] = useState("");
  const conclusion = version.conclusion ?? "NOT_REPORTABLE";
  const record = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      await send(assessmentPath(complaintId, version.market, "/filing"), "POST", {
        filing_reference: reference,
        filed_on: filedOn,
      });
      onSaved();
    } catch (failure) {
      setError(errorText(failure, "The filing was not recorded."));
    }
  };
  return (
    <section className="ca-drawer-section uw-ma-signed" aria-label="Signed conclusion">
      <div className="uw-cr-decision">
        <ToneBadge
          tone={conclusion === "REPORTABLE" ? "warning" : "good"}
          label={`${CONCLUSION_LABELS[conclusion]} · version ${version.version}`}
        />
        {version.report_type_label && <span className="uw-cr-meta">{version.report_type_label}</span>}
        {version.due_on && <span className="uw-cr-meta">Due {formatDay(version.due_on)}</span>}
        <span className="uw-cr-meta">
          Signed by {version.signed_by} · {formatDate(version.signed_at)} · guide {versionWords(version.question_set)} ·
          scale {versionWords(version.scale_version)}
          {version.sample ? " · sample" : ""}
        </span>
        {originWords(version.answers) && <span className="uw-cr-meta">{originWords(version.answers)}</span>}
        {version.override_reason && (
          <span className="uw-cr-meta">
            Overrides the suggestion ({CONCLUSION_LABELS[version.suggested_conclusion].toLowerCase()}):{" "}
            {version.override_reason}
          </span>
        )}
        {version.scale_disagreement_reason && (
          <span className="uw-cr-meta">Against the harm-severity scale: {version.scale_disagreement_reason}</span>
        )}
        {version.filed_on && (
          <span className="uw-cr-meta">
            Filed {formatDay(version.filed_on)} · {version.filing_reference}
          </span>
        )}
      </div>
      {conclusion === "REPORTABLE" && worksheetMarkets(workspace?.navigation).includes(version.market) && (
        <div className="ca-action-row">
          <button
            type="button"
            // On the new navigation the drawer's one main button is the complaint's next step (0.10.70).
            className={workspace?.navigation === "new" ? "ac-secondary" : "ac-primary"}
            onClick={() => workspace?.open("Complaints", reportsTab(complaintId))}
            disabled={!workspace}
          >
            <PenLine size={15} aria-hidden="true" />{" "}
            {version.filed_on ? "Open the report record" : "Open the report worksheet"}
          </button>
          <p className="ac-muted">
            The worksheet is drafted from this conclusion in the authority's field order. A second person approves it;
            you submit it in the authority's route and record it there. MDARIX submits nothing.
          </p>
        </div>
      )}
      {conclusion === "REPORTABLE" &&
        !worksheetMarkets(workspace?.navigation).includes(version.market) &&
        !version.filed_on &&
        canDecide && (
          <form className="ca-form-grid" onSubmit={record} aria-label="Filing reference and date">
            <label className="ca-field">
              Filing reference
              <input
                value={reference}
                maxLength={ASSESSMENT_LIMITS.referenceMax}
                placeholder="e.g. the MDR number"
                onChange={(event) => setReference(event.target.value)}
              />
            </label>
            <label className="ca-field">
              Filed on
              <input type="date" value={filedOn} onChange={(event) => setFiledOn(event.target.value)} />
            </label>
            <button type="submit" className="ac-secondary" disabled={!reference.trim() || !filedOn}>
              Record the filing
            </button>
            <p className="ac-muted">
              Empty until your organization reports to the authority itself: MDARIX submits nothing.
            </p>
          </form>
        )}
      <InlineError text={error} />
    </section>
  );
}

/** The organization's explanation and examples beside a question's locked wording (its decision guide, 0.10.64). */
export function OwnText({ question }: { question: Pick<Question, "explanation" | "examples"> }) {
  if (!question.explanation && !question.examples) return null;
  return (
    <>
      {question.explanation && (
        <p className="uw-hint">
          <strong>Your explanation:</strong> {question.explanation}
        </p>
      )}
      {question.examples && (
        <p className="uw-hint">
          <strong>Your examples:</strong> {question.examples}
        </p>
      )}
    </>
  );
}

/**
 * The flagship story asks "in the US and India?": once the market shown is signed, India comes next when it is
 * enabled and not assessed yet. Outside that story the complaint's own next action leads.
 */
/** Why a market other than the event's own is assessed (0.10.70; the flagship's India): one sentence, starter. */
export const WHY_ASSESSED =
  "Assessed because your procedure asks every market where this device is sold to be assessed.";

export function WhyAssessed() {
  return (
    <p className="uw-cr-meta uw-why-assessed">
      {WHY_ASSESSED} <em>{STARTER_LABEL}.</em>
    </p>
  );
}

/** Whether a receipt line is the conclusion of a market other than the event's own ("Market conclusion, India
 * (CDSCO)" on a US complaint): the record names markets in words, so the line is read by its market's name. */
export const otherMarketLine = (kind: string, own: string | null | undefined): boolean =>
  kind.startsWith("Market conclusion, ") && !!own && !kind.includes(marketLabel(own));

export function alsoIndia(
  story: string | null | undefined,
  shown: ReadonlyArray<Pick<MarketItem, "market" | "current">>,
  active: Pick<MarketItem, "market" | "current">,
): boolean {
  return (
    story === "reportable" &&
    active.market !== "IN" &&
    !!active.current &&
    shown.some((item) => item.market === "IN" && !item.current)
  );
}
