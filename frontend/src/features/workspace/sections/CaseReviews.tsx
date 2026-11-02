import { deadlineLabel } from "../../../app/dates";
import { useEffect, useState } from "react";
import { ClipboardCheck, Play, UserMinus, XCircle } from "lucide-react";
import { ApiError } from "../../../app/apiClient";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Drawer, Table, errorText, formatDate, listOf, send, useResource } from "../../customer-admin/shared";
import { safeText } from "../../../app/displayId";
import { StatementKind } from "../../shared/StatementKind";
import { useCan, usePanelState, useWorkspace } from "../workspaceContext";
import { CaseDocumentLinks } from "./Documents";
import { localDay } from "../workspaceModel";
import { dueAtFromDay } from "../caseWorkflow";
import { dueState, dueText } from "../tasks";
import { clockText, watchStateOf, type Clock, type WatchState } from "../reportability";
import {
  EMPTY_COMPLETE,
  NOTES_MAX,
  RATIONALE_MAX,
  REQUEST_REASON_MAX,
  REVIEW_REASON_MAX,
  assessableMarkets,
  assessableRisks,
  caseReviewsPath,
  completeBody,
  completeProblem,
  isOpenReview,
  openReviewOf,
  outcomeView,
  outcomesFor,
  policyRows,
  reasonsOf,
  regulatoryContext,
  requestReviewBody,
  requestReviewProblem,
  reviewPath,
  reviewReasonBody,
  reviewReasonProblem,
  reviewStatusView,
  reviewType,
  reviewTypeLabel,
  reviewerText,
  riskContext,
  sortReviews,
  toggled,
  type CaseReviews,
  type CompleteForm,
  type Finding,
  type NewHazard,
  CONTROL_ANSWERS,
  EMPTY_FINDING,
  type ContextItem,
  type Review,
  type ReviewDetail,
  type ReviewType,
} from "../reviews";

/** A review's state as a badge (never colour alone). */
export function ReviewStatusBadge({ review }: { review: Review | null | undefined }) {
  const view = reviewStatusView(review);
  return <ToneBadge tone={view.tone} label={view.label} />;
}

/** A review's due date, flagged when overdue or due within two days. */
export function ReviewDue({ review }: { review: Review }) {
  const task = {
    due_at: review.due_at ?? null,
    overdue: review.overdue ?? null,
    status: review.status ?? null,
    completed_at: review.completed_at ?? null,
  };
  const state = isOpenReview(review) ? dueState(task) : "done";
  const text = isOpenReview(review) ? dueText(task, formatDate) : review.due_at ? formatDate(review.due_at) : "—";
  return (
    <span className={state === "overdue" ? "uw-flag-critical" : state === "due_soon" ? "uw-flag-warning" : undefined}>
      {text}
    </span>
  );
}

/**
 * A case's risk and regulatory reviews: what the review policy requires and why, the reviews requested so far with
 * their outcomes, and a way to request one. Reviewers open a review to see its context and record their outcome.
 */
