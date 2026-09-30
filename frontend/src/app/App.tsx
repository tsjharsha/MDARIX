import { useEffect, useMemo, useState } from "react";
import { PublicMegaSite } from "../PublicMegaSite";
import { AppView, navigateTo, viewFromPath } from "./router";
import { Stage3CommandCenter } from "../features/command-center/Stage3CommandCenter";
import { Stage2Experience } from "../features/stage2/Stage2Experience";
import { Stage2AdminControlPlane } from "../features/stage2/Stage2AdminControlPlane";
import { AskMdarixPage } from "../features/ask/AskMdarixPage";
import { MappingStudio } from "../features/stage2/MappingStudio";
import { SubscriptionAdministration } from "../features/stage2/SubscriptionAdministration";
import { allowedViewsForRole, isCustomerAdminRole, isPlatformAdminRole } from "./navigationPolicy";
import { requestJson } from "./apiClient";
import { PlatformProductConfiguration } from "../features/stage2/PlatformProductConfiguration";
import { ConsentBanner } from "../features/shared/ConsentBanner";
import { CustomerAdminControlPlane } from "../features/customer-admin/CustomerAdminControlPlane";
import { PlatformAdminScreen } from "../features/admin/PlatformAdminScreen";
import { RegulatoryCopilot } from "../features/regulatory/RegulatoryCopilot";
import { RiskTraceabilityWorkspace } from "../features/risk/RiskTraceabilityWorkspace";
import { SignatureVerificationWorkspace } from "../features/signature/SignatureVerificationWorkspace";
import { InvestigatorHome } from "../features/investigator/InvestigatorHome";
import { MyWork } from "../features/investigator/MyWork";
import { SimplifiedPlatformAdminScreen } from "../features/admin/SimplifiedPlatformAdminScreen";
import { Product, InvestigationSummary, TemporalMode, Product360 } from "./types";
import { api } from "./api";
import { PlatformCustomers } from "../features/admin/PlatformCustomers";
import { CreateCustomer } from "../features/admin/CreateCustomer";
import { Customer360 } from "../features/admin/Customer360";
import { CustomerAdminManagement } from "../features/admin/CustomerAdminManagement";
import { PlatformAdministrationAudit } from "../features/admin/PlatformAdministrationAudit";
import { AuthPage } from "../features/auth/AuthPage";
import { AssuranceView, AuditTrailView } from "../features/investigator/AssuranceAuditViews";
import { Product360View } from "../features/investigator/Product360View";
import { InvestigationAccessView } from "../features/investigator/InvestigationAccessView";
import { EvidenceAccessView } from "../features/investigator/EvidenceAccessView";
import { DecisionCenterView } from "../features/investigator/DecisionCenterView";

