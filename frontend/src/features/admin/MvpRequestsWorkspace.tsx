import { useEffect, useState } from "react";
import { Archive, PhoneCall, RefreshCw, RotateCcw } from "lucide-react";
import { requestJson } from "../../app/apiClient";
import { Table } from "../customer-admin/shared";
import { retentionText, type TrialRetention } from "./customers/trials";

export type MvpRequestItem = {
  id: string;
  status: "NEW" | "CONTACTED" | "CLOSED" | string;
  organization: string;
  tenant_business_id: string | null;
  requested_by: string | null;
  email: string;
  phone: string | null;
  contact_preference: string | null;
  expectations: string;
  scope: string | null;
  move_trial_data: boolean;
  days_left: number | null;
  created_at: string | null;
  updated_at: string | null;
  handled_at: string | null;
  note: string | null;
  /** When the trial's data is deleted; held while this request asks to move it (null once the trial is converted). */
  retention?: TrialRetention | null;
};

export const MVP_REQUESTS_PATH = "/api/v1/platform-admin/mvp-requests";

/** What the trial wants done with its data, in the MDARIX team's words. */
export const mvpDataText = (row: Pick<MvpRequestItem, "move_trial_data">) =>
  row.move_trial_data ? "Move the trial data into the pilot" : "Start the pilot without the trial data";

/** The request's other lines: what is in scope, how to reach the person, and the trial's days left. */
export function mvpRequestLines(row: Pick<MvpRequestItem, "days_left" | "scope" | "contact_preference">): string[] {
  const lines: string[] = [];
  if (row.scope) lines.push(`In scope: ${row.scope}`);
  if (row.contact_preference) lines.push(`Reach them: ${row.contact_preference}`);
  if (row.days_left !== null && row.days_left !== undefined)
    lines.push(`${row.days_left} ${row.days_left === 1 ? "day" : "days"} left in the trial`);
  return lines;
}

const FILTERS: [string, string][] = [
  ["NEW", "New"],
  ["CONTACTED", "Contacted"],
  ["CLOSED", "Closed"],
];

const formatDay = (value: string) =>
  new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

const formatDate = (value: string | null) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

