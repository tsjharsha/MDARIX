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
  DATA_INTEGRATION_SECTIONS,
  IDENTITY_SECTIONS,
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
export const DOMAINS = [
  ["Platform Overview", "Health, activity and attention", LayoutDashboard, ["Overview"]],
  ["Customers & Tenants", "Customer and tenant lifecycle", Users, CUSTOMER_TENANT_SECTIONS],
  ["Plans & Licensing", "Plans, subscriptions and reminders", Settings2, PLANS_SECTIONS],
  ["Identity & Access", "Accounts, roles and onboarding requests", LockKeyhole, IDENTITY_SECTIONS],
  ["Data & Integrations", "Define, connect, map, release and run customer data", Database, DATA_INTEGRATION_SECTIONS],
  ["AI Control Center", "Models, evaluations and assurance", ShieldCheck, AI_SECTIONS],
  ["Security", "Isolation, audit, support access and retention", LockKeyhole, SECURITY_SECTIONS],
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

export function PlatformAdminScreen({
  securityContext,
  onNavigate,
  initialItem,
  initialDomain,
  embedded = false,
  onLocationChange,
}: PlatformAdminScreenProps) {
  const Workspace = embedded ? "div" : "main";
  const [data, setData] = useState<AdminData>(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [, setUnavailable] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [activeDomain, setActiveDomain] = useState(
    initialDomain ?? (initialItem ? "Data & Integrations" : "Platform Overview"),
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
        : activeDomain === "Operations" || activeDomain === "Data & Integrations"
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
              <Plus size={15} /> Create customer
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
                setActiveDomain("Data & Integrations");
                setActiveItem("Mappings");
              }}
            >
              <Database size={15} /> Data mapping
            </button>
            <button
              onClick={() => {
                setActiveDomain("Data & Integrations");
                setActiveItem("Runs & failures");
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
                setActiveDomain("Data & Integrations");
                setActiveItem("Releases");
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
            <h3>One place to administer the whole product</h3>
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
            ["Data & Integrations", "Define, connect and run customer data", Database],
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
            "Data & Integrations",
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
            <h3>Platform signals</h3>
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
              "Data & Integrations",
              ExternalLink,
            ],
            ["Configuration activity", data.mappings.length, "Data & Integrations", Database],
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
              <h3>Platform signals</h3>
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
          <span className="platform-admin-divider">Platform administration</span>
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
          <span className="platform-admin-sidebar-title">Platform administration</span>
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
        {/* Embedded in the console, whose main landmark already contains it. */}
        <Workspace className="platform-admin-workspace" data-admin-view={`${activeDomain}:${activeItem}`}>
          {workspaceHeading}
          {renderWorkspace()}
        </Workspace>
      </div>
    </div>
  );
}
