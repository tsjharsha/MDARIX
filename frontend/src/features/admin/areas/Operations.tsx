import { useMemo, useState } from "react";
import { Activity, Database, Inbox, Mail, RotateCcw, ServerCog, Trash2, TriangleAlert } from "lucide-react";
import { Panel, StatTile } from "../console/charts";
import {
  ConfirmDialog,
  SearchBox,
  Table,
  formatDate,
  send,
  useResource,
  type Confirmation,
} from "../../customer-admin/shared";
import { displayCode } from "../customers/model";
import { StatusBadge } from "../customers/StatusBadge";
import { Banner, Intro, TenantCell, type BannerMessage } from "./common";
import { ProblemReports } from "./ProblemReports";

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
    reminders_dead_lettered?: number;
    reminder_delivery: string;
  };
};

export function Operations({ section }: { section: string }) {
  if (section === "Queues & jobs") return <Queues />;
  if (section === "Email & notifications") return <Email />;
  if (section === "Problem reports") return <ProblemReports />;
  if (section === "Developer API") return <DeveloperApi />;
  if (section === "Tenant cells") return <Cells />;
  return <Health />;
}

/**
 * The Application tile from /health/status: ok and degraded answer 200, down answers 503 (which arrives as a failed
 * request). A request that fails for another reason is "Unknown", not "Down".
 */
export function applicationHealth(
  state: "loading" | "ready" | "error" | "forbidden",
  status: string | undefined,
): { value: string | null; detail: string; tone?: "good" | "warning" | "critical" } {
  if (state === "loading") return { value: null, detail: "Checking" };
  const word = String(status ?? "").toLowerCase();
  if (state === "ready" && word === "ok") return { value: "OK", detail: "Accepting requests", tone: "good" };
  if (state === "ready" && word === "degraded")
    return { value: "Degraded", detail: "Serving requests; a supporting service needs attention", tone: "warning" };
  if (state === "error") return { value: "Down", detail: "Not accepting requests", tone: "critical" };
  return { value: "Unknown", detail: "The status could not be read", tone: "warning" };
}

const useOps = () => useResource<Ops>("/api/v1/platform-admin/console/operations");

/** Is the platform up: database, background work and email, at a glance. */
function Health() {
  const ops = useOps();
  // The public status word (/health/ready is for the deployment's own probes and is not served to browsers).
  const health = useResource<{ status: string }>("/health/status");
  const application = applicationHealth(health.state, health.data?.status);
  const data = ops.data;
  return (
    <div className="ac-grid">
      <section className="ac-stats ar-stats-4" aria-label="System health">
        <StatTile
          label="Application"
          value={application.value}
          detail={application.detail}
          icon={<ServerCog size={18} />}
          tone={application.tone}
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
      <Panel eyebrow="Behind the scenes" title="Background worker" state={ops.state} error={ops.error}>
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

const ERROR_LENGTH = 90;
/** Long text cut to `length` characters with an ellipsis. */
const shorten = (text: string, length: number) => (text.length > length ? `${text.slice(0, length - 1)}…` : text);

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
        The background worker has not checked in yet. It sends queued work (integration records, report jobs) and checks
        in every few seconds while it runs. Ask your technical team to start the background worker.
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
          : "The background worker has stopped: it has not checked in for over a minute, so queued work and reports wait. Ask your technical team to restart the background worker."}
      </Intro>
      <section className="ac-stats ar-stats-4" aria-label="Background worker">
        <StatTile
          label="State"
          value={running ? "Running" : "Stopped"}
          detail={`Last checked in ${sinceText(worker.seconds_since)}`}
          icon={<Activity size={18} />}
          tone={running ? "good" : "critical"}
        />
        <StatTile
          label="Running since"
          value={worker.started_at ? formatDate(worker.started_at) : null}
          detail={`Checked for work ${(metrics.cycles ?? 0).toLocaleString()} time${metrics.cycles === 1 ? "" : "s"}`}
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
          label="Reports in the latest round"
          value={reports.ready ?? 0}
          detail={`${reports.claimed ?? 0} picked up, ${reports.failed ?? 0} failed`}
          icon={<Database size={18} />}
          tone={reports.failed ? "warning" : "good"}
        />
      </section>
    </>
  );
}

