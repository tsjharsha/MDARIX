import { useEffect, useMemo, useState } from "react";

type Section = "Overview" | "Organization" | "Users" | "Roles & Access" | "Product Configuration" | "Integrations" | "Data Mapping" | "Plans & Entitlements" | "Security" | "Notifications" | "Audit";

type Context = {
  display_name?: string;
  active_role?: string | null;
  tenant_id?: string;
  environment?: string;
  current_tenant?: { tenant_name?: string; tenant_key?: string; status?: string };
};

const nav: Array<{ section: Section; items: string[]; endpoint: string }> = [
  { section: "Overview", items: ["Dashboard", "Requires Attention", "Recent Administration"], endpoint: "/api/v1/admin/tenant-dashboard" },
  { section: "Organization", items: ["Company Profile", "Tenant Information", "Region & Data Residency"], endpoint: "/api/v1/session/context" },
  { section: "Users", items: ["All Users", "Invite User", "Pending Invitations", "Inactive Users"], endpoint: "/api/v1/admin/identity/users" },
  { section: "Roles & Access", items: ["Roles", "Personas", "Permission Sets", "Field Permissions", "Action Permissions", "Approval Authority", "Effective Access"], endpoint: "/api/v1/admin/identity/roles" },
  { section: "Product Configuration", items: ["Product Visibility", "Product Configuration", "Persona Visibility"], endpoint: "/api/v1/admin/configuration/mappings" },
  { section: "Integrations", items: ["Connections", "Connector Health", "Sync Activity", "Credentials Status"], endpoint: "/api/v1/admin/configuration/connectors" },
  { section: "Data Mapping", items: ["Active Mapping", "Tenant Overrides", "Mapping Updates", "Conflicts", "Reference Data"], endpoint: "/api/v1/admin/configuration/data-mappings" },
  { section: "Plans & Entitlements", items: ["Current Plan", "Effective Entitlements", "Usage & Limits"], endpoint: "/api/v1/admin/governance/entitlements" },
  { section: "Security", items: ["MFA", "SSO", "Sessions", "Authentication Policy", "Security Events"], endpoint: "/api/v1/session/context" },
  { section: "Notifications", items: ["Email Recipients", "Reminder Preferences", "Administrative Notifications"], endpoint: "/api/v1/admin/smtp-status" },
  { section: "Audit", items: ["Administrative Audit", "Access Events", "Configuration History", "Export"], endpoint: "/api/v1/admin/audit-history" },
];

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { credentials: "include" });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.detail?.message ?? payload?.detail ?? `Request failed (${response.status})`);
  return payload as T;
}

function rowsOf(value: any): any[] {
  if (Array.isArray(value)) return value;
  return value?.items ?? value?.users ?? value?.roles ?? value?.entitlements ?? value?.records ?? value?.alerts ?? value?.recent_audit ?? [];
}

function statusOf(value: any): string {
  return String(value?.status ?? value?.state ?? value?.lifecycle_status ?? "ACTIVE").replace(/_/g, " ");
}

