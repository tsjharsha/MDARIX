// Shapes and small helpers for the platform administrator's Customers & Tenants area.

import { describeError } from "../../../app/apiClient";

export const SECTIONS = ["Customers", "Tenants", "Trials", "Feedback"] as const;
export type Section = (typeof SECTIONS)[number];

export type CustomerAdmin = {
  id: string;
  business_id?: string | null;
  email: string;
  display_name: string | null;
  status: string;
  tenant_id: string;
  tenant_business_id?: string | null;
  tenant_key: string | null;
  tenant_name?: string | null;
  customer_id: string | null;
  customer_business_id?: string | null;
  customer_name: string | null;
  can_suspend: boolean;
  is_last_active_admin: boolean;
  can_reactivate: boolean;
  can_resend_invitation: boolean;
  can_reset_password: boolean;
};

export type Plan = { id: string; business_id?: string | null; code: string; name: string; status?: string };

export type TenantSummary = {
  id: string;
  business_id?: string | null;
  tenant_key?: string | null;
  display_name?: string | null;
  status?: string | null;
  // Set on the all-customers picker, where tenants of different customers are listed together.
  tenant_name?: string | null;
  customer_name?: string | null;
  customer_business_id?: string | null;
};

/** One customer (the legal and commercial parent) with the tenants it owns. */
export type CustomerAccount = {
  id: string;
  // The Customer ID people see (CUST000001).
  business_id?: string | null;
  customer_identifier: string;
  name: string;
  legal_name?: string | null;
  country?: string | null;
  status?: string | null;
  tenant_count: number;
  active_admins: number;
  tenants: Array<{
    id: string;
    business_id?: string | null;
    tenant_key: string;
    display_name?: string | null;
    status?: string | null;
    data_region?: string | null;
    plan_name?: string | null;
    active_admins: number;
  }>;
};

/** The environment a tenant can start with; each tenant has at most one of each type. */
export const ENVIRONMENT_TYPES = ["PRODUCTION", "VALIDATION", "SANDBOX", "UAT", "DEMO"] as const;

/** How a tenant is named in a list mixing several customers: "Customer · Tenant (KEY)". */
export const tenantOptionLabel = (tenant: TenantSummary) => {
  const tenantName = tenant.tenant_name ?? tenant.display_name ?? tenant.tenant_key ?? "Tenant";
  const owner = tenant.customer_name && tenant.customer_name !== tenantName ? `${tenant.customer_name} · ` : "";
  return `${owner}${tenantName}${tenant.tenant_key ? ` (${tenant.tenant_key})` : ""}`;
};

/** Status labels the platform administrator reads at a glance (the raw code stays in the title). */
export const statusTone = (status: unknown): "good" | "warning" | "critical" | "neutral" => {
  const value = String(status ?? "").toUpperCase();
  if (value === "ACTIVE") return "good";
  if (["INVITED", "PROVISIONED", "PROVISIONING", "DRAFT", "EXPIRING_SOON"].includes(value)) return "warning";
  if (["SUSPENDED", "EXPIRED", "TERMINATED", "OFFBOARDED", "FAILED"].includes(value)) return "critical";
  return "neutral";
};

export const titleCase = (value: unknown) =>
  String(value ?? "")
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/^\w/, (letter) => letter.toUpperCase());