type GaveUpItem = {
  id: string;
  event_name: string;
  aggregate_type: string;
  attempts: number;
  last_error: string | null;
  occurred_at: string | null;
  dead_lettered_at: string | null;
  tenant_id: string | null;
  tenant_name?: string | null;
  tenant_key?: string | null;
};
type GaveUpGroup = {
  key: string;
  event_name: string;
  tenant_name?: string | null;
  tenant_key?: string | null;
  ids: string[];
  count: number;
  last_error: string | null;
  first: string | null;
  last: string | null;
};

/** Items of the same kind in the same tenant, so a batch (for example test leftovers) is handled in one step. */
export function groupGaveUp(items: GaveUpItem[]): GaveUpGroup[] {
  const groups = new Map<string, GaveUpGroup>();
  for (const item of items) {
    const key = `${item.event_name}|${item.tenant_id ?? ""}`;
    const group = groups.get(key) ?? {
      key,
      event_name: item.event_name,
      tenant_name: item.tenant_name,
      tenant_key: item.tenant_key,
      ids: [],
      count: 0,
      last_error: item.last_error,
      first: item.occurred_at,
      last: item.occurred_at,
    };
    group.ids.push(item.id);
    group.count += 1;
    if (item.occurred_at && (!group.first || item.occurred_at < group.first)) group.first = item.occurred_at;
    if (item.occurred_at && (!group.last || item.occurred_at > group.last)) group.last = item.occurred_at;
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => b.count - a.count);
}

/** Work that gave up after its retries: send it again once the cause is fixed, or discard it when it is not needed.
 * Both ask for a reason, which the server keeps in each tenant's audit trail. */
