import { useEffect, useState } from "react";
import { PublicMegaSite } from "../PublicMegaSite";
import { AppView, navigateTo, viewFromPath } from "./router";
import { Stage2AdminControlPlane } from "../features/stage2/Stage2AdminControlPlane";
import { MappingStudio } from "../features/stage2/MappingStudio";
import { SubscriptionAdministration } from "../features/stage2/SubscriptionAdministration";
import { allowedViewsForRole, isCustomerAdminRole, isPlatformAdminRole } from "./navigationPolicy";
import { requestJson } from "./apiClient";
import { api } from "./api";
import { PlatformProductConfiguration } from "../features/stage2/PlatformProductConfiguration";
import { ConsentBanner } from "../features/shared/ConsentBanner";
import { CustomerAdminControlPlane } from "../features/customer-admin/CustomerAdminControlPlane";
import { PlatformAdminScreen } from "../features/admin/PlatformAdminScreen";
import { RegulatoryCopilot } from "../features/regulatory/RegulatoryCopilot";
import { RiskTraceabilityWorkspace } from "../features/risk/RiskTraceabilityWorkspace";
import { SignatureVerificationWorkspace } from "../features/signature/SignatureVerificationWorkspace";
import { SimplifiedPlatformAdminScreen } from "../features/admin/SimplifiedPlatformAdminScreen";
import { UserWorkspace } from "../features/workspace/UserWorkspace";
import { PlatformAdministrationAudit } from "../features/admin/PlatformAdministrationAudit";
import { AuthPage } from "../features/auth/AuthPage";

export function App() {
  const publicPath = window.location.pathname;
  if (
    publicPath === "/" ||
    [
      // Current website pages.
      "/platform",
      "/solutions",
      "/product-lifecycle",
      "/trust",
      "/resources",
      "/company",
      // Former pages; the site redirects them to the section that now holds their content.
      "/why-mdarix",
      "/pricing",
      "/plans",
      "/roadmap",
      "/capabilities",
      "/ai-trust",
      "/integrations",
      "/security",
      "/request-demo",
      // Match whole path segments only, so app routes such as /platform-admin/... are never sent to the website.
    ].some((route) => publicPath === route || publicPath.startsWith(`${route}/`))
  )
    return <PublicMegaSite path={publicPath} />;
  if (
    [
      "/signin",
      "/signup",
      "/forgot-password",
      "/verify-email",
      "/activate-account",
      "/reset-password",
      "/mfa",
    ].includes(publicPath)
  )
    return <AuthPage mode={publicPath.slice(1)} />;
  return <PrivateApplicationGate />;
}

// Older customer screens open the platform console on the matching Customers & Tenants section.
const CUSTOMER_CONSOLE_VIEWS: Partial<Record<AppView, string>> = {
  "platform-tenants": "Customers",
  "platform-customers": "Customers",
  "admin-customers": "Customers",
  "admin-customer-360": "Customers",
  "admin-manage": "Customer administrators",
  "admin-create-customer": "Onboarding",
  "platform-onboarding": "Onboarding",
  // Former full-screen registries now open their section of the console.
  "admin-integration-registry": "Integrations:Connector catalog",
  "admin-api-registry": "Operations:Developer API",
};

export function PrivateApplicationGate() {
  const [state, setState] = useState<"CHECKING" | "AUTHORIZED" | "DENIED">("CHECKING");
  useEffect(() => {
    requestJson("/api/v1/auth/session", { retries: 0, timeoutMs: 10000 })
      .then(() => setState("AUTHORIZED"))
      .catch(() => setState("DENIED"));
  }, []);
  useEffect(() => {
    if (state === "DENIED") window.location.replace(`/signin?returnTo=${encodeURIComponent(window.location.pathname)}`);
  }, [state]);
  if (state !== "AUTHORIZED")
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <span className="eyebrow">MDARIX secure application</span>
          <h1>{state === "CHECKING" ? "Checking your session…" : "Sign in required"}</h1>
          <p>Customer application routes require an authenticated session.</p>
        </div>
      </div>
    );
  return <PrivateApplication />;
}

