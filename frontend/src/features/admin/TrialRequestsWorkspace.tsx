import { useEffect, useState } from "react";
import { DialogBehaviour } from "../shared/DialogBehaviour";
import { Check, Copy, MailCheck, RefreshCw, Trash2, X } from "lucide-react";
import { requestJson } from "../../app/apiClient";
import { Table, idColumn } from "../customer-admin/shared";

type TrialRequest = {
  id: string;
  email: string;
  display_name: string;
  organization: string;
  status: "PENDING_REVIEW" | "APPROVED" | "DECLINED" | string;
  created_at: string | null;
  reviewed_at: string | null;
  decision_reason: string | null;
  tenant_key: string | null;
  tenant_identifier: string | null;
  trial_expires_at: string | null;
  data_delete_after: string | null;
  data_deleted: boolean;
  owner_status: string | null;
  // What the requester told MDARIX about their company and trial, as readable lines (trial/request_profile.py).
  profile?: { job_title?: string; country?: string; [key: string]: unknown };
  profile_lines?: { label: string; value: string }[];
};
type DueTrial = { tenant_id: string; tenant_key: string; name: string; trial_ended_at: string; delete_after: string };
type ReviewResult = TrialRequest & { email_delivery?: string; email_error?: string; activation_path?: string };

const FILTERS: [string, string][] = [
  ["PENDING_REVIEW", "Pending"],
  ["APPROVED", "Approved"],
  ["DECLINED", "Declined"],
];

const formatDate = (value: string | null) =>
  value ? new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—";