// Requests for a pilot conversation, sent from Next steps inside free trials (backend/app/trial/mvp_request.py): what
// the organization expects, what is in scope, how to reach the person, and whether to move the trial data. Staff reply
// to arrange a scoping call, mark the request contacted, and close it when the conversation is over.
export function MvpRequestsWorkspace() {
  const [items, setItems] = useState<MvpRequestItem[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [filter, setFilter] = useState("NEW");
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<{ tone: "good" | "bad"; text: string } | null>(null);

  const load = () => {
    setState("loading");
    requestJson<{ items: MvpRequestItem[]; counts: Record<string, number> }>(MVP_REQUESTS_PATH)
      .then((data) => {
        setItems(data.items);
        setCounts(data.counts);
        setState("ready");
      })
      .catch(() => setState("error"));
  };
  useEffect(load, []);

  const move = async (row: MvpRequestItem, status: string) => {
    setBusy(row.id);
    setResult(null);
    try {
      await requestJson(`${MVP_REQUESTS_PATH}/${row.id}/status`, { method: "POST", body: JSON.stringify({ status }) });
      // Closing a request that held the trial data lets its deletion resume, after a grace period (retention.py).
      const released = status === "CLOSED" && row.retention?.held_for_mvp_request;
      setResult({
        tone: "good",
        text: `${row.organization}: marked ${status.toLowerCase()}.${released ? " Its trial data is no longer held; the new deletion date is shown below." : ""}`,
      });
      load();
    } catch (error) {
      setResult({ tone: "bad", text: error instanceof Error ? error.message : "The request could not be updated." });
    } finally {
      setBusy(null);
    }
  };

  const rows = items.filter((item) => item.status === filter);
  return (
    <section className="platform-admin-card trial-queue" aria-labelledby="mvp-queue-title">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Pilot requests</span>
          <h3 id="mvp-queue-title">Free trials that asked for a pilot conversation</h3>
          <p>
            Reply to each requester to arrange a scoping call, then mark the request contacted. Close it when the
            conversation is over; the organization can then ask again. Prices go only in the written proposal. While a
            request that asks to move the trial data is open, that data is not deleted; closing it lets the deletion
            resume.
          </p>
        </div>
        <div className="trial-queue-head-actions">
          <button className="platform-admin-secondary" onClick={load} disabled={state === "loading"}>
            <RefreshCw size={15} /> Refresh
          </button>
        </div>
      </div>

      {/* A choice, not a third row of tabs under the trial section's own (UX2). */}
      <label className="trial-queue-show">
        <span>Show</span>
        <select value={filter} onChange={(event) => setFilter(event.target.value)}>
          {FILTERS.map(([value, label]) => (
            <option key={value} value={value}>
              {label} ({counts[value] ?? 0})
            </option>
          ))}
        </select>
      </label>

      {result && (
        <div className={`trial-queue-result is-${result.tone}`} role="status">
          <p>{result.text}</p>
        </div>
      )}

      {state === "error" ? (
        <p className="trial-queue-empty">Pilot requests could not be loaded. Refresh to try again.</p>
      ) : state === "loading" && !items.length ? (
        <p className="trial-queue-empty">Loading pilot requests…</p>
      ) : rows.length === 0 ? (
        <p className="trial-queue-empty">{filter === "NEW" ? "No new pilot requests." : "Nothing here yet."}</p>
      ) : (
        <Table
          caption="Pilot requests"
          rows={rows}
          rowKey={(row) => row.id}
          empty={{ title: "Nothing here yet", detail: "Requests appear here as free trials ask for a pilot." }}
          columns={[
            {
              key: "organization",
              label: "Organization",
              render: (row) => (
                <span className="cc-stack">
                  <strong>{row.organization}</strong>
                  {row.tenant_business_id && <small>{row.tenant_business_id}</small>}
                </span>
              ),
            },
            {
              key: "expectations",
              label: "What they expect",
              render: (row) => (
                <span className="cc-stack">
                  <span>{row.expectations}</span>
                  {mvpRequestLines(row).map((line) => (
                    <small key={line}>{line}</small>
                  ))}
                </span>
              ),
            },
            {
              key: "data",
              label: "Trial data",
              render: (row) => (
                <span className="cc-stack">
                  <span>{mvpDataText(row)}</span>
                  {row.retention && <small>{retentionText(row.retention, formatDay)}</small>}
                </span>
              ),
            },
            {
              key: "contact",
              label: "Contact",
              render: (row) => (
                <span className="cc-stack">
                  <span>{row.requested_by ?? "—"}</span>
                  <a href={`mailto:${row.email}`}>{row.email}</a>
                  <small>
                    {row.phone ? <a href={`tel:${row.phone.replace(/[^\d+]/g, "")}`}>{row.phone}</a> : "No phone given"}
                  </small>
                </span>
              ),
            },
            { key: "requested", label: "Requested", render: (row) => formatDate(row.created_at) },
            {
              key: "handled",
              label: filter === "NEW" ? "Status" : "Updated",
              render: (row) =>
                row.status === "NEW" ? <span className="trial-queue-pill">New</span> : formatDate(row.handled_at),
            },
            {
              key: "actions",
              label: "",
              render: (row) => (
                <div className="trial-queue-actions">
                  {row.status === "NEW" && (
                    <button
                      className="platform-admin-primary"
                      disabled={busy !== null}
                      onClick={() => move(row, "CONTACTED")}
                    >
                      <PhoneCall size={14} /> Mark contacted
                    </button>
                  )}
                  {row.status !== "CLOSED" && (
                    <button
                      className="platform-admin-secondary"
                      disabled={busy !== null}
                      onClick={() => move(row, "CLOSED")}
                    >
                      <Archive size={14} /> Close
                    </button>
                  )}
                  {row.status === "CLOSED" && (
                    <button
                      className="platform-admin-secondary"
                      disabled={busy !== null}
                      onClick={() => move(row, "NEW")}
                    >
                      <RotateCcw size={14} /> Reopen
                    </button>
                  )}
                </div>
              ),
            },
          ]}
        />
      )}
    </section>
  );
}
