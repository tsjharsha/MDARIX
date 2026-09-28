import type { AppView } from "./router";

export const AUTH_ENDPOINTS = { session: "/api/v1/auth/session", signin: "/api/v1/auth/signin", signout: "/api/v1/auth/signout" } as const;

export const PLATFORM_ADMIN_VIEWS: readonly AppView[] = [
  "admin", "admin-stage2", "admin-product-configuration", "admin-subscriptions", "admin-mapping",
  "admin-customers", "admin-create-customer", "admin-customer-360",
  "admin-manage", "admin-audit", "platform-customers", "platform-tenants", "platform-onboarding",
  "platform-licenses", "platform-tenant-health", "platform-tenant-audit",
  "admin-config-360", "admin-master-data", "admin-canonical-model", "admin-data-mapping", "admin-transformations",
  "admin-validation", "admin-baselines", "admin-mapping-versions", "admin-config-releases", "admin-config-health", "admin-config-dependencies",
  "admin-reference-data", "admin-validation-rules", "admin-configuration-sets", "admin-customer-baselines", "admin-customer-overrides",
  "admin-change-requests", "admin-deployments", "admin-import-export", "admin-upgrade-center", "admin-integration-registry", "admin-api-registry",
  "admin-schema-registry", "admin-transformation-library", "regulatory-copilot",
];

export const CUSTOMER_ADMIN_VIEWS: readonly AppView[] = ["customer-admin", "regulatory-copilot"];

export function isPlatformAdminRole(role?: string | null) {
  return ["ADMIN", "ADMINISTRATOR", "MDARIX ADMINISTRATOR", "PLATFORM ADMIN", "PLATFORM_ADMIN"].includes((role ?? "").trim().toUpperCase());
}

export function isCustomerAdminRole(role?: string | null) {
  return ["CUSTOMER ADMIN", "CUSTOMER_ADMIN"].includes((role ?? "").trim().toUpperCase());
}

export function allowedViewsForRole(role?: string | null): readonly AppView[] | null {
  if (isPlatformAdminRole(role)) return PLATFORM_ADMIN_VIEWS;
  if (isCustomerAdminRole(role)) return CUSTOMER_ADMIN_VIEWS;
  return null;
}

export function clearTenantScopedCache(storage: Pick<Storage, "length" | "key" | "removeItem">) {
  const keys: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key?.startsWith("mdarix:tenant:") || key?.startsWith("mdarix:context:")) keys.push(key);
  }
  keys.forEach((key) => storage.removeItem(key));
  return keys.length;
}

export function apiErrorMessage(payload: unknown, fallback = "The request could not be completed.") {
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "object" && detail !== null && "message" in detail) return String((detail as { message: unknown }).message);
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

export const MOBILE_FOCUS_ORDER = ["menu", "user-context", "primary-content", "logout"] as const;
