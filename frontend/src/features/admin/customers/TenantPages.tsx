import { useState } from "react";
import { ArrowLeft, Globe2, PauseCircle, PlayCircle, Plus } from "lucide-react";
import { Panel } from "../console/charts";
import {
  ConfirmDialog,
  SearchBox,
  Table,
  Tabs,
  errorText,
  formatDate,
  send,
  useResource,
  type Confirmation,
} from "../../customer-admin/shared";
import { CustomerAdmins } from "./CustomerAdmins";
import { lifecycleAction, titleCase } from "./model";
import { StatusBadge } from "./StatusBadge";
import { DialogBehaviour } from "../../shared/DialogBehaviour";

/** Every tenant (customer workspace). Opening a row shows the tenant's page. */
export function TenantDirectory({ onOpen }: { onOpen: (tenantId: string) => void }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({ page: String(page) });
  if (query.trim()) params.set("q", query.trim());
  if (status) params.set("status", status);
  const tenants = useResource<{ items: any[]; total: number; pages: number }>(
    `/api/v1/platform-admin/tenants?${params}`,
  );
  const pages = tenants.data?.pages ?? 1;
  return (
    <Panel eyebrow="Tenants" title="Tenant directory" state={tenants.state} error={tenants.error}>
      <div className="cc-toolbar">
        <SearchBox
          value={query}
          onChange={(value) => {
            setQuery(value);
            setPage(1);
          }}
          label="Search tenant name"
        />
        <select
          aria-label="Tenant status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
        >
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="SUSPENDED">Suspended</option>
          <option value="PROVISIONED">Provisioned</option>
        </select>
      </div>
      <Table
        caption="Tenants"
        rows={tenants.data?.items ?? []}
        rowKey={(row) => row.id}
        empty={{ title: "No matching tenants", detail: "Change the search or status filter." }}
        columns={[
          {
            key: "tenant",
            fields: ["name", "tenant_key", "tenant_identifier"],
            label: "Tenant",
            render: (row) => (
              <button type="button" className="ac-link cc-stack" onClick={() => onOpen(row.id)}>
                <strong>{row.name}</strong>
                <small>{row.tenant_key ?? row.tenant_identifier}</small>
              </button>
            ),
          },
          {
            key: "customer",
            fields: ["customer_name", "customer_identifier", "customer_id"],
            label: "Customer",
            render: (row) => (
              <span className="cc-stack">
                <strong>{row.customer_name ?? "—"}</strong>
                <small>{row.customer_identifier}</small>
              </span>
            ),
          },
          {
            key: "region",
            fields: ["residency_region", "region"],
            label: "Data region",
            render: (row) => row.residency_region ?? row.region ?? "—",
          },
          {
            key: "plan",
            fields: ["plan_name", "plan_code"],
            label: "Plan",
            render: (row) => row.plan_name ?? row.plan_code ?? "—",
          },
          {
            key: "environments",
            fields: ["environment_count"],
            label: "Environments",
            numeric: true,
            render: (row) => row.environment_count ?? 0,
          },
          { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
        ]}
      />
      <div className="cc-pager">
        <span>{tenants.data?.total ?? 0} tenants</span>
        <button type="button" className="ac-secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
          Previous
        </button>
        <span>
          Page {page} of {pages}
        </span>
        <button type="button" className="ac-secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>
          Next
        </button>
      </div>
    </Panel>
  );
}

const SECTIONS = [
  "Overview",
  "Administrators",
  "Environments",
  "Domain & identity",
  "AI processing",
  "Data",
  "Activity",
] as const;
type Section = (typeof SECTIONS)[number];

export function TenantPage({
  tenantId,
  onBack,
  onOpenCustomer,
  onMessage,
}: {
  tenantId: string;
  onBack: () => void;
  onOpenCustomer?: (customerId: string) => void;
  onMessage: (text: string, tone?: "good" | "critical") => void;
}) {
  const record = useResource<{ tenant: any; environments: any[]; identity_providers: any[] }>(
    `/api/v1/platform-admin/tenants/${tenantId}`,
  );
  const [section, setSection] = useState<Section>("Overview");
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const tenant = record.data?.tenant;
  const next = lifecycleAction(tenant?.status);
  const name = tenant?.display_name ?? tenant?.tenant_key ?? "Tenant";
  const changeStanding = () =>
    next &&
    setConfirm({
      title: next === "SUSPENDED" ? `Suspend ${name}?` : `Reactivate ${name}?`,
      body:
        next === "SUSPENDED"
          ? "Nobody in this tenant can sign in until it is reactivated. Its data is kept."
          : "The tenant becomes active again and its users can sign in.",
      confirmLabel: next === "SUSPENDED" ? "Suspend tenant" : "Reactivate tenant",
      danger: next === "SUSPENDED",
      reason: { label: "Reason (kept in the audit trail)", min: 5 },
      password: true,
      run: (reason, password) =>
        send(`/api/v1/platform-admin/tenants/${tenantId}/lifecycle`, "POST", {
          status: next,
          reason,
          password,
          lock_version: tenant?.lock_version,
        }),
      done: next === "SUSPENDED" ? `${name} is suspended.` : `${name} is active again.`,
    });
  return (
    <div className="cc-page">
      <div className="cc-page-head">
        <button type="button" className="ac-link" onClick={onBack}>
          <ArrowLeft size={16} aria-hidden="true" /> Back
        </button>
        <div className="cc-title">
          <div>
            <p className="ac-eyebrow">Tenant · {tenant?.tenant_key ?? "…"}</p>
            <h2>{name}</h2>
            {tenant?.customer_name && (
              <p className="ac-muted">
                Belongs to{" "}
                {onOpenCustomer && tenant.customer_id ? (
                  <button type="button" className="ac-link" onClick={() => onOpenCustomer(tenant.customer_id)}>
                    {tenant.customer_name}
                  </button>
                ) : (
                  <strong>{tenant.customer_name}</strong>
                )}{" "}
                ({tenant.customer_identifier})
              </p>
            )}
          </div>
          <span className="cc-actions">
            <StatusBadge status={tenant?.status} />
            {next && (
              <button
                type="button"
                className={next === "SUSPENDED" ? "ca-danger" : "ac-primary"}
                onClick={changeStanding}
              >
                {next === "SUSPENDED" ? (
                  <PauseCircle size={16} aria-hidden="true" />
                ) : (
                  <PlayCircle size={16} aria-hidden="true" />
                )}{" "}
                {next === "SUSPENDED" ? "Suspend tenant" : "Reactivate tenant"}
              </button>
            )}
          </span>
        </div>
      </div>
      {record.state === "error" && (
        <p className="ca-inline-error" role="alert">
          {record.error ?? "The tenant could not be loaded."}
        </p>
      )}
      <Tabs tabs={SECTIONS} active={section} onChange={setSection} label="Tenant sections" />
      {tenant && section === "Overview" && <TenantOverview tenant={tenant} />}
      {tenant && section === "Administrators" && (
        <CustomerAdmins
          tenantId={tenantId}
          tenants={[{ id: tenantId, tenant_key: tenant.tenant_key, display_name: tenant.display_name }]}
          onMessage={onMessage}
        />
      )}
      {tenant && section === "Environments" && (
        <Environments
          tenantId={tenantId}
          rows={record.data?.environments ?? []}
          defaultRegion={tenant.residency_region ?? tenant.primary_region ?? ""}
          onChanged={(message) => {
            onMessage(message);
            record.reload();
          }}
        />
      )}
      {tenant && section === "Domain & identity" && (
        <DomainIdentity tenantId={tenantId} providers={record.data?.identity_providers ?? []} onMessage={onMessage} />
      )}
      {tenant && section === "AI processing" && (
        <TenantAiSettings tenantId={tenantId} name={name} onMessage={onMessage} />
      )}
      {tenant && section === "Data" && (
        <TenantData
          tenantId={tenantId}
          tenantKey={tenant.tenant_key}
          status={tenant.status}
          name={name}
          onMessage={onMessage}
          onChanged={() => record.reload()}
        />
      )}
      {tenant && section === "Activity" && <TenantActivity tenantId={tenantId} />}
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(message) => {
          setConfirm(null);
          onMessage(message);
          record.reload();
        }}
      />
    </div>
  );
}

