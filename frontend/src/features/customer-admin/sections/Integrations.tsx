import { useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { ColumnChart, Panel, ToneBadge } from "../../admin/console/charts";
import { dailyCounts, runOutcomes, titleCase, type Tone } from "../../admin/console/dashboardModel";
import { useConsole } from "../context";
import { Table, Tabs, errorText, formatDate, listOf, send, useResource } from "../shared";
import { LifecycleActions, LifecycleBadge } from "./Access";

const TABS = ["Connections", "Sync activity", "Reconciliation"] as const;
type Tab = (typeof TABS)[number];

const resultTone = (status: unknown): Tone => {
  const value = String(status ?? "").toUpperCase();
  if (["HEALTHY", "SUCCESS", "COMPLETE", "SUCCEEDED", "COMPLETED", "RECONCILED", "MATCHED"].includes(value))
    return "good";
  if (["FAILED", "FAILURE", "ERROR"].includes(value)) return "critical";
  if (["INVALID_CONFIGURATION", "NOT_CONFIGURED", "MISMATCH", "PARTIAL"].includes(value)) return "warning";
  return "neutral";
};

export function IntegrationsSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "Connections",
  );
  return (
    <>
      <p className="ca-lede">
        Secrets are never stored here. A connection points to a credential reference held in your secret manager.
      </p>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Integration sections" />
      {active === "Connections" && <Connections />}
      {active === "Sync activity" && <SyncActivity />}
      {active === "Reconciliation" && <Reconciliation />}
    </>
  );
}

type Check = { connector: string; action: string; status: string; reason?: string; at: Date };

