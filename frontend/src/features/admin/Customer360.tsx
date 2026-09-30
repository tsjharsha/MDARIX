import { useEffect, useState } from "react";
import { api } from "../../app/api";

export function Customer360() {
  const [record, setRecord] = useState<any>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("Overview");
  const [detail, setDetail] = useState<any>(null);
  const tabs = [
    "Overview",
    "Administrators",
    "Users",
    "Plan",
    "Entitlements",
    "Integrations",
    "Security",
    "Usage",
    "Audit",
  ];
  useEffect(() => {
    const tenantId = new URLSearchParams(window.location.search).get("tenant_id");
    if (!tenantId) {
      setError("Select a customer from Customers / Tenants first.");
      return;
    }
    api<any>(`/api/v1/platform-admin/customers/${tenantId}`)
      .then(setRecord)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!record) return;
    const tenantId = record.id;
    const endpoint =
      tab === "Plan" || tab === "Entitlements"
        ? `/api/v1/platform-admin/customers/${tenantId}/subscription`
        : tab === "Usage"
          ? `/api/v1/platform-admin/customers/${tenantId}/usage`
          : tab === "Integrations"
            ? "/api/v1/admin/configuration/connectors"
            : tab === "Audit"
              ? "/api/v1/admin/audit-history"
              : tab === "Administrators" || tab === "Users"
                ? "/api/v1/admin/identity/users"
                : null;
    if (!endpoint) {
      setDetail(null);
      return;
    }
    api<any>(endpoint)
      .then(setDetail)
      .catch((e) => setDetail({ error: e.message }));
  }, [record, tab]);
  const values: Record<string, any> = {
    Overview: record
      ? [
          ["Status", record.status],
          ["Tenant ID", record.tenant_key],
          ["Plan", record.plan_id ?? "Not assigned"],
          ["Audit events", record.counts.audit_events],
        ]
      : [],
    Administrators: [["Customer administrators", record?.counts?.administrators ?? 0]],
    Users: [["Users", record?.counts?.users ?? 0]],
    Plan: [
      ["Subscription", detail?.status ?? record?.plan_id ?? "Not assigned"],
      ["Plan version", detail?.plan_version ?? "Not available"],
    ],
    Entitlements: [
      ["Licensed users", detail?.usage?.licensed_users ?? detail?.licensed_users ?? "Not available"],
      ["Seat cap", detail?.limits?.licensed_users_limit ?? "Not available"],
    ],
    Integrations: [["Configured connectors", record?.counts?.connectors ?? 0]],
    Security: [
      ["Boundary", "Tenant-scoped"],
      ["Access", "Server-authorized"],
    ],
    Usage: [
      ["Licensed users", detail?.licensed_users ?? record?.counts?.users ?? 0],
      ["Connectors", detail?.connectors ?? record?.counts?.connectors ?? 0],
    ],
    Audit: [["Audit events", record?.counts?.audit_events ?? 0]],
  };
  return (
    <div className="content governance-view customer-record-page">
      <section className="governance-hero">
        <div>
          <span className="eyebrow">Customer record</span>
          <h2>{record?.name ?? "Customer 360"}</h2>
          <p>
            Tenant {record?.tenant_key ?? "metadata"}. Platform administration is server-authorized and business content
            remains tenant-scoped.
          </p>
        </div>
        <span className="version-pill">{record?.status ?? "Loading"}</span>
      </section>
      {error && <section className="panel field-error">{error}</section>}
      {record && (
        <>
          <nav className="record-tabs" aria-label="Customer record tabs">
            {tabs.map((item) => (
              <button className={tab === item ? "selected" : ""} key={item} onClick={() => setTab(item)}>
                {item}
              </button>
            ))}
          </nav>
          <section className="record-detail-layout">
            <article className="panel">
              <span className="eyebrow">{tab}</span>
              <h3>{tab === "Overview" ? "Customer overview" : `${tab} detail`}</h3>
              <div className="record-field-grid">
                {(values[tab] ?? []).map(([label, value]: [string, any]) => (
                  <div key={label}>
                    <small>{label}</small>
                    <strong>{String(value)}</strong>
                  </div>
                ))}
              </div>
              {detail?.error && (
                <p className="field-error" role="alert">
                  {detail.error}
                </p>
              )}
              <p className="record-scope-note">
                Server-derived detail. No tenant identifier supplied by the browser is used as authorization.
              </p>
            </article>
            <aside className="panel">
              <div className="section-title">Related records</div>
              <p>
                Use the tabs to inspect administrators, users, plan, entitlements, integrations, security, usage, and
                audit evidence.
              </p>
              <button className="secondary-link" onClick={() => setTab("Audit")}>
                Open audit history
              </button>
            </aside>
          </section>
        </>
      )}
    </div>
  );
}