/** Names whose spelling titleCase would mangle (OIDC, OpenAI, TrackWise…), keyed by their lower-case code. */
const KNOWN_NAMES: Record<string, string> = {
  oidc: "OIDC",
  saml: "SAML",
  saml2: "SAML",
  openai: "OpenAI",
  azure_openai: "Azure OpenAI",
  anthropic: "Anthropic",
  trackwise: "TrackWise",
  trackwise_digital: "TrackWise Digital",
  veeva: "Veeva",
  veeva_vault: "Veeva Vault",
  mastercontrol: "MasterControl",
  sap: "SAP",
  sap_s4hana: "SAP S/4HANA",
  servicenow: "ServiceNow",
  salesforce: "Salesforce",
  sharepoint: "SharePoint",
  rest: "REST API",
  rest_api: "REST API",
  api: "API",
  sftp: "SFTP",
  csv: "CSV",
  csv_upload: "CSV upload",
  file: "File upload",
  file_upload: "File upload",
  jdbc: "Database (JDBC)",
  odbc: "Database (ODBC)",
  database: "Database",
  webhook: "Webhook",
  qms: "QMS",
  erp: "ERP",
  plm: "PLM",
  crm: "CRM",
  lims: "LIMS",
  mes: "MES",
  mfa: "MFA",
  sso: "SSO",
  ai: "AI",
  llm: "AI model",
};

/**
 * A code or system name as people read it: known names keep their spelling (OIDC, OpenAI, TrackWise), event names
 * and record types read as words ("tenant.created" -> "Tenant created", "MappingConfiguration" -> "Mapping
 * configuration"), a name already written for people ("Veeva Vault QMS") is kept, and anything else reads like
 * titleCase.
 */
export const displayCode = (value: unknown) => {
  const raw = String(value ?? "").trim();
  if (!raw) return "";
  const key = raw.toLowerCase().replace(/[\s-]+/g, "_");
  if (KNOWN_NAMES[key]) return KNOWN_NAMES[key];
  const mixedCase = raw !== raw.toUpperCase() && raw !== raw.toLowerCase();
  if (mixedCase && /\s/.test(raw) && !/[._]/.test(raw)) return raw;
  // "MappingConfiguration" -> "Mapping Configuration" before the words are read.
  const words = mixedCase && !/[\s._-]/.test(raw) ? raw.replace(/([a-z0-9])([A-Z])/g, "$1 $2") : raw;
  return words
    .split(/[._\s-]+/)
    .filter(Boolean)
    .map((word, index) => {
      // Inside a longer name only single-word spellings apply (OIDC, API), not descriptions ("File upload").
      const known = KNOWN_NAMES[word.toLowerCase()];
      if (known && !known.includes(" ")) return known;
      const lower = word.toLowerCase();
      return index === 0 ? lower.replace(/^\w/, (letter) => letter.toUpperCase()) : lower;
    })
    .join(" ");
};

/** A customer or tenant that has not been active yet: "Activate" makes it active for the first time. */
export const NEW_STATES = [
  "DRAFT",
  "PENDING_APPROVAL",
  "PROVISIONING",
  "PROVISIONED",
  "PENDING_CUSTOMER_ACTIVATION",
] as const;

/** A customer in one of these states lets its tenants be used (and accepts new tenants). */
export const ACCESS_STATES = ["ACTIVE", "EXPIRING_SOON"] as const;

export type StatusAction = { target: "ACTIVE" | "SUSPENDED"; verb: "Activate" | "Deactivate" | "Reactivate" };

/**
 * The one status change offered for a customer or tenant: a new one is activated, a running one deactivated
 * (a reversible suspend), and an inactive or expired one reactivated. Terminated or archived records have none.
 */
export const statusAction = (status: unknown): StatusAction | null => {
  const value = String(status ?? "").toUpperCase();
  if ((NEW_STATES as readonly string[]).includes(value)) return { target: "ACTIVE", verb: "Activate" };
  if (value === "SUSPENDED" || value === "EXPIRED") return { target: "ACTIVE", verb: "Reactivate" };
  if ((ACCESS_STATES as readonly string[]).includes(value)) return { target: "SUSPENDED", verb: "Deactivate" };
  return null;
};

/** The MDARIX operator organization is never deactivated (the server refuses with OPERATOR_PROTECTED). */
export const customerStatusAction = (status: unknown, isOperator?: unknown): StatusAction | null => {
  const action = statusAction(status);
  return isOperator === true && action?.target === "SUSPENDED" ? null : action;
};

