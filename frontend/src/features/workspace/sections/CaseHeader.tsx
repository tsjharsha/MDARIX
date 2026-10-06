import { useState } from "react";
import { CalendarClock, ChevronRight, Pause, Play, XCircle } from "lucide-react";
import { Panel, ToneBadge } from "../../admin/console/charts";
import { Drawer, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { displayId, safeText } from "../../../app/displayId";
import { useCan, useWorkspace } from "../workspaceContext";
import {
  CHECK_RESULT,
  STEP_STATUS,
  TRANSITION_REASON_MAX,
  caseDueState,
  casePriorityLabel,
  caseStateLabel,
  caseStateTone,
  caseSteps,
  caseTransitions,
  readinessChecks,
  readinessHeadline,
  readinessPath,
  transitionBody,
  transitionPath,
  transitionProblem,
  type CaseReadiness,
  type CaseTransition,
  type CaseWorkflowFields,
  type StepDestination,
} from "../caseWorkflow";
import { priorityTone } from "../tasks";
import { StatusBadge } from "./common";

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
const ownerText = (row: Record<string, unknown> | null | undefined) =>
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
  onStep,
  onChanged,
}: {
  investigationId: string;
  row: Record<string, any> | null | undefined;
  /** Opens the manage drawer (priority, due date, owner); absent for a role that may not change the case. */
  onManage?: () => void;
  onStep: (destination: StepDestination) => void;
  onChanged: () => void;
}) {
  const canWork = useCan("investigation.work");
  const canAssign = useCan("investigation.assign");
  const readiness = useResource<CaseReadiness>(readinessPath(investigationId));
  const [transition, setTransition] = useState<CaseTransition | null>(null);
  const current: Record<string, any> = {
    ...(row ?? {}),
    workflow_state: row?.workflow_state ?? readiness.data?.workflow_state ?? null,
  };
  const transitions = caseTransitions(current, { work: canWork, assign: canAssign });
  const steps = caseSteps(readiness.data);
  const checks = readinessChecks(readiness.data);
  const label = displayId(current, "investigation_identifier", "Investigation");
  return (
    <>
      <Panel eyebrow="Case" title={label} action={<CaseStateBadge row={current} />}>
        <p className="uw-case-question">{safeText(current.investigation_question) ?? "No question recorded."}</p>
        <dl className="ca-facts">
          <div>
            <dt>State</dt>
            <dd>{caseStateLabel(current) ?? safeText(current.status) ?? "—"}</dd>
          </div>
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
      <Panel eyebrow="Case progress" title="Where this case stands" source={readiness}>
        <ol className="uw-stepper" aria-label="Case steps">
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
        <section className="ca-drawer-section">
          <h3>Readiness checklist</h3>
          <p className="ac-muted">{readinessHeadline(checks)}</p>
          {checks.length > 0 && (
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
          )}
          <p className="ac-note">
            Readiness shows what is in place and what is missing. It never decides the case: authorized people do.
          </p>
        </section>
      </Panel>
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
      setError(errorText(failure, "The case's state was not changed."));
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
        <p className="ac-muted">Recorded in the case's history and the audit trail.</p>
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

/** "Open" link used by the case lists. */
export function OpenCaseLink({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" className="ac-link" onClick={onClick}>
      {label} <ChevronRight size={14} aria-hidden="true" />
    </button>
  );
}