function GaveUp({ onChanged }: { onChanged: () => void }) {
  const list = useResource<{ total: number; items: GaveUpItem[] }>("/api/v1/platform-admin/console/dead-letters");
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [message, setMessage] = useState<BannerMessage>(null);
  const groups = useMemo(() => groupGaveUp(list.data?.items ?? []), [list.data]);
  const act = (group: GaveUpGroup, discard: boolean) => {
    const what = `${group.count} ${displayCode(group.event_name)} item${group.count === 1 ? "" : "s"}`;
    const where = group.tenant_name ? ` for ${group.tenant_name}` : "";
    setConfirm({
      title: discard ? `Discard ${what}?` : `Retry ${what}?`,
      body: discard
        ? `The ${what}${where} are removed from the queue and will not be sent. Use this for work that is not needed, such as test leftovers. The audit trail keeps what was discarded and why.`
        : `The ${what}${where} go back in the queue with a fresh set of retries; the background worker sends them within seconds. Retry once the cause of the failure is fixed.`,
      confirmLabel: discard ? "Discard" : "Retry",
      danger: discard,
      reason: { label: "Reason (kept in the audit trail)", min: 10 },
      run: (reason) =>
        send(`/api/v1/platform-admin/console/dead-letters/${discard ? "discard" : "retry"}`, "POST", {
          ids: group.ids,
          reason,
        }),
      done: discard ? `Discarded ${what}${where}.` : `${what}${where} are back in the queue.`,
    });
  };
  return (
    <Panel eyebrow="Queue" title="Gave up after retries" state={list.state} error={list.error}>
      <Banner message={message} onDismiss={() => setMessage(null)} />
      <Table
        caption="Gave up after retries"
        rows={groups}
        rowKey={(row) => row.key}
        empty={{
          title: "Nothing gave up",
          detail:
            "Background work that still fails after repeated retries over several hours appears here for a decision.",
        }}
        columns={[
          { key: "kind", label: "Kind", render: (row) => displayCode(row.event_name), fields: ["event_name"] },
          {
            key: "tenant",
            label: "Tenant",
            render: (row) => <TenantCell row={row} />,
            fields: ["tenant_name", "tenant_key"],
          },
          { key: "count", label: "Items", numeric: true, render: (row) => row.count },
          {
            key: "error",
            label: "Last error",
            // A long error is shortened; the full text shows on hover.
            render: (row) =>
              row.last_error ? <span title={row.last_error}>{shorten(row.last_error, ERROR_LENGTH)}</span> : "—",
            fields: ["last_error"],
          },
          {
            key: "when",
            label: "Queued",
            render: (row) =>
              row.first === row.last ? formatDate(row.last) : `${formatDate(row.first)} – ${formatDate(row.last)}`,
            fields: ["first", "last"],
          },
          {
            key: "actions",
            label: "",
            render: (row) => (
              <span className="ca-action-row">
                <button type="button" className="ac-link" onClick={() => act(row, false)}>
                  <RotateCcw size={14} aria-hidden="true" /> Retry
                </button>
                <button type="button" className="ac-link" onClick={() => act(row, true)}>
                  <Trash2 size={14} aria-hidden="true" /> Discard
                </button>
              </span>
            ),
          },
        ]}
      />
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(text) => {
          setConfirm(null);
          setMessage({ text, tone: "good" });
          list.reload();
          onChanged();
        }}
      />
    </Panel>
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
      <GaveUp onChanged={ops.reload} />
      <div className="ac-grid two">
        <Panel eyebrow="Queue" title="Waiting work by kind" state={ops.state} error={ops.error}>
          <Table
            caption="Waiting work by kind"
            rows={data?.queue.pending_by_event ?? []}
            rowKey={(row) => row.event}
            empty={{ title: "Nothing waiting", detail: "All background work is processed." }}
            columns={[
              { key: "kind", label: "Kind", render: (row) => displayCode(row.event) },
              { key: "count", label: "Waiting", numeric: true, render: (row) => row.pending },
            ]}
          />
        </Panel>
        <Panel eyebrow="Tenant setup" title="Customer setup jobs" state={ops.state} error={ops.error}>
          <Table
            caption="Customer setup jobs"
            rows={data?.provisioning_jobs.recent ?? []}
            rowKey={(row) => row.id}
            empty={{ title: "No jobs yet", detail: "Creating a customer starts a setup job." }}
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
          <strong>{email?.reminders_pending ?? 0}</strong>{" "}
          {email?.reminders_pending === 1 ? "reminder is waiting to be sent." : "reminders are waiting to be sent."}
        </p>
        <p className="ar-notice" role="note">
          <Mail size={16} aria-hidden="true" />{" "}
          {email?.reminder_delivery === "CONNECTED"
            ? "The background worker emails queued reminders to each tenant's Customer Administrators and the contacts in its notification settings."
            : "Email is not configured, so queued reminders are not sent."}{" "}
          Schedules and wording are set per tenant under Plans &amp; Licensing, Reminders.
        </p>
        {Boolean(email?.reminders_dead_lettered) && (
          <p className="ca-inline-error" role="alert">
            {email?.reminders_dead_lettered} {email?.reminders_dead_lettered === 1 ? "reminder" : "reminders"} could not
            be delivered after every retry. See Queues &amp; jobs, Gave up after retries.
          </p>
        )}
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
        rows={shown}
        rowKey={(row) => `${row.method} ${row.path}`}
        pageSize={50}
        pageNoun="operation"
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
    </Panel>
  );
}

type CellRow = {
  id: string;
  tenant_name?: string | null;
  tenant_key?: string | null;
  tenant_business_id?: string | null;
  hosting_mode: string;
  status: string;
  enrolled_at: string | null;
  last_heartbeat_at: string | null;
  seconds_since_heartbeat: number | null;
  contact: "NEVER" | "CURRENT" | "LATE";
  health: string | null;
  software_version: string | null;
  schema_version: string | null;
  jobs_failed: number;
  jobs_reported: number;
  packages: Record<string, number>;
  licence_status: string | null;
  licence_valid_until: string | null;
};

const HOSTING: Record<string, string> = {
  MDARIX_MANAGED: "Run by MDARIX",
  CUSTOMER_CLOUD: "Customer's cloud",
  CUSTOMER_ON_PREM: "Customer's own servers",
};

/** The cell's last contact, as a word with a tone. */
export function cellContact(row: Pick<CellRow, "contact" | "seconds_since_heartbeat" | "status">): {
  value: string;
  tone: "good" | "warning" | "critical";
} {
  if (row.status === "PROVISIONING") return { value: "Not enrolled yet", tone: "warning" };
  if (row.contact === "NEVER") return { value: "Never", tone: "critical" };
  if (row.contact === "LATE") return { value: `Late (${sinceText(row.seconds_since_heartbeat)})`, tone: "critical" };
  return { value: sinceText(row.seconds_since_heartbeat) || "Just now", tone: "good" };
}

