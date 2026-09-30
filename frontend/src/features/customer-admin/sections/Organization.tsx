import { CheckCircle2, XCircle } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { useConsole } from "../context";
import { Table, listOf, useResource } from "../shared";
import { LifecycleBadge } from "./Access";

export function OrganizationSection() {
  const { context } = useConsole();
  const products = useResource<any[]>("/api/v1/admin/catalog/products");
  return (
    <>
      <div className="ac-grid two">
        <Panel eyebrow="Organization" title={context?.current_tenant?.tenant_name ?? "Your organization"}>
          <dl className="ca-facts">
            <div>
              <dt>Tenant key</dt>
              <dd>{context?.current_tenant?.tenant_key ?? "—"}</dd>
            </div>
            <div>
              <dt>Tenant ID</dt>
              <dd className="ca-mono-sm">{context?.tenant_id ?? "—"}</dd>
            </div>
            <div>
              <dt>Environment</dt>
              <dd>{titleCase(context?.environment ?? "—")}</dd>
            </div>
            <div>
              <dt>Plan</dt>
              <dd>{context?.plan?.name ?? "—"}</dd>
            </div>
          </dl>
          <p className="ac-muted">
            Company details, data residency and region are set when MDARIX provisions your organization. Contact your
            account team to change them.
          </p>
        </Panel>
        <Panel eyebrow="Your account" title={context?.display_name ?? "Administrator"}>
          <dl className="ca-facts">
            <div>
              <dt>Email</dt>
              <dd>{context?.email ?? "—"}</dd>
            </div>
            <div>
              <dt>Role</dt>
              <dd>Customer Administrator</dd>
            </div>
          </dl>
          <h3 className="ca-subhead">What this role can do</h3>
          <ul className="ca-boundary">
            {[
              "Invite, suspend, restore and offboard users",
              "Create roles and permission sets and assign them",
              "Configure connections, mappings and their releases",
              "Set single sign-on, reminders and contacts",
              "Review and export the audit trail",
            ].map((item) => (
              <li key={item}>
                <CheckCircle2 size={15} className="ac-tone-icon tone-good" aria-hidden="true" /> {item}
              </li>
            ))}
            {[
              "See or change another organization",
              "Grant MDARIX platform roles",
              "Change plan limits or contract terms",
              "Read business records without a business role",
            ].map((item) => (
              <li key={item}>
                <XCircle size={15} className="ac-tone-icon tone-critical" aria-hidden="true" /> Cannot: {item}
              </li>
            ))}
          </ul>
        </Panel>
      </div>
      <Panel eyebrow="Organization" title="Products" state={products.state} error={products.error}>
        <Table
          caption="Products"
          rows={listOf(products.data)}
          rowKey={(row) => row.id}
          empty={{ title: "No products yet", detail: "Products appear once your product data is connected." }}
          columns={[
            {
              key: "name",
              label: "Product",
              render: (row) => (
                <span className="ca-person">
                  <strong>{row.name}</strong>
                  <small>{row.product_identifier}</small>
                </span>
              ),
            },
            { key: "family", label: "Family", render: (row) => row.product_family ?? "—" },
            { key: "versions", label: "Versions", numeric: true, render: (row) => row.version_count ?? 0 },
            { key: "status", label: "Lifecycle", render: (row) => <LifecycleBadge status={row.lifecycle_status} /> },
          ]}
        />
      </Panel>
    </>
  );
}
