import { useState } from "react";
import { AlertTriangle, CheckCircle2, CircleSlash, RefreshCcw } from "lucide-react";
import { BarList, Panel, StatTile } from "../console/charts";
import type { Slice, Tone } from "../console/dashboardModel";
import { SearchBox, Table, formatDate, listOf, useResource } from "../../customer-admin/shared";
import { titleCase } from "../customers/model";
import { StatusBadge } from "../customers/StatusBadge";
import { Intro, Pager, TenantCell, TenantPicker } from "./common";

export function Integrations({ section }: { section: string }) {
  if (section === "Runs & failures") return <Runs />;
  if (section === "Reconciliation") return <Reconciliation />;
  if (section === "Credentials") return <Credentials />;
  if (section === "API & schemas") return <Schemas />;
  return <Catalog />;
}

type Application = {
  application_id: string;
  display_name: string;
  category?: string | null;
  description?: string | null;
  status?: string | null;
  integration_support_status?: string | null;
  default_connector_type?: string | null;
  supports_schema_discovery?: boolean;
};

/** The source systems MDARIX can connect to, and the connector versions available for each. */
function Catalog() {
  const applications = useResource<Application[]>("/api/v1/admin/mapping/applications");
  const [selected, setSelected] = useState("");
  const versions = useResource<any[]>(
    selected ? `/api/v1/admin/mapping/connector-versions?application_id=${encodeURIComponent(selected)}` : null,
  );
  const rows = listOf(applications.data) as Application[];
  const chosen = rows.find((row) => row.application_id === selected);
  return (
    <div className="ac-grid two">
      <Panel eyebrow="Source systems" title="Connector catalog" state={applications.state} error={applications.error}>
        <Intro>Systems a customer can connect (QMS, ERP, PLM and others). Choose one to see its connectors.</Intro>
        <Table
          caption="Source systems"
          rows={rows}
          rowKey={(row) => row.application_id}
          empty={{ title: "No source systems", detail: "The catalog is empty." }}
          columns={[
            {
              key: "system",
              label: "System",
              render: (row) => (
                <button
                  type="button"
                  className={`ac-link cc-stack${row.application_id === selected ? " ar-selected" : ""}`}
                  onClick={() => setSelected(row.application_id)}
                >
                  <strong>{row.display_name}</strong>
                  <small>{row.category ?? "—"}</small>
                </button>
              ),
            },
            { key: "support", label: "Support", render: (row) => titleCase(row.integration_support_status ?? "—") },
            { key: "type", label: "Connects by", render: (row) => row.default_connector_type ?? "—" },
            { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
          ]}
        />
      </Panel>
      <Panel
        eyebrow={chosen ? chosen.display_name : "Connectors"}
        title="Connector versions"
        state={selected ? versions.state : "ready"}
        error={versions.error}
      >
        {chosen ? (
          <>
            {chosen.description && <Intro>{chosen.description}</Intro>}
            <Table
              caption="Connector versions"
              rows={listOf(versions.data)}
              rowKey={(row) => `${row.connector_id}-${row.version}`}
              empty={{ title: "No connector yet", detail: "No connector version is published for this system." }}
              columns={[
                { key: "connector", label: "Connector", render: (row) => <strong>{row.connector_id}</strong> },
                { key: "type", label: "Type", render: (row) => row.connector_type },
                { key: "version", label: "Version", render: (row) => row.version },
                {
                  key: "sync",
                  label: "Incremental sync",
                  render: (row) => (row.supports_incremental_sync ? "Yes" : "No"),
                },
                { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
              ]}
            />
          </>
        ) : (
          <p className="ac-muted">Choose a system on the left.</p>
        )}
      </Panel>
    </div>
  );
}

type Run = {
  id: string;
  tenant_name?: string | null;
  tenant_key?: string | null;
  customer_name?: string | null;
  source_system: string;
  connection_id: string;
  run_type?: string;
  status: string;
  records_received: number;
  records_accepted: number;
  records_rejected: number;
  records_quarantined: number;
  retry_attempt: number;
  reconciliation_status?: string | null;
  schema_drift_status?: string | null;
  failure_category?: string | null;
  started_at?: string | null;
};
type RunPage = {
  items: Run[];
  total: number;
  pages: number;
  last_30_days: { by_status: Record<string, number>; by_reconciliation: Record<string, number> };
};

function useRuns(filters: Record<string, string>) {
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({ page: String(page), page_size: "25" });
  Object.entries(filters).forEach(([key, value]) => value && params.set(key, value));
  const runs = useResource<RunPage>(`/api/v1/platform-admin/console/integration-runs?${params}`);
  return { runs, page, setPage };
}

const toneOf = (status: string): Tone => {
  const value = status.toUpperCase();
  if (["SUCCEEDED", "SUCCESS", "COMPLETED", "MATCH", "MATCHED", "RECONCILED"].includes(value)) return "good";
  if (["FAILED", "ERROR", "MISMATCH"].includes(value)) return "critical";
  if (["PARTIAL", "RETRYING", "QUARANTINED", "COMPLETED_WITH_WARNINGS"].includes(value)) return "warning";
  return "neutral";
};

const slices = (counts: Record<string, number> = {}): Slice[] =>
  Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([key, count]) => ({ key, label: titleCase(key), count, tone: toneOf(key) }));

const RUN_COLUMNS = [
  { key: "when", fields: ["started_at"], label: "Started", render: (row: Run) => formatDate(row.started_at) },
  {
    key: "tenant",
    fields: ["tenant_name", "tenant_key", "customer_name", "tenant_id"],
    label: "Tenant",
    render: (row: Run) => <TenantCell row={row} />,
  },
  {
    key: "source",
    fields: ["source_system", "connection_id"],
    label: "Source",
    render: (row: Run) => (
      <span className="cc-stack">
        <strong>{row.source_system}</strong>
        <small>{row.connection_id}</small>
      </span>
    ),
  },
  {
    key: "records",
    fields: ["records_received", "records_accepted", "records_rejected"],
    label: "Records in / kept / rejected",
    numeric: true,
    render: (row: Run) => `${row.records_received} / ${row.records_accepted} / ${row.records_rejected}`,
  },
  { key: "status", label: "Result", render: (row: Run) => <StatusBadge status={row.status} /> },
];

/** Every connector run on the platform, with the failing ones one click away. */
function Runs() {
  const [status, setStatus] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [query, setQuery] = useState("");
  const { runs, page, setPage } = useRuns({ status, tenant_id: tenantId, q: query.trim() });
  const counts = runs.data?.last_30_days.by_status ?? {};
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  const failed = (counts.FAILED ?? 0) + (counts.ERROR ?? 0) + (counts.PARTIAL ?? 0);
  const warnings = counts.COMPLETED_WITH_WARNINGS ?? 0;
  const filter = (apply: () => void) => {
    apply();
    setPage(1);
  };
  return (
    <div className="ac-grid">
      <section className="ac-stats ar-stats-4" aria-label="Runs in the last 30 days">
        <StatTile
          label="Runs (30 days)"
          value={runs.data ? total : null}
          detail="All tenants"
          icon={<RefreshCcw size={18} />}
          onOpen={() => filter(() => setStatus(""))}
        />
        <StatTile
          label="Failed"
          value={runs.data ? failed : null}
          detail={failed ? "Needs a look" : "None"}
          icon={<AlertTriangle size={18} />}
          tone={failed ? "critical" : "good"}
          onOpen={() => filter(() => setStatus("problems"))}
        />
        <StatTile
          label="With warnings"
          value={runs.data ? warnings : null}
          detail="Completed; some records need review"
          icon={<AlertTriangle size={18} />}
          tone={warnings ? "warning" : "good"}
          onOpen={() => filter(() => setStatus("completed_with_warnings"))}
        />
        <StatTile
          label="Completed"
          value={runs.data ? (counts.COMPLETED ?? 0) + (counts.SUCCEEDED ?? 0) : null}
          detail="No errors or warnings"
          icon={<CheckCircle2 size={18} />}
          tone="good"
          onOpen={() => filter(() => setStatus("completed"))}
        />
      </section>
      <Panel eyebrow="All tenants" title="Integration runs" state={runs.state} error={runs.error}>
        <div className="cc-toolbar">
          <SearchBox value={query} onChange={(value) => filter(() => setQuery(value))} label="Search source system" />
          <select aria-label="Result" value={status} onChange={(event) => filter(() => setStatus(event.target.value))}>
            <option value="">All results</option>
            <option value="problems">Failed or rejected records</option>
            <option value="completed_with_warnings">Completed with warnings</option>
            <option value="completed">Completed</option>
          </select>
          <TenantPicker
            value={tenantId}
            onChange={(value) => filter(() => setTenantId(value))}
            allLabel="All tenants"
            inline
          />
        </div>
        <Table
          caption="Integration runs"
          rows={runs.data?.items ?? []}
          rowKey={(row) => row.id}
          empty={{ title: "No runs", detail: "No run matches these filters." }}
          columns={[
            ...RUN_COLUMNS,
            {
              key: "problem",
              label: "Problem",
              render: (row: Run) =>
                row.failure_category
                  ? titleCase(row.failure_category)
                  : row.schema_drift_status && !/^(NONE|NO_DRIFT|OK|MATCH)$/i.test(row.schema_drift_status)
                    ? `Schema: ${titleCase(row.schema_drift_status)}`
                    : row.records_rejected
                      ? "Rejected records"
                      : "—",
            },
          ]}
        />
        <Pager page={page} pages={runs.data?.pages ?? 1} total={runs.data?.total ?? 0} noun="run" onPage={setPage} />
      </Panel>
    </div>
  );
}

/** Runs that were checked against their source, and whether the counts matched. */
function Reconciliation() {
  const { runs, page, setPage } = useRuns({ reconciled: "true" });
  return (
    <div className="ac-grid two ar-wide-right">
      <Panel eyebrow="Last 30 days" title="Reconciliation results" state={runs.state} error={runs.error}>
        <Intro>After a run, the records kept are checked against the source system. A mismatch needs a look.</Intro>
        {runs.data && Object.keys(runs.data.last_30_days.by_reconciliation).length ? (
          <BarList items={slices(runs.data.last_30_days.by_reconciliation)} />
        ) : (
          <p className="ac-muted">No run was reconciled in the last 30 days.</p>
        )}
      </Panel>
      <Panel eyebrow="All tenants" title="Reconciled runs" state={runs.state} error={runs.error}>
        <Table
          caption="Reconciled runs"
          rows={runs.data?.items ?? []}
          rowKey={(row) => row.id}
          empty={{ title: "No reconciled runs", detail: "Runs appear here once they are reconciled." }}
          columns={[
            ...RUN_COLUMNS.filter((column) => column.key !== "status"),
            {
              key: "reconciliation",
              label: "Reconciliation",
              render: (row: Run) => <StatusBadge status={row.reconciliation_status} />,
            },
          ]}
        />
        <Pager page={page} pages={runs.data?.pages ?? 1} total={runs.data?.total ?? 0} noun="run" onPage={setPage} />
      </Panel>
    </div>
  );
}

/** Which connections have their secret configured. Secrets themselves are never shown. */
function Credentials() {
  const credentials = useResource<any[]>("/api/v1/admin/integrations/credentials");
  const rows = listOf(credentials.data);
  const missing = rows.filter((row) => !row.credential_configured).length;
  return (
    <Panel
      eyebrow="MDARIX platform tenant"
      title="Connection credentials"
      state={credentials.state}
      error={credentials.error}
    >
      <Intro>
        Secrets live in the secret store; MDARIX keeps only a reference to them and never shows their value.{" "}
        {rows.length > 0 &&
          (missing ? `${missing} of ${rows.length} connections have no secret yet.` : "Every connection has one.")}
      </Intro>
      <Table
        caption="Connection credentials"
        rows={rows}
        rowKey={(row) => row.id}
        empty={{ title: "No connections", detail: "Connections of the platform tenant appear here." }}
        columns={[
          {
            key: "connection",
            label: "Connection",
            render: (row) => (
              <span className="cc-stack">
                <strong>{row.code}</strong>
                <small>
                  {row.connector_type} · {row.version}
                </small>
              </span>
            ),
          },
          {
            key: "secret",
            label: "Secret",
            render: (row) =>
              row.credential_configured ? (
                <span className="ar-yes">
                  <CheckCircle2 size={14} aria-hidden="true" /> Configured
                </span>
              ) : (
                <span className="ar-no">
                  <CircleSlash size={14} aria-hidden="true" /> Not configured
                </span>
              ),
          },
          { key: "reference", label: "Secret reference", render: (row) => row.credential_ref ?? "—" },
          { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
        ]}
      />
    </Panel>
  );
}

/** The records and fields each source system offers, as mapping starts from them. */
function Schemas() {
  const applications = useResource<Application[]>("/api/v1/admin/mapping/applications");
  const [applicationId, setApplicationId] = useState("");
  const [objectId, setObjectId] = useState("");
  const objects = useResource<any[]>(
    applicationId ? `/api/v1/admin/mapping/applications/${encodeURIComponent(applicationId)}/objects` : null,
  );
  const fields = useResource<any[]>(
    objectId ? `/api/v1/admin/mapping/objects/${encodeURIComponent(objectId)}/fields` : null,
  );
  const apps = listOf(applications.data) as Application[];
  const objectRows = listOf(objects.data);
  return (
    <div className="ac-grid">
      <Panel eyebrow="Source schemas" title="Records and fields" state={applications.state} error={applications.error}>
        <Intro>
          Choose a source system to see the records it offers, then a record to see its fields. The platform API itself
          is under Operations, Developer API.
        </Intro>
        <label className="ca-field ar-picker">
          Source system
          <select
            value={applicationId}
            onChange={(event) => {
              setApplicationId(event.target.value);
              setObjectId("");
            }}
          >
            <option value="">Choose a source system</option>
            {apps.map((app) => (
              <option key={app.application_id} value={app.application_id}>
                {app.display_name}
              </option>
            ))}
          </select>
        </label>
      </Panel>
      {applicationId && (
        <div className="ac-grid two ar-wide-right">
          <Panel eyebrow="Records" title="Source records" state={objects.state} error={objects.error}>
            <Table
              caption="Source records"
              rows={objectRows}
              rowKey={(row) => row.source_object_id}
              empty={{ title: "No records", detail: "This system has no cataloged record yet." }}
              columns={[
                {
                  key: "object",
                  label: "Record",
                  render: (row) => (
                    <button
                      type="button"
                      className={`ac-link cc-stack${row.source_object_id === objectId ? " ar-selected" : ""}`}
                      onClick={() => setObjectId(row.source_object_id)}
                    >
                      <strong>{row.object_name}</strong>
                      <small>Key: {row.primary_key_field ?? "—"}</small>
                    </button>
                  ),
                },
              ]}
            />
          </Panel>
          <Panel eyebrow="Fields" title="Fields" state={objectId ? fields.state : "ready"} error={fields.error}>
            {objectId ? (
              <Table
                caption="Fields"
                rows={listOf(fields.data)}
                rowKey={(row) => row.source_field_id}
                empty={{ title: "No fields", detail: "No field is cataloged for this record." }}
                columns={[
                  {
                    key: "field",
                    label: "Field",
                    render: (row) => (
                      <span className="cc-stack">
                        <strong>{row.field_label ?? row.field_name}</strong>
                        <small>{row.field_name}</small>
                      </span>
                    ),
                  },
                  { key: "type", label: "Type", render: (row) => titleCase(row.data_type) },
                  { key: "required", label: "Required", render: (row) => (row.required ? "Yes" : "No") },
                  {
                    key: "sensitivity",
                    label: "Sensitivity",
                    render: (row) => titleCase(row.sensitivity_classification ?? "—"),
                  },
                ]}
              />
            ) : (
              <p className="ac-muted">Choose a record on the left.</p>
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}