/**
 * Every customer's cell as its heartbeats describe it. A cell calls the platform every quarter hour with versions,
 * health, job outcomes and counts; the platform never calls a cell and never sees its records.
 */
function Cells() {
  const cells = useResource<{ items: CellRow[]; heartbeat_every_minutes: number }>(
    "/api/v1/platform-admin/console/cells",
  );
  const rows = cells.data?.items ?? [];
  const late = rows.filter((row) => row.status === "ACTIVE" && row.contact !== "CURRENT").length;
  const failing = rows.filter((row) => row.jobs_failed > 0).length;
  return (
    <div className="ac-grid">
      <Intro>
        Each cell is one customer's own MDARIX, with its own database and keys. It reports here every{" "}
        {cells.data?.heartbeat_every_minutes ?? 15} minutes: what it runs, whether it is healthy, which jobs failed and
        which packages it holds. Nothing a customer records ever reaches this page.
      </Intro>
      <section className="ac-stats ar-stats-4" aria-label="Tenant cells">
        <StatTile
          label="Cells"
          value={cells.data ? rows.length : null}
          detail="Registered"
          icon={<ServerCog size={18} />}
        />
        <StatTile
          label="Reporting"
          value={cells.data ? rows.filter((row) => row.contact === "CURRENT").length : null}
          detail="Heard from within the last half hour"
          icon={<Activity size={18} />}
          tone={cells.data ? (late ? "warning" : "good") : undefined}
        />
        <StatTile
          label="Late or silent"
          value={cells.data ? late : null}
          detail="Enrolled cells not heard from in time"
          icon={<TriangleAlert size={18} />}
          tone={cells.data ? (late ? "critical" : "good") : undefined}
        />
        <StatTile
          label="With failing jobs"
          value={cells.data ? failing : null}
          detail="A scheduled job failed at the last report"
          icon={<Database size={18} />}
          tone={cells.data ? (failing ? "warning" : "good") : undefined}
        />
      </section>
      <Panel eyebrow="Fleet" title="Tenant cells" state={cells.state} error={cells.error}>
        <Table<CellRow>
          caption="Tenant cells"
          rows={rows}
          rowKey={(row) => row.id}
          pageSize={25}
          pageNoun="cells"
          empty={{
            title: "No cells yet",
            detail: "Issue a cell's documents with scripts/cell_platform.py to register one.",
          }}
          columns={[
            { key: "tenant", label: "Organization", render: (row) => <TenantCell row={row} /> },
            { key: "hosting_mode", label: "Hosting", render: (row) => HOSTING[row.hosting_mode] ?? row.hosting_mode },
            { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
            {
              key: "contact",
              label: "Last contact",
              render: (row) => {
                const contact = cellContact(row);
                return <span className={`ac-tone-${contact.tone}`}>{contact.value}</span>;
              },
              sortValue: (row) => row.seconds_since_heartbeat ?? Number.MAX_SAFE_INTEGER,
            },
            { key: "health", label: "Health", render: (row) => (row.health ? row.health.toUpperCase() : "") },
            { key: "software_version", label: "Version", render: (row) => row.software_version ?? "" },
            {
              key: "jobs",
              label: "Jobs",
              render: (row) => (row.jobs_reported ? `${row.jobs_failed} failed of ${row.jobs_reported}` : ""),
              sortValue: (row) => row.jobs_failed,
            },
            {
              key: "packages",
              label: "Packages",
              render: (row) =>
                Object.entries(row.packages)
                  .map(([state, count]) => `${count} ${state.toLowerCase()}`)
                  .join(", "),
            },
            {
              key: "licence",
              label: "Licence",
              render: (row) =>
                row.licence_status
                  ? `${row.licence_status}${row.licence_valid_until ? ` until ${formatDate(row.licence_valid_until)}` : ""}`
                  : "",
            },
          ]}
        />
      </Panel>
    </div>
  );
}
