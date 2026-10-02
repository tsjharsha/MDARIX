import { useMemo, useState } from "react";
import { Activity, Database, Inbox, Mail, ServerCog, TriangleAlert } from "lucide-react";
import { Panel, StatTile } from "../console/charts";
import { SearchBox, Table, formatDate, useResource } from "../../customer-admin/shared";
import { titleCase } from "../customers/model";
import { StatusBadge } from "../customers/StatusBadge";
import { Intro, TenantCell } from "./common";

type Ops = {
  database: string;
  worker_heartbeat: string;
  worker?: {
    state: "RUNNING" | "STOPPED" | "NOT_REPORTED";
    last_seen_at: string | null;
    seconds_since: number | null;
    started_at: string | null;
    metrics?: {
      cycles?: number;
      published?: number;
      failed?: number;
      dead_lettered?: number;
      report_jobs?: { claimed?: number; ready?: number; failed?: number };
    };
  };
  queue: {
    pending: number;
    retrying: number;
    dead_lettered: number;
    published: number;
    oldest_pending_at: string | null;
    pending_by_event: Array<{ event: string; pending: number }>;
  };
  provisioning_jobs: {
    by_status: Record<string, number>;
    recent: Array<{
      id: string;
      job_identifier: string;
      status: string;
      retry_count: number;
      created_at?: string | null;
      completed_at?: string | null;
      tenant_name?: string | null;
      tenant_key?: string | null;
      customer_name?: string | null;
    }>;
  };
  email: {
    configured: boolean;
    present: Record<string, boolean>;
    sender_domain_verified: boolean;
    reminders_pending: number;
    reminder_delivery: string;
  };
};

export function Operations({ section }: { section: string }) {
  if (section === "Queues & jobs") return <Queues />;
  if (section === "Email & notifications") return <Email />;
  if (section === "Developer API") return <DeveloperApi />;
  return <Health />;
}

const useOps = () => useResource<Ops>("/api/v1/platform-admin/console/operations");

/** Is the platform up: database, background work and email, at a glance. */
function Health() {
  const ops = useOps();
  const ready = useResource<{ status: string; database?: string }>("/health/ready");
  const data = ops.data;
  return (
    <div className="ac-grid">
      <section className="ac-stats ar-stats-4" aria-label="System health">
        <StatTile
          label="Application"
          value={ready.data ? titleCase(ready.data.status) : ready.state === "error" ? "Not ready" : null}
          detail="Accepting requests"
          icon={<ServerCog size={18} />}
          tone={ready.data?.status === "ready" ? "good" : ready.state === "error" ? "critical" : undefined}
        />
        <StatTile
          label="Database"
          value={data ? (data.database === "OK" ? "Reachable" : "Unavailable") : null}
          detail="Primary database"
          icon={<Database size={18} />}
          tone={data ? (data.database === "OK" ? "good" : "critical") : undefined}
        />
        <StatTile
          label="Waiting work"
          value={data ? data.queue.pending : null}
          detail={data?.queue.dead_lettered ? `${data.queue.dead_lettered} gave up after retries` : "Nothing stuck"}
          icon={<Inbox size={18} />}
          tone={data ? (data.queue.dead_lettered ? "critical" : data.queue.pending ? "warning" : "good") : undefined}
        />
        <StatTile
          label="Email"
          value={data ? (data.email.configured ? "Configured" : "Not configured") : null}
          detail="Invitations and password resets"
          icon={<Mail size={18} />}
          tone={data ? (data.email.configured ? "good" : "warning") : undefined}
        />
      </section>
      <Panel eyebrow="Background worker" title="Worker" state={ops.state} error={ops.error}>
        <WorkerStatus worker={data?.worker} />
        {data?.queue.oldest_pending_at && (
          <p>
            Oldest waiting item: <strong>{formatDate(data.queue.oldest_pending_at)}</strong>
          </p>
        )}
      </Panel>
    </div>
  );
}

const sinceText = (seconds: number | null) =>
  seconds === null
    ? ""
    : seconds < 60
      ? `${seconds} second${seconds === 1 ? "" : "s"} ago`
      : seconds < 3600
        ? `${Math.floor(seconds / 60)} minute${seconds < 120 ? "" : "s"} ago`
        : `${Math.floor(seconds / 3600)} hour${seconds < 7200 ? "" : "s"} ago`;