/** A tenant can be activated only once provisioning has finished; earlier states have no status change. */
export const TENANT_ACTIVATABLE = ["PROVISIONED", "PENDING_CUSTOMER_ACTIVATION"] as const;
export const tenantStatusAction = (status: unknown): StatusAction | null => {
  const action = statusAction(status);
  if (action?.verb !== "Activate") return action;
  return (TENANT_ACTIVATABLE as readonly string[]).includes(String(status ?? "").toUpperCase()) ? action : null;
};

/** The status a change moves to (kept for callers that only need the target). */
export const lifecycleAction = (status: unknown): "ACTIVE" | "SUSPENDED" | null => statusAction(status)?.target ?? null;

/** Whether a customer's own status lets its tenants be used. */
export const customerGivesAccess = (status: unknown) =>
  (ACCESS_STATES as readonly string[]).includes(String(status ?? "").toUpperCase());

/** A status as the Customers & Tenants screens name it: a suspended customer or tenant is "Inactive". */
export const lifecycleStatusLabel = (status: unknown) => {
  const value = String(status ?? "").toUpperCase();
  if (!value) return "Unknown";
  if (value === "SUSPENDED") return "Inactive";
  return titleCase(value);
};

/** A tenant whose own status is fine but whose customer is inactive, so nobody can sign in to it. */
export const blockedByCustomer = (row: { effective_access?: unknown } | null | undefined) =>
  String(row?.effective_access ?? "").toUpperCase() === "BLOCKED_BY_CUSTOMER";

/**
 * Why a tenant cannot be activated or reactivated now (its customer is not active), or null when it can. An unknown
 * customer status leaves the decision to the server.
 */
export const tenantActivationBlock = (customerName: string | null | undefined, customerStatus: unknown) => {
  const value = String(customerStatus ?? "").toUpperCase();
  if (!value || customerGivesAccess(value)) return null;
  const name = customerName || "this tenant's customer";
  if (value === "SUSPENDED") return `Its customer ${name} is inactive; reactivate the customer first.`;
  if ((NEW_STATES as readonly string[]).includes(value))
    return `Its customer ${name} is not active yet; activate the customer first.`;
  return `Its customer ${name} is ${lifecycleStatusLabel(value).toLowerCase()}; reactivate the customer first.`;
};

/** A tenant counted in a customer's deactivation: every tenant whose own status still lets it be used. */
export const tenantsLosingAccess = (tenants: Array<{ status?: unknown }>) =>
  tenants.filter((tenant) => statusAction(tenant.status)?.target === "SUSPENDED").length;

/** The tenants a customer's status change reached, as the server reports them. */
export type TenantAffected = {
  tenant_id: string;
  business_id?: string | null;
  name?: string | null;
  effective_access?: string | null;
};

/** One line after a customer's status change, naming the tenants it reached. */
export const customerStatusResult = (name: string, verb: StatusAction["verb"], affected: TenantAffected[] = []) => {
  const done =
    verb === "Deactivate"
      ? `${name} is inactive.`
      : verb === "Reactivate"
        ? `${name} is active again.`
        : `${name} is active.`;
  if (!affected.length) return `${done} It has no tenants.`;
  const names = affected.map((tenant) => tenant.name || tenant.business_id || "Unnamed tenant");
  const listed = names.length > 5 ? `${names.slice(0, 5).join(", ")} and ${names.length - 5} more` : names.join(", ");
  if (verb === "Deactivate") return `${done} Nobody can sign in to ${listed}.`;
  const open = affected.filter((tenant) => String(tenant.effective_access ?? "").toUpperCase() === "ACTIVE").length;
  return `${done} ${open} of ${affected.length} tenant${affected.length === 1 ? "" : "s"} can be used again: ${listed}.`;
};

// ---- Editing details -------------------------------------------------------------------------------------------

/** The least and most a reason for a change may be (the server enforces the same). */
export const REASON_MIN = 10;
export const REASON_MAX = 1000;

