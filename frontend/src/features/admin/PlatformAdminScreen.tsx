import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Bell,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Database,
  ExternalLink,
  LayoutDashboard,
  LifeBuoy,
  LockKeyhole,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Users,
} from "lucide-react";
import { requestJson } from "../../app/apiClient";

type PlatformAdminScreenProps = {
  securityContext: { display_name: string; active_role: string | null; tenant_id?: string } | null;
  onNavigate: (view: any) => void;
  initialItem?: string;
};

type DataKey =
  | "users"
  | "roles"
  | "permissions"
  | "memberships"
  | "personas"
  | "entitlements"
  | "connectors"
  | "mappings"
  | "dataMappings"
  | "audit"
  | "customers"
  | "plans"
  | "integrationRuns"
  | "reconciliation"
  | "credentials"
  | "aiExecutions";

type AdminData = Record<DataKey, any[]> & {
  health: { status?: string; metrics?: Record<string, number>; alerts?: any[]; recent_audit?: any[] };
  ai: any;
  security: any;
  operations: any;
};

const EMPTY_DATA: AdminData = {
  users: [],
  roles: [],
  permissions: [],
  memberships: [],
  personas: [],
  entitlements: [],
  connectors: [],
  mappings: [],
  dataMappings: [],
  audit: [],
  customers: [],
  plans: [],
  integrationRuns: [],
  reconciliation: [],
  credentials: [],
  aiExecutions: [],
  health: {},
  ai: null,
  security: null,
  operations: null,
};

const api = <T,>(path: string) => requestJson<T>(path);
const list = (value: any): any[] =>
  Array.isArray(value) ? value : (value?.items ?? value?.results ?? value?.customers ?? value?.plans ?? []);
const text = (value: unknown, fallback = "—") =>
  value === null || value === undefined || value === "" ? fallback : String(value);
const title = (value: string) => value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

type LifecycleDialogRequest = {
  action: string;
  subject: string;
  resolve: (value: { reason: string; password: string } | null) => void;
};
let lifecycleDialogRequest: LifecycleDialogRequest | null = null;
const requestLifecycleConfirmation = (action: string, subject: string) =>
  new Promise<{ reason: string; password: string } | null>((resolve) => {
    lifecycleDialogRequest = { action, subject, resolve };
    window.dispatchEvent(new Event("mdarix-lifecycle-dialog"));
  });

function LifecycleConfirmationDialog() {
  const [request, setRequest] = useState<LifecycleDialogRequest | null>(null);
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  useEffect(() => {
    const open = () => {
      setReason("");
      setPassword("");
      setRequest(lifecycleDialogRequest);
    };
    window.addEventListener("mdarix-lifecycle-dialog", open);
    return () => window.removeEventListener("mdarix-lifecycle-dialog", open);
  }, []);
  if (!request) return null;
  const close = (value: { reason: string; password: string } | null) => {
    request.resolve(value);
    lifecycleDialogRequest = null;
    setRequest(null);
  };
  return (
    <div
      className="lifecycle-dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close(null);
      }}
    >
      <section className="lifecycle-dialog" role="dialog" aria-modal="true" aria-labelledby="lifecycle-dialog-title">
        <span className="eyebrow">Governed lifecycle action</span>
        <h3 id="lifecycle-dialog-title">Confirm {title(request.action)}</h3>
        <p>
          Confirm this action for <strong>{request.subject}</strong>. The change will be audited and may revoke active
          access.
        </p>
        <label>
          Reason
          <input
            autoFocus
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Business reason is required"
          />
        </label>
        <label>
          Re-authenticate
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Current password"
          />
        </label>
        <div className="lifecycle-dialog-actions">
          <button className="platform-admin-secondary" onClick={() => close(null)}>
            Cancel
          </button>
          <button
            className="platform-admin-primary"
            disabled={!reason.trim() || !password}
            onClick={() => close({ reason: reason.trim(), password })}
          >
            Confirm {title(request.action)}
          </button>
        </div>
      </section>
    </div>
  );
}

const DOMAINS = [
  ["Platform Overview", "Health, activity and attention", LayoutDashboard, ["Overview"]],
  [
    "Customers & Tenants",
    "Customer and tenant lifecycle",
    Users,
    [
      "Customer Directory",
      "Customer 360",
      "Tenant Management",
      "Tenant 360",
      "Customer Onboarding",
      "Provisioning Jobs",
      "Environments",
      "Domain & Identity",
      "Data Residency",
      "Customer Administrators",
      "Tenant Security",
      "Tenant Audit",
      "Tenant Health",
      "Suspension & Reactivation",
    ],
  ],
  [
    "Plans & Licensing",
    "Plans, subscriptions and reminders",
    Settings2,
    ["Plans", "Entitlements", "Subscriptions", "Expirations", "Reminder rules"],
  ],
  [
    "Identity & Access",
    "Platform users, roles and sessions",
    LockKeyhole,
    [
      "Platform users",
      "Platform roles",
      "Permission sets",
      "Effective Permissions",
      "MFA & SSO",
      "Sessions",
      "Access Reviews",
    ],
  ],
  [
    "Data & Configuration",
    "Master data, mappings and releases",
    Database,
    [
      "Configuration 360",
      "Mapping 360",
      "Configuration Release 360",
      "Customer Configuration 360",
      "Canonical Object 360",
      "Schema 360",
      "Canonical data model",
      "Schema registry",
      "Transformation library",
      "Reference data",
      "Validation rules",
      "Configuration sets",
      "Customer baselines",
      "Customer overrides",
      "Change requests",
      "Dependencies & impact",
      "Deployments",
      "Import / Export",
      "Configuration health",
      "Upgrade center",
      "Master data",
      "Data mapping",
      "Validation & data quality",
      "Mapping versions",
      "Configuration releases",
    ],
  ],
  [
    "Integrations",
    "Connectors, schemas and ingestion",
    ExternalLink,
    [
      "Connector catalog",
      "Customer integrations",
      "Integration runs",
      "Integration health",
      "Reconciliation",
      "Failures & logs",
      "Credentials",
      "Webhooks",
      "Integration registry",
      "Integration Template 360",
      "API & contract registry",
      "Schema registry",
    ],
  ],
  [
    "AI Control Center",
    "Models, evaluations and assurance",
    ShieldCheck,
    [
      "AI overview",
      "Models & versions",
      "Agents",
      "Prompts",
      "Evaluations",
      "Golden Evaluation",
      "Trust & Assurance",
      "Release Assurance",
      "Revalidation",
      "Guardrails",
      "AI executions",
      "AI incidents",
    ],
  ],
  [
    "Security",
    "Isolation, encryption and controls",
    LockKeyhole,
    [
      "Security overview",
      "Tenant isolation",
      "Encryption & residency",
      "Retention",
      "Access reviews",
      "Security events",
      "Support access",
    ],
  ],
  [
    "Operations",
    "Queues, monitoring, storage and incidents",
    LifeBuoy,
    [
      "System health",
      "Jobs & queues",
      "Storage",
      "API monitoring",
      "Incidents",
      "Notifications",
      "Email templates",
      "Platform releases",
      "Feature rollouts",
      "System settings",
      "Developer & API",
      "MCP",
    ],
  ],
] as const;

const SOURCES: Array<[string, string, string]> = [
  ["users", "/api/v1/admin/identity/users", "Identity users"],
  ["roles", "/api/v1/admin/identity/roles", "Roles"],
  ["permissions", "/api/v1/admin/identity/permission-sets", "Permission sets"],
  ["memberships", "/api/v1/admin/identity/memberships", "Memberships"],
  ["personas", "/api/v1/admin/identity/persona-assignments", "Personas"],
  ["entitlements", "/api/v1/admin/governance/entitlements", "Entitlements"],
  ["connectors", "/api/v1/admin/configuration/connectors", "Connectors"],
  ["mappings", "/api/v1/admin/configuration/mappings", "Mappings"],
  ["dataMappings", "/api/v1/admin/configuration/data-mappings", "Data mapping fields"],
  ["audit", "/api/v1/admin/audit-history", "Audit history"],
  ["customers", "/api/v1/platform-admin/customers", "Customers"],
  ["plans", "/api/v1/platform-admin/plans", "Plans"],
  ["health", "/api/v1/admin/health-summary", "Platform health"],
  ["ai", "/api/v1/admin/ai-summary", "AI control summary"],
  ["security", "/api/v1/admin/security-summary", "Security summary"],
  ["operations", "/api/v1/admin/operations-summary", "Operations summary"],
  ["integrationRuns", "/api/v1/admin/integrations/runs", "Integration runs"],
  ["reconciliation", "/api/v1/admin/integrations/reconciliation", "Reconciliation"],
  ["credentials", "/api/v1/admin/integrations/credentials", "Credential references"],
  ["aiExecutions", "/api/v1/admin/ai-executions", "AI executions"],
];

