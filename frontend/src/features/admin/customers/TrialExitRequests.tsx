import { useState } from "react";
import { Panel, ToneBadge } from "../console/charts";
import type { Tone } from "../console/dashboardModel";
import { Drawer, Table, errorText, formatDate, send, useResource } from "../../customer-admin/shared";

export type TrialExitItem = {
  id: string;
  status: string;
  reason_code: string | null;
  reason_label: string | null;
  reason: string | null;
  delete_data: boolean;
  data_deleted: boolean;
  created_at: string | null;
  decided_at: string | null;
  decision_note: string | null;
  organization: string;
  trial_tenant_id: string;
  tenant_business_id: string | null;
  tenant_status: string | null;
  requested_by: string | null;
  days_left: number | null;
};

export const TRIAL_EXIT_PATH = "/api/v1/platform-admin/trial-exit-requests";

/** A request's state as a badge: waiting for a decision, ended (data deleted or kept), declined, withdrawn. */
export function exitState(item: Pick<TrialExitItem, "status" | "data_deleted">): { label: string; tone: Tone } {
  if (item.status === "PENDING") return { label: "Waiting for you", tone: "warning" };
  if (item.status === "APPROVED")
    return item.data_deleted
      ? { label: "Ended, data deleted", tone: "good" }
      : { label: "Ended, data kept 30 days", tone: "neutral" };
  if (item.status === "DECLINED") return { label: "Declined", tone: "neutral" };
  return { label: "Withdrawn", tone: "neutral" };
}

/** Why the organization is leaving, in one line: the reason chosen, then its own words. */
export function exitWhy(item: Pick<TrialExitItem, "reason_label" | "reason">): string {
  return [item.reason_label, item.reason].filter(Boolean).join(": ") || "No reason given";
}

type Decision = { item: TrialExitItem; kind: "approve" | "decline" | "delete" };

/**
 * Requests from free trials to end early (backend/app/trial/early_exit.py). Approving ends the trial now and, when
 * chosen, deletes its data at once; declining keeps it running and emails the owner the note. A trial ended with its
 * data kept can have the data deleted here before the usual 30 days.
 */
export function TrialExitRequests({ onChanged }: { onChanged: () => void }) {
  const requests = useResource<{ items: TrialExitItem[]; pending: number }>(TRIAL_EXIT_PATH);
  const [deciding, setDeciding] = useState<Decision | null>(null);
  const items = requests.data?.items ?? [];
  if (requests.state === "ready" && !items.length) return null;
  const pending = requests.data?.pending ?? 0;
  return (
    <Panel
      eyebrow="Leaving early"
      title={pending ? `Requests to end a trial early · ${pending} waiting` : "Requests to end a trial early"}
      source={requests}
    >
      <Table<TrialExitItem>
        caption="Requests to end a trial early"
        rows={items}
        rowKey={(row) => row.id}
        empty={{ title: "No requests", detail: "No free trial has asked to end early." }}
        columns={[
          {
            key: "organization",
            label: "Organization",
            render: (row) => (
              <span>
                <strong>{row.organization}</strong>
                {row.tenant_business_id && <small className="ac-muted"> · {row.tenant_business_id}</small>}
              </span>
            ),
          },
          { key: "asked", label: "Asked", render: (row) => (row.created_at ? formatDate(row.created_at) : "—") },
          { key: "by", label: "By", render: (row) => row.requested_by ?? "—" },
          { key: "why", label: "Why", render: (row) => exitWhy(row) },
          { key: "data", label: "Their data", render: (row) => (row.delete_data ? "Delete it" : "Keep it 30 days") },
          { key: "left", label: "Days left", render: (row) => (row.days_left ?? "—").toString() },
          {
            key: "state",
            label: "State",
            render: (row) => {
              const state = exitState(row);
              return <ToneBadge tone={state.tone} label={state.label} />;
            },
          },
          {
            key: "actions",
            label: " ",
            render: (row) =>
              row.status === "PENDING" ? (
                <span className="ca-action-row">
                  <button
                    type="button"
                    className="ac-primary"
                    onClick={() => setDeciding({ item: row, kind: "approve" })}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className="ac-secondary"
                    onClick={() => setDeciding({ item: row, kind: "decline" })}
                  >
                    Decline
                  </button>
                </span>
              ) : row.status === "APPROVED" && !row.data_deleted && row.tenant_status !== "ARCHIVED" ? (
                <button
                  type="button"
                  className="ac-secondary"
                  onClick={() => setDeciding({ item: row, kind: "delete" })}
                >
                  Delete data now
                </button>
              ) : null,
          },
        ]}
      />
      {deciding && (
        <DecisionDrawer
          decision={deciding}
          onClose={() => setDeciding(null)}
          onDone={() => {
            setDeciding(null);
            requests.reload();
            onChanged();
          }}
        />
      )}
    </Panel>
  );
}

