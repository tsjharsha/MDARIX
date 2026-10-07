import { useRef, useState } from "react";
import { ArrowLeft, Ban, CreditCard, PauseCircle, Pencil, PlayCircle, Plus } from "lucide-react";
import { Panel } from "../console/charts";
import {
  ConfirmDialog,
  Table,
  Tabs,
  errorText,
  formatDate,
  idColumn,
  send,
  useResource,
  type Confirmation,
} from "../../customer-admin/shared";
import { displayId } from "../../../app/displayId";
import { AddTenant } from "./AddTenant";
import { CustomerAdmins } from "./CustomerAdmins";
import { EditDetails } from "./EditDetails";
import {
  CUSTOMER_FIELD_GROUPS,
  REASON_MIN,
  blockedByCustomer,
  changeErrorText,
  customerGivesAccess,
  customerStatusResult,
  isoDate,
  lifecycleStatusLabel,
  presentGroups,
  customerStatusAction,
  tenantsLosingAccess,
  titleCase,
  type Plan,
  type TenantAffected,
  type TenantSummary,
} from "./model";
import { StatusBadge } from "./StatusBadge";
import { DialogBehaviour } from "../../shared/DialogBehaviour";

const SECTIONS = ["Overview", "Administrators", "Subscription", "Usage", "Activity"] as const;
type Section = (typeof SECTIONS)[number];

type Record = {
  customer: { [key: string]: any; id: string; lifecycle_status?: string; lock_version?: number | null };
  tenants: Array<TenantSummary & { [key: string]: any; effective_access?: string | null }>;
};

/**
 * One customer (the legal and commercial parent) and the tenants it owns: its details (maintained by MDARIX
 * platform administrators), status, tenants, administrators, subscription, usage and activity. Administrators,
 * plans and usage belong to a tenant, so each is shown with its tenant. A customer's status gates its tenants: while
 * it is inactive nobody can sign in to any of them, but each tenant keeps its own status.
 */