/** Whether the background worker runs (from the heartbeat it records every few seconds) and what it has done. */
function WorkerStatus({ worker }: { worker: Ops["worker"] }) {
  if (!worker || worker.state === "NOT_REPORTED")
    return (
      <Intro>
        The background worker has not reported a heartbeat. It sends queued work (integration records, report jobs) and
        records a heartbeat every few seconds while it runs. Start it with{" "}
        <code>docker compose up -d mdarix-outbox-worker</code>.
      </Intro>
    );
  const running = worker.state === "RUNNING";
  const metrics = worker.metrics ?? {};
  const reports = metrics.report_jobs ?? {};
  return (
    <>
      <Intro>
        {running
          ? "The background worker is running: it sends queued work and produces requested reports every few seconds."
          : "The background worker has stopped: no heartbeat for over a minute, so queued work and reports wait. Restart it with docker compose up -d mdarix-outbox-worker."}
      </Intro>
      <section className="ac-stats ar-stats-4" aria-label="Background worker">
        <StatTile
          label="State"
          value={running ? "Running" : "Stopped"}
          detail={`Last heartbeat ${sinceText(worker.seconds_since)}`}
          icon={<Activity size={18} />}
          tone={running ? "good" : "critical"}
        />
        <StatTile
          label="Running since"
          value={worker.started_at ? formatDate(worker.started_at) : null}
          detail={`${(metrics.cycles ?? 0).toLocaleString()} cycles`}
          icon={<ServerCog size={18} />}
        />
        <StatTile
          label="Sent"
          value={metrics.published ?? 0}
          detail={`${metrics.failed ?? 0} attempts failed, ${metrics.dead_lettered ?? 0} gave up (since start)`}
          icon={<Inbox size={18} />}
          tone={metrics.dead_lettered ? "warning" : "good"}
        />
        <StatTile
          label="Reports in last cycle"
          value={reports.ready ?? 0}
          detail={`${reports.claimed ?? 0} picked up, ${reports.failed ?? 0} failed`}
          icon={<Database size={18} />}
          tone={reports.failed ? "warning" : "good"}
        />
      </section>
    </>
  );
}