export type FieldSpec = { key: string; label: string; required?: boolean; type?: "text" | "email" | "url" | "tel" };
export type FieldGroup = { title: string; fields: FieldSpec[] };

/** The customer details a platform administrator maintains (identifiers are not editable). */
export const CUSTOMER_FIELD_GROUPS: FieldGroup[] = [
  {
    title: "Company",
    fields: [
      { key: "legal_name", label: "Legal name", required: true },
      { key: "display_name", label: "Display name", required: true },
      { key: "trading_name", label: "Trading name" },
      { key: "customer_type", label: "Customer type", required: true },
      { key: "industry", label: "Industry" },
      { key: "company_size", label: "Company size" },
      { key: "website", label: "Website", type: "url" },
      { key: "crm_reference", label: "CRM reference" },
    ],
  },
  {
    title: "Location",
    fields: [
      { key: "country", label: "Country", required: true },
      { key: "state_province", label: "State or province" },
      { key: "headquarters", label: "Headquarters" },
    ],
  },
  {
    title: "Contacts",
    fields: [
      { key: "primary_business_contact.name", label: "Business contact name" },
      { key: "primary_business_contact.email", label: "Business contact email", type: "email" },
      { key: "primary_business_contact.phone", label: "Business contact phone", type: "tel" },
      { key: "billing_contact.name", label: "Billing contact name" },
      { key: "billing_contact.email", label: "Billing contact email", type: "email" },
      { key: "billing_contact.phone", label: "Billing contact phone", type: "tel" },
    ],
  },
  {
    title: "MDARIX account team",
    fields: [
      { key: "internal_account_owner", label: "Account owner" },
      { key: "implementation_manager", label: "Implementation manager" },
    ],
  },
];

/** The tenant details a platform administrator maintains (the tenant key and IDs are not editable). */
export const TENANT_TYPES = ["STANDARD", "ENTERPRISE", "PRIVATE_DEPLOYMENT"] as const;
export const TENANT_FIELD_GROUPS: FieldGroup[] = [
  {
    title: "Tenant",
    fields: [
      { key: "display_name", label: "Display name", required: true },
      { key: "name", label: "Name", required: true },
      { key: "tenant_type", label: "Tenant type", required: true },
      { key: "deployment_model", label: "Deployment", required: true },
      { key: "configuration_version", label: "Configuration version" },
    ],
  },
  {
    title: "Regions",
    fields: [
      { key: "primary_region", label: "Primary region", required: true },
      { key: "residency_region", label: "Data residency", required: true },
      { key: "database_region", label: "Database region" },
      { key: "storage_region", label: "Storage region" },
    ],
  },
];

export type FormValues = { [key: string]: string };

/**
 * Only the fields the record carries (a field the server does not return cannot be shown or edited), and only the
 * groups that keep at least one field.
 */
export const presentGroups = (record: { [key: string]: unknown } | null | undefined, groups: FieldGroup[]) =>
  groups
    .map((group) => ({ ...group, fields: group.fields.filter((field) => field.key.split(".")[0] in (record ?? {})) }))
    .filter((group) => group.fields.length > 0);

const fieldKeys = (groups: FieldGroup[]) => groups.flatMap((group) => group.fields);

const valueAt = (record: { [key: string]: unknown }, key: string): unknown => {
  const [head, tail] = key.split(".");
  const value = record[head];
  if (!tail) return value;
  return value && typeof value === "object" ? (value as { [key: string]: unknown })[tail] : undefined;
};

const asText = (value: unknown) => (value === null || value === undefined ? "" : String(value));

/** The form's starting values: every field as text, empty where the record has nothing. */
export const formFrom = (record: { [key: string]: unknown } | null | undefined, groups: FieldGroup[]): FormValues =>
  Object.fromEntries(fieldKeys(groups).map((field) => [field.key, asText(valueAt(record ?? {}, field.key)).trim()]));

/**
 * Only the fields that changed, ready to send: text trimmed, an emptied optional field as null. A contact
 * ({name, email, phone}) is sent whole when any part of it changed, or as null when all of it was cleared.
 */