const TENANT_DETAILS: Array<[string, string]> = [
  ["Tenant key", "tenant_key"],
  ["Tenant ID", "tenant_identifier"],
  ["Deployment", "deployment_model"],
  ["Primary region", "primary_region"],
  ["Data residency", "residency_region"],
  ["Database region", "database_region"],
  ["Storage region", "storage_region"],
  ["AI processing region", "ai_processing_region"],
  ["Backup region", "backup_region"],
];

function TenantOverview({ tenant }: { tenant: any }) {
  return (
    <Panel eyebrow="Workspace" title="Tenant details">
      <dl className="cc-details">
        {TENANT_DETAILS.map(([label, key]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{tenant[key] || "—"}</dd>
          </div>
        ))}
        <div>
          <dt>Cross-border processing</dt>
          <dd>{tenant.cross_border_processing_allowed ? "Allowed" : "Not allowed"}</dd>
        </div>
        <div>
          <dt>Activated</dt>
          <dd>{formatDate(tenant.activated_at)}</dd>
        </div>
      </dl>
    </Panel>
  );
}

type AiSettings = {
  ai_processing_allowed: boolean;
  monthly_token_budget: number;
  budget_is_default: boolean;
  tokens_used: number;
  requests: number;
  refused: number;
  month: string;
  models: { provider: string; model: string }[];
};