/** Background work waiting, retrying or given up, and recent tenant provisioning. */
function Queues() {
  const ops = useOps();
  const data = ops.data;
  return (
    <div className="ac-grid">
      <section className="ac-stats ar-stats-4" aria-label="Queue">
        <StatTile
          label="Waiting"
          value={data ? data.queue.pending : null}
          detail="Not yet processed"
          icon={<Inbox size={18} />}
        />
        <StatTile
          label="Retrying"
          value={data ? data.queue.retrying : null}
          detail="Failed once, will try again"
          icon={<TriangleAlert size={18} />}
          tone={data?.queue.retrying ? "warning" : "good"}
        />
        <StatTile
          label="Gave up"
          value={data ? data.queue.dead_lettered : null}
          detail="Needs someone to look"
          icon={<TriangleAlert size={18} />}
          tone={data?.queue.dead_lettered ? "critical" : "good"}
        />
        <StatTile
          label="Done"
          value={data ? data.queue.published : null}
          detail="Processed"
          icon={<ServerCog size={18} />}
        />
      </section>
      <div className="ac-grid two">
        <Panel eyebrow="Queue" title="Waiting work by kind" state={ops.state} error={ops.error}>
          <Table
            caption="Waiting work by kind"
            rows={data?.queue.pending_by_event ?? []}
            rowKey={(row) => row.event}
            empty={{ title: "Nothing waiting", detail: "All background work is processed." }}
            columns={[
              { key: "kind", label: "Kind", render: (row) => titleCase(row.event) },
              { key: "count", label: "Waiting", numeric: true, render: (row) => row.pending },
            ]}
          />
        </Panel>
        <Panel eyebrow="Tenant setup" title="Provisioning jobs" state={ops.state} error={ops.error}>
          <Table
            caption="Provisioning jobs"
            rows={data?.provisioning_jobs.recent ?? []}
            rowKey={(row) => row.id}
            empty={{ title: "No jobs yet", detail: "Onboarding a customer creates a provisioning job." }}
            columns={[
              { key: "tenant", label: "Tenant", render: (row) => <TenantCell row={row} /> },
              { key: "started", label: "Started", render: (row) => formatDate(row.created_at) },
              { key: "retries", label: "Retries", numeric: true, render: (row) => row.retry_count },
              { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
            ]}
          />
        </Panel>
      </div>
    </div>
  );
}

const SMTP_SETTINGS: Array<[string, string]> = [
  ["host", "Mail server"],
  ["username", "User name"],
  ["password", "Password"],
  ["sender", "Sender address"],
];

/** Whether MDARIX can send email, and what is waiting to be sent. */
function Email() {
  const ops = useOps();
  const email = ops.data?.email;
  return (
    <div className="ac-grid two">
      <Panel eyebrow="Outgoing email" title="Email delivery" state={ops.state} error={ops.error}>
        <Intro>
          {email?.configured
            ? "Email is configured: invitations and password resets are sent."
            : "Email is not configured: invitations and password resets are created but not sent."}
        </Intro>
        <dl className="cc-details">
          {SMTP_SETTINGS.map(([key, label]) => (
            <div key={key}>
              <dt>{label}</dt>
              <dd>{email?.present?.[key] ? "Set" : "Missing"}</dd>
            </div>
          ))}
          <div>
            <dt>Sender domain</dt>
            <dd>{email?.sender_domain_verified ? "Verified" : "Not verified"}</dd>
          </div>
        </dl>
        <p className="ac-muted">Settings live in the server environment; values are never shown.</p>
      </Panel>
      <Panel eyebrow="Renewal reminders" title="Reminder emails" state={ops.state} error={ops.error}>
        <p>
          <strong>{email?.reminders_pending ?? 0}</strong> reminders are queued.
        </p>
        <p className="ar-notice" role="note">
          <Mail size={16} aria-hidden="true" /> Sending queued renewal reminders is not connected yet, so customers do
          not receive them. Schedules and wording are set per tenant under Plans &amp; Licensing, Reminders.
        </p>
      </Panel>
    </div>
  );
}

type Operation = { method: string; path: string; summary?: string; tag: string };

/** The platform's HTTP API, grouped by area and searchable. */
function DeveloperApi() {
  const contract = useResource<{
    info?: { title?: string; version?: string };
    paths?: Record<string, Record<string, any>>;
  }>("/api/v1/platform-admin/api-contract");
  const [query, setQuery] = useState("");
  const operations = useMemo<Operation[]>(() => {
    const rows: Operation[] = [];
    Object.entries(contract.data?.paths ?? {}).forEach(([path, methods]) =>
      Object.entries(methods).forEach(([method, detail]) => {
        if (!["get", "post", "put", "patch", "delete"].includes(method)) return;
        rows.push({ method: method.toUpperCase(), path, summary: detail?.summary, tag: detail?.tags?.[0] ?? "Other" });
      }),
    );
    return rows.sort((a, b) => a.tag.localeCompare(b.tag) || a.path.localeCompare(b.path));
  }, [contract.data]);
  const term = query.trim().toLowerCase();
  const shown = term
    ? operations.filter((row) =>
        `${row.method} ${row.path} ${row.summary ?? ""} ${row.tag}`.toLowerCase().includes(term),
      )
    : operations;
  return (
    <Panel
      eyebrow={contract.data?.info ? `${contract.data.info.title ?? "API"} ${contract.data.info.version ?? ""}` : "API"}
      title="Developer API"
      state={contract.state}
      error={contract.error}
    >
      <Intro>
        {operations.length} operations. Every call needs a signed-in session and is limited to the caller&apos;s tenant
        unless it is a platform administration call.
      </Intro>
      <div className="cc-toolbar">
        <SearchBox value={query} onChange={setQuery} label="Search path, method or area" />
      </div>
      <Table
        caption="API operations"
        rows={shown.slice(0, 50)}
        rowKey={(row) => `${row.method} ${row.path}`}
        empty={{ title: "No matching operation", detail: "Change the search." }}
        columns={[
          { key: "area", label: "Area", render: (row) => row.tag },
          {
            key: "method",
            label: "Method",
            render: (row) => <code className={`ar-method ar-${row.method.toLowerCase()}`}>{row.method}</code>,
          },
          {
            key: "path",
            label: "Path",
            render: (row) => (
              <span className="cc-stack">
                <code>{row.path}</code>
                {row.summary && <small>{row.summary}</small>}
              </span>
            ),
          },
        ]}
      />
      {shown.length > 50 && (
        <p className="ac-muted">
          Showing 50 of {shown.length}. Search by path, method or area (for example &quot;subscription&quot;) to narrow
          the list.
        </p>
      )}
    </Panel>
  );
}