export function CustomerPage({
  customerId,
  onBack,
  onOpenTenant,
  onMessage,
}: {
  customerId: string;
  onBack: () => void;
  onOpenTenant: (tenantId: string) => void;
  onMessage: (text: string, tone?: "good" | "critical") => void;
}) {
  const record = useResource<Record>(`/api/v1/platform-admin/customer-records/${customerId}`);
  const [section, setSection] = useState<Section>("Overview");
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [addingTenant, setAddingTenant] = useState(false);
  const [editing, setEditing] = useState(false);
  // The result of the latest status change, naming the tenants it reached (read when the dialog reports done).
  const outcome = useRef<string | null>(null);
  const customer = record.data?.customer;
  const tenants = record.data?.tenants ?? [];
  const name = customer?.display_name ?? customer?.legal_name ?? "Customer";
  const status = customer?.lifecycle_status;
  const action = customerStatusAction(status, customer?.is_operator);
  const canAddTenant = customerGivesAccess(status);

  const changeStatus = () => {
    if (!action) return;
    const count = tenantsLosingAccess(tenants);
    const body =
      action.verb === "Deactivate"
        ? `Nobody can sign in to its ${count} tenant${count === 1 ? "" : "s"} while it is inactive. Each tenant keeps its own status, and is restored when the customer is reactivated. Data is kept.`
        : action.verb === "Reactivate"
          ? `People can sign in again to the tenants of ${name} that are themselves active. Inactive tenants stay inactive.`
          : `${name} becomes active. Each of its tenants can be used once the tenant itself is active.`;
    outcome.current = null;
    setConfirm({
      title: `${action.verb} ${name}?`,
      body,
      confirmLabel: `${action.verb} customer`,
      danger: action.verb === "Deactivate",
      reason: { label: "Reason (kept in the audit trail)", min: REASON_MIN },
      password: true,
      run: async (reason, password) => {
        try {
          const response = await send<{ tenants_affected?: TenantAffected[] }>(
            `/api/v1/platform-admin/customer-records/${customerId}/lifecycle`,
            "POST",
            { status: action.target, reason, password, lock_version: customer?.lock_version },
          );
          outcome.current = customerStatusResult(name, action.verb, response?.tenants_affected ?? []);
        } catch (error) {
          // A wrong password keeps the server's own words; conflicts and protected organizations are explained.
          throw new Error(changeErrorText(error, "customer", "The status was not changed."));
        }
      },
      done: customerStatusResult(name, action.verb),
    });
  };

  return (
    <div className="cc-page">
      <div className="cc-page-head">
        <button type="button" className="ac-link" onClick={onBack}>
          <ArrowLeft size={16} aria-hidden="true" /> All customers
        </button>
        <div className="cc-title">
          <div>
            <p className="ac-eyebrow">Customer · {customer ? displayId(customer, "customer_identifier") : "…"}</p>
            <h2>{name}</h2>
          </div>
          <span className="cc-actions">
            <StatusBadge status={status} label={lifecycleStatusLabel(status)} />
            {customer && (
              <button type="button" className="ac-secondary" onClick={() => setEditing(true)}>
                <Pencil size={16} aria-hidden="true" /> Edit details
              </button>
            )}
            {customer && action && (
              <button
                type="button"
                className={action.verb === "Deactivate" ? "ca-danger" : "ac-primary"}
                onClick={changeStatus}
              >
                {action.verb === "Deactivate" ? (
                  <PauseCircle size={16} aria-hidden="true" />
                ) : (
                  <PlayCircle size={16} aria-hidden="true" />
                )}{" "}
                {action.verb} customer
              </button>
            )}
          </span>
        </div>
      </div>
      {record.state === "error" && (
        <p className="ca-inline-error" role="alert">
          {record.error ?? "The customer could not be loaded."}
        </p>
      )}
      <Tabs tabs={SECTIONS} active={section} onChange={setSection} label="Customer sections">
        {customer && section === "Overview" && (
          <Overview
            customer={customer}
            tenants={tenants}
            onOpenTenant={onOpenTenant}
            onAddTenant={canAddTenant ? () => setAddingTenant(true) : undefined}
          />
        )}
        {customer && section === "Administrators" && (
          <CustomerAdmins customerId={customerId} tenants={tenants} onMessage={onMessage} />
        )}
        {customer && section === "Subscription" && (
          <Subscription customerId={customerId} tenants={tenants} onMessage={onMessage} />
        )}
        {customer && section === "Usage" && <Usage customerId={customerId} tenants={tenants} />}
        {customer && section === "Activity" && <Activity customerId={customerId} />}
        <ConfirmDialog
          request={confirm}
          onClose={() => setConfirm(null)}
          onDone={(message) => {
            setConfirm(null);
            onMessage(outcome.current ?? message);
            outcome.current = null;
            record.reload();
          }}
        />
        {editing && customer && (
          <EditDetails
            title={`Edit ${name}`}
            what="customer"
            record={customer}
            groups={presentGroups(customer, CUSTOMER_FIELD_GROUPS)}
            url={`/api/v1/platform-admin/customer-records/${customerId}`}
            onClose={() => setEditing(false)}
            onReload={() => {
              setEditing(false);
              record.reload();
            }}
            onSaved={() => {
              setEditing(false);
              onMessage(`The details of ${name} are saved.`);
              record.reload();
            }}
          />
        )}
        {addingTenant && (
          <AddTenant
            customerId={customerId}
            customerName={name}
            onClose={() => setAddingTenant(false)}
            onAdded={(message) => {
              setAddingTenant(false);
              onMessage(message);
              record.reload();
            }}
          />
        )}
      </Tabs>
    </div>
  );
}

const DETAILS: Array<[string, string]> = [
  ["Legal name", "legal_name"],
  ["Trading name", "trading_name"],
  ["Customer type", "customer_type"],
  ["Industry", "industry"],
  ["Company size", "company_size"],
  ["Country", "country"],
  ["State or province", "state_province"],
  ["Headquarters", "headquarters"],
  ["Website", "website"],
  ["CRM reference", "crm_reference"],
  ["Account owner", "internal_account_owner"],
  ["Implementation manager", "implementation_manager"],
];

const CONTACTS: Array<[string, string]> = [
  ["Business contact", "primary_business_contact"],
  ["Billing contact", "billing_contact"],
];

// A contact as one line: name, email and phone where given.
const contactText = (contact: unknown) => {
  if (!contact || typeof contact !== "object") return "—";
  const { name, email, phone } = contact as { name?: string | null; email?: string | null; phone?: string | null };
  return [name, email, phone].filter(Boolean).join(" · ") || "—";
};

