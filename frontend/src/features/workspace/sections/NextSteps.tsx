import { useState } from "react";
import { ArrowRight, ChevronRight } from "lucide-react";
import { ApiError } from "../../../app/apiClient";
import { Empty, Panel } from "../../admin/console/charts";
import { Drawer, errorText, listOf, send, useResource } from "../../customer-admin/shared";
import { safeText } from "../../../app/displayId";
import { WORKFLOW_ROLE_CODES, roleLabel } from "../../../app/roles";
import { unknownSetFrom } from "../../investigator/savedResults";
import { sectionAllowed, useCan, useWorkspace } from "../workspaceContext";
import { localDay } from "../workspaceModel";
import { CASE_PRIORITIES, casePriorityLabel } from "../caseWorkflow";
import { REQUEST_TITLE_MAX } from "../evidenceWorkflow";
import { BRIEF_TAB } from "../decisionBrief";
import {
  NEXT_STEP_REASON_MAX,
  emptyNextStep,
  nextStepBody,
  nextStepForm,
  nextStepOptions,
  nextStepOptionsPath,
  nextStepProblem,
  nextStepResultText,
  nextStepsPath,
  type ChangeForm,
  type NextStepInput,
  type NextStepOption,
} from "../nextSteps";
import type { NewRequestForm } from "../evidenceWorkflow";

type Person = { id: string; business_id?: string | null; display_name?: string | null };

/**
 * The investigator's next steps for a case (Decisions › Decision center), offered by the server: continue, wait,
 * request a risk or regulatory review, ask for more evidence or testing, review a supplier or product change, or
 * escalate for a quality review through the Decision Brief. Each step asks for a reason; none of them decides the case.
 * Shown only to people who work investigations; hidden when the server says the role may not.
 */
export function NextStepsPanel({ investigationId }: { investigationId: string }) {
  const canWork = useCan("investigation.work");
  if (!canWork) return null;
  return <NextSteps investigationId={investigationId} />;
}

