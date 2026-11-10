import { useState, type ReactNode } from "react";
import { Boxes, CalendarClock, ChevronRight, Pause, Play, XCircle } from "lucide-react";
import { Panel, ToneBadge } from "../../admin/console/charts";
import { Drawer, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { displayId, safeText, sourceId } from "../../../app/displayId";
import { lotsText } from "../signalAi";
import { useCan, usePanelState, useWorkspace } from "../workspaceContext";
import {
  CHECK_RESULT,
  STEP_STATUS,
  TRANSITION_REASON_MAX,
  caseDueState,
  casePriorityLabel,
  caseStateLabel,
  caseStateTone,
  caseProgress,
  caseSteps,
  caseTransitions,
  nextCaseStep,
  readinessChecks,
  readinessHeadline,
  readinessPath,
  transitionBody,
  transitionPath,
  transitionProblem,
  type CaseReadiness,
  type CaseSection,
  type CaseTransition,
  type CaseWorkflowFields,
  type StepDestination,
} from "../caseWorkflow";
import { priorityTone } from "../tasks";
import { StatusBadge } from "./common";
import { WhyAsked } from "../../shared/Basis";
import { CASE_STEP_WHY } from "../whyAsked";

/** A case's state: its workflow state's label when the server sends one, else its plain status as before. */
export function CaseStateBadge({ row }: { row: CaseWorkflowFields | null | undefined }) {
  const label = caseStateLabel(row);
  return label ? <ToneBadge tone={caseStateTone(row)} label={label} /> : <StatusBadge value={row?.status} />;
}

export function CasePriority({ priority }: { priority: unknown }) {
  return priority ? (
    <ToneBadge tone={priorityTone(priority)} label={casePriorityLabel(priority)} />
  ) : (
    <span className="ac-muted">Not set</span>
  );
}

/** The case's due date, flagged when it is overdue or due within two days. */
export function CaseDue({ row }: { row: CaseWorkflowFields }) {
  const state = caseDueState(row);
  if (!row.due_at) return state === "overdue" ? <span className="uw-flag-critical">Overdue</span> : <>No due date</>;
  const when = formatDate(row.due_at);
  if (state === "overdue") return <span className="uw-flag-critical">{when} · overdue</span>;
  if (state === "due_soon") return <span className="uw-flag-warning">{when} · due soon</span>;
  return <>{when}</>;
}

/** Who owns the case, when the response names them (never a UUID). */
export const ownerText = (row: Record<string, unknown> | null | undefined) =>
  safeText(row?.owner_name) ?? safeText(row?.owner_display_name) ?? safeText(row?.owner_ref) ?? "No owner recorded";

/**
 * The case header of the workspace: its ID, question, state, priority, due date and owner, the state changes the
 * person may make, the stepper from Overview to Human review, and the readiness checklist. Every state change asks
 * for a reason; the server decides whether it is allowed.
 */
export function CaseHeader({
  investigationId,
  row,
  onManage,
  onLotImpact,
  onStep,
  onSection,
  onChanged,
}: {
  investigationId: string;
  row: Record<string, any> | null | undefined;
  /** Opens the manage drawer (priority, due date, owner); absent for a role that may not change the case. */
  onManage?: () => void;
  /** Opens the case's Lot impact (a free trial, T-G5); absent where it is not offered. */
  onLotImpact?: () => void;
  onStep: (destination: StepDestination) => void;
  /** The new navigation (stage 8): one progress line over the four sections instead of the stepper, and the next
   * step as the main button; it opens the section and the part where the step is done. */
  onSection?: (section: CaseSection, part?: string) => void;
  onChanged: () => void;
}) {
  const canWork = useCan("investigation.work");
  const canAssign = useCan("investigation.assign");
  const readiness = useResource<CaseReadiness>(readinessPath(investigationId));
  const current: Record<string, any> = {
    ...(row ?? {}),
    workflow_state: row?.workflow_state ?? readiness.data?.workflow_state ?? null,
  };
  const transitions = caseTransitions(current, { work: canWork, assign: canAssign });
  // The state change asked for has its own address (panel=state-change:<state>), so Back closes it.
  const [transition, setTransition] = usePanelState<CaseTransition>(
    "state-change",
    (item) => item.to,
    (to) => transitions.find((item) => item.to === to) ?? null,
  );
  const steps = caseSteps(readiness.data);
  const checks = readinessChecks(readiness.data);
  const label = displayId(current, "investigation_identifier", "Investigation");
  return (
    <>
      {onSection ? (
        // The record page's highlights (0.10.74, Release C part C2): the reference, its product, the question, the
        // chips (state, priority, due), the owner, the complaints and lots in scope and what blocks the decision.
        <CaseHighlights
          row={current}
          label={label}
          readiness={readiness.data}
          actions={
            (transitions.length > 0 || onManage || onLotImpact) && (
              <div className="ca-action-row">
                {transitions.map((item) => (
                  <button
                    type="button"
                    key={`${item.to}:${item.label}`}
                    className="ac-secondary"
                    onClick={() => setTransition(item)}
                  >
                    {item.label}
                  </button>
                ))}
                {onManage && (
                  <button type="button" className="ac-secondary" onClick={onManage}>
                    <CalendarClock size={15} aria-hidden="true" /> Priority and due date
                  </button>
                )}
                {onLotImpact && (
                  <button type="button" className="ac-secondary" onClick={onLotImpact}>
                    <Boxes size={15} aria-hidden="true" /> Lot impact
                  </button>
                )}
              </div>
            )
          }
        >
          <CaseProgressLine steps={readiness.data ? steps : []} onSection={onSection} />
        </CaseHighlights>
      ) : (
        <Panel eyebrow="Investigation" title={label} action={<CaseStateBadge row={current} />}>
          <p className="uw-case-question">{safeText(current.investigation_question) ?? "No question recorded."}</p>
          <dl className="ca-facts">
            <div>
              <dt>Priority</dt>
              <dd>
                <CasePriority priority={current.priority} />
              </dd>
            </div>
            <div>
              <dt>Due</dt>
              <dd>
                <CaseDue row={current} />
              </dd>
            </div>
            <div>
              <dt>Owner</dt>
              <dd>{ownerText(current)}</dd>
            </div>
          </dl>
          {onLotImpact && (
            <p className="uw-li-entry">
              <button type="button" className="ac-secondary" onClick={onLotImpact}>
                <Boxes size={15} aria-hidden="true" /> Lot impact: which other lots share the suspect part
              </button>
            </p>
          )}
          {(transitions.length > 0 || onManage) && (
            <div className="ca-action-row">
              {transitions.map((item) => (
                <button
                  type="button"
                  key={`${item.to}:${item.label}`}
                  className={item.danger ? "ac-secondary" : "ac-primary"}
                  onClick={() => setTransition(item)}
                >
                  {item.to === "ON_HOLD" ? (
                    <Pause size={15} aria-hidden="true" />
                  ) : item.to === "CANCELLED" ? (
                    <XCircle size={15} aria-hidden="true" />
                  ) : (
                    <Play size={15} aria-hidden="true" />
                  )}{" "}
                  {item.label}
                </button>
              ))}
              {onManage && (
                <button type="button" className="ac-secondary" onClick={onManage}>
                  <CalendarClock size={15} aria-hidden="true" /> Priority and due date
                </button>
              )}
            </div>
          )}
        </Panel>
      )}
      <Collapsed when={!!onSection} summary="Each step and the readiness checklist">
        <Panel
          eyebrow="Investigation progress"
          // Folded, the fold's own label names it (0.10.87).
          title={onSection ? "" : "Where this investigation stands"}
          source={readiness}
        >
          {!onSection && (
            <ol className="uw-stepper" aria-label="Investigation steps">
              {steps.map((step, index) => {
                const status = STEP_STATUS[step.status];
                return (
                  <li key={step.key} className={`uw-step tone-${status.tone}`}>
                    <button
                      type="button"
                      disabled={!step.destination}
                      onClick={() => step.destination && onStep(step.destination)}
                      aria-label={`${index + 1}. ${step.label}: ${status.label}${step.detail ? `. ${step.detail}` : ""}`}
                    >
                      <span className="uw-step-number" aria-hidden="true">
                        {index + 1}
                      </span>
                      <span className="uw-step-text">
                        <strong>{step.label}</strong>
                        <small>{status.label}</small>
                      </span>
                    </button>
                    {step.detail && <small className="uw-step-detail">{step.detail}</small>}
                  </li>
                );
              })}
            </ol>
          )}
          {onSection && (
            <ul className="uw-case-steps" aria-label="Investigation steps">
              {steps.map((step) => (
                <li key={step.key}>
                  <ToneBadge tone={STEP_STATUS[step.status].tone} label={STEP_STATUS[step.status].label} />
                  <span>
                    <strong>{step.label}</strong>
                    {step.detail && <small>{step.detail}</small>}
                    <WhyAsked why={CASE_STEP_WHY[step.key]} />
                  </span>
                </li>
              ))}
            </ul>
          )}
          <section className="ca-drawer-section">
            <h3>Readiness checklist</h3>
            <p className="ac-muted">{readinessHeadline(checks)}</p>
            {checks.length > 0 && (
              <details className="uw-more">
                <summary>Show each check ({checks.length})</summary>
                <ul className="uw-checklist" aria-label="Readiness checks">
                  {checks.map((check) => (
                    <li key={check.key}>
                      <ToneBadge tone={CHECK_RESULT[check.result].tone} label={CHECK_RESULT[check.result].label} />
                      <span>
                        <strong>{check.label}</strong>
                        {check.rationale && <small>{check.rationale}</small>}
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <p className="ac-note">Readiness shows what is in place and what is missing.</p>
          </section>
        </Panel>
      </Collapsed>
      {transition && (
        <TransitionDrawer
          investigationId={investigationId}
          label={label}
          transition={transition}
          onClose={() => setTransition(null)}
          onDone={() => {
            setTransition(null);
            readiness.reload();
            onChanged();
          }}
        />
      )}
    </>
  );
}

/** Ask for the reason of a state change, then send it; the server's refusal (an invalid change) is shown as said. */
function TransitionDrawer({
  investigationId,
  label,
  transition,
  onClose,
  onDone,
}: {
  investigationId: string;
  label: string;
  transition: CaseTransition;
  onClose: () => void;
  onDone: () => void;
}) {
  const { notify } = useWorkspace();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const problem = transitionProblem(reason);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      await send(transitionPath(investigationId), "POST", transitionBody(transition, reason));
      notify(`${label}: ${transition.label.toLowerCase()} recorded.`);
      onDone();
    } catch (failure) {
      setError(errorText(failure, "The investigation's state was not changed."));
      setBusy(false);
    }
  };
  return (
    <Drawer title={`${transition.label}: ${label}`} onClose={onClose}>
      <form className="ca-form ca-drawer-section" onSubmit={submit}>
        <label className="ca-field">
          {transition.prompt}
          <textarea
            required
            rows={3}
            maxLength={TRANSITION_REASON_MAX}
            value={reason}
            placeholder="At least 10 characters"
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        {reason.trim() && problem && <p className="ac-muted">{problem}</p>}
        <p className="ac-muted">Recorded in the investigation's history and the audit trail.</p>
        {error && (
          <p className="ac-message tone-critical" role="alert">
            {error}
          </p>
        )}
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Back
          </button>
          <button type="submit" className={transition.danger ? "ca-danger" : "ac-primary"} disabled={busy || !!problem}>
            {busy ? "Saving…" : transition.label}
          </button>
        </div>
      </form>
    </Drawer>
  );
}

/** The investigation's highlights on the new navigation: one card with its facts, its actions and its path. */
function CaseHighlights({
  row,
  label,
  readiness,
  actions,
  children,
}: {
  row: Record<string, any>;
  label: string;
  readiness: CaseReadiness | null | undefined;
  actions: ReactNode;
  children: ReactNode;
}) {
  const { work } = useWorkspace();
  const product = work.products.find((item) => item.id === String(row.product_id ?? work.productId ?? ""));
  const scope = useResource<{
    current?: { included_complaints?: unknown[]; lots?: Array<{ lot_identifier?: string | null }> } | null;
  }>(row.id ? `/api/v1/investigations/${encodeURIComponent(String(row.id))}/scope` : null);
  const complaints = scope.data?.current?.included_complaints?.length;
  const lotNames = (scope.data?.current?.lots ?? []).map((lot) => lot.lot_identifier).filter(Boolean);
  // The part of each lot that differs ("003 · 004", not "SAMPLE-ORBIT-300-LOT-003 · ..."), the full ones in the
  // tooltip (0.10.85, D3.9).
  const lots =
    lotNames.length > 3 ? `${lotNames.length} lots` : lotsText(lotNames as string[]).replace(/ and /g, " · ");
  const blocking = readinessChecks(readiness).filter(
    (check) => (check.result === "BLOCKED" || check.result === "PENDING") && check.key !== "decision",
  );
  return (
    <header className="uw-card uw-highlights" aria-label="The investigation at a glance">
      <div className="uw-hl-top">
        <div className="uw-hl-title">
          {/* The question is the investigation's name; its reference is the customer's own (0.10.85, D3.9, D3.12). */}
          <p className="ac-eyebrow">
            Investigation · {sourceId(row, "investigation_identifier") ?? label} ·{" "}
            {product?.name ?? "product not recorded"}
          </p>
          <h2 className="uw-case-question">{safeText(row.investigation_question) ?? "No question recorded."}</h2>
        </div>
        <div className="uw-cp-chips">
          <CaseStateBadge row={row} />
          {row.priority && <CasePriority priority={row.priority} />}
          <span className="ms-chip">
            <CaseDue row={row} />
          </span>
        </div>
      </div>
      <dl className="uw-hl-fields">
        <div>
          <dt>Owner</dt>
          <dd>{ownerText(row)}</dd>
        </div>
        <div>
          <dt>Complaints in scope</dt>
          <dd>
            {complaints ?? "—"}
            {/* Why it differs from the trend's count (0.10.82): every complaint linked, not the last 30 days. */}
            {complaints != null && <small> every complaint linked to it, not only the trend's recent ones</small>}
          </dd>
        </div>
        <div>
          <dt>Lots in scope</dt>
          <dd className="uw-mono" title={lotNames.join(", ")}>
            {lots || "—"}
          </dd>
        </div>
        <div>
          <dt>Blocking the decision</dt>
          <dd>{readiness ? (blocking.length ? blocking[0].label : "Nothing") : "…"}</dd>
        </div>
      </dl>
      {actions}
      {children}
    </header>
  );
}

/** "Open" link used by the case lists. */
export function OpenCaseLink({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" className="ac-link" onClick={onClick}>
      {label} <ChevronRight size={14} aria-hidden="true" />
    </button>
  );
}

/**
 * The investigation's one progress line (stage 8): Summary · Evidence · Decisions & actions · History, each with how
 * many of its steps are done, and the next step as the screen's main button (8.7). Each section opens on a click.
 */
export function CaseProgressLine({
  steps,
  onSection,
}: {
  steps: ReturnType<typeof caseSteps>;
  onSection: (section: CaseSection, part?: string) => void;
}) {
  // Its steps not read yet: say so (0.10.70: with none read, every section read "Done" and "Every step is done: the
  // decision is signed" on an investigation opened a moment ago).
  if (!steps.length)
    return (
      <nav className="uw-case-progress" aria-label="Where this investigation stands">
        <p className="ac-muted" role="status">
          Reading where this investigation stands…
        </p>
      </nav>
    );
  const progress = caseProgress(steps);
  const next = nextCaseStep(steps);
  return (
    <nav className="uw-case-progress" aria-label="Where this investigation stands">
      <ol>
        {progress.map((item) => (
          <li key={item.section} className={`state-${item.state.toLowerCase()}`}>
            <button
              type="button"
              aria-current={item.state === "CURRENT" ? "step" : undefined}
              onClick={() => onSection(item.section)}
            >
              <strong>{item.section}</strong>
              <small>
                {item.state === "DONE"
                  ? "Done"
                  : item.section === "History"
                    ? "Once the decision is signed"
                    : `${item.done} of ${item.total} done`}
              </small>
            </button>
          </li>
        ))}
      </ol>
      {next ? (
        <div>
          <button type="button" className="ac-primary" onClick={() => onSection(next.section, next.part)}>
            Next: {next.label} <ChevronRight size={15} aria-hidden="true" />
          </button>
          <WhyAsked why={CASE_STEP_WHY[next.key]} />
        </div>
      ) : (
        <p className="ac-muted">Every step is done: the decision is signed. Its record is in History.</p>
      )}
    </nav>
  );
}

/** On the new navigation the step list and the readiness checklist sit behind one line: the progress line leads. */
function Collapsed({ when, summary, children }: { when: boolean; summary: string; children: ReactNode }) {
  return when ? (
    <details className="uw-more uw-case-more">
      <summary>{summary}</summary>
      {children}
    </details>
  ) : (
    <>{children}</>
  );
}