/** Whether the tenant's content may go to an AI model, its monthly token allowance, and this month's use. */
function TenantAiSettings({
  tenantId,
  name,
  onMessage,
}: {
  tenantId: string;
  name: string;
  onMessage: (text: string, tone?: "good" | "critical") => void;
}) {
  const url = `/api/v1/platform-admin/tenants/${tenantId}/ai-settings`;
  const settings = useResource<AiSettings>(url);
  const [budget, setBudget] = useState("");
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const data = settings.data;
  const on = data?.ai_processing_allowed ?? false;
  const ask = (body: Record<string, unknown>, title: string, effect: string, done: string) =>
    setConfirm({
      title,
      body: effect,
      confirmLabel: "Save",
      reason: { label: "Reason (kept in the audit trail)", min: 5 },
      run: (reason) => send(url, "PUT", { ...body, reason }),
      done,
    });
  return (
    <>
      <Panel eyebrow="AI processing" title={`AI for ${name}`} state={settings.state} error={settings.error}>
        {data && (
          <dl className="cc-details">
            <div>
              <dt>AI processing</dt>
              <dd>{on ? "On" : "Off: rule-based answers only"}</dd>
            </div>
            <div>
              <dt>Tokens used this month</dt>
              <dd>
                {data.tokens_used.toLocaleString()} of {data.monthly_token_budget.toLocaleString()}
                {data.budget_is_default ? " (server default)" : ""}
              </dd>
            </div>
            <div>
              <dt>AI requests this month</dt>
              <dd>
                {data.requests.toLocaleString()} · {data.refused.toLocaleString()} answered from rules instead
              </dd>
            </div>
            <div>
              <dt>Model in use</dt>
              <dd>{data.models.length ? data.models.map((item) => item.provider).join(", ") : "None configured"}</dd>
            </div>
          </dl>
        )}
        <div className="ca-action-row">
          <button
            type="button"
            className={on ? "ca-danger" : "ac-primary"}
            disabled={!data}
            onClick={() =>
              ask(
                { ai_processing_allowed: !on },
                on ? `Turn AI off for ${name}?` : `Turn AI on for ${name}?`,
                on
                  ? "Nothing from this tenant is sent to an AI model; its features answer from rules."
                  : "This tenant's AI features may send the records an answer needs to the configured model, with personal information masked.",
                on ? `AI processing is off for ${name}.` : `AI processing is on for ${name}.`,
              )
            }
          >
            {on ? "Turn AI off" : "Turn AI on"}
          </button>
        </div>
        <form
          className="ca-form"
          onSubmit={(event) => {
            event.preventDefault();
            const value = Number(budget);
            if (!Number.isInteger(value) || value < 0) return onMessage("Enter a whole number of tokens.", "critical");
            ask(
              { monthly_token_budget: value },
              "Change the monthly AI allowance?",
              `${name} may use up to ${value.toLocaleString()} tokens a month; after that its features answer from rules.`,
              "Monthly AI allowance saved.",
            );
          }}
        >
          <div className="ca-form-grid">
            <label className="ca-field">
              Monthly token allowance
              <input
                type="number"
                min={0}
                step={1000}
                inputMode="numeric"
                required
                placeholder={data ? String(data.monthly_token_budget) : ""}
                value={budget}
                onChange={(event) => setBudget(event.target.value)}
              />
            </label>
          </div>
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={!data}>
              Save allowance
            </button>
            {data && !data.budget_is_default && (
              <button
                type="button"
                className="ac-secondary"
                onClick={() =>
                  ask(
                    { use_default_budget: true },
                    "Use the standard allowance?",
                    "The tenant goes back to the server's standard monthly allowance.",
                    "Standard allowance restored.",
                  )
                }
              >
                Use standard allowance
              </button>
            )}
          </div>
        </form>
      </Panel>
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(message) => {
          setConfirm(null);
          setBudget("");
          onMessage(message);
          settings.reload();
        }}
      />
    </>
  );
}