// Free-trial requests from the website. Approve creates the private 30-day trial workspace and sends the invitation.
export function TrialRequestsWorkspace() {
  const [items, setItems] = useState<TrialRequest[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [filter, setFilter] = useState("PENDING_REVIEW");
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<TrialRequest | null>(null);
  const [declining, setDeclining] = useState<TrialRequest | null>(null);
  const [retention, setRetention] = useState<DueTrial[] | null>(null);
  const [reason, setReason] = useState("");
  const [result, setResult] = useState<{ tone: "good" | "bad"; text: string; link?: string } | null>(null);

  const load = () => {
    setState("loading");
    requestJson<{ items: TrialRequest[]; counts: Record<string, number> }>("/api/v1/platform-admin/trial-requests")
      .then((data) => {
        setItems(data.items);
        setCounts(data.counts);
        setState("ready");
      })
      .catch(() => setState("error"));
  };
  useEffect(load, []);

  const act = async (row: TrialRequest, path: string, body?: object) => {
    setBusy(row.id);
    setResult(null);
    try {
      const data = await requestJson<ReviewResult>(`/api/v1/platform-admin/trial-requests/${row.id}/${path}`, {
        method: "POST",
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      const link = data.activation_path ? `${window.location.origin}${data.activation_path}` : undefined;
      const sent = data.email_delivery === "SENT";
      const created = path === "approve" ? `Trial workspace ${data.tenant_key} created for ${row.organization}. ` : "";
      setResult(
        path === "decline"
          ? { tone: "good", text: `Declined ${row.organization}.` }
          : sent
            ? { tone: "good", text: `${created}Invitation emailed to ${row.email}.` }
            : link
              ? {
                  tone: "good",
                  text: `${created}Email is not configured on this development server. Send ${row.email} this one-time activation link (valid 48 hours):`,
                  link,
                }
              : {
                  tone: "bad",
                  text: `${created}The invitation email to ${row.email} could not be sent${
                    data.email_error ? `: ${data.email_error}` : "."
                  } Fix the email settings, then use Resend invitation.`,
                },
      );
      load();
    } catch (error) {
      setResult({ tone: "bad", text: error instanceof Error ? error.message : "The request could not be completed." });
    } finally {
      setBusy(null);
      setConfirming(null);
      setDeclining(null);
      setReason("");
    }
  };

  const openRetention = async () => {
    setResult(null);
    try {
      const data = await requestJson<{ due: DueTrial[] }>("/api/v1/platform-admin/trial-retention");
      setRetention(data.due);
    } catch (error) {
      setResult({ tone: "bad", text: error instanceof Error ? error.message : "Retention could not be checked." });
    }
  };
  const runRetention = async () => {
    setBusy("retention");
    try {
      const data = await requestJson<{ purged: number }>("/api/v1/platform-admin/trial-retention/run", {
        method: "POST",
      });
      setResult({
        tone: "good",
        text: `Deleted the data of ${data.purged} closed trial${data.purged === 1 ? "" : "s"}.`,
      });
      load();
    } catch (error) {
      setResult({ tone: "bad", text: error instanceof Error ? error.message : "Trial data could not be deleted." });
    } finally {
      setBusy(null);
      setRetention(null);
    }
  };

  const rows = items.filter((item) => item.status === filter);
  return (
    <section className="platform-admin-card trial-queue" aria-labelledby="trial-queue-title">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Free trial requests</span>
          <h3 id="trial-queue-title">Website sign-ups waiting for review</h3>
          <p>
            Approve to create a private 30-day trial workspace with sample data and email the requester an invitation.
            Decline with a reason; nothing is created.
          </p>
        </div>
        <div className="trial-queue-head-actions">
          <button className="platform-admin-secondary" onClick={openRetention} disabled={busy !== null}>
            <Trash2 size={15} /> Delete expired trial data
          </button>
          <button className="platform-admin-secondary" onClick={load} disabled={state === "loading"}>
            <RefreshCw size={15} /> Refresh
          </button>
        </div>
      </div>

      <div className="trial-queue-filters" role="tablist" aria-label="Trial request status">
        {FILTERS.map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={filter === value}
            className={filter === value ? "is-active" : ""}
            onClick={() => setFilter(value)}
          >
            {label} <span>{counts[value] ?? 0}</span>
          </button>
        ))}
      </div>

      {result && (
        <div className={`trial-queue-result is-${result.tone}`} role="status">
          <p>{result.text}</p>
          {result.link && (
            <div className="trial-queue-link">
              <code>{result.link}</code>
              <button
                className="platform-admin-secondary"
                onClick={() => navigator.clipboard?.writeText(result.link ?? "")}
                aria-label="Copy activation link"
              >
                <Copy size={14} /> Copy
              </button>
            </div>
          )}
        </div>
      )}

      {state === "error" ? (
        <p className="trial-queue-empty">Trial requests could not be loaded. Refresh to try again.</p>
      ) : state === "loading" && !items.length ? (
        <p className="trial-queue-empty">Loading trial requests…</p>
      ) : rows.length === 0 ? (
        <p className="trial-queue-empty">
          {filter === "PENDING_REVIEW" ? "No requests are waiting for review." : "Nothing here yet."}
        </p>
      ) : (
        <Table
          caption="Trial requests"
          rows={rows}
          rowKey={(row) => row.id}
          empty={{ title: "Nothing here yet", detail: "Requests appear here as companies ask for a trial." }}
          columns={[
            idColumn("Request ID"),
            { key: "organization", label: "Company", render: (row) => <strong>{row.organization}</strong> },
            {
              key: "requester",
              label: "Requester",
              render: (row) => (
                <span className="cc-stack">
                  {row.display_name}
                  <small>{row.email}</small>
                  {Boolean(row.profile?.job_title || row.profile?.country) && (
                    <small>{[row.profile?.job_title, row.profile?.country].filter(Boolean).join(" · ")}</small>
                  )}
                </span>
              ),
            },
            {
              key: "answers",
              label: "About the request",
              render: (row) =>
                row.profile_lines?.length ? (
                  <details className="trial-queue-answers">
                    <summary>{row.profile_lines.length} answers</summary>
                    <dl>
                      {row.profile_lines.map((line) => (
                        <div key={line.label}>
                          <dt>{line.label}</dt>
                          <dd>{line.value}</dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                ) : (
                  <small>Not given (requested before these questions)</small>
                ),
            },
            { key: "requested", label: "Requested", render: (row) => formatDate(row.created_at) },
            {
              key: "outcome",
              label: filter === "APPROVED" ? "Workspace" : filter === "DECLINED" ? "Reason" : "Status",
              render: (row) =>
                row.status === "APPROVED" ? (
                  <span className="cc-stack">
                    {row.tenant_key}
                    {row.data_deleted ? (
                      <small>Trial data deleted</small>
                    ) : (
                      <small>
                        Trial ends {formatDate(row.trial_expires_at)} · data kept until{" "}
                        {formatDate(row.data_delete_after)}
                      </small>
                    )}
                  </span>
                ) : row.status === "DECLINED" ? (
                  (row.decision_reason ?? "—")
                ) : (
                  <span className="trial-queue-pill">Pending review</span>
                ),
            },
            {
              key: "actions",
              label: "",
              render: (row) => (
                <div className="trial-queue-actions">
                  {row.status === "PENDING_REVIEW" && (
                    <>
                      <button
                        className="platform-admin-primary"
                        disabled={busy !== null}
                        onClick={() => setConfirming(row)}
                      >
                        <Check size={14} /> Approve
                      </button>
                      <button
                        className="platform-admin-secondary"
                        disabled={busy !== null}
                        onClick={() => setDeclining(row)}
                      >
                        <X size={14} /> Decline
                      </button>
                    </>
                  )}
                  {row.status === "APPROVED" && row.owner_status === "INVITED" && !row.data_deleted && (
                    <button
                      className="platform-admin-secondary"
                      disabled={busy !== null}
                      onClick={() => act(row, "resend-invitation")}
                    >
                      <MailCheck size={14} /> Resend invitation
                    </button>
                  )}
                  {row.status === "APPROVED" && row.owner_status === "ACTIVE" && !row.data_deleted && (
                    <span className="trial-queue-pill is-active">Owner active</span>
                  )}
                </div>
              ),
            },
          ]}
        />
      )}

      {confirming && (
        <div className="trial-queue-dialog" role="dialog" aria-modal="true" aria-labelledby="trial-approve-title">
          <DialogBehaviour onClose={() => setConfirming(null)} />
          <div>
            <h4 id="trial-approve-title">Approve a free trial for {confirming.organization}?</h4>
            <p>This creates, in one step:</p>
            <ul>
              <li>a private trial workspace on the Free Trial plan (3 users, 5,000 uploaded rows)</li>
              <li>a 30-day trial that closes automatically</li>
              <li>the sample dataset</li>
              <li>an account for {confirming.email} and a one-time invitation valid for 48 hours</li>
            </ul>
            <div className="trial-queue-dialog-actions">
              <button className="platform-admin-secondary" onClick={() => setConfirming(null)}>
                Cancel
              </button>
              <button
                className="platform-admin-primary"
                disabled={busy !== null}
                onClick={() => act(confirming, "approve")}
              >
                {busy ? "Creating workspace…" : "Approve and create workspace"}
              </button>
            </div>
          </div>
        </div>
      )}

      {retention && (
        <div className="trial-queue-dialog" role="dialog" aria-modal="true" aria-labelledby="trial-retention-title">
          <DialogBehaviour onClose={() => setRetention(null)} />
          <div>
            <h4 id="trial-retention-title">Delete expired trial data</h4>
            {retention.length === 0 ? (
              <p>No closed trial has passed its 30-day retention period. Nothing will be deleted.</p>
            ) : (
              <>
                <p>
                  These trials closed more than 30 days ago. Their records and uploads are deleted, their users can no
                  longer sign in, and the workspace is archived. The audit trail is kept. This cannot be undone.
                </p>
                <ul>
                  {retention.map((trial) => (
                    <li key={trial.tenant_id}>
                      {trial.name} ({trial.tenant_key}), trial ended {formatDate(trial.trial_ended_at)}
                    </li>
                  ))}
                </ul>
              </>
            )}
            <div className="trial-queue-dialog-actions">
              <button className="platform-admin-secondary" onClick={() => setRetention(null)}>
                {retention.length ? "Cancel" : "Close"}
              </button>
              {retention.length > 0 && (
                <button className="platform-admin-primary" disabled={busy !== null} onClick={runRetention}>
                  {busy ? "Deleting…" : `Delete data of ${retention.length} trial${retention.length === 1 ? "" : "s"}`}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {declining && (
        <div className="trial-queue-dialog" role="dialog" aria-modal="true" aria-labelledby="trial-decline-title">
          <DialogBehaviour onClose={() => setDeclining(null)} />
          <form
            onSubmit={(event) => {
              event.preventDefault();
              act(declining, "decline", { reason: reason.trim() });
            }}
          >
            <h4 id="trial-decline-title">Decline the request from {declining.organization}?</h4>
            <label>
              Reason (kept for audit)
              <textarea
                required
                minLength={3}
                maxLength={500}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="For example: not a medical-device organization"
              />
            </label>
            <div className="trial-queue-dialog-actions">
              <button type="button" className="platform-admin-secondary" onClick={() => setDeclining(null)}>
                Cancel
              </button>
              <button
                type="submit"
                className="platform-admin-primary"
                disabled={busy !== null || reason.trim().length < 3}
              >
                Decline request
              </button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}
