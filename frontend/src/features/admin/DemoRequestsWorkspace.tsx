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
  // md44: a request booked from inside a free trial names the organization, the times that suit and its progress.
  source?: "WEBSITE" | "TRIAL" | string;
  organization?: string | null;
  preferred_time?: string | null;
  context?: {
    chapters_tried?: number;
    chapters_total?: number;
    days_left?: number;
    own_data?: boolean;
    focus?: string[];
  } | null;
};

/** Where a request came from, in one line: the website, or a trial with its organization. */
export const demoSourceText = (row: Pick<DemoRequest, "source" | "organization">) =>
  row.source === "TRIAL" ? `Free trial${row.organization ? `: ${row.organization}` : ""}` : "Website";

/** A trial request's context in short lines: when suits, how far the trial got, what to focus on, the note. */
export function demoContextLines(row: Pick<DemoRequest, "source" | "preferred_time" | "context" | "note">): string[] {
  if (row.source !== "TRIAL") return row.note ? [row.note] : [];
  const lines: string[] = [];
  if (row.preferred_time) lines.push(`Suits: ${row.preferred_time}`);
  const context = row.context ?? {};
  if (context.chapters_total)
    lines.push(
      `${context.chapters_tried ?? 0} of ${context.chapters_total} story chapters tried` +
        (context.days_left !== undefined ? `, ${context.days_left} days left` : "") +
        (context.own_data ? ", own data uploaded" : ""),
    );
  if (context.focus?.length) lines.push(`Focus: ${context.focus.join("; ")}`);
  if (row.note) lines.push(`Note: ${row.note}`);
  return lines;
}

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

/** The requests the panel lists: every one while the website offers demo requests; otherwise only those booked from
 * free trials (a website request can no longer be made), with their counts by status. */
export function shownDemoRequests<T extends Pick<DemoRequest, "source" | "status">>(
  items: T[],
  websiteRequests: boolean,
) {
  const shown = websiteRequests ? items : items.filter((item) => item.source === "TRIAL");
  const counts: Record<string, number> = {};
  for (const item of shown) counts[item.status] = (counts[item.status] ?? 0) + 1;
  return { items: shown, counts };
}

// Demo requests from the website (name, work email, phone) and from inside free trials (the organization, the times
// that suit and how far into the story the trial went). Staff contact the requester and record the outcome.
// 0.10.44: while the website offers no demo request (`websiteRequests` false: app/featureSet.ts
// websiteDemoRequestsOffered) the panel lists only the trials' one-to-one demo requests, and is not shown until one
// arrives: Platform Admin showed an empty "Website visitors who asked for a demo" panel.
export function DemoRequestsWorkspace({ websiteRequests = true }: { websiteRequests?: boolean }) {
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
        const shown = shownDemoRequests(data.items, websiteRequests);
        setItems(shown.items);
        setCounts(websiteRequests ? data.counts : shown.counts);
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
  // Without website requests, nothing to show until a free trial books a demo (a failed read still says so).
  if (!websiteRequests && !items.length && state !== "error") return null;
  return (
    <section className="platform-admin-card trial-queue" aria-labelledby="demo-queue-title">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Demo requests</span>
          <h3 id="demo-queue-title">
            {websiteRequests ? "Website visitors who asked for a demo" : "Free trials that asked for a one-to-one demo"}
          </h3>
          <p>
            {websiteRequests
              ? "Contact each requester by email or phone to arrange the demo, then mark the request contacted."
              : "Booked from a trial's Getting started. Contact the requester to agree a time, then mark the request contacted."}{" "}
            Close it when the demo has happened or the requester is not a fit.
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
          empty={{
            title: "Nothing here yet",
            detail: websiteRequests
              ? "Requests appear here as visitors ask for a demo."
              : "Requests appear here as free trials book a demo.",
          }}
          columns={[
            idColumn("Request ID"),
            { key: "name", label: "Name", render: (row) => <strong>{row.name}</strong> },
            {
              key: "source",
              label: "From",
              render: (row) => (
                <span className="cc-stack">
                  <span>{demoSourceText(row)}</span>
                  {demoContextLines(row).map((line) => (
                    <small key={line}>{line}</small>
                  ))}
                </span>
              ),
            },
            {
              key: "contact",
              label: "Contact",
              render: (row) => (
                <span className="cc-stack">
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