function Connections() {
  const { confirm, notify } = useConsole();
  const connectors = useResource<any[]>("/api/v1/admin/configuration/connectors");
  const credentials = useResource<any[]>("/api/v1/admin/integrations/credentials");
  const [checks, setChecks] = useState<Check[]>([]);
  const [busy, setBusy] = useState("");
  const [form, setForm] = useState({ code: "", connector_type: "", endpoint: "", credential_ref: "" });
  const credentialFor = (id: string) => listOf(credentials.data).find((row) => row.id === id);

  const run = async (row: any, action: "provider-health" | "discover-schema", label: string) => {
    setBusy(`${row.id}:${action}`);
    try {
      const result = await send<any>(`/api/v1/admin/configuration/connectors/${row.id}/${action}`, "POST");
      setChecks((items) => [
        { connector: row.code, action: label, status: result.status, reason: result.reason, at: new Date() },
        ...items.slice(0, 9),
      ]);
    } catch (reason) {
      setChecks((items) => [
        {
          connector: row.code,
          action: label,
          status: "FAILED",
          reason: errorText(reason, "Request failed"),
          at: new Date(),
        },
        ...items.slice(0, 9),
      ]);
    } finally {
      setBusy("");
    }
  };

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    const configuration: Record<string, string> = {};
    if (form.endpoint.trim()) configuration.endpoint = form.endpoint.trim();
    if (form.credential_ref.trim()) configuration.credential_ref = form.credential_ref.trim();
    try {
      await send("/api/v1/admin/configuration/connectors", "POST", {
        code: form.code.trim().toUpperCase(),
        connector_type: form.connector_type.trim().toUpperCase(),
        configuration,
      });
      notify(`Connection ${form.code} created as a draft. Run a health check, then activate it.`);
      setForm({ code: "", connector_type: "", endpoint: "", credential_ref: "" });
      connectors.reload();
      credentials.reload();
    } catch (reason) {
      notify(errorText(reason, "Connection could not be created."), "critical");
    }
  };

  return (
    <>
      <Panel eyebrow="Integrations" title="Connections" state={connectors.state} error={connectors.error}>
        <Table
          caption="Connections"
          rows={listOf(connectors.data)}
          rowKey={(row) => row.id}
          empty={{ title: "No connections yet", detail: "Add your first source system below." }}
          columns={[
            {
              key: "code",
              label: "Connection",
              render: (row) => (
                <span className="ca-person">
                  <strong>{row.code}</strong>
                  <small>
                    {titleCase(row.connector_type ?? "")} · {row.version}
                  </small>
                </span>
              ),
            },
            {
              key: "endpoint",
              label: "Endpoint",
              render: (row) => row.configuration?.endpoint ?? <span className="ac-muted">Not set</span>,
            },
            {
              key: "credential",
              label: "Credential",
              render: (row) =>
                credentialFor(row.id)?.credential_configured ? (
                  <ToneBadge tone="good" label="Reference set" />
                ) : (
                  <ToneBadge tone="warning" label="No reference" />
                ),
            },
            { key: "status", label: "Status", render: (row) => <LifecycleBadge status={row.status} /> },
            {
              key: "checks",
              label: "Checks",
              render: (row) => (
                <span className="ca-row-actions">
                  <button
                    type="button"
                    className="ac-link"
                    disabled={!!busy}
                    onClick={() => void run(row, "provider-health", "Health check")}
                  >
                    Health
                  </button>
                  <button
                    type="button"
                    className="ac-link"
                    disabled={!!busy}
                    onClick={() => void run(row, "discover-schema", "Schema discovery")}
                  >
                    Schema
                  </button>
                  {String(row.status).toUpperCase() === "ACTIVE" && (
                    <button
                      type="button"
                      className="ac-link"
                      onClick={() =>
                        confirm({
                          title: `Run a sync for ${row.code}?`,
                          body: "Records are read from the source and queued for processing into MDARIX. This is recorded in the audit trail.",
                          confirmLabel: "Run sync",
                          done: `Sync for ${row.code} completed.`,
                          run: async () => {
                            const result = await send<any>(
                              `/api/v1/admin/configuration/connectors/${row.id}/execute`,
                              "POST",
                              {},
                            );
                            setChecks((items) => [
                              {
                                connector: row.code,
                                action: "Sync",
                                status: result.status,
                                reason: `${result.records_read ?? 0} records read`,
                                at: new Date(),
                              },
                              ...items.slice(0, 9),
                            ]);
                          },
                        })
                      }
                    >
                      Sync now
                    </button>
                  )}
                </span>
              ),
            },
            {
              key: "manage",
              label: "",
              render: (row) => (
                <LifecycleActions
                  status={row.status}
                  name={row.code}
                  path={`/api/v1/admin/configuration/connectors/${row.id}/status`}
                  onDone={connectors.reload}
                />
              ),
            },
          ]}
        />
        {checks.length > 0 && (
          <div className="ca-results" aria-live="polite">
            <h3 className="ca-subhead">Latest checks</h3>
            <ul>
              {checks.map((check, index) => (
                <li key={`${check.at.getTime()}-${index}`}>
                  <ToneBadge tone={resultTone(check.status)} label={titleCase(check.status ?? "Unknown")} />
                  <span>
                    <strong>
                      {check.connector} · {check.action}
                    </strong>
                    {check.reason && <small>{titleCase(String(check.reason))}</small>}
                  </span>
                  <small className="ac-muted">{check.at.toLocaleTimeString()}</small>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Panel>
      <Panel eyebrow="New" title="Add a connection">
        <form className="ca-form" onSubmit={create}>
          <div className="ca-form-grid">
            <label className="ca-field">
              Code
              <input
                required
                pattern="[A-Za-z0-9_]+"
                title="Letters, numbers and underscores"
                value={form.code}
                onChange={(event) => setForm({ ...form, code: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Source system type
              <input
                required
                placeholder="e.g. TRACKWISE, PLM, ERP"
                value={form.connector_type}
                onChange={(event) => setForm({ ...form, connector_type: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Endpoint (https)
              <input
                type="url"
                placeholder="https://"
                value={form.endpoint}
                onChange={(event) => setForm({ ...form, endpoint: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Credential reference
              <input
                pattern="[A-Za-z0-9_]{1,120}"
                title="The name of the secret in your secret manager, not the secret itself"
                placeholder="e.g. TRACKWISE_PROD_READER"
                value={form.credential_ref}
                onChange={(event) => setForm({ ...form, credential_ref: event.target.value })}
              />
            </label>
          </div>
          <p className="ac-muted">
            Never paste a password or token here. Enter only the reference name; the server rejects secret values.
          </p>
          <div className="ca-action-row">
            <button type="submit" className="ac-primary">
              <Plus size={16} /> Add connection
            </button>
          </div>
        </form>
      </Panel>
    </>
  );
}

function SyncActivity() {
  const runs = useResource<any[]>("/api/v1/admin/integrations/runs");
  const rows = listOf(runs.data);
  const trend = useMemo(
    () =>
      dailyCounts(
        rows.map((row) => row.started_at),
        14,
      ),
    [runs.data],
  );
  const outcomes = runOutcomes(rows);
  return (
    <>
      <Panel eyebrow="Integrations" title="Sync runs · last 14 days" state={runs.state} error={runs.error}>
        <ColumnChart data={trend} unit="runs" caption="by start date" />
        <div className="ac-inline-stats">
          <span>{outcomes.succeeded} succeeded</span>
          <span>{outcomes.failed} failed</span>
          <span>{outcomes.inProgress} other / in progress</span>
        </div>
      </Panel>
      <Panel eyebrow="Integrations" title="Run history" state={runs.state} error={runs.error}>
        <Table
          caption="Sync runs"
          rows={rows.slice(0, 50)}
          rowKey={(row) => row.id}
          empty={{ title: "No sync runs yet", detail: "Runs appear after a connection syncs." }}
          columns={[
            { key: "source", label: "Source", render: (row) => row.source_system ?? "—" },
            { key: "type", label: "Type", render: (row) => titleCase(row.run_type ?? "") },
            {
              key: "status",
              label: "Status",
              render: (row) => <ToneBadge tone={resultTone(row.status)} label={titleCase(row.status ?? "Unknown")} />,
            },
            { key: "received", label: "Received", numeric: true, render: (row) => row.records_received ?? 0 },
            { key: "accepted", label: "Accepted", numeric: true, render: (row) => row.records_accepted ?? 0 },
            { key: "rejected", label: "Rejected", numeric: true, render: (row) => row.records_rejected ?? 0 },
            { key: "drift", label: "Schema drift", render: (row) => titleCase(row.schema_drift_status ?? "—") },
            { key: "started", label: "Started", numeric: true, render: (row) => formatDate(row.started_at) },
          ]}
        />
      </Panel>
    </>
  );
}

function Reconciliation() {
  const records = useResource<any[]>("/api/v1/admin/integrations/reconciliation");
  return (
    <Panel eyebrow="Integrations" title="Reconciliation" state={records.state} error={records.error}>
      <p className="ac-muted">
        Every sync is checked: records expected versus received, accepted, rejected and unresolved.
      </p>
      <Table
        caption="Reconciliation records"
        rows={listOf(records.data).slice(0, 50)}
        rowKey={(row) => row.id}
        empty={{ title: "No reconciliation records", detail: "They appear after the first sync completes." }}
        columns={[
          {
            key: "status",
            label: "Status",
            render: (row) => <ToneBadge tone={resultTone(row.status)} label={titleCase(row.status ?? "Unknown")} />,
          },
          { key: "expected", label: "Expected", numeric: true, render: (row) => row.expected_count ?? 0 },
          { key: "received", label: "Received", numeric: true, render: (row) => row.received_count ?? 0 },
          { key: "accepted", label: "Accepted", numeric: true, render: (row) => row.accepted_count ?? 0 },
          { key: "rejected", label: "Rejected", numeric: true, render: (row) => row.rejected_count ?? 0 },
          { key: "quarantined", label: "Quarantined", numeric: true, render: (row) => row.quarantined_count ?? 0 },
          { key: "unresolved", label: "Unresolved", numeric: true, render: (row) => row.unresolved_count ?? 0 },
          { key: "when", label: "Reconciled", numeric: true, render: (row) => formatDate(row.reconciled_at) },
        ]}
      />
    </Panel>
  );
}
