import { CheckCircle2, Download, RefreshCw, XCircle } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { useConsole } from "../context";
import { Table, formatDate, idColumn, listOf, send, useResource } from "../shared";
import { LifecycleBadge } from "./Access";
import { hideUuid } from "../../../app/displayId";
import { readable } from "../labels";
import { EmailIntakePanel } from "./EmailIntake";

type DataExport = {
  id: string;
  status: string;
  reason: string;
  size_bytes: number | null;
  summary: { tables: number; rows: number; files: number } | null;
  created_at: string;
  expires_at: string | null;
  yours?: boolean; // only the person who asked for it downloads it (RSK-036)
};

/** A complete copy of everything the organization stored, prepared in the background, downloadable for 7 days. */
function DataExports() {
  const { confirm } = useConsole();
  const exports = useResource<{ exports: DataExport[] }>("/api/v1/admin/exports");
  const rows = exports.data?.exports ?? [];
  const busy = rows.some((row) => row.status === "QUEUED" || row.status === "RUNNING");
  return (
    <Panel
      eyebrow="Your data"
      title="Export all your data"
      source={exports}
      action={
        <span className="ca-row-actions">
          <button type="button" className="ac-secondary" onClick={() => exports.reload()}>
            <RefreshCw size={15} aria-hidden="true" /> Refresh
          </button>
          <button
            type="button"
            className="ac-primary"
            disabled={busy}
            onClick={() =>
              confirm({
                title: "Prepare a full export?",
                body: "Every record, the audit trail and every file your organization stored are collected into one zip file. Passwords and secrets are never included. It is ready in a few minutes and can be downloaded for 7 days.",
                confirmLabel: "Prepare export",
                reason: { label: "Why is the export needed?", min: 10 },
                mfaCode: true,
                done: "The export is being prepared. Refresh in a few minutes.",
                run: async (reason, _password, _acknowledged, mfaCode) => {
                  await send("/api/v1/admin/exports", "POST", { reason, ...(mfaCode ? { mfa_code: mfaCode } : {}) });
                  exports.reload();
                },
              })
            }
          >
            {busy ? "Export in progress…" : "Prepare export"}
          </button>
        </span>
      }
    >
      <p className="ac-muted">
        One zip file with all your records, your stored files and a list of what is inside, so you can check that
        nothing is missing. Each download is recorded in the audit trail.
      </p>
      <Table
        caption="Data exports"
        rows={rows}
        rowKey={(row) => row.id}
        empty={{
          title: "No exports yet",
          detail: "Prepare an export to download everything your organization stored.",
        }}
        columns={[
          idColumn("Export ID"),
          { key: "requested", label: "Requested", render: (row) => formatDate(row.created_at) },
          { key: "status", label: "Status", render: (row) => readable(row.status) },
          {
            key: "contents",
            label: "Contents",
            render: (row) =>
              row.summary
                ? `${row.summary.rows.toLocaleString()} records · ${row.summary.files.toLocaleString()} files`
                : "—",
          },
          {
            key: "expires",
            label: "Available until",
            render: (row) => (row.expires_at ? formatDate(row.expires_at) : "—"),
          },
          {
            key: "download",
            label: "Download",
            render: (row) =>
              row.status === "READY" && row.yours === false ? (
                "Only whoever asked for it"
              ) : row.status === "READY" ? (
                <a className="ac-link" href={`/api/v1/admin/exports/${row.id}/download`} download>
                  <Download size={14} aria-hidden="true" /> Download zip
                </a>
              ) : (
                "—"
              ),
          },
        ]}
      />
    </Panel>
  );
}

export function OrganizationSection() {
  const { context } = useConsole();
  const products = useResource<any[]>("/api/v1/admin/catalog/products");
  return (
    <>
      <div className="ac-grid two">
        <Panel eyebrow="Organization" title={context?.current_tenant?.tenant_name ?? "Your organization"}>
          <dl className="ca-facts">
            <div>
              <dt>Organization ID</dt>
              <dd>{hideUuid(context?.tenant_business_id ?? context?.current_tenant?.tenant_business_id)}</dd>
            </div>
            <div>
              <dt>Environment</dt>
              <dd>{readable(context?.environment)}</dd>
            </div>
            <div>
              <dt>Plan</dt>
              <dd>{context?.plan?.name ?? "—"}</dd>
            </div>
          </dl>
          <p className="ac-muted">
            Company details and where your data is stored are set by MDARIX when your organization is set up. Contact
            your MDARIX account team to change them.
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
              "Turn AI processing on or off, and set reminders and contacts",
              "Work in the investigation workspace with an Investigator's rights",
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
      <Panel eyebrow="Organization" title="Products" source={products}>
        <Table
          caption="Products"
          rows={listOf(products.data)}
          rowKey={(row) => row.id}
          empty={{
            title: "No products yet",
            detail: "Products appear once your product data is imported or connected under Integrations.",
          }}
          columns={[
            idColumn("Product ID", "product_identifier"),
            {
              key: "name",
              label: "Product",
              fields: ["name"],
              render: (row) => <strong>{row.name}</strong>,
            },
            { key: "family", label: "Family", render: (row) => row.product_family ?? "—" },
            { key: "versions", label: "Versions", numeric: true, render: (row) => row.version_count ?? 0 },
            { key: "status", label: "Status", render: (row) => <LifecycleBadge status={row.lifecycle_status} /> },
          ]}
        />
      </Panel>
      {context?.email_intake && <EmailIntakePanel />}
      <DataExports />
    </>
  );
}
