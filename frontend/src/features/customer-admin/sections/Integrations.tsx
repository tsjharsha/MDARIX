import { useMemo, useState } from "react";
import { KeyRound, Plus } from "lucide-react";
import { ColumnChart, Panel, ToneBadge } from "../../admin/console/charts";
import { dailyCounts, runOutcomes, titleCase, type Tone } from "../../admin/console/dashboardModel";
import { useConsole } from "../context";
import { Table, Tabs, errorText, formatDate, idColumn, listOf, send, useResource } from "../shared";
import { LifecycleActions, LifecycleBadge } from "./Access";
import { DialogBehaviour } from "../../shared/DialogBehaviour";
import { formatTime } from "../../../app/dates";

const TABS = ["Connections", "Sync activity", "Reconciliation"] as const;

const EMPTY_CONNECTION = {
  code: "",
  connector_type: "",
  endpoint: "",
  credential_ref: "",
  source_object: "",
  mapping_code: "",
};

/** One option per mapping code (its newest version), marked when it is released and so able to import. */
const mappingOptions = (rows: unknown) => {
  const byCode = new Map<string, any>();
  for (const row of listOf(rows)) {
    const seen = byCode.get(row.code);
    if (!seen || String(row.status).toUpperCase() === "RELEASED") byCode.set(row.code, row);
  }
  return [...byCode.values()]
    .sort((a, b) => String(a.code).localeCompare(String(b.code)))
    .map((row) => ({
      code: String(row.code),
      label: `${row.code} (${String(row.status).toUpperCase() === "RELEASED" ? "released" : titleCase(row.status ?? "draft").toLowerCase()})`,
    }));
};

