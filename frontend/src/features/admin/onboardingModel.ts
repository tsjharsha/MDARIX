// The rules of the new-customer wizard (CreateCustomer.tsx): what each step needs, which plans can be chosen, and how
// the server's provisioning result reads. The server checks everything again (backend/app/access/common.py).

export const STEPS = [
  "Customer",
  "Tenant",
  "Region",
  "Plan",
  "Included features",
  "Administrator",
  "Sign-in",
  "Baseline",
  "Review & create",
] as const;
export const REVIEW_STEP = STEPS.length;

export const REGIONS: [string, string][] = [
  ["US", "United States"],
  ["EU", "European Union"],
  ["UK", "United Kingdom"],
  ["Canada", "Canada"],
  ["India", "India"],
];

export const ENVIRONMENTS: [string, string][] = [
  ["PRODUCTION", "Production"],
  ["VALIDATION", "Validation"],
  ["UAT", "User acceptance testing"],
  ["SANDBOX", "Sandbox"],
  ["DEMO", "Demo"],
];

export type OnboardingForm = {
  company_name: string;
  customer_reference: string;
  tenant_code: string;
  environment_type: string;
  region: string;
  plan_code: string;
  licensed_users_limit: number;
  customer_admin_email: string;
  customer_admin_display_name: string;
  customer_admin_company: string;
  reason: string;
};

export const EMPTY_FORM: OnboardingForm = {
  company_name: "",
  customer_reference: "",
  tenant_code: "",
  environment_type: "PRODUCTION",
  region: "US",
  plan_code: "",
  licensed_users_limit: 25,
  customer_admin_email: "",
  customer_admin_display_name: "",
  customer_admin_company: "",
  reason: "",
};

/** A saved draft (possibly from the earlier wizard) as a form: known fields only, wrong types dropped. */
export const formFromDraft = (draft: unknown): OnboardingForm => {
  const data = draft && typeof draft === "object" ? (draft as Record<string, unknown>) : {};
  const form = { ...EMPTY_FORM };
  for (const key of Object.keys(EMPTY_FORM) as (keyof OnboardingForm)[]) {
    const value = data[key];
    if (key === "licensed_users_limit") {
      if (typeof value === "number" && Number.isFinite(value)) form.licensed_users_limit = value;
    } else if (typeof value === "string") {
      form[key] = value;
    }
  }
  // The earlier wizard kept the CRM reference in "domain".
  if (!form.customer_reference && typeof data.domain === "string") form.customer_reference = data.domain;
  return form;
};

export type Plan = {
  code: string;
  name?: string | null;
  description?: string | null;
  status?: string | null;
  capabilities?: Record<string, boolean>;
  limits?: Record<string, unknown>;
};

/** Plans a new customer can start on: active, with the administration feature, and not the free trial (trials are
 * approved from Identity & Access > Onboarding). */
export const eligiblePlans = (plans: Plan[]) =>
  plans.filter(
    (plan) =>
      String(plan.status ?? "").toUpperCase() === "ACTIVE" &&
      plan.capabilities?.ADMIN_CONTROL_PLANE === true &&
      plan.code !== "FREE_TRIAL",
  );

/** "Acme Medical Devices, Inc." -> "ACME_MEDICAL_DEVICES_INC" (the server keeps tenant codes in capitals). */
// Letters that do not decompose into a base letter plus an accent.
const TRANSLITERATE: Record<string, string> = {
  Ø: "O",
  ø: "o",
  Æ: "AE",
  æ: "ae",
  Œ: "OE",
  œ: "oe",
  ß: "ss",
  Ł: "L",
  ł: "l",
  Đ: "D",
  đ: "d",
  Þ: "TH",
  þ: "th",
};

export const suggestTenantCode = (name: string) =>
  name
    .replace(/[ØøÆæŒœßŁłĐđÞþ]/g, (letter) => TRANSLITERATE[letter])
    .normalize("NFKD")
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toUpperCase()
    .slice(0, 40);

export const TENANT_CODE = /^[A-Za-z0-9][A-Za-z0-9_-]{2,39}$/;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
export const REASON_MIN = 10;