export function App() {
  const publicPath = window.location.pathname;
  if (
    publicPath === "/" ||
    [
      "/platform",
      "/product-lifecycle",
      "/why-mdarix",
      "/resources",
      "/plans",
      "/pricing",
      "/roadmap",
      "/capabilities",
      "/solutions",
      "/ai-trust",
      "/integrations",
      "/security",
      "/company",
      "/request-demo",
    ].some((route) => publicPath.startsWith(route))
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
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<string>("");
  const [version, setVersion] = useState<string>("D");
  const [asOf, setAsOf] = useState("2026-02-15");
  const [mode, setMode] = useState<TemporalMode>("event");
  const [view, setView] = useState<Product360 | null>(null);
  const [error, setError] = useState("");
  const [activeView, setActiveView] = useState<AppView>(() => viewFromPath(window.location.pathname));
  const [selectedInvestigationId, setSelectedInvestigationId] = useState("");
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [investigationsLoading, setInvestigationsLoading] = useState(false);

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

  useEffect(() => {
    api<Product[]>("/api/v1/products")
      .then((items) => {
        setProducts(items);
        setSelectedProduct(items[0]?.id ?? "");
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!selectedProduct) return;
    const params = new URLSearchParams({ version_id: version, as_of: `${asOf}T00:00:00Z`, mode });
    api<Product360>(`/api/v1/products/${selectedProduct}/product-360?${params}`)
      .then((item) => {
        setView(item);
        setError("");
      })
      .catch((err) => setError(err.message));
  }, [selectedProduct, version, asOf, mode]);

  useEffect(() => {
    if (!selectedProduct) return;
    let active = true;
    setInvestigationsLoading(true);
    api<InvestigationSummary[]>(`/api/v1/products/${selectedProduct}/investigations`)
      .then((items) => {
        if (active) {
          setInvestigations(items);
          setSelectedInvestigationId((current) =>
            items.some((item) => item.id === current) ? current : (items[0]?.id ?? ""),
          );
        }
      })
      .catch((err) => {
        if (active) setError(`Investigations could not be loaded: ${err.message}`);
      })
      .finally(() => {
        if (active) setInvestigationsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedProduct]);

  const selected = useMemo(() => products.find((p) => p.id === selectedProduct), [products, selectedProduct]);
  const activeRole = securityContext?.active_role?.trim().toUpperCase();
  const isPlatformAdmin = isPlatformAdminRole(activeRole);
  const isCustomerAdmin = isCustomerAdminRole(activeRole);
  const canSee = (item: string) =>
    !securityContext?.allowed_menu?.length || securityContext.allowed_menu.includes(item);

  useEffect(() => {
    if (isPlatformAdmin && !allowedViewsForRole(activeRole)?.includes(activeView)) changeView("admin");
    if (isCustomerAdmin && activeView !== "customer-admin") changeView("customer-admin");
  }, [isPlatformAdmin, isCustomerAdmin]);

  const switchTenant = async (tenantId: string) => {
    if (!tenantId || tenantId === securityContext?.tenant_id) return;
    try {
      await requestJson<{ status: string; tenant_id: string }>("/api/v1/me/tenant-context", {
        method: "POST",
        body: JSON.stringify({ tenant_id: tenantId }),
      });
      sessionStorage.clear();
      window.location.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Tenant switch failed");
    }
  };
  const contextToolbar = (
    <div className="toolbar">
      {securityContext && (
        <span className="context-summary" aria-label="Authenticated user and active role">
          {securityContext.display_name} | {securityContext.active_role ?? "No active role"}
        </span>
      )}
      {securityContext?.memberships && securityContext.memberships.length > 1 && (
        <select
          aria-label="Active tenant"
          value={securityContext.tenant_id ?? ""}
          onChange={(event) => void switchTenant(event.target.value)}
        >
          {securityContext.memberships.map((membership) => (
            <option key={membership.tenant_id} value={membership.tenant_id}>
              {membership.tenant_name} · {membership.tenant_key}
            </option>
          ))}
        </select>
      )}
      <button className="secondary-link" onClick={() => changeView("ask")}>
        Ask MDARIX
      </button>
      <select value={selectedProduct} onChange={(e) => setSelectedProduct(e.target.value)} aria-label="Product">
        {products.map((product) => (
          <option key={product.id} value={product.id}>
            {product.name}
          </option>
        ))}
      </select>
      <select value={version} onChange={(e) => setVersion(e.target.value)} aria-label="Version">
        {(selected?.available_versions ?? ["D"]).map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
      <select
        value={selectedInvestigationId}
        onChange={(e) => setSelectedInvestigationId(e.target.value)}
        aria-label="Investigation"
        disabled={investigationsLoading || !investigations.length}
      >
        {!investigations.length && (
          <option value="">{investigationsLoading ? "Loading investigations…" : "No investigations"}</option>
        )}
        {investigations.map((item) => (
          <option key={item.id} value={item.id ?? ""}>
            {item.investigation_identifier ?? "Investigation"} — {item.status ?? "unknown"}
          </option>
        ))}
      </select>
      <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} aria-label="As of date" />
      <div className="segmented">
        <button className={mode === "current" ? "selected" : ""} onClick={() => setMode("current")}>
          Current
        </button>
        <button className={mode === "event" ? "selected" : ""} onClick={() => setMode("event")}>
          Event
        </button>
        <button className={mode === "known" ? "selected" : ""} onClick={() => setMode("known")}>
          Known
        </button>
      </div>
    </div>
  );

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

  return (
    <div
      className={`app-shell ${isPlatformAdmin ? "platform-admin-shell" : ""} ${isCustomerAdmin ? "customer-admin-shell" : "quality-shell"}`}
    >
      {!isPlatformAdmin && !isCustomerAdmin && (
        <aside className="side-nav">
          <div className="brand-block">
            <div className="brand">{securityContext?.current_tenant?.tenant_name ?? "MDARIX"}</div>
            <span>Product Lifecycle Intelligence · {securityContext?.environment ?? "environment"}</span>
          </div>
          <nav>
            {isPlatformAdmin ? (
              <>
                <p className="nav-section-label">Administrator control plane</p>
                <button
                  className={`nav-link ${activeView === "admin" ? "active" : ""}`}
                  onClick={() => changeView("admin")}
                >
                  Platform administration <small>Customers, access, plans, integrations, security &amp; audit</small>
                </button>
              </>
            ) : isCustomerAdmin ? (
              <>
                <p className="nav-section-label">Customer administration</p>
                {[
                  ["Overview", "Overview"],
                  ["Organization", "Organization"],
                  ["Users", "Users"],
                  ["Roles & Access", "Roles & Access"],
                  ["Configuration", "Configuration"],
                  ["Integrations", "Integrations"],
                  ["Plans & Entitlements", "Plans & Entitlements"],
                  ["Security", "Security"],
                  ["Audit", "Audit"],
                ].map(([label, section]) => (
                  <button
                    key={label}
                    className={`nav-link ${activeView === "customer-admin" && section === "Overview" ? "active" : ""}`}
                    onClick={() => {
                      window.dispatchEvent(new CustomEvent("customer-admin-section", { detail: section }));
                      changeView("customer-admin");
                    }}
                  >
                    {label}
                  </button>
                ))}
              </>
            ) : (
              <>
                <p className="nav-section-label">Workspace</p>
                {canSee("home") && (
                  <button
                    className={`nav-link ${activeView === "home" ? "active" : ""}`}
                    onClick={() => changeView("home")}
                  >
                    Home
                  </button>
                )}
                {canSee("home") && (
                  <button
                    className={`nav-link ${activeView === "my-work" ? "active" : ""}`}
                    onClick={() => changeView("my-work")}
                  >
                    My Work <small>Assignments, gaps, and reviews</small>
                  </button>
                )}
                {canSee("products") && (
                  <button
                    className={`nav-link ${activeView === "products" ? "active" : ""}`}
                    onClick={() => changeView("products")}
                  >
                    Products
                  </button>
                )}
                {canSee("products") && (
                  <button
                    className={`nav-link ${activeView === "signals" ? "active" : ""}`}
                    onClick={() => changeView("signals")}
                  >
                    Signals &amp; Complaints
                  </button>
                )}
                {canSee("products") && (
                  <button
                    className={`nav-link ${activeView === "story" ? "active" : ""}`}
                    onClick={() => changeView("story")}
                  >
                    Story View
                  </button>
                )}
                {canSee("home") && (
                  <button
                    className={`nav-link ${activeView === "persona" ? "active" : ""}`}
                    onClick={() => changeView("persona")}
                  >
                    Persona Dashboard
                  </button>
                )}
                {canSee("home") && (
                  <button
                    className={`nav-link ${activeView === "ask" ? "active" : ""}`}
                    onClick={() => changeView("ask")}
                  >
                    Ask MDARIX
                  </button>
                )}
                <p className="nav-section-label">Investigation</p>
                {canSee("investigations") && (
                  <button
                    className={`nav-link ${activeView === "investigations" ? "active" : ""}`}
                    onClick={() => changeView("investigations")}
                  >
                    Investigations
                  </button>
                )}
                {canSee("evidence") && (
                  <button
                    className={`nav-link ${activeView === "evidence" ? "active" : ""}`}
                    onClick={() => changeView("evidence")}
                  >
                    Evidence
                  </button>
                )}
                <p className="nav-section-label">Decision & Trust</p>
                {canSee("decision-center") && (
                  <button
                    className={`nav-link ${activeView === "decision" ? "active" : ""}`}
                    onClick={() => changeView("decision")}
                  >
                    Decision Center
                  </button>
                )}
                {canSee("assurance") && (
                  <button
                    className={`nav-link ${activeView === "assurance" ? "active" : ""}`}
                    onClick={() => changeView("assurance")}
                  >
                    AI Assurance <small>Inspect AI trust controls</small>
                  </button>
                )}
                {canSee("audit") && (
                  <button
                    className={`nav-link ${activeView === "audit" ? "active" : ""}`}
                    onClick={() => changeView("audit")}
                  >
                    Audit Trail <small>Review recorded activity</small>
                  </button>
                )}
              </>
            )}
          </nav>
          <div className="side-nav-footer">
            <p>
              Evidence before inference.
              <br />
              Authorized humans decide.
            </p>
          </div>
        </aside>
      )}
      <main>
        {!isPlatformAdmin && !isCustomerAdmin && (
          <button
            className="logout-control"
            onClick={async () => {
              await requestJson("/api/v1/auth/signout", { method: "POST", retries: 0 }).catch(() => undefined);
              window.location.replace("/signin");
            }}
            aria-label="Sign out of MDARIX"
          >
            Logout
          </button>
        )}
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
        {![
          "customer-admin",
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
        ].includes(activeView) && (
          <header className={`topbar ${activeView === "home" ? "home-topbar" : ""}`}>
            {activeView === "home" && contextToolbar}
            <div>
              <p className="eyebrow">
                {activeView === "home" ? "Intelligence workspace" : "Persistent workflow context"}
              </p>
              <h1>
                {activeView === "home" ? "Good decisions start with product reality" : (view?.product.name ?? "MDARIX")}
              </h1>
              <div className="workflow-storyline" aria-label="End-to-end investigation workflow">
                <span className={activeView === "products" ? "active" : ""}>Product reality</span>
                <i>›</i>
                <span className={activeView === "investigations" ? "active" : ""}>Investigate</span>
                <i>›</i>
                <span className={activeView === "evidence" ? "active" : ""}>Evidence</span>
                <i>›</i>
                <span className={activeView === "decision" ? "active" : ""}>Decide</span>
                <i>›</i>
                <span className={activeView === "assurance" ? "active" : ""}>Assurance</span>
                <i>›</i>
                <span className={activeView === "audit" ? "active" : ""}>Audit</span>
              </div>
            </div>
            {activeView !== "home" && contextToolbar}
          </header>
        )}
        {error && <div className="error">{error}</div>}
        {view && activeView === "home" && (
          <>
            <InvestigatorHome
              tenantName={securityContext?.current_tenant?.tenant_name ?? "Authenticated tenant"}
              userName={securityContext?.display_name ?? "Investigator"}
              productName={view.product.name ?? "Product not selected"}
              version={view.selected_version?.version_identifier ?? version}
              investigationCount={investigations.length}
              evidenceCount={view.evidence.length}
              limitationsCount={view.limitations.length}
              onNavigate={changeView}
            />
            <Stage3CommandCenter />
          </>
        )}
        {view && activeView === "my-work" && <MyWork productId={selectedProduct} onOpen={changeView} />}
        {view && activeView === "products" && <Product360View view={view} />}
        {view && activeView === "signals" && <Stage2Experience mode="signals" />}
        {view && activeView === "persona" && <Stage2Experience mode="persona" />}
        {view && activeView === "story" && <Stage2Experience mode="story" investigationId={selectedInvestigationId} />}
        {view && activeView === "ask" && (
          <AskMdarixPage
            investigationId={selectedInvestigationId}
            productVersionId={view.selected_version?.id as string | undefined}
          />
        )}
        {view && activeView === "investigations" && (
          <InvestigationAccessView
            view={view}
            selectedInvestigationId={selectedInvestigationId}
            onSelect={setSelectedInvestigationId}
            temporalMode={mode}
            asOf={asOf}
            onOpenDecision={() => setActiveView("decision")}
          />
        )}
        {view && activeView === "evidence" && <EvidenceAccessView productEvidenceCount={view.evidence.length} />}
        {view && activeView === "decision" && selectedInvestigationId && (
          <DecisionCenterView investigationId={selectedInvestigationId} temporalMode={mode} asOf={asOf} />
        )}
        {view && activeView === "decision" && !selectedInvestigationId && (
          <div className="content">
            <section className="panel empty-state">
              <h2>Select an investigation first</h2>
              <p>Open Investigations and select a live investigation before entering Decision Center.</p>
            </section>
          </div>
        )}
        {view && activeView === "assurance" && <AssuranceView view={view} />}
        {view && activeView === "audit" && <AuditTrailView view={view} />}
        {activeView === "customer-admin" && (
          <CustomerAdminControlPlane
            securityContext={securityContext}
            products={products}
            investigations={investigations}
            onNavigate={changeView}
          />
        )}
        {activeView === "regulatory-copilot" && <RegulatoryCopilot />}
        {activeView === "risk-traceability" && <RiskTraceabilityWorkspace />}
        {activeView === "signature-verification" && <SignatureVerificationWorkspace />}
        {isPlatformAdmin && ["admin", "platform-tenants"].includes(activeView) && (
          <SimplifiedPlatformAdminScreen
            securityContext={securityContext}
            onNavigate={changeView}
            initialSection={activeView === "platform-tenants" ? "Customers" : "Overview"}
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
            "admin-integration-registry",
            "admin-api-registry",
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
                    "admin-integration-registry": "Integration registry",
                    "admin-api-registry": "API & contract registry",
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
        {activeView === "admin-customers" && <PlatformCustomers onNavigate={changeView} />}
        {activeView === "admin-create-customer" && <CreateCustomer onCreated={() => changeView("admin-customers")} />}
        {activeView === "admin-customer-360" && <Customer360 />}
        {activeView === "admin-manage" && <CustomerAdminManagement />}
        {activeView === "admin-audit" && <PlatformAdministrationAudit />}
        {isPlatformAdmin && activeView === "platform-customers" && <PlatformCustomers onNavigate={changeView} />}
        {isPlatformAdmin && activeView === "platform-onboarding" && (
          <CreateCustomer onCreated={() => changeView("platform-customers")} />
        )}
        {isPlatformAdmin && activeView === "platform-licenses" && <SubscriptionAdministration />}
        {isPlatformAdmin && activeView === "platform-tenant-audit" && <PlatformAdministrationAudit />}
      </main>
      <ConsentBanner />
    </div>
  );
}
