// Shapes and small helpers for the platform administrator's Customers & Tenants area.

export const SECTIONS = ["Customers", "Customer administrators", "Tenants", "Onboarding"] as const;
export type Section = (typeof SECTIONS)[number];

export type CustomerRow = {
  id: string; // tenant id (one row per customer tenant)
  customer_id: string | null;
  customer_identifier?: string | null;
  name?: string | null;
  tenant_key?: string | null;
  primary_admin?: string | null;
  primary_admin_email?: string | null;
  plan_code?: string | null;
  plan_name?: string | null;
  expires_at?: string | null;
  seat_usage?: number | null;
  seat_cap?: number | null;
  status?: string | null;
  data_region?: string | null;
};

export type CustomerAdmin = {
  id: string;
  email: string;
  display_name: string | null;
  status: string;
  tenant_id: string;
  tenant_key: string | null;
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
