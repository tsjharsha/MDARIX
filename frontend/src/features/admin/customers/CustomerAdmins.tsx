import { useState } from "react";
import { KeyRound, MailPlus, PauseCircle, PlayCircle, UserPlus } from "lucide-react";
import { Panel } from "../console/charts";
import {
  ConfirmDialog,
  SearchBox,
  Table,
  errorText,
  send,
  useResource,
  type Confirmation,
} from "../../customer-admin/shared";
import type { CustomerAdmin, TenantSummary } from "./model";
import { StatusBadge } from "./StatusBadge";

const REASON = { label: "Reason (kept in the audit trail)", min: 5 };

/**
 * Customer Administrators, for one customer (inside its page) or for every customer (own tab).
 * The platform administrator can add one, resend an invitation, send a password reset, and suspend or
 * reactivate one. The last active administrator of a customer cannot be suspended (the server enforces it too).
 */
export function CustomerAdmins({
  customerId,
  tenants,
  onMessage,
}: {
  customerId?: string;
  tenants?: TenantSummary[];
  onMessage: (text: string, tone?: "good" | "critical") => void;
}) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const params = new URLSearchParams();
  if (customerId) params.set("customer_id", customerId);
  if (query.trim()) params.set("q", query.trim());
  if (status) params.set("status", status);
  const admins = useResource<{ items: CustomerAdmin[] }>(`/api/v1/platform-admin/customer-admins?${params}`);
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [adding, setAdding] = useState(false);
  const rows = admins.data?.items ?? [];
  const base = (row: CustomerAdmin) => `/api/v1/platform-admin/customer-admins/${row.id}`;
  const name = (row: CustomerAdmin) => row.display_name || row.email;

  const actions = (row: CustomerAdmin) => (
    <span className="cc-actions">
      {row.can_resend_invitation && (
        <button
          type="button"
          className="ac-link"
          onClick={() =>
            setConfirm({
              title: `Resend the invitation to ${name(row)}?`,
              body: `A new activation link is emailed to ${row.email}. Earlier links stop working.`,
              confirmLabel: "Resend invitation",
              reason: REASON,
              run: (reason) => send(`${base(row)}/resend-invitation`, "POST", { reason }),
              done: `Invitation resent to ${row.email}.`,
            })
          }
        >
          <MailPlus size={14} aria-hidden="true" /> Resend invitation
        </button>
      )}
      {row.can_reset_password && (
        <button
          type="button"
          className="ac-link"
          onClick={() =>
            setConfirm({
              title: `Send a password reset to ${name(row)}?`,
              body: `A single-use reset link is emailed to ${row.email}. Their current password works until they use it.`,
              confirmLabel: "Send reset link",
              reason: REASON,
              run: (reason) => send(`${base(row)}/password-reset`, "POST", { reason }),
              done: `Password reset link sent to ${row.email}.`,
            })
          }
        >
          <KeyRound size={14} aria-hidden="true" /> Reset password
        </button>
      )}
      {row.can_suspend && (
        <button
          type="button"
          className="ac-link cc-danger-link"
          onClick={() =>
            setConfirm({
              title: `Suspend ${name(row)}?`,
              body: "They are signed out everywhere and cannot sign in until reactivated. The customer's other administrators are not affected.",
              confirmLabel: "Suspend administrator",
              danger: true,
              reason: REASON,
              run: (reason) => send(`${base(row)}/status`, "POST", { status: "SUSPENDED", reason }),
              done: `${name(row)} is suspended.`,
            })
          }
        >
          <PauseCircle size={14} aria-hidden="true" /> Suspend
        </button>
      )}
      {row.is_last_active_admin && (
        <small className="ac-muted" title="Add or replace an administrator first, or suspend the whole customer.">
          Only active administrator
        </small>
      )}
      {row.can_reactivate && (
        <button
          type="button"
          className="ac-link"
          onClick={() =>
            setConfirm({
              title: `Reactivate ${name(row)}?`,
              body: "They can sign in again with their existing password.",
              confirmLabel: "Reactivate",
              reason: REASON,
              run: (reason) => send(`${base(row)}/status`, "POST", { status: "ACTIVE", reason }),
              done: `${name(row)} is active again.`,
            })
          }
        >
          <PlayCircle size={14} aria-hidden="true" /> Reactivate
        </button>
      )}
    </span>
  );

  return (
    <Panel
      eyebrow={customerId ? "This customer" : "All customers"}
      title="Customer administrators"
      state={admins.state}
      error={admins.error}
      action={
        <button type="button" className="ac-primary" onClick={() => setAdding(true)}>
          <UserPlus size={16} aria-hidden="true" /> Add administrator
        </button>
      }
    >
      <div className="cc-toolbar">
        <SearchBox value={query} onChange={setQuery} label="Search name, email or customer" />
        <select aria-label="Administrator status" value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="INVITED">Invited</option>
          <option value="SUSPENDED">Suspended</option>
        </select>
      </div>
      <Table
        caption="Customer administrators"
        rows={rows}
        rowKey={(row) => row.id}
        empty={{
          title: "No customer administrators",
          detail: customerId ? "Add the first administrator for this customer." : "No administrator matches.",
        }}
        columns={[
          {
            key: "name",
            label: "Administrator",
            render: (row) => (
              <span className="cc-stack">
                <strong>{name(row)}</strong>
                <small>{row.email}</small>
              </span>
            ),
          },
          ...(customerId
            ? []
            : [
                {
                  key: "customer",
                  label: "Customer",
                  render: (row: CustomerAdmin) => (
                    <span className="cc-stack">
                      <strong>{row.customer_name ?? "—"}</strong>
                      <small>{row.tenant_key}</small>
                    </span>
                  ),
                },
              ]),
          { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
          { key: "actions", label: "Actions", render: actions },
        ]}
      />
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(message) => {
          setConfirm(null);
          onMessage(message);
          admins.reload();
        }}
      />
      {adding && (
        <AddAdministrator
          tenants={tenants}
          onClose={() => setAdding(false)}
          onAdded={(message) => {
            setAdding(false);
            onMessage(message);
            admins.reload();
          }}
        />
      )}
    </Panel>
  );
}

