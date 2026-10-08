import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Check, CircleAlert, RotateCcw } from "lucide-react";
import { describeError, postJson, requestJson } from "../../app/apiClient";
import { useResource } from "../customer-admin/shared";
import {
  EMPTY_FORM,
  ENVIRONMENTS,
  JOB_STEP_LABELS,
  REGIONS,
  REVIEW_STEP,
  STEPS,
  eligiblePlans,
  featureLabel,
  formFromDraft,
  invitationText,
  provisionPayload,
  reachableStep,
  stepProblems,
  suggestTenantCode,
  type OnboardingForm,
  type Plan,
} from "./onboardingModel";
import { lifecycleStatusLabel } from "./customers/model";

const DRAFT_STORAGE = "mdarix.platform.onboarding.draft";

const newDraftKey = () => `onboarding-${crypto.randomUUID()}`;
const storedDraftKey = () => {
  try {
    const key = window.localStorage.getItem(DRAFT_STORAGE) ?? newDraftKey();
    window.localStorage.setItem(DRAFT_STORAGE, key);
    return key;
  } catch {
    return newDraftKey();
  }
};
const forgetDraftKey = () => {
  try {
    window.localStorage.removeItem(DRAFT_STORAGE);
  } catch {
    // Storage can be unavailable; the next wizard then simply starts with a new key.
  }
};

type Provisioned = {
  customer_id?: string | null;
  customer_business_id?: string | null;
  tenant_business_id?: string | null;
  tenant_key: string;
  status: string;
  customer_admin_email: string;
  invitation?: string;
  job_id?: string;
  job_identifier?: string;
};
type JobStep = { code: string; status: string };
type Job = { status?: string; step_details?: JobStep[] };

/**
 * A new customer with its first tenant, plan and Customer Administrator, step by step. Each step is checked before
 * the next opens; the last step shows everything entered, the server's own check, and the reason (kept in the audit
 * trail). After provisioning the result says what was created and what happens next.
 */
