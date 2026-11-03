import { useEffect, useState, type ReactNode } from "react";
import { ClipboardCheck, FilePlus2, FileSignature, GitCompare, Play, RefreshCw, Save, Send } from "lucide-react";
import { AI_TIMEOUT_MS, ApiError, postJson } from "../../../app/apiClient";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Drawer, Table, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { safeText } from "../../../app/displayId";
import { roleNote } from "../../../app/roles";
import { AiInterpretationNote, StatementKind } from "../../shared/StatementKind";
import { useCanRunAi, usePanelFlag, useWorkspace } from "../workspaceContext";
import {
  ACTION_MAX,
  BRIEF_REVIEW_ACTIONS,
  COMMENT_MAX,
  NARRATIVE_TEXT_MAX,
  aiDisclosure,
  aiDraftUnedited,
  briefContext,
  briefCounts,
  briefChecks,
  briefControls,
  briefLines,
  briefNextStep,
  briefPath,
  briefReview,
  briefReviewActionLabel,
  briefReviewDoneMessage,
  briefReviewBody,
  briefReviewProblem,
  briefStatusView,
  briefVersionPath,
  compareBriefs,
  defaultComparison,
  narrativeBody,
  narrativeChanged,
  narrativeFormFrom,
  narrativeGaps,
  narrativeProblem,
  scorecard,
  scorecardHeadline,
  shortHash,
  submitBody,
  versionsNewestFirst,
  type BriefLine,
  type BriefNextStep,
  type BriefState,
  type BriefVersion,
  type BriefVersionRow,
  type NarrativeForm,
} from "../decisionBrief";

const record = (value: unknown): Record<string, any> =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, any>) : {};

/** The quality review panel, which the top of the tab and the Decision tab scroll to. */
const BRIEF_REVIEW_ID = "brief-quality-review";
const scrollToReview = () =>
  document.getElementById(BRIEF_REVIEW_ID)?.scrollIntoView({ behavior: "smooth", block: "start" });

/** A hash shown short, with the whole value on hover and for screen readers. */
function Hash({ value }: { value: unknown }) {
  const full = typeof value === "string" ? value : "";
  return full ? (
    <code className="ca-mono-sm" title={full} aria-label={full}>
      {shortHash(full)}
    </code>
  ) : (
    <>—</>
  );
}

function BriefStatusBadge({ version }: { version: BriefVersion | BriefVersionRow | null | undefined }) {
  const view = briefStatusView(version);
  return <ToneBadge tone={view.tone} label={view.label} />;
}

/**
 * A case's Decision Brief: the versioned package a quality reviewer checks before a decision is made. Its author
 * composes it from the case's records (optionally starting from an AI draft they must edit), writes the problem
 * statement, proposed conclusion and recommended actions, and submits it once the readiness checks allow. A quality
 * reviewer who did not write it starts the review and accepts it for decision or returns it with a comment. The brief
 * gives context; authorized people decide.
 */