export function CaseReviewsPanel({
  investigationId,
  caseLabel,
  initialReview = null,
  readOnly = false,
}: {
  investigationId: string;
  caseLabel: string;
  /** A review named by a task or a link, opened at once. */
  initialReview?: string | null;
  readOnly?: boolean;
}) {
  const canRequest = useCan("investigation.work");
  const reviews = useResource<CaseReviews>(caseReviewsPath(investigationId));
  // Each drawer has its own address (panel=<kind>:<id>), so Back closes it and a refresh reopens it.
  const [opened, setOpened] = usePanelState<string>(
    "review",
    (id) => id,
    (id) => id,
  );
  useEffect(() => {
    if (initialReview) setOpened(initialReview);
  }, []);
  const [requesting, setRequesting] = usePanelState<ReviewType>(
    "request-review",
    (type) => type,
    (key) => (key === "RISK" || key === "REGULATORY" ? key : null),
  );
  const items = sortReviews(listOf(reviews.data?.items) as Review[]);
  const policy = policyRows(reviews.data?.policy);
  return (
    <>
      <p className="ac-note">
        MDARIX gathers the context; risk and regulatory reviewers decide. A review's outcome is always a person's
        judgement, with their rationale.
      </p>
      <CaseDocumentLinks investigationId={investigationId} />
      <Panel eyebrow={caseLabel} title="Which reviews this investigation needs" source={reviews}>
        <div className="uw-review-policy">
          {policy.map((row) => {
            const open = openReviewOf(items, row.type);
            return (
              <section key={row.type} className="uw-intel-card" aria-label={row.label}>
                <header>
                  <strong>{row.label}</strong>
                  {row.required === null ? (
                    <ToneBadge tone="neutral" label="Policy not reported" />
                  ) : row.required ? (
                    <ToneBadge tone="warning" label="Required" />
                  ) : (
                    <ToneBadge tone="neutral" label="Not required" />
                  )}
                </header>
                <p className="ac-muted">{row.text}</p>
                {row.reasons.length > 0 && (
                  <ul className="uw-intel-list" aria-label={`Why: ${row.label}`}>
                    {row.reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                )}
                {open ? (
                  <p className="ac-muted">
                    {safeText(open.business_id) ?? "A review"} is {reviewStatusView(open).label.toLowerCase()}.{" "}
                    <button type="button" className="ac-link" onClick={() => setOpened(String(open.id))}>
                      Open it
                    </button>
                  </p>
                ) : (
                  canRequest &&
                  !readOnly && (
                    <div className="ca-action-row">
                      <button type="button" className="ac-secondary" onClick={() => setRequesting(row.type)}>
                        <ClipboardCheck size={15} aria-hidden="true" /> Request {row.label.toLowerCase()}
                      </button>
                    </div>
                  )
                )}
              </section>
            );
          })}
        </div>
      </Panel>
      <Panel eyebrow={caseLabel} title="Reviews of this investigation" source={reviews}>
        <Table
          caption="Reviews of this investigation"
          rows={items}
          rowKey={(row) => String(row.id)}
          empty={{
            title: "No reviews yet",
            detail: "Risk and regulatory reviews requested for this investigation appear here with their outcomes.",
          }}
          columns={[
            {
              key: "business_id",
              label: "Review ID",
              render: (row) => <strong>{safeText(row.business_id) ?? "—"}</strong>,
            },
            { key: "type", label: "Type", render: (row) => reviewTypeLabel(row) },
            {
              key: "status",
              label: "Status",
              sortValue: (row) => reviewStatusView(row).label,
              render: (row) => <ReviewStatusBadge review={row} />,
            },
            { key: "reviewer", label: "Reviewer", render: (row) => reviewerText(row) },
            {
              key: "outcome",
              label: "Outcome",
              render: (row) => {
                const outcome = outcomeView(row);
                return outcome ? <ToneBadge tone={outcome.tone} label={outcome.label} /> : "—";
              },
            },
            {
              key: "due_at",
              label: "Due",
              sortValue: (row) => row.due_at ?? "",
              render: (row) => <ReviewDue review={row} />,
            },
            {
              key: "policy",
              label: "Basis",
              render: (row) => (row.required_by_policy ? "Required by policy" : "Requested"),
            },
            {
              key: "open",
              label: "",
              render: (row) => (
                <button type="button" className="ac-link" onClick={() => setOpened(String(row.id))}>
                  Open
                </button>
              ),
            },
          ]}
        />
      </Panel>
      {requesting && (
        <RequestReviewDrawer
          investigationId={investigationId}
          type={requesting}
          onClose={() => setRequesting(null)}
          onDone={() => {
            setRequesting(null);
            reviews.reload();
          }}
        />
      )}
      {opened && <ReviewDrawer reviewId={opened} onClose={() => setOpened(null)} onChanged={() => reviews.reload()} />}
    </>
  );
}

/** Ask for a risk or regulatory review of the case, with an optional reason and due date. */
function RequestReviewDrawer({
  investigationId,
  type,
  onClose,
  onDone,
}: {
  investigationId: string;
  type: ReviewType;
  onClose: () => void;
  onDone: () => void;
}) {
  const { notify } = useWorkspace();
  const [reason, setReason] = useState("");
  const [dueDay, setDueDay] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const problem =
    requestReviewProblem(reason) ?? (dueDay && dueDay < localDay() ? "The due date cannot be in the past." : null);
  const label = type === "RISK" ? "Risk review" : "Regulatory review";
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      const made = await send<Review>(
        caseReviewsPath(investigationId),
        "POST",
        requestReviewBody(type, reason, dueDay ? dueAtFromDay(dueDay) : null),
      );
      const id = safeText(made?.business_id);
      notify(id ? `${label} ${id} requested.` : `${label} requested.`);
      onDone();
    } catch (failure) {
      setError(
        failure instanceof ApiError && failure.code === "REVIEW_ALREADY_OPEN"
          ? `A ${label.toLowerCase()} is already open for this investigation. Open it from the list instead.`
          : errorText(failure, "The review was not requested."),
      );
      setBusy(false);
    }
  };
  return (
    <Drawer title={`Request a ${label.toLowerCase()}`} onClose={onClose}>
      <form className="ca-form ca-drawer-section" onSubmit={submit}>
        <p className="ac-muted">
          The review goes to the {type === "RISK" ? "risk" : "regulatory"} reviewers' queue. They see the case's context
          and record their own outcome.
        </p>
        <label className="ca-field">
          What should the reviewer look at? (optional)
          <textarea
            rows={3}
            maxLength={REQUEST_REASON_MAX}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        <label className="ca-field">
          Due (optional)
          <input type="date" value={dueDay} min={localDay()} onChange={(event) => setDueDay(event.target.value)} />
        </label>
        {problem && <p className="uw-hint">{problem}</p>}
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
            {busy ? "Requesting…" : `Request ${label.toLowerCase()}`}
          </button>
        </div>
      </form>
    </Drawer>
  );
}