function Overview({
  customer,
  tenants,
  onOpenTenant,
  onAddTenant,
}: {
  customer: Record["customer"];
  tenants: Record["tenants"];
  onOpenTenant: (tenantId: string) => void;
  // Offered only while the customer is active.
  onAddTenant?: () => void;
}) {
  // Rows the server does not return (an older record) are left out rather than shown empty.
  const details = DETAILS.filter(([, key]) => key in customer);
  const contacts = CONTACTS.filter(([, key]) => key in customer);
  return (
    <div className="ac-grid two">
      <Panel eyebrow="Maintained by MDARIX platform administrators" title="Customer details">
        <dl className="cc-details">
          <div>
            <dt>Customer ID</dt>
            <dd>{displayId(customer, "customer_identifier")}</dd>
          </div>
          {details.map(([label, key]) => (
            <div key={key}>
              <dt>{label}</dt>
              <dd>{customer[key] || "—"}</dd>
            </div>
          ))}
          {contacts.map(([label, key]) => (
            <div key={key}>
              <dt>{label}</dt>
              <dd>{contactText(customer[key])}</dd>
            </div>
          ))}
          <div>
            <dt>Customer since</dt>
            <dd>{formatDate(customer.created_at)}</dd>
          </div>
        </dl>
      </Panel>
      <Panel
        eyebrow="Workspaces and data boundaries"
        title="Tenants"
        action={
          onAddTenant ? (
            <button type="button" className="ac-primary" onClick={onAddTenant}>
              <Plus size={16} aria-hidden="true" /> Add tenant
            </button>
          ) : (
            <span className="cc-hint">Activate the customer to add tenants.</span>
          )
        }
      >
        <p className="ac-muted">
          Each tenant has its own plan, users and administrators; nothing is shared between tenants.
        </p>
        <Table
          caption="Tenants of this customer"
          rows={tenants}
          rowKey={(row) => row.id}
          empty={{ title: "No tenants", detail: "This customer has no tenant yet." }}
          columns={[
            idColumn("Tenant ID", "tenant_key"),
            {
              key: "tenant",
              label: "Tenant",
              render: (row) => (
                <button type="button" className="ac-link" onClick={() => onOpenTenant(row.id)}>
                  <strong>{row.display_name ?? row.tenant_key}</strong>
                </button>
              ),
            },
            { key: "region", label: "Data region", render: (row) => row.residency_region ?? "—" },
            {
              key: "status",
              fields: ["status", "effective_access"],
              label: "Status",
              render: (row) => (
                <span className="cc-status-cell">
                  <StatusBadge status={row.status} label={lifecycleStatusLabel(row.status)} />
                  {blockedByCustomer(row) && (
                    <span className="cc-blocked">
                      <Ban size={13} aria-hidden="true" /> Blocked: customer inactive
                    </span>
                  )}
                </span>
              ),
            },
          ]}
        />
      </Panel>
    </div>
  );
}

function useTab(customerId: string, tab: string) {
  return useResource<{ items: any[] }>(`/api/v1/platform-admin/customer-records/${customerId}/tabs/${tab}`);
}

// A tenant by its key or name; a tenant missing from the list is never shown by its UUID.
const tenantLabel = (tenants: TenantSummary[], id: string) => {
  const tenant = tenants.find((item) => item.id === id);
  return tenant?.tenant_key ?? tenant?.display_name ?? (tenant ? displayId(tenant) : "Other tenant");
};

