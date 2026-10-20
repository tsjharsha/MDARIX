import { useState, type FormEvent } from "react";
import { DoorOpen, Signpost, Undo2 } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { Drawer, errorText, send, useResource } from "../../customer-admin/shared";
import { formatDay } from "../../../app/dates";
import { NEXT_STEPS_LINK } from "../../help/trialNextSteps";

export type TrialExitRequest = {
  id: string;
  status: "PENDING" | "APPROVED" | "DECLINED" | "WITHDRAWN" | string;
  reason_code: string | null;
  reason_label: string | null;
  reason: string | null;
  delete_data: boolean;
  data_deleted: boolean;
  created_at: string | null;
  decided_at: string | null;
  decision_note: string | null;
};
type ExitState = { request: TrialExitRequest | null; is_owner: boolean; reasons: Record<string, string> };

export const EXIT_REQUEST_PATH = "/api/v1/trial/exit-request";

/** What the owner's latest request says to them: waiting, or not approved with the MDARIX team's note. */
export function exitRequestText(request: TrialExitRequest | null | undefined): string | null {
  if (!request) return null;
  const on = request.created_at ? ` on ${formatDay(request.created_at)}` : "";
  if (request.status === "PENDING")
    return `You asked to end the trial early${on}. The MDARIX team will confirm by email; until then the trial continues.`;
  if (request.status === "DECLINED")
    return `The MDARIX team has not ended the trial${request.decision_note ? `: ${request.decision_note}` : "."}`;
  return null;
}

/**
 * Ending the trial early (backend/app/trial/early_exit.py), for the person who started it: a request with an optional
 * reason and whether to delete the data. The MDARIX team confirms it; until then it can be withdrawn. `onNextSteps`
 * opens Next steps, for an owner who would rather continue with a pilot.
 */
export function EndTrialPanel({ onNextSteps }: { onNextSteps?: () => void } = {}) {
  const state = useResource<ExitState>(EXIT_REQUEST_PATH);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const data = state.data;
  if (!data?.is_owner) return null;
  const request = data.request;
  const pending = request?.status === "PENDING";
  const withdraw = async () => {
    setBusy(true);
    setError("");
    try {
      await send(`${EXIT_REQUEST_PATH}/withdraw`, "POST");
      state.reload();
    } catch (failure) {
      setError(errorText(failure, "The request could not be withdrawn. Please try again."));
    } finally {
      setBusy(false);
    }
  };
  const status = exitRequestText(request);
  return (
    <Panel eyebrow="Leaving early" title="End your trial early">
      <p className="uw-trial-note">
        If MDARIX is not for you right now, you can end the trial before its 30 days. Your request goes to the MDARIX
        team; once they confirm it, the trial ends and, if you ask, everything your organization stored in it is
        deleted. You will get an email either way.
      </p>
      {onNextSteps && (
        <p className="uw-trial-note">
          Would you rather continue on your real data?{" "}
          <button type="button" className="ac-link" onClick={onNextSteps}>
            <Signpost size={14} aria-hidden="true" /> {NEXT_STEPS_LINK}
          </button>
        </p>
      )}
      {status && (
        <p className={`uw-exit-status${pending ? " is-pending" : ""}`} role="status">
          {status}
        </p>
      )}
      {error && (
        <p className="uw-flag-critical" role="alert">
          {error}
        </p>
      )}
      <div className="ca-action-row">
        {pending ? (
          <button type="button" className="ac-secondary" onClick={() => void withdraw()} disabled={busy}>
            <Undo2 size={15} aria-hidden="true" /> {busy ? "Withdrawing…" : "Withdraw my request"}
          </button>
        ) : (
          <button type="button" className="ac-secondary uw-exit-button" onClick={() => setOpen(true)}>
            <DoorOpen size={15} aria-hidden="true" /> End my trial early
          </button>
        )}
      </div>
      {open && (
        <EndTrialForm
          reasons={data.reasons}
          onClose={() => setOpen(false)}
          onSent={() => {
            setOpen(false);
            state.reload();
          }}
        />
      )}
    </Panel>
  );
}

function EndTrialForm({
  reasons,
  onClose,
  onSent,
}: {
  reasons: Record<string, string>;
  onClose: () => void;
  onSent: () => void;
}) {
  const [reasonCode, setReasonCode] = useState("");
  const [reason, setReason] = useState("");
  const [deleteData, setDeleteData] = useState(true);
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!understood) return setError("Tick that you understand the trial cannot be restarted once it has ended.");
    setBusy(true);
    setError("");
    try {
      await send(EXIT_REQUEST_PATH, "POST", {
        reason_code: reasonCode || null,
        reason: reason.trim() || null,
        delete_data: deleteData,
      });
      onSent();
    } catch (failure) {
      setError(errorText(failure, "Your request was not sent. Please try again."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Drawer title="End your trial early" onClose={onClose}>
      <form className="ca-form" onSubmit={submit}>
        <section className="ca-drawer-section">
          <p>
            The MDARIX team confirms your request, usually within one business day, and emails you when the trial has
            ended.
          </p>
          <label className="ca-field">
            Why are you ending the trial? (optional)
            <select value={reasonCode} onChange={(event) => setReasonCode(event.target.value)}>
              <option value="">Choose a reason…</option>
              {Object.entries(reasons).map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="ca-field">
            Anything you would like us to know (optional)
            <textarea
              value={reason}
              maxLength={1000}
              rows={3}
              placeholder="For example: we need connections to our QMS before we can evaluate further."
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          <label className="ca-check">
            <input type="checkbox" checked={deleteData} onChange={(event) => setDeleteData(event.target.checked)} />{" "}
            Delete our data when the trial ends
          </label>
          <p className="ac-muted">
            {deleteData
              ? "Everything your organization stored in the trial is deleted, including your team's accounts. It cannot be recovered."
              : "Your data is kept for 30 days after the trial ends, in case you change your mind, then deleted."}
          </p>
          <label className="ca-check">
            <input type="checkbox" checked={understood} onChange={(event) => setUnderstood(event.target.checked)} /> I
            understand that once the MDARIX team confirms, the trial ends and cannot be restarted.
          </label>
          {error && (
            <p className="uw-flag-critical" role="alert">
              {error}
            </p>
          )}
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy}>
              {busy ? "Sending…" : "Send the request"}
            </button>
            <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
              Keep my trial
            </button>
          </div>
        </section>
      </form>
    </Drawer>
  );
}
