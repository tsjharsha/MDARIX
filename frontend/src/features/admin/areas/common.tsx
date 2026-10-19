import { X } from "lucide-react";
import { useResource } from "../../customer-admin/shared";
import { tenantOptionLabel, type TenantSummary } from "../customers/model";
import { safeText } from "../../../app/displayId";

/** Choose a tenant by name instead of typing its identifier. */
export function TenantPicker({
  value,
  onChange,
  label = "Tenant",
  allLabel,
  inline = false,
  withoutTrials = false,
}: {
  value: string;
  onChange: (tenantId: string) => void;
  label?: string;
  // When set, an empty choice with this label (e.g. "All tenants") is offered.
  allLabel?: string;
  // In a filter toolbar the label is not shown (the select is still named for screen readers).
  inline?: boolean;
  // Leave the free trials out (the server marks them is_trial).
  withoutTrials?: boolean;
}) {
  const tenants = useResource<{ items: TenantSummary[] }>("/api/v1/platform-admin/customer-admin-tenants");
  const options = (tenants.data?.items ?? []).filter((tenant) => !(withoutTrials && tenant.is_trial));
  return (
    <label className={`ca-field ar-picker${inline ? " ar-inline" : ""}`}>
      {!inline && label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={tenants.state === "loading"}
        aria-label={label}
      >
        {tenants.state === "loading" ? (
          <option value="">Loading tenants…</option>
        ) : (
          <option value="">{allLabel ?? "Choose a tenant"}</option>
        )}
        {options.map((tenant) => (
          <option key={tenant.id} value={tenant.id}>
            {tenantOptionLabel(tenant)}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Tenant shown as "Customer · Tenant" with its Tenant ID and key underneath. */
export function TenantCell({
  row,
}: {
  row: {
    tenant_name?: string | null;
    tenant_key?: string | null;
    tenant_business_id?: string | null;
    customer_name?: string | null;
  };
}) {
  const owner = row.customer_name && row.customer_name !== row.tenant_name ? `${row.customer_name} · ` : "";
  const codes = [safeText(row.tenant_business_id), safeText(row.tenant_key)].filter(Boolean).join(" · ");
  return (
    <span className="cc-stack">
      <strong>{row.tenant_name ? `${owner}${row.tenant_name}` : "—"}</strong>
      {codes && <small>{codes}</small>}
    </span>
  );
}

/** A person by name with their User ID underneath; an unresolved reference (a bare UUID) is never shown. */
export function PersonCell({
  name,
  businessId,
  none = "—",
}: {
  name?: string | null;
  businessId?: string | null;
  none?: string;
}) {
  const shown = safeText(name);
  const id = safeText(businessId);
  if (!shown && !id) return <>{name ? "Unknown user" : none}</>;
  return (
    <span className="cc-stack">
      <strong>{shown ?? id}</strong>
      {shown && id && <small>{id}</small>}
    </span>
  );
}

export function Pager({
  page,
  pages,
  total,
  noun,
  onPage,
}: {
  page: number;
  pages: number;
  total: number;
  noun: string;
  onPage: (page: number) => void;
}) {
  return (
    <div className="cc-pager">
      <span>
        {total} {noun}
        {total === 1 ? "" : "s"}
      </span>
      <button type="button" className="ac-secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </button>
      <span>
        Page {page} of {pages}
      </span>
      <button type="button" className="ac-secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next
      </button>
    </div>
  );
}

/** A short plain-language explanation shown at the top of a section. */
export function Intro({ children }: { children: React.ReactNode }) {
  return <p className="ar-intro">{children}</p>;
}

export type BannerMessage = { text: string; tone: "good" | "critical" } | null;

/** The area's message banner (a result or an error), shown at the top and dismissable, as AdminArea shows it. */
export function Banner({ message, onDismiss }: { message: BannerMessage; onDismiss: () => void }) {
  if (!message) return null;
  return (
    <div className={`ac-message tone-${message.tone}`} role="status">
      {message.text}
      <button type="button" className="ac-link" onClick={onDismiss} aria-label="Dismiss message">
        <X size={14} />
      </button>
    </div>
  );
}