export function CreateCustomer({ onCreated }: { onCreated: (customerId?: string) => void }) {
  const [draftKey, setDraftKey] = useState(storedDraftKey);
  const [form, setForm] = useState<OnboardingForm>(EMPTY_FORM);
  const [step, setStep] = useState(1);
  const [resumed, setResumed] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [check, setCheck] = useState<{ state: "idle" | "checking" | "ok" | "failed"; text?: string }>({
    state: "idle",
  });
  const [result, setResult] = useState<{ provisioned: Provisioned; job: Job | null } | null>(null);
  const plans = useResource<Plan[]>("/api/v1/platform-admin/plans");
  const choosable = useMemo(() => eligiblePlans(Array.isArray(plans.data) ? plans.data : []), [plans.data]);
  const planCodes = choosable.map((plan) => plan.code);
  const plan = choosable.find((item) => item.code === form.plan_code);
  const furthest = reachableStep(form, planCodes);
  const problems = stepProblems(step, form, planCodes);

  // Continue an unfinished wizard from where it was left (the server keeps the draft).
  useEffect(() => {
    requestJson<{ draft_data?: unknown; current_step?: number }>(
      `/api/v1/platform-admin/onboarding/drafts/${encodeURIComponent(draftKey)}`,
    )
      .then((draft) => {
        const restored = formFromDraft(draft?.draft_data);
        if (!restored.company_name) return;
        setForm(restored);
        setStep(Math.min(Math.max(1, Number(draft?.current_step) || 1), REVIEW_STEP));
        setResumed(true);
      })
      .catch(() => undefined);
  }, [draftKey]);

  // The first eligible plan is chosen until the administrator picks one.
  useEffect(() => {
    if (!form.plan_code && choosable.length) setForm((current) => ({ ...current, plan_code: choosable[0].code }));
  }, [choosable, form.plan_code]);

  // On the last step the server checks the whole request first, without creating anything.
  useEffect(() => {
    if (step !== REVIEW_STEP || result) return;
    let active = true;
    setCheck({ state: "checking" });
    postJson("/api/v1/platform-admin/onboarding/validate", provisionPayload(form))
      .then(() => active && setCheck({ state: "ok" }))
      .catch((reason) => active && setCheck({ state: "failed", text: describeError(reason, "The check failed") }));
    return () => {
      active = false;
    };
    // The reason does not change the check; everything else does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, result, form.company_name, form.tenant_code, form.region, form.plan_code, form.customer_admin_email]);

  const update = <K extends keyof OnboardingForm>(key: K, value: OnboardingForm[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const saveDraft = (nextStep: number) =>
    requestJson(`/api/v1/platform-admin/onboarding/drafts/${encodeURIComponent(draftKey)}`, {
      method: "PUT",
      body: JSON.stringify({ idempotency_key: draftKey, current_step: nextStep, draft_data: form }),
    }).catch(() => undefined); // a lost draft never blocks onboarding

  const go = (next: number) => {
    if (next > furthest) return;
    setError("");
    void saveDraft(next);
    setStep(next);
  };

  const startOver = () => {
    forgetDraftKey();
    setDraftKey(storedDraftKey());
    setForm({ ...EMPTY_FORM, plan_code: choosable[0]?.code ?? "" });
    setStep(1);
    setResumed(false);
    setConfirmed(false);
    setError("");
    setResult(null);
  };

  const provision = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || problems.length || !confirmed) return;
    setBusy(true);
    setError("");
    try {
      const provisioned = await postJson<Provisioned>("/api/v1/platform/tenants/provision", provisionPayload(form), {
        timeoutMs: 60_000,
      });
      const job = provisioned.job_id
        ? await requestJson<Job>(`/api/v1/platform-admin/provisioning-jobs/${provisioned.job_id}`).catch(() => null)
        : null;
      forgetDraftKey(); // the next "New customer" starts empty
      setResult({ provisioned, job });
    } catch (reason) {
      setError(describeError(reason, "The customer could not be created"));
    } finally {
      setBusy(false);
    }
  };

  if (result) return <ProvisionResult form={form} {...result} onOpen={onCreated} onAnother={startOver} />;

  return (
    <form className="cw-wizard" onSubmit={provision} noValidate>
      {resumed && (
        <p className="cw-note" role="status">
          You are continuing a new customer you started earlier.
          <button type="button" className="ac-link" onClick={startOver}>
            <RotateCcw size={14} aria-hidden="true" /> Start over
          </button>
        </p>
      )}
      <ol className="cw-steps" aria-label="Steps">
        {STEPS.map((label, index) => {
          const number = index + 1;
          const done = number < furthest || (number < step && !stepProblems(number, form, planCodes).length);
          return (
            <li key={label}>
              <button
                type="button"
                className={`cw-step${number === step ? " current" : ""}${done ? " done" : ""}`}
                aria-current={number === step ? "step" : undefined}
                disabled={number > furthest}
                onClick={() => go(number)}
              >
                <span className="cw-step-number" aria-hidden="true">
                  {done && number !== step ? <Check size={13} /> : number}
                </span>
                {label}
              </button>
            </li>
          );
        })}
      </ol>

      <section className="cw-panel" aria-labelledby="cw-step-title">
        <h3 id="cw-step-title">
          Step {step} of {STEPS.length}: {STEPS[step - 1]}
        </h3>
        {step === 1 && (
          <Fields hint="The organization MDARIX contracts with. Its tenants, plan and administrators come next.">
            <Field label="Legal or company name" required>
              <input
                value={form.company_name}
                onChange={(event) => update("company_name", event.target.value)}
                maxLength={255}
                autoComplete="organization"
              />
            </Field>
            <Field label="CRM reference" hint="Optional: the customer's number in your CRM.">
              <input
                value={form.customer_reference}
                onChange={(event) => update("customer_reference", event.target.value)}
                maxLength={120}
              />
            </Field>
          </Fields>
        )}
        {step === 2 && (
          <Fields hint="A tenant is the customer's own workspace and data boundary. More tenants can be added later from the customer's page.">
            <Field label="Tenant name">
              <input value={form.company_name} readOnly aria-readonly="true" />
            </Field>
            <Field
              label="Tenant code"
              required
              hint="A short permanent code: letters, digits, underscores or hyphens. It cannot be changed later."
            >
              <span className="cw-inline">
                <input
                  value={form.tenant_code}
                  onChange={(event) => update("tenant_code", event.target.value.toUpperCase())}
                  maxLength={40}
                  spellCheck={false}
                />
                <button
                  type="button"
                  className="ac-secondary"
                  onClick={() => update("tenant_code", suggestTenantCode(form.company_name))}
                  disabled={!form.company_name.trim()}
                >
                  Suggest
                </button>
              </span>
            </Field>
            <Field label="Environment">
              <select
                value={form.environment_type}
                onChange={(event) => update("environment_type", event.target.value)}
              >
                {ENVIRONMENTS.map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
          </Fields>
        )}
        {step === 3 && (
          <Fields hint="The tenant's records are stored and processed in this region. Storing data in another region needs an approved cross-border policy, which is arranged separately.">
            <Field label="Data region" required>
              <select value={form.region} onChange={(event) => update("region", event.target.value)}>
                {REGIONS.map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
          </Fields>
        )}
        {step === 4 && (
          <Fields hint="The plan sets what the customer can use. Only published plans that include customer administration are offered.">
            <Field label="Plan" required>
              <select
                value={form.plan_code}
                onChange={(event) => update("plan_code", event.target.value)}
                disabled={plans.state !== "ready"}
              >
                {!choosable.length && (
                  <option value="">{plans.state === "ready" ? "No plan available" : "Loading…"}</option>
                )}
                {choosable.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.name || item.code}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Licensed users" required hint="How many people the customer may have.">
              <input
                type="number"
                min={1}
                step={1}
                value={Number.isFinite(form.licensed_users_limit) ? form.licensed_users_limit : ""}
                onChange={(event) => update("licensed_users_limit", Number.parseInt(event.target.value, 10))}
              />
            </Field>
          </Fields>
        )}
        {step === 5 && (
          <Fields hint="The features included come from the plan; they change when the plan changes (Plans & Licensing).">
            {plan ? (
              <ul className="cw-list">
                {Object.entries(plan.capabilities ?? {})
                  .filter(([, enabled]) => enabled)
                  .map(([code]) => (
                    <li key={code}>
                      <Check size={14} aria-hidden="true" /> {featureLabel(code)}
                    </li>
                  ))}
                {!Object.values(plan.capabilities ?? {}).some(Boolean) && (
                  <li>No features are listed for this plan.</li>
                )}
              </ul>
            ) : (
              <p className="ac-muted">Choose a plan first.</p>
            )}
          </Fields>
        )}
        {step === 6 && (
          <Fields hint="The customer's first administrator. They are invited by email, set their own password and then add their colleagues.">
            <Field label="Work email" required>
              <input
                type="email"
                value={form.customer_admin_email}
                onChange={(event) => update("customer_admin_email", event.target.value)}
                autoComplete="off"
              />
            </Field>
            <Field label="Name" required>
              <input
                value={form.customer_admin_display_name}
                onChange={(event) => update("customer_admin_display_name", event.target.value)}
                maxLength={120}
              />
            </Field>
            <Field label="Company" hint="Leave empty to use the customer's name.">
              <input
                value={form.customer_admin_company}
                onChange={(event) => update("customer_admin_company", event.target.value)}
                maxLength={160}
                placeholder={form.company_name}
              />
            </Field>
          </Fields>
        )}
        {step === 7 && (
          <Fields>
            <ul className="cw-list">
              <li>
                <Check size={14} aria-hidden="true" /> People sign in with their work email and a password of their own.
              </li>
              <li>
                <Check size={14} aria-hidden="true" /> Authenticator-app two-factor sign-in (MFA), required for the
                roles set in the platform&apos;s security settings.
              </li>
              <li>
                <CircleAlert size={14} aria-hidden="true" /> Single sign-on (Microsoft Entra ID, Okta, SAML) is not
                available yet.
              </li>
            </ul>
          </Fields>
        )}
        {step === 8 && (
          <Fields>
            <p className="ar-intro">
              The tenant starts from the MDARIX standard configuration for medical device quality: record types,
              workflow roles, review policies and detection rules. Customer-specific configuration is managed later
              under Data &amp; Integrations &gt; Customer configuration.
            </p>
          </Fields>
        )}
        {step === REVIEW_STEP && (
          <div className="cw-review">
            <dl>
              <Review label="Customer" onEdit={() => go(1)}>
                {form.company_name}
                {form.customer_reference && <small>CRM reference {form.customer_reference}</small>}
              </Review>
              <Review label="Tenant" onEdit={() => go(2)}>
                {form.tenant_code.toUpperCase()}
                <small>{ENVIRONMENTS.find(([code]) => code === form.environment_type)?.[1]}</small>
              </Review>
              <Review label="Data region" onEdit={() => go(3)}>
                {REGIONS.find(([code]) => code === form.region)?.[1] ?? form.region}
              </Review>
              <Review label="Plan" onEdit={() => go(4)}>
                {plan?.name || form.plan_code}
                <small>{form.licensed_users_limit} licensed users</small>
              </Review>
              <Review label="First administrator" onEdit={() => go(6)}>
                {form.customer_admin_display_name}
                <small>{form.customer_admin_email}</small>
              </Review>
            </dl>
            {check.state === "checking" && <p className="ac-muted">Checking the request with the server…</p>}
            {check.state === "ok" && (
              <p className="cw-check ok" role="status">
                <Check size={15} aria-hidden="true" /> Ready to create: the server accepted every detail.
              </p>
            )}
            {check.state === "failed" && (
              <p className="ca-inline-error" role="alert">
                {check.text}
              </p>
            )}
            <Field
              label="Reason for creating this customer"
              required
              hint="Kept in the audit trail, e.g. “Signed contract 2026-114”."
            >
              <textarea
                rows={2}
                value={form.reason}
                maxLength={1000}
                onChange={(event) => update("reason", event.target.value)}
              />
            </Field>
            <label className="cw-confirm">
              <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
              <span>I have checked the customer, tenant, plan and administrator details above.</span>
            </label>
          </div>
        )}
        {problems.length > 0 && step !== 5 && step !== 7 && step !== 8 && (
          <ul className="cw-problems" aria-live="polite">
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        {error && (
          <p className="ca-inline-error" role="alert">
            {error}
          </p>
        )}
      </section>

      <div className="cw-actions">
        <button type="button" className="ac-secondary" disabled={step === 1 || busy} onClick={() => go(step - 1)}>
          Back
        </button>
        {step < REVIEW_STEP ? (
          <button type="button" className="ac-primary" disabled={problems.length > 0} onClick={() => go(step + 1)}>
            Continue
          </button>
        ) : (
          <button
            type="submit"
            className="ac-primary"
            disabled={
              busy || problems.length > 0 || !confirmed || check.state === "failed" || check.state === "checking"
            }
          >
            {busy ? "Creating…" : "Create customer"}
          </button>
        )}
      </div>
      {step === REVIEW_STEP && !confirmed && !problems.length && (
        <p className="ac-muted cw-hint-right">Tick the confirmation to create the customer.</p>
      )}
    </form>
  );
}

function Fields({ hint, children }: { hint?: string; children: ReactNode }) {
  return (
    <div className="cw-fields">
      {hint && <p className="ar-intro">{hint}</p>}
      {children}
    </div>
  );
}

function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className="ca-field">
      <span>
        {label}
        {required && <span className="cw-required"> (required)</span>}
      </span>
      {children}
      {hint && <small className="ac-muted">{hint}</small>}
    </label>
  );
}

function Review({ label, onEdit, children }: { label: string; onEdit: () => void; children: ReactNode }) {
  return (
    <div className="cw-review-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
      <dd>
        <button type="button" className="ac-link" onClick={onEdit} aria-label={`Change ${label.toLowerCase()}`}>
          Change
        </button>
      </dd>
    </div>
  );
}

/** What provisioning created, each step the server recorded, and what to do next. */
function ProvisionResult({
  form,
  provisioned,
  job,
  onOpen,
  onAnother,
}: {
  form: OnboardingForm;
  provisioned: Provisioned;
  job: Job | null;
  onOpen: (customerId?: string) => void;
  onAnother: () => void;
}) {
  const steps = job?.step_details ?? [];
  const failed = steps.filter((item) => String(item.status).toUpperCase() !== "COMPLETED");
  const active = String(provisioned.status).toUpperCase() === "ACTIVE" && !failed.length;
  return (
    <section className="cw-result" aria-labelledby="cw-result-title">
      <div className={`ac-message tone-${active ? "good" : "critical"}`} role="status">
        <strong id="cw-result-title">
          {active
            ? `${form.company_name} is set up and active.`
            : `${form.company_name} was created, but setup did not finish.`}
        </strong>
      </div>
      <dl className="cw-review">
        <div className="cw-review-row">
          <dt>Customer</dt>
          <dd>
            {form.company_name}
            <small>{provisioned.customer_business_id}</small>
          </dd>
        </div>
        <div className="cw-review-row">
          <dt>Tenant</dt>
          <dd>
            {provisioned.tenant_key}
            <small>
              {provisioned.tenant_business_id} · {active ? "Active" : lifecycleStatusLabel(provisioned.status)}
            </small>
          </dd>
        </div>
        <div className="cw-review-row">
          <dt>First administrator</dt>
          <dd>{invitationText(provisioned.invitation, provisioned.customer_admin_email)}</dd>
        </div>
        {provisioned.job_identifier && (
          <div className="cw-review-row">
            <dt>Setup record</dt>
            <dd>{provisioned.job_identifier}</dd>
          </div>
        )}
      </dl>
      {steps.length > 0 && (
        <>
          <h4>What was set up</h4>
          <ol className="cw-job">
            {steps.map((item) => {
              const done = String(item.status).toUpperCase() === "COMPLETED";
              return (
                <li key={item.code} className={done ? "done" : "failed"}>
                  {done ? <Check size={15} aria-hidden="true" /> : <CircleAlert size={15} aria-hidden="true" />}
                  <span>{JOB_STEP_LABELS[item.code] ?? item.code}</span>
                  <small>{done ? "Done" : "Not done"}</small>
                </li>
              );
            })}
          </ol>
        </>
      )}
      <p className="ar-intro">
        Next: the administrator accepts the invitation, sets a password and adds their colleagues. You can change the
        customer&apos;s details, plan and status from its page.
      </p>
      <div className="cw-actions">
        <button type="button" className="ac-secondary" onClick={onAnother}>
          Add another customer
        </button>
        <button type="button" className="ac-primary" onClick={() => onOpen(provisioned.customer_id ?? undefined)}>
          Open {form.company_name}
        </button>
      </div>
    </section>
  );
}
