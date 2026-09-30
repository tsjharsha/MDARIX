import React, { useEffect, useState } from "react";

export function CreateCustomer({ onCreated }: { onCreated: () => void }) {
  const [form, setForm] = useState({
    company_name: "",
    tenant_code: "",
    region: "US",
    residency: "US",
    plan_code: "ENTERPRISE_TEST",
    licensed_users_limit: 25,
    customer_admin_email: "",
    customer_admin_display_name: "",
    customer_admin_company: "",
    domain: "",
    identity_provider: "MDARIX Identity",
    baseline: "MDARIX Standard MedTech 1.0",
    reason: "",
  });
  const [message, setMessage] = useState("");
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<any>(null);
  const [draftKey] = useState(() => {
    const key = window.localStorage.getItem("mdarix.platform.onboarding.draft") ?? `onboarding-${crypto.randomUUID()}`;
    window.localStorage.setItem("mdarix.platform.onboarding.draft", key);
    return key;
  });
  const stepLabels = [
    "Customer",
    "Tenant",
    "Region",
    "Plan",
    "Entitlements",
    "Admin",
    "Identity",
    "Baseline",
    "Review & Provision",
  ];
  const update = (key: string, value: string | number) => setForm((current) => ({ ...current, [key]: value }));
  const saveDraft = async (nextStep = step) => {
    try {
      await fetch(`/api/v1/platform-admin/onboarding/drafts/${encodeURIComponent(draftKey)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idempotency_key: draftKey, current_step: nextStep, draft_data: form }),
      });
    } catch {
      /* draft persistence must not block the governed flow */
    }
  };
  useEffect(() => {
    fetch(`/api/v1/platform-admin/onboarding/drafts/${encodeURIComponent(draftKey)}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((draft) => {
        if (draft?.draft_data) setForm((current) => ({ ...current, ...draft.draft_data }));
        if (draft?.current_step) setStep(draft.current_step);
      })
      .catch(() => undefined);
  }, [draftKey]);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const payload = {
      company_name: form.company_name,
      tenant_code: form.tenant_code,
      region: form.region,
      residency: form.residency,
      plan_code: form.plan_code,
      licensed_users_limit: form.licensed_users_limit,
      customer_admin_email: form.customer_admin_email,
      customer_admin_display_name: form.customer_admin_display_name,
      customer_admin_company: form.customer_admin_company || form.company_name,
      invitation_required: true,
    };
    try {
      const validationResponse = await fetch("/api/v1/platform-admin/onboarding/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const validation = await validationResponse.json();
      if (!validationResponse.ok) throw new Error(validation.detail?.message ?? "Onboarding validation failed");
      const response = await fetch("/api/v1/platform/tenants/provision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail?.message ?? "Provisioning failed");
      setJob({ ...result, steps: [] });
      setMessage(`Provisioning ${result.status}.`);
      if (result.job_id) {
        const poll = async () => {
          try {
            const statusResponse = await fetch(`/api/v1/platform-admin/provisioning-jobs/${result.job_id}`);
            const status = await statusResponse.json();
            if (!statusResponse.ok) throw new Error(status.detail?.message ?? "Provisioning status unavailable");
            setJob((current: any) => ({ ...current, ...status }));
          } catch {
            /* keep the last server state */
          }
        };
        await poll();
        const timer = window.setInterval(poll, 3000);
        window.setTimeout(() => window.clearInterval(timer), 18000);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Provisioning failed");
    } finally {
      setBusy(false);
    }
  };
  const fields =
    step === 1 ? (
      <>
        <label>
          Legal / company name
          <input required value={form.company_name} onChange={(e) => update("company_name", e.target.value)} />
        </label>
        <label>
          Customer reference
          <input
            value={form.domain}
            onChange={(e) => update("domain", e.target.value)}
            placeholder="CRM or approved domain"
          />
        </label>
      </>
    ) : step === 2 ? (
      <>
        <label>
          Tenant display name
          <input required value={form.company_name} readOnly />
        </label>
        <label>
          Tenant code
          <input
            required
            value={form.tenant_code}
            onChange={(e) => update("tenant_code", e.target.value)}
            placeholder="Generated tenant key"
          />
        </label>
      </>
    ) : step === 3 ? (
      <>
        <label>
          Primary region
          <select value={form.region} onChange={(e) => update("region", e.target.value)}>
            <option>US</option>
            <option>EU</option>
            <option>UK</option>
            <option>Canada</option>
            <option>India</option>
          </select>
        </label>
        <label>
          Data residency
          <select value={form.residency} onChange={(e) => update("residency", e.target.value)}>
            <option>US</option>
            <option>EU</option>
            <option>UK</option>
            <option>Canada</option>
            <option>India</option>
          </select>
        </label>
      </>
    ) : step === 4 ? (
      <>
        <label>
          Plan
          <select value={form.plan_code} onChange={(e) => update("plan_code", e.target.value)}>
            <option>ENTERPRISE_TEST</option>
            <option>STARTER</option>
            <option>PROFESSIONAL</option>
            <option>ENTERPRISE</option>
          </select>
        </label>
        <label>
          Licensed users
          <input
            type="number"
            min="1"
            value={form.licensed_users_limit}
            onChange={(e) => update("licensed_users_limit", Number(e.target.value))}
          />
        </label>
      </>
    ) : step === 5 ? (
      <div className="onboarding-summary">
        <strong>Entitlements inherit from the selected published plan.</strong>
        <span>
          Product 360, Investigations, Evidence, Audit and governed AI remain subject to plan and release gates.
        </span>
      </div>
    ) : step === 6 ? (
      <>
        <label>
          Initial Customer Administrator
          <input
            required
            type="email"
            value={form.customer_admin_email}
            onChange={(e) => update("customer_admin_email", e.target.value)}
            placeholder="admin@customer.com"
          />
        </label>
        <label>
          Administrator name
          <input
            required
            value={form.customer_admin_display_name}
            onChange={(e) => update("customer_admin_display_name", e.target.value)}
          />
        </label>
      </>
    ) : step === 7 ? (
      <>
        <label>
          Identity provider
          <select value={form.identity_provider} onChange={(e) => update("identity_provider", e.target.value)}>
            <option>MDARIX Identity</option>
            <option>Microsoft Entra ID</option>
            <option>Okta</option>
            <option>SAML / OIDC pending</option>
          </select>
        </label>
        <div className="onboarding-summary">
          <strong>MFA is required for critical operations.</strong>
          <span>SSO configuration is completed after the tenant is provisioned.</span>
        </div>
      </>
    ) : step === 8 ? (
      <label>
        Configuration baseline
        <input value={form.baseline} onChange={(e) => update("baseline", e.target.value)} />
      </label>
    ) : (
      <div className="onboarding-summary">
        <strong>Review before provisioning</strong>
        <span>
          {form.company_name} · {form.tenant_code} · {form.region} · {form.plan_code}
        </span>
        <span>Initial admin: {form.customer_admin_email || "Not entered"}</span>
        <label>
          Provisioning reason
          <input required value={form.reason} onChange={(e) => update("reason", e.target.value)} />
        </label>
      </div>
    );
  return (
    <div className="content governance-view">
      <section className="panel onboarding-wizard">
        <div className="section-title">Create Customer &amp; Tenant</div>
        <p>
          Platform-controlled onboarding. The server generates immutable tenant identity and remains authoritative for
          provisioning, entitlements and invitations.
        </p>
        <div className="admin-stepper">
          {stepLabels.map((label, index) => (
            <button
              type="button"
              key={label}
              className={step === index + 1 ? "selected" : ""}
              onClick={() => index + 1 <= step && (saveDraft(index + 1), setStep(index + 1))}
            >
              {index + 1}. {label}
            </button>
          ))}
        </div>
        <form className="admin-form-grid" onSubmit={submit}>
          <h3>{stepLabels[step - 1]}</h3>
          {fields}
          {step === 9 && (
            <label className="onboarding-confirm">
              <input type="checkbox" required /> I confirm the customer, tenant, subscription and identity information
              has been reviewed.
            </label>
          )}
          <div className="toolbar">
            <button
              type="button"
              className="secondary-link"
              disabled={step === 1 || busy}
              onClick={() => {
                saveDraft(step - 1);
                setStep(step - 1);
              }}
            >
              Back
            </button>
            {step < 9 ? (
              <button
                type="button"
                className="primary-action"
                onClick={() => {
                  saveDraft(step + 1);
                  setStep(step + 1);
                }}
              >
                Continue
              </button>
            ) : (
              <button className="primary-action" type="submit" disabled={busy}>
                {busy ? "Provisioning…" : "Provision Customer"}
              </button>
            )}
          </div>
        </form>
        {message && (
          <p className="review-success" role="status">
            {message}
          </p>
        )}
      </section>
      {job && (
        <section className="panel provisioning-job">
          <div className="section-title">Provisioning job progress</div>
          <p>
            Tenant: {job.tenant_key} · Status: {job.status}
          </p>
          <ol>
            {job.steps.map((item: string, index: number) => (
              <li className={job.status === "ACTIVE" || index < 2 ? "complete" : "pending"} key={item}>
                <span>{job.status === "ACTIVE" || index < 2 ? "✓" : "○"}</span>
                {item}
              </li>
            ))}
          </ol>
          {job.status === "ACTIVE" && (
            <button className="secondary-link" onClick={onCreated}>
              Open customers
            </button>
          )}
        </section>
      )}
    </div>
  );
}