/** Choose which mapping a connection uses; the rest of its configuration is kept as it is. */
function LinkMapping({
  connection,
  mappings,
  onClose,
  onLinked,
}: {
  connection: any;
  mappings: unknown;
  onClose: () => void;
  onLinked: (message: string) => void;
}) {
  const [code, setCode] = useState<string>(connection.configuration?.mapping_code ?? "");
  const [record, setRecord] = useState<string>(connection.configuration?.source_object ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    const configuration = { ...(connection.configuration ?? {}) };
    if (code) configuration.mapping_code = code;
    else delete configuration.mapping_code;
    if (record.trim()) configuration.source_object = record.trim();
    try {
      await send(`/api/v1/admin/control-plane/connectors/${connection.id}`, "PATCH", { values: { configuration } });
      onLinked(code ? `${connection.code} now uses mapping ${code}.` : `${connection.code} no longer uses a mapping.`);
    } catch (reason) {
      setError(errorText(reason, "The connection was not changed."));
      setBusy(false);
    }
  };
  return (
    <div className="ac-modal-backdrop" role="presentation">
      <DialogBehaviour onClose={onClose} />
      <form className="ac-modal" role="dialog" aria-modal="true" aria-labelledby="ca-link-mapping" onSubmit={submit}>
        <p className="ac-eyebrow">{connection.code}</p>
        <h2 id="ca-link-mapping">Mapping for this connection</h2>
        <p>On Sync now, the records read are turned into MDARIX records with this mapping, once it is released.</p>
        <label className="ca-field">
          Mapping
          <select value={code} onChange={(event) => setCode(event.target.value)}>
            <option value="">None (records are only staged)</option>
            {mappingOptions(mappings).map((option) => (
              <option key={option.code} value={option.code}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          Record to read
          <input value={record} onChange={(event) => setRecord(event.target.value)} placeholder="e.g. Complaint" />
        </label>
        {error && (
          <p className="ca-inline-error" role="alert">
            {error}
          </p>
        )}
        <div className="ac-modal-actions">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </div>
  );
}
/** Store the API key the customer's system issued for this connection; it is encrypted and never shown again. */
function ApiKeyDialog({
  connection,
  onClose,
  onSaved,
}: {
  connection: any;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const path = `/api/v1/admin/configuration/connectors/${connection.id}/api-key`;
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await send<any>(path, "PUT", { api_key: key.trim() });
      onSaved(`API key ending ${result.api_key_ends_with} saved for ${connection.code}.`);
    } catch (reason) {
      setError(errorText(reason, "The key was not saved."));
      setBusy(false);
    }
  };
  const remove = async () => {
    setBusy(true);
    try {
      await send(path, "DELETE");
      onSaved(`API key removed from ${connection.code}.`);
    } catch (reason) {
      setError(errorText(reason, "The key was not removed."));
      setBusy(false);
    }
  };
  return (
    <div className="ac-modal-backdrop" role="presentation">
      <DialogBehaviour onClose={onClose} />
      <form className="ac-modal" role="dialog" aria-modal="true" aria-labelledby="ca-api-key" onSubmit={save}>
        <p className="ac-eyebrow">{connection.code}</p>
        <h2 id="ca-api-key">API key for this connection</h2>
        <p>
          Paste the key your source system issued for this organization. MDARIX encrypts it and uses it only to read
          records; it is never shown again.
          {connection.has_api_key && ` The current key ends in ${connection.api_key_ends_with}.`}
        </p>
        <label className="ca-field">
          API key
          <input
            type="password"
            autoComplete="off"
            required
            minLength={8}
            value={key}
            onChange={(event) => setKey(event.target.value)}
          />
        </label>
        {error && (
          <p className="ca-inline-error" role="alert">
            {error}
          </p>
        )}
        <div className="ac-modal-actions">
          {connection.has_api_key && (
            <button type="button" className="ac-secondary" onClick={() => void remove()} disabled={busy}>
              Remove key
            </button>
          )}
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy || key.trim().length < 8}>
            {busy ? "Saving…" : "Save key"}
          </button>
        </div>
      </form>
    </div>
  );
}

/** What a sync did, in words: records read, and what the mapping imported, skipped or refused. */
export const syncSummary = (result: any): string => {
  const read = `${result?.records_read ?? 0} records read`;
  const imported = result?.canonical_import;
  if (!imported) return read;
  if (String(imported.status).toUpperCase() !== "IMPORTED") {
    const issue = imported.report?.issues?.[0]?.message ?? imported.reason;
    return `${read}; nothing imported${issue ? `: ${issue}` : ""}`;
  }
  const parts = [`${imported.created ?? 0} new`, `${imported.updated ?? 0} updated`];
  if (imported.skipped) parts.push(`${imported.skipped} left out by the mapping's filter`);
  return `${read}; imported ${parts.join(", ")}`;
};

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
        Each connection reads one record type from a source system with that system's API key. Keys are encrypted and
        never shown again; a connection can instead name a credential reference held in your secret manager.
      </p>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Integration sections">
        {active === "Connections" && <Connections />}
        {active === "Sync activity" && <SyncActivity />}
        {active === "Reconciliation" && <Reconciliation />}
      </Tabs>
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
  const mappings = useResource<any[]>("/api/v1/admin/configuration/mappings");
  const [form, setForm] = useState({ ...EMPTY_CONNECTION });
  const [linking, setLinking] = useState<any | null>(null);
  const [keying, setKeying] = useState<any | null>(null);
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
    // The mapping turns the connector's records into MDARIX records on "Sync now"; the record names what to read.
    if (form.mapping_code) configuration.mapping_code = form.mapping_code;
    if (form.source_object.trim()) configuration.source_object = form.source_object.trim();
    try {
      await send("/api/v1/admin/configuration/connectors", "POST", {
        code: form.code.trim().toUpperCase(),
        connector_type: form.connector_type.trim().toUpperCase(),
        configuration,
      });
      notify(`Connection ${form.code} created as a draft. Run a health check, then activate it.`);
      setForm({ ...EMPTY_CONNECTION });
      connectors.reload();
      credentials.reload();
    } catch (reason) {
      notify(errorText(reason, "Connection could not be created."), "critical");
    }
  };

  return (
    <>
      <Panel eyebrow="Integrations" title="Connections" source={connectors}>
        <Table
          caption="Connections"
          rows={listOf(connectors.data)}
          rowKey={(row) => row.id}
          empty={{ title: "No connections yet", detail: "Add your first source system below." }}
          columns={[
            idColumn("Connection ID", "code"),
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
              render: (row) => (
                <span className="ca-person">
                  {row.has_api_key ? (
                    <ToneBadge tone="good" label={`API key ••••${row.api_key_ends_with ?? ""}`} />
                  ) : credentialFor(row.id)?.credential_configured ? (
                    <ToneBadge tone="good" label="Reference set" />
                  ) : (
                    <ToneBadge tone="warning" label="No key" />
                  )}
                  <button type="button" className="ac-link" onClick={() => setKeying(row)}>
                    <KeyRound size={14} aria-hidden="true" /> {row.has_api_key ? "Replace key" : "Set API key"}
                  </button>
                </span>
              ),
            },
            {
              key: "mapping",
              label: "Mapping",
              render: (row) => (
                <span className="ca-person">
                  <strong>{row.configuration?.mapping_code ?? <span className="ac-muted">None</span>}</strong>
                  <button type="button" className="ac-link" onClick={() => setLinking(row)}>
                    {row.configuration?.mapping_code ? "Change" : "Choose mapping"}
                  </button>
                </span>
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
                                reason: syncSummary(result),
                                at: new Date(),
                              },
                              ...items.slice(0, 9),
                            ]);
                            connectors.reload();
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
                    {check.reason && <small>{String(check.reason)}</small>}
                  </span>
                  <small className="ac-muted">{formatTime(check.at)}</small>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Panel>
      {linking && (
        <LinkMapping
          connection={linking}
          mappings={mappings.data}
          onClose={() => setLinking(null)}
          onLinked={(message) => {
            setLinking(null);
            notify(message);
            connectors.reload();
          }}
        />
      )}
      {keying && (
        <ApiKeyDialog
          connection={keying}
          onClose={() => setKeying(null)}
          onSaved={(message) => {
            setKeying(null);
            notify(message);
            connectors.reload();
          }}
        />
      )}
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
                pattern="MDARIX_CONNECTOR_SECRET_[A-Z0-9_]{1,80}"
                title="The name of the server secret (MDARIX_CONNECTOR_SECRET_…), never the secret itself"
                placeholder="e.g. MDARIX_CONNECTOR_SECRET_TEN0351_TRACKWISE"
                value={form.credential_ref}
                onChange={(event) => setForm({ ...form, credential_ref: event.target.value })}
              />
            </label>
          </div>
          <div className="ca-form-grid">
            <label className="ca-field">
              Record to read
              <input
                placeholder="e.g. complaints"
                value={form.source_object}
                onChange={(event) => setForm({ ...form, source_object: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Mapping (turns records into MDARIX records)
              <select
                value={form.mapping_code}
                onChange={(event) => setForm({ ...form, mapping_code: event.target.value })}
              >
                <option value="">None yet (records are only staged)</option>
                {mappingOptions(mappings.data).map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="ac-muted">
            Add the API key after creating the connection (Set API key), or enter a credential reference name here;
            never paste a key into these fields. Only a released mapping imports records; until then Sync now reads and
            stages them.
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
      <Panel eyebrow="Integrations" title="Sync runs · last 14 days" source={runs}>
        <ColumnChart data={trend} unit="runs" caption="by start date" />
        <div className="ac-inline-stats">
          <span>{outcomes.succeeded} succeeded</span>
          <span>{outcomes.failed} failed</span>
          <span>{outcomes.inProgress} other / in progress</span>
        </div>
      </Panel>
      <Panel eyebrow="Integrations" title="Run history" source={runs}>
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
    <Panel eyebrow="Integrations" title="Reconciliation" source={records}>
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