/** What still stops a step from being complete (empty when it is complete). */
export const stepProblems = (step: number, form: OnboardingForm, planCodes: string[] = []): string[] => {
  const problems: string[] = [];
  if (step === 1 && !form.company_name.trim()) problems.push("Enter the customer's legal or company name.");
  if (step === 2 && !TENANT_CODE.test(form.tenant_code.trim()))
    problems.push(
      "The tenant code needs 3–40 letters, digits, underscores or hyphens, starting with a letter or digit.",
    );
  if (step === 3 && !REGIONS.some(([code]) => code === form.region)) problems.push("Choose the data region.");
  if (step === 4) {
    if (!planCodes.includes(form.plan_code)) problems.push("Choose a plan.");
    if (!Number.isInteger(form.licensed_users_limit) || form.licensed_users_limit < 1)
      problems.push("Licensed users must be a whole number of at least 1.");
  }
  if (step === 6) {
    if (!EMAIL.test(form.customer_admin_email.trim())) problems.push("Enter the administrator's work email.");
    if (!form.customer_admin_display_name.trim()) problems.push("Enter the administrator's name.");
  }
  if (step === REVIEW_STEP && form.reason.trim().length < REASON_MIN)
    problems.push(`Give the reason for creating this customer (at least ${REASON_MIN} characters).`);
  return problems;
};

/** The furthest step that can be opened: every step before it is complete. */
export const reachableStep = (form: OnboardingForm, planCodes: string[]) => {
  for (let step = 1; step < REVIEW_STEP; step += 1) if (stepProblems(step, form, planCodes).length) return step;
  return REVIEW_STEP;
};

/** The request the server provisions from. Processing and residency are the same region (a different residency
 * needs an approved cross-border policy, which the server refuses here). */
export const provisionPayload = (form: OnboardingForm) => ({
  company_name: form.company_name.trim(),
  customer_reference: form.customer_reference.trim() || null,
  tenant_code: form.tenant_code.trim().toUpperCase(),
  environment_type: form.environment_type,
  region: form.region,
  residency: form.region,
  plan_code: form.plan_code,
  licensed_users_limit: form.licensed_users_limit,
  customer_admin_email: form.customer_admin_email.trim().toLowerCase(),
  customer_admin_display_name: form.customer_admin_display_name.trim(),
  customer_admin_company: form.customer_admin_company.trim() || form.company_name.trim(),
  invitation_required: true,
  reason: form.reason.trim(),
});

/** The provisioning steps the server records, as people read them. */
export const JOB_STEP_LABELS: Record<string, string> = {
  CUSTOMER: "Customer record created",
  TENANT: "Tenant workspace created",
  PLAN: "Plan and entitlements assigned",
  MEMBERSHIP: "Administrator added to the tenant",
  INVITATION: "Administrator invitation prepared",
  ISOLATION: "Data isolation checked",
  CONFIGURATION: "Standard configuration applied",
};

/** What happened to the administrator's invitation, in plain words. */
export const invitationText = (state: unknown, email: string) => {
  const value = String(state ?? "").toUpperCase();
  if (value === "SENT") return `Invitation email sent to ${email}.`;
  if (value === "CREATED")
    return `Invitation created for ${email}, but email is not set up on this server. Send it from Identity & Access > Customer administrators (Resend invitation).`;
  if (value === "EXISTING") return `${email} already had an invitation; no new one was sent.`;
  return `Invitation for ${email}: ${value.toLowerCase() || "unknown"}.`;
};

/** Feature codes as people read them ("DECISION_CENTER_SIGNATURES" -> "Decision center signatures"). */
export const featureLabel = (code: string) =>
  ({
    ADMIN_CONTROL_PLANE: "Customer administration",
    ASK_MDARIX: "Ask MDARIX (AI assistance)",
    DECISION_CENTER_SIGNATURES: "Electronic signatures on decisions",
    CONNECTOR_CONFIGURATION: "Connectors to customer systems",
  })[code] ?? code.charAt(0) + code.slice(1).toLowerCase().replace(/_/g, " ");
