import { useState } from "react";
import { Download, Upload } from "lucide-react";
import { Panel } from "../console/charts";
import { SearchBox, Table, useResource } from "../../customer-admin/shared";
import { CustomerImportDialog } from "./CustomerImportDialog";
import type { CustomerAccount } from "./model";
import { StatusBadge } from "./StatusBadge";

/**
 * Every customer once, with the tenants it owns. A customer is the legal and commercial parent; each tenant is a
 * separate workspace and data boundary with its own plan and administrators. Opening a row shows the customer.
 */
export function CustomerDirectory({ onOpen }: { onOpen: (customerId: string) => void }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [plan, setPlan] = useState("");
  const [page, setPage] = useState(1);
  const [importing, setImporting] = useState(false);
  const params = new URLSearchParams({ page: String(page) });
  if (query.trim()) params.set("q", query.trim());
  if (status) params.set("status", status);
  if (plan.trim()) params.set("plan", plan.trim());
  const customers = useResource<{ items: CustomerAccount[]; total: number; pages: number }>(
    `/api/v1/platform-admin/customer-accounts?${params}`,
  );
  const plans = useResource<any[]>("/api/v1/platform-admin/plans");
  // The export keeps its established shape: one row per tenant, with the owning customer on each row.
  const exportParams = new URLSearchParams({ format: "csv", page: "1", page_size: "100", sort: "name" });
  if (query.trim()) exportParams.set("q", query.trim());
  if (plan.trim()) exportParams.set("plan", plan.trim());
  const reset = (apply: () => void) => {
    apply();
    setPage(1);
  };
  const total = customers.data?.total ?? 0;
  const pages = customers.data?.pages ?? 1;
  return (
    <Panel
      eyebrow="Customers"
      title="Customer directory"
      state={customers.state}
      error={customers.error}
      action={
        <span className="cc-actions">
          <a
            className="ac-secondary"
            href={`/api/v1/platform-admin/customers?${exportParams}`}
            title="One row per tenant, with its customer"
          >
            <Download size={16} aria-hidden="true" /> Export CSV
          </a>
          <button type="button" className="ac-secondary" onClick={() => setImporting(true)}>
            <Upload size={16} aria-hidden="true" /> Import CSV
          </button>
        </span>
      }
    >
      <div className="cc-toolbar">
        <SearchBox
          value={query}
          onChange={(value) => reset(() => setQuery(value))}
          label="Search customer, ID or tenant"
        />
        <select aria-label="Status" value={status} onChange={(event) => reset(() => setStatus(event.target.value))}>
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="SUSPENDED">Suspended</option>
          <option value="PROVISIONED">Provisioned</option>
          <option value="EXPIRED">Expired</option>
        </select>
        <select aria-label="Plan" value={plan} onChange={(event) => reset(() => setPlan(event.target.value))}>
          <option value="">All plans</option>
          {(Array.isArray(plans.data) ? plans.data : []).map((item) => (
            <option key={item.code} value={item.code}>
              {item.name ?? item.code}
            </option>
          ))}
        </select>
      </div>
      <Table
        caption="Customers"
        rows={customers.data?.items ?? []}
        rowKey={(row) => row.id}
        empty={{ title: "No matching customers", detail: "Change the search or filters, or onboard a new customer." }}
        columns={[
          {
            key: "customer",
            label: "Customer",
            render: (row) => (
              <button type="button" className="ac-link cc-stack" onClick={() => onOpen(row.id)}>
                <strong>{row.name || "Unnamed customer"}</strong>
                <small>{row.customer_identifier}</small>
              </button>
            ),
          },
          {
            key: "tenants",
            label: "Tenants",
            render: (row) =>
              row.tenants.length ? (
                <span className="cc-tenant-list">
                  {row.tenants.map((tenant) => (
                    <span key={tenant.id} className="cc-stack">
                      <strong>{tenant.display_name ?? tenant.tenant_key}</strong>
                      <small>
                        {[tenant.tenant_key, tenant.plan_name, tenant.data_region].filter(Boolean).join(" · ")}
                      </small>
                    </span>
                  ))}
                </span>
              ) : (
                <span className="ac-muted">No tenant yet</span>
              ),
          },
          { key: "admins", label: "Active administrators", numeric: true, render: (row) => row.active_admins },
          { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
          {
            key: "open",
            label: "",
            render: (row) => (
              <button type="button" className="ac-link" onClick={() => onOpen(row.id)}>
                Open
              </button>
            ),
          },
        ]}
      />
      <div className="cc-pager">
        <span>
          {total} customer{total === 1 ? "" : "s"}
        </span>
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
      {importing && (
        <CustomerImportDialog
          onClose={() => setImporting(false)}
          onImported={() => {
            setImporting(false);
            customers.reload();
          }}
        />
      )}
    </Panel>
  );
}