function Status({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  return <span className={`ca-status ${normalized.includes("fail") || normalized.includes("denied") || normalized.includes("inactive") ? "danger" : normalized.includes("pending") || normalized.includes("attention") ? "warning" : "success"}`}>{value}</span>;
}

function Metric({ label, value, note, tone = "default" }: { label: string; value: string | number; note: string; tone?: string }) {
  return <article className={`ca-metric ${tone}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

function DataTable({ rows, section }: { rows: any[]; section: Section }) {
  if (!rows.length) return <div className="ca-empty"><strong>No tenant records returned</strong><p>This view is correctly scoped to the authenticated tenant. No records currently require action.</p></div>;
  const keys = Object.keys(rows[0]).filter((key) => !["tenant_id", "id"].includes(key)).slice(0, 5);
  return <div className="ca-table-wrap"><table className="ca-table"><caption>{section} records — server-derived tenant scope</caption><thead><tr>{keys.map((key) => <th key={key}>{key.replace(/_/g, " ")}</th>)}<th>Status</th></tr></thead><tbody>{rows.slice(0, 30).map((row, index) => <tr key={String(row.id ?? row.code ?? index)}>{keys.map((key) => <td key={key}>{String(row[key] ?? "—")}</td>)}<td><Status value={statusOf(row)} /></td></tr>)}</tbody></table></div>;
}

function SpecializedRecords({ rows, section }: { rows: any[]; section: Section }) {
  if (!rows.length) return <DataTable rows={rows} section={section} />;
  const title = section === "Users" ? "People and access allocation" : section === "Roles & Access" ? "Authorization model" : section === "Integrations" ? "Connection health" : section === "Data Mapping" ? "Mapping readiness" : section === "Plans & Entitlements" ? "Commercial access boundary" : section === "Security" ? "Security posture" : section === "Audit" ? "Administrative evidence" : "Tenant configuration";
  const description = section === "Users" ? "Active, invited, and inactive identities belonging to this tenant." : section === "Roles & Access" ? "Personas, roles, permission sets, and effective access are evaluated server-side; deny wins." : section === "Integrations" ? "Tenant connector state is shown without exposing stored secrets." : section === "Data Mapping" ? "Customer mappings and overrides remain separate from platform master configuration." : section === "Plans & Entitlements" ? "Plan and entitlements are visible here; contractual limits cannot be changed by Customer Admin." : section === "Security" ? "MFA, SSO, sessions, and security events are constrained to this tenant." : section === "Audit" ? "Immutable tenant-scoped administrative events and configuration history." : "Server-authorized tenant configuration.";
  const actions = section === "Users" ? ["Deactivate", "Revoke sessions"] : section === "Roles & Access" ? ["Review effective access"] : section === "Integrations" ? ["Test connection", "Run sync"] : section === "Data Mapping" ? ["Preview mapping", "Activate mapping"] : section === "Plans & Entitlements" ? ["View subscription"] : section === "Audit" ? ["Export CSV", "Evidence package"] : [];
  return <><div className="ca-specialized-intro"><strong>{title}</strong><p>{description}</p></div><div className="ca-record-cards">{rows.slice(0, 30).map((row, index) => <article className="ca-record-card" key={String(row.id ?? row.code ?? index)}><div><strong>{String(row.display_name ?? row.name ?? row.code ?? row.action ?? row.email ?? "Tenant record")}</strong><Status value={statusOf(row)} /></div><p>{String(row.email ?? row.connector_type ?? row.entity_type ?? row.description ?? row.version ?? "Tenant-scoped record")}</p><small>{String(row.last_sync ?? row.created_at ?? row.tenant_id ?? "Server recorded")}</small>{actions.length > 0 && <div className="ca-record-actions">{actions.map((action) => <button key={action} className="secondary-link" type="button" onClick={() => { if (section === "Audit" && action === "Export CSV") window.open("/api/v1/admin/audit-history/export?output_format=CSV", "_blank"); else if (section === "Audit" && action === "Evidence package") window.open("/api/v1/admin/audit-history/evidence-package", "_blank"); else if (section === "Security" && action === "MFA") window.location.assign("/mfa?setup=1"); }}>{action}</button>)}</div>}</article>)}</div></>;
}

export function CustomerAdminControlPlane({ securityContext, products, investigations, onNavigate }: { securityContext: Context | null; products: any[]; investigations: any[]; onNavigate: (view: any) => void }) {
  const [section, setSection] = useState<Section>("Overview");
  const [item, setItem] = useState("Dashboard");
  const [data, setData] = useState<any>(null);
  const [dashboard, setDashboard] = useState<any>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [invite, setInvite] = useState({ firstName: "", lastName: "", email: "", company: "" });
  const [inviteMessage, setInviteMessage] = useState("");
  const currentNav = nav.find((entry) => entry.section === section) ?? nav[0];
  const rows = useMemo(() => rowsOf(data).filter((row) => JSON.stringify(row).toLowerCase().includes(query.toLowerCase())), [data, query]);

  const select = (next: Section, nextItem?: string) => { setSection(next); setItem(nextItem ?? nav.find((entry) => entry.section === next)?.items[0] ?? "Overview"); setQuery(""); };
  const submitInvite = async () => {
    setInviteMessage("");
    if (!invite.firstName || !invite.lastName || !invite.email || !invite.company) { setInviteMessage("First name, last name, email, and company are required."); return; }
    try {
      const response = await fetch("/api/v1/admin/identity/users", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: invite.email, display_name: `${invite.firstName} ${invite.lastName}`.trim(), company: invite.company, role: "USER" }) });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(payload?.detail?.message ?? payload?.detail ?? "Invitation could not be sent");
      setInvite({ firstName: "", lastName: "", email: "", company: "" });
      setInviteMessage(payload?.email_delivery === "SENT" ? "Invitation sent. The user will create their own password." : `Invitation created. Delivery status: ${payload?.email_delivery ?? "NOT_CONFIGURED"}.`);
      select("Users", "All Users");
    } catch (reason) { setInviteMessage(reason instanceof Error ? reason.message : "Invitation could not be sent"); }
  };

  useEffect(() => {
    const handler = (event: Event) => { const requested = String((event as CustomEvent).detail); if (nav.some((entry) => entry.section === requested)) select(requested as Section); };
    window.addEventListener("customer-admin-section", handler);
    return () => window.removeEventListener("customer-admin-section", handler);
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    getJson<any>(currentNav.endpoint).then((value) => { if (active) setData(value); }).catch((reason) => { if (active) { setData(null); setError(reason instanceof Error ? reason.message : "Unable to load tenant data"); } }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [currentNav.endpoint]);

  useEffect(() => { getJson<any>("/api/v1/admin/tenant-dashboard").then(setDashboard).catch(() => setDashboard(null)); }, []);

  const metrics = dashboard?.metrics ?? {};
  const health = dashboard?.health ?? {};
  const tenantName = securityContext?.current_tenant?.tenant_name ?? "Authenticated tenant";
  const activeUsers = metrics.active_users ?? rowsOf(data).filter((row) => String(row.status).toUpperCase() === "ACTIVE").length;
  const attention = health.alerts?.length ?? metrics.integration_issues ?? 0;

  return <div className="content customer-admin-page customer-admin-control-plane">
    <section className="ca-hero ca-hero-compact"><div className="ca-product-brand"><h1>MDARIX</h1><span>Customer administration</span><div className="ca-badges"><span>TENANT SCOPED</span><span>ROLE: {securityContext?.active_role ?? "CUSTOMER_ADMIN"}</span><span>ENVIRONMENT: {securityContext?.environment ?? "VALIDATION"}</span></div></div><div className="ca-context"><span className="eyebrow">Authenticated tenant</span><strong>{tenantName}</strong><code>{securityContext?.tenant_id ?? "Unavailable"}</code><Status value={securityContext?.current_tenant?.status ?? "ACTIVE"} /><small>Tenant context is server-derived and cannot be changed here.</small></div></section>
    <div className="ca-shell">
      <aside className="ca-sidebar" aria-label="Customer administration navigation"><div className="ca-sidebar-title">Administration</div>{nav.map((entry) => <button key={entry.section} className={section === entry.section ? "selected" : ""} onClick={() => select(entry.section)} aria-expanded={section === entry.section}><span>{entry.section}</span><small>{entry.items.length} controls</small><b>›</b></button>)}</aside>
      <main className="ca-main"><div className="ca-breadcrumb"><button onClick={() => select("Overview")}>Customer administration</button><span>›</span><strong>{section}</strong>{item !== currentNav.items[0] && <><span>›</span><strong>{item}</strong></>}</div><div className="ca-heading"><div><span className="eyebrow">{section}</span><h2>{item}</h2><p>All records and actions are limited to {tenantName}.</p></div>{section === "Users" && <button className="primary-action" onClick={() => select("Users", "Invite User")}>+ Invite user</button>}</div>
        {section !== "Overview" && <div className="ca-subnav" role="tablist">{currentNav.items.map((child) => <button key={child} className={item === child ? "active" : ""} onClick={() => setItem(child)} role="tab" aria-selected={item === child}>{child}</button>)}</div>}
        {section === "Overview" ? <><div className="ca-metrics"><Metric label="Active users" value={activeUsers} note="Tenant users" /><Metric label="Available seats" value={metrics.available_seats ?? "—"} note="Plan-controlled capacity" /><Metric label="Active connectors" value={metrics.active_connectors ?? (rowsOf(data).length || "—")} note="Configured connections" /><Metric label="Needs attention" value={attention} note="Review required" tone={attention ? "warning" : ""} /><Metric label="Investigations" value={metrics.investigations ?? investigations.length} note="Authorized records" /></div><div className="ca-dashboard-grid"><section className="ca-card"><div className="ca-card-head"><div><span className="eyebrow">Requires attention</span><h3>Administration queue</h3></div><Status value={attention ? "ATTENTION REQUIRED" : "HEALTHY"} /></div>{health.alerts?.length ? health.alerts.slice(0, 5).map((alert: any, index: number) => <button className="ca-alert-row" key={alert.code ?? index}><strong>{alert.label ?? alert.code ?? "Review required"}</strong><span>{alert.count ?? 1} · {alert.severity ?? "Review"} ›</span></button>) : <div className="ca-empty compact"><strong>No open administration alerts</strong><p>Tenant controls are currently within expected limits.</p></div>}</section><section className="ca-card"><div className="ca-card-head"><div><span className="eyebrow">Tenant boundary</span><h3>What this role can do</h3></div></div><ul className="ca-check-list"><li>Manage users, invitations, roles, and permissions</li><li>Configure tenant mappings and connections</li><li>Review entitlements, security, and audit history</li><li>Cannot access another tenant or platform controls</li></ul></section></div><section className="ca-card"><div className="ca-card-head"><div><span className="eyebrow">Recent administration</span><h3>Activity recorded for this tenant</h3></div><button className="secondary-link" onClick={() => select("Audit")}>View all audit</button></div><DataTable rows={rowsOf(dashboard?.recent_audit ?? dashboard?.audit)} section="Audit" /></section></> : <><div className="ca-toolbar"><input aria-label={`Search ${section}`} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${section.toLowerCase()}...`} /><span>{rows.length} result{rows.length === 1 ? "" : "s"}</span></div>{loading && <div className="ca-state">Loading server-authorized {section.toLowerCase()} data…</div>}{error && <div className="ca-error" role="alert">{error}</div>}{!loading && !error && item === "Invite User" ? <div className="ca-form-card"><h3>Invite a tenant user</h3><p>Send a secure activation invitation. Passwords are created by the invited user and are never entered or displayed by Customer Admin.</p><div className="ca-form-grid"><label>First name<input value={invite.firstName} onChange={(event) => setInvite({ ...invite, firstName: event.target.value })} placeholder="First name" /></label><label>Last name<input value={invite.lastName} onChange={(event) => setInvite({ ...invite, lastName: event.target.value })} placeholder="Last name" /></label><label>Email<input type="email" value={invite.email} onChange={(event) => setInvite({ ...invite, email: event.target.value })} placeholder="user@company.com" /></label><label>Company<input value={invite.company} onChange={(event) => setInvite({ ...invite, company: event.target.value })} placeholder="Company" /></label></div><button className="primary-action" onClick={() => void submitInvite()}>Send invitation</button>{inviteMessage && <p className="ca-state" role="status">{inviteMessage}</p>}</div> : !loading && !error && <div className="ca-card"><div className="ca-card-head"><div><span className="eyebrow">{item}</span><h3>Tenant-scoped records</h3></div><Status value="SERVER AUTHORIZED" /></div><SpecializedRecords rows={rows} section={section} /></div>}</>}
      </main>
    </div>
    <section className="ca-journey"><span className="eyebrow">Customer investigation journey</span><div><strong>Product context</strong><i>→</i><strong>Signals</strong><i>→</i><strong>Evidence</strong><i>→</i><strong>Human decision</strong></div><p>Administration permissions do not grant business-record access. Business roles must be assigned explicitly.</p></section>
  </div>;
}