type Mode = "details" | "complete" | "recuse" | "cancel";

/**
 * One review for its reviewer: the request, the case's risk or regulatory context, and the actions the server allows
 * now (start, record the outcome, recuse, cancel). The outcome is always chosen by the reviewer.
 */
export function ReviewDrawer({
  reviewId,
  onClose,
  onChanged,
}: {
  reviewId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { notify } = useWorkspace();
  const review = useResource<ReviewDetail>(reviewPath(reviewId));
  const [mode, setMode] = useState<Mode>("details");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const data = review.data;
  const type = reviewType(data);
  const name = safeText(data?.business_id) ?? "Review";
  const actions = data?.actions ?? {};
  const done = (text: string) => {
    notify(text);
    setMode("details");
    setBusy(false);
    review.reload();
    onChanged();
  };
  const start = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await send(reviewPath(reviewId, "start"), "POST");
      done(`${name} started. It is assigned to you.`);
    } catch (failure) {
      setError(errorText(failure, "The review could not be started."));
      setBusy(false);
    }
  };
  return (
    <Drawer title={data ? `${name} · ${reviewTypeLabel(data)}` : "Review"} onClose={onClose}>
      {review.state === "loading" && !data && <p className="ac-muted ca-drawer-section">Loading the review…</p>}
      {(review.state === "error" || review.state === "forbidden") && (
        <p className="ac-message tone-critical ca-drawer-section" role="alert">
          {review.state === "forbidden"
            ? "Your role cannot open this review."
            : (review.error ?? "The review could not be loaded.")}
        </p>
      )}
      {data && (
        <>
          <section className="ca-drawer-section">
            <dl className="ca-facts">
              <div>
                <dt>Status</dt>
                <dd>
                  <ReviewStatusBadge review={data} />
                </dd>
              </div>
              <div>
                <dt>Case</dt>
                <dd>
                  {safeText(data.investigation?.business_id) ?? "—"}
                  {safeText(data.investigation?.product?.name) ? ` · ${data.investigation?.product?.name}` : ""}
                </dd>
              </div>
              <div>
                <dt>Reviewer</dt>
                <dd>{reviewerText(data)}</dd>
              </div>
              <div>
                <dt>Due</dt>
                <dd>
                  <ReviewDue review={data} />
                </dd>
              </div>
              <div>
                <dt>Requested by</dt>
                <dd>
                  {safeText(data.requested_by_name) ?? "—"}
                  {data.created_at ? ` · ${formatDate(data.created_at)}` : ""}
                </dd>
              </div>
              <div>
                <dt>Scope version</dt>
                <dd>{data.scope_version ?? "—"}</dd>
              </div>
            </dl>
            {safeText(data.investigation?.question) && (
              <p className="uw-case-question">{data.investigation?.question}</p>
            )}
            {safeText(data.request_reason) && (
              <p>
                <strong>Asked to look at: </strong>
                {data.request_reason}
              </p>
            )}
            {data.required_by_policy && (
              <div>
                <ToneBadge tone="warning" label="Required by policy" />
                {reasonsOf(data.policy_reasons).length > 0 && (
                  <ul className="uw-intel-list">
                    {reasonsOf(data.policy_reasons).map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            {safeText(data.superseded_reason) && (
              <p className="ac-message tone-warning" role="note">
                Superseded: {data.superseded_reason}
              </p>
            )}
          </section>
          {outcomeView(data) && (
            <section className="ca-drawer-section">
              <h3>Outcome recorded by the reviewer</h3>
              <p>
                <ToneBadge tone={outcomeView(data)!.tone} label={outcomeView(data)!.label} />
                {data.completed_at ? <span className="ac-muted"> · {formatDate(data.completed_at)}</span> : null}
              </p>
              {safeText(data.rationale) && <p className="uw-intel-statement">{data.rationale}</p>}
              <AssessedSummary review={data} />
            </section>
          )}
          {mode === "details" &&
            (actions.can_start || actions.can_complete || actions.can_recuse || actions.can_cancel) && (
              <div className="ca-action-row ca-drawer-section">
                {actions.can_start && (
                  <button type="button" className="ac-primary" disabled={busy} onClick={() => void start()}>
                    <Play size={15} aria-hidden="true" /> {busy ? "Starting…" : "Start review"}
                  </button>
                )}
                {actions.can_complete && (
                  <button type="button" className="ac-primary" onClick={() => setMode("complete")}>
                    <ClipboardCheck size={15} aria-hidden="true" /> Record outcome
                  </button>
                )}
                {actions.can_recuse && (
                  <button type="button" className="ac-secondary" onClick={() => setMode("recuse")}>
                    <UserMinus size={15} aria-hidden="true" /> Recuse
                  </button>
                )}
                {actions.can_cancel && (
                  <button type="button" className="ac-secondary" onClick={() => setMode("cancel")}>
                    <XCircle size={15} aria-hidden="true" /> Cancel review
                  </button>
                )}
              </div>
            )}
          {error && (
            <p className="ac-message tone-critical" role="alert">
              {error}
            </p>
          )}
          {mode === "complete" && (
            <CompleteForm
              review={data}
              type={type}
              onCancel={() => setMode("details")}
              onDone={() => done(`${name}: outcome recorded.`)}
            />
          )}
          {(mode === "recuse" || mode === "cancel") && (
            <ReasonForm
              reviewId={reviewId}
              action={mode}
              onCancel={() => setMode("details")}
              onDone={() => done(mode === "recuse" ? `You recused yourself from ${name}.` : `${name} cancelled.`)}
            />
          )}
          {type === "RISK" && <RiskContextView context={data.context} />}
          {type === "REGULATORY" && <RegulatoryContextView context={data.context} />}
        </>
      )}
    </Drawer>
  );
}

function AssessedSummary({ review }: { review: Review }) {
  const assessed = review.assessed ?? {};
  const markets = listOf(assessed.markets)
    .map((item: unknown) => safeText(item))
    .filter(Boolean);
  const risks = listOf(assessed.risk_ids).length;
  const notes = safeText(assessed.notes);
  const findings = listOf(assessed.findings) as {
    key: string;
    risk_identifier?: string | null;
    description?: string | null;
    control_label?: string | null;
    reason?: string | null;
    risk_file_update?: { due_on: string } | null;
  }[];
  if (!markets.length && !risks && !notes && !findings.length) return null;
  return (
    <ul className="uw-intel-list" aria-label="What the reviewer assessed">
      {risks > 0 && <li>Risks assessed: {risks}</li>}
      {findings.map((item) => (
        <li key={item.key}>
          {item.risk_identifier ?? (item.description ? `Not in the risk file: ${item.description}` : item.key)}
          {item.control_label ? ` · risk control: ${item.control_label}` : ""}
          {item.reason ? ` (${item.reason})` : ""}
          {item.risk_file_update ? ` · risk file update due ${item.risk_file_update.due_on}` : ""}
        </li>
      ))}
      {markets.length > 0 && <li>Markets assessed: {markets.join(", ")}</li>}
      {notes && <li>Notes: {notes}</li>}
    </ul>
  );
}

/** Record the outcome: chosen by the reviewer, with a rationale, and what was assessed. */
function CompleteForm({
  review,
  type,
  onCancel,
  onDone,
}: {
  review: ReviewDetail;
  type: ReviewType | null;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState<CompleteForm>(EMPTY_COMPLETE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [touched, setTouched] = useState(false);
  const problem = completeProblem(type, form);
  const set = (change: Partial<CompleteForm>) => setForm((value) => ({ ...value, ...change }));
  const risks = type === "RISK" ? assessableRisks(riskContext(review.context)) : [];
  const people = useResource<{ id: string; display_name: string | null }[]>(
    type === "RISK" ? "/api/v1/investigation-assignees" : null,
  );
  const markets = type === "REGULATORY" ? assessableMarkets(regulatoryContext(review.context)) : [];
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      await send(reviewPath(String(review.id), "complete"), "POST", completeBody(form));
      onDone();
    } catch (failure) {
      setError(errorText(failure, "The outcome was not recorded."));
      setBusy(false);
    }
  };
  return (
    <form className="ca-form ca-drawer-section" onSubmit={submit}>
      <h3>Record your outcome</h3>
      <p className="ac-muted">MDARIX does not suggest an outcome. Choose the one your review supports.</p>
      <label className="ca-field">
        Outcome
        <select value={form.outcome} onChange={(event) => set({ outcome: event.target.value })}>
          <option value="">Choose an outcome</option>
          {outcomesFor(type).map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <label className="ca-field">
        Rationale
        <textarea
          required
          rows={5}
          maxLength={RATIONALE_MAX}
          value={form.rationale}
          placeholder="At least 20 characters"
          onChange={(event) => set({ rationale: event.target.value })}
        />
      </label>
      {type === "RISK" && (
        <fieldset className="ca-fieldset">
          <legend>Risks in the risk file you assessed: did each risk control work?</legend>
          {risks.length ? (
            risks.map((item) => {
              const id = String(item.id);
              const finding = form.findings[id] ?? EMPTY_FINDING;
              const setFinding = (change: Partial<Finding>) =>
                set({ findings: { ...form.findings, [id]: { ...finding, ...change } } });
              return (
                <div key={item.key} className="uw-rv-finding">
                  <label className="ca-check">
                    <input
                      type="checkbox"
                      checked={form.riskIds.includes(id)}
                      onChange={(event) => set({ riskIds: toggled(form.riskIds, id, event.target.checked) })}
                    />
                    {item.label}
                  </label>
                  {form.riskIds.includes(id) && (
                    <div className="ca-form-grid">
                      <label className="ca-field">
                        Did its risk control work?
                        <select
                          value={finding.control}
                          onChange={(event) => setFinding({ control: event.target.value })}
                        >
                          <option value="">Choose…</option>
                          {CONTROL_ANSWERS.map((answer) => (
                            <option key={answer.value} value={answer.value}>
                              {answer.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="ca-field">
                        Reason
                        <input
                          value={finding.reason}
                          onChange={(event) => setFinding({ reason: event.target.value })}
                        />
                      </label>
                      {finding.control === "NO" && (
                        <UpdateFields
                          people={people.data ?? []}
                          ownerId={finding.ownerId}
                          dueDay={finding.dueDay}
                          onChange={(ownerId, dueDay) => setFinding({ ownerId, dueDay })}
                        />
                      )}
                    </div>
                  )}
                </div>
              );
            })
          ) : (
            <p className="ac-muted">The context lists no risks to choose from.</p>
          )}
          <h3>New failure mode or hazard, not in the risk file</h3>
          {form.newHazards.map((hazard, index) => {
            const change = (patch: Partial<NewHazard>) =>
              set({ newHazards: form.newHazards.map((item, at) => (at === index ? { ...item, ...patch } : item)) });
            return (
              <div key={index} className="ca-form-grid uw-rv-finding">
                <label className="ca-field">
                  Risk file update required: what is new
                  <input value={hazard.description} onChange={(event) => change({ description: event.target.value })} />
                </label>
                <UpdateFields
                  people={people.data ?? []}
                  ownerId={hazard.ownerId}
                  dueDay={hazard.dueDay}
                  onChange={(ownerId, dueDay) => change({ ownerId, dueDay })}
                />
              </div>
            );
          })}
          <button
            type="button"
            className="ac-secondary"
            onClick={() => set({ newHazards: [...form.newHazards, { description: "", ownerId: "", dueDay: "" }] })}
          >
            Add a new failure mode or hazard
          </button>
          <p className="ac-muted">
            ISO 14971:2019 clause 10. Each risk file update shows under Records › Risk file input until it is done.
          </p>
        </fieldset>
      )}
      {type === "REGULATORY" && (
        <fieldset className="ca-fieldset">
          <legend>Markets you assessed (optional)</legend>
          {markets.length ? (
            markets.map((market) => (
              <label className="ca-check" key={market}>
                <input
                  type="checkbox"
                  checked={form.markets.includes(market)}
                  onChange={(event) => set({ markets: toggled(form.markets, market, event.target.checked) })}
                />
                {market}
              </label>
            ))
          ) : (
            <p className="ac-muted">The context lists no markets to choose from.</p>
          )}
        </fieldset>
      )}
      <label className="ca-field">
        Notes (optional)
        <textarea
          rows={3}
          maxLength={NOTES_MAX}
          value={form.notes}
          onChange={(event) => set({ notes: event.target.value })}
        />
      </label>
      {(touched || form.outcome || form.rationale) && problem && <p className="uw-hint">{problem}</p>}
      {error && (
        <p className="ac-message tone-critical" role="alert">
          {error}
        </p>
      )}
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={onCancel} disabled={busy}>
          Back
        </button>
        <button type="submit" className="ac-primary" disabled={busy || !!problem}>
          {busy ? "Saving…" : "Record outcome"}
        </button>
      </div>
    </form>
  );
}

function UpdateFields({
  people,
  ownerId,
  dueDay,
  onChange,
}: {
  people: { id: string; display_name: string | null }[];
  ownerId: string;
  dueDay: string;
  onChange: (ownerId: string, dueDay: string) => void;
}) {
  return (
    <>
      <label className="ca-field">
        Owner of the risk file update
        <select value={ownerId} onChange={(event) => onChange(event.target.value, dueDay)}>
          <option value="">Choose…</option>
          {people.map((person) => (
            <option key={person.id} value={person.id}>
              {person.display_name ?? "A colleague"}
            </option>
          ))}
        </select>
      </label>
      <label className="ca-field">
        Due date
        <input type="date" value={dueDay} onChange={(event) => onChange(ownerId, event.target.value)} />
      </label>
    </>
  );
}

function ReasonForm({
  reviewId,
  action,
  onCancel,
  onDone,
}: {
  reviewId: string;
  action: "recuse" | "cancel";
  onCancel: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const problem = reviewReasonProblem(reason);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      await send(reviewPath(reviewId, action), "POST", reviewReasonBody(reason));
      onDone();
    } catch (failure) {
      setError(
        errorText(failure, action === "recuse" ? "The recusal was not recorded." : "The review was not cancelled."),
      );
      setBusy(false);
    }
  };
  return (
    <form className="ca-form ca-drawer-section" onSubmit={submit}>
      <label className="ca-field">
        {action === "recuse"
          ? "Why are you recusing yourself? The review goes back to its queue."
          : "Why is this review cancelled?"}
        <textarea
          required
          rows={3}
          maxLength={REVIEW_REASON_MAX}
          value={reason}
          placeholder="At least 10 characters"
          onChange={(event) => setReason(event.target.value)}
        />
      </label>
      {reason.trim() && problem && <p className="uw-hint">{problem}</p>}
      <p className="ac-muted">Recorded in the review's history and the audit trail.</p>
      {error && (
        <p className="ac-message tone-critical" role="alert">
          {error}
        </p>
      )}
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={onCancel} disabled={busy}>
          Back
        </button>
        <button type="submit" className={action === "cancel" ? "ca-danger" : "ac-primary"} disabled={busy || !!problem}>
          {busy ? "Saving…" : action === "recuse" ? "Recuse" : "Cancel review"}
        </button>
      </div>
    </form>
  );
}

function ItemList({ title, items, empty }: { title: string; items: ContextItem[]; empty: string }) {
  return (
    <div className="uw-related">
      <h3>
        {title} <span className="ac-tab-count">{items.length}</span>
      </h3>
      {items.length ? (
        <ul className="uw-intel-list">
          {items.map((item) => (
            <li key={item.key}>
              {item.label}
              {item.detail && <small className="ac-muted"> · {item.detail}</small>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="ac-muted">{empty}</p>
      )}
    </div>
  );
}

/** What a risk reviewer needs: the product's risk file and the case's hypotheses, gaps and failure chains. */
function RiskContextView({ context }: { context: unknown }) {
  const risk = riskContext(context);
  return (
    <section className="ca-drawer-section" aria-label="Risk context">
      <h3>Risk context</h3>
      <p className="ac-muted">
        Gathered from the product's risk file and this case. It informs your review; it decides nothing.
      </p>
      <ItemList title="Risks" items={risk.risks} empty="No risks recorded for this product." />
      <ItemList title="Hazards" items={risk.hazards} empty="No hazards recorded." />
      <ItemList title="Harms" items={risk.harms} empty="No harms recorded." />
      <ItemList title="Risk controls" items={risk.controls} empty="No risk controls recorded." />
      <ItemList title="Failure modes" items={risk.failureModes} empty="No failure modes recorded." />
      <div className="uw-related">
        <h3>
          Hypotheses <span className="ac-tab-count">{risk.hypotheses.length}</span>
        </h3>
        {risk.hypotheses.length ? (
          <ul className="uw-intel-list">
            {risk.hypotheses.map((item) => (
              <li key={item.key}>
                <StatementKind kind="HYPOTHESIS" origin={item.origin ?? undefined} /> {item.label}
                <small className="ac-muted">
                  {" "}
                  · Judgement: {item.judgement ?? "not judged yet"}
                  {item.supporting !== null ? ` · ${item.supporting} supporting` : ""}
                  {item.contradicting !== null ? ` · ${item.contradicting} contradicting` : ""}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <p className="ac-muted">No hypotheses recorded.</p>
        )}
      </div>
      <p>
        <strong>Contradictions: </strong>
        {risk.contradictions ?? "—"}
      </p>
      <ItemList title="Open unknowns" items={risk.openUnknowns} empty="No open unknowns." />
      <ItemList title="Failure chains" items={risk.failureChains} empty="No failure chains recorded." />
    </section>
  );
}

/** What a regulatory reviewer needs: complaints in scope by market, their dates and flags, the earliest awareness. */
function RegulatoryContextView({ context }: { context: unknown }) {
  const regulatory = regulatoryContext(context);
  return (
    <section className="ca-drawer-section" aria-label="Regulatory context">
      <h3>Regulatory context</h3>
      <p className="ac-message tone-warning" role="note">
        {regulatory.note}
      </p>
      <dl className="ca-facts">
        <div>
          <dt>Complaints in scope</dt>
          <dd>{regulatory.complaints.length}</dd>
        </div>
        <div>
          <dt>Earliest awareness</dt>
          <dd>{regulatory.earliestAwareness ? formatDate(regulatory.earliestAwareness) : "—"}</dd>
        </div>
      </dl>
      <ReportingClocks context={context} />
      {regulatory.markets.length > 0 && (
        <div className="uw-related">
          <h3>Complaints per market</h3>
          <ul className="uw-intel-list">
            {regulatory.markets.map((item) => (
              <li key={item.market}>
                {item.market}: {item.count}
              </li>
            ))}
          </ul>
        </div>
      )}
      {regulatory.complaints.length ? (
        <div className="ac-table-wrap">
          <table className="ac-table">
            <caption className="ca-sr-only">Complaints in scope</caption>
            <thead>
              <tr>
                <th scope="col">Complaint</th>
                <th scope="col">Market</th>
                <th scope="col">Event</th>
                <th scope="col">Received</th>
                <th scope="col">Flags</th>
              </tr>
            </thead>
            <tbody>
              {regulatory.complaints.map((item) => (
                <tr key={item.key}>
                  <td>{item.label}</td>
                  <td>{item.market ?? "—"}</td>
                  <td>{item.eventDate ? formatDate(item.eventDate) : "—"}</td>
                  <td>{item.receivedDate ? formatDate(item.receivedDate) : "—"}</td>
                  <td>
                    {item.flags.length
                      ? item.flags.map((flag) => <ToneBadge key={flag} tone="serious" label={flag} />)
                      : "None recorded"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty title="No complaints in scope" detail="The investigation's scope lists no complaints yet." />
      )}
    </section>
  );
}

type ReportingClock = {
  complaint: { id: string; business_id: string | null };
  state: WatchState;
  binding: Clock | null;
  decision: "REPORTED" | "NOT_REPORTABLE" | null;
};

/** Each complaint's reporting clock against the organization's own windows (exported for its unit test). */
export function ReportingClocks({ context }: { context: unknown }) {
  const { open } = useWorkspace();
  const clocks = listOf((context as { reporting_clocks?: unknown } | null)?.reporting_clocks) as ReportingClock[];
  if (!clocks.length) return null;
  return (
    <div className="uw-related">
      <h3>Reporting clocks (your organization&apos;s windows)</h3>
      <ul className="uw-intel-list">
        {clocks.map((item) => {
          const state = watchStateOf(item.state);
          return (
            <li key={item.complaint.id}>
              <strong>{item.complaint.business_id ?? "Complaint"}</strong>{" "}
              <ToneBadge
                tone={state.tone}
                label={
                  item.decision
                    ? item.decision === "REPORTED"
                      ? "Reported"
                      : "Not reportable"
                    : item.binding
                      ? clockText(item.binding)
                      : state.label
                }
              />
              {item.binding && !item.decision && (
                <small>
                  {" "}
                  {item.binding.window} · due {deadlineLabel(item.binding)}
                </small>
              )}
            </li>
          );
        })}
      </ul>
      <button type="button" className="ac-link" onClick={() => open("Complaints", "Reportability")}>
        Assess each market on the reportability watch
      </button>
    </div>
  );
}
