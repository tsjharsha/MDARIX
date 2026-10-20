import { useState } from "react";
import { CheckCircle2, Inbox, Mail } from "lucide-react";
import { Panel, StatTile } from "../console/charts";
import { ConfirmDialog, Table, formatDate, send, useResource, type Confirmation } from "../../customer-admin/shared";
import { StatusBadge } from "../customers/StatusBadge";
import { Banner, Intro, TenantCell, type BannerMessage } from "./common";

/** One problem report as GET /api/v1/platform-admin/support/problems lists it (backend/app/support_api.py). */
export type ProblemReport = {
  id: string;
  business_id: string | null;
  tenant_name: string | null;
  tenant_business_id: string | null;
  reporter: string | null;
  reporter_business_id: string | null;
  summary: string;
  details: string;
  path: string | null;
  request_id: string | null;
  status: "OPEN" | "CLOSED";
  created_at: string | null;
  closed_at: string | null;
  resolution: string | null;
};

type Listing = { items: ProblemReport[]; counts: { OPEN: number; CLOSED: number } };
type Filter = "OPEN" | "CLOSED" | "";

const FILTERS: Array<[Filter, string]> = [
  ["OPEN", "Open"],
  ["CLOSED", "Closed"],
  ["", "All"],
];

/** A reply to the person who sent the report, in the administrator's own mail program (FUN-07). The subject names
 * the report, so the answer can be found again. Null when the reporter's address is not known. */
export function replyLink(report: ProblemReport): string | null {
  const address = (report.reporter ?? "").trim();
  if (!address.includes("@") || /[\s,;<>?&]/.test(address)) return null;
  const subject = `Re: ${report.business_id ?? "Your problem report"}: ${report.summary}`;
  const body = `Hello,\n\nThank you for reporting "${report.summary}" in MDARIX.\n\n`;
  return `mailto:${address}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

/**
 * Problems reported from the help menu of a signed-in screen (FUN-07). Until 0.10.37 they reached the MDARIX team only
 * as an email to the support mailbox; here every report is listed, can be answered by email, and is closed with what
 * was done, which the customer's audit trail records.
 */
export function ProblemReports() {
  const [filter, setFilter] = useState<Filter>("OPEN");
  const list = useResource<Listing>(`/api/v1/platform-admin/support/problems${filter ? `?status=${filter}` : ""}`);
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [message, setMessage] = useState<BannerMessage>(null);
  const counts = list.data?.counts;
  const close = (report: ProblemReport) =>
    setConfirm({
      title: `Close ${report.business_id ?? "this report"}?`,
      body: "Write what was done, for example the answer you sent or the fix. The customer's audit trail keeps it.",
      confirmLabel: "Close report",
      reason: { label: "What was done", min: 3 },
      run: (resolution) => send(`/api/v1/platform-admin/support/problems/${report.id}/close`, "POST", { resolution }),
      done: `${report.business_id ?? "The report"} is closed.`,
    });
  return (
    <div className="ac-grid">
      <Intro>
        People report a problem from the help menu of any signed-in screen. Each report is also emailed to the support
        mailbox, and a reply to that email reaches the person who sent it.
      </Intro>
      <section className="ac-stats ar-stats-4" aria-label="Problem reports">
        <StatTile
          label="Open"
          value={counts ? counts.OPEN : null}
          detail="Waiting for an answer"
          icon={<Inbox size={18} />}
          tone={counts?.OPEN ? "warning" : "good"}
        />
        <StatTile
          label="Closed"
          value={counts ? counts.CLOSED : null}
          detail="Answered or fixed"
          icon={<CheckCircle2 size={18} />}
        />
      </section>
      <Panel
        eyebrow="Support"
        title="Problem reports"
        state={list.state}
        error={list.error}
        requestId={list.requestId}
        onRetry={list.reload}
        action={
          <span className="ca-action-row" role="group" aria-label="Show">
            {FILTERS.map(([value, label]) => (
              <button
                key={label}
                type="button"
                className={filter === value ? "ac-primary" : "ac-secondary"}
                aria-pressed={filter === value}
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
          </span>
        }
      >
        <Banner message={message} onDismiss={() => setMessage(null)} />
        <Table
          caption="Problem reports"
          rows={list.data?.items ?? []}
          rowKey={(row) => row.id}
          pageSize={25}
          pageNoun="report"
          empty={{
            title: filter === "OPEN" ? "No open problem reports" : "No problem reports",
            detail: "A report sent from the help menu appears here within seconds.",
          }}
          columns={[
            {
              key: "business_id",
              label: "Report ID",
              render: (row) => row.business_id ?? "—",
              sortValue: (row) => row.business_id,
            },
            {
              key: "created_at",
              label: "Received",
              render: (row) => formatDate(row.created_at),
              sortValue: (row) => row.created_at,
            },
            {
              key: "tenant",
              label: "Organization",
              render: (row) => <TenantCell row={row} />,
              fields: ["tenant_name", "tenant_business_id"],
            },
            { key: "reporter", label: "Reported by", render: (row) => row.reporter ?? "Unknown" },
            {
              key: "summary",
              label: "Problem",
              render: (row) => (
                <span className="cc-stack">
                  <strong>{row.summary}</strong>
                  <small className="ar-problem-details">{row.details}</small>
                  {row.path && <small>Page: {row.path}</small>}
                  {row.request_id && <small>Reference: {row.request_id}</small>}
                  {row.status === "CLOSED" && row.resolution && <small>Done: {row.resolution}</small>}
                </span>
              ),
              fields: ["summary", "details", "path", "request_id", "resolution"],
            },
            {
              key: "status",
              label: "Status",
              render: (row) => <StatusBadge status={row.status} />,
              sortValue: (row) => row.status,
            },
            {
              key: "actions",
              label: "",
              render: (row) => {
                const reply = replyLink(row);
                return (
                  <span className="ca-action-row">
                    {reply && (
                      <a className="ac-link" href={reply}>
                        <Mail size={14} aria-hidden="true" /> Reply by email
                      </a>
                    )}
                    {row.status === "OPEN" && (
                      <button type="button" className="ac-link" onClick={() => close(row)}>
                        <CheckCircle2 size={14} aria-hidden="true" /> Close
                      </button>
                    )}
                  </span>
                );
              },
            },
          ]}
        />
      </Panel>
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(text) => {
          setConfirm(null);
          setMessage({ text, tone: "good" });
          list.reload();
        }}
      />
    </div>
  );
}
