import { useEffect, useState } from "react";
import { Archive, PhoneCall, RefreshCw, RotateCcw } from "lucide-react";
import { requestJson } from "../../app/apiClient";
import { Table, idColumn } from "../customer-admin/shared";

type DemoRequest = {
  id: string;
  name: string;
  email: string;
  phone: string;
  status: "NEW" | "CONTACTED" | "CLOSED" | string;
  created_at: string | null;
  handled_at: string | null;
  note: string | null;
};

const FILTERS: [string, string][] = [
  ["NEW", "New"],
  ["CONTACTED", "Contacted"],
  ["CLOSED", "Closed"],
];

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

// Demo requests from the website: name, work email and phone. Staff contact the requester and record the outcome.
export function DemoRequestsWorkspace() {
  const [items, setItems] = useState<DemoRequest[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [filter, setFilter] = useState("NEW");
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<{ tone: "good" | "bad"; text: string } | null>(null);

  const load = () => {
    setState("loading");
    requestJson<{ items: DemoRequest[]; counts: Record<string, number> }>("/api/v1/platform-admin/demo-requests")
      .then((data) => {
        setItems(data.items);
        setCounts(data.counts);
        setState("ready");
      })
      .catch(() => setState("error"));
  };
  useEffect(load, []);

  const move = async (row: DemoRequest, status: string) => {
    setBusy(row.id);
    setResult(null);
    try {
      await requestJson(`/api/v1/platform-admin/demo-requests/${row.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      setResult({ tone: "good", text: `${row.name}: marked ${status.toLowerCase()}.` });
      load();
    } catch (error) {
      setResult({ tone: "bad", text: error instanceof Error ? error.message : "The request could not be updated." });
    } finally {
      setBusy(null);
    }
  };

  const rows = items.filter((item) => item.status === filter);
  return (
    <section className="platform-admin-card trial-queue" aria-labelledby="demo-queue-title">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Demo requests</span>
          <h3 id="demo-queue-title">Website visitors who asked for a demo</h3>
          <p>
            Contact each requester by email or phone to arrange the demo, then mark the request contacted. Close it when
            the demo has happened or the requester is not a fit.
          </p>
        </div>
        <div className="trial-queue-head-actions">
          <button className="platform-admin-secondary" onClick={load} disabled={state === "loading"}>
            <RefreshCw size={15} /> Refresh
          </button>
        </div>
      </div>

      <div className="trial-queue-filters" role="tablist" aria-label="Demo request status">
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
        </div>
      )}

      {state === "error" ? (
        <p className="trial-queue-empty">Demo requests could not be loaded. Refresh to try again.</p>
      ) : state === "loading" && !items.length ? (
        <p className="trial-queue-empty">Loading demo requests…</p>
      ) : rows.length === 0 ? (
        <p className="trial-queue-empty">{filter === "NEW" ? "No new demo requests." : "Nothing here yet."}</p>
      ) : (
        <Table
          caption="Demo requests"
          rows={rows}
          rowKey={(row) => row.id}
          empty={{ title: "Nothing here yet", detail: "Requests appear here as visitors ask for a demo." }}
          columns={[
            idColumn("Request ID"),
            { key: "name", label: "Name", render: (row) => <strong>{row.name}</strong> },
            {
              key: "contact",
              label: "Contact",
              render: (row) => (
                <span className="cc-stack">
                  <a href={`mailto:${row.email}`}>{row.email}</a>
                  <small>
                    <a href={`tel:${row.phone.replace(/[^\d+]/g, "")}`}>{row.phone}</a>
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
