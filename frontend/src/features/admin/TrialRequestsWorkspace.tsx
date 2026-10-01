import { useEffect, useState } from "react";
import { Check, Copy, MailCheck, RefreshCw, X } from "lucide-react";
import { requestJson } from "../../app/apiClient";

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
};
type ReviewResult = TrialRequest & { email_delivery?: string; activation_path?: string };

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
      setResult({
        tone: "good",
        text:
          path === "decline"
            ? `Declined ${row.organization}.`
            : `${path === "approve" ? `Trial workspace ${data.tenant_key} created for ${row.organization}. ` : ""}${
                sent
                  ? `Invitation emailed to ${row.email}.`
                  : `Email is not configured on this server. Send ${row.email} this one-time activation link (valid 72 hours):`
              }`,
        link: sent ? undefined : link,
      });
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
        <button className="platform-admin-secondary" onClick={load} disabled={state === "loading"}>
          <RefreshCw size={15} /> Refresh
        </button>
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
        <div className="trial-queue-table-wrap">
          <table className="trial-queue-table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Requester</th>
                <th>Requested</th>
                <th>{filter === "APPROVED" ? "Workspace" : filter === "DECLINED" ? "Reason" : "Status"}</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.organization}</strong>
                  </td>
                  <td>
                    {row.display_name}
                    <small>{row.email}</small>
                  </td>
                  <td>{formatDate(row.created_at)}</td>
                  <td>
                    {row.status === "APPROVED" ? (
                      <>
                        {row.tenant_key}
                        <small>Trial ends {formatDate(row.trial_expires_at)}</small>
                      </>
                    ) : row.status === "DECLINED" ? (
                      (row.decision_reason ?? "—")
                    ) : (
                      <span className="trial-queue-pill">Pending review</span>
                    )}
                  </td>
                  <td>
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
                      {row.status === "APPROVED" && (
                        <button
                          className="platform-admin-secondary"
                          disabled={busy !== null}
                          onClick={() => act(row, "resend-invitation")}
                        >
                          <MailCheck size={14} /> Resend invitation
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {confirming && (
        <div className="trial-queue-dialog" role="dialog" aria-modal="true" aria-labelledby="trial-approve-title">
          <div>
            <h4 id="trial-approve-title">Approve a free trial for {confirming.organization}?</h4>
            <p>This creates, in one step:</p>
            <ul>
              <li>a private trial workspace on the Free Trial plan (3 users, 5,000 uploaded rows)</li>
              <li>a 30-day trial that closes automatically</li>
              <li>the sample dataset</li>
              <li>an account for {confirming.email} and a one-time invitation valid for 72 hours</li>
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

      {declining && (
        <div className="trial-queue-dialog" role="dialog" aria-modal="true" aria-labelledby="trial-decline-title">
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
