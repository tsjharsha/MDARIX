import { useState, type ReactNode } from "react";
import { FileSignature, Gavel, Undo2 } from "lucide-react";
import { requestJson } from "../../../app/apiClient";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Drawer, Table, errorText, formatDate, listOf, send, useResource } from "../../customer-admin/shared";
import { safeText } from "../../../app/displayId";
import { WORKFLOW_ROLE_CODES, roleLabel } from "../../../app/roles";
import { AiInterpretationNote, StatementKind } from "../../shared/StatementKind";
import { useWorkspace, type SessionContext } from "../workspaceContext";
import {
  aiDisclosure,
  briefLines,
  briefReview,
  briefStatusView,
  scorecard,
  scorecardHeadline,
  type BriefLine,
} from "../decisionBrief";
import {
  CONDITIONS_MAX,
  FOLLOW_UP_TITLE_MAX,
  RATIONALE_MAX,
  RETURN_COMMENT_MAX,
  SUPERSEDE_REASON_MAX,
  acknowledgementRequired,
  caseDecisionPath,
  decisionFormProblems,
  decisionHistory,
  emptyDecisionForm,
  emptyFollowUp,
  followUpOptions,
  hashState,
  outcomeLabel,
  outcomeOptions,
  outcomeRules,
  outcomeTone,
  recommendedActions,
  residualUnknowns,
  returnBody,
  returnProblem,
  reviewerLine,
  signBody,
  signErrorView,
  signatureMeaning,
  signedDecisionRef,
  credentialsProblem,
  type CaseDecisionContext,
  type DecisionBrief,
  type DecisionForm,
  type DecisionReviewer,
  type FollowUpChoice,
  type SignContext,
} from "../humanDecision";
import { DecisionRecordDrawer, Fingerprint } from "./DecisionRecord";
import { FollowUpsPanel, ImpactAssessmentsPanel } from "./AfterDecision";
import { CaseStoryLink } from "./CaseStoryLink";

const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

/** The role a signature is given in, as words: a decision role the person holds, else their active role. */
function signerRole(session: SessionContext | null): string | null {
  const roles = Array.isArray(session?.roles) ? session.roles : [];
  const decisionRole = roles.find((role) => ["APPROVER", "LEADER"].includes(String(role?.code ?? "").toUpperCase()));
  if (decisionRole) return roleLabel(decisionRole.code, decisionRole.label);
  return session?.active_role ? roleLabel(session.active_role) : null;
}

/**
 * A case's human decision (Phase 6): the approved Decision Brief as the decision maker reads it, the decision form
 * (outcome, conditions, follow-ups, acknowledgement of what is still unknown, rationale), the meaning of the signature
 * and then a separate Sign step that asks for the password and authenticator code. Returning the case to the
 * investigator is a separate action without a signature. Below: the decision history, the follow-ups and the impact
 * assessments. The brief gives context and AI text is labelled; the decision is always the signer's own.
 */