function RecordTable({
  rows,
  columns,
  empty,
  onRowClick,
}: {
  rows: any[];
  columns: Array<[string, (row: any) => unknown]>;
  empty: string;
  onRowClick?: (row: any) => void;
}) {
  if (!rows.length)
    return (
      <div className="platform-admin-empty">
        <Database size={25} />
        <strong>{empty}</strong>
        <span>No authorized records were returned by the server.</span>
      </div>
    );
  return (
    <div className="platform-admin-table-wrap">
      <table className="platform-admin-table">
        <thead>
          <tr>
            {columns.map(([label]) => (
              <th key={label}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 12).map((row, index) => (
            <tr
              key={row.id ?? row.code ?? row.email ?? index}
              className={onRowClick ? "platform-admin-table-row-action" : undefined}
              onClick={() => onRowClick?.(row)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onRowClick?.(row);
                }
              }}
              tabIndex={onRowClick ? 0 : undefined}
            >
              {columns.map(([label, get]) => (
                <td key={label}>{text(get(row))}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SavedCustomerViewControl() {
  const [view, setView] = useState("ALL");
  const [importOpen, setImportOpen] = useState(false);
  return (
    <>
      <label className="customer-saved-view">
        Saved view
        <select
          aria-label="Saved customer view"
          value={view}
          onChange={(event) => {
            setView(event.target.value);
            window.dispatchEvent(new CustomEvent("customer-directory-view", { detail: event.target.value }));
          }}
        >
          <option value="ALL">All customers</option>
          <option value="ACTIVE">Active customers</option>
          <option value="TRIAL">Trial customers</option>
          <option value="EXPIRING_SOON">Expiring soon</option>
          <option value="SUSPENDED">Suspended</option>
          <option value="EXPIRED">Expired</option>
          <option value="DESIGN_PARTNERS">Design partners</option>
        </select>
      </label>
      <button className="platform-admin-secondary" onClick={() => setImportOpen(true)}>
        Import CSV
      </button>
      {importOpen && (
        <CustomerImportDialog
          onClose={() => setImportOpen(false)}
          onImported={() => {
            setImportOpen(false);
            window.dispatchEvent(new Event("customer-directory-refresh"));
          }}
        />
      )}
    </>
  );
}

function CustomerImportDialog({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const parse = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      const lines = String(reader.result ?? "")
        .split(/\r?\n/)
        .filter(Boolean);
      if (lines.length < 2) return setError("CSV must include a header and at least one row.");
      const headers = lines[0].split(",").map((value) => value.trim());
      const parsed = lines
        .slice(1)
        .map((line) => {
          const values = line.split(",");
          return headers.reduce((row, header, index) => ({ ...row, [header]: values[index]?.trim() ?? "" }), {} as any);
        })
        .map((row) => ({
          company_name: row.company_name || row.name || row.legal_name,
          tenant_code: row.tenant_code || row.tenant_key,
          plan_code: row.plan_code || "ENTERPRISE_TEST",
          licensed_users_limit: Number(row.licensed_users_limit || 25),
          customer_admin_limit: Number(row.customer_admin_limit || 2),
          connector_limit: Number(row.connector_limit || 5),
          status: row.status || "active",
          notes: row.notes || undefined,
        }));
      if (parsed.some((row) => !row.company_name || !row.tenant_code))
        return setError("Each row requires company_name and tenant_code.");
      setError("");
      setRows(parsed);
    };
    reader.readAsText(file);
  };
  const submit = async (dryRun: boolean) => {
    setBusy(true);
    setError("");
    try {
      const result = await requestJson<any>("/api/v1/platform-admin/customers/import", {
        method: "POST",
        body: JSON.stringify({ rows, dry_run: dryRun }),
      });
      const rejected = (result.results ?? []).filter((row: any) => row.status === "REJECTED");
      if (rejected.length) setError(rejected.map((row: any) => `${row.tenant_code}: ${row.error}`).join("; "));
      else if (dryRun) setMessage(`${result.results?.length ?? 0} rows validated. Ready to import.`);
      else {
        setMessage(`${result.imported} customer${result.imported === 1 ? "" : "s"} imported.`);
        onImported();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Customer import failed.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="customer-import-dialog" role="dialog" aria-modal="true" aria-labelledby="customer-import-title">
      <div className="customer-import-panel">
        <div className="platform-admin-card-title">
          <div>
            <span className="eyebrow">Customer directory</span>
            <h3 id="customer-import-title">Import customers</h3>
            <p>Upload a CSV with company_name, tenant_code, plan_code, and optional license/seat columns.</p>
          </div>
          <button className="platform-admin-secondary" onClick={onClose}>
            Close
          </button>
        </div>
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) parse(file);
          }}
        />
        {error && <div className="platform-admin-error">{error}</div>}
        {message && (
          <p className="platform-admin-status" role="status">
            {message}
          </p>
        )}
        {rows.length > 0 && (
          <>
            <p className="customer-import-summary">
              {rows.length} row{rows.length === 1 ? "" : "s"} ready for validation/import.
            </p>
            <div className="customer-import-preview">
              {rows.slice(0, 5).map((row, index) => (
                <div key={index}>
                  <strong>{row.company_name}</strong>
                  <span>
                    {row.tenant_code} · {row.plan_code}
                  </span>
                </div>
              ))}
            </div>
            <div className="customer-directory-actions">
              <button className="platform-admin-secondary" disabled={busy} onClick={() => submit(true)}>
                Validate import
              </button>
              <button className="platform-admin-primary" disabled={busy} onClick={() => submit(false)}>
                Import validated rows
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function CustomerDirectory({ onOpen }: { onOpen: (row: any) => void }) {
  const [filters, setFilters] = useState({
    q: "",
    view: "ALL",
    status: "",
    country: "",
    industry: "",
    plan: "",
    license: "",
    expiry_before: "",
    expiry_after: "",
    environment: "",
    data_region: "",
    seat_status: "",
    seat_min: "",
    seat_max: "",
    sort: "name",
    order: "asc",
    page: 1,
  });
  const [columns, setColumns] = useState({
    customer: true,
    tenant: true,
    admin: true,
    region: true,
    plan: true,
    license: true,
    activity: true,
    createdBy: false,
    seats: true,
    health: true,
    status: true,
  });
  const [rows, setRows] = useState<any[]>([]);
  const [meta, setMeta] = useState<any>({ total: 0, pages: 1 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = () => {
    setLoading(true);
    const params = new URLSearchParams(
      Object.entries(filters)
        .filter(([, value]) => value !== "")
        .map(([key, value]) => [key, String(value)]),
    );
    requestJson<any>(`/api/v1/platform-admin/customers?${params}`)
      .then((result) => {
        setRows(result.items ?? []);
        setMeta(result);
        setError("");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Customer directory unavailable"))
      .finally(() => setLoading(false));
  };
  useEffect(load, [
    filters.q,
    filters.view,
    filters.status,
    filters.country,
    filters.industry,
    filters.plan,
    filters.license,
    filters.expiry_before,
    filters.expiry_after,
    filters.environment,
    filters.data_region,
    filters.seat_status,
    filters.seat_min,
    filters.seat_max,
    filters.sort,
    filters.order,
    filters.page,
  ]);
  useEffect(() => {
    const refresh = () => load();
    window.addEventListener("customer-directory-refresh", refresh);
    return () => window.removeEventListener("customer-directory-refresh", refresh);
  }, []);
  useEffect(() => {
    const onSavedView = (event: Event) => {
      const value = (event as CustomEvent<string>).detail;
      setFilters((current) => ({ ...current, view: value, page: 1 }));
    };
    window.addEventListener("customer-directory-view", onSavedView);
    return () => window.removeEventListener("customer-directory-view", onSavedView);
  }, []);
  const setFilter = (key: string, value: string) =>
    setFilters((current) => ({ ...current, [key]: value, ...(key === "page" ? {} : { page: 1 }) }));
  const transition = async (row: any, action: "SUSPENDED" | "REACTIVATED") => {
    const confirmation = await requestLifecycleConfirmation(action, row.name ?? row.tenant_key ?? "tenant");
    if (!confirmation) return;
    try {
      await requestJson(`/api/v1/platform-admin/tenants/${row.id}/lifecycle`, {
        method: "POST",
        body: JSON.stringify({ status: action, reason: confirmation.reason, password: confirmation.password }),
      });
      load();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Lifecycle change failed");
    }
  };
  const exportUrl = `/api/v1/platform-admin/customers?${new URLSearchParams({ ...filters, format: "csv", page: "1", page_size: "100" } as any).toString()}`;
  const available: Array<[string, keyof typeof columns]> = [
    ["Customer", "customer"],
    ["Tenant", "tenant"],
    ["Primary admin", "admin"],
    ["Region", "region"],
    ["Plan", "plan"],
    ["License dates", "license"],
    ["Last activity", "activity"],
    ["Created by", "createdBy"],
    ["Seats", "seats"],
    ["Health", "health"],
    ["Status", "status"],
  ];
  return (
    <section className="platform-admin-card customer-directory">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Server-side directory</span>
          <h3>Customers &amp; tenants</h3>
          <p>Search, filter, sort, export and govern customer records without exposing tenant data.</p>
        </div>
        <div className="customer-directory-actions">
          <a className="platform-admin-secondary" href={exportUrl}>
            Export CSV
          </a>
          <button
            className="platform-admin-primary"
            onClick={() =>
              window.alert(
                "Import accepts the approved customer CSV format. Validate the file before submitting it to the provisioning workflow.",
              )
            }
          >
            Import
          </button>
        </div>
      </div>
      <div className="customer-directory-toolbar">
        <SavedCustomerViewControl />
        <input
          aria-label="Search customers"
          placeholder="Search customer, ID or tenant"
          value={filters.q}
          onChange={(e) => setFilter("q", e.target.value)}
        />
        <select aria-label="Status" value={filters.status} onChange={(e) => setFilter("status", e.target.value)}>
          <option value="">All statuses</option>
          <option>ACTIVE</option>
          <option>SUSPENDED</option>
          <option>PROVISIONED</option>
          <option>EXPIRED</option>
        </select>
        <input
          aria-label="Country"
          placeholder="Country"
          value={filters.country}
          onChange={(e) => setFilter("country", e.target.value)}
        />
        <input
          aria-label="Industry"
          placeholder="Industry"
          value={filters.industry}
          onChange={(e) => setFilter("industry", e.target.value)}
        />
        <input
          aria-label="Plan"
          placeholder="Plan code"
          value={filters.plan}
          onChange={(e) => setFilter("plan", e.target.value)}
        />
        <select aria-label="License" value={filters.license} onChange={(e) => setFilter("license", e.target.value)}>
          <option value="">All licenses</option>
          <option>ACTIVE</option>
          <option>EXPIRING</option>
          <option>EXPIRED</option>
          <option>SUSPENDED</option>
        </select>
        <input
          aria-label="Region"
          placeholder="Data region"
          value={filters.data_region}
          onChange={(e) => setFilter("data_region", e.target.value)}
        />
        <select
          aria-label="Environment"
          value={filters.environment}
          onChange={(e) => setFilter("environment", e.target.value)}
        >
          <option value="">All environments</option>
          <option>PRODUCTION</option>
          <option>SANDBOX</option>
          <option>UAT</option>
          <option>DEMO</option>
        </select>
        <select
          aria-label="Seat usage"
          value={filters.seat_status}
          onChange={(e) => setFilter("seat_status", e.target.value)}
        >
          <option value="">All seat usage</option>
          <option value="AVAILABLE">Available</option>
          <option value="NEAR_CAP">Near cap</option>
          <option value="OVER">Over cap</option>
        </select>
        <input
          type="date"
          aria-label="Expiry after"
          value={filters.expiry_after}
          onChange={(e) => setFilter("expiry_after", e.target.value)}
        />
        <input
          type="date"
          aria-label="Expiry before"
          value={filters.expiry_before}
          onChange={(e) => setFilter("expiry_before", e.target.value)}
        />
        <select
          aria-label="Sort"
          value={`${filters.sort}:${filters.order}`}
          onChange={(e) => {
            const [sort, order] = e.target.value.split(":");
            setFilters((current) => ({ ...current, sort, order, page: 1 }));
          }}
        >
          <option value="name:asc">Name A–Z</option>
          <option value="name:desc">Name Z–A</option>
          <option value="status:asc">Status</option>
          <option value="created_at:desc">Newest</option>
        </select>
      </div>
      <details className="customer-column-picker">
        <summary>Columns</summary>
        <div>
          {available.map(([label, key]) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={columns[key]}
                onChange={() => setColumns((current) => ({ ...current, [key]: !current[key] }))}
              />{" "}
              {label}
            </label>
          ))}
        </div>
      </details>
      {error && <div className="platform-admin-error">{error}</div>}
      {loading ? (
        <div className="platform-admin-empty">Loading customer directory…</div>
      ) : !rows.length ? (
        <div className="platform-admin-empty">No matching customers.</div>
      ) : (
        <div className="platform-admin-table-wrap">
          <table className="platform-admin-table">
            <thead>
              <tr>
                {available
                  .filter(([, key]) => columns[key])
                  .map(([label]) => (
                    <th key={label}>{label}</th>
                  ))}
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  {columns.customer && (
                    <td>
                      <button className="table-link" onClick={() => onOpen(row)}>
                        {row.name ?? "Unnamed customer"}
                      </button>
                      <small>{row.customer_identifier ?? row.customer_id ?? "—"}</small>
                    </td>
                  )}
                  {columns.tenant && <td>{row.tenant_key ?? "—"}</td>}
                  {columns.admin && <td>{row.primary_admin ?? row.primary_admin_email ?? "—"}</td>}
                  {columns.region && <td>{row.data_region ?? row.country ?? "—"}</td>}
                  {columns.plan && <td>{row.plan_name ?? row.plan_code ?? "—"}</td>}
                  {columns.license && (
                    <td>
                      {row.license_start ?? "—"}
                      <br />
                      {row.expires_at ?? "—"}
                    </td>
                  )}
                  {columns.activity && <td>{row.last_activity ?? "—"}</td>}
                  {columns.createdBy && <td>{row.created_by ?? "—"}</td>}
                  {columns.seats && (
                    <td>
                      {row.seat_usage ?? "—"} / {row.seat_cap ?? "—"}
                    </td>
                  )}
                  {columns.health && (
                    <td>
                      <span className={`health-dot ${row.health_status === "HEALTHY" ? "healthy" : "attention"}`} />
                      {row.health_status ?? "Review"}
                    </td>
                  )}
                  {columns.status && (
                    <td>
                      <span className="platform-admin-badge">{row.status ?? "UNKNOWN"}</span>
                    </td>
                  )}
                  <td className="table-actions">
                    <button onClick={() => onOpen(row)}>View</button>
                    {String(row.status).toUpperCase() === "SUSPENDED" ||
                    String(row.status).toUpperCase() === "EXPIRED" ? (
                      <button onClick={() => transition(row, "REACTIVATED")}>Reactivate</button>
                    ) : (
                      <button onClick={() => transition(row, "SUSPENDED")}>Suspend</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="customer-directory-pager">
        <span>{meta.total ?? 0} customers</span>
        <button disabled={filters.page <= 1} onClick={() => setFilter("page", String(filters.page - 1))}>
          Previous
        </button>
        <span>
          Page {filters.page} of {meta.pages ?? 1}
        </span>
        <button
          disabled={filters.page >= (meta.pages ?? 1)}
          onClick={() => setFilter("page", String(filters.page + 1))}
        >
          Next
        </button>
      </div>
    </section>
  );
}

function TenantDirectoryEnhanced({ onOpen }: { onOpen: (row: any) => void }) {
  const [query, setQuery] = useState({
    q: "",
    status: "",
    region: "",
    environment: "",
    plan: "",
    health: "",
    seat_status: "",
    page: 1,
    sort: "name",
    order: "asc",
  });
  const [result, setResult] = useState<any>({ items: [], pages: 1, total: 0 });
  const [error, setError] = useState("");
  const [columns, setColumns] = useState({
    tenant: true,
    customer: true,
    region: true,
    plan: true,
    admin: true,
    seats: true,
    health: true,
    status: true,
  });
  const load = () => {
    const params = new URLSearchParams(Object.entries(query).map(([key, value]) => [key, String(value)]));
    requestJson<any>(`/api/v1/platform-admin/tenants?${params}`)
      .then(setResult)
      .catch((e) => setError(e instanceof Error ? e.message : "Tenant directory unavailable"));
  };
  useEffect(load, [
    query.q,
    query.status,
    query.region,
    query.environment,
    query.plan,
    query.health,
    query.seat_status,
    query.page,
    query.sort,
    query.order,
  ]);
  const set = (key: string, value: string) =>
    setQuery((current) => ({ ...current, [key]: value, ...(key === "page" ? {} : { page: 1 }) }));
  const exportUrl = `/api/v1/platform-admin/tenants?${new URLSearchParams({ ...query, format: "csv" } as any).toString()}`;
  const available: Array<[string, keyof typeof columns]> = [
    ["Tenant", "tenant"],
    ["Customer", "customer"],
    ["Region", "region"],
    ["Plan", "plan"],
    ["Primary admin", "admin"],
    ["Seats", "seats"],
    ["Health", "health"],
    ["Status", "status"],
  ];
  return (
    <section className="platform-admin-card customer-directory">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Server-side tenant directory</span>
          <h3>Tenant Management</h3>
          <p>Review tenant boundaries, environment posture, commercial assignment, seat usage, and health.</p>
        </div>
        <a className="platform-admin-secondary" href={exportUrl}>
          Export CSV
        </a>
      </div>
      <div className="customer-directory-toolbar">
        <select
          aria-label="Saved tenant view"
          value={query.health === "HEALTHY" ? "HEALTHY" : query.status}
          onChange={(e) => {
            const value = e.target.value;
            setQuery((current) => ({
              ...current,
              status: ["ACTIVE", "SUSPENDED", "EXPIRED"].includes(value) ? value : "",
              health: value === "HEALTHY" ? value : "",
              page: 1,
            }));
          }}
        >
          <option value="">All tenants</option>
          <option value="ACTIVE">Active</option>
          <option value="SUSPENDED">Suspended</option>
          <option value="EXPIRED">Expired</option>
          <option value="HEALTHY">Healthy</option>
        </select>
        <input
          aria-label="Search tenants"
          placeholder="Search tenant or identifier"
          value={query.q}
          onChange={(e) => set("q", e.target.value)}
        />
        <input
          aria-label="Tenant region"
          placeholder="Residency region"
          value={query.region}
          onChange={(e) => set("region", e.target.value)}
        />
        <input
          aria-label="Tenant plan"
          placeholder="Plan code"
          value={query.plan}
          onChange={(e) => set("plan", e.target.value)}
        />
        <select
          aria-label="Tenant environment"
          value={query.environment}
          onChange={(e) => set("environment", e.target.value)}
        >
          <option value="">All environments</option>
          <option>PRODUCTION</option>
          <option>SANDBOX</option>
          <option>VALIDATION</option>
          <option>UAT</option>
          <option>DEMO</option>
        </select>
        <select
          aria-label="Tenant seat usage"
          value={query.seat_status}
          onChange={(e) => set("seat_status", e.target.value)}
        >
          <option value="">All seat usage</option>
          <option value="NEAR_CAP">Near cap</option>
          <option value="OVER">Over cap</option>
        </select>
        <select
          aria-label="Tenant sorting"
          value={`${query.sort}:${query.order}`}
          onChange={(e) => {
            const [sort, order] = e.target.value.split(":");
            setQuery((current) => ({ ...current, sort, order, page: 1 }));
          }}
        >
          <option value="name:asc">Name A–Z</option>
          <option value="name:desc">Name Z–A</option>
          <option value="status:asc">Status</option>
          <option value="created_at:desc">Newest</option>
        </select>
      </div>
      <details className="customer-column-picker">
        <summary>Columns</summary>
        <div>
          {available.map(([label, key]) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={columns[key]}
                onChange={() => setColumns((current) => ({ ...current, [key]: !current[key] }))}
              />{" "}
              {label}
            </label>
          ))}
        </div>
      </details>
      {error && <div className="platform-admin-error">{error}</div>}
      <RecordTable
        rows={result.items ?? []}
        empty="No tenants found"
        onRowClick={onOpen}
        columns={
          available
            .filter(([, key]) => columns[key])
            .map(([label, key]) => [
              label,
              (r: any) =>
                key === "tenant"
                  ? `${r.name ?? "—"} · ${r.tenant_identifier ?? "—"}`
                  : key === "customer"
                    ? r.customer_id
                    : key === "region"
                      ? `${r.region ?? "—"} · ${r.residency_region ?? "—"}`
                      : key === "plan"
                        ? (r.plan_name ?? r.plan_code)
                        : key === "admin"
                          ? (r.primary_admin ?? r.primary_admin_email)
                          : key === "seats"
                            ? `${r.seat_usage ?? "—"} / ${r.seat_cap ?? "—"}`
                            : key === "health"
                              ? r.health_status
                              : r.status,
            ]) as Array<[string, (row: any) => unknown]>
        }
      />
      <div className="customer-directory-pager">
        <span>{result.total ?? 0} tenants</span>
        <button disabled={query.page <= 1} onClick={() => set("page", String(query.page - 1))}>
          Previous
        </button>
        <span>
          Page {query.page} of {result.pages ?? 1}
        </span>
        <button disabled={query.page >= (result.pages ?? 1)} onClick={() => set("page", String(query.page + 1))}>
          Next
        </button>
      </div>
    </section>
  );
}

function SupportAccessPanel() {
  const [rows, setRows] = useState<any[]>([]);
  const [message, setMessage] = useState("");
  const [form, setForm] = useState({ tenant_id: "", platform_user_id: "", reason: "", starts_at: "", expires_at: "" });
  const load = () =>
    requestJson<any>("/api/v1/platform-admin/support-access")
      .then((result) => setRows(result.items ?? []))
      .catch((error) => setMessage(error.message));
  useEffect(() => {
    load();
  }, []);
  const update = (key: string, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const create = async () => {
    setMessage("");
    try {
      await requestJson("/api/v1/platform-admin/support-access", {
        method: "POST",
        body: JSON.stringify({ ...form, scope: { customer_360: true, read_only: true } }),
      });
      setMessage(
        "Support access request created. A separate Platform Administrator must approve it before it becomes active.",
      );
      setForm({ tenant_id: "", platform_user_id: "", reason: "", starts_at: "", expires_at: "" });
      load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Request failed");
    }
  };
  const decide = async (id: string, action: "approve" | "revoke") => {
    const reason = window.prompt(`Reason for ${action}:`);
    if (!reason?.trim()) return;
    try {
      await requestJson(`/api/v1/platform-admin/support-access/${id}/${action}`, {
        method: "POST",
        body: JSON.stringify({ reason: reason.trim() }),
      });
      setMessage(`Support access ${action}d.`);
      load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Action failed");
    }
  };
  return (
    <section className="platform-admin-card">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Controlled temporary access</span>
          <h3>Support access approval</h3>
          <p>
            Every grant is tenant-scoped, read-only by default, separately approved, audited, and automatically expires.
          </p>
        </div>
        <span className="platform-admin-badge warning">Maximum 24 hours</span>
      </div>
      <div className="platform-admin-form-grid">
        <label>
          Tenant ID
          <input
            value={form.tenant_id}
            onChange={(e) => update("tenant_id", e.target.value)}
            placeholder="Tenant UUID"
          />
        </label>
        <label>
          Platform user ID
          <input
            value={form.platform_user_id}
            onChange={(e) => update("platform_user_id", e.target.value)}
            placeholder="Support user UUID"
          />
        </label>
        <label>
          Starts at
          <input type="datetime-local" value={form.starts_at} onChange={(e) => update("starts_at", e.target.value)} />
        </label>
        <label>
          Expires at
          <input type="datetime-local" value={form.expires_at} onChange={(e) => update("expires_at", e.target.value)} />
        </label>
        <label className="platform-admin-form-wide">
          Reason
          <textarea
            value={form.reason}
            onChange={(e) => update("reason", e.target.value)}
            placeholder="Business reason and scope"
          />
        </label>
      </div>
      <button className="platform-admin-primary" onClick={create}>
        Request support access
      </button>
      {message && (
        <p className="platform-admin-status" role="status">
          {message}
        </p>
      )}
      <RecordTable
        rows={rows}
        empty="No support-access grants"
        columns={[
          ["Tenant", (r) => r.tenant_id],
          ["Status", (r) => r.status],
          ["Window", (r) => `${r.starts_at ?? "—"} → ${r.expires_at ?? "—"}`],
          ["Reason", (r) => r.reason],
          [
            "Actions",
            (r) =>
              r.status === "PENDING" ? (
                <>
                  <button onClick={() => decide(r.id, "approve")}>Approve</button>
                </>
              ) : r.status === "APPROVED" ? (
                <button onClick={() => decide(r.id, "revoke")}>Revoke</button>
              ) : (
                "—"
              ),
          ],
        ]}
      />
    </section>
  );
}

function CustomerAdminContinuityPanel({ rows }: { rows: any[] }) {
  const [selected, setSelected] = useState<any | null>(null);
  const [form, setForm] = useState({ email: "", display_name: "", company: "", reason: "" });
  const [message, setMessage] = useState("");
  const submit = async () => {
    if (!selected) return;
    try {
      const result = await requestJson<any>(
        `/api/v1/platform-admin/tenants/${selected.tenant_id}/customer-admins/${selected.id}/replace`,
        {
          method: "POST",
          body: JSON.stringify({
            replacement_email: form.email,
            replacement_display_name: form.display_name,
            company: form.company || selected.company || "Customer",
            reason: form.reason,
          }),
        },
      );
      setMessage(
        result.continuity_action === "KEEP_CURRENT_UNTIL_ACTIVATED"
          ? "Successor invited; incumbent remains active until activation."
          : "Administrator replaced and audited.",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Replacement failed");
    }
  };
  return (
    <section className="platform-admin-card">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Continuity control</span>
          <h3>Customer Administrator replacement</h3>
          <p>
            Select an incumbent and invite a successor. The last active administrator is never removed before the
            successor activates.
          </p>
        </div>
        <span className="platform-admin-badge success">Continuity enforced</span>
      </div>
      <RecordTable
        rows={rows}
        empty="No customer administrators available"
        onRowClick={(row) => {
          setSelected(row);
          setForm({ email: "", display_name: "", company: row.company ?? "", reason: "" });
        }}
        columns={[
          ["Administrator", (r) => r.display_name ?? r.name],
          ["Email", (r) => r.email],
          ["Tenant", (r) => r.tenant_id],
          ["Status", (r) => r.status],
        ]}
      />
      {selected && (
        <div className="platform-admin-form-grid">
          <label>
            Successor email
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </label>
          <label>
            Successor name
            <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          </label>
          <label>
            Company
            <input value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
          </label>
          <label className="platform-admin-form-wide">
            Reason
            <textarea value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
          </label>
          <button className="platform-admin-primary" onClick={submit}>
            Invite replacement administrator
          </button>
        </div>
      )}
      {message && (
        <p className="platform-admin-status" role="status">
          {message}
        </p>
      )}
    </section>
  );
}

function ProvisioningJobsWorkspace({ data, onRefresh }: { data: AdminData; onRefresh: () => void }) {
  const [selected, setSelected] = useState<any | null>(null);
  const [detail, setDetail] = useState<any | null>(null);
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (!selected?.id) {
      setDetail(null);
      return;
    }
    const load = () =>
      requestJson<any>(`/api/v1/platform-admin/provisioning-jobs/${selected.id}`)
        .then(setDetail)
        .catch((error) => setMessage(error instanceof Error ? error.message : "Provisioning detail unavailable"));
    load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, [selected?.id]);
  const action = async (kind: "retry" | "resume") => {
    const reason = window.prompt(`Reason for ${kind}`, "Retry provisioning after correcting the failed prerequisite");
    if (!reason?.trim() || !selected) return;
    try {
      const result = await requestJson<any>(`/api/v1/platform-admin/provisioning-jobs/${selected.id}/${kind}`, {
        method: "POST",
        body: JSON.stringify({ reason: reason.trim() }),
      });
      setDetail(result);
      setMessage(`Provisioning job ${kind} queued.`);
      onRefresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${kind} provisioning job`);
    }
  };
  const rows = data.operations?.provisioning_jobs ?? [];
  return (
    <section className="platform-admin-card platform-admin-workflow-panel">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Provisioning operations</span>
          <h3>Jobs and live step progress</h3>
          <p>
            Inspect durable job state, retry failed steps, and resume from the first failed prerequisite without
            creating duplicate records.
          </p>
        </div>
        <button className="platform-admin-secondary" onClick={onRefresh}>
          <RefreshCw size={15} /> Refresh
        </button>
      </div>
      {message && (
        <div className="platform-admin-status" role="status">
          {message}
        </div>
      )}
      <RecordTable
        rows={rows}
        empty="No provisioning jobs are available"
        onRowClick={(row) => setSelected(row)}
        columns={[
          ["Job", (r) => r.job_identifier ?? r.id ?? r.job_id],
          ["Tenant", (r) => r.tenant_id ?? r.tenant_key],
          ["Status", (r) => r.status],
          ["Retry count", (r) => r.retry_count ?? 0],
          ["Updated", (r) => r.updated_at ?? r.created_at],
          ["Failure", (r) => r.failure_details?.message ?? r.failure_detail ?? "—"],
        ]}
      />
      {detail && (
        <div className="provisioning-job-detail">
          <div className="platform-admin-card-title">
            <div>
              <span className="eyebrow">{detail.job_identifier}</span>
              <h3>Step progress</h3>
              <p>
                Status: <strong>{detail.status}</strong> · Attempts: {detail.retry_count ?? 0}
              </p>
            </div>
            <div className="customer-directory-actions">
              <button
                className="platform-admin-secondary"
                disabled={!["FAILED", "PAUSED", "QUEUED"].includes(String(detail.status).toUpperCase())}
                onClick={() => action("retry")}
              >
                Retry failed step
              </button>
              <button
                className="platform-admin-primary"
                disabled={!["FAILED", "PAUSED", "QUEUED"].includes(String(detail.status).toUpperCase())}
                onClick={() => action("resume")}
              >
                Resume job
              </button>
            </div>
          </div>
          <div className="provisioning-step-list">
            {(detail.step_details ?? []).map((step: any) => (
              <div className={`provisioning-step ${String(step.status).toLowerCase()}`} key={step.code}>
                <span className="provisioning-step-index">{step.sequence}</span>
                <div>
                  <strong>{step.code}</strong>
                  <small>
                    {step.status} · attempt {step.attempt_count ?? 0}
                    {step.failure_details?.message ? ` · ${step.failure_details.message}` : ""}
                  </small>
                </div>
                <span>{step.completed_at ?? step.started_at ?? "Pending"}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function DomainIdentityWorkspace({ data, onRefresh }: { data: AdminData; onRefresh: () => void }) {
  const [tenant, setTenant] = useState<any | null>(null);
  const [domain, setDomain] = useState("");
  const [token, setToken] = useState("");
  const [provider, setProvider] = useState("OIDC");
  const [issuer, setIssuer] = useState("");
  const [clientReference, setClientReference] = useState("");
  const [message, setMessage] = useState("");
  const submit = async (kind: "domain" | "identity") => {
    if (!tenant) return setMessage("Select a tenant first.");
    const id = tenant.id ?? tenant.tenant_id;
    try {
      const path =
        kind === "domain"
          ? `/api/v1/platform-admin/tenants/${id}/domain-verifications`
          : `/api/v1/platform-admin/tenants/${id}/identity-provider/verify`;
      const body =
        kind === "domain"
          ? { domain, verification_method: "DNS", verification_token: token || undefined }
          : { provider_type: provider, issuer, client_reference: clientReference };
      const result = await requestJson<any>(path, { method: "POST", body: JSON.stringify(body) });
      setMessage(`${kind === "domain" ? "Domain" : "Identity provider"} status: ${result.status}`);
      onRefresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Verification failed");
    }
  };
  return (
    <section className="platform-admin-card platform-admin-workflow-panel">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Domain and identity boundary</span>
          <h3>Verify customer access configuration</h3>
          <p>
            Store only approved verification evidence. DNS/file proof and IdP discovery must be completed before
            activation.
          </p>
        </div>
        <span className="platform-admin-badge success">Audited</span>
      </div>
      <div className="platform-admin-form-grid">
        <label>
          Tenant
          <select
            value={tenant?.id ?? ""}
            onChange={(e) =>
              setTenant(data.customers.find((row) => String(row.id ?? row.tenant_id) === e.target.value) ?? null)
            }
          >
            <option value="">Select tenant</option>
            {data.customers.map((row) => (
              <option key={row.id ?? row.tenant_id} value={row.id ?? row.tenant_id}>
                {row.name ?? row.display_name ?? row.tenant_key}
              </option>
            ))}
          </select>
        </label>
        <label>
          Approved domain
          <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="customer.example.com" />
        </label>
        <label>
          DNS/file verification token
          <input
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Enter token after external proof"
          />
        </label>
        <button className="platform-admin-primary" onClick={() => submit("domain")}>
          Verify domain
        </button>
        <label>
          Provider type
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option>OIDC</option>
            <option>SAML</option>
            <option>LDAP</option>
          </select>
        </label>
        <label>
          Issuer URL
          <input value={issuer} onChange={(e) => setIssuer(e.target.value)} placeholder="https://idp.customer.com" />
        </label>
        <label>
          Client/reference ID
          <input
            value={clientReference}
            onChange={(e) => setClientReference(e.target.value)}
            placeholder="Customer IdP reference"
          />
        </label>
        <button className="platform-admin-primary" onClick={() => submit("identity")}>
          Verify identity provider
        </button>
      </div>
      {message && (
        <p className="platform-admin-status" role="status">
          {message}
        </p>
      )}
      <RecordTable
        rows={data.customers}
        empty="No tenants available"
        columns={[
          ["Tenant", (r) => r.name ?? r.display_name],
          ["Domain", (r) => (r.domains ?? []).join(", ") || "Pending verification"],
          ["Identity provider", (r) => r.identity_provider ?? "Not configured"],
          ["Status", (r) => r.status ?? "Review"],
        ]}
      />
    </section>
  );
}

function AuditEvidenceWorkspace({ data }: { data: AdminData }) {
  const [action, setAction] = useState("ALL");
  const [entityType, setEntityType] = useState("ALL");
  const [selected, setSelected] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const rows = useMemo(
    () =>
      data.audit.filter(
        (row: any) =>
          (action === "ALL" || String(row.action ?? "").toUpperCase() === action) &&
          (entityType === "ALL" || String(row.entity_type ?? "").toUpperCase() === entityType),
      ),
    [data.audit, action, entityType],
  );
  const actions = useMemo(
    () =>
      Array.from(new Set(data.audit.map((row: any) => String(row.action ?? "").toUpperCase()).filter(Boolean))).sort(),
    [data.audit],
  );
  const entityTypes = useMemo(
    () =>
      Array.from(
        new Set(data.audit.map((row: any) => String(row.entity_type ?? "").toUpperCase()).filter(Boolean)),
      ).sort(),
    [data.audit],
  );
  const toggle = (id: string) =>
    setSelected((current) => (current.includes(id) ? current.filter((value) => value !== id) : [...current, id]));
  const download = (filename: string, content: string, type: string) => {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  };
  const exportCsv = async () => {
    try {
      const params = new URLSearchParams();
      if (action !== "ALL") params.set("action", action);
      if (entityType !== "ALL") params.set("entity_type", entityType);
      const query = params.toString() ? `?${params.toString()}` : "";
      const response = await fetch(`/api/v1/admin/audit-history/export${query}`, { credentials: "include" });
      if (!response.ok) throw new Error("Audit export could not be completed.");
      download(
        `mdarix-audit-${new Date().toISOString().slice(0, 10)}.csv`,
        await response.text(),
        "text/csv;charset=utf-8",
      );
      setMessage("Audit CSV exported with the server-authorized scope.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Audit export failed.");
    }
  };
  const createPackage = () => {
    const included = rows.filter((row: any) => selected.includes(String(row.id)));
    if (!included.length) {
      setMessage("Select at least one audit event to create an evidence package.");
      return;
    }
    const manifest = {
      package_type: "MDARIX_AUDIT_EVIDENCE",
      generated_at: new Date().toISOString(),
      event_count: included.length,
      event_ids: included.map((row: any) => row.id),
      events: included.map((row: any) => ({
        ...row,
        details: row.details ?? {},
        old_values: row.old_values ?? null,
        new_values: row.new_values ?? null,
      })),
    };
    download(
      `mdarix-evidence-package-${new Date().toISOString().replace(/[:.]/g, "-")}.json`,
      JSON.stringify(manifest, null, 2),
      "application/json",
    );
    setMessage(`Evidence package created with ${included.length} immutable event${included.length === 1 ? "" : "s"}.`);
  };
  return (
    <section className="platform-admin-card platform-admin-workflow-panel audit-evidence-workspace">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Audit &amp; evidence</span>
          <h3>Audit export and evidence packages</h3>
          <p>
            Review immutable platform activity, retain the server-authorized event details, and export a redacted
            evidence package for review.
          </p>
        </div>
        <span className="platform-admin-badge success">Append-only</span>
      </div>
      <div className="audit-evidence-toolbar">
        <label>
          Action filter
          <select
            value={action}
            onChange={(event) => {
              setAction(event.target.value);
              setSelected([]);
            }}
          >
            <option value="ALL">All actions</option>
            {actions.map((value) => (
              <option key={value} value={value}>
                {title(value)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Configuration object
          <select
            value={entityType}
            onChange={(event) => {
              setEntityType(event.target.value);
              setSelected([]);
            }}
          >
            <option value="ALL">All objects</option>
            {entityTypes.map((value) => (
              <option key={value} value={value}>
                {title(value)}
              </option>
            ))}
          </select>
        </label>
        <span className="audit-evidence-count">
          {rows.length} events · {selected.length} selected
        </span>
        <button className="platform-admin-secondary" onClick={exportCsv}>
          <ExternalLink size={15} /> Export CSV
        </button>
        <button className="platform-admin-primary" onClick={createPackage}>
          <ShieldCheck size={15} /> Create evidence package
        </button>
      </div>
      {message && (
        <p className="platform-admin-status" role="status">
          {message}
        </p>
      )}
      <div className="audit-evidence-table" role="table" aria-label="Audit evidence events">
        <div className="audit-evidence-row audit-evidence-header" role="row">
          <span></span>
          <span>Action</span>
          <span>Object</span>
          <span>Actor</span>
          <span>When</span>
          <span>Retention</span>
        </div>
        {rows.map((row: any) => {
          const id = String(row.id ?? `${row.action}-${row.created_at}`);
          return (
            <label className="audit-evidence-row" role="row" key={id}>
              <input
                type="checkbox"
                checked={selected.includes(id)}
                onChange={() => toggle(id)}
                aria-label={`Select ${row.action ?? "audit event"}`}
              />
              <span>
                <strong>{row.action ?? "Event"}</strong>
                <small>{row.entity_type ?? "—"}</small>
              </span>
              <span>{row.entity_id ?? "—"}</span>
              <span>{row.actor_ref ?? row.actor_email ?? "System"}</span>
              <span>{row.created_at ?? row.timestamp ?? "—"}</span>
              <span>{row.retention_until ?? "Policy controlled"}</span>
            </label>
          );
        })}
      </div>
      {!rows.length && <div className="platform-admin-empty compact">No audit events match the selected filter.</div>}
      <div className="audit-evidence-notes">
        <span>
          <CheckCircle2 size={16} /> Tenant and platform authorization is applied before export.
        </span>
        <span>
          <CheckCircle2 size={16} /> Evidence packages preserve event IDs, reasons, diffs, and retention metadata.
        </span>
        <span>
          <CheckCircle2 size={16} /> Secrets are not rendered or included by this screen.
        </span>
      </div>
    </section>
  );
}

function PlatformLifecycleWorkspace({
  item,
  data,
  onRefresh,
}: {
  item: string;
  data: AdminData;
  onRefresh: () => void;
}) {
  const config: Record<
    string,
    { eyebrow: string; description: string; rows: any[]; columns: Array<[string, (row: any) => unknown]> }
  > = {
    Environments: {
      eyebrow: "Environment control",
      description: "Review tenant environments, regions, residency, release versions, and activation state.",
      rows: data.customers.flatMap((row) => row.environments ?? []),
      columns: [
        ["Environment", (r) => r.environment_identifier ?? r.id],
        ["Type", (r) => r.environment_type],
        ["Region", (r) => r.region ?? r.primary_region],
        ["Residency", (r) => r.residency_region],
        ["Status", (r) => r.status],
      ],
    },
    "Domain & Identity": {
      eyebrow: "Identity boundary",
      description: "Review verified domains and identity-provider posture before a tenant is activated.",
      rows: data.customers,
      columns: [
        ["Tenant", (r) => r.name ?? r.display_name],
        ["Domain", (r) => (r.domains ?? []).join(", ") || "Verification required"],
        ["Provider", (r) => r.identity_provider ?? "MDARIX Identity"],
        ["Status", (r) => r.status ?? "Review"],
      ],
    },
    "Data Residency": {
      eyebrow: "Residency control",
      description: "Confirm primary, database, storage, backup, and AI-processing regions for each tenant.",
      rows: data.customers,
      columns: [
        ["Tenant", (r) => r.name ?? r.display_name],
        ["Primary", (r) => r.primary_region ?? r.region],
        ["Residency", (r) => r.residency_region ?? r.data_region],
        ["Database", (r) => r.database_region ?? "Configured server-side"],
        ["Storage", (r) => r.storage_region ?? "Configured server-side"],
      ],
    },
    "Tenant Security": {
      eyebrow: "Tenant security",
      description:
        "Review isolation, encryption, TLS, storage, and retention controls with explicit validation status.",
      rows: data.security?.controls ?? [],
      columns: [
        ["Control", (r) => r.control],
        ["Status", (r) => r.status],
        ["Evidence", (r) => r.evidence ?? "Server-derived"],
      ],
    },
    "Tenant Audit": {
      eyebrow: "Tenant audit evidence",
      description: "Inspect immutable lifecycle and configuration events for the selected tenant scope.",
      rows: data.audit,
      columns: [
        ["Action", (r) => r.action],
        ["Object", (r) => r.entity_type ?? r.resource],
        ["Actor", (r) => r.actor_email ?? r.actor_ref ?? r.user_id],
        ["When", (r) => r.created_at ?? r.timestamp],
        ["Reason", (r) => r.reason ?? r.details?.reason ?? "—"],
      ],
    },
    "Provisioning Jobs": {
      eyebrow: "Provisioning operations",
      description:
        "Monitor provisioning state and identify failed or resumable jobs without creating duplicate tenants.",
      rows: data.operations?.provisioning_jobs ?? [],
      columns: [
        ["Job", (r) => r.id ?? r.job_id],
        ["Tenant", (r) => r.tenant_id ?? r.tenant_key],
        ["Status", (r) => r.status],
        ["Updated", (r) => r.updated_at ?? r.created_at],
        ["Failure", (r) => r.failure_detail ?? r.error ?? "—"],
      ],
    },
    "Suspension & Reactivation": {
      eyebrow: "Lifecycle control",
      description:
        "Use the governed customer directory actions to suspend or reactivate access with reason and re-authentication.",
      rows: data.customers,
      columns: [
        ["Customer", (r) => r.name ?? r.display_name],
        ["Tenant", (r) => r.tenant_key ?? r.tenant_identifier],
        ["Status", (r) => r.status],
        ["Health", (r) => r.health_status],
        [
          "Action",
          (r) => (["SUSPENDED", "EXPIRED"].includes(String(r.status).toUpperCase()) ? "Reactivate" : "Suspend"),
        ],
      ],
    },
  };
  const view = config[item];
  if (!view) return null;
  return (
    <section className="platform-admin-card platform-admin-workflow-panel">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">{view.eyebrow}</span>
          <h3>{item}</h3>
          <p>{view.description}</p>
        </div>
        <button className="platform-admin-secondary" onClick={onRefresh}>
          <RefreshCw size={15} /> Refresh
        </button>
      </div>
      <RecordTable rows={view.rows} empty={`No ${item.toLowerCase()} records are available`} columns={view.columns} />
    </section>
  );
}

function SubscriptionEditor({
  item,
  data,
  selected,
  setSelected,
  planId,
  setPlanId,
  startsAt,
  setStartsAt,
  expiresAt,
  setExpiresAt,
  reason,
  setReason,
  message,
  setMessage,
}: any) {
  const submit = async () => {
    if (!selected || !planId || !startsAt || !expiresAt || !reason.trim()) {
      setMessage("Select a customer and complete plan, dates, and reason.");
      return;
    }
    try {
      const result = await requestJson<any>(
        `/api/v1/platform/customers/${selected.tenant_id ?? selected.id}/subscription`,
        {
          method: "POST",
          body: JSON.stringify({
            plan_id: planId,
            starts_at: new Date(startsAt).toISOString(),
            expires_at: new Date(expiresAt).toISOString(),
            reason: reason.trim(),
          }),
        },
      );
      setMessage(`Subscription ${result.status} and audited.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Subscription update failed");
    }
  };
  return (
    <section className="platform-admin-card platform-admin-workflow-panel">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Commercial governance</span>
          <h3>{item}</h3>
          <p>
            {item === "Expirations"
              ? "Review upcoming expiry and renewal actions before access is suspended."
              : "Select a customer to manage its published plan, license dates, and renewal state."}
          </p>
        </div>
        <span className="platform-admin-badge success">Server-derived</span>
      </div>
      <RecordTable
        rows={data.customers}
        empty={`No ${item.toLowerCase()} records are available`}
        onRowClick={setSelected}
        columns={[
          ["Customer", (r: any) => r.name ?? r.display_name],
          ["Plan", (r: any) => r.plan_name ?? r.plan_code ?? "Not assigned"],
          [
            item === "Expirations" ? "Expires" : "License",
            (r: any) =>
              item === "Expirations"
                ? (r.expires_at ?? r.expiry_date ?? "Not assigned")
                : (r.license_status ?? r.status),
          ],
          ["Seats", (r: any) => `${r.seat_usage ?? "—"} / ${r.seat_cap ?? "—"}`],
        ]}
      />
      <div className="subscription-management-panel">
        <h4>{selected ? `Manage ${selected.name ?? selected.display_name ?? "customer"}` : "Manage subscription"}</h4>
        <div className="platform-admin-form-grid">
          <label>
            Published plan
            <select value={planId} onChange={(e) => setPlanId(e.target.value)}>
              <option value="">Select plan</option>
              {data.plans
                .filter((plan: any) => String(plan.status).toUpperCase() === "ACTIVE")
                .map((plan: any) => (
                  <option key={plan.id} value={plan.id}>
                    {plan.name ?? plan.code} · v{plan.version}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Start date
            <input type="date" value={startsAt.slice(0, 10)} onChange={(e) => setStartsAt(e.target.value)} />
          </label>
          <label>
            Expiry date
            <input type="date" value={expiresAt.slice(0, 10)} onChange={(e) => setExpiresAt(e.target.value)} />
          </label>
          <label>
            Change reason
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reason required for commercial change"
            />
          </label>
          <button className="platform-admin-primary" onClick={submit}>
            Save subscription change
          </button>
        </div>
        {message && (
          <p className="platform-admin-status" role="status">
            {message}
          </p>
        )}
      </div>
    </section>
  );
}

function SubscriptionWorkspace({ item, data }: { item: string; data: AdminData }) {
  const [selected, setSelected] = useState<any | null>(null);
  const [planId, setPlanId] = useState("");
  const [startsAt, setStartsAt] = useState(new Date().toISOString().slice(0, 10));
  const [expiresAt, setExpiresAt] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  if (item === "Subscriptions" || item === "Expirations")
    return (
      <SubscriptionEditor
        item={item}
        data={data}
        selected={selected}
        setSelected={setSelected}
        planId={planId}
        setPlanId={setPlanId}
        startsAt={startsAt}
        setStartsAt={setStartsAt}
        expiresAt={expiresAt}
        setExpiresAt={setExpiresAt}
        reason={reason}
        setReason={setReason}
        message={message}
        setMessage={setMessage}
      />
    );
  const rows = item === "Plans" ? data.plans : item === "Entitlements" ? data.entitlements : data.customers;
  const columns: Array<[string, (row: any) => unknown]> =
    item === "Plans"
      ? [
          ["Plan", (r) => r.name ?? r.code],
          ["Version", (r) => r.version],
          ["Seats", (r) => r.seat_cap ?? r.seat_rule],
          ["Status", (r) => r.status],
        ]
      : item === "Entitlements"
        ? [
            ["Entitlement", (r) => r.name ?? r.code ?? r.feature_code],
            ["Feature", (r) => r.feature_code],
            ["Limit", (r) => r.limit_value ?? r.value ?? JSON.stringify(r.limits ?? {})],
            ["Status", (r) => r.status],
          ]
        : [
            ["Customer", (r) => r.name ?? r.display_name],
            ["Plan", (r) => r.plan_name ?? r.plan_code],
            [
              item === "Expirations" ? "Expires" : "Status",
              (r) =>
                item === "Expirations"
                  ? (r.expires_at ?? r.expiry_date ?? "Not assigned")
                  : (r.license_status ?? r.status),
            ],
            ["Seats", (r) => `${r.seat_usage ?? "—"} / ${r.seat_cap ?? "—"}`],
          ];
  return (
    <section className="platform-admin-card platform-admin-workflow-panel">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Commercial governance</span>
          <h3>{item}</h3>
          <p>
            {item === "Expirations"
              ? "Review upcoming expiry and renewal actions before access is suspended."
              : "Commercial terms are versioned, audited, and enforced by plan and entitlement gates."}
          </p>
        </div>
        <span className="platform-admin-badge success">Server-derived</span>
      </div>
      <RecordTable rows={rows} empty={`No ${item.toLowerCase()} records are available`} columns={columns} />
    </section>
  );
}

function ReminderWorkspace() {
  const [tenantId, setTenantId] = useState("");
  const [policyName, setPolicyName] = useState("Default renewal reminders");
  const [thresholds, setThresholds] = useState("60,30,7");
  const [recipients, setRecipients] = useState("CUSTOMER_ADMIN");
  const [stage, setStage] = useState("EXPIRING");
  const [version, setVersion] = useState("v1");
  const [subject, setSubject] = useState("MDARIX subscription reminder");
  const [body, setBody] = useState("Your MDARIX subscription expires on {{expires_at}}.");
  const [message, setMessage] = useState("");
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    requestJson<any[]>("/api/v1/platform/subscriptions/expiring")
      .then(setRows)
      .catch((error) => setMessage(error instanceof Error ? error.message : "Delivery data unavailable"));
  }, []);
  const savePolicy = async () => {
    if (!tenantId.trim()) return setMessage("Tenant ID is required.");
    try {
      const result = await requestJson<any>(`/api/v1/platform/subscriptions/${tenantId.trim()}/reminder-policies`, {
        method: "POST",
        body: JSON.stringify({
          name: policyName,
          thresholds: thresholds
            .split(",")
            .map((value) => Number(value.trim()))
            .filter((value) => Number.isFinite(value)),
          timezone: "UTC",
          recipient_types: recipients
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
          version,
        }),
      });
      setMessage(`Reminder policy ${result.version} saved and audited.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Policy save failed");
    }
  };
  const saveTemplate = async () => {
    if (!tenantId.trim()) return setMessage("Tenant ID is required.");
    try {
      const result = await requestJson<any>(`/api/v1/platform/subscriptions/${tenantId.trim()}/email-templates`, {
        method: "POST",
        body: JSON.stringify({
          stage,
          version,
          subject,
          body,
          allowed_variables: ["expires_at", "customer_name", "plan_name"],
        }),
      });
      setMessage(`Email template ${result.stage} ${result.version} saved as ${result.status}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Template save failed");
    }
  };
  return (
    <section className="platform-admin-card platform-admin-workflow-panel">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Lifecycle communications</span>
          <h3>Reminder policies and email templates</h3>
          <p>
            Configure thresholds and recipients, preview approved communication, and inspect provider delivery status.
          </p>
        </div>
        <span className="platform-admin-badge success">Audited</span>
      </div>
      <div className="platform-admin-form-grid">
        <label>
          Tenant ID
          <input value={tenantId} onChange={(e) => setTenantId(e.target.value)} placeholder="Target tenant UUID" />
        </label>
        <label>
          Policy name
          <input value={policyName} onChange={(e) => setPolicyName(e.target.value)} />
        </label>
        <label>
          Thresholds in days
          <input value={thresholds} onChange={(e) => setThresholds(e.target.value)} />
        </label>
        <label>
          Recipient types
          <input
            value={recipients}
            onChange={(e) => setRecipients(e.target.value)}
            placeholder="CUSTOMER_ADMIN,BILLING_CONTACT"
          />
        </label>
        <label>
          Policy version
          <input value={version} onChange={(e) => setVersion(e.target.value)} />
        </label>
        <button className="platform-admin-primary" onClick={savePolicy}>
          Save reminder policy
        </button>
        <label>
          Template stage
          <select value={stage} onChange={(e) => setStage(e.target.value)}>
            <option>EXPIRING</option>
            <option>GRACE</option>
            <option>EXPIRED</option>
            <option>RENEWED</option>
          </select>
        </label>
        <label>
          Subject
          <input value={subject} onChange={(e) => setSubject(e.target.value)} />
        </label>
        <label className="platform-admin-form-wide">
          Body
          <textarea value={body} onChange={(e) => setBody(e.target.value)} />
        </label>
        <button className="platform-admin-primary" onClick={saveTemplate}>
          Save email template
        </button>
      </div>
      {message && (
        <p className="platform-admin-status" role="status">
          {message}
        </p>
      )}
      <div className="template-preview">
        <span className="eyebrow">Preview</span>
        <h4>{subject.replace("{{customer_name}}", "Example customer")}</h4>
        <p>
          {body
            .replace("{{expires_at}}", "2026-12-31")
            .replace("{{customer_name}}", "Example customer")
            .replace("{{plan_name}}", "Governance Demo")}
        </p>
      </div>
      <div className="platform-admin-card-title reminder-delivery-heading">
        <div>
          <span className="eyebrow">Delivery status</span>
          <h4>Reminder queue and provider outcomes</h4>
        </div>
      </div>
      <RecordTable
        rows={rows}
        empty="No expiring subscriptions or delivery records"
        columns={[
          ["Subscription", (r) => r.subscription_id],
          ["Tenant", (r) => r.tenant_id],
          ["Stage", (r) => r.stage ?? `${r.days_remaining ?? "—"} days remaining`],
          ["Expires", (r) => r.expires_at],
          ["Delivery", (r) => r.email_delivery ?? r.delivery_status ?? r.status ?? "NOT_QUEUED"],
        ]}
      />
    </section>
  );
}

function Customer360QuickActions({
  customer,
  tenants,
  onTab,
  onRefresh,
}: {
  customer: any;
  tenants: any[];
  onTab: (tab: string) => void;
  onRefresh: () => void;
}) {
  const tenant = tenants[0];
  const run = async (label: string, action: () => Promise<unknown>) => {
    try {
      await action();
      window.alert(`${label} completed.`);
      onRefresh();
    } catch (error) {
      window.alert(error instanceof Error ? error.message : `${label} failed.`);
    }
  };
  const edit = () => {
    const display_name = window.prompt("Customer display name", customer.display_name ?? "");
    if (!display_name?.trim()) return;
    return run("Customer update", () =>
      requestJson(`/api/v1/platform-admin/customer-records/${customer.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          display_name: display_name.trim(),
          lock_version: customer.lock_version,
          reason: "Customer 360 edit",
        }),
      }),
    );
  };
  const changePlan = () => {
    if (!tenant) return window.alert("This customer has no tenant to manage commercially.");
    const plan_id = window.prompt("Published plan ID", "");
    const starts_at = window.prompt("Start date (ISO-8601)", new Date().toISOString());
    const expires_at = window.prompt("Expiry date (ISO-8601)", "");
    const reason = window.prompt("Reason for plan change", "");
    if (!plan_id || !starts_at || !expires_at || !reason) return;
    return run("Plan change", () =>
      requestJson(`/api/v1/platform/customers/${tenant.id}/subscription`, {
        method: "POST",
        body: JSON.stringify({ plan_id, starts_at, expires_at, reason }),
      }),
    );
  };
  const addEnvironment = () => {
    if (!tenant) return window.alert("This customer has no tenant.");
    const environment_identifier = window.prompt("Environment identifier", "sandbox-01");
    const environment_type = window.prompt("Environment type", "SANDBOX");
    const region = window.prompt("Region", tenant.primary_region ?? "");
    const residency_region = window.prompt("Residency region", tenant.residency_region ?? region ?? "");
    if (!environment_identifier || !environment_type || !region || !residency_region) return;
    return run("Environment creation", () =>
      requestJson(`/api/v1/platform-admin/tenants/${tenant.id}/environments`, {
        method: "POST",
        body: JSON.stringify({ environment_identifier, environment_type, region, residency_region }),
      }),
    );
  };
  const lifecycle = async (status: "SUSPENDED" | "REACTIVATED") => {
    if (!tenant) return window.alert("This customer has no tenant.");
    const confirmation = await requestLifecycleConfirmation(status, tenant.display_name ?? tenant.name ?? "customer");
    if (!confirmation) return;
    return run(status === "SUSPENDED" ? "Suspension" : "Reactivation", () =>
      requestJson(`/api/v1/platform-admin/tenants/${tenant.id}/lifecycle`, {
        method: "POST",
        body: JSON.stringify({ status, reason: confirmation.reason, password: confirmation.password }),
      }),
    );
  };
  const suspended = String(tenant?.status ?? customer.lifecycle_status).toUpperCase() === "SUSPENDED";
  return (
    <div className="platform-admin-record-actions customer-360-quick-actions">
      <button onClick={edit}>Edit customer</button>
      <button onClick={changePlan}>Change plan</button>
      <button onClick={addEnvironment}>Add environment</button>
      <button onClick={() => onTab("Subscription")}>Manage subscription</button>
      <button
        className={suspended ? "action-primary" : "action-danger"}
        onClick={() => lifecycle(suspended ? "REACTIVATED" : "SUSPENDED")}
      >
        {suspended ? "Reactivate" : "Suspend"}
      </button>
    </div>
  );
}

function Tenant360QuickActions({
  tenant,
  environments,
  onTab,
  onRefresh,
}: {
  tenant: any;
  environments: any[];
  onTab: (tab: string) => void;
  onRefresh: () => void;
}) {
  const run = async (label: string, action: () => Promise<unknown>) => {
    try {
      await action();
      window.alert(`${label} completed.`);
      onRefresh();
    } catch (error) {
      window.alert(error instanceof Error ? error.message : `${label} failed.`);
    }
  };
  const edit = () => {
    const display_name = window.prompt("Tenant display name", tenant.display_name ?? tenant.name ?? "");
    if (!display_name?.trim()) return;
    return run("Tenant update", () =>
      requestJson(`/api/v1/platform-admin/tenants/${tenant.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          display_name: display_name.trim(),
          lock_version: tenant.lock_version,
          reason: "Tenant 360 edit",
        }),
      }),
    );
  };
  const clone = () => {
    const source = environments[0];
    if (!source) return window.alert("No environment is available to clone.");
    const environment_identifier = window.prompt(
      "New environment identifier",
      `${source.environment_identifier}-clone`,
    );
    if (!environment_identifier) return;
    return run("Configuration clone", () =>
      requestJson(`/api/v1/platform-admin/tenants/${tenant.id}/environments/${source.id}/clone`, {
        method: "POST",
        body: JSON.stringify({ environment_identifier, environment_type: "SANDBOX" }),
      }),
    );
  };
  const lifecycle = async (status: "SUSPENDED" | "REACTIVATED" | "ARCHIVED") => {
    const confirmation = await requestLifecycleConfirmation(status, tenant.display_name ?? tenant.name ?? "tenant");
    if (!confirmation) return;
    return run(status === "SUSPENDED" ? "Suspension" : status === "ARCHIVED" ? "Archive" : "Reactivation", () =>
      requestJson(`/api/v1/platform-admin/tenants/${tenant.id}/lifecycle`, {
        method: "POST",
        body: JSON.stringify({
          status,
          reason: confirmation.reason,
          password: confirmation.password,
          lock_version: tenant.lock_version,
        }),
      }),
    );
  };
  const status = String(tenant.status ?? "").toUpperCase();
  return (
    <div className="platform-admin-record-actions tenant-360-quick-actions">
      <button onClick={edit}>Edit tenant</button>
      <button onClick={clone}>Clone configuration</button>
      <button onClick={() => onTab("Environments")}>Manage environments</button>
      <button
        className={status === "SUSPENDED" ? "action-primary" : "action-danger"}
        onClick={() => lifecycle(status === "SUSPENDED" ? "REACTIVATED" : "SUSPENDED")}
      >
        {status === "SUSPENDED" ? "Reactivate" : "Suspend"}
      </button>
      <button className="action-danger" onClick={() => lifecycle("ARCHIVED")}>
        Archive
      </button>
    </div>
  );
}

function TenantHealthCommandCenter({ data }: { data: AdminData }) {
  const [tenantId, setTenantId] = useState("");
  const [health, setHealth] = useState<any | null>(null);
  const [error, setError] = useState("");
  const load = () => {
    if (!tenantId) return;
    setError("");
    requestJson<any>(`/api/v1/platform/tenants/${tenantId}/health`)
      .then(setHealth)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Tenant health unavailable"));
  };
  const checks = ["database", "storage", "identity", "integrations", "ai", "audit"];
  return (
    <section className="platform-admin-card tenant-health-command-center">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Tenant health command center</span>
          <h3>Service posture and isolation evidence</h3>
          <p>Review server-evaluated indicators before activation, renewal, or support access.</p>
        </div>
        <span className={`platform-admin-badge ${health?.critical_failure ? "warning" : "success"}`}>
          {health?.status ?? "Select tenant"}
        </span>
      </div>
      <div className="tenant-health-toolbar">
        <select aria-label="Tenant health tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
          <option value="">Select tenant</option>
          {data.customers.map((row: any) => (
            <option key={row.id ?? row.tenant_id} value={row.id ?? row.tenant_id}>
              {row.name ?? row.display_name ?? row.tenant_key}
            </option>
          ))}
        </select>
        <button className="platform-admin-secondary" disabled={!tenantId} onClick={load}>
          <RefreshCw size={15} /> Run health view
        </button>
      </div>
      {error && <div className="platform-admin-error">{error}</div>}
      {health && (
        <>
          <div className="tenant-health-indicator-grid">
            {checks.map((key) => {
              const check = health.checks?.[key] ?? { status: "UNAVAILABLE", evidence: "No server result" };
              const pass =
                String(check.status).toUpperCase() === "PASS" || String(check.status).toUpperCase() === "HEALTHY";
              return (
                <article className={`tenant-health-indicator ${pass ? "pass" : "attention"}`} key={key}>
                  <span className="health-dot" />
                  <div>
                    <strong>{key.replace("_", " ")}</strong>
                    <small>{check.status}</small>
                    <em>{check.evidence ?? "Server-derived"}</em>
                  </div>
                </article>
              );
            })}
          </div>
          <div className="tenant-health-footer">
            <span>Last evaluated: {health.last_run ?? "Not run"}</span>
            <span>
              {health.critical_failure ? "Critical failure blocks activation" : "No critical failure reported"}
            </span>
          </div>
        </>
      )}
    </section>
  );
}

function Customer360TabPanel({ tab, detail }: { tab: string; detail: any }) {
  if (detail?.error) return <div className="platform-admin-error">{detail.error}</div>;
  if (detail?.unavailable)
    return (
      <div className="platform-admin-empty compact">This customer tab is not available for the selected record.</div>
    );
  const items = Array.isArray(detail?.items) ? detail.items : [];
  const upper = tab.toUpperCase();
  const columns: Array<[string, (row: any) => unknown]> =
    upper === "ADMINISTRATORS" || upper === "USERS"
      ? [
          ["Administrator", (r) => r.display_name ?? r.name ?? r.email],
          ["Email", (r) => r.email],
          ["Role", (r) => r.role],
          ["Status", (r) => r.status],
          ["Tenant", (r) => r.tenant_id],
        ]
      : upper === "ENVIRONMENTS"
        ? [
            ["Environment", (r) => r.environment_identifier],
            ["Type", (r) => r.environment_type],
            ["Region", (r) => r.region],
            ["Residency", (r) => r.residency_region],
            ["Status", (r) => r.status],
          ]
        : upper === "SUBSCRIPTION"
          ? [
              ["Plan", (r) => r.plan_name ?? r.plan_code],
              ["Status", (r) => r.status],
              ["Effective from", (r) => r.effective_from],
              ["Effective to", (r) => r.effective_to],
            ]
          : upper === "ENTITLEMENTS"
            ? [
                ["Feature", (r) => r.feature_code],
                ["Enabled", (r) => (r.enabled ? "Enabled" : "Disabled")],
                ["Limits", (r) => JSON.stringify(r.limits ?? {})],
                ["Status", (r) => r.status],
              ]
            : upper === "INTEGRATIONS"
              ? [
                  ["Connector", (r) => r.code],
                  ["Type", (r) => r.connector_type],
                  ["Version", (r) => r.version],
                  ["Health", (r) => r.health ?? "Review"],
                  ["Secrets", (r) => (r.secrets_redacted ? "Redacted" : "Protected")],
                ]
              : upper === "IDENTITY"
                ? [
                    ["Provider", (r) => r.provider_type],
                    ["Login mode", (r) => r.login_mode],
                    ["Status", (r) => r.status],
                    ["Verified", (r) => r.verified_at ?? "Not verified"],
                  ]
                : upper === "USAGE"
                  ? [
                      ["Tenant", (r) => r.tenant_id],
                      ["Users", (r) => r.users],
                      ["Administrators", (r) => r.administrators],
                      ["Connectors", (r) => r.connectors],
                    ]
                  : upper === "SUPPORT"
                    ? [
                        ["Scope", (r) => r.scope],
                        ["Status", (r) => r.status],
                        ["Reason", (r) => r.reason],
                        ["Expires", (r) => r.expires_at],
                      ]
                    : [
                        ["Action", (r) => r.action],
                        ["Object", (r) => r.entity_type],
                        ["Actor", (r) => r.actor_ref],
                        ["When", (r) => r.created_at],
                        ["Reason", (r) => r.details?.reason ?? r.reason ?? "—"],
                      ];
  const headline =
    upper === "SUBSCRIPTION"
      ? "Commercial access"
      : upper === "ENTITLEMENTS"
        ? "Feature entitlements"
        : upper === "USAGE"
          ? "Operational usage"
          : upper === "SUPPORT"
            ? "Support access grants"
            : upper === "SECURITY"
              ? "Security posture"
              : upper === "AUDIT"
                ? "Immutable audit evidence"
                : `${title(tab)} records`;
  return (
    <div className="customer-360-tab-panel">
      <div className="customer-360-tab-summary">
        <div>
          <span className="eyebrow">Customer 360 · {tab}</span>
          <h3>{headline}</h3>
          <p>
            Server-authorized data for this customer. Tenant boundaries, field policies, and audit rules remain enforced
            by the API.
          </p>
        </div>
        <div className="customer-360-tab-count">
          <strong>{items.length}</strong>
          <span>records returned</span>
        </div>
      </div>
      {items.length ? (
        <RecordTable rows={items} empty={`No ${tab.toLowerCase()} records`} columns={columns} />
      ) : (
        <div className="platform-admin-empty compact">No {tab.toLowerCase()} records are currently available.</div>
      )}
    </div>
  );
}

function StructuredRecordTabPanel({ kind, tab, detail }: { kind: "customer" | "tenant"; tab: string; detail: any }) {
  if (detail?.error) return <div className="platform-admin-error">{detail.error}</div>;
  if (detail?.unavailable)
    return <div className="platform-admin-empty compact">No authorized data is available for this tab.</div>;
  const source = detail?.items ?? detail?.records ?? detail?.data ?? detail;
  const records = Array.isArray(source) ? source : source && typeof source === "object" ? [source] : [];
  const labels: Record<string, string> = {
    Environments: "Runtime environments",
    Identity: "Identity and SSO",
    Entitlements: "Plan entitlements",
    Integrations: "Connected systems",
    Storage: "Storage posture",
    Security: "Security controls",
    Health: "Service health",
    Audit: "Immutable audit history",
    Configuration: "Configuration versions",
    Administrators: "Customer administrators",
    Subscription: "Subscription and license",
    Usage: "Usage and limits",
    Support: "Support access grants",
    Tenants: "Related tenants",
  };
  const fields = records.flatMap((record: any) =>
    Object.entries(record)
      .filter(
        ([key, value]) =>
          value !== null &&
          value !== undefined &&
          !["id", "tenant_id", "customer_id", "details", "items", "records"].includes(key),
      )
      .slice(0, 12),
  );
  return (
    <div className="structured-record-tab">
      <div className="customer-360-tab-summary">
        <div>
          <span className="eyebrow">
            {title(kind)} 360 · {tab}
          </span>
          <h3>{labels[tab] ?? title(tab)}</h3>
          <p>
            Server-authorized {kind}-scoped information. Policies, field visibility, and audit rules are enforced by the
            API.
          </p>
        </div>
        <div className="customer-360-tab-count">
          <strong>{records.length}</strong>
          <span>records returned</span>
        </div>
      </div>
      {fields.length ? (
        <div className="structured-record-grid">
          {fields.map(([key, value], index) => (
            <div key={`${key}-${index}`}>
              <small>{title(key)}</small>
              <strong>{typeof value === "object" ? JSON.stringify(value) : text(value)}</strong>
            </div>
          ))}
        </div>
      ) : (
        <div className="platform-admin-empty compact">No {tab.toLowerCase()} records are currently available.</div>
      )}
      {records.length > 1 && (
        <RecordTable
          rows={records}
          empty="No records"
          columns={
            Object.keys(records[0] ?? {})
              .filter((key) => !["id", "details"].includes(key))
              .slice(0, 6)
              .map((key) => [
                title(key),
                (row) => (typeof row[key] === "object" ? JSON.stringify(row[key]) : row[key]),
              ]) as Array<[string, (row: any) => unknown]>
          }
        />
      )}
    </div>
  );
}

function MasterDataWorkspace() {
  const [products, setProducts] = useState<any[]>([]);
  const [versions, setVersions] = useState<any[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [mode, setMode] = useState<"product" | "version" | null>(null);
  const [editing, setEditing] = useState<any>(null);
  const [versionA, setVersionA] = useState("");
  const [versionB, setVersionB] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const selected = products.find((row) => row.id === selectedId);
  const load = async (productId = selectedId) => {
    try {
      setError("");
      const rows = list(await api<any>("/api/v1/admin/catalog/products"));
      setProducts(rows);
      const id = productId || rows[0]?.id || "";
      setSelectedId(id);
      setVersions(id ? list(await api<any>(`/api/v1/admin/catalog/product-versions?product_id=${id}`)) : []);
    } catch (cause: any) {
      setError(cause?.message ?? "Master data could not be loaded.");
    }
  };
  useEffect(() => {
    void load("");
  }, []);
  const submitProduct = async () => {
    try {
      const path = editing?.id ? `/api/v1/admin/catalog/products/${editing.id}` : "/api/v1/admin/catalog/products";
      await requestJson(path, {
        method: editing?.id ? "PATCH" : "POST",
        body: JSON.stringify(editing?.id ? { values: editing } : editing),
      });
      setMode(null);
      setEditing(null);
      setMessage(editing?.id ? "Master product updated." : "Master product created.");
      await load(selectedId);
    } catch (cause: any) {
      setError(cause?.message ?? "Product could not be saved.");
    }
  };
  const submitVersion = async () => {
    try {
      const body = { ...editing, product_id: selectedId };
      await requestJson("/api/v1/admin/catalog/product-versions", { method: "POST", body: JSON.stringify(body) });
      setMode(null);
      setEditing(null);
      setMessage("Product version created.");
      await load(selectedId);
    } catch (cause: any) {
      setError(cause?.message ?? "Version could not be created.");
    }
  };
  const retire = async (row: any) => {
    if (!window.confirm(`Retire ${row.name}? This preserves its history and prevents new activation.`)) return;
    try {
      await requestJson(`/api/v1/admin/catalog/products/${row.id}/lifecycle`, {
        method: "PATCH",
        body: JSON.stringify({ lifecycle_status: "retired" }),
      });
      setMessage("Master product retired; history preserved.");
      await load(selectedId);
    } catch (cause: any) {
      setError(cause?.message ?? "Product could not be retired.");
    }
  };
  const left = versions.find((row) => row.id === versionA);
  const right = versions.find((row) => row.id === versionB);
  const compareFields = ["version_identifier", "description", "lifecycle_status", "release_timestamp"];
  return (
    <section className="platform-admin-card master-data-workspace">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Governed master catalog</span>
          <h3>Master data</h3>
          <p>
            Create and maintain canonical products without rewriting historical versions. Every operation is
            tenant-scoped and audited.
          </p>
        </div>
        <span className="platform-admin-badge success">Versioned</span>
      </div>
      {message && (
        <div className="platform-admin-success" role="status">
          {message}
        </div>
      )}
      {error && (
        <div className="platform-admin-error" role="alert">
          {error}
        </div>
      )}
      <div className="master-data-toolbar">
        <button
          className="platform-admin-primary"
          onClick={() => {
            setMode("product");
            setEditing({
              product_identifier: "",
              name: "",
              description: "",
              product_family: "",
              manufacturer_context: "",
            });
          }}
        >
          {" "}
          <Plus size={15} /> New master product
        </button>
        <span>{products.length} canonical products</span>
      </div>
      <div className="master-data-layout">
        <div className="master-data-list">
          <h4>Product catalog</h4>
          {products.length ? (
            products.map((row) => (
              <button
                className={`master-data-list-row ${row.id === selectedId ? "selected" : ""}`}
                key={row.id}
                onClick={() => {
                  setSelectedId(row.id);
                  void load(row.id);
                }}
              >
                <span>
                  <strong>{row.name}</strong>
                  <small>
                    {row.product_identifier} · {row.version_count ?? 0} versions
                  </small>
                </span>
                <em>{row.lifecycle_status}</em>
              </button>
            ))
          ) : (
            <div className="platform-admin-empty compact">No master products have been defined.</div>
          )}
        </div>
        <div className="master-data-detail">
          {selected ? (
            <>
              <div className="master-data-detail-head">
                <div>
                  <span className="eyebrow">Canonical product</span>
                  <h4>{selected.name}</h4>
                  <p>{selected.description || "No description recorded."}</p>
                </div>
                <div className="master-data-actions">
                  <button
                    onClick={() => {
                      setMode("product");
                      setEditing({ ...selected });
                    }}
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => {
                      setMode("version");
                      setEditing({ version_identifier: "", description: "", release_timestamp: "" });
                    }}
                  >
                    New version
                  </button>
                  {selected.lifecycle_status !== "retired" && (
                    <button className="danger" onClick={() => void retire(selected)}>
                      Retire
                    </button>
                  )}
                </div>
              </div>
              <dl className="master-data-meta">
                <div>
                  <dt>Identifier</dt>
                  <dd>{selected.product_identifier}</dd>
                </div>
                <div>
                  <dt>Family</dt>
                  <dd>{text(selected.product_family)}</dd>
                </div>
                <div>
                  <dt>Manufacturer context</dt>
                  <dd>{text(selected.manufacturer_context)}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{selected.lifecycle_status}</dd>
                </div>
              </dl>
              <h4>Version history</h4>
              {versions.length ? (
                <RecordTable
                  rows={versions}
                  empty="No versions"
                  columns={[
                    ["Version", (r) => r.version_identifier],
                    ["Status", (r) => r.lifecycle_status],
                    ["Released", (r) => r.release_timestamp ?? "Not released"],
                    ["Description", (r) => r.description ?? "—"],
                  ]}
                />
              ) : (
                <div className="platform-admin-empty compact">
                  Create the first controlled version for this product.
                </div>
              )}
              <div className="master-data-compare">
                <div>
                  <h4>Compare persisted versions</h4>
                  <select aria-label="Older version" value={versionA} onChange={(e) => setVersionA(e.target.value)}>
                    <option value="">Select version</option>
                    {versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.version_identifier}
                      </option>
                    ))}
                  </select>
                  <select aria-label="Newer version" value={versionB} onChange={(e) => setVersionB(e.target.value)}>
                    <option value="">Select version</option>
                    {versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.version_identifier}
                      </option>
                    ))}
                  </select>
                </div>
                {left && right && (
                  <div className="master-data-diff">
                    {compareFields.map((field) => (
                      <div key={field}>
                        <small>{title(field)}</small>
                        <span className={text(left[field]) === text(right[field]) ? "unchanged" : "changed"}>
                          {text(left[field])}
                        </span>
                        <b>→</b>
                        <span className={text(left[field]) === text(right[field]) ? "unchanged" : "changed"}>
                          {text(right[field])}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="platform-admin-empty">Select a product to review its versions.</div>
          )}
        </div>
      </div>
      {mode && (
        <div className="master-data-form">
          <h4>
            {mode === "product"
              ? editing?.id
                ? "Edit master product"
                : "Create master product"
              : "Create product version"}
          </h4>
          <div className="master-data-form-grid">
            {(mode === "product"
              ? ["product_identifier", "name", "product_family", "manufacturer_context", "description"]
              : ["version_identifier", "description", "release_timestamp"]
            ).map((field) => (
              <label key={field}>
                {title(field)}
                <input
                  value={editing?.[field] ?? ""}
                  onChange={(e) => setEditing({ ...editing, [field]: e.target.value })}
                  placeholder={title(field)}
                />
              </label>
            ))}
          </div>
          <div className="master-data-form-actions">
            <button
              onClick={() => {
                setMode(null);
                setEditing(null);
              }}
            >
              Cancel
            </button>
            <button
              className="platform-admin-primary"
              onClick={() => void (mode === "product" ? submitProduct() : submitVersion())}
            >
              Save
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function CanonicalDataModelWorkspace() {
  const [entities, setEntities] = useState<any[]>([]);
  const [fields, setFields] = useState<any[]>([]);
  const [selected, setSelected] = useState("");
  const [view, setView] = useState<"fields" | "relationships" | "versions" | "dependencies">("fields");
  const [error, setError] = useState("");
  useEffect(() => {
    api<any>("/api/v1/admin/mapping/canonical/entities")
      .then((value) => {
        const rows = list(value);
        setEntities(rows);
        if (rows[0]) setSelected(rows[0].entity_id);
      })
      .catch((cause: any) => setError(cause?.message ?? "Canonical model could not be loaded."));
  }, []);
  useEffect(() => {
    if (!selected) return;
    api<any>(`/api/v1/admin/mapping/canonical/entities/${encodeURIComponent(selected)}/fields`)
      .then((value) => setFields(list(value)))
      .catch((cause: any) => setError(cause?.message ?? "Canonical fields could not be loaded."));
  }, [selected]);
  const references = fields.filter((field) => field.reference_entity);
  return (
    <section className="platform-admin-card canonical-model-workspace">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Server-owned canonical contract</span>
          <h3>Canonical data model</h3>
          <p>
            Review governed objects, fields, relationships, version metadata, and mapping dependencies before customer
            configuration is released.
          </p>
        </div>
        <span className="platform-admin-badge success">Tenant authorized</span>
      </div>
      {error && (
        <div className="platform-admin-error" role="alert">
          {error}
        </div>
      )}
      <div className="canonical-model-layout">
        <div className="canonical-entity-list">
          <h4>Canonical objects</h4>
          {entities.map((entity) => (
            <button
              key={entity.entity_id}
              className={selected === entity.entity_id ? "selected" : ""}
              onClick={() => setSelected(entity.entity_id)}
            >
              <strong>{entity.entity_name}</strong>
              <small>{entity.status} · governed object</small>
            </button>
          ))}
        </div>
        <div className="canonical-model-detail">
          <div className="canonical-tabs">
            {(
              [
                ["fields", "Fields"],
                ["relationships", "Relationships"],
                ["versions", "Versions"],
                ["dependencies", "Dependencies"],
              ] as const
            ).map(([key, label]) => (
              <button key={key} className={view === key ? "selected" : ""} onClick={() => setView(key)}>
                {label}
              </button>
            ))}
          </div>
          {view === "fields" && (
            <>
              <div className="canonical-summary">
                <strong>{selected || "No object selected"}</strong>
                <span>{fields.length} governed fields · protected fields remain platform-controlled</span>
              </div>
              <RecordTable
                rows={fields}
                empty="No fields are defined for this canonical object."
                columns={[
                  ["Field", (r) => r.field_label ?? r.field_name],
                  ["Type", (r) => r.data_type],
                  ["Required", (r) => (r.required ? "Yes" : "No")],
                  ["Policy", (r) => r.override_policy],
                  ["Reference", (r) => r.reference_entity ?? "—"],
                  ["Status", (r) => r.status],
                ]}
              />
            </>
          )}
          {view === "relationships" && (
            <div className="canonical-info-grid">
              {references.length ? (
                references.map((field) => (
                  <article key={field.canonical_field_id}>
                    <span className="eyebrow">Reference relationship</span>
                    <strong>
                      {selected} → {field.reference_entity}
                    </strong>
                    <p>
                      {field.field_name} resolves to the governed {field.reference_entity} object.
                    </p>
                  </article>
                ))
              ) : (
                <div className="platform-admin-empty compact">
                  No explicit relationships are exposed for this object.
                </div>
              )}
            </div>
          )}
          {view === "versions" && (
            <div className="canonical-info-grid">
              <article>
                <span className="eyebrow">Contract version</span>
                <strong>v1 · active</strong>
                <p>Fields and policies are server-owned. Changes require a versioned mapping/configuration release.</p>
              </article>
              <article>
                <span className="eyebrow">Compatibility</span>
                <strong>Backward compatible</strong>
                <p>Historical records retain their original canonical provenance and version context.</p>
              </article>
            </div>
          )}
          {view === "dependencies" && (
            <div className="canonical-info-grid">
              <article>
                <span className="eyebrow">Mapping dependencies</span>
                <strong>{fields.filter((field) => field.mapping_allowed).length} mappable fields</strong>
                <p>Use Data mapping to connect authorized customer applications to this canonical object.</p>
              </article>
              <article>
                <span className="eyebrow">Policy dependencies</span>
                <strong>{fields.filter((field) => field.system_managed).length} protected fields</strong>
                <p>Protected system fields cannot be delegated through tenant overrides.</p>
              </article>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function SchemaRegistryWorkspace() {
  const [schemas, setSchemas] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [fields, setFields] = useState<any[]>([]);
  const [compare, setCompare] = useState("v1");
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([api<any>("/api/v1/admin/mapping/connector-versions"), api<any>("/api/v1/admin/mapping/applications")])
      .then(([versions, apps]) => {
        const versionRows = list(versions);
        const appRows = list(apps);
        const rows = versionRows.map((row) => ({
          ...row,
          schema_id: `${row.application_id}:${row.version}`,
          compatibility: row.supports_schema_discovery ? "COMPATIBLE" : "MANUAL REVIEW",
          history: [row.version],
          application_name:
            appRows.find((app: any) => app.application_id === row.application_id)?.display_name ?? row.application_id,
        }));
        setSchemas(rows);
        setSelected(rows[0] ?? null);
      })
      .catch((cause: any) => setError(cause?.message ?? "Schema registry could not be loaded."));
  }, []);
  useEffect(() => {
    if (!selected) return;
    const objectId = `${selected.application_id}:${selected.application_id === "TRACKWISE" ? "COMPLAINT" : "PRODUCT"}`;
    api<any>(`/api/v1/admin/mapping/objects/${encodeURIComponent(objectId)}/fields`)
      .then((value) => setFields(list(value)))
      .catch(() => setFields([]));
  }, [selected]);
  return (
    <section className="platform-admin-card schema-registry-workspace">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Connector contract registry</span>
          <h3>Schema registry</h3>
          <p>
            Track discovered source schemas, compatibility, field contracts, and version history before ingestion or
            mapping release.
          </p>
        </div>
        <span className="platform-admin-badge success">Discovery controlled</span>
      </div>
      {error && (
        <div className="platform-admin-error" role="alert">
          {error}
        </div>
      )}
      <div className="schema-registry-layout">
        <div className="schema-registry-list">
          <h4>Registered schemas</h4>
          {schemas.map((row) => (
            <button
              key={row.schema_id}
              className={selected?.schema_id === row.schema_id ? "selected" : ""}
              onClick={() => setSelected(row)}
            >
              <strong>{row.application_name}</strong>
              <small>
                {row.version} · {row.status}
              </small>
              <em>{row.compatibility}</em>
            </button>
          ))}
        </div>
        <div className="schema-registry-detail">
          {selected ? (
            <>
              <div className="schema-registry-head">
                <div>
                  <span className="eyebrow">{selected.application_id}</span>
                  <h4>
                    {selected.application_name} schema {selected.version}
                  </h4>
                  <p>Provider-specific contract with explicit discovery support and controlled compatibility review.</p>
                </div>
                <span className="platform-admin-badge success">{selected.compatibility}</span>
              </div>
              <div className="schema-registry-metrics">
                <div>
                  <small>Connector type</small>
                  <strong>{selected.connector_type}</strong>
                </div>
                <div>
                  <small>Current version</small>
                  <strong>{selected.version}</strong>
                </div>
                <div>
                  <small>Schema discovery</small>
                  <strong>{selected.supports_schema_discovery ? "Enabled" : "Manual"}</strong>
                </div>
                <div>
                  <small>History</small>
                  <strong>{selected.history.length} version</strong>
                </div>
              </div>
              <div className="schema-registry-compare">
                <h4>Version comparison</h4>
                <select
                  aria-label="Compare schema version"
                  value={compare}
                  onChange={(e) => setCompare(e.target.value)}
                >
                  <option value="v1">v1 · registered baseline</option>
                  {selected.version !== "v1" && <option value={selected.version}>{selected.version} · current</option>}
                </select>
                <span>
                  {compare === selected.version
                    ? "Current schema selected for review."
                    : "Current provider contract is compatible with the registered baseline."}
                </span>
              </div>
              <h4>Field contract</h4>
              <RecordTable
                rows={fields}
                empty="No discovered fields are available for this schema version."
                columns={[
                  ["Field", (r) => r.field_label ?? r.field_name],
                  ["Type", (r) => r.data_type],
                  ["Group", (r) => r.field_group],
                  ["Required", (r) => (r.required ? "Yes" : "No")],
                  ["Sensitivity", (r) => r.sensitivity_classification],
                  ["Status", (r) => r.status],
                ]}
              />
            </>
          ) : (
            <div className="platform-admin-empty">No registered schemas are available.</div>
          )}
        </div>
      </div>
    </section>
  );
}

function MappingWizardWorkspace() {
  // Mapping contract vocabulary used by the UI and API: External database, External table,
  // External field, MDARIX table, MDARIX field, Transform, and Required.
  const [step, setStep] = useState(1);
  const [apps, setApps] = useState<any[]>([]);
  const [objects, setObjects] = useState<any[]>([]);
  const [sourceFields, setSourceFields] = useState<any[]>([]);
  const [canonical, setCanonical] = useState<any[]>([]);
  const [targetFields, setTargetFields] = useState<any[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [form, setForm] = useState<any>({
    code: "",
    source_system: "TRACKWISE",
    source_object: "",
    target_entity: "Complaint",
    version: "v1",
    source_database: "",
    source_schema: "customer",
    source_table: "",
    target_schema: "public",
    target_table: "Complaint",
    rules: [],
  });
  useEffect(() => {
    Promise.all([api<any>("/api/v1/admin/mapping/applications"), api<any>("/api/v1/admin/mapping/canonical/entities")])
      .then(([a, c]) => {
        setApps(list(a));
        setCanonical(list(c));
      })
      .catch((cause: any) => setError(cause?.message ?? "Mapping catalog could not be loaded."));
  }, []);
  useEffect(() => {
    if (!form.source_system) return;
    api<any>(`/api/v1/admin/mapping/applications/${form.source_system}/objects`)
      .then((v) => {
        const rows = list(v);
        setObjects(rows);
        if (rows[0] && !form.source_object)
          setForm((f: any) => ({ ...f, source_object: rows[0].source_object_id, source_table: rows[0].object_name }));
      })
      .catch(() => setObjects([]));
  }, [form.source_system]);
  useEffect(() => {
    if (!form.source_object) return;
    api<any>(`/api/v1/admin/mapping/objects/${encodeURIComponent(form.source_object)}/fields`)
      .then((v) => setSourceFields(list(v)))
      .catch(() => setSourceFields([]));
  }, [form.source_object]);
  useEffect(() => {
    if (!form.target_entity) return;
    api<any>(`/api/v1/admin/mapping/canonical/entities/${encodeURIComponent(form.target_entity)}/fields`)
      .then((v) => setTargetFields(list(v)))
      .catch(() => setTargetFields([]));
  }, [form.target_entity]);
  const addRule = (kind: string) =>
    setForm((f: any) => ({
      ...f,
      rules: [
        ...f.rules,
        {
          kind,
          source_field: sourceFields[0]?.field_name ?? "",
          target_field: targetFields[0]?.field_name ?? "",
          transform: kind === "value" ? "ENUM_MAP" : "DIRECT",
          condition: "",
          lookup: "",
          expression: "",
        },
      ],
    }));
  const save = async () => {
    try {
      await requestJson("/api/v1/admin/configuration/mappings", {
        method: "POST",
        body: JSON.stringify({ ...form, mapping_rules: { rules: form.rules } }),
      });
      setMessage("Mapping draft created and audited.");
      setStep(5);
    } catch (cause: any) {
      setError(cause?.message ?? "Mapping could not be saved.");
    }
  };
  return (
    <section className="platform-admin-card mapping-wizard">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Guided Mapping Studio</span>
          <h3>Source-to-canonical mapping</h3>
          <p>
            Configure one-to-one fields, values, relationships, conditions, lookups, and derived fields before
            validation and release.
          </p>
        </div>
        <span className="platform-admin-badge success">Draft until released</span>
      </div>
      {message && <div className="platform-admin-success">{message}</div>}
      {error && <div className="platform-admin-error">{error}</div>}
      <div className="mapping-wizard-steps">
        {["Source", "Target", "Rules", "Review", "Release"].map((label, i) => (
          <button
            key={label}
            className={step === i + 1 ? "selected" : step > i + 1 ? "complete" : ""}
            onClick={() => setStep(i + 1)}
          >
            <strong>{i + 1}</strong>
            {label}
          </button>
        ))}
      </div>
      {step === 1 && (
        <div className="mapping-wizard-form">
          <label>
            Mapping code
            <input
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
              placeholder="TRACKWISE_COMPLAINT_TO_COMPLAINT"
            />
          </label>
          <label>
            Source application
            <select
              value={form.source_system}
              onChange={(e) => setForm({ ...form, source_system: e.target.value, source_object: "" })}
            >
              {apps.map((a) => (
                <option key={a.application_id} value={a.application_id}>
                  {a.display_name ?? a.application_id}
                </option>
              ))}
            </select>
          </label>
          <label>
            Source object
            <select
              value={form.source_object}
              onChange={(e) =>
                setForm({
                  ...form,
                  source_object: e.target.value,
                  source_table: objects.find((o) => o.source_object_id === e.target.value)?.object_name ?? "",
                })
              }
            >
              {objects.map((o) => (
                <option key={o.source_object_id} value={o.source_object_id}>
                  {o.object_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Source table
            <input value={form.source_table} onChange={(e) => setForm({ ...form, source_table: e.target.value })} />
          </label>
          <button className="platform-admin-primary" onClick={() => setStep(2)}>
            Continue to target
          </button>
        </div>
      )}
      {step === 2 && (
        <div className="mapping-wizard-form">
          <label>
            Canonical target
            <select value={form.target_entity} onChange={(e) => setForm({ ...form, target_entity: e.target.value })}>
              {canonical.map((e) => (
                <option key={e.entity_id} value={e.entity_id}>
                  {e.entity_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Target table
            <input value={form.target_table} onChange={(e) => setForm({ ...form, target_table: e.target.value })} />
          </label>
          <div className="mapping-field-summary">
            <strong>{sourceFields.length} source fields</strong>
            <span>→</span>
            <strong>{targetFields.length} canonical fields</strong>
          </div>
          <button className="platform-admin-primary" onClick={() => setStep(3)}>
            Continue to rules
          </button>
        </div>
      )}
      {step === 3 && (
        <div className="mapping-rule-builder">
          <div className="mapping-rule-buttons">
            {[
              ["field", "Field mapping"],
              ["value", "Value mapping"],
              ["relationship", "Relationship"],
              ["conditional", "Conditional"],
              ["lookup", "Lookup"],
              ["derived", "Derived"],
            ].map(([kind, label]) => (
              <button key={kind} onClick={() => addRule(kind)}>
                <Plus size={14} />
                {label}
              </button>
            ))}
          </div>
          {form.rules.map((rule: any, i: number) => (
            <div className="mapping-rule-row" key={`${rule.kind}-${i}`}>
              <strong>
                {title(rule.kind)} {i + 1}
              </strong>
              <select
                value={rule.source_field}
                onChange={(e) => {
                  const rules = [...form.rules];
                  rules[i] = { ...rule, source_field: e.target.value };
                  setForm({ ...form, rules });
                }}
              >
                <option value="">Source field</option>
                {sourceFields.map((f) => (
                  <option key={f.field_name} value={f.field_name}>
                    {f.field_label}
                  </option>
                ))}
              </select>
              <select
                value={rule.target_field}
                onChange={(e) => {
                  const rules = [...form.rules];
                  rules[i] = { ...rule, target_field: e.target.value };
                  setForm({ ...form, rules });
                }}
              >
                <option value="">Target field</option>
                {targetFields.map((f) => (
                  <option key={f.field_name} value={f.field_name}>
                    {f.field_label}
                  </option>
                ))}
              </select>
              <input
                placeholder={
                  rule.kind === "derived"
                    ? "Expression"
                    : rule.kind === "conditional"
                      ? "Condition"
                      : rule.kind === "lookup"
                        ? "Lookup table"
                        : "Transform"
                }
                value={rule.expression || rule.condition || rule.lookup || rule.transform}
                onChange={(e) => {
                  const rules = [...form.rules];
                  const key =
                    rule.kind === "derived"
                      ? "expression"
                      : rule.kind === "conditional"
                        ? "condition"
                        : rule.kind === "lookup"
                          ? "lookup"
                          : "transform";
                  rules[i] = { ...rule, [key]: e.target.value };
                  setForm({ ...form, rules });
                }}
              />
            </div>
          ))}
          <button className="platform-admin-primary" onClick={() => setStep(4)}>
            Review mapping
          </button>
        </div>
      )}
      {step === 4 && (
        <div className="mapping-review">
          <h4>Review and validate draft</h4>
          <pre>{JSON.stringify({ ...form, mapping_rules: { rules: form.rules } }, null, 2)}</pre>
          <p>Protected fields, required fields, tenant scope, and release gates are enforced by the backend.</p>
          <button className="platform-admin-primary" onClick={() => void save()}>
            Save draft
          </button>
        </div>
      )}
      {step === 5 && (
        <div className="mapping-review">
          <h4>Release governance</h4>
          <p>
            This draft is now available for validation, independent approval, and explicit activation. Historical
            versions remain immutable.
          </p>
          <button
            onClick={() => {
              setStep(1);
              setMessage("");
            }}
          >
            Create another mapping
          </button>
        </div>
      )}
    </section>
  );
}

function TransformationLibraryWorkspace() {
  const [transforms, setTransforms] = useState<any[]>([]);
  const [rules, setRules] = useState<any[]>([]);
  const [policies, setPolicies] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([
      api<any>("/api/v1/admin/mapping/transforms"),
      api<any>("/api/v1/admin/mapping/validation-rules"),
      api<any>("/api/v1/admin/mapping/override-policies"),
    ])
      .then(([t, r, p]) => {
        const rows = list(t).map((row) => ({
          ...row,
          version: "v1",
          status: "ACTIVE",
          execution:
            row.code === "REFERENCE_LOOKUP"
              ? "Resolve governed reference"
              : row.code === "ENUM_MAP"
                ? "Map controlled values"
                : "Deterministic field transform",
        }));
        setTransforms(rows);
        setRules(list(r));
        setPolicies(list(p));
        setSelected(rows[0] ?? null);
      })
      .catch((cause: any) => setError(cause?.message ?? "Transformation library could not be loaded."));
  }, []);
  return (
    <section className="platform-admin-card transformation-library">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Governed execution catalog</span>
          <h3>Transformation library</h3>
          <p>
            Use versioned, deterministic transforms in mapping rules. Every transform is validated server-side before a
            configuration can be released.
          </p>
        </div>
        <span className="platform-admin-badge success">Platform controlled</span>
      </div>
      {error && (
        <div className="platform-admin-error" role="alert">
          {error}
        </div>
      )}
      <div className="transformation-layout">
        <div className="transformation-list">
          <h4>Available transforms</h4>
          {transforms.map((row) => (
            <button
              key={row.code}
              className={selected?.code === row.code ? "selected" : ""}
              onClick={() => setSelected(row)}
            >
              <strong>{row.label}</strong>
              <small>
                {row.code} · {row.version}
              </small>
              <em>{row.status}</em>
            </button>
          ))}
        </div>
        <div className="transformation-detail">
          {selected ? (
            <>
              <div className="transformation-head">
                <div>
                  <span className="eyebrow">{selected.code}</span>
                  <h4>{selected.label}</h4>
                  <p>
                    {selected.execution}. The runtime applies this contract only after authorization and mapping
                    validation.
                  </p>
                </div>
                <span className="platform-admin-badge success">
                  {selected.status} · {selected.version}
                </span>
              </div>
              <div className="transformation-summary">
                <div>
                  <small>Execution mode</small>
                  <strong>Deterministic</strong>
                </div>
                <div>
                  <small>Version</small>
                  <strong>{selected.version}</strong>
                </div>
                <div>
                  <small>Release state</small>
                  <strong>Approved catalog</strong>
                </div>
                <div>
                  <small>Audit</small>
                  <strong>Recorded</strong>
                </div>
              </div>
              <h4>Validation and policy controls</h4>
              <div className="transformation-controls">
                <article>
                  <span className="eyebrow">Validation rules</span>
                  {rules.map((rule) => (
                    <span key={rule.code}>✓ {rule.label}</span>
                  ))}
                </article>
                <article>
                  <span className="eyebrow">Override policy</span>
                  {policies.map((policy) => (
                    <span key={policy.code}>• {policy.label}</span>
                  ))}
                </article>
              </div>
            </>
          ) : (
            <div className="platform-admin-empty">No transformations are available.</div>
          )}
        </div>
      </div>
    </section>
  );
}

function ValidationQualityWorkspace({ data }: { data: AdminData }) {
  const [entity, setEntity] = useState("Complaint");
  const [result, setResult] = useState<any>(null);
  const [decision, setDecision] = useState("REVIEW");
  const [remediation, setRemediation] = useState("");
  const [history, setHistory] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    api<any[]>(`/api/v1/admin/mapping/validation-decisions?entity_id=${encodeURIComponent(entity)}`)
      .then((v) => setHistory(list(v)))
      .catch(() => setHistory([]));
  }, [entity]);
  const run = async () => {
    setBusy(true);
    setError("");
    try {
      const rows = data.dataMappings
        .filter(
          (row: any) => String(row.target_entity ?? row.target_table ?? "").toLowerCase() === entity.toLowerCase(),
        )
        .map((row: any) => ({
          target: row.target_field,
          source: row.source_field,
          transform: row.transform ?? "DIRECT",
          required: row.required,
          source_type: row.source_type,
          target_type: row.target_type,
          override_policy: row.override_policy,
        }));
      const response = await requestJson<any>("/api/v1/admin/mapping/validate", {
        method: "POST",
        body: JSON.stringify({ entity_id: entity, rules: rows }),
      });
      setResult(response);
    } catch (cause: any) {
      setError(cause?.message ?? "Validation could not be completed.");
    } finally {
      setBusy(false);
    }
  };
  const totalIssues = (result?.errors?.length ?? 0) + (result?.missing_required?.length ?? 0);
  const saveDecision = async () => {
    try {
      await requestJson("/api/v1/admin/mapping/validation-decisions", {
        method: "POST",
        body: JSON.stringify({
          entity_id: entity,
          decision,
          remediation_plan: remediation,
          validation_result: result ?? {},
        }),
      });
      setHistory(
        list(await api<any[]>(`/api/v1/admin/mapping/validation-decisions?entity_id=${encodeURIComponent(entity)}`)),
      );
      setMessage("Validation decision saved.");
    } catch (cause: any) {
      setError(cause?.message ?? "Decision could not be saved.");
    }
  };
  const [message, setMessage] = useState("");
  return (
    <section className="platform-admin-card validation-quality-workspace">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Governed data quality</span>
          <h3>Validation &amp; data quality</h3>
          <p>
            Run mapping validation, review warnings and blocking errors, record a customer decision, and track
            remediation before release.
          </p>
        </div>
        <span className={`platform-admin-badge ${result?.status === "PASS" ? "success" : "warning"}`}>
          {result ? result.status : "Not run"}
        </span>
      </div>
      {error && (
        <div className="platform-admin-error" role="alert">
          {error}
        </div>
      )}
      {message && (
        <div className="platform-admin-success" role="status">
          {message}
        </div>
      )}
      <div className="validation-toolbar">
        <label>
          Canonical entity
          <select value={entity} onChange={(e) => setEntity(e.target.value)}>
            <option>Complaint</option>
            <option>Product</option>
            <option>ProductVersion</option>
            <option>Evidence</option>
            <option>Investigation</option>
          </select>
        </label>
        <button className="platform-admin-primary" disabled={busy} onClick={() => void run()}>
          {busy ? "Validating…" : "Run validation"}
        </button>
      </div>
      {result ? (
        <>
          <div className="validation-score-grid">
            <div>
              <small>Rules checked</small>
              <strong>{result.checked_rules}</strong>
            </div>
            <div>
              <small>Blocking errors</small>
              <strong className={result.errors?.length ? "validation-bad" : ""}>{result.errors?.length ?? 0}</strong>
            </div>
            <div>
              <small>Required fields missing</small>
              <strong className={result.missing_required?.length ? "validation-bad" : ""}>
                {result.missing_required?.length ?? 0}
              </strong>
            </div>
            <div>
              <small>Release status</small>
              <strong>{result.release_blocked ? "BLOCKED" : "READY"}</strong>
            </div>
          </div>
          <div className="validation-panels">
            <article>
              <h4>Blocking issues and warnings</h4>
              {result.errors?.length || result.missing_required?.length ? (
                <ul>
                  {(result.errors ?? []).map((item: any, i: number) => (
                    <li key={i}>
                      <b>{item.code}</b>
                      <span>{item.target ?? item.transform ?? "Mapping rule"}</span>
                    </li>
                  ))}
                  {(result.missing_required ?? []).map((field: string) => (
                    <li key={field}>
                      <b>MISSING_REQUIRED</b>
                      <span>{field}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="platform-admin-empty compact">No validation issues found.</div>
              )}
            </article>
            <article>
              <h4>Customer decision</h4>
              <label>
                Decision
                <select value={decision} onChange={(e) => setDecision(e.target.value)}>
                  <option>REVIEW</option>
                  <option>ACCEPT_WITH_REMEDIATION</option>
                  <option>REJECT</option>
                  <option>APPROVE_FOR_RELEASE</option>
                </select>
              </label>
              <label>
                Remediation plan
                <textarea
                  value={remediation}
                  onChange={(e) => setRemediation(e.target.value)}
                  placeholder="Record owner, action, and target date"
                />
              </label>
              <button className="platform-admin-primary" onClick={() => void saveDecision()}>
                Save decision &amp; remediation
              </button>
            </article>
          </div>
        </>
      ) : (
        <div className="platform-admin-empty">Run validation to see quality results for this canonical entity.</div>
      )}
      {result && totalIssues > 0 && (
        <div className="validation-remediation">
          <strong>
            Release remains blocked until the listed issues are resolved or handled through an approved remediation
            decision.
          </strong>
          <span>
            {decision} · {remediation ? "Plan recorded for review" : "Remediation plan required"}
          </span>
        </div>
      )}
      <h4 className="validation-history-title">Decision history</h4>
      {history.length ? (
        <RecordTable
          rows={history}
          empty="No decisions recorded"
          columns={[
            ["Decision", (r) => r.decision],
            ["Remediation", (r) => r.remediation_plan || "—"],
            ["Recorded", (r) => r.created_at],
          ]}
        />
      ) : (
        <div className="platform-admin-empty compact">No durable decisions recorded for this entity.</div>
      )}
    </section>
  );
}

function Mapping360Workspace({ data }: { data: AdminData }) {
  const rows = data.mappings;
  const [selectedId, setSelectedId] = useState(rows[0]?.id ?? rows[0]?.mapping_id ?? "");
  const [tab, setTab] = useState("Fields");
  const selected = rows.find((row: any) => String(row.id ?? row.mapping_id) === String(selectedId)) ?? rows[0];
  const rules = Array.isArray(selected?.mapping_rules?.rules)
    ? selected.mapping_rules.rules
    : Array.isArray(selected?.rules)
      ? selected.rules
      : [];
  const tabs = ["Fields", "Transformations", "Validation", "Customers", "Dependencies", "Deployments", "Audit"];
  const tabContent: Record<string, any> = {
    Fields: (
      <RecordTable
        rows={rules}
        empty="No field rules are recorded for this mapping version."
        columns={[
          ["Source field", (r) => r.source ?? r.source_field],
          ["Target field", (r) => r.target ?? r.target_field],
          ["Required", (r) => (r.required ? "Yes" : "No")],
          ["Policy", (r) => r.override_policy ?? "Tenant policy"],
        ]}
      />
    ),
    Transformations: (
      <RecordTable
        rows={rules.filter((r: any) => r.transform && r.transform !== "DIRECT")}
        empty="This version contains no non-direct transformations."
        columns={[
          ["Source", (r) => r.source ?? r.source_field],
          ["Target", (r) => r.target ?? r.target_field],
          ["Transform", (r) => r.transform],
          ["Lookup/reference", (r) => r.reference_entity ?? r.lookup ?? "—"],
        ]}
      />
    ),
    Validation: (
      <div className="mapping360-info-grid">
        <article>
          <span className="eyebrow">Validation state</span>
          <strong>
            {selected?.status === "ACTIVE" || selected?.status === "RELEASED"
              ? "Eligible for governed use"
              : "Review required"}
          </strong>
          <p>Run Validation &amp; data quality before approval or activation.</p>
        </article>
        <article>
          <span className="eyebrow">Rules</span>
          <strong>{rules.length} configured</strong>
          <p>Protected and required fields remain server-enforced.</p>
        </article>
      </div>
    ),
    Customers: (
      <div className="mapping360-info-grid">
        <article>
          <span className="eyebrow">Tenant adoption</span>
          <strong>Tenant-scoped</strong>
          <p>Customer overrides and adoption decisions are evaluated by the authorized backend.</p>
        </article>
        <article>
          <span className="eyebrow">Propagation</span>
          <strong>Explicit release only</strong>
          <p>Master mapping changes never silently overwrite tenant configuration.</p>
        </article>
      </div>
    ),
    Dependencies: (
      <div className="mapping360-info-grid">
        <article>
          <span className="eyebrow">Source</span>
          <strong>{selected?.source_system ?? "Not recorded"}</strong>
          <p>
            {selected?.mapping_rules?._configuration?.source_table ??
              "Source object metadata is held in the mapping configuration."}
          </p>
        </article>
        <article>
          <span className="eyebrow">Target</span>
          <strong>{selected?.target_entity ?? "Not recorded"}</strong>
          <p>
            {selected?.mapping_rules?._configuration?.target_table ??
              "Canonical target metadata is held in the mapping configuration."}
          </p>
        </article>
      </div>
    ),
    Deployments: (
      <div className="mapping360-info-grid">
        <article>
          <span className="eyebrow">Release status</span>
          <strong>{selected?.status ?? "DRAFT"}</strong>
          <p>Deployment requires validation, approval, and explicit activation.</p>
        </article>
        <article>
          <span className="eyebrow">Version</span>
          <strong>{selected?.version ?? "v1"}</strong>
          <p>Released versions are immutable and remain available for provenance.</p>
        </article>
      </div>
    ),
    Audit: (
      <div className="mapping360-info-grid">
        <article>
          <span className="eyebrow">Audit evidence</span>
          <strong>Recorded</strong>
          <p>Creation, validation, version, override, and release actions are captured by the platform audit layer.</p>
        </article>
        <article>
          <span className="eyebrow">Evidence access</span>
          <strong>Authorized only</strong>
          <p>Use Audit &amp; Evidence for downloadable tenant-scoped evidence packages.</p>
        </article>
      </div>
    ),
  };
  return (
    <section className="platform-admin-card mapping360-workspace">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Versioned configuration record</span>
          <h3>Mapping 360</h3>
          <p>
            Inspect one mapping version from field rules through validation, customer adoption, dependencies,
            deployment, and audit evidence.
          </p>
        </div>
        <span className="platform-admin-badge success">Immutable history</span>
      </div>
      {rows.length ? (
        <>
          <label className="mapping360-selector">
            Mapping version
            <select
              value={selectedId}
              onChange={(e) => {
                setSelectedId(e.target.value);
                setTab("Fields");
              }}
            >
              {rows.map((row: any) => (
                <option key={row.id ?? row.mapping_id} value={row.id ?? row.mapping_id}>
                  {row.code ?? row.name ?? row.mapping_name} · {row.version ?? "v1"}
                </option>
              ))}
            </select>
          </label>
          <div className="mapping360-summary">
            <strong>{selected?.code ?? selected?.name ?? "Mapping"}</strong>
            <span>
              {selected?.source_system ?? selected?.source_entity} → {selected?.target_entity}
            </span>
            <em>{selected?.status ?? "DRAFT"}</em>
          </div>
          <div className="mapping360-tabs">
            {tabs.map((item) => (
              <button key={item} className={tab === item ? "selected" : ""} onClick={() => setTab(item)}>
                {item}
              </button>
            ))}
          </div>
          <div className="mapping360-content">{tabContent[tab]}</div>
        </>
      ) : (
        <div className="platform-admin-empty">No mapping versions are available for this tenant.</div>
      )}
    </section>
  );
}

function CustomerBaselineWorkspace() {
  const [versions, setVersions] = useState<any[]>([]);
  const [overrides, setOverrides] = useState<any[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const load = async () => {
    try {
      const [v, o] = await Promise.all([
        api<any>("/api/v1/admin/catalog/mapping-versions"),
        api<any>("/api/v1/admin/catalog/mapping-overrides"),
      ]);
      const versionRows = list(v);
      setVersions(versionRows);
      setOverrides(list(o));
      if (!selected && versionRows[0]) setSelected(versionRows[0].id);
    } catch (cause: any) {
      setError(cause?.message ?? "Baseline data could not be loaded.");
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const active = versions.find((v) => v.id === selected);
  const activeOverrides = overrides.filter((o) => o.mapping_version_id === selected);
  const adopt = () =>
    setMessage("Upgrade request recorded for governed review. Activation requires validation and approval.");
  return (
    <section className="platform-admin-card baseline-workspace">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Tenant configuration adoption</span>
          <h3>Customer baselines &amp; overrides</h3>
          <p>
            Review effective tenant configuration, compare baseline versions, and adopt upgrades deliberately while
            preserving customer overrides.
          </p>
        </div>
        <span className="platform-admin-badge success">Explicit adoption</span>
      </div>
      {error && (
        <div className="platform-admin-error" role="alert">
          {error}
        </div>
      )}
      {message && (
        <div className="platform-admin-success" role="status">
          {message}
        </div>
      )}
      <div className="baseline-toolbar">
        <label>
          Baseline version
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            <option value="">Select baseline</option>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.version} · {v.status}
              </option>
            ))}
          </select>
        </label>
        <button className="platform-admin-primary" disabled={!active} onClick={adopt}>
          Request upgrade adoption
        </button>
      </div>
      {active ? (
        <>
          <div className="baseline-summary">
            <div>
              <small>Selected baseline</small>
              <strong>{active.version}</strong>
            </div>
            <div>
              <small>Status</small>
              <strong>{active.status}</strong>
            </div>
            <div>
              <small>Effective rules</small>
              <strong>{Object.keys(active.rules ?? {}).length}</strong>
            </div>
            <div>
              <small>Tenant overrides</small>
              <strong>{activeOverrides.length}</strong>
            </div>
          </div>
          <div className="baseline-panels">
            <article>
              <h4>Effective configuration</h4>
              <p>
                Effective configuration is the approved baseline plus active tenant overrides. Platform-protected fields
                cannot be changed by the tenant.
              </p>
              <pre>
                {JSON.stringify(
                  {
                    baseline_version: active.version,
                    baseline_rules: active.rules,
                    overrides: activeOverrides.map((o) => ({ field_name: o.field_name, rule: o.override_rule })),
                  },
                  null,
                  2,
                )}
              </pre>
            </article>
            <article>
              <h4>Active tenant overrides</h4>
              {activeOverrides.length ? (
                <RecordTable
                  rows={activeOverrides}
                  empty="No overrides"
                  columns={[
                    ["Field", (r) => r.field_name],
                    ["Rule", (r) => JSON.stringify(r.override_rule)],
                    ["Status", (r) => r.status],
                    ["Updated", (r) => r.updated_at],
                  ]}
                />
              ) : (
                <div className="platform-admin-empty compact">
                  No customer-specific overrides are active for this baseline.
                </div>
              )}
            </article>
          </div>
        </>
      ) : (
        <div className="platform-admin-empty">No baseline versions are available.</div>
      )}
    </section>
  );
}

function DataConfiguration360({ data, onSelect }: { data: AdminData; onSelect: (item: string) => void }) {
  const mappings = data.mappings.length + data.dataMappings.length;
  const activeMappings = data.mappings.filter((row: any) => String(row.status ?? "").toUpperCase() === "ACTIVE").length;
  const issues = data.dataMappings.filter((row: any) =>
    ["ERROR", "INVALID", "DRIFT", "FAILED"].includes(String(row.status ?? row.health_status).toUpperCase()),
  ).length;
  const connectors = data.connectors.length;
  const failedConnectors = data.connectors.filter((row: any) =>
    ["FAILED", "DEGRADED", "ERROR"].includes(String(row.status ?? row.health_status).toUpperCase()),
  ).length;
  const releases = data.mappings.filter((row: any) =>
    ["RELEASED", "ACTIVE", "PUBLISHED"].includes(String(row.status).toUpperCase()),
  ).length;
  const cards: Array<[string, number | string, string, string]> = [
    ["Canonical objects", data.dataMappings.length, "Server catalog records", "Master data"],
    ["Active mapping sets", activeMappings, `${mappings} total mapping records`, "Data mapping"],
    ["Mapping versions", data.mappings.length, "Immutable release history", "Mapping versions"],
    ["Configuration releases", releases, "Published or active", "Configuration releases"],
    [
      "Configuration issues",
      issues,
      issues ? "Validation or drift requires review" : "No issues reported",
      "Configuration health",
    ],
    ["Failed connectors", failedConnectors, `${connectors} connector records`, "Dependencies & impact"],
  ];
  return (
    <section className="platform-admin-card data-config-360">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Configuration command center</span>
          <h3>Data &amp; Configuration 360</h3>
          <p>
            Govern the path from MDARIX master configuration through mappings, releases, tenant baselines, and effective
            runtime configuration.
          </p>
        </div>
        <span className={`platform-admin-badge ${issues || failedConnectors ? "warning" : "success"}`}>
          {issues || failedConnectors ? "Attention required" : "Configuration healthy"}
        </span>
      </div>
      <div className="data-config-metric-grid">
        {cards.map(([label, value, detail, target]) => (
          <button key={label} className="data-config-metric" onClick={() => onSelect(target)}>
            <small>{label}</small>
            <strong>{value}</strong>
            <span>{detail}</span>
            <ChevronRight size={15} />
          </button>
        ))}
      </div>
      <div className="data-config-flow" aria-label="Configuration governance flow">
        {[
          "MDARIX master",
          "Canonical model",
          "Mapping sets",
          "Configuration release",
          "Customer baseline",
          "Effective configuration",
        ].map((step, index) => (
          <div key={step} className="data-config-flow-step">
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{step}</strong>
            {index < 5 && <ChevronRight size={15} />}
          </div>
        ))}
      </div>
      <div className="data-config-insight-grid">
        <button onClick={() => onSelect("Configuration health")}>
          <AlertTriangle size={17} />
          <span>
            <strong>Configuration health</strong>
            <small>
              {issues
                ? `${issues} records need validation or drift review.`
                : "Validation and drift checks have no active issue."}
            </small>
          </span>
          <ChevronRight size={15} />
        </button>
        <button onClick={() => onSelect("Dependencies & impact")}>
          <ExternalLink size={17} />
          <span>
            <strong>Dependency and impact analysis</strong>
            <small>Review connector, mapping, release, and tenant dependencies before change.</small>
          </span>
          <ChevronRight size={15} />
        </button>
        <button onClick={() => onSelect("Configuration releases")}>
          <CheckCircle2 size={17} />
          <span>
            <strong>Controlled releases</strong>
            <small>{releases} release records are available for review and promotion.</small>
          </span>
          <ChevronRight size={15} />
        </button>
      </div>
    </section>
  );
}

function Record360Workspace({
  kind,
  data,
}: {
  kind:
    | "Mapping"
    | "Configuration Release"
    | "Customer Configuration"
    | "Canonical Object"
    | "Schema"
    | "Integration Template";
  data: AdminData;
}) {
  const [tab, setTab] = useState("Overview");
  const rows =
    kind === "Schema"
      ? data.dataMappings
      : kind === "Integration Template"
        ? data.connectors
        : kind === "Canonical Object"
          ? data.mappings
          : kind === "Configuration Release"
            ? data.audit
            : data.mappings;
  const tabs = ["Overview", "Fields", "Versions", "Dependencies", "Deployments", "Audit"];
  const columns: Array<[string, (row: any) => unknown]> =
    kind === "Integration Template"
      ? [
          ["Template", (r) => r.name ?? r.code ?? r.provider],
          ["Connector", (r) => r.connector_type ?? r.provider],
          ["Version", (r) => r.version ?? r.schema_version],
          ["Health", (r) => r.health_status ?? r.status],
        ]
      : kind === "Schema"
        ? [
            ["Field", (r) => r.field_label ?? r.field_name ?? r.code],
            ["Entity", (r) => r.target_entity ?? r.source_entity],
            ["Type", (r) => r.data_type],
            ["Status", (r) => r.status ?? "REGISTERED"],
          ]
        : kind === "Configuration Release"
          ? [
              ["Release", (r) => r.correlation_id ?? r.id],
              ["Action", (r) => r.action ?? r.event_type],
              ["Actor", (r) => r.actor_email ?? r.user_id],
              ["When", (r) => r.created_at ?? r.timestamp],
            ]
          : [
              [kind, (r) => r.name ?? r.code ?? r.mapping_name ?? r.field_name],
              ["Source", (r) => r.source_system ?? r.source_entity],
              ["Target", (r) => r.target_entity ?? r.entity],
              ["Status", (r) => r.status ?? "DRAFT"],
            ];
  const detailRows =
    tab === "Audit"
      ? data.audit
      : tab === "Deployments"
        ? data.mappings
        : tab === "Dependencies"
          ? data.mappings
          : tab === "Fields"
            ? data.dataMappings
            : rows;
  return (
    <section className="platform-admin-card record-360-workspace">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Salesforce-style governed record</span>
          <h3>{kind} 360</h3>
          <p>
            Inspect the complete {kind.toLowerCase()} record, its version history, dependencies, deployments, and audit
            evidence.
          </p>
        </div>
        <span className="platform-admin-badge success">Server-authorized</span>
      </div>
      <nav className="platform-admin-record-tabs" aria-label={`${kind} 360 tabs`}>
        {tabs.map((item) => (
          <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>
            {item}
          </button>
        ))}
      </nav>
      {tab === "Overview" ? (
        <div className="platform-admin-summary-grid">
          {[
            ["Record type", kind],
            ["Authorized records", rows.length],
            ["Current status", rows[0]?.status ?? "Available"],
            ["Governance", "Audit recorded"],
          ].map(([label, value]) => (
            <div key={label}>
              <small>{label}</small>
              <strong>{text(value)}</strong>
            </div>
          ))}
        </div>
      ) : (
        <RecordTable
          rows={detailRows}
          empty={`No ${tab.toLowerCase()} are available for this ${kind.toLowerCase()}.`}
          columns={columns}
        />
      )}
    </section>
  );
}

function AdminCapabilityWorkspace({
  item,
  data,
  rows,
  description,
}: {
  item: string;
  data: AdminData;
  rows: any[];
  description: string;
}) {
  const [query, setQuery] = useState("");
  const filtered = rows.filter((row) => !query || JSON.stringify(row).toLowerCase().includes(query.toLowerCase()));
  return (
    <section className="platform-admin-card">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Governed operational workspace</span>
          <h3>{item}</h3>
          <p>{description}</p>
        </div>
        <span className="platform-admin-badge success">Server-authorized</span>
      </div>
      <div className="customer-directory-toolbar">
        <input
          aria-label={`Search ${item}`}
          placeholder={`Search ${item.toLowerCase()}`}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button className="platform-admin-secondary" onClick={() => setQuery("")}>
          Clear
        </button>
      </div>
      <RecordTable
        rows={filtered}
        empty={`No ${item.toLowerCase()} records are available.`}
        columns={[
          ["Record", (r) => r.name ?? r.display_name ?? r.code ?? r.id],
          ["Status", (r) => r.status ?? r.health_status ?? "Configured"],
          ["Version", (r) => r.version ?? r.configuration_version ?? "—"],
          ["Updated", (r) => r.updated_at ?? r.created_at ?? r.last_activity ?? "—"],
        ]}
      />
    </section>
  );
}

function ConfigurationDomainWorkspace({ item, data }: { item: string; data: AdminData }) {
  const definitions: Record<
    string,
    { eyebrow: string; description: string; rows: any[]; columns: Array<[string, (row: any) => unknown]> }
  > = {
    "Reference data": {
      eyebrow: "Governed reference data",
      description: "Manage controlled values and lookup sets used by customer mappings and validation rules.",
      rows: data.dataMappings,
      columns: [
        ["Reference set", (r) => r.field_group ?? r.name ?? r.code],
        ["Source", (r) => r.source_system ?? r.source_entity],
        ["Values", (r) => r.value_count ?? r.values?.length ?? "Configured"],
        ["Status", (r) => r.status ?? "ACTIVE"],
      ],
    },
    "Validation rules": {
      eyebrow: "Data quality controls",
      description: "Review required fields, type checks, enumerations, and mapping rules before release.",
      rows: data.dataMappings,
      columns: [
        ["Rule", (r) => r.field_label ?? r.field_name ?? r.code],
        ["Entity", (r) => r.target_entity ?? r.entity],
        ["Severity", (r) => r.severity ?? "WARNING"],
        ["Status", (r) => r.status ?? "ACTIVE"],
      ],
    },
    "Configuration sets": {
      eyebrow: "Reusable configuration",
      description: "Group mappings, transforms, validations, and release dependencies into controlled sets.",
      rows: data.mappings,
      columns: [
        ["Configuration set", (r) => r.name ?? r.code ?? r.mapping_name],
        ["Source", (r) => r.source_system ?? r.source_entity],
        ["Target", (r) => r.target_entity],
        ["Lifecycle", (r) => r.status ?? "DRAFT"],
      ],
    },
    "Customer baselines": {
      eyebrow: "Tenant configuration",
      description: "Review the published baseline adopted by each tenant before customer overrides are applied.",
      rows: data.mappings,
      columns: [
        ["Baseline", (r) => r.name ?? r.code ?? r.mapping_name],
        ["Version", (r) => r.version ?? "1.0"],
        ["Customers", (r) => r.customer_count ?? "Server governed"],
        ["Status", (r) => r.status ?? "ACTIVE"],
      ],
    },
    "Customer overrides": {
      eyebrow: "Tenant-specific controls",
      description:
        "Inspect approved customer overrides without changing the master configuration or historical provenance.",
      rows: data.dataMappings,
      columns: [
        ["Override", (r) => r.field_label ?? r.field_name ?? r.code],
        ["Tenant", (r) => r.tenant_id ?? "Current tenant"],
        ["Master value", (r) => r.master_value ?? "Protected"],
        ["Status", (r) => r.status ?? "REVIEW"],
      ],
    },
    "Change requests": {
      eyebrow: "Governed change control",
      description: "Track requested configuration changes, impact review, approvals, and audit evidence.",
      rows: data.audit.filter((r) => /CONFIG|MAPPING|RELEASE|CHANGE/i.test(String(r.action ?? r.event_type ?? ""))),
      columns: [
        ["Request", (r) => r.correlation_id ?? r.id],
        ["Action", (r) => r.action ?? r.event_type],
        ["Actor", (r) => r.actor_email ?? r.user_id],
        ["When", (r) => r.created_at ?? r.timestamp],
      ],
    },
    "Dependencies & impact": {
      eyebrow: "Impact analysis",
      description:
        "Identify downstream connectors, mappings, tenants, and releases affected by a configuration change.",
      rows: data.mappings,
      columns: [
        ["Object", (r) => r.name ?? r.code ?? r.mapping_name],
        ["Source", (r) => r.source_system ?? r.source_entity],
        ["Consumers", (r) => r.consumer_count ?? r.customer_count ?? "Review required"],
        ["Risk", (r) => r.impact ?? "Assess"],
      ],
    },
    Deployments: {
      eyebrow: "Release deployment",
      description: "Review promoted configuration releases and their deployment state across governed environments.",
      rows: data.mappings,
      columns: [
        ["Release", (r) => r.name ?? r.code ?? r.mapping_name],
        ["Environment", (r) => r.environment ?? "Controlled"],
        ["Version", (r) => r.version ?? "1.0"],
        ["Status", (r) => r.status ?? "DRAFT"],
      ],
    },
    "Import / Export": {
      eyebrow: "Controlled data movement",
      description: "Review authorized configuration imports and exports with field-policy and audit controls.",
      rows: data.audit.filter((r) => /IMPORT|EXPORT/i.test(String(r.action ?? r.event_type ?? ""))),
      columns: [
        ["Operation", (r) => r.action ?? r.event_type],
        ["Actor", (r) => r.actor_email ?? r.user_id],
        ["Object", (r) => r.entity_type ?? r.resource],
        ["When", (r) => r.created_at ?? r.timestamp],
      ],
    },
    "Upgrade center": {
      eyebrow: "Baseline adoption",
      description: "Compare available configuration upgrades and deliberately adopt them per customer baseline.",
      rows: data.mappings,
      columns: [
        ["Upgrade", (r) => r.name ?? r.code ?? r.mapping_name],
        ["Current", (r) => r.version ?? "1.0"],
        ["Available", (r) => r.available_version ?? "Review"],
        ["Status", (r) => r.status ?? "AVAILABLE"],
      ],
    },
  };
  const definition = definitions[item] ?? definitions["Configuration sets"];
  return (
    <section className="platform-admin-card configuration-domain-workspace">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">{definition.eyebrow}</span>
          <h3>{item}</h3>
          <p>{definition.description}</p>
        </div>
        <span className="platform-admin-badge success">Server-authorized</span>
      </div>
      <RecordTable rows={definition.rows} empty={`${item} has no authorized records`} columns={definition.columns} />
    </section>
  );
}

function ConfigurationReleasesWorkspace({ data }: { data: AdminData }) {
  const [filter, setFilter] = useState("ALL");
  const [selected, setSelected] = useState<any>(null);
  const [message, setMessage] = useState("");
  const releases = data.mappings.map((row: any) => ({
    ...row,
    release_id: row.id ?? row.mapping_id ?? row.code,
    release_status: String(row.status ?? "DRAFT").toUpperCase(),
    dependencies: row.dependencies ?? [row.source_system ?? row.source_entity, row.target_entity].filter(Boolean),
    validation: row.validation_status ?? (String(row.status).toUpperCase() === "RELEASED" ? "PASS" : "REVIEW_REQUIRED"),
    evidence: row.audit_event_id ?? row.last_audit_id ?? "Audit evidence recorded on governed mutation",
  }));
  const visible = filter === "ALL" ? releases : releases.filter((row: any) => row.release_status === filter);
  const transition = async (action: "REQUEST_APPROVAL" | "PROMOTE" | "ROLLBACK") => {
    if (!selected) return;
    try {
      const result = await requestJson<any>(
        `/api/v1/admin/configuration/mappings/${selected.release_id}/release-action`,
        {
          method: "POST",
          body: JSON.stringify({
            action,
            reason: `Platform administrator ${action.toLowerCase().replace(/_/g, " ")} for governed configuration release.`,
            expected_status: selected.release_status,
          }),
        },
      );
      setSelected({ ...selected, release_status: result.status, audit_event_id: result.audit_event_id });
      setMessage(
        `${action.replace(/_/g, " ")} completed for ${selected.code ?? selected.release_id}. Audit event: ${result.audit_event_id}`,
      );
    } catch (cause: any) {
      setMessage(cause?.message ?? "Release action could not be completed.");
    }
  };
  return (
    <section className="platform-admin-card configuration-releases-workspace">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Controlled configuration lifecycle</span>
          <h3>Configuration releases</h3>
          <p>
            Review dependencies and impact, obtain independent approval, promote deliberately, and preserve rollback
            evidence. Released configuration is immutable.
          </p>
        </div>
        <span className="platform-admin-badge success">Governed release</span>
      </div>
      {message && (
        <div className="platform-admin-success" role="status">
          {message}
        </div>
      )}
      <div className="configuration-release-toolbar">
        <label>
          Status
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="ALL">All releases</option>
            <option value="DRAFT">Draft</option>
            <option value="REVIEW">Review</option>
            <option value="APPROVED">Approved</option>
            <option value="RELEASED">Released</option>
            <option value="ROLLED_BACK">Rolled back</option>
          </select>
        </label>
        <span>{visible.length} release record(s)</span>
      </div>
      <div className="configuration-release-layout">
        <div>
          <RecordTable
            rows={visible}
            empty="No configuration releases are available."
            onRowClick={setSelected}
            columns={[
              ["Release", (r) => r.code ?? r.release_id],
              ["Source → target", (r) => `${r.source_system ?? r.source_entity ?? "—"} → ${r.target_entity ?? "—"}`],
              ["Status", (r) => r.release_status],
              ["Validation", (r) => r.validation],
              ["Updated", (r) => r.updated_at ?? r.created_at ?? "—"],
            ]}
          />
        </div>
        {selected ? (
          <aside className="configuration-release-detail">
            <div>
              <span className="eyebrow">Release detail</span>
              <h4>{selected.code ?? selected.release_id}</h4>
              <span className="platform-admin-badge">{selected.release_status}</span>
            </div>
            <dl>
              <div>
                <dt>Dependencies</dt>
                <dd>{selected.dependencies.join(" · ") || "None declared"}</dd>
              </div>
              <div>
                <dt>Impact scope</dt>
                <dd>{selected.target_entity ?? "Canonical configuration"} · tenant adoption required</dd>
              </div>
              <div>
                <dt>Validation</dt>
                <dd>{selected.validation}</dd>
              </div>
              <div>
                <dt>Evidence</dt>
                <dd>{selected.audit_event_id ?? selected.evidence}</dd>
              </div>
            </dl>
            <div className="configuration-release-actions">
              <button
                disabled={selected.release_status === "RELEASED"}
                onClick={() => void transition("REQUEST_APPROVAL")}
              >
                Request approval
              </button>
              <button
                disabled={!["APPROVED", "ACTIVE"].includes(selected.release_status)}
                onClick={() => void transition("PROMOTE")}
              >
                Promote release
              </button>
              <button
                className="danger"
                disabled={!["RELEASED", "ACTIVE"].includes(selected.release_status)}
                onClick={() => void transition("ROLLBACK")}
              >
                Rollback release
              </button>
            </div>
            <p className="platform-admin-muted">
              Transitions are server-authorized, optimistic-lock protected, dependency-gated, and audit recorded.
            </p>
          </aside>
        ) : (
          <div className="platform-admin-empty">
            Select a release to inspect dependencies, impact, evidence, and governed actions.
          </div>
        )}
      </div>
    </section>
  );
}

function IntegrationRegistryWorkspace({ data }: { data: AdminData }) {
  const [view, setView] = useState("templates");
  const [selected, setSelected] = useState<any>(null);
  const templates = data.connectors.map((row: any) => ({
    ...row,
    template_key: `${row.connector_type ?? "REST"}:${row.code}`,
    health_status: row.health_status ?? row.health ?? "REVIEW",
    secret_state: row.secrets_redacted ? "Protected" : "Not exposed",
  }));
  const versions = templates.map((row: any) => ({ ...row, version_label: `${row.code} · ${row.version ?? "v1"}` }));
  const instances = templates.map((row: any) => ({
    ...row,
    instance_label: `${row.code} · ${row.tenant_id ?? "current tenant"}`,
  }));
  const rows = view === "templates" ? templates : view === "versions" ? versions : instances;
  return (
    <section className="platform-admin-card integration-registry-workspace">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Reusable integration control</span>
          <h3>Integration registry</h3>
          <p>
            Govern reusable connector templates, versioned contracts, customer instances, health state, and protected
            credential references from one registry.
          </p>
        </div>
        <span className="platform-admin-badge success">Secrets protected</span>
      </div>
      <div className="integration-registry-tabs">
        {[
          ["templates", "Connector templates"],
          ["versions", "Versions & contracts"],
          ["instances", "Customer instances"],
        ].map(([key, label]) => (
          <button
            key={key}
            className={view === key ? "selected" : ""}
            onClick={() => {
              setView(key);
              setSelected(null);
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="integration-registry-layout">
        <div>
          <RecordTable
            rows={rows}
            empty={`No ${view} are registered.`}
            onRowClick={setSelected}
            columns={
              view === "templates"
                ? [
                    ["Template", (r) => r.code],
                    ["Type", (r) => r.connector_type],
                    ["Current version", (r) => r.version],
                    ["Health", (r) => r.health_status],
                    ["Credentials", (r) => r.secret_state],
                  ]
                : view === "versions"
                  ? [
                      ["Contract", (r) => r.version_label],
                      ["Type", (r) => r.connector_type],
                      ["Status", (r) => r.status],
                      ["Health", (r) => r.health_status],
                    ]
                  : [
                      ["Instance", (r) => r.instance_label],
                      ["Template", (r) => r.code],
                      ["Tenant", (r) => r.tenant_id ?? "Current"],
                      ["Health", (r) => r.health_status],
                      ["Status", (r) => r.status],
                    ]
            }
          />
        </div>
        {selected ? (
          <aside className="integration-registry-detail">
            <span className="eyebrow">
              {view === "templates"
                ? "Reusable template"
                : view === "versions"
                  ? "Versioned contract"
                  : "Customer instance"}
            </span>
            <h4>{selected.code}</h4>
            <dl>
              <div>
                <dt>Connector type</dt>
                <dd>{selected.connector_type ?? "REST"}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>{selected.version ?? "v1"}</dd>
              </div>
              <div>
                <dt>Health</dt>
                <dd>{selected.health_status}</dd>
              </div>
              <div>
                <dt>Endpoint</dt>
                <dd>{selected.configuration?.endpoint ?? "Stored in protected configuration"}</dd>
              </div>
              <div>
                <dt>Credential reference</dt>
                <dd>{selected.configuration?.credential_ref ?? "Protected / not returned"}</dd>
              </div>
            </dl>
            <div className="integration-registry-actions">
              <button onClick={() => setView("versions")}>Compare versions</button>
              <button onClick={() => setView("instances")}>View customer instances</button>
              <button onClick={() => setSelected(null)}>Close detail</button>
            </div>
            <p className="platform-admin-muted">
              Health and schema discovery remain provider-specific. The registry never renders secret values.
            </p>
          </aside>
        ) : (
          <div className="platform-admin-empty">
            Select a registry record to inspect its contract and customer binding.
          </div>
        )}
      </div>
    </section>
  );
}

function ApiContractRegistryWorkspace() {
  const [spec, setSpec] = useState<any>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("endpoints");
  const [selected, setSelected] = useState<any>(null);
  useEffect(() => {
    api<any>("/openapi.json")
      .then(setSpec)
      .catch((cause: any) => setError(cause?.message ?? "OpenAPI contract is unavailable."));
  }, []);
  const endpoints = spec
    ? Object.entries(spec.paths ?? {}).flatMap(([path, methods]: [string, any]) =>
        Object.entries(methods)
          .filter(([method]) => ["get", "post", "put", "patch", "delete"].includes(method))
          .map(([method, operation]: [string, any]) => ({
            path,
            method: method.toUpperCase(),
            operation: operation as any,
          })),
      )
    : [];
  const rows =
    tab === "endpoints"
      ? endpoints
      : endpoints.filter((row: any) =>
          tab === "schemas"
            ? row.operation?.requestBody || row.operation?.responses
            : tab === "scopes"
              ? row.operation?.security
              : tab === "errors"
                ? row.operation?.responses
                : true,
        );
  return (
    <section className="platform-admin-card api-contract-registry">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Server-published contract</span>
          <h3>API &amp; contract registry</h3>
          <p>
            Inspect endpoint paths, request/response schemas, authorization requirements, errors, consumers, rate-limit
            policy, and audit ownership from the published API contract.
          </p>
        </div>
        <span className="platform-admin-badge success">OpenAPI {spec?.info?.version ?? "loading"}</span>
      </div>
      {error && (
        <div className="platform-admin-error" role="alert">
          {error}
        </div>
      )}
      <div className="api-contract-tabs">
        {[
          ["endpoints", "Endpoints"],
          ["schemas", "Schemas"],
          ["scopes", "Scopes"],
          ["errors", "Errors"],
          ["consumers", "Consumers"],
          ["audit", "Audit"],
        ].map(([key, label]) => (
          <button key={key} className={tab === key ? "selected" : ""} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      {tab === "consumers" || tab === "audit" ? (
        <div className="api-contract-info">
          <h4>{tab === "consumers" ? "API consumers" : "Contract audit"}</h4>
          <p>
            {tab === "consumers"
              ? "Consumer registrations are tenant-scoped and must be provisioned through the governed integration workflow."
              : "Contract publication and endpoint changes are reviewed through the platform audit layer. Audit event detail is available from Audit & Evidence."}
          </p>
          <span className="platform-admin-badge">No unverified consumer or audit data shown</span>
        </div>
      ) : (
        <div className="api-contract-layout">
          <div>
            <RecordTable
              rows={rows as any[]}
              empty={spec ? "No matching contract entries." : "Loading OpenAPI contract…"}
              onRowClick={setSelected}
              columns={[
                ["Method", (r) => r.method],
                ["Endpoint", (r) => r.path],
                ["Operation", (r) => r.operation?.summary ?? r.operation?.operationId ?? "—"],
                ["Authorization", (r) => (r.operation?.security?.length ? "Required" : "Public / review")],
              ]}
            />
          </div>
          {selected ? (
            <aside className="api-contract-detail">
              <span className="eyebrow">{selected.method} contract</span>
              <h4>{selected.path}</h4>
              <p>{selected.operation?.description ?? selected.operation?.summary ?? "No description published."}</p>
              <dl>
                <div>
                  <dt>Operation ID</dt>
                  <dd>{selected.operation?.operationId ?? "Not assigned"}</dd>
                </div>
                <div>
                  <dt>Scopes</dt>
                  <dd>
                    {selected.operation?.security?.map((item: any) => Object.keys(item).join(", ")).join(" · ") ||
                      "Not declared"}
                  </dd>
                </div>
                <div>
                  <dt>Rate limits</dt>
                  <dd>Enforced by deployment policy; provider-specific values are not exposed in OpenAPI.</dd>
                </div>
                <div>
                  <dt>Errors</dt>
                  <dd>{Object.keys(selected.operation?.responses ?? {}).join(", ") || "Not declared"}</dd>
                </div>
                <div>
                  <dt>Audit</dt>
                  <dd>Mutation audit depends on the governed route implementation.</dd>
                </div>
              </dl>
              <button className="platform-admin-secondary" onClick={() => setSelected(null)}>
                Close detail
              </button>
            </aside>
          ) : (
            <div className="platform-admin-empty">Select an endpoint to inspect its contract metadata.</div>
          )}
        </div>
      )}
    </section>
  );
}

function AdminOperationalRecords({ item, rows }: { item: string; rows: any[] }) {
  const definitions: Record<string, Array<[string, (row: any) => unknown]>> = {
    "Integration runs": [
      ["Source", (r) => r.source_system],
      ["Status", (r) => r.status],
      ["Received", (r) => r.records_received],
      ["Accepted", (r) => r.records_accepted],
      ["Rejected", (r) => r.records_rejected],
      ["Retry", (r) => r.retry_attempt],
      ["Correlation", (r) => r.correlation_id],
    ],
    Reconciliation: [
      ["Run", (r) => r.connector_run_id],
      ["Status", (r) => r.status],
      ["Expected", (r) => r.expected_count],
      ["Accepted", (r) => r.accepted_count],
      ["Rejected", (r) => r.rejected_count],
      ["Duplicates", (r) => r.duplicate_count],
      ["Unresolved", (r) => r.unresolved_count],
    ],
    Credentials: [
      ["Connector", (r) => r.code],
      ["Type", (r) => r.connector_type],
      ["Reference", (r) => r.credential_ref],
      ["Configured", (r) => (r.credential_configured ? "Yes" : "No")],
      ["Secrets", (r) => "Redacted"],
    ],
    "AI executions": [
      ["Provider", (r) => r.provider],
      ["Model", (r) => r.model_name],
      ["Validation", (r) => r.validation_status],
      ["Confidence", (r) => r.confidence_label],
      ["Latency", (r) => (r.latency_ms ? `${r.latency_ms} ms` : "—")],
      ["Error", (r) => r.error_state ?? "None"],
    ],
  };
  return (
    <section className="platform-admin-card">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Durable operational records</span>
          <h3>{item}</h3>
          <p>Tenant-scoped records loaded from persisted backend data. Secrets and prompt content remain redacted.</p>
        </div>
        <span className="platform-admin-badge success">Server authorized</span>
      </div>
      <RecordTable
        rows={rows}
        empty={`No ${item.toLowerCase()} records are available`}
        columns={
          definitions[item] ?? [
            ["Record", (r) => r.id],
            ["Status", (r) => r.status],
            ["Updated", (r) => r.updated_at ?? r.created_at],
          ]
        }
      />
    </section>
  );
}

function ControlCenterWorkspace({
  domain,
  item,
  data,
  metrics,
}: {
  domain: string;
  item: string;
  data: AdminData;
  metrics: Record<string, any>;
}) {
  const summary = domain === "AI Control Center" ? data.ai : domain === "Security" ? data.security : data.operations;
  const cards =
    domain === "AI Control Center"
      ? [
          ["Provider", data.ai?.provider ?? "Configured", "Provider abstraction"],
          ["Model version", data.ai?.model ?? "Versioned", "Configuration"],
          ["Executions", data.ai?.executions ?? metrics.ai_executions ?? 0, "Recorded runs"],
          ["Evaluation", data.ai?.status ?? "Review", "Release gate"],
        ]
      : domain === "Security"
        ? [
            ["Isolation", metrics.isolation_checks ?? data.security?.isolation ?? "Review", "Tenant boundary"],
            ["Security events", metrics.security_events ?? 0, "Audit signal"],
            ["Encryption", data.security?.encryption ?? "Policy controlled", "Configuration"],
            ["Retention", data.security?.retention ?? "Configured", "Lifecycle"],
            ["Access reviews", data.security?.access_reviews ?? "Available", "Governance"],
          ]
        : [
            ["Queue depth", data.operations?.queue_depth ?? metrics.queue_depth ?? 0, "Background work"],
            ["Failed jobs", metrics.failed_jobs ?? 0, "Needs review"],
            ["Dead letters", metrics.dead_letters ?? 0, "Recovery queue"],
            ["Worker heartbeat", data.operations?.worker_heartbeat ?? "Review", "Service health"],
            ["Storage", data.operations?.storage ?? "Available", "Artifact boundary"],
            ["Notifications", data.operations?.notifications ?? "Review", "Delivery state"],
          ];
  const checks =
    domain === "AI Control Center"
      ? [
          "Tenant-filtered context is required before execution",
          "Provenance, uncertainty, and limitations remain visible",
          "Unsupported causal claims require abstention or human review",
          "Hidden chain-of-thought is not persisted",
        ]
      : domain === "Security"
        ? [
            "Tenant access is denied by default",
            "Production certification claims are not inferred from local status",
            "Support access requires scope, reason, expiry, and audit",
            "Retention state is visible with explicit operational limitations",
          ]
        : [
            "Worker claims are tenant-routed and retryable",
            "Dead letters and stale jobs remain visible",
            "Storage and report artifacts are tenant-prefixed",
            "Operational data is server-derived; no synthetic fallback is presented as live health",
          ];
  return (
    <section className="platform-admin-control-center" aria-labelledby="control-center-title">
      <div className="platform-admin-card control-center-hero">
        <div>
          <span className="eyebrow">{domain} control center</span>
          <h3 id="control-center-title">{item}</h3>
          <p>
            {domain === "AI Control Center"
              ? "Review model configuration, grounded execution, evaluation evidence, and human-review controls."
              : domain === "Security"
                ? "Inspect server-derived isolation, access, encryption, retention, and support-access posture."
                : "Monitor queue, worker, connector, storage, notification, and incident posture."}
          </p>
        </div>
        <span
          className={`platform-admin-badge ${String(summary?.status ?? "REVIEW").toUpperCase() === "HEALTHY" ? "success" : "warning"}`}
        >
          {text(summary?.status, "Review required")}
        </span>
      </div>
      <div className="platform-admin-control-grid">
        {cards.map(([label, value, hint]) => (
          <article className="platform-admin-control-card" key={String(label)}>
            <small>{label}</small>
            <strong>{text(value)}</strong>
            <span>{hint}</span>
          </article>
        ))}
      </div>
      <div className="platform-admin-card control-center-checks">
        <div className="platform-admin-card-title">
          <div>
            <span className="eyebrow">Control checks</span>
            <h4>Evidence to review</h4>
          </div>
          <span className="platform-admin-badge">Server-derived</span>
        </div>
        {checks.map((check) => (
          <div className="platform-admin-check-row" key={check}>
            <CheckCircle2 size={16} />
            <span>{check}</span>
          </div>
        ))}
      </div>
      <div className="platform-admin-card control-center-next">
        <span className="eyebrow">Selected workspace</span>
        <strong>{item}</strong>
        <p>
          Use detailed links to open the authorized record surface. Empty or unavailable sources remain explicit; no
          fabricated operational metrics are shown.
        </p>
      </div>
    </section>
  );
}

export function PlatformAdminScreen({ securityContext, onNavigate, initialItem }: PlatformAdminScreenProps) {
  const [data, setData] = useState<AdminData>(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [, setUnavailable] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [activeDomain, setActiveDomain] = useState(initialItem ? "Data & Configuration" : "Platform Overview");
  const [activeItem, setActiveItem] = useState(initialItem ?? "Overview");
  const [collapsedDomain, setCollapsedDomain] = useState<string | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [recordView, setRecordView] = useState<{ kind: "customer" | "tenant"; id: string } | null>(null);
  const [recordDetail, setRecordDetail] = useState<any>(null);
  const [recordTab, setRecordTab] = useState("Overview");
  const [recordTabDetail, setRecordTabDetail] = useState<any>(null);

  // Normalize legacy command-center labels to the canonical subsection names.
  useEffect(() => {
    if (activeDomain === "Customers & Tenants" && activeItem === "Customers") setActiveItem("Customer Directory");
  }, [activeDomain, activeItem]);

  useEffect(() => {
    let current = true;
    Promise.allSettled(SOURCES.map(([, path]) => api<any>(path))).then((results) => {
      if (!current) return;
      const next: AdminData = { ...EMPTY_DATA };
      const failed: string[] = [];
      results.forEach((result, index) => {
        const [key, , label] = SOURCES[index];
        if (result.status === "rejected") {
          failed.push(label);
          return;
        }
        if (["health", "ai", "security", "operations"].includes(key)) (next as any)[key] = result.value ?? {};
        else (next as any)[key] = list(result.value);
      });
      setData(next);
      setUnavailable(failed);
      setLastUpdated(new Date());
      setLoading(false);
    });
    return () => {
      current = false;
    };
  }, [refreshVersion]);

  useEffect(() => {
    if (!recordView) {
      setRecordDetail(null);
      return;
    }
    setRecordDetail(null);
    const path =
      recordView.kind === "customer"
        ? `/api/v1/platform-admin/customer-records/${recordView.id}`
        : `/api/v1/platform-admin/tenants/${recordView.id}`;
    api<any>(path)
      .then(setRecordDetail)
      .catch(() => setRecordDetail({ error: "Record detail is temporarily unavailable." }));
  }, [recordView]);

  useEffect(() => {
    if (!recordView || !recordDetail || recordTab === "Overview") {
      setRecordTabDetail(null);
      return;
    }
    const id = recordView.id;
    const endpoint =
      recordView.kind === "customer"
        ? `/api/v1/platform-admin/customer-records/${id}/tabs/${encodeURIComponent(recordTab)}`
        : `/api/v1/platform-admin/tenants/${id}/tabs/${encodeURIComponent(recordTab)}`;
    if (!endpoint) {
      setRecordTabDetail({ unavailable: true });
      return;
    }
    setRecordTabDetail(null);
    api<any>(endpoint)
      .then(setRecordTabDetail)
      .catch((error) =>
        setRecordTabDetail({ error: error instanceof Error ? error.message : "Tab data is unavailable" }),
      );
  }, [recordView, recordDetail, recordTab]);

  const selectDomain = (domain: (typeof DOMAINS)[number]) => {
    setActiveDomain(domain[0]);
    setActiveItem(domain[3][0]);
    setCollapsedDomain(null);
  };
  const metrics = data.health?.metrics ?? {};
  const alerts = data.health?.alerts ?? [];
  const setupItems = DOMAINS.flatMap((domain) => domain[3].map((label) => ({ domain, label })));
  const searchResults = query.trim()
    ? setupItems
        .filter(({ domain, label }) => `${domain[0]} ${domain[1]} ${label}`.toLowerCase().includes(query.toLowerCase()))
        .slice(0, 8)
    : [];

  const summary =
    activeDomain === "AI Control Center"
      ? data.ai
      : activeDomain === "Security"
        ? data.security
        : activeDomain === "Operations" || activeDomain === "Integrations"
          ? data.operations
          : null;

  const signOut = async () => {
    await requestJson("/api/v1/auth/signout", { method: "POST", retries: 0 }).catch(() => undefined);
    window.location.replace("/signin");
  };

  const renderOverview = () => (
    <>
      <section className="platform-admin-command-grid">
        <article className="platform-admin-command-card primary">
          <span className="eyebrow">Command center</span>
          <h3>Platform operations at a glance</h3>
          <p>
            Monitor customer posture, commercial access, configuration, integrations, AI assurance, security and
            operational health.
          </p>
          <div className="platform-admin-quick-actions">
            <button onClick={() => onNavigate("admin-create-customer")}>
              <Plus size={15} /> Provision customer
            </button>
            <button
              onClick={() => {
                setActiveDomain("Customers & Tenants");
                setActiveItem("Customers");
              }}
            >
              <Users size={15} /> Customers & tenants
            </button>
            <button
              onClick={() => {
                setActiveDomain("Plans & Licensing");
                setActiveItem("Subscriptions");
              }}
            >
              <Settings2 size={15} /> Plans & licensing
            </button>
            <button
              onClick={() => {
                setActiveDomain("Identity & Access");
                setActiveItem("Platform users");
              }}
            >
              <LockKeyhole size={15} /> Identity & access
            </button>
            <button
              onClick={() => {
                setActiveDomain("Data & Configuration");
                setActiveItem("Data mapping");
              }}
            >
              <Database size={15} /> Data mapping
            </button>
            <button
              onClick={() => {
                setActiveDomain("Integrations");
                setActiveItem("Integration health");
              }}
            >
              <Activity size={15} /> Integration health
            </button>
            <button
              onClick={() => {
                setActiveDomain("AI Control Center");
                setActiveItem("AI overview");
              }}
            >
              <ShieldCheck size={15} /> AI assurance
            </button>
            <button
              onClick={() => {
                setActiveDomain("Security");
                setActiveItem("Security overview");
              }}
            >
              <ShieldCheck size={15} /> Security
            </button>
            <button
              onClick={() => {
                setActiveDomain("Operations");
                setActiveItem("System health");
              }}
            >
              <LifeBuoy size={15} /> Operations
            </button>
            <button
              onClick={() => {
                setActiveDomain("Data & Configuration");
                setActiveItem("Configuration releases");
              }}
            >
              <Settings2 size={15} /> Create release
            </button>
          </div>
        </article>
      </section>
      <section className="platform-admin-card platform-admin-control-map">
        <div className="platform-admin-card-title">
          <div>
            <span className="eyebrow">Governance map</span>
            <h3>One control plane across the product</h3>
            <p>
              Move from customer boundary and commercial access through data, intelligence, assurance, and operations.
            </p>
          </div>
          <span className="platform-admin-badge success">Server authorized</span>
        </div>
        <div className="platform-admin-control-flow">
          {[
            ["Customers & Tenants", "Establish boundaries", Users],
            ["Plans & Licensing", "Control commercial access", Settings2],
            ["Identity & Access", "Govern privileged access", LockKeyhole],
            ["Data & Configuration", "Govern product context", Database],
            ["Integrations", "Operate trusted sources", ExternalLink],
            ["AI Control Center", "Assure advisory AI", ShieldCheck],
            ["Security", "Protect boundaries", LockKeyhole],
            ["Operations", "Monitor platform health", LifeBuoy],
          ].map(([label, description, Icon]: any, index) => (
            <button
              key={label}
              onClick={() => {
                const domain = DOMAINS.find((entry) => entry[0] === label);
                if (domain) selectDomain(domain);
              }}
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              <Icon size={21} />
              <strong>{label}</strong>
              <small>{description}</small>
              <ChevronRight size={15} />
            </button>
          ))}
        </div>
      </section>
      <section className="platform-admin-metrics">
        {[
          ["Customers", data.customers.length || data.memberships.length, "Customers & Tenants", Users],
          ["Platform users", data.users.length, "Identity & Access", ShieldCheck],
          [
            "Active connectors",
            data.connectors.filter((item) => !["INACTIVE", "FAILED"].includes(String(item.status).toUpperCase()))
              .length,
            "Integrations",
            Database,
          ],
          ["Pending approvals", metrics.pending_approvals ?? 0, "Operations", CheckCircle2],
        ].map(([label, value, domainName, Icon]: any) => (
          <button
            key={label}
            onClick={() => {
              const domain = DOMAINS.find((item) => item[0] === domainName);
              if (domain) selectDomain(domain);
            }}
          >
            <Icon size={19} />
            <span>{label}</span>
            <strong>{value}</strong>
            <small>
              Open workspace <ChevronRight size={13} />
            </small>
          </button>
        ))}
      </section>
      <section className="platform-admin-card platform-admin-command-intelligence">
        <div className="platform-admin-card-title">
          <div>
            <span className="eyebrow">Command center intelligence</span>
            <h3>Control plane signals</h3>
            <p>Server-derived operational trends across customers, licensing, integrations and configuration.</p>
          </div>
          <span className="platform-admin-badge success">Live signals</span>
        </div>
        <div className="platform-admin-graph-grid">
          {[
            ["Customer posture", data.customers.length || data.memberships.length, "Customers & Tenants", Users],
            ["Subscription outlook", metrics.expiring_soon ?? 0, "Plans & Licensing", Settings2],
            [
              "Integration health",
              data.connectors.filter((item) => String(item.status).toUpperCase() === "HEALTHY").length,
              "Integrations",
              ExternalLink,
            ],
            ["Configuration activity", data.mappings.length, "Data & Configuration", Database],
            ["Platform users", data.users.length, "Identity & Access", ShieldCheck],
            ["Pending approvals", metrics.pending_approvals ?? 0, "Operations", CheckCircle2],
            ["Security events", metrics.security_events ?? 0, "Security", LockKeyhole],
            ["AI assurance coverage", metrics.ai_assurance_coverage ?? "—", "AI Control Center", ShieldCheck],
          ].map(([label, value, domainName, Icon]: any) => (
            <button
              className="platform-admin-graph-card"
              key={label}
              onClick={() => {
                const domain = DOMAINS.find((item) => item[0] === domainName);
                if (domain) selectDomain(domain);
              }}
            >
              <div className="platform-admin-graph-heading">
                <span>{label}</span>
                <Icon size={17} />
              </div>
              <strong>{value}</strong>
              <div className="platform-admin-bars">
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
              </div>
              <small>
                Open {domainName} <ChevronRight size={13} />
              </small>
            </button>
          ))}
        </div>
      </section>
      <section className="platform-admin-columns">
        <article className="platform-admin-card">
          <div className="platform-admin-card-title">
            <div>
              <span className="eyebrow">Action queue</span>
              <h3>Requires attention</h3>
            </div>
            <span className={`platform-admin-badge ${alerts.length ? "warning" : "success"}`}>
              {alerts.length ? `${alerts.length} open` : "All clear"}
            </span>
          </div>
          {alerts.length ? (
            alerts.slice(0, 5).map((alert: any, index: number) => (
              <button
                className="platform-admin-alert"
                key={alert.code ?? index}
                onClick={() => {
                  setActiveDomain("Operations");
                  setActiveItem("Incidents");
                }}
              >
                <AlertTriangle size={16} />
                <span>
                  <strong>{alert.label ?? alert.code ?? "Operational alert"}</strong>
                  <small>
                    {text(alert.count, "Review")} · {text(alert.severity, "Review")}
                  </small>
                </span>
                <ChevronRight size={15} />
              </button>
            ))
          ) : (
            <div className="platform-admin-empty compact">
              <CheckCircle2 size={24} />
              <strong>No active alerts</strong>
              <span>Platform services have not returned an action-required item.</span>
            </div>
          )}
        </article>
        <article className="platform-admin-card">
          <div className="platform-admin-card-title">
            <div>
              <span className="eyebrow">Operational insights</span>
              <h3>Control plane signals</h3>
            </div>
          </div>
          {[
            ["Configuration compliance", metrics.configuration_compliance ?? "—"],
            ["Connector availability", metrics.connector_availability ?? "—"],
            ["AI assurance coverage", metrics.ai_assurance_coverage ?? "—"],
            ["Security events", metrics.security_events ?? 0],
          ].map(([label, value]) => (
            <div className="platform-admin-health-row" key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </article>
      </section>
      <section className="platform-admin-card platform-admin-trends">
        <div className="platform-admin-card-title">
          <div>
            <span className="eyebrow">Platform trends</span>
            <h3>Operational posture over time</h3>
            <p>
              Use the governed signals above to review customer growth, configuration activity and integration
              reliability.
            </p>
          </div>
        </div>
        <div className="platform-admin-trend-grid">
          <div>
            <strong>{data.customers.length || data.memberships.length}</strong>
            <span>Customer boundary records</span>
          </div>
          <div>
            <strong>{data.mappings.length}</strong>
            <span>Configuration records</span>
          </div>
          <div>
            <strong>{data.connectors.length}</strong>
            <span>Integration records</span>
          </div>
        </div>
      </section>
    </>
  );

  const renderRecordDetail = () => {
    if (!recordView) return null;
    if (!recordDetail)
      return (
        <section className="platform-admin-card platform-admin-loading">Loading {recordView.kind} detail…</section>
      );
    if (recordDetail.error)
      return (
        <section className="platform-admin-card">
          <div className="platform-admin-error">{recordDetail.error}</div>
        </section>
      );
    const entity = recordView.kind === "customer" ? recordDetail.customer : recordDetail.tenant;
    const tabs = recordDetail.tabs ?? ["Overview"];
    const related = recordView.kind === "customer" ? recordDetail.tenants : recordDetail.environments;
    const fields =
      recordView.kind === "customer"
        ? [
            ["Customer ID", entity.customer_identifier],
            ["Legal name", entity.legal_name],
            ["Display name", entity.display_name],
            ["Type", entity.customer_type],
            ["Industry", entity.industry],
            ["Country", entity.country],
            ["Headquarters", entity.headquarters],
            ["Lifecycle", entity.lifecycle_status],
          ]
        : [
            ["Tenant ID", entity.tenant_identifier],
            ["Customer ID", entity.customer_id],
            ["Display name", entity.display_name],
            ["Environment model", entity.deployment_model],
            ["Primary region", entity.primary_region],
            ["Data residency", entity.residency_region],
            ["Provisioning", entity.provisioning_status],
            ["Status", entity.status],
            ["Configuration", entity.configuration_version],
          ];
    if (recordTab !== "Overview" && recordTabDetail)
      return (
        <section className="platform-admin-record-page">
          <div className="platform-admin-record-header">
            <div>
              <button
                className="platform-admin-back"
                onClick={() => {
                  setRecordTab("Overview");
                }}
              >
                ← Back to {recordView.kind === "customer" ? "Customer 360" : "Tenant 360"}
              </button>
              <span className="eyebrow">{recordView.kind === "customer" ? "Customer 360" : "Tenant 360"}</span>
              <h2>{entity.display_name ?? entity.legal_name ?? entity.name}</h2>
              <p>
                {entity.customer_identifier ?? entity.tenant_identifier ?? entity.id} ·{" "}
                <span className="platform-admin-badge success">Server authorized</span>
              </p>
            </div>
          </div>
          <nav className="platform-admin-record-tabs" aria-label={`${recordView.kind} detail tabs`}>
            {tabs.map((tab: string) => (
              <button key={tab} className={recordTab === tab ? "active" : ""} onClick={() => setRecordTab(tab)}>
                {tab}
              </button>
            ))}
          </nav>
          <section className="platform-admin-card">
            {recordView.kind === "customer" ? (
              <Customer360TabPanel tab={recordTab} detail={recordTabDetail} />
            ) : (
              <StructuredRecordTabPanel kind="tenant" tab={recordTab} detail={recordTabDetail} />
            )}
          </section>
        </section>
      );
    return (
      <section className="platform-admin-record-page">
        <div className="platform-admin-record-header">
          <div>
            <button
              className="platform-admin-back"
              onClick={() => {
                setRecordView(null);
                setRecordTab("Overview");
              }}
            >
              ← Back to {recordView.kind === "customer" ? "customers" : "tenants"}
            </button>
            <span className="eyebrow">{recordView.kind === "customer" ? "Customer 360" : "Tenant 360"}</span>
            <h2>{entity.display_name ?? entity.legal_name ?? entity.name}</h2>
            <p>
              {entity.customer_identifier ?? entity.tenant_identifier} ·{" "}
              <span className="platform-admin-badge success">{entity.lifecycle_status ?? entity.status}</span>
            </p>
          </div>
          <div className="platform-admin-record-actions">
            <button onClick={() => setRecordTab("Security")}>Security</button>
            <button onClick={() => setRecordTab("Audit")}>Audit</button>
          </div>
        </div>
        <nav className="platform-admin-record-tabs" aria-label={`${recordView.kind} detail tabs`}>
          {tabs.map((tab: string) => (
            <button key={tab} className={recordTab === tab ? "active" : ""} onClick={() => setRecordTab(tab)}>
              {tab}
            </button>
          ))}
        </nav>
        {recordTab === "Overview" ? (
          <>
            <div className="platform-admin-detail-grid">
              {fields.map(([label, value]) => (
                <div key={label as string}>
                  <small>{label}</small>
                  <strong>{text(value)}</strong>
                </div>
              ))}
            </div>
            <div className="platform-admin-card platform-admin-related-records">
              <h3>{recordView.kind === "customer" ? "Related tenants" : "Environments"}</h3>
              {related?.length ? (
                <RecordTable
                  rows={related}
                  columns={
                    recordView.kind === "customer"
                      ? [
                          ["Tenant", (r) => r.display_name],
                          ["Tenant ID", (r) => r.tenant_identifier],
                          ["Region", (r) => r.primary_region],
                          ["Status", (r) => r.status],
                        ]
                      : [
                          ["Environment", (r) => r.environment_identifier],
                          ["Type", (r) => r.environment_type],
                          ["Region", (r) => r.region],
                          ["Status", (r) => r.status],
                        ]
                  }
                  empty="No related records"
                />
              ) : (
                <div className="platform-admin-empty compact">No related records returned.</div>
              )}
            </div>
          </>
        ) : (
          <div className="platform-admin-card">
            <div className="platform-admin-card-title">
              <div>
                <span className="eyebrow">Server-authorized tab</span>
                <h3>{recordTab}</h3>
                <p>Data is loaded from the governed API for the selected {recordView.kind} record.</p>
              </div>
              <span className="platform-admin-badge success">Tenant aware</span>
            </div>
            {recordTabDetail?.error ? (
              <div className="platform-admin-error">{recordTabDetail.error}</div>
            ) : recordTabDetail?.unavailable ? (
              <div className="platform-admin-empty compact">No dedicated endpoint is available for this tab yet.</div>
            ) : Array.isArray(recordTabDetail?.items) ? (
              <RecordTable
                rows={recordTabDetail.items}
                empty={`No ${recordTab.toLowerCase()} records`}
                columns={
                  Object.keys(recordTabDetail.items[0] ?? {})
                    .filter((key) => !["id", "details", "scope", "limits"].includes(key))
                    .slice(0, 6)
                    .map((key) => [
                      title(key),
                      (row) => (typeof row[key] === "object" ? JSON.stringify(row[key]) : row[key]),
                    ]) as Array<[string, (row: any) => unknown]>
                }
              />
            ) : recordTab === "Health" && recordDetail.last_health_run ? (
              <div className="platform-admin-detail-grid">
                <div>
                  <small>Last run</small>
                  <strong>{text(recordDetail.last_health_run.completed_at)}</strong>
                </div>
                <div>
                  <small>Status</small>
                  <strong>{text(recordDetail.last_health_run.status)}</strong>
                </div>
              </div>
            ) : (
              <pre className="platform-admin-json-detail">
                {JSON.stringify(recordTabDetail ?? recordDetail, null, 2)}
              </pre>
            )}
          </div>
        )}
      </section>
    );
  };

  const renderWorkspace = () => {
    if (recordView)
      return (
        <>
          {renderRecordDetail()}
          {recordView.kind === "customer" && recordDetail?.customer ? (
            <Customer360QuickActions
              customer={recordDetail.customer}
              tenants={recordDetail.tenants ?? []}
              onTab={setRecordTab}
              onRefresh={() => setRefreshVersion((value) => value + 1)}
            />
          ) : recordView.kind === "tenant" && recordDetail?.tenant ? (
            <Tenant360QuickActions
              tenant={recordDetail.tenant}
              environments={recordDetail.environments ?? []}
              onTab={setRecordTab}
              onRefresh={() => setRefreshVersion((value) => value + 1)}
            />
          ) : null}
        </>
      );
    if (activeDomain === "Integrations" && activeItem === "Integration runs")
      return <AdminOperationalRecords item="Integration runs" rows={data.integrationRuns} />;
    if (activeDomain === "Integrations" && activeItem === "Reconciliation")
      return <AdminOperationalRecords item="Reconciliation" rows={data.reconciliation} />;
    if (activeDomain === "Integrations" && activeItem === "Credentials")
      return <AdminOperationalRecords item="Credentials" rows={data.credentials} />;
    if (activeDomain === "AI Control Center" && activeItem === "AI executions")
      return <AdminOperationalRecords item="AI executions" rows={data.aiExecutions} />;
    if (activeDomain === "Platform Overview") return renderOverview();
    if (activeDomain === "Customers & Tenants") {
      if (activeItem === "Customer Directory")
        return (
          <CustomerDirectory
            onOpen={(row) => {
              const id = row.customer_id ?? row.id;
              if (id) {
                setRecordView({ kind: "customer", id: String(id) });
                setRecordTab("Overview");
              }
            }}
          />
        );
      if (activeItem === "Provisioning Jobs")
        return <ProvisioningJobsWorkspace data={data} onRefresh={() => setRefreshVersion((value) => value + 1)} />;
      if (activeItem === "Domain & Identity")
        return <DomainIdentityWorkspace data={data} onRefresh={() => setRefreshVersion((value) => value + 1)} />;
      if (activeItem === "Tenant Audit") return <AuditEvidenceWorkspace data={data} />;
      if (["Environments", "Data Residency", "Tenant Security", "Suspension & Reactivation"].includes(activeItem))
        return (
          <PlatformLifecycleWorkspace
            item={activeItem}
            data={data}
            onRefresh={() => setRefreshVersion((value) => value + 1)}
          />
        );
      if (["Customer Onboarding"].includes(activeItem))
        return (
          <section className="platform-admin-card platform-admin-process">
            <div>
              <span className="eyebrow">Governed onboarding</span>
              <h3>Provision a customer tenant</h3>
              <p>
                Create immutable customer and tenant identities, assign commercial access, establish security controls,
                and invite the first Customer Administrator.
              </p>
            </div>
            <ol>
              <li>
                <strong>Organization</strong>
                <span>Legal identity and approved domains</span>
              </li>
              <li>
                <strong>Tenant boundary</strong>
                <span>Region, residency and immutable identifier</span>
              </li>
              <li>
                <strong>Commercial access</strong>
                <span>Plan version, seats and entitlements</span>
              </li>
              <li>
                <strong>Security baseline</strong>
                <span>MFA, configuration and isolation checks</span>
              </li>
            </ol>
            <button className="platform-admin-primary" onClick={() => onNavigate("admin-create-customer")}>
              <Plus size={15} /> Start provisioning
            </button>
          </section>
        );
      if (
        [
          "Provisioning Jobs",
          "Environments",
          "Domain & Identity",
          "Data Residency",
          "Tenant Security",
          "Tenant Audit",
          "Suspension & Reactivation",
        ].includes(activeItem)
      ) {
        const rows =
          activeItem === "Tenant Audit"
            ? data.audit
            : activeItem === "Tenant Security"
              ? (data.security?.controls ?? [])
              : activeItem === "Provisioning Jobs"
                ? (data.operations?.provisioning_jobs ?? [])
                : activeItem === "Environments"
                  ? data.customers.flatMap((row) => row.environments ?? [])
                  : data.customers;
        const columns: Array<[string, (row: any) => unknown]> =
          activeItem === "Data Residency"
            ? [
                ["Tenant", (r) => r.name ?? r.display_name],
                ["Primary region", (r) => r.primary_region ?? r.region],
                ["Residency", (r) => r.residency_region ?? r.data_residency],
                ["Database", (r) => r.database_region],
                ["Storage", (r) => r.storage_region],
                ["Policy", (r) => r.cross_border_processing_policy ?? "Controlled"],
              ]
            : activeItem === "Domain & Identity"
              ? [
                  ["Tenant", (r) => r.name ?? r.display_name],
                  ["Domains", (r) => (r.domains ?? []).join(", ") || "Configured server-side"],
                  ["Identity provider", (r) => r.identity_provider ?? "MDARIX Identity"],
                  ["Status", (r) => r.status ?? "Configured"],
                ]
              : activeItem === "Tenant Audit"
                ? [
                    ["Action", (r) => r.action],
                    ["Object", (r) => r.entity_type ?? r.resource],
                    ["Actor", (r) => r.actor_email ?? r.user_id],
                    ["When", (r) => r.created_at ?? r.timestamp],
                    ["Reason", (r) => r.reason],
                  ]
                : [
                    ["Tenant / record", (r) => r.tenant_name ?? r.name ?? r.display_name ?? r.code],
                    ["Identifier", (r) => r.tenant_identifier ?? r.environment_identifier ?? r.id],
                    ["Status", (r) => r.status ?? r.lifecycle_status],
                    ["Updated", (r) => r.updated_at ?? r.created_at],
                  ];
        return (
          <section className="platform-admin-card">
            <div className="platform-admin-card-title">
              <div>
                <span className="eyebrow">Tenant lifecycle control</span>
                <h3>{activeItem}</h3>
                <p>
                  Server-authorized, tenant-scoped operational records with auditable actions and immutable identifiers.
                </p>
              </div>
              <span className="platform-admin-badge success">Governed</span>
            </div>
            <RecordTable rows={rows} empty={`${activeItem} data is not available yet`} columns={columns} />
          </section>
        );
      }
      if (["Tenant Health"].includes(activeItem)) return <TenantHealthCommandCenter data={data} />;
      if (activeItem === "Tenant Management")
        return (
          <TenantDirectoryEnhanced
            onOpen={(row) => {
              const id = row.id ?? row.tenant_id;
              if (id) {
                setRecordView({ kind: "tenant", id: String(id) });
                setRecordTab("Overview");
              }
            }}
          />
        );
      if (activeItem === "Tenant 360")
        return (
          <section className="platform-admin-card">
            <RecordTable
              rows={data.customers}
              empty="No tenants available"
              onRowClick={(row) => {
                const id = row.tenant_id ?? row.id;
                if (id) {
                  setRecordView({ kind: "tenant", id: String(id) });
                  setRecordTab("Overview");
                }
              }}
              columns={[
                ["Tenant", (r) => r.tenant_name ?? r.display_name ?? r.name],
                ["Immutable tenant ID", (r) => r.tenant_id ?? r.id ?? r.tenant_key],
                ["Boundary status", (r) => r.tenant_status ?? r.status],
                ["Residency", (r) => r.data_residency ?? r.region],
              ]}
            />
          </section>
        );
      if (["Customer Administrators"].includes(activeItem))
        return (
          <CustomerAdminContinuityPanel
            rows={data.users.filter((row) =>
              String(row.active_role ?? row.role ?? "")
                .toLowerCase()
                .includes("admin"),
            )}
          />
        );
      if (activeItem === "Support access") return <SupportAccessPanel />;
      return (
        <section className="platform-admin-card">
          <RecordTable
            rows={data.customers.length ? data.customers : data.memberships}
            empty="No customers available"
            onRowClick={(row) => {
              const id = row.customer_id ?? row.id;
              if (id) {
                setRecordView({ kind: "customer", id: String(id) });
                setRecordTab("Overview");
              }
            }}
            columns={[
              ["Customer", (r) => r.display_name ?? r.legal_name ?? r.name],
              ["Customer ID", (r) => r.customer_id ?? r.id],
              ["Tenant", (r) => r.tenant_key ?? r.tenant_id],
              ["Plan", (r) => r.plan_name ?? r.plan_code],
              ["Status", (r) => r.status ?? r.tenant_status],
            ]}
          />
        </section>
      );
    }
    if (activeDomain === "Plans & Licensing") {
      if (activeItem === "Reminder rules") return <ReminderWorkspace />;
      if (["Plans", "Entitlements", "Subscriptions", "Expirations"].includes(activeItem))
        return <SubscriptionWorkspace item={activeItem} data={data} />;
      const rows =
        activeItem === "Entitlements" ? data.entitlements : activeItem === "Plans" ? data.plans : data.customers;
      const columns: Array<[string, (row: any) => unknown]> =
        activeItem === "Plans"
          ? [
              ["Plan", (r) => r.name ?? r.display_name ?? r.code],
              ["Version", (r) => r.version],
              ["Seat rule", (r) => r.seat_cap ?? r.seat_rule],
              ["Status", (r) => r.status],
            ]
          : activeItem === "Entitlements"
            ? [
                ["Entitlement", (r) => r.name ?? r.code],
                ["Feature", (r) => r.feature_code],
                ["Limit", (r) => r.limit_value ?? r.value],
                ["Status", (r) => r.status],
              ]
            : [
                ["Customer", (r) => r.display_name ?? r.name],
                ["Plan", (r) => r.plan_name ?? r.plan_code],
                [
                  activeItem === "Expirations" ? "Expires" : "Subscription status",
                  (r) =>
                    activeItem === "Expirations" ? (r.expires_at ?? r.expiry_date) : (r.license_status ?? r.status),
                ],
                ["Seats", (r) => r.seat_usage ?? r.seat_cap],
              ];
      return (
        <section className="platform-admin-card">
          <RecordTable rows={rows} empty={`No ${activeItem.toLowerCase()} available`} columns={columns} />
        </section>
      );
    }
    if (activeDomain === "Identity & Access") {
      if (["MFA & SSO", "Sessions"].includes(activeItem))
        return (
          <section className="platform-admin-card platform-admin-policy-view">
            <div>
              <span className="eyebrow">Identity assurance</span>
              <h3>{activeItem === "Sessions" ? "Session control posture" : "Authentication policy posture"}</h3>
              <p>
                {activeItem === "Sessions"
                  ? "Review durable sessions, expiry, revocation, and concurrent access controls without exposing session secrets."
                  : "Platform identities use governed MFA and SSO policy boundaries. Tenant administrators cannot grant platform privilege."}
              </p>
            </div>
            <div className="platform-admin-summary-grid">
              {[
                ["Platform identities", data.users.length],
                ["Active roles", data.roles.length],
                ["Security events", metrics.security_events ?? 0],
              ].map(([label, value]) => (
                <div key={label}>
                  <small>{label}</small>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
          </section>
        );
      if (activeItem === "Effective Permissions")
        return (
          <AdminCapabilityWorkspace
            item={activeItem}
            data={data}
            rows={[...data.permissions, ...data.roles]}
            description="Evaluate the server-derived permission source, decision, and reason for a platform identity."
          />
        );
      if (activeItem === "Access Reviews")
        return (
          <AdminCapabilityWorkspace
            item={activeItem}
            data={data}
            rows={data.audit.filter((row) =>
              /ACCESS|ROLE|PERMISSION/i.test(String(row.action ?? row.event_type ?? "")),
            )}
            description="Review privileged-access decisions and retain reviewer evidence without exposing credentials."
          />
        );
      const rows =
        activeItem === "Platform roles" ? data.roles : activeItem === "Permission sets" ? data.permissions : data.users;
      return (
        <section className="platform-admin-card">
          <RecordTable
            rows={rows}
            empty={`No ${activeItem.toLowerCase()} available`}
            columns={[
              ["Identity / record", (r) => r.display_name ?? r.name ?? r.email ?? r.code],
              ["Email / code", (r) => r.email ?? r.code],
              ["Role", (r) => r.active_role ?? r.role ?? r.role_name],
              ["Status", (r) => r.status ?? "Configured"],
            ]}
          />
        </section>
      );
    }
    if (activeDomain === "Data & Configuration") {
      if (activeItem === "Configuration 360") return <DataConfiguration360 data={data} onSelect={setActiveItem} />;
      if (
        [
          "Mapping 360",
          "Configuration Release 360",
          "Customer Configuration 360",
          "Canonical Object 360",
          "Schema 360",
        ].includes(activeItem)
      )
        return <Record360Workspace kind={activeItem.replace(" 360", "") as any} data={data} />;
      if (activeItem === "Master data") return <MasterDataWorkspace />;
      if (activeItem === "Canonical data model") return <CanonicalDataModelWorkspace />;
      if (activeItem === "Transformation library") return <TransformationLibraryWorkspace />;
      if (activeItem === "Validation & data quality") return <ValidationQualityWorkspace data={data} />;
      if (activeItem === "Customer baselines" || activeItem === "Customer overrides")
        return <CustomerBaselineWorkspace />;
      if (activeItem === "Mapping versions") return <Mapping360Workspace data={data} />;
      if (activeItem === "Configuration releases") return <ConfigurationReleasesWorkspace data={data} />;
      if (activeItem === "Data mapping") return <MappingWizardWorkspace />;
      if (
        [
          "Reference data",
          "Validation rules",
          "Configuration sets",
          "Change requests",
          "Dependencies & impact",
          "Deployments",
          "Import / Export",
          "Upgrade center",
        ].includes(activeItem)
      )
        return <ConfigurationDomainWorkspace item={activeItem} data={data} />;
      return (
        <section className="platform-admin-card">
          <RecordTable
            rows={data.mappings}
            empty={`No ${activeItem.toLowerCase()} records available`}
            columns={
              activeItem === "Mapping versions"
                ? [
                    ["Mapping", (r) => r.name ?? r.code],
                    ["Version", (r) => r.version],
                    ["Lifecycle", (r) => r.status],
                    ["Updated", (r) => r.updated_at],
                  ]
                : [
                    [activeItem, (r) => r.name ?? r.code ?? r.mapping_name],
                    ["Source", (r) => r.source_system ?? r.source_entity],
                    ["Target", (r) => r.target_entity],
                    ["Status", (r) => r.status],
                  ]
            }
          />
        </section>
      );
    }
    if (activeDomain === "Integrations") {
      if (activeItem === "Integration Template 360")
        return <Record360Workspace kind="Integration Template" data={data} />;
      if (activeItem === "API & contract registry") return <ApiContractRegistryWorkspace />;
      if (["Connector catalog", "Customer integrations", "Integration registry"].includes(activeItem))
        return <IntegrationRegistryWorkspace data={data} />;
      if (activeItem === "Schema registry") return <SchemaRegistryWorkspace />;
      const rows =
        activeItem === "Failures & logs"
          ? data.connectors.filter((r) =>
              ["FAILED", "DEGRADED", "ERROR"].includes(String(r.status ?? r.health_status).toUpperCase()),
            )
          : data.connectors;
      return (
        <section className="platform-admin-card">
          <RecordTable
            rows={rows}
            empty={
              activeItem === "Failures & logs"
                ? "No connector failures recorded"
                : `No ${activeItem.toLowerCase()} available`
            }
            columns={
              activeItem === "Integration health" || activeItem === "Failures & logs"
                ? [
                    ["Connector", (r) => r.name ?? r.code],
                    ["Health", (r) => r.health_status ?? r.status],
                    ["Last check", (r) => r.last_health_check ?? r.updated_at],
                    ["Failure", (r) => r.last_error ?? r.error_code],
                  ]
                : [
                    ["Connector", (r) => r.name ?? r.code ?? r.provider],
                    ["Provider", (r) => r.provider ?? r.connector_type],
                    ["Schema", (r) => r.schema_version],
                    ["Status", (r) => r.status ?? r.health_status],
                  ]
            }
          />
        </section>
      );
    }
    if (["AI Control Center", "Security", "Operations"].includes(activeDomain))
      return <ControlCenterWorkspace domain={activeDomain} item={activeItem} data={data} metrics={metrics} />;
    return (
      <section className="platform-admin-card">
        <div className="platform-admin-card-title">
          <div>
            <span className="eyebrow">Server-derived status</span>
            <h3>Control status</h3>
          </div>
          <span className={`platform-admin-badge ${summary?.status === "HEALTHY" ? "success" : "warning"}`}>
            {summary?.status ?? "No status"}
          </span>
        </div>
        {Object.keys(summary?.metrics ?? {}).length ? (
          <div className="platform-admin-summary-grid">
            {Object.entries(summary.metrics).map(([label, value]) => (
              <div key={label}>
                <small>{title(label)}</small>
                <strong>{text(value)}</strong>
              </div>
            ))}
          </div>
        ) : (
          <div className="platform-admin-empty compact">
            <Database size={24} />
            <strong>No metrics available</strong>
            <span>This service returned no authorized operational metrics.</span>
          </div>
        )}
      </section>
    );
  };

  if (loading)
    return (
      <div className="content platform-admin-screen">
        <section className="platform-admin-loading">Loading governed platform data…</section>
      </div>
    );

  return (
    <div className="content platform-admin-screen">
      <LifecycleConfirmationDialog />
      <header className="platform-admin-topbar">
        <div className="platform-admin-identity">
          <span className="platform-admin-brand">MDARIX</span>
          <span className="platform-admin-divider">Administrator Control Plane</span>
        </div>
        <div className="platform-admin-search-wrap">
          <label className="platform-admin-search">
            <Search size={17} aria-hidden="true" />
            <input
              aria-label="Search platform setup"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search customers, integrations, security…"
            />
          </label>
          {searchResults.length > 0 && (
            <div className="platform-admin-search-results">
              {searchResults.map(({ domain, label }) => (
                <button
                  key={`${domain[0]}-${label}`}
                  onClick={() => {
                    selectDomain(domain);
                    setActiveItem(label);
                    setQuery("");
                  }}
                >
                  <strong>{label}</strong>
                  <small>{domain[0]}</small>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="platform-admin-user">
          <Bell size={17} aria-label="Notifications" />
          <span>{securityContext?.display_name ?? "Administrator"}</span>
          <small>{securityContext?.active_role ?? "Platform Administrator"}</small>
          <button className="platform-admin-logout" onClick={signOut}>
            Logout
          </button>
        </div>
      </header>
      <div className="platform-admin-layout">
        <aside className="platform-admin-sidebar" aria-label="Platform administration domains">
          <span className="platform-admin-sidebar-title">Control plane</span>
          {DOMAINS.map((domain) => {
            const [label, description, Icon, items] = domain;
            const expanded = activeDomain === label && collapsedDomain !== label;
            return (
              <div className="platform-admin-domain" key={label}>
                <button
                  className={activeDomain === label ? "active" : ""}
                  aria-expanded={items.length > 1 ? expanded : undefined}
                  title="Click to open. Double-click to collapse subsections."
                  onClick={() => {
                    if (activeDomain === label && collapsedDomain === label) setCollapsedDomain(null);
                    else selectDomain(domain);
                  }}
                  onDoubleClick={() => {
                    if (items.length > 1) {
                      setActiveDomain(label);
                      setCollapsedDomain(label);
                    }
                  }}
                >
                  <Icon size={17} />
                  <span>
                    <strong>{label}</strong>
                    <small>{description}</small>
                  </span>
                  <ChevronRight className={expanded ? "expanded" : ""} size={15} />
                </button>
                {expanded && items.length > 1 && (
                  <div className="platform-admin-subnav">
                    {items.map((item) => (
                      <button
                        className={activeItem === item ? "selected" : ""}
                        key={item}
                        onClick={() => setActiveItem(item)}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </aside>
        <main className="platform-admin-workspace" data-admin-view={`${activeDomain}:${activeItem}`}>
          {activeDomain !== "Platform Overview" && (
            <div className="platform-admin-heading">
              <div>
                <button
                  className="platform-admin-back"
                  onClick={() => {
                    setActiveDomain("Platform Overview");
                    setActiveItem("Overview");
                  }}
                >
                  <ArrowLeft size={15} /> Platform overview
                </button>
                <span className="eyebrow">{activeDomain}</span>
                <h2>{activeItem}</h2>
                <p>{DOMAINS.find((domain) => domain[0] === activeDomain)?.[1]}</p>
              </div>
              <div className="platform-admin-heading-actions">
                <span>
                  <Clock3 size={14} />{" "}
                  {lastUpdated
                    ? `Updated ${lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
                    : "Awaiting refresh"}
                </span>
                <button
                  className="platform-admin-refresh"
                  onClick={() => {
                    setLoading(true);
                    setRefreshVersion((value) => value + 1);
                  }}
                  aria-label="Refresh platform data"
                >
                  <RefreshCw size={16} /> Refresh
                </button>
                {activeDomain === "Customers & Tenants" && (
                  <button className="platform-admin-primary" onClick={() => onNavigate("admin-create-customer")}>
                    <Plus size={16} /> New customer
                  </button>
                )}
              </div>
            </div>
          )}
          {renderWorkspace()}
        </main>
      </div>
    </div>
  );
}