function NextSteps({ investigationId }: { investigationId: string }) {
  const { session, open } = useWorkspace();
  const options = useResource<unknown>(nextStepOptionsPath(investigationId));
  const [chosen, setChosen] = useState<NextStepOption | null>(null);
  if (options.state === "forbidden") return null;
  const steps = nextStepOptions(options.data);
  const canOpenInvestigations = sectionAllowed(
    "Investigations",
    session?.allowed_menu,
    session?.business_permissions,
    session?.sample_only,
  );
  const choose = (step: NextStepOption) => {
    if (nextStepForm(step.action) === "brief") {
      open("Investigations", BRIEF_TAB);
      return;
    }
    setChosen(step);
  };
  return (
    <Panel eyebrow="Next steps" title="What happens next with this investigation" source={options}>
      <p className="ac-muted">
        Choose how the work moves on. A next step records your reason and routes the work. A decision on the
        investigation is prepared through the Decision Brief.
      </p>
      {steps.length ? (
        <ul className="uw-list" aria-label="Next steps">
          {steps.map((step) => (
            <li key={step.action}>
              <span>
                <strong>{step.label}</strong>
                {step.description && <small>{step.description}</small>}
                {!step.available && step.reason && <small className="uw-flag-warning">{step.reason}</small>}
              </span>
              {nextStepForm(step.action) === "brief" ? (
                canOpenInvestigations && (
                  <button type="button" className="ac-link" onClick={() => choose(step)}>
                    Open the Decision Brief <ChevronRight size={14} aria-hidden="true" />
                  </button>
                )
              ) : (
                <button
                  type="button"
                  className="ac-secondary"
                  disabled={!step.available}
                  title={!step.available ? (step.reason ?? "Not available for this investigation now") : undefined}
                  onClick={() => choose(step)}
                >
                  Choose <ArrowRight size={14} aria-hidden="true" />
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <Empty
          title="No next steps right now"
          detail="Nothing is suggested for this investigation at the moment. Next steps appear here as the investigation moves on."
        />
      )}
      {chosen && (
        <NextStepDrawer
          investigationId={investigationId}
          step={chosen}
          onClose={() => setChosen(null)}
          onDone={() => {
            setChosen(null);
            options.reload();
          }}
          onOpenBrief={() => {
            setChosen(null);
            open("Investigations", BRIEF_TAB);
          }}
        />
      )}
    </Panel>
  );
}

/** The small form of one step: a reason, plus the details its kind needs. */
function NextStepDrawer({
  investigationId,
  step,
  onClose,
  onDone,
  onOpenBrief,
}: {
  investigationId: string;
  step: NextStepOption;
  onClose: () => void;
  onDone: () => void;
  onOpenBrief: () => void;
}) {
  const { notify } = useWorkspace();
  const form = nextStepForm(step.action);
  const [input, setInput] = useState<NextStepInput>(emptyNextStep);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [touched, setTouched] = useState(false);
  const problem = nextStepProblem(step.action, input, localDay());
  const setRequest = (change: Partial<NewRequestForm>) =>
    setInput((value) => ({ ...value, request: { ...value.request, ...change } }));
  const setChange = (change: Partial<ChangeForm>) =>
    setInput((value) => ({ ...value, change: { ...value.change, ...change } }));
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await send(nextStepsPath(investigationId), "POST", nextStepBody(step.action, input));
      notify(nextStepResultText(step.label, response));
      onDone();
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "USE_DECISION_BRIEF") {
        notify("Escalation for a quality review goes through the Decision Brief.");
        onOpenBrief();
        return;
      }
      setError(errorText(failure, "The next step was not recorded."));
      setBusy(false);
    }
  };
  return (
    <Drawer title={step.label} onClose={onClose}>
      <form className="ca-form ca-drawer-section" onSubmit={submit}>
        {step.description && <p className="ac-muted">{step.description}</p>}
        <label className="ca-field">
          Reason (kept in the investigation's history)
          <textarea
            required
            rows={3}
            maxLength={NEXT_STEP_REASON_MAX}
            value={input.reason}
            placeholder="At least 10 characters"
            onChange={(event) => setInput((value) => ({ ...value, reason: event.target.value }))}
          />
        </label>
        {form === "review" && (
          <p className="ac-muted">
            The review goes to the reviewers' queue. They see the investigation's context and record their own outcome.
          </p>
        )}
        {form === "request" && (
          <RequestFields investigationId={investigationId} form={input.request} set={setRequest} />
        )}
        {form === "change" && <ChangeFields form={input.change} set={setChange} />}
        {(touched || input.reason.trim()) && problem && <p className="uw-hint">{problem}</p>}
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
            {busy ? "Saving…" : `Record: ${step.label}`}
          </button>
        </div>
      </form>
    </Drawer>
  );
}

/** The fields of the New request drawer (Phase 3), for a request to a colleague or a role queue. */
function RequestFields({
  investigationId,
  form,
  set,
}: {
  investigationId: string;
  form: NewRequestForm;
  set: (change: Partial<NewRequestForm>) => void;
}) {
  const people = useResource<Person[]>(form.recipientMode === "person" ? "/api/v1/investigation-assignees" : null);
  const unknowns = useResource<unknown>(`/api/v1/investigations/${encodeURIComponent(investigationId)}/unknowns`);
  const unknownRows = unknownSetFrom(unknowns.data)?.unknowns ?? [];
  return (
    <>
      <div className="ca-chips" role="radiogroup" aria-label="Ask">
        {(["person", "role"] as const).map((mode) => (
          <button
            type="button"
            role="radio"
            key={mode}
            aria-checked={form.recipientMode === mode}
            className={form.recipientMode === mode ? "selected" : ""}
            onClick={() => set({ recipientMode: mode })}
          >
            {mode === "person" ? "A person" : "A role queue"}
          </button>
        ))}
      </div>
      {form.recipientMode === "person" ? (
        <label className="ca-field">
          Person
          <select value={form.recipientUserId} onChange={(event) => set({ recipientUserId: event.target.value })}>
            <option value="">{people.state === "loading" ? "Loading…" : "Choose a person"}</option>
            {listOf(people.data).map((person: Person) => (
              <option key={person.id} value={person.id}>
                {safeText(person.display_name) ?? "Person"}
                {safeText(person.business_id) ? ` (${person.business_id})` : ""}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <label className="ca-field">
          Role queue
          <select value={form.recipientRole} onChange={(event) => set({ recipientRole: event.target.value })}>
            <option value="">Choose a role</option>
            {WORKFLOW_ROLE_CODES.map((code) => (
              <option key={code} value={code}>
                {roleLabel(code)}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="ca-field">
        What you need
        <input
          required
          maxLength={REQUEST_TITLE_MAX}
          value={form.title}
          placeholder="e.g. Seal hardness test results for lot KS-5521"
          onChange={(event) => set({ title: event.target.value })}
        />
      </label>
      <label className="ca-field">
        Documents, data or tests requested (one per line)
        <textarea required rows={3} value={form.items} onChange={(event) => set({ items: event.target.value })} />
      </label>
      <label className="ca-field">
        Unknown it would resolve (optional)
        <select value={form.unknownId} onChange={(event) => set({ unknownId: event.target.value })}>
          <option value="">
            {unknowns.state === "loading"
              ? "Loading…"
              : unknownRows.length
                ? "Not tied to an unknown"
                : "No unknowns recorded for this investigation"}
          </option>
          {unknownRows.map((row) => (
            <option key={row.unknown_id} value={row.unknown_id}>
              {safeText(row.business_id) ?? "Unknown"} · {row.statement}
            </option>
          ))}
        </select>
      </label>
      <div className="ca-form-grid">
        <label className="ca-field">
          Due (optional)
          <input
            type="date"
            value={form.dueDay}
            min={localDay()}
            onChange={(event) => set({ dueDay: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Priority
          <select value={form.priority} onChange={(event) => set({ priority: event.target.value })}>
            {CASE_PRIORITIES.map((priority) => (
              <option key={priority} value={priority}>
                {casePriorityLabel(priority)}
              </option>
            ))}
          </select>
        </label>
      </div>
    </>
  );
}

/** Who reviews a supplier or product change (optional: a person or a role queue) and what to call it. */
function ChangeFields({ form, set }: { form: ChangeForm; set: (change: Partial<ChangeForm>) => void }) {
  const people = useResource<Person[]>(form.mode === "person" ? "/api/v1/investigation-assignees" : null);
  return (
    <>
      <div className="ca-chips" role="radiogroup" aria-label="Assign the review to">
        {(["none", "person", "role"] as const).map((mode) => (
          <button
            type="button"
            role="radio"
            key={mode}
            aria-checked={form.mode === mode}
            className={form.mode === mode ? "selected" : ""}
            onClick={() => set({ mode })}
          >
            {mode === "none" ? "The default queue" : mode === "person" ? "A person" : "A role queue"}
          </button>
        ))}
      </div>
      {form.mode === "person" && (
        <label className="ca-field">
          Person
          <select value={form.assigneeUserId} onChange={(event) => set({ assigneeUserId: event.target.value })}>
            <option value="">{people.state === "loading" ? "Loading…" : "Choose a person"}</option>
            {listOf(people.data).map((person: Person) => (
              <option key={person.id} value={person.id}>
                {safeText(person.display_name) ?? "Person"}
                {safeText(person.business_id) ? ` (${person.business_id})` : ""}
              </option>
            ))}
          </select>
        </label>
      )}
      {form.mode === "role" && (
        <label className="ca-field">
          Role queue
          <select value={form.assignedRole} onChange={(event) => set({ assignedRole: event.target.value })}>
            <option value="">Choose a role</option>
            {WORKFLOW_ROLE_CODES.map((code) => (
              <option key={code} value={code}>
                {roleLabel(code)}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="ca-field">
        Title (optional)
        <input
          maxLength={REQUEST_TITLE_MAX}
          value={form.title}
          onChange={(event) => set({ title: event.target.value })}
        />
      </label>
    </>
  );
}