function DecisionDrawer({
  decision,
  onClose,
  onDone,
}: {
  decision: Decision;
  onClose: () => void;
  onDone: () => void;
}) {
  const { item, kind } = decision;
  const [deleteData, setDeleteData] = useState(item.delete_data);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async () => {
    if (kind === "decline" && note.trim().length < 10)
      return setError("Write a short note to the trial owner (10 characters or more).");
    setBusy(true);
    setError("");
    try {
      if (kind === "approve")
        await send(`${TRIAL_EXIT_PATH}/${item.id}/approve`, "POST", {
          delete_data: deleteData,
          note: note.trim() || null,
        });
      else if (kind === "decline") await send(`${TRIAL_EXIT_PATH}/${item.id}/decline`, "POST", { note: note.trim() });
      else await send(`${TRIAL_EXIT_PATH}/${item.id}/delete-data`, "POST");
      onDone();
    } catch (failure) {
      setError(errorText(failure, "That did not work. Nothing was changed; please try again."));
    } finally {
      setBusy(false);
    }
  };
  const title =
    kind === "approve"
      ? `End ${item.organization}'s trial`
      : kind === "decline"
        ? `Keep ${item.organization}'s trial running`
        : `Delete ${item.organization}'s trial data`;
  return (
    <Drawer title={title} onClose={onClose}>
      <section className="ca-drawer-section">
        <p>
          <b>Why:</b> {exitWhy(item)}
        </p>
        <p>
          <b>They asked to:</b> {item.delete_data ? "delete their data" : "keep their data for 30 days"}.
        </p>
        {kind === "approve" && (
          <>
            <p>The trial ends now: nobody in the organization can sign in to it any more.</p>
            <label className="ca-check">
              <input type="checkbox" checked={deleteData} onChange={(event) => setDeleteData(event.target.checked)} />{" "}
              Delete the trial&apos;s data now
            </label>
            <p className="ac-muted">
              {deleteData
                ? "Every record, upload and file is deleted and the team's accounts are made anonymous; only a minimal record that the trial existed is kept. This cannot be undone."
                : "The data is kept for 30 days after today, then deleted by the retention run (or here, with Delete data now)."}
            </p>
            <label className="ca-field">
              Internal note (optional)
              <input value={note} maxLength={500} onChange={(event) => setNote(event.target.value)} />
            </label>
            <p className="ac-muted">
              The owner is emailed that the trial has ended and asked, by reply, why they left.
            </p>
          </>
        )}
        {kind === "decline" && (
          <label className="ca-field">
            Note to the trial owner (emailed and shown in their Getting started)
            <textarea
              value={note}
              rows={3}
              maxLength={500}
              placeholder="For example: we would like a short call first; could you reply with a time that suits?"
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
        )}
        {kind === "delete" && (
          <p>
            Every record, upload and file of this ended trial is deleted now instead of after 30 days, and the
            team&apos;s accounts are made anonymous. This cannot be undone. The owner is emailed that the data was
            deleted.
          </p>
        )}
        {error && (
          <p className="uw-flag-critical" role="alert">
            {error}
          </p>
        )}
        <div className="ca-action-row">
          <button type="button" className="ac-primary" onClick={() => void submit()} disabled={busy}>
            {busy
              ? "Working…"
              : kind === "approve"
                ? deleteData
                  ? "End the trial and delete its data"
                  : "End the trial"
                : kind === "decline"
                  ? "Keep the trial running"
                  : "Delete the data"}
          </button>
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
        </div>
      </section>
    </Drawer>
  );
}