export function PrivateApplication() {
  const [securityContext, setSecurityContext] = useState<{
    display_name: string;
    active_role: string | null;
    tenant_id?: string;
    personas?: Array<{ code: string; label: string }>;
    allowed_menu?: string[];
    environment?: string;
    memberships?: Array<{ tenant_id: string; tenant_key: string; tenant_name: string; is_default: boolean }>;
    current_tenant?: { tenant_id: string; tenant_name?: string };
    entitlements?: Array<{ feature_code: string; enabled: boolean; limits?: Record<string, unknown> }>;
  } | null>(null);
  const [contextState, setContextState] = useState<"LOADING" | "READY" | "ERROR">("LOADING");
  const [activeView, setActiveView] = useState<AppView>(() => viewFromPath(window.location.pathname));

  useEffect(() => {
    api<any>("/api/v1/session/context")
      .then((value) => {
        const role = String(value.active_role ?? "")
          .trim()
          .toUpperCase();
        const current = viewFromPath(window.location.pathname);
        const allowed = allowedViewsForRole(role);
        const target: AppView =
          isPlatformAdminRole(role) && !allowed?.includes(current)
            ? "admin"
            : isCustomerAdminRole(role) && current !== "customer-admin"
              ? "customer-admin"
              : current;
        setSecurityContext(value);
        setActiveView(target);
        if (target !== current) navigateTo(target);
        const tenant = value.current_tenant?.tenant_name ?? "MDARIX";
        document.title = `${tenant} · MDARIX`;
        document.documentElement.style.setProperty("--tenant-accent", "#087b73");
        setContextState("READY");
      })
      .catch(() => {
        setSecurityContext(null);
        setContextState("ERROR");
      });
  }, []);
  useEffect(() => {
    const onPopState = () => setActiveView(viewFromPath(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);
  const changeView = (view: AppView) => {
    setActiveView(view);
    navigateTo(view);
  };

  const activeRole = securityContext?.active_role?.trim().toUpperCase();
  const isPlatformAdmin = isPlatformAdminRole(activeRole);
  const isCustomerAdmin = isCustomerAdminRole(activeRole);

  useEffect(() => {
    if (isPlatformAdmin && !allowedViewsForRole(activeRole)?.includes(activeView)) changeView("admin");
    if (isCustomerAdmin && activeView !== "customer-admin") changeView("customer-admin");
  }, [isPlatformAdmin, isCustomerAdmin]);

  if (contextState !== "READY")
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <span className="eyebrow">MDARIX secure application</span>
          <h1>{contextState === "LOADING" ? "Loading your workspace…" : "Workspace unavailable"}</h1>
          <p>
            {contextState === "LOADING"
              ? "Applying your tenant, role, and permission context."
              : "Your authorized tenant context could not be loaded. Please sign in again."}
          </p>
          {contextState === "ERROR" && (
            <a className="primary-action" href="/signin">
              Return to sign in
            </a>
          )}
        </div>
      </div>
    );

  // Non-admin users: the user workspace owns navigation, product context and sign-out.
  if (!isPlatformAdmin && !isCustomerAdmin)
    return (
      <>
        <UserWorkspace session={securityContext} initialView={activeView} />
        <ConsentBanner />
      </>
    );

  return (
    <div
      className={`app-shell ${isPlatformAdmin ? "platform-admin-shell" : ""} ${isCustomerAdmin ? "customer-admin-shell" : "quality-shell"}`}
    >
      <main>
        {isPlatformAdmin &&
          activeView !== "admin" &&
          [
            "admin-stage2",
            "admin-product-configuration",
            "admin-subscriptions",
            "admin-mapping",
            "admin-customers",
            "admin-create-customer",
            "admin-customer-360",
            "admin-manage",
            "admin-audit",
          ].includes(activeView) && (
            <div className="platform-admin-return-bar">
              <button onClick={() => changeView("admin")}>← Platform administration</button>
              <span>Controlled workspace</span>
            </div>
          )}
        {activeView === "customer-admin" && (
          <CustomerAdminControlPlane securityContext={securityContext} onNavigate={changeView} />
        )}
        {activeView === "regulatory-copilot" && <RegulatoryCopilot />}
        {activeView === "risk-traceability" && <RiskTraceabilityWorkspace />}
        {activeView === "signature-verification" && <SignatureVerificationWorkspace />}
        {isPlatformAdmin && (activeView === "admin" || activeView in CUSTOMER_CONSOLE_VIEWS) && (
          <SimplifiedPlatformAdminScreen
            key={activeView}
            securityContext={securityContext}
            onNavigate={changeView}
            initialSection={CUSTOMER_CONSOLE_VIEWS[activeView] ?? "Overview"}
          />
        )}
        {isPlatformAdmin &&
          [
            "platform-tenant-health",
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
            "admin-schema-registry",
            "admin-transformation-library",
          ].includes(activeView) && (
            <PlatformAdminScreen
              securityContext={securityContext}
              onNavigate={changeView}
              initialItem={
                (
                  {
                    "admin-config-360": "Configuration 360",
                    "admin-master-data": "Master data",
                    "admin-canonical-model": "Canonical data model",
                    "admin-data-mapping": "Data mapping",
                    "admin-transformations": "Transformation library",
                    "admin-validation": "Validation & data quality",
                    "admin-baselines": "Customer baselines & overrides",
                    "admin-mapping-versions": "Mapping versions",
                    "admin-config-releases": "Configuration releases",
                    "admin-config-health": "Configuration health",
                    "admin-config-dependencies": "Dependencies & impact",
                    "admin-reference-data": "Reference data",
                    "admin-validation-rules": "Validation rules",
                    "admin-configuration-sets": "Configuration sets",
                    "admin-customer-baselines": "Customer baselines",
                    "admin-customer-overrides": "Customer overrides",
                    "admin-change-requests": "Change requests",
                    "admin-deployments": "Deployments",
                    "admin-import-export": "Import / Export",
                    "admin-upgrade-center": "Upgrade center",
                    "admin-schema-registry": "Schema registry",
                    "admin-transformation-library": "Transformation library",
                  } as Record<string, string>
                )[activeView]
              }
            />
          )}
        {activeView === "admin-stage2" && <Stage2AdminControlPlane />}
        {isPlatformAdmin && activeView === "admin-product-configuration" && <PlatformProductConfiguration />}
        {activeView === "admin-subscriptions" && <SubscriptionAdministration />}
        {activeView === "admin-mapping" && <MappingStudio />}
        {activeView === "admin-audit" && <PlatformAdministrationAudit />}
        {isPlatformAdmin && activeView === "platform-licenses" && <SubscriptionAdministration />}
        {isPlatformAdmin && activeView === "platform-tenant-audit" && <PlatformAdministrationAudit />}
      </main>
      <ConsentBanner />
    </div>
  );
}