export const changedFields = (
  record: { [key: string]: unknown } | null | undefined,
  form: FormValues,
  groups: FieldGroup[],
): { [key: string]: unknown } => {
  const before = formFrom(record, groups);
  const changes: { [key: string]: unknown } = {};
  const nested: { [key: string]: boolean } = {};
  for (const field of fieldKeys(groups)) {
    const now = (form[field.key] ?? "").trim();
    if (now === before[field.key]) continue;
    const [head, tail] = field.key.split(".");
    if (tail) nested[head] = true;
    else changes[head] = now === "" ? null : now;
  }
  for (const head of Object.keys(nested)) {
    const parts = fieldKeys(groups).filter((field) => field.key.startsWith(`${head}.`));
    const contact = Object.fromEntries(
      parts.map((field) => [field.key.slice(head.length + 1), (form[field.key] ?? "").trim() || null]),
    );
    changes[head] = Object.values(contact).some(Boolean) ? contact : null;
  }
  return changes;
};

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** What stops the form from being saved, one plain sentence per problem (empty when it can be saved). */
export const formProblems = (form: FormValues, groups: FieldGroup[]): string[] => {
  const problems: string[] = [];
  for (const field of fieldKeys(groups)) {
    const value = (form[field.key] ?? "").trim();
    if (field.required && !value) problems.push(`${field.label} is required.`);
    else if (value && field.type === "email" && !EMAIL.test(value)) problems.push(`${field.label} is not an email.`);
  }
  // A contact that is given at all needs a name and an email to be reachable.
  const contacts = new Set(
    fieldKeys(groups).flatMap((field) => (field.key.includes(".") ? [field.key.split(".")[0]] : [])),
  );
  for (const head of contacts) {
    const name = (form[`${head}.name`] ?? "").trim();
    const email = (form[`${head}.email`] ?? "").trim();
    const phone = (form[`${head}.phone`] ?? "").trim();
    if ((name || email || phone) && (!name || !email)) {
      const label = head === "billing_contact" ? "The billing contact" : "The business contact";
      problems.push(`${label} needs a name and an email.`);
    }
  }
  return problems;
};

/** Whether a reason is long enough (and not too long) to be recorded with a change. */
export const reasonReady = (reason: string) => {
  const length = reason.trim().length;
  return length >= REASON_MIN && length <= REASON_MAX;
};

const TRANSITION_CODES = ["INVALID_LIFECYCLE_TRANSITION", "INVALID_TENANT_TRANSITION", "INVALID_CUSTOMER_TRANSITION"];
const GATE_CODES = ["OPERATOR_PROTECTED", "CUSTOMER_NOT_ACTIVE"];
const errorParts = (error: unknown) => ({
  status: (error as { status?: unknown } | null)?.status,
  code: String((error as { code?: unknown } | null)?.code ?? "").toUpperCase(),
});

/** Whether a failure was a version conflict (someone else saved first), so the screen can offer to reload. */
export const isVersionConflict = (error: unknown) => {
  const { status, code } = errorParts(error);
  return status === 409 && !TRANSITION_CODES.includes(code) && !GATE_CODES.includes(code);
};

/** A failed change in plain words: a version conflict, nothing changed, a protected organization, a gated tenant. */
export const changeErrorText = (error: unknown, what: "customer" | "tenant", fallback: string) => {
  const { code } = errorParts(error);
  if (code === "OPERATOR_PROTECTED") return "The MDARIX operator organization can't be deactivated.";
  if (code === "CUSTOMER_NOT_ACTIVE") return "Its customer is inactive; reactivate the customer first.";
  if (code === "NO_CHANGES") return "Nothing was changed. Edit a field before saving.";
  if (isVersionConflict(error)) return `Someone else changed this ${what}; reload to see their changes.`;
  return describeError(error, fallback);
};

export const isoDate = (date: Date) => date.toISOString().slice(0, 10);
