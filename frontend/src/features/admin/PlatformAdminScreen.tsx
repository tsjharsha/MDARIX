import { useEffect, useState } from "react";
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
import { SECTIONS as CUSTOMER_TENANT_SECTIONS } from "./customers/model";
import { AdminArea, isAreaDomain } from "./areas/AdminArea";
import {
  AI_SECTIONS,
  IDENTITY_SECTIONS,
  INTEGRATION_SECTIONS,
  OPERATIONS_SECTIONS,
  PLANS_SECTIONS,
  SECURITY_SECTIONS,
} from "./areas/sections";

type PlatformAdminScreenProps = {
  securityContext: { display_name: string; active_role: string | null; tenant_id?: string } | null;
  onNavigate: (view: any) => void;
  initialItem?: string;
  // Embedded mode: rendered inside the Platform Administrator console, which owns the header and navigation.
  initialDomain?: string;
  embedded?: boolean;
  onLocationChange?: (domain: string, item: string) => void;
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

// Transformation codes used before Master Data v1 -> md_master.transformation_definition codes.
const MASTER_TRANSFORM_CODE: Record<string, string> = {
  DIRECT: "DIRECT_COPY",
  DIRECT_COPY: "DIRECT_COPY",
  UPPER: "UPPERCASE",
  LOWER: "LOWERCASE",
  DATE_ISO8601: "DATE_PARSE",
  REFERENCE_LOOKUP: "LOOKUP",
};

export const DOMAINS = [
  ["Platform Overview", "Health, activity and attention", LayoutDashboard, ["Overview"]],
  ["Customers & Tenants", "Customer and tenant lifecycle", Users, CUSTOMER_TENANT_SECTIONS],
  ["Plans & Licensing", "Plans, subscriptions and reminders", Settings2, PLANS_SECTIONS],
  ["Identity & Access", "Platform users, roles and access", LockKeyhole, IDENTITY_SECTIONS],
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
  ["Integrations", "Connectors, runs and schemas", ExternalLink, INTEGRATION_SECTIONS],
  ["AI Control Center", "Models, evaluations and assurance", ShieldCheck, AI_SECTIONS],
  ["Security", "Isolation, encryption and controls", LockKeyhole, SECURITY_SECTIONS],
  ["Operations", "Health, queues, email and API", LifeBuoy, OPERATIONS_SECTIONS],
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
          transform: kind === "value" ? "ENUM_MAP" : "DIRECT_COPY",
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
            row.code === "LOOKUP"
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
          transform: MASTER_TRANSFORM_CODE[row.transform ?? "DIRECT_COPY"] ?? row.transform,
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
        rows={rules.filter((r: any) => r.transform && !["DIRECT", "DIRECT_COPY"].includes(r.transform))}
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
  const transition = async (action: "REQUEST_APPROVAL" | "APPROVE" | "PROMOTE" | "ROLLBACK") => {
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
                disabled={selected.release_status !== "READY_FOR_APPROVAL"}
                onClick={() => void transition("APPROVE")}
                title="Must be a different administrator from the one who requested approval"
              >
                Approve
              </button>
              <button disabled={selected.release_status !== "APPROVED"} onClick={() => void transition("PROMOTE")}>
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
              Approval needs a second administrator; only released mappings can import data.
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

export function PlatformAdminScreen({
  securityContext,
  onNavigate,
  initialItem,
  initialDomain,
  embedded = false,
  onLocationChange,
}: PlatformAdminScreenProps) {
  const [data, setData] = useState<AdminData>(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [, setUnavailable] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [activeDomain, setActiveDomain] = useState(
    initialDomain ?? (initialItem ? "Data & Configuration" : "Platform Overview"),
  );
  const [activeItem, setActiveItem] = useState(initialItem ?? "Overview");

  // Embedded mode: the host console drives the location and is told about in-workspace navigation.
  useEffect(() => {
    if (!embedded) return;
    if (initialDomain) setActiveDomain(initialDomain);
    if (initialItem) setActiveItem(initialItem);
  }, [embedded, initialDomain, initialItem]);
  useEffect(() => {
    if (embedded) onLocationChange?.(activeDomain, activeItem);
  }, [embedded, activeDomain, activeItem]);
  const [collapsedDomain, setCollapsedDomain] = useState<string | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
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

  const renderWorkspace = () => {
    // Plans & Licensing … Operations have their own pages (areas/); only the remaining domains render here.
    if (isAreaDomain(activeDomain)) return <AdminArea domain={activeDomain} section={activeItem} />;
    if (activeDomain === "Platform Overview") return renderOverview();
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
      <div className={embedded ? "platform-admin-embedded" : "content platform-admin-screen"}>
        <section className="platform-admin-loading">Loading governed platform data…</section>
      </div>
    );

  const workspaceHeading = activeDomain !== "Platform Overview" && (
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
      </div>
    </div>
  );

  if (embedded)
    return (
      <div className="platform-admin-embedded">
        <section className="platform-admin-workspace" data-admin-view={`${activeDomain}:${activeItem}`}>
          {workspaceHeading}
          {renderWorkspace()}
        </section>
      </div>
    );

  return (
    <div className="content platform-admin-screen">
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
          {workspaceHeading}
          {renderWorkspace()}
        </main>
      </div>
    </div>
  );
}
