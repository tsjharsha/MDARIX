import { useEffect, useState } from "react";
import { PublicMegaSite } from "../PublicMegaSite";
import { AppView, navigateTo, viewFromPath } from "./router";
import { Stage2AdminControlPlane } from "../features/stage2/Stage2AdminControlPlane";
import { MappingStudio } from "../features/stage2/MappingStudio";
import { SubscriptionAdministration } from "../features/stage2/SubscriptionAdministration";
import { allowedViewsForRole, isCustomerAdminRole, isPlatformAdminRole } from "./navigationPolicy";
import { ApiError, requestJson } from "./apiClient";
import { signOut } from "../features/shared/session";
import { api } from "./api";
import { PlatformProductConfiguration } from "../features/stage2/PlatformProductConfiguration";
import { ConsentBanner } from "../features/shared/ConsentBanner";
import { CustomerAdminControlPlane } from "../features/customer-admin/CustomerAdminControlPlane";
import { RegulatoryCopilot } from "../features/regulatory/RegulatoryCopilot";
import { RiskTraceabilityWorkspace } from "../features/risk/RiskTraceabilityWorkspace";
import { SignatureVerificationWorkspace } from "../features/signature/SignatureVerificationWorkspace";
import { SimplifiedPlatformAdminScreen } from "../features/admin/SimplifiedPlatformAdminScreen";
import { UserWorkspace } from "../features/workspace/UserWorkspace";
import { PlatformAdministrationAudit } from "../features/admin/PlatformAdministrationAudit";
import { AuthPage } from "../features/auth/AuthPage";
import { RequestDemoPage } from "../features/auth/RequestDemoPage";

export function App() {
  const publicPath = window.location.pathname;
  if (["/signin", "/signup", "/forgot-password", "/activate-account", "/reset-password", "/mfa"].includes(publicPath))
    return <AuthPage mode={publicPath.slice(1)} />;
  if (publicPath === "/request-demo") return <RequestDemoPage />;
  // The signed-in application lives under /app and /platform-admin (router.ts). Match whole path segments, so a
  // website page such as /platform is never mistaken for /platform-admin.
  if (["/app", "/platform-admin"].some((root) => publicPath === root || publicPath.startsWith(`${root}/`)))
    return <PrivateApplicationGate />;
  // Everything else is the website: its pages, former page addresses it redirects, legal pages, and a "not found"
  // page for unknown addresses (rather than a sign-in prompt).
  return <PublicMegaSite path={publicPath} />;
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
  "platform-tenant-health": "Tenants",
  // Former Data & Configuration screens open their section of the console.
  "admin-config-360": "Data & Configuration:Mappings",
  "admin-master-data": "Data & Configuration:Customer configuration",
  "admin-canonical-model": "Data & Configuration:Data model",
  "admin-data-mapping": "Data & Configuration:Mappings",
  "admin-transformations": "Data & Configuration:Rules & reference data",
  "admin-validation": "Data & Configuration:Mappings",
  "admin-baselines": "Data & Configuration:Customer configuration",
  "admin-mapping-versions": "Data & Configuration:Mappings",
  "admin-config-releases": "Data & Configuration:Releases",
  "admin-config-health": "Data & Configuration:Mappings",
  "admin-config-dependencies": "Data & Configuration:Releases",
  "admin-reference-data": "Data & Configuration:Rules & reference data",
  "admin-validation-rules": "Data & Configuration:Rules & reference data",
  "admin-configuration-sets": "Data & Configuration:Mappings",
  "admin-customer-baselines": "Data & Configuration:Customer configuration",
  "admin-customer-overrides": "Data & Configuration:Customer configuration",
  "admin-change-requests": "Data & Configuration:Releases",
  "admin-deployments": "Data & Configuration:Releases",
  "admin-import-export": "Data & Configuration:Mappings",
  "admin-upgrade-center": "Data & Configuration:Customer configuration",
  "admin-schema-registry": "Data & Configuration:Data model",
  "admin-transformation-library": "Data & Configuration:Rules & reference data",
};

export function PrivateApplicationGate() {
  const [state, setState] = useState<"CHECKING" | "AUTHORIZED" | "DENIED">("CHECKING");
  useEffect(() => {
    requestJson<{ mfa_state?: string | null }>("/api/v1/auth/session", { retries: 0, timeoutMs: 10000 })
      .then((session) => {
        // Password checked but the second factor is still due (or must be set up first).
        if (session.mfa_state === "VERIFY") window.location.replace("/mfa");
        else if (session.mfa_state === "ENROLL") window.location.replace("/mfa?setup=1");
        else setState("AUTHORIZED");
      })
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
  const [contextState, setContextState] = useState<"LOADING" | "READY" | "ERROR" | "TRIAL_ENDED">("LOADING");
  const [trialEndedMessage, setTrialEndedMessage] = useState("");
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
      .catch((error) => {
        setSecurityContext(null);
        if (error instanceof ApiError && error.code === "TRIAL_ENDED") {
          setTrialEndedMessage(error.message);
          setContextState("TRIAL_ENDED");
        } else setContextState("ERROR");
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

  if (contextState === "TRIAL_ENDED") return <TrialEnded message={trialEndedMessage} />;
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

  // The admin consoles provide their own main landmark; other views use the shell's.
  const ownsMain =
    activeView === "customer-admin" ||
    (isPlatformAdmin && (activeView === "admin" || activeView in CUSTOMER_CONSOLE_VIEWS));
  return (
    <div
      className={`app-shell ${isPlatformAdmin ? "platform-admin-shell" : ""} ${isCustomerAdmin ? "customer-admin-shell" : "quality-shell"}`}
    >
      <div className="app-main" role={ownsMain ? undefined : "main"}>
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
        {activeView === "admin-stage2" && <Stage2AdminControlPlane />}
        {isPlatformAdmin && activeView === "admin-product-configuration" && <PlatformProductConfiguration />}
        {activeView === "admin-subscriptions" && <SubscriptionAdministration />}
        {activeView === "admin-mapping" && <MappingStudio />}
        {activeView === "admin-audit" && <PlatformAdministrationAudit />}
        {isPlatformAdmin && activeView === "platform-licenses" && <SubscriptionAdministration />}
        {isPlatformAdmin && activeView === "platform-tenant-audit" && <PlatformAdministrationAudit />}
      </div>
      <ConsentBanner />
    </div>
  );
}

/** A free trial past its end date: what happens to the data, and how to continue. */
function TrialEnded({ message }: { message: string }) {
  return (
    <main className="auth-shell" id="main">
      <div className="auth-card">
        <span className="eyebrow">Free trial</span>
        <h1>Your free trial has ended</h1>
        <p>{message || "Your MDARIX free trial has ended. Contact us to continue with your data intact."}</p>
        <p>
          Nothing is lost yet: your workspace and data are kept until the deletion date, and continuing keeps them as
          they are.
        </p>
        <a className="primary-action" href="/contact">
          Contact us to continue
        </a>
        <p className="auth-links">
          <button type="button" className="link-button" onClick={() => void signOut()}>
            Sign out
          </button>
          <a href="/trial-agreement">Free trial agreement</a>
        </p>
      </div>
    </main>
  );
}