export function CaseDecisionPanel({
  investigationId,
  caseLabel,
  initialFollowUp = null,
  initialAssessment = null,
  onCaseChanged,
}: {
  investigationId: string;
  caseLabel: string;
  initialFollowUp?: string | null;
  initialAssessment?: string | null;
  /** Called when the case's state changed here (a decision signed, a return, a material impact). */
  onCaseChanged?: () => void;
}) {
  const { notify } = useWorkspace();
  const context = useResource<CaseDecisionContext>(caseDecisionPath(investigationId));
  const data = context.data;
  const brief = data?.brief ?? null;
  const actions = data?.actions ?? {};
  const [message, setMessage] = useState<{ text: string; tone: "critical" | "warning" } | null>(null);
  const [recordId, setRecordId] = useState<string | null>(null);
  const [signedKey, setSignedKey] = useState(0);
  const [returning, setReturning] = useState(false);
  const current = data?.current_decision ?? null;
  const history = decisionHistory(data?.decisions, current);
  const reload = (text?: string) => {
    setMessage(text ? { text, tone: "warning" } : null);
    context.reload();
  };
  return (
    <>
      <p className="ac-note">
        MDARIX gathers what the case's records establish and what reviewers found. The decision is yours: the outcome,
        the conditions and the rationale are written by you, and AI text is never the decision.
      </p>
      <Panel
        eyebrow={safeText(data?.investigation?.business_id) ?? caseLabel}
        title="Human decision"
        source={context}
        action={
          current ? (
            <ToneBadge
              tone={outcomeTone(current.outcome)}
              label={outcomeLabel(current.outcome, current.outcome_label)}
            />
          ) : undefined
        }
      >
        {safeText(data?.investigation?.question) && <p className="uw-case-question">{data?.investigation?.question}</p>}
        {current ? (
          <div className="uw-related">
            <p>
              <strong>{safeText(current.business_id) ?? "Decision"}</strong> ·{" "}
              {outcomeLabel(current.outcome, current.outcome_label)}
              {safeText(current.signer_name) ? ` · signed by ${current.signer_name}` : ""}
              {safeText(current.signer_role) ? ` (${roleLabel(current.signer_role)})` : ""}
              {current.decided_at || current.signed_at
                ? ` · ${formatDate(current.decided_at ?? current.signed_at)}`
                : ""}
            </p>
            {safeText(current.conditions) && (
              <p className="uw-intel-statement">
                <strong>Conditions: </strong>
                {current.conditions}
              </p>
            )}
            {(current.id || safeText(current.business_id)) && (
              <div className="ca-action-row">
                <button
                  type="button"
                  className="ac-secondary"
                  onClick={() => setRecordId(String(current.id ?? current.business_id))}
                >
                  <FileSignature size={15} aria-hidden="true" /> View the signed record
                </button>
              </div>
            )}
          </div>
        ) : (
          <p className="ac-muted">No decision has been signed on this case yet.</p>
        )}
        {!brief && (
          <Empty
            title="No brief to decide on yet"
            detail="A decision is made on a Decision Brief that a quality reviewer accepted for decision. It appears here once accepted."
          />
        )}
        {message && (
          <p className={`ac-message tone-${message.tone}`} role="alert">
            {message.text}
          </p>
        )}
        <div className="ca-action-row">
          <CaseStoryLink
            investigationId={investigationId}
            caseLabel={safeText(data?.investigation?.business_id) ?? caseLabel}
            className="ac-link"
          />
        </div>
      </Panel>
      {data && brief && <BriefForDecision brief={brief} reviewers={listOf(data.reviewers) as DecisionReviewer[]} />}
      {data && brief && actions.can_sign === true && (
        <DecisionFormPanel
          key={`${brief.id ?? ""}:${brief.content_hash ?? ""}:${current?.id ?? ""}`}
          investigationId={investigationId}
          caseLabel={caseLabel}
          context={data}
          brief={brief}
          onSigned={(decision) => {
            setMessage(null);
            setSignedKey((value) => value + 1);
            context.reload();
            onCaseChanged?.();
            if (decision) setRecordId(decision);
          }}
          onRefused={(text) => reload(text)}
        />
      )}
      {data && brief && actions.can_sign !== true && (
        <Panel eyebrow="Signing" title="Sign the decision">
          <p className="ac-muted" role="note">
            {safeText(actions.reason) ??
              "Only an authorized decision maker who did not prepare or review this brief can sign. Administrators never sign."}
          </p>
        </Panel>
      )}
      {data && brief && actions.can_return === true && (
        <Panel eyebrow="Not ready to decide?" title="Return to the investigator">
          <p className="ac-muted">
            Send the brief back with a comment on what is missing. This is not a decision and needs no signature; the
            investigator prepares a new brief version.
          </p>
          <div className="ca-action-row">
            <button type="button" className="ac-secondary" onClick={() => setReturning(true)}>
              <Undo2 size={15} aria-hidden="true" /> Return to the investigator
            </button>
          </div>
        </Panel>
      )}
      <Panel eyebrow="History" title="Decisions on this case">
        <Table
          caption="Decisions on this case"
          rows={history}
          rowKey={(row) => row.key}
          empty={{
            title: "No signed decisions yet",
            detail:
              "Each signed decision appears here. A new decision supersedes the previous one; both stay on record.",
          }}
          columns={[
            { key: "businessId", label: "Decision ID", render: (row) => <strong>{row.businessId}</strong> },
            {
              key: "outcome",
              label: "Outcome",
              render: (row) => <ToneBadge tone={row.outcomeTone} label={row.outcome} />,
            },
            {
              key: "status",
              label: "Status",
              sortValue: (row) => row.status,
              render: (row) => <ToneBadge tone={row.statusTone} label={row.status} />,
            },
            {
              key: "signer",
              label: "Signed by",
              sortValue: (row) => row.signer ?? "",
              render: (row) =>
                row.signer ? `${row.signer}${row.signerRole ? ` (${roleLabel(row.signerRole)})` : ""}` : "—",
            },
            {
              key: "decidedAt",
              label: "Signed",
              sortValue: (row) => row.decidedAt ?? "",
              render: (row) => formatDate(row.decidedAt),
            },
            {
              key: "links",
              label: "Supersedes / superseded by",
              sortValue: (row) => row.supersededBy?.label ?? row.supersedes?.label ?? "",
              render: (row) => (
                <span className="ca-person">
                  {row.supersedes && (
                    <small>
                      Supersedes{" "}
                      {row.supersedes.id ? (
                        <button
                          type="button"
                          className="ac-link"
                          onClick={() => setRecordId(String(row.supersedes?.id))}
                        >
                          {row.supersedes.label}
                        </button>
                      ) : (
                        row.supersedes.label
                      )}
                    </small>
                  )}
                  {row.supersededBy && (
                    <small>
                      Superseded by{" "}
                      {row.supersededBy.id ? (
                        <button
                          type="button"
                          className="ac-link"
                          onClick={() => setRecordId(String(row.supersededBy?.id))}
                        >
                          {row.supersededBy.label}
                        </button>
                      ) : (
                        row.supersededBy.label
                      )}
                    </small>
                  )}
                  {!row.supersedes && !row.supersededBy && <span className="ac-muted">—</span>}
                </span>
              ),
            },
            {
              key: "record",
              label: "",
              render: (row) =>
                row.id ? (
                  <button type="button" className="ac-link" onClick={() => setRecordId(String(row.id))}>
                    Signed record
                  </button>
                ) : null,
            },
          ]}
        />
      </Panel>
      <FollowUpsPanel investigationId={investigationId} initialFollowUp={initialFollowUp} reloadKey={signedKey} />
      <ImpactAssessmentsPanel
        investigationId={investigationId}
        initialAssessment={initialAssessment}
        onReopened={() => {
          context.reload();
          onCaseChanged?.();
        }}
      />
      {recordId && <DecisionRecordDrawer key={recordId} decisionId={recordId} onClose={() => setRecordId(null)} />}
      {returning && brief && (
        <ReturnDrawer
          investigationId={investigationId}
          brief={brief}
          onClose={() => setReturning(false)}
          onDone={() => {
            setReturning(false);
            notify(`${safeText(brief.business_id) ?? "The brief"} was returned to the investigator.`);
            context.reload();
            onCaseChanged?.();
          }}
        />
      )}
    </>
  );
}

