import { useEffect, useState } from "react";
import { PublicMegaSite } from "../PublicMegaSite";
import { AppView, navigateTo, viewFromPath } from "./router";
import { Stage2AdminControlPlane } from "../features/stage2/Stage2AdminControlPlane";
import { MappingStudio } from "../features/stage2/MappingStudio";
import { SubscriptionAdministration } from "../features/stage2/SubscriptionAdministration";
import { allowedViewsForRole, isCustomerAdminRole, isPlatformAdminRole } from "./navigationPolicy";
import { ApiError, requestJson, signInPath } from "./apiClient";
import { SectionErrorBoundary } from "./ErrorBoundary";
import {
  canSwitchToWorkspace,
  customerAdminDestination,
  rememberMode,
  rememberedMode,
  type CustomerAdminMode,
} from "./consoleChoice";
import { SessionTimeoutWatch } from "../features/shared/SessionTimeout";
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
import { PilotGuidePage } from "../features/help/PilotGuidePage";

export function App() {
  const publicPath = window.location.pathname;
  if (["/signin", "/signup", "/forgot-password", "/activate-account", "/reset-password", "/mfa"].includes(publicPath))
    return <AuthPage mode={publicPath.slice(1)} />;
  if (publicPath === "/request-demo") return <RequestDemoPage />;
  if (publicPath === "/help/pilot-guide") return <PilotGuidePage />;
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
  "admin-manage": "Identity & Access:Customer administrators",
  "admin-create-customer": "New customer",
  "platform-onboarding": "Identity & Access:Onboarding",
  // Former full-screen registries now open their section of the console.
  "admin-integration-registry": "Data & Integrations:Connector catalog",
  "admin-api-registry": "Operations:Developer API",
  "platform-tenant-health": "Tenants",
  // Former Data & Configuration screens open their section of the console.
  "admin-config-360": "Data & Integrations:Mappings",
  "admin-master-data": "Data & Integrations:Customer configuration",
  "admin-canonical-model": "Data & Integrations:Data model",
  "admin-data-mapping": "Data & Integrations:Mappings",
  "admin-transformations": "Data & Integrations:Rules & reference data",
  "admin-validation": "Data & Integrations:Mappings",
  "admin-baselines": "Data & Integrations:Customer configuration",
  "admin-mapping-versions": "Data & Integrations:Mappings",
  "admin-config-releases": "Data & Integrations:Releases",
  "admin-config-health": "Data & Integrations:Mappings",
  "admin-config-dependencies": "Data & Integrations:Releases",
  "admin-reference-data": "Data & Integrations:Rules & reference data",
  "admin-validation-rules": "Data & Integrations:Rules & reference data",
  "admin-configuration-sets": "Data & Integrations:Mappings",
  "admin-customer-baselines": "Data & Integrations:Customer configuration",
  "admin-customer-overrides": "Data & Integrations:Customer configuration",
  "admin-change-requests": "Data & Integrations:Releases",
  "admin-deployments": "Data & Integrations:Releases",
  "admin-import-export": "Data & Integrations:Mappings",
  "admin-upgrade-center": "Data & Integrations:Customer configuration",
  "admin-schema-registry": "Data & Integrations:Data model",
  "admin-transformation-library": "Data & Integrations:Rules & reference data",
};

/** The session check failed for a reason that is not "signed out": the server could not be reached or failed. */
const isOutage = (error: unknown) => error instanceof ApiError && (error.status === 0 || error.status >= 500);
// Retry an unreachable server after 2, 4, 8 … seconds, at most every 30 seconds.
const retryDelay = (attempt: number) => Math.min(30_000, 2000 * 2 ** attempt);

