import { createContext, useContext } from "react";
import type { Confirmation } from "./shared";

export const SECTIONS = [
  "Dashboard",
  "Users",
  "Roles & Access",
  "Integrations",
  "Data Mapping",
  "Plan & Subscription",
  "Security",
  "Notifications",
  "Audit",
  "Organization",
] as const;

export type Section = (typeof SECTIONS)[number];

export type TenantContext = {
  user_id?: string;
  // The signed-in person's User ID and their organization's Tenant and Customer IDs (the IDs people see).
  business_id?: string | null;
  tenant_business_id?: string | null;
  customer_business_id?: string | null;
  email?: string;
  display_name?: string;
  active_role?: string | null;
  tenant_id?: string;
  environment?: string;
  current_tenant?: {
    tenant_id?: string;
    tenant_business_id?: string | null;
    tenant_name?: string;
    tenant_key?: string;
  };
  plan?: { business_id?: string | null; code?: string; name?: string; version?: string } | null;
  license?: { state?: string; effective?: boolean };
  entitlements?: Array<{ feature_code: string; enabled: boolean; limits?: Record<string, unknown> }>;
};

export type ConsoleApi = {
  context: TenantContext | null;
  open: (section: Section, tab?: string) => void;
  confirm: (request: Confirmation) => void;
  notify: (text: string, tone?: "good" | "critical") => void;
};

export const ConsoleContext = createContext<ConsoleApi>({
  context: null,
  open: () => undefined,
  confirm: () => undefined,
  notify: () => undefined,
});

export const useConsole = () => useContext(ConsoleContext);

/** Roles a Customer Administrator may give. Platform roles are never offered and are rejected by the server. */
export const ASSIGNABLE_ROLES = [
  { value: "VIEWER", label: "Viewer" },
  { value: "INVESTIGATOR", label: "Investigator" },
  { value: "REVIEWER", label: "Reviewer" },
  { value: "APPROVER", label: "Approver" },
  { value: "LEADER", label: "Leader" },
  { value: "CUSTOMER_ADMIN", label: "Customer Administrator" },
] as const;

/** Seat limit declared by the active plan, if any (same keys the server enforces). */
export function licensedSeatLimit(context: TenantContext | null): number | null {
  for (const entitlement of context?.entitlements ?? []) {
    const limits = entitlement.limits ?? {};
    const value = Number(limits.licensed_users_limit ?? limits.licensed_users);
    if (Number.isFinite(value) && value > 0) return value;
  }
  return null;
}