function Section({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <section className="uw-related" aria-label={title}>
      <h4>
        {title}
        {typeof count === "number" && (
          <>
            {" "}
            <span className="ac-tab-count">{count}</span>
          </>
        )}
      </h4>
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

function ReviewOutcome({ title, value }: { title: string; value: unknown }) {
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
        <p className="ac-muted">No review recorded in this brief.</p>
      )}
    </Section>
  );
}

/** The approved brief as the decision maker reads it, with its fingerprint and whether it still matches. */
function BriefForDecision({ brief, reviewers }: { brief: DecisionBrief; reviewers: DecisionReviewer[] }) {
  const hash = hashState(brief);
  const residual = residualUnknowns(brief);
  const facts = briefLines(brief.established_facts);
  const contradictions = briefLines(brief.contradictions);
  const actions = recommendedActions(brief);
  const ai = aiDisclosure({ ai_assistance: brief.ai_assistance });
  const checks = record(brief.readiness).checks;
  const groups = Array.isArray(checks) ? scorecard(checks) : [];
  return (
    <Panel
      eyebrow="What you decide on"
      title={`Decision Brief ${safeText(brief.business_id) ?? ""}${brief.version !== undefined && brief.version !== null ? ` · version ${brief.version}` : ""}`}
      action={<ToneBadge tone={hash.tone} label={`Fingerprint: ${hash.label.toLowerCase()}`} />}
    >
      <dl className="ca-facts">
        <div>
          <dt>Brief ID</dt>
          <dd>{safeText(brief.business_id) ?? "—"}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{brief.status || brief.status_label ? briefStatusView(brief).label : "—"}</dd>
        </div>
        <div>
          <dt>Accepted for decision</dt>
          <dd>
            {brief.approved_at ? formatDate(brief.approved_at) : "—"}
            {safeText(brief.quality_reviewer_name) ? ` by ${brief.quality_reviewer_name}` : ""}
          </dd>
        </div>
        <div>
          <dt>Fingerprint</dt>
          <dd>
            <Fingerprint value={brief.content_hash} /> <ToneBadge tone={hash.tone} label={hash.label} />
          </dd>
        </div>
      </dl>
      {hash.key === "mismatch" && (
        <p className="ac-message tone-critical" role="alert">
          This brief no longer matches the fingerprint taken when it was accepted. Do not decide on it; report it to
          your quality lead.
        </p>
      )}
      {groups.length > 0 && <p className="ac-muted">Readiness: {scorecardHeadline(groups)}</p>}
      <Section title="Problem statement">
        <p className="uw-intel-statement">{safeText(brief.narrative?.problem_statement) ?? "Not written."}</p>
      </Section>
      <Section title="Proposed conclusion (the investigator's, for you to judge)">
        <p className="uw-intel-statement">{safeText(brief.narrative?.proposed_conclusion) ?? "Not written."}</p>
      </Section>
      <Section title="Recommended actions" count={actions.length}>
        {actions.length ? (
          <ol className="uw-intel-list">
            {actions.map((item, index) => (
              <li key={`${index}:${item}`}>{item}</li>
            ))}
          </ol>
        ) : (
          <p className="ac-muted">None listed.</p>
        )}
      </Section>
      <Section title="Established facts" count={facts.length}>
        <Lines lines={facts} kind="FACT" empty="No established facts listed." />
      </Section>
      <Section title="Contradictions" count={contradictions.length}>
        <Lines lines={contradictions} empty="No contradictions listed." />
      </Section>
      <div className="uw-intel-board">
        <Section title="Open unknowns" count={residual.open.length}>
          <Lines lines={residual.open} empty="No open unknowns." />
        </Section>
        <Section title="Accepted limitations" count={residual.limitations.length}>
          <Lines lines={residual.limitations} empty="None accepted." />
        </Section>
      </div>
      <div className="uw-intel-board">
        <ReviewOutcome title="Risk review" value={brief.risk_review} />
        <ReviewOutcome title="Regulatory review" value={brief.regulatory_review} />
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
      <Section title="Reviewers" count={reviewers.length}>
        {reviewers.length ? (
          <ol className="ca-timeline" aria-label="Who prepared and reviewed the brief">
            {reviewers.map((item, index) => {
              const line = reviewerLine(item);
              return (
                <li key={index}>
                  <strong>
                    {line.kind}
                    {line.action ? ` · ${line.action}` : ""}
                  </strong>
                  <small className="ac-muted">
                    {" "}
                    · {line.name ?? "—"}
                    {line.role ? ` (${roleLabel(line.role)})` : ""}
                    {line.at ? ` · ${formatDate(line.at)}` : ""}
                  </small>
                  {line.comment && <p className="uw-intel-statement">{line.comment}</p>}
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="ac-muted">No reviewers recorded.</p>
        )}
      </Section>
    </Panel>
  );
}

/** The decision form; once complete it shows what the signature means and opens the separate Sign step. */
function DecisionFormPanel({
  investigationId,
  caseLabel,
  context,
  brief,
  onSigned,
  onRefused,
}: {
  investigationId: string;
  caseLabel: string;
  context: CaseDecisionContext;
  brief: DecisionBrief;
  onSigned: (decisionId: string | null) => void;
  onRefused: (text: string) => void;
}) {
  const { session, notify } = useWorkspace();
  const [form, setForm] = useState<DecisionForm>(emptyDecisionForm);
  const [touched, setTouched] = useState(false);
  const [signing, setSigning] = useState(false);
  const outcomes = outcomeOptions(context.outcomes);
  const followUps = followUpOptions(context.follow_up_options);
  const rules = outcomeRules(form.outcome);
  const people = useResource<Array<{ id: string; business_id?: string | null; display_name?: string | null }>>(
    rules.followUps ? "/api/v1/investigation-assignees" : null,
  );
  const ackRequired = acknowledgementRequired(brief);
  const residual = residualUnknowns(brief);
  const current = context.current_decision ?? null;
  const supersedes = current ? String(current.id ?? "") || null : null;
  const problems = decisionFormProblems(form, { acknowledgementRequired: ackRequired, supersedes: !!current });
  const hash = hashState(brief);
  const briefVersionId = String(brief.id ?? "");
  const briefContentHash = String(brief.content_hash ?? "");
  const missingBrief = !briefVersionId || !briefContentHash;
  const set = (change: Partial<DecisionForm>) => {
    setTouched(true);
    setForm((value) => ({ ...value, ...change }));
  };
  const setFollowUp = (key: string, change: Partial<FollowUpChoice>) =>
    set({ followUps: { ...form.followUps, [key]: { ...(form.followUps[key] ?? emptyFollowUp()), ...change } } });
  const chosen = outcomes.find((item) => item.code === form.outcome);
  const meaning = form.outcome
    ? (safeText(context.signature_meaning) ??
      signatureMeaning({
        signer: session?.display_name,
        role: signerRole(session),
        outcome: chosen?.label ?? form.outcome,
        caseId: safeText(context.investigation?.business_id) ?? caseLabel,
        briefId: brief.business_id,
        version: brief.version,
        contentHash: brief.content_hash,
      }))
    : null;
  const signContext: SignContext = {
    briefVersionId,
    briefContentHash,
    supersedesDecisionId: supersedes,
  };
  const blocked = hash.key === "mismatch" || missingBrief;
  return (
    <Panel eyebrow="Your decision" title="Decide">
      <form
        className="ca-form"
        onSubmit={(event) => {
          event.preventDefault();
          setTouched(true);
          if (!problems.length && !blocked) setSigning(true);
        }}
      >
        <fieldset className="ca-fieldset uw-pick-fieldset">
          <legend>Outcome</legend>
          <ul className="uw-pick-list uw-decision-options">
            {outcomes.map((option) => (
              <li key={option.code}>
                <label className="ca-check">
                  <input
                    type="radio"
                    name={`decision-outcome-${investigationId}`}
                    value={option.code}
                    checked={form.outcome === option.code}
                    onChange={() => set({ outcome: option.code })}
                  />
                  <span>
                    <strong>{option.label}</strong>
                    {option.description && (
                      <>
                        <br />
                        <small className="ac-muted">{option.description}</small>
                      </>
                    )}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
        {rules.conditions && (
          <label className="ca-field">
            Conditions (required)
            <textarea
              rows={4}
              maxLength={CONDITIONS_MAX}
              value={form.conditions}
              placeholder="State the conditions on which the conclusion is accepted."
              onChange={(event) => set({ conditions: event.target.value })}
            />
          </label>
        )}
        {rules.followUps && (
          <fieldset className="ca-fieldset uw-pick-fieldset">
            <legend>Follow-up actions required (optional)</legend>
            <ul className="uw-pick-list uw-decision-options">
              {followUps.map((option) => {
                const choice = form.followUps[option.code] ?? emptyFollowUp();
                return (
                  <li key={option.code}>
                    <label className="ca-check">
                      <input
                        type="checkbox"
                        checked={choice.selected}
                        onChange={(event) => setFollowUp(option.code, { selected: event.target.checked })}
                      />
                      <strong>{option.label}</strong>
                    </label>
                    {choice.selected && (
                      <div className="ca-form-grid uw-decision-follow-up">
                        <label className="ca-field">
                          Title (optional)
                          <input
                            maxLength={FOLLOW_UP_TITLE_MAX}
                            value={choice.title}
                            onChange={(event) => setFollowUp(option.code, { title: event.target.value })}
                          />
                        </label>
                        <label className="ca-field">
                          Assign to a person (optional)
                          <select
                            value={choice.assigneeUserId}
                            onChange={(event) => setFollowUp(option.code, { assigneeUserId: event.target.value })}
                          >
                            <option value="">{people.state === "loading" ? "Loading…" : "No one in particular"}</option>
                            {listOf(people.data).map((person) => (
                              <option key={person.id} value={person.id}>
                                {safeText(person.display_name) ?? "Person"}
                                {safeText(person.business_id) ? ` (${person.business_id})` : ""}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="ca-field">
                          Or a role queue (optional)
                          <select
                            value={choice.assignedRole}
                            disabled={!!choice.assigneeUserId}
                            onChange={(event) => setFollowUp(option.code, { assignedRole: event.target.value })}
                          >
                            <option value="">Default for this action</option>
                            {WORKFLOW_ROLE_CODES.map((code) => (
                              <option key={code} value={code}>
                                {roleLabel(code)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="ca-field">
                          Due date (optional)
                          <input
                            type="date"
                            value={choice.dueDay}
                            onChange={(event) => setFollowUp(option.code, { dueDay: event.target.value })}
                          />
                        </label>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </fieldset>
        )}
        {ackRequired && (
          <label className="ca-check ca-acknowledge">
            <input
              type="checkbox"
              checked={form.acknowledged}
              onChange={(event) => set({ acknowledged: event.target.checked })}
            />
            I have read the {residual.open.length} open {residual.open.length === 1 ? "unknown" : "unknowns"} and{" "}
            {residual.limitations.length} accepted {residual.limitations.length === 1 ? "limitation" : "limitations"}{" "}
            the brief lists, and I decide with them in view.
          </label>
        )}
        <label className="ca-field">
          Your rationale (in your own words)
          <textarea
            rows={5}
            maxLength={RATIONALE_MAX}
            value={form.rationale}
            placeholder="At least 20 characters: why this outcome is supportable on the evidence in the brief."
            onChange={(event) => set({ rationale: event.target.value })}
          />
        </label>
        {current && (
          <>
            <p className="ca-note-box">
              This case already has a signed decision ({safeText(current.business_id) ?? "the current decision"}:{" "}
              {outcomeLabel(current.outcome, current.outcome_label)}). Your decision supersedes it. The earlier signed
              record is kept unchanged.
            </p>
            <label className="ca-field">
              Why this decision supersedes the current one
              <textarea
                rows={3}
                maxLength={SUPERSEDE_REASON_MAX}
                value={form.supersedeReason}
                placeholder="At least 10 characters"
                onChange={(event) => set({ supersedeReason: event.target.value })}
              />
            </label>
          </>
        )}
        {touched && problems.length > 0 && (
          <ul className="uw-intel-list" aria-label="What is still needed before signing">
            {problems.map((problem) => (
              <li key={problem} className="uw-hint">
                {problem}
              </li>
            ))}
          </ul>
        )}
        {meaning && (
          <p className="ca-note-box" aria-label="Meaning of your signature">
            <strong>What your signature means: </strong>
            {meaning}
          </p>
        )}
        {blocked && (
          <p className="ac-message tone-critical" role="alert">
            {missingBrief
              ? "The brief's version or fingerprint is missing, so it cannot be signed. Reload the page."
              : "The brief does not match its fingerprint, so it cannot be signed."}
          </p>
        )}
        <div className="ca-action-row">
          <button type="submit" className="ac-primary" disabled={blocked || (touched && problems.length > 0)}>
            <Gavel size={15} aria-hidden="true" /> Continue to sign
          </button>
          <span className="ac-muted">You confirm your identity in the next step.</span>
        </div>
      </form>
      {signing && meaning && (
        <SignDrawer
          investigationId={investigationId}
          form={form}
          context={signContext}
          meaning={meaning}
          outcome={chosen?.label ?? outcomeLabel(form.outcome)}
          briefLabel={`${safeText(brief.business_id) ?? "Decision Brief"}${brief.version !== undefined && brief.version !== null ? ` · version ${brief.version}` : ""}`}
          onClose={() => setSigning(false)}
          onSigned={(result) => {
            setSigning(false);
            const signed = signedDecisionRef(result);
            notify(`${signed.label} was signed. It is recorded with the exact brief version you reviewed.`);
            onSigned(signed.ref);
          }}
          onRefused={(text) => {
            setSigning(false);
            onRefused(text);
          }}
        />
      )}
    </Panel>
  );
}

/**
 * The Sign step: the decision and the meaning of the signature again, then the password and authenticator code. They
 * are typed here, sent once with the signature request and cleared as soon as the call returns; nothing is stored.
 */
function SignDrawer({
  investigationId,
  form,
  context,
  meaning,
  outcome,
  briefLabel,
  onClose,
  onSigned,
  onRefused,
}: {
  investigationId: string;
  form: DecisionForm;
  context: SignContext;
  meaning: string;
  outcome: string;
  briefLabel: string;
  onClose: () => void;
  onSigned: (result: Record<string, any> | null) => void;
  /** The brief changed or a decision was signed meanwhile: the view reloads with this message. */
  onRefused: (text: string) => void;
}) {
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const problem = credentialsProblem({ password, mfaCode });
  const close = () => {
    setPassword("");
    setMfaCode("");
    onClose();
  };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError("");
    try {
      // The body is built at this moment only; the password and code are not kept anywhere else.
      const result = await requestJson<Record<string, any>>(caseDecisionPath(investigationId, "sign"), {
        method: "POST",
        body: JSON.stringify(signBody(form, context, { password, mfaCode })),
        // A wrong password answers 401: it is shown here, it does not end the session.
        redirectOnUnauthorized: false,
      });
      onSigned(result ?? null);
    } catch (failure) {
      const view = signErrorView(failure);
      if (view.reload) onRefused(view.text);
      else setError(view.text);
    } finally {
      setPassword("");
      setMfaCode("");
      setBusy(false);
    }
  };
  return (
    <Drawer title="Sign the decision" onClose={close}>
      <form className="ca-form ca-drawer-section" onSubmit={submit}>
        <dl className="ca-facts">
          <div>
            <dt>Outcome</dt>
            <dd>{outcome}</dd>
          </div>
          <div>
            <dt>Brief</dt>
            <dd>{briefLabel}</dd>
          </div>
          {form.conditions.trim() && outcomeRules(form.outcome).conditions && (
            <div>
              <dt>Conditions</dt>
              <dd>{form.conditions.trim()}</dd>
            </div>
          )}
        </dl>
        <p className="ca-note-box">
          <strong>What your signature means: </strong>
          {meaning}
        </p>
        <p className="ac-muted">
          Your signature records who you are, the time, this meaning and a fingerprint of the brief version you
          reviewed, so any later change is detected.
        </p>
        <label className="ca-field">
          Your password
          <input
            type="password"
            name="current-password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <label className="ca-field">
          Authenticator code
          <input
            name="one-time-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={mfaCode}
            placeholder="6-digit code"
            onChange={(event) => setMfaCode(event.target.value.replace(/\D/g, ""))}
          />
        </label>
        {error && (
          <p className="ac-message tone-critical" role="alert">
            {error}
          </p>
        )}
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={close} disabled={busy}>
            Back
          </button>
          <button type="submit" className="ac-primary" disabled={busy || !password}>
            <FileSignature size={15} aria-hidden="true" /> {busy ? "Signing…" : "Sign decision"}
          </button>
        </div>
      </form>
    </Drawer>
  );
}

/** Return the brief to the investigator with a comment: not a decision, no signature. */
function ReturnDrawer({
  investigationId,
  brief,
  onClose,
  onDone,
}: {
  investigationId: string;
  brief: DecisionBrief;
  onClose: () => void;
  onDone: () => void;
}) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const problem = returnProblem(comment);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      await send(caseDecisionPath(investigationId, "return"), "POST", returnBody(String(brief.id ?? ""), comment));
      onDone();
    } catch (failure) {
      setError(errorText(failure, "The brief was not returned."));
      setBusy(false);
    }
  };
  return (
    <Drawer title={`Return ${safeText(brief.business_id) ?? "the brief"} to the investigator`} onClose={onClose}>
      <form className="ca-form ca-drawer-section" onSubmit={submit}>
        <p className="ac-muted">
          Returning is not a decision and needs no signature. The investigator sees your comment and prepares a new
          version of the brief.
        </p>
        <label className="ca-field">
          What is missing or needs more work
          <textarea
            required
            rows={4}
            maxLength={RETURN_COMMENT_MAX}
            value={comment}
            placeholder="At least 10 characters"
            onChange={(event) => setComment(event.target.value)}
          />
        </label>
        {comment.trim() && problem && <p className="ac-muted">{problem}</p>}
        {error && (
          <p className="ac-message tone-critical" role="alert">
            {error}
          </p>
        )}
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy || !!problem}>
            {busy ? "Returning…" : "Return to the investigator"}
          </button>
        </div>
      </form>
    </Drawer>
  );
}