export function PrivateApplicationGate() {
  const [state, setState] = useState<"CHECKING" | "AUTHORIZED" | "UNREACHABLE">("CHECKING");
  useEffect(() => {
    let attempt = 0;
    let timer: number | undefined;
    let active = true;
    const check = () =>
      requestJson<{ mfa_state?: string | null }>("/api/v1/auth/session", {
        retries: 0,
        timeoutMs: 10000,
        // This check decides where to go itself: never signed in is not "your session expired".
        redirectOnUnauthorized: false,
      })
        .then((session) => {
          if (!active) return;
          // Password checked but the second factor is still due (or must be set up first).
          if (session.mfa_state === "VERIFY") window.location.replace("/mfa");
          else if (session.mfa_state === "ENROLL") window.location.replace("/mfa?setup=1");
          else setState("AUTHORIZED");
        })
        .catch((error) => {
          if (!active) return;
          // A server that is down or restarting is not a sign-out: say so and keep trying.
          if (isOutage(error)) {
            setState("UNREACHABLE");
            timer = window.setTimeout(check, retryDelay(attempt++));
            return;
          }
          const idle = error instanceof ApiError && error.code === "SESSION_IDLE_TIMEOUT";
          window.location.replace(signInPath(idle ? "idle" : undefined, window.location));
        });
    void check();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, []);
  if (state !== "AUTHORIZED")
    return (
      <div className="auth-shell">
        <div className="auth-card" role={state === "UNREACHABLE" ? "status" : undefined}>
          <span className="eyebrow">MDARIX secure application</span>
          <h1>{state === "CHECKING" ? "Checking your session…" : "MDARIX is not reachable, retrying"}</h1>
          <p>
            {state === "CHECKING"
              ? "Customer application routes require an authenticated session."
              : "You are still signed in. MDARIX opens as soon as the connection is back; you do not need to sign in again."}
          </p>
        </div>
      </div>
    );
  return <PrivateApplication />;
}

type SecurityContext = {
  display_name: string;
  active_role: string | null;
  tenant_id?: string;
  personas?: Array<{ code: string; label: string }>;
  allowed_menu?: string[];
  environment?: string;
  memberships?: Array<{ tenant_id: string; tenant_key: string; tenant_name: string; is_default: boolean }>;
  current_tenant?: { tenant_id: string; tenant_name?: string };
  entitlements?: Array<{ feature_code: string; enabled: boolean; limits?: Record<string, unknown> }>;
};

export function PrivateApplication() {
  const [securityContext, setSecurityContext] = useState<SecurityContext | null>(null);
  const [contextState, setContextState] = useState<"LOADING" | "READY" | "ERROR" | "UNREACHABLE" | "TRIAL_ENDED">(
    "LOADING",
  );
  const [contextError, setContextError] = useState<ApiError | null>(null);
  const [loadKey, setLoadKey] = useState(0);
  const [trialEndedMessage, setTrialEndedMessage] = useState("");
  const [activeView, setActiveView] = useState<AppView>(() => viewFromPath(window.location.pathname));
  const [adminMode, setAdminMode] = useState<CustomerAdminMode>(() => rememberedMode());

  useEffect(() => {
    let timer: number | undefined;
    let active = true;
    api<any>("/api/v1/session/context")
      .then((value) => {
        if (!active) return;
        const role = String(value.active_role ?? "")
          .trim()
          .toUpperCase();
        const current = viewFromPath(window.location.pathname);
        const allowed = allowedViewsForRole(role);
        let target: AppView = current;
        if (isPlatformAdminRole(role) && !allowed?.includes(current)) target = "admin";
        else if (isCustomerAdminRole(role)) {
          const destination = customerAdminDestination(current, rememberedMode(), allowed);
          target = destination.view;
          setAdminMode(destination.mode);
        }
        setSecurityContext(value);
        setActiveView(target);
        if (target !== current) navigateTo(target);
        const tenant = value.current_tenant?.tenant_name ?? "MDARIX";
        document.title = `${tenant} · MDARIX`;
        document.documentElement.style.setProperty("--tenant-accent", "#087b73");
        setContextState("READY");
      })
      .catch((error) => {
        if (!active) return;
        setSecurityContext(null);
        if (error instanceof ApiError && error.code === "TRIAL_ENDED") {
          setTrialEndedMessage(error.message);
          setContextState("TRIAL_ENDED");
        } else if (isOutage(error)) {
          // Not a sign-out: keep the page and try again shortly.
          setContextError(error);
          setContextState("UNREACHABLE");
          timer = window.setTimeout(() => setLoadKey((key) => key + 1), retryDelay(Math.min(loadKey, 4)));
        } else {
          setContextError(error instanceof ApiError ? error : null);
          setContextState("ERROR");
        }
      });
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [loadKey]);
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
  const allowedViews = allowedViewsForRole(activeRole);

  useEffect(() => {
    if (isPlatformAdmin && !allowedViews?.includes(activeView)) changeView("admin");
    if (isCustomerAdmin) {
      // Back and forward between the console and the workspace follow the address.
      const destination = customerAdminDestination(activeView, adminMode, allowedViews);
      if (destination.mode !== adminMode) setAdminMode(destination.mode);
      if (destination.view !== activeView) changeView(destination.view);
    }
  }, [isPlatformAdmin, isCustomerAdmin, activeView]);

  const switchTo = (mode: CustomerAdminMode) => {
    rememberMode(mode);
    setAdminMode(mode);
    changeView(mode === "workspace" ? "home" : "customer-admin");
  };

  if (contextState === "TRIAL_ENDED") return <TrialEnded message={trialEndedMessage} />;
  if (contextState !== "READY")
    return (
      <div className="auth-shell">
        <div className="auth-card" role={contextState === "LOADING" ? undefined : "status"}>
          <span className="eyebrow">MDARIX secure application</span>
          <h1>
            {contextState === "LOADING"
              ? "Loading your workspace…"
              : contextState === "UNREACHABLE"
                ? "MDARIX is not reachable, retrying"
                : "Workspace unavailable"}
          </h1>
          <p>
            {contextState === "LOADING"
              ? "Applying your tenant, role, and permission context."
              : contextState === "UNREACHABLE"
                ? "You are still signed in. Your workspace opens as soon as MDARIX answers again."
                : (contextError?.message ?? "Your organization's workspace could not be loaded.")}
          </p>
          {contextError?.requestId && contextState !== "LOADING" && (
            <p className="auth-links">
              Reference for support: <code>{contextError.requestId}</code>
            </p>
          )}
          {contextState === "ERROR" && (
            <p className="auth-links">
              <button type="button" className="primary-action" onClick={() => setLoadKey((key) => key + 1)}>
                Try again
              </button>{" "}
              <a href="/signin">Return to sign in</a>
            </p>
          )}
        </div>
      </div>
    );

  // Business users, and a customer administrator who switched into the workspace: the user workspace owns
  // navigation, product context and sign-out.
  if ((!isPlatformAdmin && !isCustomerAdmin) || (isCustomerAdmin && adminMode === "workspace"))
    return (
      <>
        <SectionErrorBoundary name="The workspace">
          <UserWorkspace
            session={securityContext}
            initialView={activeView}
            onAdminConsole={isCustomerAdmin ? () => switchTo("console") : undefined}
          />
        </SectionErrorBoundary>
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
      {/* The customer-admin console runs its own idle sign-out; every other screen here uses this one. */}
      {activeView !== "customer-admin" && <SessionTimeoutWatch />}
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
        <SectionErrorBoundary name="This screen" resetKey={activeView}>
          {activeView === "customer-admin" && (
            <CustomerAdminControlPlane
              securityContext={securityContext}
              onNavigate={changeView}
              onOpenWorkspace={canSwitchToWorkspace(allowedViews) ? () => switchTo("workspace") : undefined}
            />
          )}
          {activeView === "regulatory-copilot" && <RegulatoryCopilot />}
          {activeView === "risk-traceability" && <RiskTraceabilityWorkspace />}
          {activeView === "signature-verification" && <SignatureVerificationWorkspace />}
          {isPlatformAdmin && (activeView === "admin" || activeView in CUSTOMER_CONSOLE_VIEWS) && (
            <SimplifiedPlatformAdminScreen
              key={activeView}
              securityContext={securityContext}
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
        </SectionErrorBoundary>
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
