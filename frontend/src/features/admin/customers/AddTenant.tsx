import { useState } from "react";
import { errorText, send, useResource } from "../../customer-admin/shared";
import { ENVIRONMENT_TYPES, titleCase, type Plan } from "./model";
import { DialogBehaviour } from "../../shared/DialogBehaviour";

/**
 * Add a tenant to an existing customer: another region, business unit or validation workspace. The tenant is a
 * separate data boundary with its own plan, first environment and first Customer Administrator, who is invited
 * by email and manages only this tenant's users.
 */
export function AddTenant({
  customerId,
  customerName,
  onClose,
  onAdded,
}: {
  customerId: string;
  customerName: string;
  onClose: () => void;
  onAdded: (message: string) => void;
}) {
  const plans = useResource<Plan[]>("/api/v1/platform-admin/plans");
  const active = (Array.isArray(plans.data) ? plans.data : []).filter((plan) => (plan.status ?? "ACTIVE") === "ACTIVE");
  const [form, setForm] = useState({
    tenant_name: "",
    tenant_code: "",
    environment_type: "PRODUCTION",
    data_region: "",
    plan_id: "",
    admin_display_name: "",
    admin_email: "",
    reason: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const planId = form.plan_id || active[0]?.id || "";
  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [key]: event.target.value });
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await send<any>(`/api/v1/platform-admin/customer-records/${customerId}/tenants`, "POST", {
        ...form,
        tenant_name: form.tenant_name.trim(),
        tenant_code: form.tenant_code.trim().toUpperCase(),
        data_region: form.data_region.trim(),
        plan_id: planId,
        admin_display_name: form.admin_display_name.trim(),
        admin_email: form.admin_email.trim(),
        reason: form.reason.trim(),
      });
      const invited =
        result.email_delivery === "NOT_CONFIGURED"
          ? "Email is not configured here, so no invitation was delivered."
          : `${result.administrator?.email} is invited by email.`;
      onAdded(`Tenant ${result.tenant?.display_name ?? form.tenant_name} added to ${customerName}. ${invited}`);
    } catch (reason) {
      setError(errorText(reason, "The tenant was not added."));
      setBusy(false);
    }
  };
  return (
    <div className="ac-modal-backdrop" role="presentation">
      <DialogBehaviour onClose={onClose} />
      <form className="ac-modal" role="dialog" aria-modal="true" aria-labelledby="cc-add-tenant" onSubmit={submit}>
        <p className="ac-eyebrow">{customerName}</p>
        <h2 id="cc-add-tenant">Add tenant</h2>
        <p>
          A tenant is a separate workspace and data boundary of this customer, with its own plan, users and
          administrators. Nothing is shared with the customer&apos;s other tenants.
        </p>
        <div className="cc-two-fields">
          <label className="ca-field">
            Tenant name
            <input
              required
              minLength={2}
              value={form.tenant_name}
              onChange={set("tenant_name")}
              placeholder="e.g. Europe Production"
            />
          </label>
          <label className="ca-field">
            Tenant code
            <input
              required
              minLength={2}
              maxLength={80}
              pattern="[A-Za-z0-9][A-Za-z0-9_\-]*"
              title="Letters, numbers, dashes or underscores"
              value={form.tenant_code}
              onChange={set("tenant_code")}
              placeholder="e.g. APEX-EU-PROD"
            />
          </label>
        </div>
        <div className="cc-two-fields">
          <label className="ca-field">
            First environment
            <select value={form.environment_type} onChange={set("environment_type")}>
              {ENVIRONMENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {titleCase(type)}
                </option>
              ))}
            </select>
          </label>
          <label className="ca-field">
            Data region
            <input
              required
              minLength={2}
              value={form.data_region}
              onChange={set("data_region")}
              placeholder="e.g. eu-central-1"
            />
          </label>
        </div>
        <label className="ca-field">
          Plan
          <select required value={planId} onChange={set("plan_id")} disabled={plans.state === "loading"}>
            {plans.state === "loading" && <option value="">Loading plans…</option>}
            {active.map((plan) => (
              <option key={plan.id} value={plan.id}>
                {plan.name ?? titleCase(plan.code)}
              </option>
            ))}
          </select>
        </label>
        <p className="ac-eyebrow">First Customer Administrator of this tenant</p>
        <div className="cc-two-fields">
          <label className="ca-field">
            Full name
            <input required value={form.admin_display_name} onChange={set("admin_display_name")} />
          </label>
          <label className="ca-field">
            Work email
            <input required type="email" value={form.admin_email} onChange={set("admin_email")} />
          </label>
        </div>
        <label className="ca-field">
          Reason (kept in the audit trail)
          <input
            required
            minLength={5}
            value={form.reason}
            onChange={set("reason")}
            placeholder="e.g. Customer opened a European operation"
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
          <button type="submit" className="ac-primary" disabled={busy || !planId}>
            {busy ? "Adding…" : "Add tenant and invite"}
          </button>
        </div>
      </form>
    </div>
  );
}