type DataExport = {
  id: string;
  status: string;
  reason: string;
  summary: { tables: number; rows: number; files: number } | null;
  created_at: string;
  expires_at: string | null;
};

/** Export everything the tenant stored (to hand it back), and delete it at the end of a contract or on request. */
function TenantData({
  tenantId,
  tenantKey,
  status,
  name,
  onMessage,
  onChanged,
}: {
  tenantId: string;
  tenantKey: string;
  status: string;
  name: string;
  onMessage: (text: string, tone?: "good" | "critical") => void;
  onChanged: () => void;
}) {
  const base = `/api/v1/platform-admin/tenants/${tenantId}`;
  const exports = useResource<{ exports: DataExport[] }>(`${base}/exports`);
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [typedKey, setTypedKey] = useState("");
  const rows = exports.data?.exports ?? [];
  const busy = rows.some((row) => row.status === "QUEUED" || row.status === "RUNNING");
  const deletable = ["SUSPENDED", "TERMINATED"].includes(String(status).toUpperCase());
  return (
    <>
      <Panel eyebrow="Data" title="Exports" state={exports.state} error={exports.error}>
        <p className="ac-muted">
          A zip of every record, the audit trail and every stored file (no passwords or secrets), kept for 7 days.
        </p>
        <div className="ca-action-row">
          <button
            type="button"
            className="ac-primary"
            disabled={busy}
            onClick={() =>
              setConfirm({
                title: `Prepare a full export of ${name}?`,
                body: "The export is prepared in the background; refresh this page to download it.",
                confirmLabel: "Prepare export",
                reason: { label: "Reason (kept in the audit trail)", min: 10 },
                run: (reason) => send(`${base}/exports`, "POST", { reason }),
                done: "The export is being prepared.",
              })
            }
          >
            {busy ? "Export in progress…" : "Prepare export"}
          </button>
          <button type="button" className="ac-secondary" onClick={() => exports.reload()}>
            Refresh
          </button>
        </div>
        <Table
          caption="Exports"
          rows={rows}
          rowKey={(row) => row.id}
          empty={{ title: "No exports", detail: "Prepare one to hand the data back to the customer." }}
          columns={[
            { key: "requested", label: "Requested", render: (row) => formatDate(row.created_at) },
            { key: "status", label: "Status", render: (row) => titleCase(row.status) },
            {
              key: "contents",
              label: "Contents",
              render: (row) =>
                row.summary ? `${row.summary.rows.toLocaleString()} records · ${row.summary.files} files` : "—",
            },
            {
              key: "download",
              label: "Download",
              render: (row) =>
                row.status === "READY" ? (
                  <a className="ac-link" href={`${base}/exports/${row.id}/download`} download>
                    Download zip
                  </a>
                ) : (
                  "—"
                ),
            },
          ]}
        />
      </Panel>
      <Panel eyebrow="Danger zone" title="Delete all of this organization's data">
        <p>
          Deletes every record, the audit trail and every stored file, pseudonymizes the people and archives the
          organization. Contract history is kept. This cannot be undone; prepare an export first if the data is to be
          returned.
        </p>
        {deletable ? (
          <form
            className="ca-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (typedKey.trim() !== tenantKey) return onMessage("Type the organization key exactly.", "critical");
              setConfirm({
                title: `Delete all of ${name}'s data?`,
                body: "Everything this organization stored is deleted for good and the organization is archived.",
                confirmLabel: "Delete all data",
                danger: true,
                reason: { label: "Reason (for example the customer's written request)", min: 10 },
                password: true,
                run: (reason, password) =>
                  send(`${base}/purge`, "POST", { reason, password, confirm_tenant_key: typedKey.trim() }),
                done: `${name}'s data has been deleted.`,
              });
            }}
          >
            <label className="ca-field">
              Type the organization key <strong>{tenantKey}</strong> to confirm
              <input value={typedKey} onChange={(event) => setTypedKey(event.target.value)} autoComplete="off" />
            </label>
            <div className="ca-action-row">
              <button type="submit" className="ca-danger" disabled={busy || typedKey.trim() !== tenantKey}>
                Delete all data
              </button>
            </div>
          </form>
        ) : (
          <p className="ac-muted">Suspend or terminate the organization first.</p>
        )}
      </Panel>
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(message) => {
          setConfirm(null);
          setTypedKey("");
          onMessage(message);
          exports.reload();
          onChanged();
        }}
      />
    </>
  );
}