function AddAdministrator({
  tenants,
  onClose,
  onAdded,
}: {
  tenants?: TenantSummary[];
  onClose: () => void;
  onAdded: (message: string) => void;
}) {
  // Inside a customer's page its tenants are known; on the all-customers tab, every active tenant can be chosen.
  const all = useResource<{ items: TenantSummary[] }>(tenants ? null : "/api/v1/platform-admin/customer-admin-tenants");
  const options: TenantSummary[] = tenants ?? all.data?.items ?? [];
  const loadingOptions = !tenants && all.state === "loading";
  const [form, setForm] = useState({ tenant_id: "", email: "", display_name: "", reason: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const tenantId = form.tenant_id || options[0]?.id || "";
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await send<any>(`/api/v1/platform-admin/tenants/${tenantId}/customer-admins`, "POST", {
        email: form.email.trim(),
        display_name: form.display_name.trim(),
        reason: form.reason.trim(),
      });
      onAdded(
        result.email_delivery === "NOT_CONFIGURED"
          ? `${result.email} added. Email is not configured here, so no invitation was delivered.`
          : `${result.email} added and invited by email.`,
      );
    } catch (reason) {
      setError(errorText(reason, "The administrator was not added."));
      setBusy(false);
    }
  };
  return (
    <div className="ac-modal-backdrop" role="presentation" onKeyDown={(event) => event.key === "Escape" && onClose()}>
      <form className="ac-modal" role="dialog" aria-modal="true" aria-labelledby="cc-add-admin" onSubmit={submit}>
        <p className="ac-eyebrow">Customer administrators</p>
        <h2 id="cc-add-admin">Add administrator</h2>
        <p>They receive an email to set their password and can then manage their organization's users.</p>
        {!tenants && all.state === "error" && (
          <p className="ca-inline-error" role="alert">
            The customer list could not be loaded: {all.error ?? "please try again"}.
          </p>
        )}
        {options.length > 1 || !tenants ? (
          <label className="ca-field">
            Customer
            <select
              required
              value={tenantId}
              disabled={loadingOptions}
              onChange={(event) => setForm({ ...form, tenant_id: event.target.value })}
            >
              {loadingOptions && <option value="">Loading customers…</option>}
              {options.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.display_name ?? tenant.tenant_key} {tenant.tenant_key ? `(${tenant.tenant_key})` : ""}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="ca-field">
          Full name
          <input
            required
            value={form.display_name}
            onChange={(event) => setForm({ ...form, display_name: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Work email
          <input
            required
            type="email"
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Reason (kept in the audit trail)
          <input
            required
            minLength={5}
            value={form.reason}
            onChange={(event) => setForm({ ...form, reason: event.target.value })}
            placeholder="e.g. Second administrator requested by the customer"
          />
        </label>
        {error && (
          <p className="ca-inline-error" role="alert">
            {error}
          </p>
        )}
        <div className="ac-modal-actions">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy || !tenantId}>
            {busy ? "Adding…" : "Add and invite"}
          </button>
        </div>
      </form>
    </div>
  );
}
