import { useState } from "react";
import { Trash2 } from "lucide-react";
import { requestJson } from "../../../app/apiClient";
import { DialogBehaviour } from "../../shared/DialogBehaviour";
import { formatDate } from "../../customer-admin/shared";

/** A closed trial past its 30 days (backend/app/trial/retention.py trials_due); a held one is kept by the run. */
export type DueTrial = {
  tenant_id: string;
  tenant_business_id?: string | null;
  tenant_key: string;
  name: string;
  trial_ended_at: string;
  delete_after?: string;
  earliest_deletion?: string | null;
  hold_reason?: string | null;
  legal_hold?: boolean;
  held_for_mvp_request?: boolean;
  hold_until?: string;
};

/** Why a due trial is kept by the run, or null when it is deleted. */
export const keptBecause = (trial: Pick<DueTrial, "legal_hold" | "held_for_mvp_request" | "hold_until">) =>
  trial.legal_hold
    ? "under a legal hold"
    : trial.held_for_mvp_request
      ? `held for its pilot request${trial.hold_until ? ` until ${new Date(trial.hold_until).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })} at the latest` : ""}`
      : null;

/**
 * "Run deletion now" (Trial organizations › Ending and deletion): runs the nightly retention job at once
 * (POST /platform-admin/trial-retention/run). The dialog lists what will be deleted and what a hold keeps.
 */
export function RunDeletionNow({
  due,
  onDone,
  initiallyOpen = false,
}: {
  due: DueTrial[];
  /** Called with a message after the run (or its failure). */
  onDone: (text: string, tone: "good" | "critical") => void;
  /** Opens with the dialog shown (tests). */
  initiallyOpen?: boolean;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  const [busy, setBusy] = useState(false);
  const deleting = due.filter((trial) => !keptBecause(trial));
  const kept = due.filter((trial) => keptBecause(trial));
  const run = async () => {
    setBusy(true);
    try {
      const data = await requestJson<{ purged: number }>("/api/v1/platform-admin/trial-retention/run", {
        method: "POST",
      });
      onDone(`Deleted the data of ${data.purged} closed trial${data.purged === 1 ? "" : "s"}.`, "good");
    } catch (error) {
      onDone(error instanceof Error ? error.message : "Trial data could not be deleted.", "critical");
    } finally {
      setBusy(false);
      setOpen(false);
    }
  };
  return (
    <>
      <button type="button" className="ac-secondary" onClick={() => setOpen(true)} disabled={busy}>
        <Trash2 size={15} aria-hidden="true" /> Run deletion now
      </button>
      {open && (
        <div className="trial-queue-dialog" role="dialog" aria-modal="true" aria-labelledby="trial-retention-title">
          <DialogBehaviour onClose={() => setOpen(false)} />
          <div>
            <h4 id="trial-retention-title">Run deletion now</h4>
            {deleting.length === 0 ? (
              <p>No closed trial is due for deletion. Nothing will be deleted.</p>
            ) : (
              <>
                <p>
                  These trials closed more than 30 days ago. Their records and uploads are deleted, their users can no
                  longer sign in, and the workspace is archived. The audit trail is kept. This cannot be undone.
                </p>
                <ul>
                  {deleting.map((trial) => (
                    <li key={trial.tenant_id}>
                      {trial.name} ({trial.tenant_key}), trial ended {formatDate(trial.trial_ended_at)}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {kept.length > 0 && (
              <>
                <p>Kept for now:</p>
                <ul>
                  {kept.map((trial) => (
                    <li key={trial.tenant_id}>
                      {trial.name} ({trial.tenant_key}), {keptBecause(trial)}
                    </li>
                  ))}
                </ul>
              </>
            )}
            <div className="trial-queue-dialog-actions">
              <button type="button" className="platform-admin-secondary" onClick={() => setOpen(false)}>
                {deleting.length ? "Cancel" : "Close"}
              </button>
              {deleting.length > 0 && (
                <button type="button" className="platform-admin-primary" disabled={busy} onClick={run}>
                  {busy ? "Deleting…" : `Delete data of ${deleting.length} trial${deleting.length === 1 ? "" : "s"}`}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