const ENVIRONMENT_TYPES = ["PRODUCTION", "SANDBOX", "VALIDATION", "UAT", "DEMO"];

function Environments({
  tenantId,
  rows,
  defaultRegion,
  onChanged,
}: {
  tenantId: string;
  rows: any[];
  defaultRegion: string;
  onChanged: (message: string) => void;
}) {
  const used = new Set(rows.map((row) => String(row.environment_type).toUpperCase()));
  const free = ENVIRONMENT_TYPES.filter((type) => !used.has(type));
  const [adding, setAdding] = useState(false);
  return (
    <Panel
      eyebrow="One of each type per tenant"
      title="Environments"
      action={
        <button
          type="button"
          className="ac-primary"
          onClick={() => setAdding(true)}
          disabled={!free.length}
          title={free.length ? undefined : "Every environment type already exists"}
        >
          <Plus size={16} aria-hidden="true" /> Add environment
        </button>
      }
    >
      <Table
        caption="Environments"
        rows={rows}
        rowKey={(row) => row.id}
        empty={{ title: "No environments", detail: "Add the tenant's first environment." }}
        columns={[
          {
            key: "name",
            label: "Environment",
            render: (row) => (
              <span className="cc-stack">
                <strong>{row.environment_identifier}</strong>
                <small>{titleCase(row.environment_type)}</small>
              </span>
            ),
          },
          { key: "region", label: "Region", render: (row) => row.region ?? "—" },
          { key: "residency", label: "Data residency", render: (row) => row.residency_region ?? "—" },
          { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
        ]}
      />
      {adding && (
        <AddEnvironment
          tenantId={tenantId}
          types={free}
          defaultRegion={defaultRegion}
          onClose={() => setAdding(false)}
          onAdded={(message) => {
            setAdding(false);
            onChanged(message);
          }}
        />
      )}
    </Panel>
  );
}

function AddEnvironment({
  tenantId,
  types,
  defaultRegion,
  onClose,
  onAdded,
}: {
  tenantId: string;
  types: string[];
  defaultRegion: string;
  onClose: () => void;
  onAdded: (message: string) => void;
}) {
  const [form, setForm] = useState({
    environment_type: types[0] ?? "",
    environment_identifier: "",
    region: defaultRegion,
    residency_region: defaultRegion,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await send(`/api/v1/platform-admin/tenants/${tenantId}/environments`, "POST", {
        ...form,
        environment_identifier: form.environment_identifier.trim(),
      });
      onAdded(`${titleCase(form.environment_type)} environment ${form.environment_identifier.trim()} added (draft).`);
    } catch (reason) {
      setError(errorText(reason, "The environment was not added."));
      setBusy(false);
    }
  };
  return (
    <div className="ac-modal-backdrop" role="presentation">
      <DialogBehaviour onClose={onClose} />
      <form className="ac-modal" role="dialog" aria-modal="true" aria-labelledby="cc-add-env" onSubmit={submit}>
        <p className="ac-eyebrow">Environments</p>
        <h2 id="cc-add-env">Add environment</h2>
        <label className="ca-field">
          Type
          <select
            value={form.environment_type}
            onChange={(event) => setForm({ ...form, environment_type: event.target.value })}
          >
            {types.map((type) => (
              <option key={type} value={type}>
                {titleCase(type)}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          Name
          <input
            required
            pattern="[A-Za-z0-9][A-Za-z0-9_.\-]*"
            title="Letters, numbers, dots, dashes or underscores"
            value={form.environment_identifier}
            onChange={(event) => setForm({ ...form, environment_identifier: event.target.value })}
            placeholder="e.g. acme-uat"
          />
        </label>
        <div className="cc-two-fields">
          <label className="ca-field">
            Region
            <input
              required
              value={form.region}
              onChange={(event) => setForm({ ...form, region: event.target.value })}
            />
          </label>
          <label className="ca-field">
            Data residency
            <input
              required
              value={form.residency_region}
              onChange={(event) => setForm({ ...form, residency_region: event.target.value })}
            />
          </label>
        </div>
        {error && (
          <p className="ca-inline-error" role="alert">
            {error}
          </p>
        )}
        <div className="ac-modal-actions">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy || !form.environment_type}>
            {busy ? "Adding…" : "Add environment"}
          </button>
        </div>
      </form>
    </div>
  );
}

function DomainIdentity({
  tenantId,
  providers,
  onMessage,
}: {
  tenantId: string;
  providers: any[];
  onMessage: (text: string, tone?: "good" | "critical") => void;
}) {
  const [domain, setDomain] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const verify = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await send<any>(`/api/v1/platform-admin/tenants/${tenantId}/domain-verifications`, "POST", {
        domain: domain.trim(),
        verification_method: "DNS",
        verification_token: token.trim(),
      });
      onMessage(`Domain ${domain.trim()}: ${titleCase(result.status ?? "submitted")}.`);
      setDomain("");
      setToken("");
    } catch (reason) {
      setError(errorText(reason, "The domain was not verified."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="ac-grid two">
      <Panel eyebrow="Sign-in" title="Identity providers">
        <Table
          caption="Identity providers"
          rows={providers}
          rowKey={(row) => row.id}
          empty={{ title: "Password sign-in", detail: "No single sign-on provider is configured for this tenant." }}
          columns={[
            { key: "type", label: "Provider", render: (row) => titleCase(row.provider_type) },
            { key: "mode", label: "Sign-in mode", render: (row) => titleCase(row.login_mode) },
            { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
          ]}
        />
      </Panel>
      <Panel eyebrow="Ownership" title="Verify a domain">
        <form className="cc-form" onSubmit={verify}>
          <label className="ca-field">
            Domain
            <input
              required
              value={domain}
              onChange={(event) => setDomain(event.target.value)}
              placeholder="example.com"
            />
          </label>
          <label className="ca-field">
            DNS verification token
            <input
              required
              minLength={8}
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="The TXT record value the customer published"
            />
          </label>
          {error && (
            <p className="ca-inline-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="ac-primary" disabled={busy}>
            <Globe2 size={16} aria-hidden="true" /> {busy ? "Verifying…" : "Verify domain"}
          </button>
        </form>
      </Panel>
    </div>
  );
}

function TenantActivity({ tenantId }: { tenantId: string }) {
  const activity = useResource<{ items: any[] }>(`/api/v1/platform-admin/tenants/${tenantId}/tabs/Activity`);
  return (
    <Panel eyebrow="Audit trail" title="Recent activity" state={activity.state} error={activity.error}>
      <Table
        caption="Recent tenant activity"
        rows={activity.data?.items ?? []}
        rowKey={(row) => row.id}
        empty={{ title: "No activity yet", detail: "Changes to this tenant appear here." }}
        columns={[
          { key: "when", label: "When", render: (row) => formatDate(row.created_at) },
          { key: "action", label: "What happened", render: (row) => titleCase(row.action) },
          { key: "reason", label: "Reason", render: (row) => row.details?.reason ?? "—" },
        ]}
      />
    </Panel>
  );
}