export function CaseDecisionBriefPanel({
  investigationId,
  caseLabel,
  readOnly = false,
  focusReview = false,
  onOpenDecision,
}: {
  investigationId: string;
  caseLabel: string;
  readOnly?: boolean;
  /** Opened from the Decision tab's "Review the brief first": scroll to the quality review once the brief is read. */
  focusReview?: boolean;
  /** Opens the case's Decision tab, offered once the brief has been accepted for decision here. */
  onOpenDecision?: () => void;
}) {
  const { notify } = useWorkspace();
  const canRunAi = useCanRunAi();
  const brief = useResource<BriefState>(briefPath(investigationId));
  const state = brief.data;
  const current = state?.current ?? null;
  const controls = briefControls(state);
  const author = {
    compose: controls.compose && !readOnly,
    edit: controls.edit && !readOnly,
    submit: controls.submit && !readOnly,
  };
  // The narrative being written, reset whenever the saved version changes.
  const savedKey = current
    ? `${current.id}:${current.content_hash ?? ""}:${JSON.stringify(current.narrative ?? {})}`
    : "";
  const [form, setForm] = useState<NarrativeForm>(() => narrativeFormFrom(current?.narrative));
  useEffect(() => setForm(narrativeFormFrom(current?.narrative)), [savedKey]);
  const dirty = !!current && narrativeChanged(form, current.narrative);
  const [useAi, setUseAi] = useState(false);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState<{ text: string; tone: "critical" | "warning" } | null>(null);
  // The submit drawer has its own address (panel=submit-brief:1), so Back closes it and a refresh reopens it.
  const [submitting, setSubmitting] = usePanelFlag("submit-brief");
  // The brief accepted for decision on this screen: the next step, signing, is offered at the top and in the review.
  const [accepted, setAccepted] = useState(false);
  const reviewControls = { startReview: controls.startReview && !readOnly, review: controls.review && !readOnly };
  const nextStep = briefNextStep(reviewControls, current, accepted);
  const hasBrief = !!current;
  useEffect(() => {
    if (focusReview && hasBrief) scrollToReview();
  }, [focusReview, hasBrief]);
  const run = async (key: string, work: () => Promise<unknown>, done: string, failed: string) => {
    if (busy) return;
    setBusy(key);
    setMessage(null);
    try {
      await work();
      notify(done);
      brief.reload();
    } catch (failure) {
      setMessage({ text: errorText(failure, failed), tone: "critical" });
    } finally {
      setBusy("");
    }
  };
  const compose = () =>
    run(
      "compose",
      () => postJson(briefPath(investigationId), { use_ai_draft: useAi }, useAi ? { timeoutMs: AI_TIMEOUT_MS } : {}),
      useAi
        ? "A new brief version was composed with an AI draft. Edit the draft into your own words before submitting."
        : "A new brief version was composed from the investigation's records.",
      "The brief could not be composed.",
    );
  const refresh = () =>
    run(
      "refresh",
      () => send(briefPath(investigationId, "draft/refresh"), "POST"),
      "The draft was refreshed from the investigation's current records.",
      "The draft could not be refreshed.",
    );
  const save = () =>
    run(
      "save",
      () => send(briefPath(investigationId, "draft"), "PUT", narrativeBody(form)),
      "Narrative saved.",
      "The narrative was not saved.",
    );
  const blocking = state?.gate?.blocking ?? [];
  const groups = scorecard(briefChecks(current), blocking);
  const gaps = current ? narrativeGaps(form, current.narrative) : [];
  const canSubmitNow =
    author.submit && state?.gate?.can_submit !== false && !dirty && !aiDraftUnedited(form, current?.narrative);
  const context = briefContext(record(current?.content));
  return (
    <>
      <p className="ac-note">
        The Decision Brief gathers what the records establish, what is still unknown and what reviewers found. It
        informs the decision maker; it never makes the decision. AI text is labelled and must be edited by the author.
      </p>
      {current && nextStep && (
        <BriefNextStepBar
          step={nextStep}
          investigationId={investigationId}
          version={current}
          onDone={() => brief.reload()}
          onOpenDecision={onOpenDecision}
        />
      )}
      {state?.communications && (state.communications.open > 0 || state.communications.unresolved > 0) && (
        <p className={`uw-hint tone-${state.communications.overdue ? "critical" : "warning"}`} role="note">
          Requests to external contacts on this case's complaints: {state.communications.open} open,{" "}
          {state.communications.overdue} overdue, {state.communications.unresolved} unresolved after attempts.{" "}
          {state.communications.items
            .slice(0, 3)
            .map((item) => `${item.ref ?? ""} ${item.party ?? ""}: ${item.subject}${item.overdue ? " (overdue)" : ""}`)
            .join("; ")}
          . See Complaints › Communications.
        </p>
      )}
      <Panel
        eyebrow={caseLabel}
        title={current ? `Decision Brief · version ${current.version}` : "Decision Brief"}
        source={brief}
        action={current ? <BriefStatusBadge version={current} /> : undefined}
      >
        {current ? (
          <>
            {safeText(current.title) && <p className="uw-case-question">{current.title}</p>}
            <dl className="ca-facts">
              <div>
                <dt>Brief ID</dt>
                <dd>{safeText(current.business_id) ?? "—"}</dd>
              </div>
              <div>
                <dt>Composed by</dt>
                <dd>
                  {safeText(current.created_by_name) ?? "—"}
                  {context.composedAt ? ` · ${formatDate(context.composedAt)}` : ""}
                </dd>
              </div>
              <div>
                <dt>Submitted</dt>
                <dd>
                  {current.submitted_at
                    ? `${formatDate(current.submitted_at)}${safeText(current.submitted_by_name) ? ` by ${current.submitted_by_name}` : ""}`
                    : "Not yet"}
                </dd>
              </div>
              <div>
                <dt>Reviewed</dt>
                <dd>
                  {current.reviewed_at
                    ? `${formatDate(current.reviewed_at)}${safeText(current.reviewed_by_name) ? ` by ${current.reviewed_by_name}` : ""}`
                    : "Not yet"}
                </dd>
              </div>
              <div>
                <dt>Records as of</dt>
                <dd>{context.asOf ? formatDate(context.asOf) : "—"}</dd>
              </div>
            </dl>
            <details className="uw-more">
              <summary>Version details for the audit record</summary>
              <dl className="ca-facts">
                <div>
                  <dt>Scope version</dt>
                  <dd>{current.scope_version ?? context.scopeVersion ?? "—"}</dd>
                </div>
                <div>
                  <dt>Brief fingerprint</dt>
                  <dd>
                    <Hash value={current.content_hash} />
                  </dd>
                </div>
                <div>
                  <dt>Evidence fingerprint</dt>
                  <dd>
                    <Hash value={context.evidenceSetHash} />
                  </dd>
                </div>
              </dl>
            </details>
          </>
        ) : (
          <Empty
            title="No brief yet"
            detail={
              author.compose
                ? "Compose the first version from the investigation's records. You then write the narrative and submit it for a quality review."
                : "The investigator composes the brief once the investigation is far enough along."
            }
          />
        )}
        {(author.compose || author.edit || author.submit) && (
          <div className="ca-action-row">
            {author.compose && canRunAi && (
              <label className="ca-check">
                <input type="checkbox" checked={useAi} onChange={(event) => setUseAi(event.target.checked)} />
                Start from an AI draft (labelled; you must edit it)
              </label>
            )}
            {author.compose && (
              <button type="button" className="ac-primary" disabled={!!busy} onClick={() => void compose()}>
                <FilePlus2 size={15} aria-hidden="true" />{" "}
                {busy === "compose" ? "Composing…" : current ? "Compose a new version" : "Compose the brief"}
              </button>
            )}
            {author.edit && (
              <button type="button" className="ac-secondary" disabled={!!busy} onClick={() => void refresh()}>
                <RefreshCw size={15} aria-hidden="true" /> {busy === "refresh" ? "Refreshing…" : "Refresh from records"}
              </button>
            )}
          </div>
        )}
        {message && (
          <p className={`ac-message tone-${message.tone}`} role="alert">
            {message.text}
          </p>
        )}
      </Panel>
      {current && (
        <Panel
          eyebrow="Readiness"
          title="Readiness scorecard"
          action={
            author.submit ? (
              <button
                type="button"
                className="ac-primary"
                disabled={!canSubmitNow || !!busy}
                onClick={() => setSubmitting(true)}
              >
                <Send size={15} aria-hidden="true" /> Submit for quality review
              </button>
            ) : undefined
          }
        >
          <p className="ac-muted">{scorecardHeadline(groups)}</p>
          {groups.map((group) => (
            <section key={group.result} className="uw-related" aria-label={group.label}>
              <h3>
                <ToneBadge tone={group.tone} label={group.label} />{" "}
                <span className="ac-tab-count">{group.checks.length}</span>
              </h3>
              <ul className="uw-checklist">
                {group.checks.map((check) => (
                  <li key={check.key}>
                    <span>
                      <strong>{check.label}</strong>
                      {check.rationale && <small>{check.rationale}</small>}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
          {author.submit && dirty && <p className="uw-hint">Save the narrative before submitting.</p>}
          {author.submit && gaps.length > 0 && (
            <ul className="uw-intel-list" aria-label="What the narrative still lacks">
              {gaps.map((gap) => (
                <li key={gap} className="uw-hint">
                  {gap}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}
      {current && (
        <NarrativePanel
          version={current}
          form={form}
          onForm={setForm}
          editable={author.edit}
          dirty={dirty}
          busy={busy === "save"}
          onSave={() => void save()}
        />
      )}
      {current && <ComposedSections version={current} />}
      {current && (
        <QualityReviewPanel
          investigationId={investigationId}
          version={current}
          canStart={reviewControls.startReview}
          canReview={reviewControls.review}
          onDone={() => brief.reload()}
          onAccepted={() => setAccepted(true)}
          onOpenDecision={accepted ? onOpenDecision : undefined}
        />
      )}
      {state && (state.versions?.length ?? 0) > 0 && (
        <VersionHistory investigationId={investigationId} versions={state.versions ?? []} />
      )}
      {submitting && current && (
        <SubmitDrawer
          investigationId={investigationId}
          version={current}
          onClose={() => setSubmitting(false)}
          onDone={(refused) => {
            setSubmitting(false);
            if (refused) setMessage({ text: refused, tone: "warning" });
            brief.reload();
          }}
        />
      )}
    </>
  );
}

/** The author's narrative: editable while the version is a draft the author may change, else read as written. */
function NarrativePanel({
  version,
  form,
  onForm,
  editable,
  dirty,
  busy,
  onSave,
}: {
  version: BriefVersion;
  form: NarrativeForm;
  onForm: (form: NarrativeForm) => void;
  editable: boolean;
  dirty: boolean;
  busy: boolean;
  onSave: () => void;
}) {
  const narrative = version.narrative ?? {};
  const set = (change: Partial<NarrativeForm>) => onForm({ ...form, ...change });
  const problem = narrativeProblem(form);
  const draft = safeText(narrative.ai_draft_text);
  const actions = narrativeBody(form).recommended_actions;
  return (
    <Panel eyebrow="Written by the author" title="Narrative">
      {narrative.ai_draft_used && (
        <div className="uw-intel-card is-ai" aria-label="AI draft">
          <header>
            <StatementKind kind="AI_INTERPRETATION" origin="AI" />
            <strong>AI draft: a starting point, not a conclusion</strong>
          </header>
          {draft ? (
            <p className="uw-intel-statement">{draft}</p>
          ) : (
            <p className="ac-muted">This version was started from an AI draft.</p>
          )}
          <p className="ac-muted">
            The author must review and edit this text. It is not a fact, not a finding and not a decision.
          </p>
          {draftOutOfDate(narrative) && (
            <p className="uw-hint">
              The case&apos;s evidence or scope changed after this draft was made. Run the AI analysis again on the case
              page, then start a new draft.
            </p>
          )}
          {editable && draft && (
            <div className="ca-action-row">
              <button type="button" className="ac-secondary" onClick={() => set({ proposedConclusion: draft })}>
                Copy into the proposed conclusion to edit
              </button>
            </div>
          )}
        </div>
      )}
      {editable ? (
        <form
          className="ca-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!problem && dirty) onSave();
          }}
        >
          <label className="ca-field">
            Problem statement
            <textarea
              rows={4}
              maxLength={NARRATIVE_TEXT_MAX}
              value={form.problemStatement}
              onChange={(event) => set({ problemStatement: event.target.value })}
            />
          </label>
          <label className="ca-field">
            Proposed conclusion (your own words)
            <textarea
              rows={5}
              maxLength={NARRATIVE_TEXT_MAX}
              value={form.proposedConclusion}
              onChange={(event) => set({ proposedConclusion: event.target.value })}
            />
          </label>
          {aiDraftUnedited(form, narrative) && (
            <p className="uw-hint">
              The proposed conclusion is still the AI draft word for word. Edit it before submitting.
            </p>
          )}
          <label className="ca-field">
            Recommended actions (one per line)
            <textarea
              rows={4}
              value={form.actions}
              onChange={(event) => set({ actions: event.target.value })}
              aria-describedby="brief-actions-hint"
            />
            <small id="brief-actions-hint" className="ac-muted">
              Each line is one action, up to {ACTION_MAX} characters.
            </small>
          </label>
          <label className="ca-field">
            Notes for the reviewer (optional)
            <textarea
              rows={3}
              maxLength={NARRATIVE_TEXT_MAX}
              value={form.notes}
              onChange={(event) => set({ notes: event.target.value })}
            />
          </label>
          {problem && <p className="uw-hint">{problem}</p>}
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy || !dirty || !!problem}>
              <Save size={15} aria-hidden="true" /> {busy ? "Saving…" : "Save narrative"}
            </button>
            {dirty && <span className="ac-muted">Unsaved changes</span>}
          </div>
        </form>
      ) : (
        <div className="uw-related">
          <h3>Problem statement</h3>
          <p className="uw-intel-statement">{safeText(narrative.problem_statement) ?? "Not written yet."}</p>
          <h3>Proposed conclusion</h3>
          <p className="uw-intel-statement">{safeText(narrative.proposed_conclusion) ?? "Not written yet."}</p>
          <h3>Recommended actions</h3>
          {actions.length ? (
            <ol className="uw-intel-list">
              {actions.map((item, index) => (
                <li key={`${index}:${item}`}>{item}</li>
              ))}
            </ol>
          ) : (
            <p className="ac-muted">None listed.</p>
          )}
          {safeText(narrative.author_notes) && (
            <>
              <h3>Notes for the reviewer</h3>
              <p className="uw-intel-statement">{narrative.author_notes}</p>
            </>
          )}
        </div>
      )}
    </Panel>
  );
}

function Section({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <section className="uw-related" aria-label={title}>
      <h3>
        {title}
        {typeof count === "number" && (
          <>
            {" "}
            <span className="ac-tab-count">{count}</span>
          </>
        )}
      </h3>
      {children}
    </section>
  );
}

function Lines({
  lines,
  empty,
  kind,
  limit = 25,
}: {
  lines: BriefLine[];
  empty: string;
  /** The kind every line has when the record does not say (a hypothesis, evidence…). */
  kind?: string;
  limit?: number;
}) {
  if (!lines.length) return <p className="ac-muted">{empty}</p>;
  return (
    <ul className="uw-intel-list">
      {lines.slice(0, limit).map((line) => (
        <li key={line.key}>
          {(line.kind || kind) && <StatementKind kind={line.kind ?? kind} origin={line.origin ?? undefined} />}{" "}
          {line.id && <strong>{line.id} · </strong>}
          {line.label}
          {line.detail && <small className="ac-muted"> · {line.detail}</small>}
          {line.evidence && <small className="ac-muted"> · Evidence {line.evidence}</small>}
        </li>
      ))}
      {lines.length > limit && <li className="ac-muted">and {lines.length - limit} more</li>}
    </ul>
  );
}

function ReviewSummary({ title, value }: { title: string; value: unknown }) {
  const review = briefReview(value);
  return (
    <Section title={title}>
      {review ? (
        <p>
          {review.id && <strong>{review.id} · </strong>}
          {review.outcome ?? review.status ?? "Recorded"}
          {review.reviewer ? ` · by ${review.reviewer}` : ""}
          {review.completedAt ? ` · ${formatDate(review.completedAt)}` : ""}
          {review.rationale && (
            <>
              <br />
              <span className="uw-intel-statement">{review.rationale}</span>
            </>
          )}
        </p>
      ) : (
        <p className="ac-muted">No review recorded in this version.</p>
      )}
    </Section>
  );
}

/** The sections MDARIX composed from the case's records, each statement with its kind and who made it. */
function ComposedSections({ version }: { version: BriefVersion }) {
  const content = record(version.content);
  const investigation = record(content.investigation);
  const product = record(content.product);
  const scope = record(content.scope);
  const inventory = record(content.evidence_inventory);
  const unknowns = record(content.unknowns);
  const leading = briefLines(content.leading_hypothesis ? [content.leading_hypothesis] : []);
  const ai = aiDisclosure(content);
  const facts = briefLines(content.established_facts);
  return (
    <Panel eyebrow="Composed from the investigation's records" title="What the brief contains">
      <p className="ac-muted">
        Each statement shows its kind (Fact, Source assertion, Derived observation or AI interpretation) and who made
        it.
      </p>
      <Section title="Case">
        <p>
          <strong>{safeText(investigation.business_id) ?? "—"}</strong>
          {safeText(product.name) ? ` · ${product.name}` : ""}
          {safeText(product.business_id) ? ` (${product.business_id})` : ""}
        </p>
        {safeText(investigation.question) && <p className="uw-intel-statement">{investigation.question}</p>}
      </Section>
      <Section title="Signals" count={briefLines(content.signals).length}>
        <Lines lines={briefLines(content.signals)} empty="No signals listed." />
      </Section>
      <Section title="Scope">
        {Object.keys(scope).length ? (
          <ul className="uw-intel-list">
            {scope.version !== undefined && <li>Version {String(scope.version)}</li>}
            {safeText(scope.question) && <li>{scope.question}</li>}
            {(scope.date_from || scope.date_to) && (
              <li>
                Period {scope.date_from ? formatDate(scope.date_from) : "open"} to{" "}
                {scope.date_to ? formatDate(scope.date_to) : "open"}
              </li>
            )}
            {Array.isArray(scope.product_versions) && <li>Product versions: {scope.product_versions.length}</li>}
            {Array.isArray(scope.included_complaints) && (
              <li>Complaints in scope: {scope.included_complaints.length}</li>
            )}
            {Array.isArray(scope.excluded_complaints) && (
              <li>Complaints excluded: {scope.excluded_complaints.length}</li>
            )}
            {Array.isArray(scope.lots) && <li>Lots: {scope.lots.length}</li>}
          </ul>
        ) : (
          <p className="ac-muted">No scope recorded.</p>
        )}
      </Section>
      {/* Not "Established facts": each statement shows its own kind, often a source assertion (UX-21). */}
      <Section title="What the evidence says" count={facts.length}>
        <Lines lines={facts} empty="No statements from the evidence yet." />
      </Section>
      <Section title="Evidence">
        {briefCounts(inventory.counts).length > 0 && (
          <p>
            {briefCounts(inventory.counts)
              .map((item) => `${item.label}: ${item.count}`)
              .join(" · ")}
          </p>
        )}
        <Lines lines={briefLines(inventory.items)} empty="No evidence in the investigation yet." />
      </Section>
      <div className="uw-intel-board">
        <Section title="Supporting evidence" count={briefLines(content.supporting_evidence).length}>
          <Lines lines={briefLines(content.supporting_evidence)} empty="None linked." />
        </Section>
        <Section title="Contradicting evidence" count={briefLines(content.contradicting_evidence).length}>
          <Lines lines={briefLines(content.contradicting_evidence)} empty="None linked." />
        </Section>
      </div>
      <Section title="Leading hypothesis">
        <Lines
          lines={leading}
          kind="HYPOTHESIS"
          empty="No hypothesis is leading. That is a valid state of an investigation."
        />
      </Section>
      <Section title="Alternative hypotheses" count={briefLines(content.alternative_hypotheses).length}>
        <Lines lines={briefLines(content.alternative_hypotheses)} kind="HYPOTHESIS" empty="None recorded." />
      </Section>
      <div className="uw-intel-board">
        <Section title="Open unknowns" count={briefLines(unknowns.open).length}>
          <Lines lines={briefLines(unknowns.open)} empty="No open unknowns." />
        </Section>
        <Section title="Accepted limitations" count={briefLines(unknowns.accepted_limitations).length}>
          <Lines lines={briefLines(unknowns.accepted_limitations)} empty="None accepted." />
        </Section>
      </div>
      <Section title="Failure chains" count={briefLines(content.failure_chains).length}>
        <Lines lines={briefLines(content.failure_chains)} empty="No failure chains recorded." />
      </Section>
      <div className="uw-intel-board">
        <ReviewSummary title="Risk review" value={content.risk_review} />
        <ReviewSummary title="Regulatory review" value={content.regulatory_review} />
      </div>
      <Section title="AI assistance disclosure" count={ai.executions.length}>
        {ai.executions.length ? (
          <>
            <AiInterpretationNote note={ai.statement} />
            <ul className="uw-intel-list" aria-label="AI runs used in this brief">
              {ai.executions.map((run) => (
                <li key={run.key}>
                  <strong>{run.id}</strong>
                  {run.kind ? ` · ${run.kind}` : ""}
                  {run.provider || run.model ? ` · ${[run.provider, run.model].filter(Boolean).join(" ")}` : ""}
                  {run.at ? ` · ${formatDate(run.at)}` : ""}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="ac-muted">{ai.statement ?? "No AI output was used in this brief."}</p>
        )}
      </Section>
    </Panel>
  );
}

/** Submit the version for a quality review, with an optional comment; a refusal names what still blocks it. */
function SubmitDrawer({
  investigationId,
  version,
  onClose,
  onDone,
}: {
  investigationId: string;
  version: BriefVersion;
  onClose: () => void;
  /** Called with the refusal to show (the brief is not ready), or null once submitted. */
  onDone: (refused: string | null) => void;
}) {
  const { notify } = useWorkspace();
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await send(briefPath(investigationId, "submit"), "POST", submitBody(comment));
      notify(`${safeText(version.business_id) ?? "The brief"} was submitted for a quality review.`);
      onDone(null);
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "BRIEF_NOT_READY") {
        onDone(`${failure.message} The scorecard shows the checks that still block it.`);
        return;
      }
      setError(errorText(failure, "The brief was not submitted."));
      setBusy(false);
    }
  };
  return (
    <Drawer title={`Submit ${safeText(version.business_id) ?? "the brief"} for a quality review`} onClose={onClose}>
      <form className="ca-form ca-drawer-section" onSubmit={submit}>
        <p className="ac-muted">
          A quality reviewer who did not write the brief reviews it. The version is fixed once submitted: changes after
          a return make a new version.
        </p>
        <label className="ca-field">
          Comment for the reviewer (optional)
          <textarea
            rows={3}
            maxLength={COMMENT_MAX}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
          />
        </label>
        {error && (
          <p className="ac-message tone-critical" role="alert">
            {error}
          </p>
        )}
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy}>
            {busy ? "Submitting…" : "Submit for quality review"}
          </button>
        </div>
      </form>
    </Drawer>
  );
}

/** Why a review action was refused, in words for the reviewer. */
const reviewFailure = (failure: unknown, fallback: string) =>
  failure instanceof ApiError && failure.code === "SOD_DENIED"
    ? "You wrote or submitted this brief, so another quality reviewer must review it."
    : errorText(failure, fallback);

/** Starting the quality review of one version, from the top of the tab or from the review panel. */
function useStartReview(investigationId: string, version: BriefVersion, onDone: () => void) {
  const { notify } = useWorkspace();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const start = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await send(briefVersionPath(investigationId, version.version, "start-review"), "POST");
      notify(`${safeText(version.business_id) ?? "The brief"}: review started.`);
      onDone();
    } catch (failure) {
      setError(reviewFailure(failure, "The review could not be started."));
    } finally {
      setBusy(false);
    }
  };
  return { start, busy, error };
}

/**
 * The review's next step at the top of the tab, so a reviewer never has to find it below the whole brief: start the
 * review, go to the review form, or, once the brief is accepted for decision, go and sign the decision.
 */
export function BriefNextStepBar({
  step,
  investigationId,
  version,
  onDone,
  onOpenDecision,
}: {
  step: BriefNextStep;
  investigationId: string;
  version: BriefVersion;
  onDone: () => void;
  onOpenDecision?: () => void;
}) {
  const starting = useStartReview(investigationId, version, onDone);
  if (step === "SIGN")
    return onOpenDecision ? (
      <Panel eyebrow="Quality review" title="Accepted for decision">
        <p className="ac-muted">
          This version of the brief is accepted for decision. An authorized decision maker signs the decision on the
          Decision tab.
        </p>
        <div className="ca-action-row">
          <button type="button" className="ac-primary" onClick={onOpenDecision}>
            <FileSignature size={15} aria-hidden="true" /> Next: sign the decision
          </button>
        </div>
      </Panel>
    ) : null;
  return (
    <Panel
      eyebrow="Quality review"
      title={step === "START_REVIEW" ? "This brief is ready for your review" : "Your review is open"}
    >
      <p className="ac-muted">
        {step === "START_REVIEW"
          ? "Start the review, read the brief below, then record whether it is fit to decide on."
          : "Read the brief below, then record your review: accept it for decision, or return it with a comment."}
      </p>
      <div className="ca-action-row">
        {step === "START_REVIEW" ? (
          <button type="button" className="ac-primary" disabled={starting.busy} onClick={() => void starting.start()}>
            <Play size={15} aria-hidden="true" /> {starting.busy ? "Starting…" : "Start review"}
          </button>
        ) : (
          <button type="button" className="ac-primary" onClick={scrollToReview}>
            <ClipboardCheck size={15} aria-hidden="true" /> Record your review
          </button>
        )}
      </div>
      {starting.error && (
        <p className="ac-message tone-critical" role="alert">
          {starting.error}
        </p>
      )}
    </Panel>
  );
}

/** The quality review: its history for everyone; Start review and the review form only for a reviewer who may. */
function QualityReviewPanel({
  investigationId,
  version,
  canStart,
  canReview,
  onDone,
  onAccepted,
  onOpenDecision,
}: {
  investigationId: string;
  version: BriefVersion;
  canStart: boolean;
  canReview: boolean;
  onDone: () => void;
  /** Called once this person has accepted the brief for decision. */
  onAccepted: () => void;
  /** Offered after the acceptance: the case's Decision tab, where the decision is signed. */
  onOpenDecision?: () => void;
}) {
  const { notify } = useWorkspace();
  const [action, setAction] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const starting = useStartReview(investigationId, version, onDone);
  const history = version.review_actions ?? [];
  const problem = briefReviewProblem(action, comment);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      await send(
        briefVersionPath(investigationId, version.version, "review"),
        "POST",
        briefReviewBody(action, comment),
      );
      const acceptedNow = action === "ACCEPT_FOR_DECISION";
      notify(briefReviewDoneMessage(action, version.business_id));
      setAction("");
      setComment("");
      if (acceptedNow) onAccepted();
      onDone();
    } catch (failure) {
      setError(reviewFailure(failure, "The review was not recorded."));
    } finally {
      setBusy(false);
    }
  };
  if (!history.length && !canStart && !canReview) return null;
  const chosen = BRIEF_REVIEW_ACTIONS.find((item) => item.value === action);
  return (
    <Panel eyebrow="Quality review" title="Review of this brief" id={BRIEF_REVIEW_ID}>
      {history.length ? (
        <ol className="ca-timeline" aria-label="Review history">
          {history.map((item, index) => (
            <li key={index}>
              <strong>{briefReviewActionLabel(item)}</strong>
              <small className="ac-muted">
                {" "}
                · {safeText(item.actor_name) ?? "—"}
                {item.actor_role ? roleNote(item.actor_role) : ""}
                {item.created_at ? ` · ${formatDate(item.created_at)}` : ""}
              </small>
              {safeText(item.comment) && <p className="uw-intel-statement">{item.comment}</p>}
            </li>
          ))}
        </ol>
      ) : (
        <p className="ac-muted">No review actions yet.</p>
      )}
      {onOpenDecision && (
        <div className="ca-action-row">
          <button type="button" className="ac-primary" onClick={onOpenDecision}>
            <FileSignature size={15} aria-hidden="true" /> Next: sign the decision
          </button>
        </div>
      )}
      {canStart && (
        <div className="ca-action-row">
          <button type="button" className="ac-primary" disabled={starting.busy} onClick={() => void starting.start()}>
            <Play size={15} aria-hidden="true" /> {starting.busy ? "Starting…" : "Start review"}
          </button>
        </div>
      )}
      {canReview && (
        <form className="ca-form" onSubmit={submit}>
          <label className="ca-field">
            Your review
            <select value={action} onChange={(event) => setAction(event.target.value)}>
              <option value="">Choose what to do with this brief</option>
              {BRIEF_REVIEW_ACTIONS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="ca-field">
            Comment{chosen && !chosen.commentRequired ? " (optional)" : ""}
            <textarea
              rows={4}
              maxLength={COMMENT_MAX}
              value={comment}
              placeholder={chosen?.commentRequired ? "At least 10 characters" : undefined}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>
          {action && problem && <p className="uw-hint">{problem}</p>}
          <p className="ac-muted">
            Accepting for decision confirms the brief is fit to decide on. It does not decide the investigation:
            authorized approvers do, in the investigation's Decision tab.
          </p>
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy || !!problem}>
              {busy ? "Saving…" : "Record review"}
            </button>
          </div>
        </form>
      )}
      {(error || starting.error) && (
        <p className="ac-message tone-critical" role="alert">
          {error || starting.error}
        </p>
      )}
    </Panel>
  );
}

/** Every version of the brief, and a comparison of any two. */
function VersionHistory({ investigationId, versions }: { investigationId: string; versions: BriefVersionRow[] }) {
  const rows = versionsNewestFirst(versions);
  const start = defaultComparison(versions);
  const [left, setLeft] = useState(start ? String(start[0]) : "");
  const [right, setRight] = useState(start ? String(start[1]) : "");
  const [comparing, setComparing] = useState<{ left: number; right: number } | null>(null);
  return (
    <Panel eyebrow="History" title="Brief versions">
      <Table
        caption="Brief versions"
        rows={rows}
        rowKey={(row) => String(row.id)}
        empty={{ title: "No versions yet", detail: "Each composed version of the brief appears here." }}
        columns={[
          {
            key: "business_id",
            label: "Brief ID",
            render: (row) => <strong>{safeText(row.business_id) ?? "—"}</strong>,
          },
          { key: "version", label: "Version", sortValue: (row) => Number(row.version), render: (row) => row.version },
          { key: "status", label: "Status", render: (row) => <BriefStatusBadge version={row} /> },
          { key: "created_by_name", label: "Composed by", render: (row) => safeText(row.created_by_name) ?? "—" },
          { key: "submitted_at", label: "Submitted", render: (row) => formatDate(row.submitted_at) },
          { key: "reviewed_at", label: "Reviewed", render: (row) => formatDate(row.reviewed_at) },
          { key: "content_hash", label: "Brief fingerprint", render: (row) => <Hash value={row.content_hash} /> },
        ]}
      />
      {rows.length > 1 && (
        <div className="ca-action-row uw-compare-row">
          <label className="ca-inline-select">
            Compare version
            <select value={left} onChange={(event) => setLeft(event.target.value)}>
              {rows.map((row) => (
                <option key={row.version} value={row.version}>
                  {row.version}
                </option>
              ))}
            </select>
          </label>
          <label className="ca-inline-select">
            with version
            <select value={right} onChange={(event) => setRight(event.target.value)}>
              {rows.map((row) => (
                <option key={row.version} value={row.version}>
                  {row.version}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="ac-secondary"
            disabled={!left || !right || left === right}
            onClick={() => setComparing({ left: Number(left), right: Number(right) })}
          >
            <GitCompare size={15} aria-hidden="true" /> Compare
          </button>
        </div>
      )}
      {comparing && (
        <BriefCompare
          key={`${comparing.left}:${comparing.right}`}
          investigationId={investigationId}
          left={comparing.left}
          right={comparing.right}
        />
      )}
    </Panel>
  );
}

function BriefCompare({ investigationId, left, right }: { investigationId: string; left: number; right: number }) {
  const before = useResource<BriefVersion>(briefVersionPath(investigationId, left));
  const after = useResource<BriefVersion>(briefVersionPath(investigationId, right));
  const failed = [before, after].find((item) => item.state === "error" || item.state === "forbidden");
  if (failed) return <p className="ca-inline-error">{failed.error ?? "A version could not be read."}</p>;
  if (!before.data || !after.data)
    return (
      <p className="ac-muted">
        Loading versions {left} and {right}…
      </p>
    );
  const rows = compareBriefs(before.data, after.data);
  return (
    <div className="ac-table-wrap">
      <table className="ac-table uw-compare">
        <caption className="ca-sr-only">
          Brief version {left} compared with version {right}
        </caption>
        <thead>
          <tr>
            <th scope="col">Part</th>
            <th scope="col">Version {left}</th>
            <th scope="col">Version {right}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className={row.same ? undefined : "uw-changed"}>
              <th scope="row">
                {row.label}
                {!row.same && <small className="uw-flag-warning"> · changed</small>}
              </th>
              <td>
                {row.left.length ? (
                  row.left.map((item) => (
                    <div key={item} className={row.removed.includes(item) ? "uw-removed" : undefined}>
                      {row.removed.includes(item) ? `− ${item}` : item}
                    </div>
                  ))
                ) : (
                  <span className="ac-muted">None</span>
                )}
              </td>
              <td>
                {row.right.length ? (
                  row.right.map((item) => (
                    <div key={item} className={row.added.includes(item) ? "uw-added" : undefined}>
                      {row.added.includes(item) ? `+ ${item}` : item}
                    </div>
                  ))
                ) : (
                  <span className="ac-muted">None</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Whether the AI draft the narrative started from was made before the case's latest evidence or scope change. */
function draftOutOfDate(narrative: unknown): boolean {
  const source = (narrative as { ai_draft_source?: { out_of_date?: unknown } } | null | undefined)?.ai_draft_source;
  return source?.out_of_date === true;
}