function Subscription({
  customerId,
  tenants,
  onMessage,
}: {
  customerId: string;
  tenants: TenantSummary[];
  onMessage: (text: string, tone?: "good" | "critical") => void;
}) {
  const subscription = useTab(customerId, "Subscription");
  const [changing, setChanging] = useState(false);
  return (
    <Panel
      eyebrow="Plan and license"
      title="Subscription"
      state={subscription.state}
      error={subscription.error}
      action={
        <button type="button" className="ac-primary" onClick={() => setChanging(true)} disabled={!tenants.length}>
          <CreditCard size={16} aria-hidden="true" /> Change subscription
        </button>
      }
    >
      <Table
        caption="Current subscription"
        rows={subscription.data?.items ?? []}
        rowKey={(row) => row.id}
        empty={{ title: "No active subscription", detail: "Choose a plan with Change subscription." }}
        columns={[
          idColumn("Subscription ID"),
          ...(tenants.length > 1
            ? [{ key: "tenant", label: "Tenant", render: (row: any) => tenantLabel(tenants, row.tenant_id) }]
            : []),
          { key: "plan", label: "Plan", render: (row) => <strong>{row.plan_name ?? row.plan_code}</strong> },
          { key: "since", label: "Since", render: (row) => formatDate(row.effective_from) },
          { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
        ]}
      />
      {changing && (
        <ChangeSubscription
          tenants={tenants}
          currentPlans={(subscription.data?.items ?? []).map((row) => row.plan_code)}
          onClose={() => setChanging(false)}
          onChanged={(message) => {
            setChanging(false);
            onMessage(message);
            subscription.reload();
          }}
        />
      )}
    </Panel>
  );
}

export function ChangeSubscription({
  tenants,
  currentPlans,
  onClose,
  onChanged,
}: {
  tenants: TenantSummary[];
  currentPlans: string[];
  onClose: () => void;
  onChanged: (message: string) => void;
}) {
  const plans = useResource<Plan[]>("/api/v1/platform-admin/plans");
  const active = (Array.isArray(plans.data) ? plans.data : []).filter((plan) => (plan.status ?? "ACTIVE") === "ACTIVE");
  const today = new Date();
  const nextYear = new Date(today);
  nextYear.setFullYear(today.getFullYear() + 1);
  const [form, setForm] = useState({
    tenant_id: tenants[0]?.id ?? "",
    plan_id: "",
    starts: isoDate(today),
    expires: isoDate(nextYear),
    reason: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Start from the customer's current plan, so a renewal is one click and an upgrade a deliberate choice.
  const current = active.find((plan) => currentPlans.includes(plan.code));
  const planId = form.plan_id || current?.id || active[0]?.id || "";
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (form.expires <= form.starts) return setError("The license must end after it starts.");
    setBusy(true);
    setError("");
    try {
      await send(`/api/v1/platform/customers/${form.tenant_id}/subscription`, "POST", {
        plan_id: planId,
        starts_at: `${form.starts}T00:00:00Z`,
        expires_at: `${form.expires}T00:00:00Z`,
        reason: form.reason.trim(),
      });
      const plan = active.find((item) => item.id === planId);
      onChanged(`Subscription changed to ${plan?.name ?? plan?.code ?? "the new plan"}.`);
    } catch (reason) {
      setError(errorText(reason, "The subscription was not changed."));
      setBusy(false);
    }
  };
  return (
    <div className="ac-modal-backdrop" role="presentation">
      <DialogBehaviour onClose={onClose} />
      <form className="ac-modal" role="dialog" aria-modal="true" aria-labelledby="cc-change-sub" onSubmit={submit}>
        <p className="ac-eyebrow">Subscription</p>
        <h2 id="cc-change-sub">Change subscription</h2>
        <p>The new plan applies immediately: features and limits follow it. The previous plan stays in the history.</p>
        {tenants.length > 1 && (
          <label className="ca-field">
            Tenant
            <select value={form.tenant_id} onChange={(event) => setForm({ ...form, tenant_id: event.target.value })}>
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.display_name ?? tenant.tenant_key} ({tenant.tenant_key})
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="ca-field">
          Plan
          <select required value={planId} onChange={(event) => setForm({ ...form, plan_id: event.target.value })}>
            {active.map((plan) => (
              <option key={plan.id} value={plan.id}>
                {plan.name ?? titleCase(plan.code)}
              </option>
            ))}
          </select>
        </label>
        <div className="cc-two-fields">
          <label className="ca-field">
            License starts
            <input
              type="date"
              required
              value={form.starts}
              onChange={(event) => setForm({ ...form, starts: event.target.value })}
            />
          </label>
          <label className="ca-field">
            License ends
            <input
              type="date"
              required
              value={form.expires}
              onChange={(event) => setForm({ ...form, expires: event.target.value })}
            />
          </label>
        </div>
        <label className="ca-field">
          Reason (kept in the audit trail)
          <input
            required
            minLength={5}
            value={form.reason}
            onChange={(event) => setForm({ ...form, reason: event.target.value })}
            placeholder="e.g. Upgrade agreed in the renewal"
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
          <button type="submit" className="ac-primary" disabled={busy || !planId || form.reason.trim().length < 5}>
            {busy ? "Saving…" : "Change subscription"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Usage({ customerId, tenants }: { customerId: string; tenants: TenantSummary[] }) {
  const usage = useTab(customerId, "Usage");
  return (
    <Panel eyebrow="Seats and connections" title="Usage" state={usage.state} error={usage.error}>
      <Table
        caption="Usage by tenant"
        rows={usage.data?.items ?? []}
        rowKey={(row) => row.tenant_id}
        empty={{ title: "No usage yet", detail: "Usage appears once the customer starts working." }}
        columns={[
          { key: "tenant", label: "Tenant", render: (row) => tenantLabel(tenants, row.tenant_id) },
          { key: "users", label: "Users", numeric: true, render: (row) => row.users },
          { key: "admins", label: "Administrators", numeric: true, render: (row) => row.administrators },
          { key: "connectors", label: "Connectors", numeric: true, render: (row) => row.connectors },
        ]}
      />
    </Panel>
  );
}

function Activity({ customerId }: { customerId: string }) {
  const activity = useTab(customerId, "Activity");
  return (
    <Panel eyebrow="Audit trail" title="Recent activity" state={activity.state} error={activity.error}>
      <Table
        caption="Recent activity"
        rows={activity.data?.items ?? []}
        rowKey={(row) => row.id}
        empty={{ title: "No activity yet", detail: "Changes to this customer appear here." }}
        columns={[
          { key: "when", label: "When", render: (row) => formatDate(row.created_at) },
          { key: "action", label: "What happened", render: (row) => titleCase(row.action) },
          { key: "reason", label: "Reason", render: (row) => row.details?.reason ?? "—" },
        ]}
      />
    </Panel>
  );
}
