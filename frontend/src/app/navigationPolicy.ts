import type { AppView } from "./router";
import { featureSetOf, viewsForFeatureSet } from "./featureSet";

export const AUTH_ENDPOINTS = {
  session: "/api/v1/auth/session",
  signin: "/api/v1/auth/signin",
  signout: "/api/v1/auth/signout",
} as const;

export const PLATFORM_ADMIN_VIEWS: readonly AppView[] = [
  "admin",
  "admin-stage2",
  "admin-product-configuration",
  "admin-subscriptions",
  "admin-mapping",
  "admin-customers",
  "admin-create-customer",
  "admin-customer-360",
  "admin-manage",
  "admin-audit",
  "platform-customers",
  "platform-tenants",
  "platform-onboarding",
  "platform-licenses",
  "platform-tenant-health",
  "platform-tenant-audit",
  "admin-config-360",
  "admin-master-data",
  "admin-canonical-model",
  "admin-data-mapping",
  "admin-transformations",
  "admin-validation",
  "admin-baselines",
  "admin-mapping-versions",
  "admin-config-releases",
  "admin-config-health",
  "admin-config-dependencies",
  "admin-reference-data",
  "admin-validation-rules",
  "admin-configuration-sets",
  "admin-customer-baselines",
  "admin-customer-overrides",
  "admin-change-requests",
  "admin-deployments",
  "admin-import-export",
  "admin-upgrade-center",
  "admin-integration-registry",
  "admin-api-registry",
  "admin-schema-registry",
  "admin-transformation-library",
  "regulatory-copilot",
  "risk-traceability",
  "signature-verification",
];

/** The investigation workspace an Investigator works in (UserWorkspace and the screens it opens). */
export const WORKSPACE_VIEWS: readonly AppView[] = [
  "home",
  "readiness",
  "my-work",
  "products",
  "complaints",
  "signals",
  "story",
  "persona",
  "ask",
  "investigations",
  "evidence",
  "decision",
  "records",
  "assurance",
  "audit",
  "regulatory-copilot",
  "risk-traceability",
  "signature-verification",
  // From trial to pilot: the workspace shows it in free-trial workspaces only (UserWorkspace).
  "next-steps",
];

/** A customer administrator manages their organization and, in the same account, may switch into the workspace
 * with an Investigator's rights. The server still decides every action: no signatures, no regulatory approval and
 * no platform administration for this role. */
export const CUSTOMER_ADMIN_VIEWS: readonly AppView[] = ["customer-admin", ...WORKSPACE_VIEWS];

export function isPlatformAdminRole(role?: string | null) {
  return ["ADMIN", "ADMINISTRATOR", "MDARIX ADMINISTRATOR", "PLATFORM ADMIN", "PLATFORM_ADMIN"].includes(
    (role ?? "").trim().toUpperCase(),
  );
}

export function isCustomerAdminRole(role?: string | null) {
  return ["CUSTOMER ADMIN", "CUSTOMER_ADMIN"].includes((role ?? "").trim().toUpperCase());
}

/** Which part of MDARIX the server is (session context `deployment_role`): the whole product (MULTI), the platform
 * (platform administration only) or one organization's cell (its workspace and administration only). The server
 * answers 404 for the rest; the interface does not offer it. */
export type DeploymentRole = "MULTI" | "PLATFORM" | "CELL";

export function viewsForDeployment(
  views: readonly AppView[] | null,
  deploymentRole?: string | null,
): readonly AppView[] | null {
  if (!views) return views;
  const role = (deploymentRole ?? "MULTI").trim().toUpperCase();
  if (role === "PLATFORM") return views.filter((view) => !WORKSPACE_VIEWS.includes(view) && view !== "customer-admin");
  if (role === "CELL") return views.filter((view) => WORKSPACE_VIEWS.includes(view) || view === "customer-admin");
  return views;
}

/** The views a role may open on this deployment; under the `mvp` feature set the parked views are left out
 * (featureSet.ts). Null for business roles: their workspace filters its own sections and tabs. */
export function allowedViewsForRole(
  role?: string | null,
  deploymentRole?: string | null,
  featureSet?: string | null,
): readonly AppView[] | null {
  const features = featureSetOf(featureSet);
  if (isPlatformAdminRole(role))
    return viewsForFeatureSet(viewsForDeployment(PLATFORM_ADMIN_VIEWS, deploymentRole), features);
  if (isCustomerAdminRole(role))
    return viewsForFeatureSet(viewsForDeployment(CUSTOMER_ADMIN_VIEWS, deploymentRole), features);
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
    if (typeof detail === "object" && detail !== null && "message" in detail)
      return String((detail as { message: unknown }).message);
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

export const MOBILE_FOCUS_ORDER = ["menu", "user-context", "primary-content", "logout"] as const;
