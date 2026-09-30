import { useEffect, useState } from "react";
import { AppView } from "../../app/router";
import { api } from "../../app/api";
import { AdminTenant } from "../../app/types";

export function PlatformCustomers({ onNavigate }: { onNavigate: (view: AppView) => void }) {
  const [rows, setRows] = useState<AdminTenant[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  useEffect(() => {
    api<AdminTenant[]>("/api/v1/platform-admin/customers")
      .then(setRows)
      .catch((e) => setError(e.message));
  }, []);
  const filtered = rows.filter(
    (row) =>
      `${row.name} ${row.tenant_key} ${row.status}`.toLowerCase().includes(query.toLowerCase()) &&
      (status === "ALL" || row.status.toUpperCase() === status),
  );
  const pageSize = 10;
  const visible = filtered.slice((page - 1) * pageSize, page * pageSize);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const open360 = (id: string) => {
    window.history.pushState({}, "", `/app/admin/customers/detail?tenant_id=${encodeURIComponent(id)}`);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };
  return (
    <div className="content governance-view">
      <section className="governance-hero">
        <div>
          <span className="eyebrow">Customers</span>
          <h2>Customers / Tenants</h2>
          <p>Search, filter, paginate, and review tenant metadata without exposing regulated business records.</p>
        </div>
        <button className="primary-action" onClick={() => onNavigate("admin-create-customer")}>
          Create customer
        </button>
      </section>
      <section className="panel">
        <div className="toolbar">
          <input
            aria-label="Search customers"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Search company, tenant code, or status"
          />
          <select
            aria-label="Filter customer status"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="ALL">All statuses</option>
            <option value="ACTIVE">Active</option>
            <option value="SUSPENDED">Suspended</option>
            <option value="PENDING">Pending</option>
          </select>
        </div>
        {error && <p className="field-error">{error}</p>}
        <div className="audit-row">
          <strong>Company</strong>
          <span>Tenant code</span>
          <small>Status</small>
        </div>
        {visible.map((row) => (
          <div className="audit-row" key={row.id}>
            <strong>{row.name}</strong>
            <span>{row.tenant_key}</span>
            <small>
              {row.status}{" "}
              <button className="secondary-link" onClick={() => open360(row.id)}>
                Customer 360
              </button>
            </small>
          </div>
        ))}
        {!visible.length && !error && <p>No customers match the selected filters.</p>}
        <div className="toolbar">
          <small>{filtered.length} customer(s)</small>
          <span>
            <button className="secondary-link" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>{" "}
            <span>
              Page {page} of {pageCount}
            </span>{" "}
            <button className="secondary-link" disabled={page >= pageCount} onClick={() => setPage(page + 1)}>
              Next
            </button>
          </span>
        </div>
      </section>
    </div>
  );
}
