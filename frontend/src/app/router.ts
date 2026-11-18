export type AppView =
  | "home"
  | "readiness"
  | "my-work"
  | "products"
  | "complaints"
  | "signals"
  | "story"
  | "persona"
  | "ask"
  | "investigations"
  | "evidence"
  | "decision"
  | "records"
  | "assurance"
  | "audit"
  | "regulatory-copilot"
  | "risk-traceability"
  | "signature-verification"
  | "next-steps"
  | "getting-started"
  | "import-data"
  | "account"
  | "feedback"
  | "look-ahead"
  | "trends"
  | "settings"
  | "team"
  | "decision-trees"
  | "reports"
  | "import"
  | "product-360"
  | "approvals"
  | "customer-admin"
  | "admin"
  | "admin-stage2"
  | "admin-product-configuration"
  | "admin-subscriptions"
  | "admin-mapping"
  | "admin-customers"
  | "admin-create-customer"
  | "admin-customer-360"
  | "admin-manage"
  | "admin-audit"
  | "admin-config-360"
  | "admin-master-data"
  | "admin-canonical-model"
  | "admin-data-mapping"
  | "admin-transformations"
  | "admin-validation"
  | "admin-baselines"
  | "admin-mapping-versions"
  | "admin-config-releases"
  | "admin-config-health"
  | "admin-config-dependencies"
  | "admin-reference-data"
  | "admin-validation-rules"
  | "admin-configuration-sets"
  | "admin-customer-baselines"
  | "admin-customer-overrides"
  | "admin-change-requests"
  | "admin-deployments"
  | "admin-import-export"
  | "admin-upgrade-center"
  | "admin-integration-registry"
  | "admin-api-registry"
  | "admin-schema-registry"
  | "admin-transformation-library"
  | "platform-customers"
  | "platform-tenants"
  | "platform-onboarding"
  | "platform-licenses"
  | "platform-tenant-health"
  | "platform-tenant-audit";

export const APP_ROUTES: Record<AppView, string> = {
  home: "/app",
  readiness: "/app/readiness",
  "my-work": "/app/my-work",
  products: "/app/products",
  complaints: "/app/complaints",
  signals: "/app/signals",
  story: "/app/story",
  persona: "/app/persona",
  ask: "/app/ask",
  investigations: "/app/investigations",
  evidence: "/app/evidence",
  decision: "/app/decision",
  records: "/app/records",
  assurance: "/app/assurance",
  audit: "/app/audit",
  "regulatory-copilot": "/app/regulatory-copilot",
  "risk-traceability": "/app/risk-traceability",
  "signature-verification": "/app/signature-verification",
  "next-steps": "/app/next-steps",
  // Sections that were named by ?section= until 0.10.67 (linkTable.json keeps the old addresses working).
  "getting-started": "/app/getting-started",
  "import-data": "/app/import-data",
  account: "/app/account",
  feedback: "/app/feedback",
  "look-ahead": "/app/look-ahead",
  // The new navigation (0.10.68, tenants.navigation = new): its screens; /app/complaints/<ref> is one complaint.
  trends: "/app/trends",
  settings: "/app/settings",
  team: "/app/team",
  // The new navigation's tabs of Release C (0.10.73): one tree per market, and the authority reports.
  "decision-trees": "/app/decision-trees",
  reports: "/app/reports",
  // A trial's own import on the new navigation (0.10.80).
  import: "/app/import",
  // Work › Products on the new navigation (0.10.94): Product 360 and Supplier 360.
  "product-360": "/app/product-360",
  // Decisions & Reports' approvals queue on the one navigation (UX2).
  approvals: "/app/approvals",
  "customer-admin": "/app/customer-admin",
  admin: "/app/admin",
  "admin-stage2": "/app/admin/stage2",
  "admin-product-configuration": "/app/admin/product-configuration",
  "admin-subscriptions": "/app/admin/subscriptions",
  "admin-mapping": "/app/admin/mapping-studio",
  "admin-customers": "/app/admin/customers",
  "admin-create-customer": "/app/admin/customers/new",
  "admin-customer-360": "/app/admin/customers/detail",
  "admin-manage": "/app/admin/customer-admins",
  "admin-audit": "/app/admin/audit",
  "admin-config-360": "/platform-admin/data-configuration",
  "admin-master-data": "/platform-admin/data-configuration/master-data",
  "admin-canonical-model": "/platform-admin/data-configuration/canonical-model",
  "admin-data-mapping": "/platform-admin/data-configuration/mappings",
  "admin-transformations": "/platform-admin/data-configuration/transformations",
  "admin-validation": "/platform-admin/data-configuration/validation",
  "admin-baselines": "/platform-admin/data-configuration/baselines",
  "admin-mapping-versions": "/platform-admin/data-configuration/mapping-versions",
  "admin-config-releases": "/platform-admin/data-configuration/releases",
  "admin-config-health": "/platform-admin/data-configuration/health",
  "admin-config-dependencies": "/platform-admin/data-configuration/dependencies",
  "admin-reference-data": "/platform-admin/data-configuration/reference-data",
  "admin-validation-rules": "/platform-admin/data-configuration/validation-rules",
  "admin-configuration-sets": "/platform-admin/data-configuration/configuration-sets",
  "admin-customer-baselines": "/platform-admin/data-configuration/customer-baselines",
  "admin-customer-overrides": "/platform-admin/data-configuration/customer-overrides",
  "admin-change-requests": "/platform-admin/data-configuration/change-requests",
  "admin-deployments": "/platform-admin/data-configuration/deployments",
  "admin-import-export": "/platform-admin/data-configuration/import-export",
  "admin-upgrade-center": "/platform-admin/data-configuration/upgrade-center",
  "admin-integration-registry": "/platform-admin/integrations/registry",
  "admin-api-registry": "/platform-admin/integrations/api-registry",
  "admin-schema-registry": "/platform-admin/integrations/schema-registry",
  "admin-transformation-library": "/platform-admin/data-configuration/transformation-library",
  "platform-customers": "/platform-admin/customers",
  "platform-tenants": "/platform-admin/tenants",
  "platform-onboarding": "/platform-admin/onboarding",
  "platform-licenses": "/platform-admin/licenses",
  "platform-tenant-health": "/platform-admin/tenant-health",
  "platform-tenant-audit": "/platform-admin/tenant-audit",
};

export function viewFromPath(pathname: string): AppView {
  const normalized = pathname.split("?")[0].replace(/\/$/, "") || "/";
  // One complaint's page (/app/complaints/<ref>) is the Complaints screen's; workspaceAddress.ts reads the reference.
  if (/^\/app\/complaints\/[^/]+$/.test(normalized)) return "complaints";
  const match = (Object.entries(APP_ROUTES) as [AppView, string][]).find(([, path]) => path === normalized);
  return match?.[0] ?? "home";
}

export function routeForView(view: AppView): string {
  return APP_ROUTES[view];
}

export function isKnownRoute(pathname: string): boolean {
  return viewFromPath(pathname) !== "home" || pathname.split("?")[0].replace(/\/$/, "") === APP_ROUTES.home;
}

export function navigateTo(view: AppView) {
  const path = routeForView(view);
  if (window.location.pathname !== path) window.history.pushState({ view }, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
