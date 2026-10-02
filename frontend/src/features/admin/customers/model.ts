// Shapes and small helpers for the platform administrator's Customers & Tenants area.

export const SECTIONS = ["Customers", "Customer administrators", "Tenants", "Onboarding"] as const;
export type Section = (typeof SECTIONS)[number];

export type CustomerAdmin = {
  id: string;
  email: string;
  display_name: string | null;
  status: string;
  tenant_id: string;
  tenant_key: string | null;
  tenant_name?: string | null;
  customer_id: string | null;
  customer_name: string | null;
  can_suspend: boolean;
  is_last_active_admin: boolean;
  can_reactivate: boolean;
  can_resend_invitation: boolean;
  can_reset_password: boolean;
};

export type Plan = { id: string; code: string; name: string; status?: string };

export type TenantSummary = {
  id: string;
  tenant_key?: string | null;
  display_name?: string | null;
  status?: string | null;
  // Set on the all-customers picker, where tenants of different customers are listed together.
  tenant_name?: string | null;
  customer_name?: string | null;
};

/** One customer (the legal and commercial parent) with the tenants it owns. */
export type CustomerAccount = {
  id: string;
  customer_identifier: string;
  name: string;
  legal_name?: string | null;
  country?: string | null;
  status?: string | null;
  tenant_count: number;
  active_admins: number;
  tenants: Array<{
    id: string;
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

/** A suspended customer is reactivated; anything else that is running can be suspended. */
export const lifecycleAction = (status: unknown): "ACTIVE" | "SUSPENDED" | null => {
  const value = String(status ?? "").toUpperCase();
  if (value === "SUSPENDED") return "ACTIVE";
  if (value === "ACTIVE") return "SUSPENDED";
  return null;
};

export const isoDate = (date: Date) => date.toISOString().slice(0, 10);
