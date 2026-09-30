import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Boxes,
  CalendarClock,
  ChevronRight,
  CircleDot,
  ClipboardList,
  Factory,
  FileText,
  GitBranch,
  History,
  Layers,
  Network,
  ShieldCheck,
} from "lucide-react";
import "./styles.css";
import "./public-marketing-design.css";
import { PublicMegaSite } from "./PublicMegaSite";
import { AppView, navigateTo, viewFromPath } from "./app/router";
import { Stage3CommandCenter } from "./features/command-center/Stage3CommandCenter";
import { Stage2Experience } from "./features/stage2/Stage2Experience";
import { ProductVersionStory } from "./features/investigator/ProductVersionStory";
import { Stage2AdminControlPlane } from "./features/stage2/Stage2AdminControlPlane";
import { AskMdarixPage } from "./features/ask/AskMdarixPage";
import { MappingStudio } from "./features/stage2/MappingStudio";
import { SubscriptionAdministration } from "./features/stage2/SubscriptionAdministration";
import { allowedViewsForRole, isCustomerAdminRole, isPlatformAdminRole } from "./app/navigationPolicy";
import { requestJson } from "./app/apiClient";
import { AppErrorBoundary } from "./app/ErrorBoundary";
import { PlatformProductConfiguration } from "./features/stage2/PlatformProductConfiguration";
import { fmt, humanize } from "./app/format";
import { AnalysisPanel, DenseTable, Metric, Panel } from "./app/ui";
import { ConsentBanner } from "./features/shared/ConsentBanner";
import { CustomerAdminControlPlane } from "./features/customer-admin/CustomerAdminControlPlane";
import { PlatformAdminScreen } from "./features/admin/PlatformAdminScreen";
import { RegulatoryCopilot } from "./features/regulatory/RegulatoryCopilot";
import { RiskTraceabilityWorkspace } from "./features/risk/RiskTraceabilityWorkspace";
import { SignatureVerificationWorkspace } from "./features/signature/SignatureVerificationWorkspace";
import { InvestigatorHome } from "./features/investigator/InvestigatorHome";
import { MyWork } from "./features/investigator/MyWork";
import { SimplifiedPlatformAdminScreen } from "./features/admin/SimplifiedPlatformAdminScreen";

type Product = {
  id: string;
  product_identifier: string;
  name: string;
  product_family: string | null;
  lifecycle_status: string;
  available_versions: string[];
};
type InvestigationSummary = Record<string, string | null>;
type TemporalMode = "current" | "event" | "known";

type TimelineEvent = {
  event_id: string;
  event_type: string;
  category: string;
  title: string;
  event_time?: string;
  effective_time?: string;
  recorded_time?: string;
  knowledge_available_time?: string;
  description?: string;
  related_entity_type?: string;
  related_entity_id?: string;
  source?: string;
  metadata?: Record<string, unknown>;
  quality_status?: string;
  late_arriving: boolean;
};

type Product360 = {
  product: Record<string, string | null>;
  selected_version: Record<string, string | null> | null;
  versions: Array<Record<string, string | null>>;
  overview: Record<string, number | boolean>;
  configuration: { components: Array<Record<string, string | null>>; suppliers: Array<Record<string, string | null>> };
  changes: Array<Record<string, string | null>>;
  manufacturing: { lots: Array<Record<string, string | null>>; sites: Array<Record<string, string | null>> };
  complaints: Array<Record<string, string | null>>;
  investigations: Array<Record<string, string | null>>;
  risks: Array<Record<string, string | null>>;
  failure_modes: Array<Record<string, string | null>>;
  controls: Array<Record<string, string | null>>;
  evidence: Array<Record<string, string | null>>;
  limitations: Array<{ code: string; severity: string; description: string }>;
  provenance: Array<Record<string, string | null>>;
  timeline: TimelineEvent[];
  temporal_context: Record<string, string | boolean | null>;
};

type WorkspaceEvidence = {
  evidence_identifier: string;
  evidence_type: string;
  title: string;
  reliability_status: string;
  chunks: Array<{ source_anchor: Record<string, unknown>; excerpt: string; materialized: boolean }>;
  observations: Array<{ statement: string; quality_status: string; source_anchor: Record<string, unknown> }>;
  entity_links: Array<{ entity_type: string; resolution_status: string; source: string }>;
};

type InvestigationWorkspace = {
  investigation: Record<string, string | null>;
  product_context: Record<string, unknown>;
  temporal_context: Record<string, string | boolean | number | null>;
  relationship_context: { nodes: unknown[]; relationships: unknown[]; metadata: Record<string, unknown> };
  evidence_context: WorkspaceEvidence[];
  retrieval_context: { status: string; results_count: number; limitations: string[] } | null;
  limitations: Array<{ code: string; severity: string; description: string }>;
  guardrails: Record<string, string | boolean>;
  metadata: Record<string, string | boolean>;
};

type AnalysisItem = {
  item_id: string;
  semantic_type: string;
  statement: string;
  rationale?: string;
  grounding_status: string;
  source_references: unknown[];
};

type InvestigationAnalysis = {
  analysis_id: string;
  status: string;
  observations: AnalysisItem[];
  temporal_patterns: AnalysisItem[];
  evidence_relationships: AnalysisItem[];
  possible_explanations: AnalysisItem[];
  contradictions: AnalysisItem[];
  missing_information: AnalysisItem[];
  questions_to_investigate: AnalysisItem[];
  limitations: AnalysisItem[];
  validation_summary: Record<string, number | string>;
  model_provenance: Record<string, string | boolean>;
};
type InvestigationBrief = {
  id: string;
  investigation_id: string;
  brief_version: number;
  status: string;
  title: string;
  temporal_mode: string;
  temporal_cutoff?: string | null;
  human_review_state: string;
  content: Record<string, any>;
  provenance: Record<string, any>;
};

type Hypothesis = {
  hypothesis_id: string;
  statement: string;
  scope: string;
  status: string;
  supporting_evidence: Array<{ relationship_type: string; rationale: string; source_references: unknown[] }>;
  contradicting_evidence: Array<{ relationship_type: string; rationale: string; source_references: unknown[] }>;
  contextual_evidence: Array<{ relationship_type: string; rationale: string; source_references: unknown[] }>;
  assumptions: string[];
  evidence_gaps: string[];
  falsification_conditions: string[];
  temporal_consistency: Record<string, string>;
};

type HypothesisSet = {
  hypothesis_set_id: string;
  status: string;
  hypotheses: Hypothesis[];
  comparison: Array<Record<string, string | number | boolean>>;
  validation_summary: Record<string, number | string>;
  guardrails: Record<string, boolean>;
};
type UnknownSet = {
  unknowns: Array<{
    unknown_id: string;
    category: string;
    statement: string;
    why_it_matters: string;
    resolution_requirement: string;
    status: string;
    materiality: string;
    provenance: Record<string, unknown>;
  }>;
};
type FailureChainSet = {
  chains: Array<{
    chain_id: string;
    chain_statement: string;
    overall_status: string;
    links: Array<{
      link_id: string;
      from_entity_or_state: string;
      relationship: string;
      to_entity_or_state: string;
      epistemic_status: string;
      unknowns: string[];
    }>;
  }>;
};
type ChallengeSet = {
  challenges: Array<{
    challenge_id: string;
    challenge_type: string;
    statement: string;
    rationale: string;
    materiality: string;
    status: string;
  }>;
};
type EvidenceSummary = {
  id: string;
  evidence_identifier: string;
  evidence_type: string;
  title: string;
  source_system?: string | null;
  reliability_status?: string | null;
  fact_type?: string | null;
  document_ref?: string | null;
};
type DecisionContext = {
  investigation: Record<string, string | null>;
  product_context: Record<string, any>;
  temporal_context: Record<string, any>;
  evidence: Array<Record<string, any>>;
  observations: Array<Record<string, any>>;
  contradictions: Array<Record<string, any>>;
  hypotheses: Array<Record<string, any>>;
  challenges: Array<Record<string, any>>;
  unknowns: Array<Record<string, any>>;
  failure_chains: Array<Record<string, any>>;
  limitations: Array<Record<string, any>>;
  readiness: { state: string; reasons: string[] };
  decision_options: string[];
};

const api = <T,>(path: string) => requestJson<T>(path);

function App() {
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

function PrivateApplicationGate() {
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

function PrivateApplication() {
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

type AdminTenant = { id: string; tenant_key: string; name: string; status: string; created_at?: string | null };
function PlatformCustomers({ onNavigate }: { onNavigate: (view: AppView) => void }) {
  const [rows, setRows] = useState<AdminTenant[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  useEffect(() => {
    api<AdminTenant[]>("/api/v1/platform-admin/customers")
      .then(setRows)
      .catch((e) => setError(e.message));
  }, []);
  const filtered = rows.filter(
    (row) =>
      `${row.name} ${row.tenant_key} ${row.status}`.toLowerCase().includes(query.toLowerCase()) &&
      (status === "ALL" || row.status.toUpperCase() === status),
  );
  const pageSize = 10;
  const visible = filtered.slice((page - 1) * pageSize, page * pageSize);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const open360 = (id: string) => {
    window.history.pushState({}, "", `/app/admin/customers/detail?tenant_id=${encodeURIComponent(id)}`);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };
  return (
    <div className="content governance-view">
      <section className="governance-hero">
        <div>
          <span className="eyebrow">Customers</span>
          <h2>Customers / Tenants</h2>
          <p>Search, filter, paginate, and review tenant metadata without exposing regulated business records.</p>
        </div>
        <button className="primary-action" onClick={() => onNavigate("admin-create-customer")}>
          Create customer
        </button>
      </section>
      <section className="panel">
        <div className="toolbar">
          <input
            aria-label="Search customers"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Search company, tenant code, or status"
          />
          <select
            aria-label="Filter customer status"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="ALL">All statuses</option>
            <option value="ACTIVE">Active</option>
            <option value="SUSPENDED">Suspended</option>
            <option value="PENDING">Pending</option>
          </select>
        </div>
        {error && <p className="field-error">{error}</p>}
        <div className="audit-row">
          <strong>Company</strong>
          <span>Tenant code</span>
          <small>Status</small>
        </div>
        {visible.map((row) => (
          <div className="audit-row" key={row.id}>
            <strong>{row.name}</strong>
            <span>{row.tenant_key}</span>
            <small>
              {row.status}{" "}
              <button className="secondary-link" onClick={() => open360(row.id)}>
                Customer 360
              </button>
            </small>
          </div>
        ))}
        {!visible.length && !error && <p>No customers match the selected filters.</p>}
        <div className="toolbar">
          <small>{filtered.length} customer(s)</small>
          <span>
            <button className="secondary-link" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>{" "}
            <span>
              Page {page} of {pageCount}
            </span>{" "}
            <button className="secondary-link" disabled={page >= pageCount} onClick={() => setPage(page + 1)}>
              Next
            </button>
          </span>
        </div>
      </section>
    </div>
  );
}

function CreateCustomer({ onCreated }: { onCreated: () => void }) {
  const [form, setForm] = useState({
    company_name: "",
    tenant_code: "",
    region: "US",
    residency: "US",
    plan_code: "ENTERPRISE_TEST",
    licensed_users_limit: 25,
    customer_admin_email: "",
    customer_admin_display_name: "",
    customer_admin_company: "",
    domain: "",
    identity_provider: "MDARIX Identity",
    baseline: "MDARIX Standard MedTech 1.0",
    reason: "",
  });
  const [message, setMessage] = useState("");
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<any>(null);
  const [draftKey] = useState(() => {
    const key = window.localStorage.getItem("mdarix.platform.onboarding.draft") ?? `onboarding-${crypto.randomUUID()}`;
    window.localStorage.setItem("mdarix.platform.onboarding.draft", key);
    return key;
  });
  const stepLabels = [
    "Customer",
    "Tenant",
    "Region",
    "Plan",
    "Entitlements",
    "Admin",
    "Identity",
    "Baseline",
    "Review & Provision",
  ];
  const update = (key: string, value: string | number) => setForm((current) => ({ ...current, [key]: value }));
  const saveDraft = async (nextStep = step) => {
    try {
      await fetch(`/api/v1/platform-admin/onboarding/drafts/${encodeURIComponent(draftKey)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idempotency_key: draftKey, current_step: nextStep, draft_data: form }),
      });
    } catch {
      /* draft persistence must not block the governed flow */
    }
  };
  useEffect(() => {
    fetch(`/api/v1/platform-admin/onboarding/drafts/${encodeURIComponent(draftKey)}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((draft) => {
        if (draft?.draft_data) setForm((current) => ({ ...current, ...draft.draft_data }));
        if (draft?.current_step) setStep(draft.current_step);
      })
      .catch(() => undefined);
  }, [draftKey]);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const payload = {
      company_name: form.company_name,
      tenant_code: form.tenant_code,
      region: form.region,
      residency: form.residency,
      plan_code: form.plan_code,
      licensed_users_limit: form.licensed_users_limit,
      customer_admin_email: form.customer_admin_email,
      customer_admin_display_name: form.customer_admin_display_name,
      customer_admin_company: form.customer_admin_company || form.company_name,
      invitation_required: true,
    };
    try {
      const validationResponse = await fetch("/api/v1/platform-admin/onboarding/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const validation = await validationResponse.json();
      if (!validationResponse.ok) throw new Error(validation.detail?.message ?? "Onboarding validation failed");
      const response = await fetch("/api/v1/platform/tenants/provision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail?.message ?? "Provisioning failed");
      setJob({ ...result, steps: [] });
      setMessage(`Provisioning ${result.status}.`);
      if (result.job_id) {
        const poll = async () => {
          try {
            const statusResponse = await fetch(`/api/v1/platform-admin/provisioning-jobs/${result.job_id}`);
            const status = await statusResponse.json();
            if (!statusResponse.ok) throw new Error(status.detail?.message ?? "Provisioning status unavailable");
            setJob((current: any) => ({ ...current, ...status }));
          } catch {
            /* keep the last server state */
          }
        };
        await poll();
        const timer = window.setInterval(poll, 3000);
        window.setTimeout(() => window.clearInterval(timer), 18000);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Provisioning failed");
    } finally {
      setBusy(false);
    }
  };
  const fields =
    step === 1 ? (
      <>
        <label>
          Legal / company name
          <input required value={form.company_name} onChange={(e) => update("company_name", e.target.value)} />
        </label>
        <label>
          Customer reference
          <input
            value={form.domain}
            onChange={(e) => update("domain", e.target.value)}
            placeholder="CRM or approved domain"
          />
        </label>
      </>
    ) : step === 2 ? (
      <>
        <label>
          Tenant display name
          <input required value={form.company_name} readOnly />
        </label>
        <label>
          Tenant code
          <input
            required
            value={form.tenant_code}
            onChange={(e) => update("tenant_code", e.target.value)}
            placeholder="Generated tenant key"
          />
        </label>
      </>
    ) : step === 3 ? (
      <>
        <label>
          Primary region
          <select value={form.region} onChange={(e) => update("region", e.target.value)}>
            <option>US</option>
            <option>EU</option>
            <option>UK</option>
            <option>Canada</option>
            <option>India</option>
          </select>
        </label>
        <label>
          Data residency
          <select value={form.residency} onChange={(e) => update("residency", e.target.value)}>
            <option>US</option>
            <option>EU</option>
            <option>UK</option>
            <option>Canada</option>
            <option>India</option>
          </select>
        </label>
      </>
    ) : step === 4 ? (
      <>
        <label>
          Plan
          <select value={form.plan_code} onChange={(e) => update("plan_code", e.target.value)}>
            <option>ENTERPRISE_TEST</option>
            <option>STARTER</option>
            <option>PROFESSIONAL</option>
            <option>ENTERPRISE</option>
          </select>
        </label>
        <label>
          Licensed users
          <input
            type="number"
            min="1"
            value={form.licensed_users_limit}
            onChange={(e) => update("licensed_users_limit", Number(e.target.value))}
          />
        </label>
      </>
    ) : step === 5 ? (
      <div className="onboarding-summary">
        <strong>Entitlements inherit from the selected published plan.</strong>
        <span>
          Product 360, Investigations, Evidence, Audit and governed AI remain subject to plan and release gates.
        </span>
      </div>
    ) : step === 6 ? (
      <>
        <label>
          Initial Customer Administrator
          <input
            required
            type="email"
            value={form.customer_admin_email}
            onChange={(e) => update("customer_admin_email", e.target.value)}
            placeholder="admin@customer.com"
          />
        </label>
        <label>
          Administrator name
          <input
            required
            value={form.customer_admin_display_name}
            onChange={(e) => update("customer_admin_display_name", e.target.value)}
          />
        </label>
      </>
    ) : step === 7 ? (
      <>
        <label>
          Identity provider
          <select value={form.identity_provider} onChange={(e) => update("identity_provider", e.target.value)}>
            <option>MDARIX Identity</option>
            <option>Microsoft Entra ID</option>
            <option>Okta</option>
            <option>SAML / OIDC pending</option>
          </select>
        </label>
        <div className="onboarding-summary">
          <strong>MFA is required for critical operations.</strong>
          <span>SSO configuration is completed after the tenant is provisioned.</span>
        </div>
      </>
    ) : step === 8 ? (
      <label>
        Configuration baseline
        <input value={form.baseline} onChange={(e) => update("baseline", e.target.value)} />
      </label>
    ) : (
      <div className="onboarding-summary">
        <strong>Review before provisioning</strong>
        <span>
          {form.company_name} · {form.tenant_code} · {form.region} · {form.plan_code}
        </span>
        <span>Initial admin: {form.customer_admin_email || "Not entered"}</span>
        <label>
          Provisioning reason
          <input required value={form.reason} onChange={(e) => update("reason", e.target.value)} />
        </label>
      </div>
    );
  return (
    <div className="content governance-view">
      <section className="panel onboarding-wizard">
        <div className="section-title">Create Customer &amp; Tenant</div>
        <p>
          Platform-controlled onboarding. The server generates immutable tenant identity and remains authoritative for
          provisioning, entitlements and invitations.
        </p>
        <div className="admin-stepper">
          {stepLabels.map((label, index) => (
            <button
              type="button"
              key={label}
              className={step === index + 1 ? "selected" : ""}
              onClick={() => index + 1 <= step && (saveDraft(index + 1), setStep(index + 1))}
            >
              {index + 1}. {label}
            </button>
          ))}
        </div>
        <form className="admin-form-grid" onSubmit={submit}>
          <h3>{stepLabels[step - 1]}</h3>
          {fields}
          {step === 9 && (
            <label className="onboarding-confirm">
              <input type="checkbox" required /> I confirm the customer, tenant, subscription and identity information
              has been reviewed.
            </label>
          )}
          <div className="toolbar">
            <button
              type="button"
              className="secondary-link"
              disabled={step === 1 || busy}
              onClick={() => {
                saveDraft(step - 1);
                setStep(step - 1);
              }}
            >
              Back
            </button>
            {step < 9 ? (
              <button
                type="button"
                className="primary-action"
                onClick={() => {
                  saveDraft(step + 1);
                  setStep(step + 1);
                }}
              >
                Continue
              </button>
            ) : (
              <button className="primary-action" type="submit" disabled={busy}>
                {busy ? "Provisioning…" : "Provision Customer"}
              </button>
            )}
          </div>
        </form>
        {message && (
          <p className="review-success" role="status">
            {message}
          </p>
        )}
      </section>
      {job && (
        <section className="panel provisioning-job">
          <div className="section-title">Provisioning job progress</div>
          <p>
            Tenant: {job.tenant_key} · Status: {job.status}
          </p>
          <ol>
            {job.steps.map((item: string, index: number) => (
              <li className={job.status === "ACTIVE" || index < 2 ? "complete" : "pending"} key={item}>
                <span>{job.status === "ACTIVE" || index < 2 ? "✓" : "○"}</span>
                {item}
              </li>
            ))}
          </ol>
          {job.status === "ACTIVE" && (
            <button className="secondary-link" onClick={onCreated}>
              Open customers
            </button>
          )}
        </section>
      )}
    </div>
  );
}

function Customer360() {
  const [record, setRecord] = useState<any>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("Overview");
  const [detail, setDetail] = useState<any>(null);
  const tabs = [
    "Overview",
    "Administrators",
    "Users",
    "Plan",
    "Entitlements",
    "Integrations",
    "Security",
    "Usage",
    "Audit",
  ];
  useEffect(() => {
    const tenantId = new URLSearchParams(window.location.search).get("tenant_id");
    if (!tenantId) {
      setError("Select a customer from Customers / Tenants first.");
      return;
    }
    api<any>(`/api/v1/platform-admin/customers/${tenantId}`)
      .then(setRecord)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!record) return;
    const tenantId = record.id;
    const endpoint =
      tab === "Plan" || tab === "Entitlements"
        ? `/api/v1/platform-admin/customers/${tenantId}/subscription`
        : tab === "Usage"
          ? `/api/v1/platform-admin/customers/${tenantId}/usage`
          : tab === "Integrations"
            ? "/api/v1/admin/configuration/connectors"
            : tab === "Audit"
              ? "/api/v1/admin/audit-history"
              : tab === "Administrators" || tab === "Users"
                ? "/api/v1/admin/identity/users"
                : null;
    if (!endpoint) {
      setDetail(null);
      return;
    }
    api<any>(endpoint)
      .then(setDetail)
      .catch((e) => setDetail({ error: e.message }));
  }, [record, tab]);
  const values: Record<string, any> = {
    Overview: record
      ? [
          ["Status", record.status],
          ["Tenant ID", record.tenant_key],
          ["Plan", record.plan_id ?? "Not assigned"],
          ["Audit events", record.counts.audit_events],
        ]
      : [],
    Administrators: [["Customer administrators", record?.counts?.administrators ?? 0]],
    Users: [["Users", record?.counts?.users ?? 0]],
    Plan: [
      ["Subscription", detail?.status ?? record?.plan_id ?? "Not assigned"],
      ["Plan version", detail?.plan_version ?? "Not available"],
    ],
    Entitlements: [
      ["Licensed users", detail?.usage?.licensed_users ?? detail?.licensed_users ?? "Not available"],
      ["Seat cap", detail?.limits?.licensed_users_limit ?? "Not available"],
    ],
    Integrations: [["Configured connectors", record?.counts?.connectors ?? 0]],
    Security: [
      ["Boundary", "Tenant-scoped"],
      ["Access", "Server-authorized"],
    ],
    Usage: [
      ["Licensed users", detail?.licensed_users ?? record?.counts?.users ?? 0],
      ["Connectors", detail?.connectors ?? record?.counts?.connectors ?? 0],
    ],
    Audit: [["Audit events", record?.counts?.audit_events ?? 0]],
  };
  return (
    <div className="content governance-view customer-record-page">
      <section className="governance-hero">
        <div>
          <span className="eyebrow">Customer record</span>
          <h2>{record?.name ?? "Customer 360"}</h2>
          <p>
            Tenant {record?.tenant_key ?? "metadata"}. Platform administration is server-authorized and business content
            remains tenant-scoped.
          </p>
        </div>
        <span className="version-pill">{record?.status ?? "Loading"}</span>
      </section>
      {error && <section className="panel field-error">{error}</section>}
      {record && (
        <>
          <nav className="record-tabs" aria-label="Customer record tabs">
            {tabs.map((item) => (
              <button className={tab === item ? "selected" : ""} key={item} onClick={() => setTab(item)}>
                {item}
              </button>
            ))}
          </nav>
          <section className="record-detail-layout">
            <article className="panel">
              <span className="eyebrow">{tab}</span>
              <h3>{tab === "Overview" ? "Customer overview" : `${tab} detail`}</h3>
              <div className="record-field-grid">
                {(values[tab] ?? []).map(([label, value]: [string, any]) => (
                  <div key={label}>
                    <small>{label}</small>
                    <strong>{String(value)}</strong>
                  </div>
                ))}
              </div>
              {detail?.error && (
                <p className="field-error" role="alert">
                  {detail.error}
                </p>
              )}
              <p className="record-scope-note">
                Server-derived detail. No tenant identifier supplied by the browser is used as authorization.
              </p>
            </article>
            <aside className="panel">
              <div className="section-title">Related records</div>
              <p>
                Use the tabs to inspect administrators, users, plan, entitlements, integrations, security, usage, and
                audit evidence.
              </p>
              <button className="secondary-link" onClick={() => setTab("Audit")}>
                Open audit history
              </button>
            </aside>
          </section>
        </>
      )}
    </div>
  );
}

function CustomerAdminManagement() {
  // The change was recorded in audit history.
  const [users, setUsers] = useState<any[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<any | null>(null);
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const load = () =>
    api<any[]>("/api/v1/admin/identity/users")
      .then(setUsers)
      .catch((error) => setMessage(error.message));
  useEffect(() => {
    load();
  }, []);
  const visible = users.filter(
    (user) =>
      String(user.role).toUpperCase() === "CUSTOMER_ADMIN" &&
      [user.email, user.display_name, user.company].some((value) =>
        String(value ?? "")
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
  );
  const updateEmail = async () => {
    if (!selected) return;
    const response = await fetch(`/api/v1/admin/control-plane/users/${selected.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values: { email } }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail?.message ?? "Email update failed");
    setMessage("Customer administrator email updated.");
    setSelected(null);
    load();
  };
  const retire = async () => {
    if (!selected || !confirm("Retire this customer administrator account?")) return;
    const response = await fetch(`/api/v1/admin/identity/users/${selected.id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "OFFBOARDED" }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail?.message ?? "Account retirement failed");
    setMessage("Customer administrator account retired; audit history was preserved.");
    setSelected(null);
    load();
  };
  const reactivate = async () => {
    if (!selected || !confirm("Reactivate this account and send a new activation email?")) return;
    const response = await fetch(`/api/v1/admin/identity/users/${selected.id}/reactivate`, { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail?.message ?? "Account reactivation failed");
    setMessage(
      result.email_delivery === "SENT"
        ? "Account reactivated and a new activation email was sent."
        : `Account reactivated. SMTP is not configured; development token: ${result.development_token ?? "not returned"}`,
    );
    setSelected(null);
    load();
  };
  return (
    <div className="content governance-view">
      <section className="panel">
        <div className="section-title">
          <ShieldCheck size={18} /> Manage Customer Administrators
        </div>
        <p>
          Search by customer name, administrator name, or email address. Email changes and account retirement are
          tenant-scoped and audited.
        </p>
        <input
          aria-label="Search customer administrators"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by customer name or email"
        />
        {message && (
          <p className="review-success" role="status">
            {message}
          </p>
        )}
        <div className="audit-row">
          <strong>Customer / Administrator</strong>
          <span>Email</span>
          <small>Status</small>
        </div>
        {visible.map((user) => (
          <div className="audit-row" key={user.id}>
            <strong>
              {user.company ?? "Customer"} — {user.display_name}
            </strong>
            <span>{user.email}</span>
            <small>
              {user.status}{" "}
              <button
                className="secondary-link"
                onClick={() => {
                  setSelected(user);
                  setEmail(user.email);
                }}
              >
                Manage
              </button>
            </small>
          </div>
        ))}
        {!visible.length && <p>No customer administrators match the search.</p>}
      </section>
      {selected && (
        <section className="panel admin-forms">
          <div className="section-title">Manage {selected.display_name}</div>
          <label>
            Account email
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <button className="primary-action" onClick={() => updateEmail().catch((error) => setMessage(error.message))}>
            Update email
          </button>
          {String(selected.status).toUpperCase() === "OFFBOARDED" ? (
            <button className="primary-action" onClick={() => reactivate().catch((error) => setMessage(error.message))}>
              Activate account and send email
            </button>
          ) : (
            <button className="secondary-link" onClick={() => retire().catch((error) => setMessage(error.message))}>
              Retire account
            </button>
          )}
        </section>
      )}
    </div>
  );
}

function PlatformAdministrationAudit() {
  const [rows, setRows] = useState<any[]>([]);
  const [retention, setRetention] = useState<any>(null);
  const [message, setMessage] = useState("");
  useEffect(() => {
    Promise.all([api<any[]>("/api/v1/admin/audit-history"), api<any>("/api/v1/admin/retention-status")])
      .then(([events, status]) => {
        setRows(events);
        setRetention(status);
      })
      .catch((error) => setMessage(error.message));
  }, []);
  return (
    <div className="content governance-view">
      <section className="panel">
        <div className="section-title">
          <ShieldCheck size={18} /> Recent platform administration activity
        </div>
        <p>Server-recorded changes with actor, request metadata, reason, and before/after values.</p>
        <div className="audit-actions">
          <a className="secondary-link" href="/api/v1/admin/audit-history/export?output_format=CSV">
            Export CSV
          </a>
          <a className="secondary-link" href="/api/v1/admin/audit-history/export?output_format=JSON">
            Export JSON
          </a>
          <a className="primary-action" href="/api/v1/stage3/compliance-report?output_format=PDF">
            Download evidence package
          </a>
        </div>
        {retention && (
          <div className={`retention-banner ${retention.status === "HEALTHY" ? "healthy" : "attention"}`}>
            <strong>{retention.policy}</strong>
            <span>
              {retention.total_events} events · {retention.expired} expired · {retention.expiring_within_30_days}{" "}
              expiring within 30 days
            </span>
          </div>
        )}
        {message && <p className="field-error">{message}</p>}
        {rows.map((row) => (
          <div className="audit-row" key={String(row.id)}>
            <strong>{row.action}</strong>
            <span>
              {row.entity_type ?? "Configuration"} · {row.actor_ref ?? "System"}
            </span>
            <small>
              {row.created_at ? String(row.created_at).slice(0, 19).replace("T", " ") : "Server recorded"}
              {row.source_ip ? ` · ${row.source_ip}` : ""}
            </small>
          </div>
        ))}
        {!rows.length && !message && <p>No platform administration activity recorded.</p>}
      </section>
    </div>
  );
}

function AuthPage({ mode }: { mode: string }) {
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [token, setToken] = useState(new URLSearchParams(window.location.search).get("token") ?? "");
  const [userId, setUserId] = useState("");
  const isTokenPassword = mode === "activate-account" || mode === "reset-password";
  const isMfa = mode === "mfa";
  const [mfaCode, setMfaCode] = useState("");
  const [mfaSecret, setMfaSecret] = useState("");
  const [mfaEnrollment] = useState(new URLSearchParams(window.location.search).get("setup") === "1");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isMfa) {
      const response = await fetch("/api/v1/auth/mfa/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: mfaCode }),
      });
      const data = await response.json();
      if (response.ok) {
        setMessage("MFA verified. Loading MDARIX...");
        window.location.href = "/app";
      } else setMessage(data.detail?.message ?? "MFA verification could not be completed.");
      return;
    }
    const endpoint =
      mode === "signin"
        ? "signin"
        : mode === "signup"
          ? "signup"
          : mode === "verify-email"
            ? "verify-email"
            : mode === "activate-account"
              ? "activate-account"
              : mode === "reset-password"
                ? "reset-password"
                : "forgot-password";
    const body =
      mode === "signup"
        ? { email, password, display_name: name, organization: company }
        : mode === "signin"
          ? { email, password }
          : mode === "verify-email"
            ? { token }
            : isTokenPassword
              ? { token, password }
              : { email };
    const response = await fetch(`/api/v1/auth/${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (response.ok) {
      if (mode === "signup") {
        setUserId(data.user_id);
        setToken(data.development_token ?? "");
        setMessage(
          data.email_delivery === "SENT"
            ? `Account created. Your User ID is ${data.user_id}. A verification email was sent.`
            : `Account created. Your User ID is ${data.user_id}. Email delivery is not configured on this host; use the controlled verification link below.`,
        );
      } else if (mode === "verify-email") {
        setMessage("Email verified. You can now sign in with your User ID and password.");
      } else if (mode === "activate-account") {
        setMessage("Account activated. You can now sign in with your email and new password.");
      } else if (mode === "reset-password") {
        setMessage("Password reset complete. You can now sign in with your new password.");
      } else if (mode === "signin") {
        if (data.mfa_required) {
          window.location.href = "/mfa";
        } else {
          setMessage("Signed in. Loading MDARIX...");
          window.location.href = "/app";
        }
      } else
        setMessage(
          data.email_delivery === "SENT"
            ? "If the account exists, reset instructions were emailed."
            : `If the account exists, reset instructions are available.${data.development_token ? ` Development token: ${data.development_token}` : ""}`,
        );
    } else {
      setMessage(
        data.detail?.code === "PASSWORD_POLICY"
          ? "Password must be at least 12 characters."
          : data.detail?.code === "ACCOUNT_EXISTS"
            ? "An account with this email already exists. Use Sign in or verify the existing account."
            : (data.detail?.message ?? "Request could not be completed."),
      );
    }
  };
  if (isMfa)
    return (
      <div className="auth-shell">
        <a className="brand" href="/">
          MDARIX
        </a>
        <form className="auth-card" onSubmit={submit}>
          <span className="eyebrow">Account security</span>
          <h1>{mfaEnrollment ? "Enroll an authenticator" : "Verify your identity"}</h1>
          <p>
            {mfaEnrollment
              ? "Generate an enrollment secret, add it to your authenticator app, then verify the first code."
              : "Enter the six-digit code from your authenticator app to continue."}
          </p>
          {mfaEnrollment && (
            <>
              <button
                className="secondary-link"
                type="button"
                onClick={async () => {
                  const response = await fetch("/api/v1/auth/mfa/enroll", { method: "POST" });
                  const data = await response.json();
                  setMfaSecret(data.secret ?? "");
                  setMessage(
                    response.ok
                      ? "Secret generated. Add it to your authenticator app."
                      : (data.detail?.message ?? "MFA enrollment is unavailable."),
                  );
                }}
              >
                Generate enrollment secret
              </button>
              {mfaSecret && (
                <p className="mfa-secret" aria-label="MFA enrollment secret">
                  {mfaSecret}
                </p>
              )}
            </>
          )}
          <input
            aria-label="Six digit authentication code"
            inputMode="numeric"
            pattern="[0-9]{6}"
            minLength={6}
            maxLength={6}
            required
            value={mfaCode}
            onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ""))}
            placeholder="000000"
          />
          <button className="primary-action" type="submit">
            {mfaEnrollment ? "Verify and enable MFA" : "Verify MFA code"}
          </button>
          {message && <p role="status">{message}</p>}
          <p className="auth-links">
            <a href="/mfa?setup=1">Set up MFA</a> · <a href="/signin">Return to sign in</a>
          </p>
        </form>
      </div>
    );
  return (
    <div className="auth-shell">
      <a className="brand" href="/">
        MDARIX
      </a>
      <form className="auth-card" onSubmit={submit}>
        <span className="eyebrow">{mode === "signin" ? "Welcome back" : "MDARIX access"}</span>
        <h1>
          {mode === "signin"
            ? "Sign in to MDARIX"
            : mode === "signup"
              ? "Create your MDARIX account"
              : mode === "verify-email"
                ? "Verify your email"
                : mode === "activate-account"
                  ? "Activate your MDARIX account"
                  : mode === "reset-password"
                    ? "Create a new password"
                    : "Reset your password"}
        </h1>
        {mode === "signup" && (
          <>
            <input
              aria-label="Display name"
              required
              placeholder="Full name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <input
              aria-label="Company"
              required
              placeholder="Company / organization"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
            />
          </>
        )}
        {mode === "verify-email" || isTokenPassword ? (
          <input
            aria-label="Token"
            required
            placeholder="Secure token"
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
        ) : (
          <input
            aria-label="User ID or work email"
            required
            type={mode === "forgot-password" ? "email" : "text"}
            placeholder={mode === "signin" ? "User ID or work email" : "Work email"}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        )}{" "}
        {mode !== "forgot-password" && mode !== "verify-email" && (
          <>
            <input
              aria-label="Password"
              required
              minLength={12}
              type="password"
              placeholder={
                isTokenPassword ? "Create password (minimum 12 characters)" : "Password (minimum 12 characters)"
              }
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {(mode === "signup" || isTokenPassword) && (
              <small>Password is created by the user and never shown to administrators.</small>
            )}
          </>
        )}
        <button className="primary-action" type="submit">
          {mode === "signin"
            ? "Sign in"
            : mode === "signup"
              ? "Create account"
              : mode === "verify-email"
                ? "Verify email"
                : mode === "activate-account"
                  ? "Activate account"
                  : mode === "reset-password"
                    ? "Reset password"
                    : "Send reset instructions"}
        </button>
        {message && (
          <p role="status">
            {message}
            {userId && token && (
              <>
                {" "}
                <br />
                <a href={`/verify-email?token=${encodeURIComponent(token)}`}>Continue to email verification</a>
              </>
            )}
          </p>
        )}
        <p className="auth-links">
          <a href="/signup">Create account</a> · <a href="/signin">Sign in</a> ·{" "}
          <a href="/verify-email">Verify email</a> · <a href="/forgot-password">Forgot password?</a>
        </p>
      </form>
    </div>
  );
}

function AssuranceView({ view }: { view: Product360 }) {
  return (
    <div className="content governance-view">
      <section className="governance-hero">
        <div>
          <span className="eyebrow">Trust &amp; governance</span>
          <h2>AI Assurance</h2>
          <p>
            Inspect how MDARIX keeps AI outputs grounded, bounded, tenant-scoped, and distinct from authorized human
            decisions.
          </p>
        </div>
        <div className="governance-status">
          <ShieldCheck size={22} />
          <strong>Human authority preserved</strong>
          <span>Assurance informs review; it does not approve a decision.</span>
        </div>
      </section>
      <div className="governance-grid">
        <section className="panel">
          <h3>Assurance checks</h3>
          <ul className="governance-list">
            <li>
              <strong>Evidence grounding</strong>
              <span>Source references and provenance remain visible.</span>
            </li>
            <li>
              <strong>Temporal context</strong>
              <span>Results are evaluated against the selected date and event mode.</span>
            </li>
            <li>
              <strong>ProductVersion context</strong>
              <span>Product and version scope are carried into the workflow.</span>
            </li>
            <li>
              <strong>Causality restraint</strong>
              <span>Unsupported root-cause conclusions are not generated.</span>
            </li>
          </ul>
        </section>
        <section className="panel">
          <h3>Current scope</h3>
          <p>
            <strong>{view.product.name}</strong>
          </p>
          <p>Version {view.selected_version?.version_identifier ?? "not selected"}</p>
          <p>{view.limitations.length} visible limitations require attention.</p>
          <div className="advisory-box">
            <strong>Review required</strong>
            <p>Authorized humans remain responsible for regulated conclusions and final decisions.</p>
          </div>
        </section>
      </div>
    </div>
  );
}

function AuditTrailView({ view }: { view: Product360 }) {
  return (
    <div className="content governance-view">
      <section className="governance-hero audit-hero">
        <div>
          <span className="eyebrow">Traceability</span>
          <h2>Audit Trail</h2>
          <p>Review the recorded context behind product, investigation, evidence, and decision activity.</p>
        </div>
        <div className="governance-status">
          <FileText size={22} />
          <strong>Controlled foundation</strong>
          <span>Tenant-scoped activity remains attributable and reviewable.</span>
        </div>
      </section>
      <section className="panel audit-table">
        <h3>Recent recorded context</h3>
        <div className="audit-row">
          <strong>Product scope</strong>
          <span>
            {view.product.product_identifier} · {view.product.name}
          </span>
          <small>Current workspace</small>
        </div>
        <div className="audit-row">
          <strong>Version context</strong>
          <span>{view.selected_version?.version_identifier ?? "Not selected"}</span>
          <small>Temporal context preserved</small>
        </div>
        <div className="audit-row">
          <strong>Evidence access</strong>
          <span>{view.evidence.length} product-linked records</span>
          <small>Tenant-scoped access</small>
        </div>
        <div className="audit-row">
          <strong>Limitations</strong>
          <span>{view.limitations.length} visible limitations</span>
          <small>Requires review before conclusion</small>
        </div>
      </section>
    </div>
  );
}

function Product360View({ view }: { view: Product360 }) {
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);
  return (
    <div className="content">
      <section className="product-header">
        <div>
          <p className="eyebrow">{view.product.product_identifier}</p>
          <h2>{view.product.name}</h2>
          <p>
            {view.product.product_family} · {view.product.lifecycle_status}
          </p>
        </div>
        <div className="version-pill">
          <Layers size={16} /> {view.selected_version?.version_identifier ?? "No version selected"}
        </div>
      </section>

      <section className="metric-strip">
        <Metric icon={<Boxes />} label="Components" value={view.overview.component_count} />
        <Metric icon={<Factory />} label="Lots" value={view.overview.lot_count} />
        <Metric icon={<AlertTriangle />} label="Complaints" value={view.overview.complaint_count} />
        <Metric icon={<FileText />} label="Evidence" value={view.overview.evidence_count} />
      </section>

      <ProductVersionStory
        productId={view.product.id ?? undefined}
        versionId={view.selected_version?.id ?? undefined}
      />

      <section className="two-col">
        <Panel title="Configuration" icon={<GitBranch />}>
          <DenseTable
            rows={view.configuration.components.slice(0, 8)}
            columns={["component_identifier", "name", "revision", "status"]}
          />
          <h3>Supplier Context</h3>
          <DenseTable
            rows={view.configuration.suppliers.slice(0, 8)}
            columns={["supplier_identifier", "name", "component_identifier"]}
          />
        </Panel>
        <Panel title="Data Quality / Limitations" icon={<ShieldCheck />}>
          <ul className="limitations">
            {view.limitations.map((item) => (
              <li key={item.code}>
                <strong>{item.code}</strong>
                <span>{item.description}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </section>

      <section className="two-col">
        <Panel title="Changes" icon={<History />}>
          <DenseTable
            rows={view.changes.slice(0, 8)}
            columns={["change_identifier", "change_type", "effective_timestamp"]}
          />
        </Panel>
        <Panel title="Manufacturing / Lots" icon={<Factory />}>
          <DenseTable
            rows={view.manufacturing.lots.slice(0, 10)}
            columns={["lot_identifier", "site_identifier", "traceability_state", "manufactured_timestamp"]}
          />
        </Panel>
      </section>

      <section className="two-col">
        <Panel title="Field / Complaints" icon={<AlertTriangle />}>
          <DenseTable
            rows={view.complaints.slice(0, 10)}
            columns={["complaint_identifier", "event_timestamp", "recorded_timestamp", "status"]}
          />
        </Panel>
        <Panel title="Evidence" icon={<FileText />}>
          <DenseTable
            rows={view.evidence.slice(0, 10)}
            columns={["evidence_identifier", "evidence_type", "reliability_status", "ingestion_timestamp"]}
          />
        </Panel>
      </section>

      <section className="two-col">
        <Panel title="Risk & Controls" icon={<ShieldCheck />}>
          <DenseTable rows={view.risks.slice(0, 6)} columns={["risk_identifier", "description", "status"]} />
          <DenseTable rows={view.controls.slice(0, 6)} columns={["control_identifier", "control_type", "status"]} />
        </Panel>
        <Panel title="Provenance" icon={<CircleDot />}>
          <DenseTable
            rows={view.provenance.slice(0, 8)}
            columns={["canonical_entity_type", "source_value", "resolution_rule", "resolution_status"]}
          />
        </Panel>
      </section>

      <section className="timeline-section">
        <div className="section-title">
          <CalendarClock size={18} /> Lifecycle Timeline
        </div>
        <div className="timeline">
          {view.timeline.slice(0, 40).map((event) => (
            <article
              key={event.event_id}
              className={expandedEventId === event.event_id ? "timeline-event expanded" : "timeline-event"}
            >
              <div className="event-date">{fmt(event.event_time ?? event.effective_time)}</div>
              <div className="event-body">
                <span className="category">{event.category}</span>
                <h3>{event.title}</h3>
                <p>
                  Event {fmt(event.event_time)} · Effective {fmt(event.effective_time)} · Recorded{" "}
                  {fmt(event.recorded_time)} · Known {fmt(event.knowledge_available_time)}
                </p>
                {event.late_arriving && <span className="late">Late-arriving evidence</span>}
                {expandedEventId === event.event_id && (
                  <div className="event-details">
                    <p>
                      <strong>Description:</strong> {event.description ?? "No additional description recorded."}
                    </p>
                    <p>
                      <strong>Related entity:</strong> {event.related_entity_type ?? "Not recorded"} /{" "}
                      {event.related_entity_id ?? "Not recorded"}
                    </p>
                    <p>
                      <strong>Source:</strong> {event.source ?? "Not recorded"}
                    </p>
                    <p>
                      <strong>Provenance:</strong>{" "}
                      {event.metadata?.provenance_available === false
                        ? "Not available"
                        : "Available when recorded by the source context."}
                    </p>
                  </div>
                )}
              </div>
              <button
                className="timeline-toggle"
                aria-label={`${expandedEventId === event.event_id ? "Collapse" : "Expand"} ${event.title}`}
                aria-expanded={expandedEventId === event.event_id}
                onClick={() => setExpandedEventId((current) => (current === event.event_id ? null : event.event_id))}
              >
                <ChevronRight size={16} />
              </button>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function InvestigationAccessView({
  view,
  selectedInvestigationId,
  onSelect,
  temporalMode,
  asOf,
  onOpenDecision,
}: {
  view: Product360;
  selectedInvestigationId: string;
  onSelect: (id: string) => void;
  temporalMode: TemporalMode;
  asOf: string;
  onOpenDecision: () => void;
}) {
  const [investigations, setInvestigations] = useState<Array<Record<string, string | null>>>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const selected = investigations.find((investigation) => investigation.id === selectedInvestigationId);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api<Array<Record<string, string | null>>>(`/api/v1/products/${view.product.id}/investigations`)
      .then((items) => {
        if (!active) return;
        setInvestigations(items);
        onSelect(
          items.some((investigation) => investigation.id === selectedInvestigationId)
            ? selectedInvestigationId
            : (items[0]?.id ?? ""),
        );
        setLoadError("");
      })
      .catch((err) => {
        if (active) setLoadError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [view.product.id]);

  return (
    <div className="content">
      <section className="product-header">
        <div>
          <p className="eyebrow">Investigation access</p>
          <h2>{view.product.name}</h2>
          <p>
            Version {view.selected_version?.version_identifier ?? "not recorded"}. Select an available investigation to
            open the existing Day 10–14 workspace.
          </p>
        </div>
        <div className="version-pill">
          <ClipboardList size={16} /> {loading ? "Loading" : `${investigations.length} available`}
        </div>
      </section>
      {loadError && <div className="error">Investigations could not be loaded: {loadError}</div>}
      {!loading && !loadError && investigations.length === 0 ? (
        <section className="panel empty-state">
          <h2>No investigations available</h2>
          <p>
            The selected product has no investigation records in the current Product 360 result. No workspace has been
            created or inferred.
          </p>
        </section>
      ) : (
        <>
          <section className="panel">
            <div className="section-title">
              <ClipboardList size={18} /> Available investigations
            </div>
            <div className="investigation-list">
              {investigations.map((investigation) => (
                <button
                  key={investigation.id}
                  className={`investigation-option ${investigation.id === selectedInvestigationId ? "selected" : ""}`}
                  onClick={() => onSelect(investigation.id ?? "")}
                >
                  <strong>{investigation.investigation_identifier ?? investigation.id}</strong>
                  <span>{investigation.investigation_question ?? "No question recorded."}</span>
                  <small>
                    ID: {investigation.id} | Status: {investigation.status ?? "not recorded"}
                  </small>
                </button>
              ))}
            </div>
          </section>
          {selectedInvestigationId && (
            <InvestigationWorkspacePanel
              key={selectedInvestigationId}
              investigationId={selectedInvestigationId}
              temporalMode={temporalMode}
              asOf={asOf}
              onOpenDecision={onOpenDecision}
            />
          )}
          {!selected && (
            <div className="error inline">The selected investigation is not available in this Product 360 result.</div>
          )}
        </>
      )}
    </div>
  );
}

function EvidenceAccessView({ productEvidenceCount }: { productEvidenceCount: number }) {
  const [evidence, setEvidence] = useState<EvidenceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    api<EvidenceSummary[]>("/api/v1/evidence?limit=50")
      .then((items) => {
        if (active) {
          setEvidence(items);
          setError("");
        }
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="content">
      <section className="product-header">
        <div>
          <p className="eyebrow">Evidence access</p>
          <h2>Tenant evidence records</h2>
          <p>
            Product 360 currently shows {productEvidenceCount} evidence record{productEvidenceCount === 1 ? "" : "s"}{" "}
            linked to the selected product scope. This list is tenant-scoped and does not imply a product link.
          </p>
        </div>
        <div className="version-pill">
          <FileText size={16} /> {loading ? "Loading" : `${evidence.length} available`}
        </div>
      </section>
      {error && <div className="error">Evidence could not be loaded: {error}</div>}
      {!loading && !error && evidence.length === 0 && (
        <section className="panel empty-state">
          <h2>No evidence records available</h2>
          <p>
            No tenant-scoped evidence records were returned. This is an empty state, not a conclusion about the selected
            product.
          </p>
        </section>
      )}
      {!loading && evidence.length > 0 && (
        <section className="panel">
          <div className="section-title">
            <FileText size={18} /> Available evidence
          </div>
          <div className="evidence-list">
            {evidence.map((item) => (
              <article key={item.id}>
                <strong>{item.evidence_identifier}</strong>
                <span>{item.title}</span>
                <small>
                  {item.evidence_type} | {item.reliability_status ?? "reliability not recorded"} |{" "}
                  {item.source_system ?? "source not recorded"}
                </small>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function DecisionCenterView({
  investigationId,
  temporalMode,
  asOf,
}: {
  investigationId: string;
  temporalMode: TemporalMode;
  asOf: string;
}) {
  const [context, setContext] = useState<DecisionContext | null>(null);
  const [advisory, setAdvisory] = useState<any>(null);
  const [selectedAction, setSelectedAction] = useState("NO_DECISION_YET");
  const [rationale, setRationale] = useState("");
  const [message, setMessage] = useState("");
  const [decision, setDecision] = useState<any>(null);
  const [reviewDisposition, setReviewDisposition] = useState("APPROVED");
  const [reviewComments, setReviewComments] = useState("");
  const [reviewSubmitted, setReviewSubmitted] = useState(false);
  const rationaleRef = useRef<HTMLTextAreaElement>(null);
  const [rationaleError, setRationaleError] = useState("");
  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({ temporal_mode: temporalMode });
    if (temporalMode !== "current") params.set("as_of", `${asOf}T00:00:00Z`);
    api<DecisionContext>(`/api/v1/investigations/${investigationId}/decision-context?${params}`)
      .then((item) => {
        if (active) {
          setContext(item);
          setMessage("");
        }
      })
      .catch((err) => {
        if (active) setMessage(`Decision context unavailable: ${err.message}`);
      });
    return () => {
      active = false;
    };
  }, [investigationId, temporalMode, asOf]);
  const temporalBody = JSON.stringify({
    temporal_mode: temporalMode,
    as_of: temporalMode === "current" ? null : `${asOf}T00:00:00Z`,
  });
  const runAdvisory = () =>
    fetch(`/api/v1/investigations/${investigationId}/decision-advisory`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: temporalBody,
    })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then(setAdvisory)
      .catch((err) => setMessage(err.message));
  const recordDecision = () => {
    if (!rationale.trim()) {
      setRationaleError("Enter a human rationale before recording this decision.");
      setMessage("Human rationale is required before recording a decision.");
      rationaleRef.current?.focus();
      return;
    }
    fetch(`/api/v1/investigations/${investigationId}/decisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selected_action: selectedAction,
        rationale,
        authorized_by_ref: "CONTROLLED_DEVELOPMENT_REVIEWER",
        temporal_mode: temporalMode,
        as_of: temporalMode === "current" ? null : `${asOf}T00:00:00Z`,
      }),
    })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then((payload) => {
        setDecision(payload);
        setMessage("Decision recorded as REQUIRES_REVIEW. Complete Human Review below.");
      })
      .catch((err) => setMessage(err.message));
  };
  const submitReview = () =>
    fetch(`/api/v1/investigations/decisions/${decision.id}/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        disposition: reviewDisposition,
        reviewer_ref: "CONTROLLED_DEVELOPMENT_REVIEWER",
        comments: reviewComments,
      }),
    })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then(() => {
        setDecision({
          ...decision,
          decision_status: reviewDisposition === "APPROVED" ? "DECIDED" : "REQUIRES_ADDITIONAL_EVIDENCE",
        });
        setReviewSubmitted(true);
        setMessage(`Human review recorded: ${reviewDisposition}.`);
      })
      .catch((err) => setMessage(`Human review could not be submitted: ${err.message}`));
  return (
    <div className="content">
      <section className="product-header">
        <div>
          <p className="eyebrow">Decision Center</p>
          <h2>{context?.investigation.identifier ?? "Loading investigation"}</h2>
          <p>
            AI recommends. Authorized humans decide. Temporal context:{" "}
            {String(context?.temporal_context.mode ?? temporalMode)} as of {asOf}.
          </p>
        </div>
        <div className="version-pill">
          <ShieldCheck size={16} /> Human review required
        </div>
      </section>
      {message && <div className="error">{message}</div>}
      {context && (
        <>
          <section className="panel readiness-panel">
            <div className="section-title">
              <ShieldCheck size={18} /> Decision Readiness
            </div>
            <h2>{context.readiness.state}</h2>
            <ul className="limitations">
              {context.readiness.reasons.map((reason) => (
                <li key={reason}>
                  <strong>LIMITATION</strong>
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          </section>
          <div className="two-col">
            <Panel title="What We Know" icon={<FileText />}>
              <DecisionItems items={context.observations} empty="No persisted observations available." />
            </Panel>
            <Panel title="Challenges / Contradictions" icon={<AlertTriangle />}>
              <DecisionItems
                items={[...context.contradictions, ...context.challenges]}
                empty="No challenge output available."
              />
            </Panel>
          </div>
          <div className="two-col">
            <Panel title="Competing Hypotheses" icon={<GitBranch />}>
              <DecisionItems items={context.hypotheses} empty="No hypotheses available." />
            </Panel>
            <Panel title="Unknowns Radar" icon={<CircleDot />}>
              <DecisionItems items={context.unknowns} empty="No unknowns recorded." />
            </Panel>
          </div>
          <Panel title="Failure Chain" icon={<Network />}>
            <DecisionItems items={context.failure_chains} empty="No supportable failure chain available." />
          </Panel>
          <section className="panel">
            <div className="section-title">
              <ClipboardList size={18} /> Decision Options
            </div>
            <select
              value={selectedAction}
              onChange={(event) => setSelectedAction(event.target.value)}
              aria-label="Decision option"
            >
              {context.decision_options.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
            <label className="required-field" htmlFor="decision-rationale">
              Human rationale <span>(required)</span>
            </label>
            <textarea
              id="decision-rationale"
              ref={rationaleRef}
              aria-required="true"
              aria-invalid={Boolean(rationaleError)}
              value={rationale}
              onChange={(event) => {
                setRationale(event.target.value);
                setRationaleError("");
                if (message.includes("rationale is required")) setMessage("");
              }}
              placeholder="Explain why this option is supportable or why no decision should be made."
              rows={4}
            />
            {rationaleError && (
              <p className="field-error" role="alert">
                {rationaleError}
              </p>
            )}
            <div className="toolbar">
              <button className="primary-action secondary" onClick={runAdvisory}>
                Generate AI Advisory
              </button>
              <button className="primary-action" onClick={recordDecision}>
                Record Human Decision
              </button>
            </div>
            {advisory && (
              <div className="advisory-box">
                <strong>AI Advisory — not a human decision</strong>
                <p>Recommended action: {advisory.advisory.recommended_action}</p>
                <p>
                  {advisory.advisory.additional_evidence_needed.join(" ") ||
                    "No additional evidence need was identified by the controlled advisory."}
                </p>
              </div>
            )}
            {decision && (
              <div className="human-review-box">
                <strong>Human Review — required before finalization</strong>
                <p>Decision status: {decision.decision_status}</p>
                <select
                  value={reviewDisposition}
                  onChange={(event) => setReviewDisposition(event.target.value)}
                  disabled={reviewSubmitted}
                >
                  <option value="APPROVED">APPROVED</option>
                  <option value="REJECTED">REJECTED</option>
                  <option value="REQUIRES_ADDITIONAL_EVIDENCE">REQUIRES_ADDITIONAL_EVIDENCE</option>
                </select>
                <textarea
                  value={reviewComments}
                  onChange={(event) => setReviewComments(event.target.value)}
                  placeholder="Human review comments"
                  rows={3}
                  disabled={reviewSubmitted}
                />
                <button className="primary-action" onClick={submitReview} disabled={reviewSubmitted}>
                  {reviewSubmitted ? "Human Review Submitted" : "Submit Human Review"}
                </button>
                {reviewSubmitted && (
                  <>
                    <p className="review-success">
                      Review saved successfully. The human disposition is preserved in Decision Memory and audit
                      history.
                    </p>
                    <ControlledSignature
                      decision={decision}
                      onSigned={(result) => {
                        setDecision({ ...decision, decision_status: result.status });
                        setMessage(`Decision ${result.status} — signed.`);
                      }}
                    />
                  </>
                )}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function DecisionItems({ items, empty }: { items: Array<Record<string, any>>; empty: string }) {
  if (!items.length) return <p className="empty-copy">{empty}</p>;
  return (
    <div className="decision-items">
      {items.slice(0, 8).map((item, index) => (
        <article key={String(item.item_id ?? item.hypothesis_id ?? item.unknown_id ?? item.chain_id ?? index)}>
          <strong>{String(item.semantic_type ?? item.category ?? item.overall_status ?? "Structured context")}</strong>
          <span>
            {String(
              item.statement ?? item.text ?? item.chain_statement ?? item.description ?? "No statement recorded.",
            )}
          </span>
        </article>
      ))}
    </div>
  );
}

function ControlledSignature({ decision, onSigned }: { decision: any; onSigned: (result: any) => void }) {
  const [open, setOpen] = useState(false);
  const [session, setSession] = useState<any>(null);
  const [choice, setChoice] = useState("APPROVE");
  const [remarks, setRemarks] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [signed, setSigned] = useState<any>(null);
  const close = () => {
    setPassword("");
    setRemarks("");
    setMessage("");
    setOpen(false);
  };
  const begin = () => {
    fetch("/api/v1/auth/session")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((x) => {
        setSession(x);
        setOpen(true);
      })
      .catch(() => setMessage("Sign in is required before a controlled signature can be recorded."));
  };
  const sign = () => {
    if (!remarks.trim() || !password) {
      setMessage("Decision remarks and current password are required.");
      return;
    }
    fetch(`/api/v1/governance/decisions/${decision.id}/sign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: choice, remarks, password, object_version: decision.updated_at }),
    })
      .then(async (r) => ({
        ok: r.ok,
        status: r.status,
        data: await r.json().catch(() => ({
          detail: {
            code: "INVALID_SERVER_RESPONSE",
            message: `Server returned HTTP ${r.status} without a valid response.`,
          },
        })),
      }))
      .then(({ ok, data }) => {
        setPassword("");
        if (!ok) {
          const code = data.detail?.code;
          const messages: Record<string, string> = {
            INVALID_REAUTHENTICATION: "The entered password is incorrect.",
            APPROVAL_AUTHORITY_DENIED:
              "This role is not authorized to sign decisions. Ask an authorized approver to sign.",
            DENIED_NOT_ENTITLED: "Controlled signatures are not enabled for this tenant.",
            STALE_OBJECT_VERSION:
              "This decision changed while you were reviewing it. Reload the current version and review again.",
            DUPLICATE_SIGNATURE: "This decision version has already been signed.",
            SOD_DENIED: "The decision creator cannot sign their own decision. Use a different authorized approver.",
          };
          setMessage(
            messages[code] ?? data.detail?.message ?? `Signature could not be recorded${code ? ` (${code})` : ""}.`,
          );
          return;
        }
        setSigned(data);
        onSigned(data);
        close();
      })
      .catch(() => {
        setPassword("");
        setMessage("Signature request failed. Check that the backend is running and try again.");
      });
  };
  const meaning =
    choice === "APPROVE"
      ? "I have reviewed this record and approve this decision."
      : "I have reviewed this record and reject this decision.";
  return (
    <div className="human-review-box">
      <button className="primary-action" onClick={begin}>
        Approve or Reject — Sign
      </button>
      {message && <p role="alert">{message}</p>}
      {signed && (
        <div className="advisory-box">
          <strong>{signed.status} — SIGNED</strong>
          <p>Signature ID: {String(signed.signature_id)}</p>
          <p>
            Signed By: {signed.signer} · Role: {signed.role}
          </p>
          <p>Fingerprint: {signed.fingerprint}</p>
        </div>
      )}
      {open && (
        <div className="advisory-box">
          <strong>Controlled Decision Signature</strong>
          <p>User: {session?.display_name} (read only)</p>
          <p>Active role: {session?.active_role} (read only)</p>
          <p>
            Record: {decision.decision_identifier} · Version: {decision.updated_at} (read only)
          </p>
          <select value={choice} onChange={(e) => setChoice(e.target.value)} aria-label="Signature decision">
            <option>APPROVE</option>
            <option>REJECT</option>
          </select>
          <textarea
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            placeholder="Mandatory decision remarks"
            rows={3}
          />
          <p>{meaning}</p>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Current password"
            autoComplete="current-password"
          />
          <div className="toolbar">
            <button className="secondary-link" onClick={close}>
              Cancel
            </button>
            <button className="primary-action" onClick={sign}>
              Confirm &amp; Sign
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function InvestigationTabSummary({
  activeTab,
  workspace,
  analysis,
  hypothesisSet,
  unknownSet,
  failureChains,
  brief,
  onOpenDecision,
}: {
  activeTab: string;
  workspace: InvestigationWorkspace | null;
  analysis: InvestigationAnalysis | null;
  hypothesisSet: HypothesisSet | null;
  unknownSet: UnknownSet | null;
  failureChains: FailureChainSet | null;
  brief: InvestigationBrief | null;
  onOpenDecision: () => void;
}) {
  const summaries: Record<string, { title: string; description: string; count: string; state: string }> = {
    overview: {
      title: "Investigation overview",
      description: "Server-authorized product, temporal, evidence, and guardrail context for this case.",
      count: `${workspace?.evidence_context.length ?? 0} evidence records`,
      state: workspace ? "Context loaded" : "Loading context",
    },
    evidence: {
      title: "Evidence review",
      description: "Inspect source anchors, reliability, and gaps before interpreting the case.",
      count: `${workspace?.evidence_context.length ?? 0} linked records`,
      state: workspace?.retrieval_context?.status ?? "Not requested",
    },
    analysis: {
      title: "Observations and analysis",
      description: "Review grounded observations, contradictions, possible explanations, and missing information.",
      count: `${analysis?.observations.length ?? 0} observations`,
      state: analysis?.status ?? "Not run",
    },
    hypotheses: {
      title: "Competing hypotheses",
      description: "Compare support and contradiction without selecting an unverified winner.",
      count: `${hypothesisSet?.hypotheses.length ?? 0} hypotheses`,
      state: hypothesisSet?.status ?? "Not run",
    },
    challenger: {
      title: "Challenger review",
      description: "Test the current interpretation for unsupported assumptions and material challenges.",
      count: "Advisory only",
      state: "Human review required",
    },
    unknowns: {
      title: "Unknowns and gaps",
      description: "Make missing tests, unresolved questions, and materiality visible.",
      count: `${unknownSet?.unknowns.length ?? 0} unknowns`,
      state: "Evidence gap posture",
    },
    "failure-chain": {
      title: "Failure chain",
      description: "Show supportable relationships while preserving unresolved links and epistemic status.",
      count: `${failureChains?.chains.length ?? 0} chains`,
      state: "Causality not established",
    },
    counterfactual: {
      title: "Constrained scenario",
      description: "Explore bounded alternatives; scenario output is hypothetical, not observed evidence.",
      count: "Bounded comparison",
      state: "Human interpretation required",
    },
    brief: {
      title: "Investigation brief",
      description: "Assemble a versioned, provenance-aware package for human review.",
      count: brief ? `Version ${brief.brief_version}` : "Not generated",
      state: brief?.human_review_state ?? "Human review required",
    },
    assurance: {
      title: "AI assurance",
      description: "Inspect grounding, provenance, temporal scope, and safety limitations.",
      count: "No hidden reasoning stored",
      state: "Advisory only",
    },
    decision: {
      title: "Decision readiness",
      description: "Prepare the case for an authorized reviewer; MDARIX never makes the regulated decision.",
      count: "Human authority",
      state: "Open Decision Center",
    },
  };
  const summary = summaries[activeTab] ?? summaries.overview;
  return (
    <section className="investigation-tab-summary" aria-live="polite">
      <div>
        <span className="eyebrow">Active workspace tab</span>
        <h3>{summary.title}</h3>
        <p>{summary.description}</p>
      </div>
      <div className="investigation-tab-status">
        <strong>{summary.count}</strong>
        <span>{summary.state}</span>
        {activeTab === "decision" && (
          <button className="primary-action" onClick={onOpenDecision}>
            Open Decision Center
          </button>
        )}
      </div>
    </section>
  );
}

function InvestigationWorkspacePanel({
  investigationId,
  temporalMode: mode,
  asOf,
  onOpenDecision,
}: {
  investigationId: string;
  temporalMode: TemporalMode;
  asOf: string;
  onOpenDecision: () => void;
}) {
  const [workspace, setWorkspace] = useState<InvestigationWorkspace | null>(null);
  const [analysis, setAnalysis] = useState<InvestigationAnalysis | null>(null);
  const [hypothesisSet, setHypothesisSet] = useState<HypothesisSet | null>(null);
  const [unknownSet, setUnknownSet] = useState<UnknownSet | null>(null);
  const [failureChains, setFailureChains] = useState<FailureChainSet | null>(null);
  const [challengeSet, setChallengeSet] = useState<ChallengeSet | null>(null);
  const [activeTab, setActiveTab] = useState<
    | "overview"
    | "evidence"
    | "analysis"
    | "hypotheses"
    | "challenger"
    | "unknowns"
    | "failure-chain"
    | "counterfactual"
    | "brief"
    | "assurance"
    | "decision"
  >("overview");
  const [brief, setBrief] = useState<InvestigationBrief | null>(null);
  const [counterfactual, setCounterfactual] = useState<any>(null);
  const [counterfactualTarget, setCounterfactualTarget] = useState("Component Rev B");
  const [counterfactualType, setCounterfactualType] = useState("REMOVE_CHANGE");
  const [counterfactualStatus, setCounterfactualStatus] = useState("IDLE");
  const [error, setError] = useState("");
  const [actionStatus, setActionStatus] = useState("");
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const requestSequence = useRef(0);

  useEffect(() => {
    const sequence = ++requestSequence.current;
    const params = new URLSearchParams({ temporal_mode: mode, retrieval_top_k: "8" });
    if (mode !== "current") params.set("as_of", `${asOf}T00:00:00Z`);
    api<InvestigationWorkspace>(`/api/v1/investigations/${investigationId}/workspace?${params}`)
      .then((item) => {
        if (sequence !== requestSequence.current) return;
        setWorkspace(item);
        setAnalysis(null);
        setHypothesisSet(null);
        setUnknownSet(null);
        setFailureChains(null);
        setChallengeSet(null);
        setError("");
        setActionStatus("");
        setPendingAction(null);
      })
      .catch((err) => {
        if (sequence === requestSequence.current) {
          setError(err.message);
          setActionStatus("BACKEND ERROR: Investigation context could not be loaded.");
          setPendingAction(null);
        }
      });
  }, [investigationId, mode, asOf]);

  const runAnalysis = () => {
    const sequence = requestSequence.current;
    setPendingAction("Run Analysis");
    setActionStatus("RUNNING: AI Investigator analysis...");
    setError("");
    const body = {
      investigation_id: investigationId,
      temporal_mode: mode,
      as_of: mode === "current" ? null : `${asOf}T00:00:00Z`,
      analysis_mode: "standard",
      retrieval_top_k: 8,
    };
    fetch(`/api/v1/investigations/${investigationId}/analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then((payload) => {
        if (sequence !== requestSequence.current) return;
        setAnalysis(payload.analysis);
        setActionStatus(
          payload.analysis?.observations?.length
            ? "SUCCESS: Analysis results are displayed below."
            : "EMPTY RESULT: No observations were returned for this context.",
        );
        setPendingAction(null);
        setError("");
      })
      .catch((err) => {
        if (sequence === requestSequence.current) {
          setError(err.message);
          setActionStatus(`BACKEND ERROR: Analysis could not be completed (${err.message}).`);
          setPendingAction(null);
        }
      });
  };

  const runHypotheses = () => {
    const sequence = requestSequence.current;
    setPendingAction("Generate Hypotheses");
    setActionStatus("RUNNING: Generating competing hypotheses...");
    setError("");
    const body = {
      investigation_id: investigationId,
      temporal_mode: mode,
      as_of: mode === "current" ? null : `${asOf}T00:00:00Z`,
      investigator_question: "Generate competing hypotheses from the validated investigation analysis.",
    };
    fetch(`/api/v1/investigations/${investigationId}/hypotheses`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then((payload) => {
        if (sequence !== requestSequence.current) return;
        setHypothesisSet(payload.hypothesis_set);
        const count = payload.hypothesis_set?.hypotheses?.length ?? 0;
        setActionStatus(
          count
            ? `SUCCESS: ${count} competing hypothesis result(s) are displayed below.`
            : "INSUFFICIENT EVIDENCE: No supportable hypotheses are available for this temporal context.",
        );
        setPendingAction(null);
        setError("");
      })
      .catch((err) => {
        if (sequence === requestSequence.current) {
          setError(err.message);
          setActionStatus(`BACKEND ERROR: Hypotheses could not be generated (${err.message}).`);
          setPendingAction(null);
        }
      });
  };

  const runDay14 = () => {
    const sequence = requestSequence.current;
    setPendingAction("Run Unknowns & Chain");
    setActionStatus("RUNNING: Evaluating Unknowns Radar and Failure Chain...");
    setError("");
    const body = {
      investigation_id: investigationId,
      temporal_mode: mode,
      as_of: mode === "current" ? null : `${asOf}T00:00:00Z`,
    };
    fetch(`/api/v1/investigations/${investigationId}/challenges`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then((payload) => {
        if (sequence !== requestSequence.current) return Promise.reject(new Error("STALE_CONTEXT"));
        setChallengeSet(payload.challenge_set);
        return fetch(`/api/v1/investigations/${investigationId}/unknowns`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then((payload) => {
        if (sequence !== requestSequence.current) return Promise.reject(new Error("STALE_CONTEXT"));
        setUnknownSet(payload.unknown_set);
        return fetch(`/api/v1/investigations/${investigationId}/failure-chains`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then((payload) => {
        if (sequence !== requestSequence.current) return;
        setFailureChains(payload.failure_chain_set);
        setActionStatus(
          payload.failure_chain_set?.chains?.length
            ? "SUCCESS: Unknowns and Failure Chain results are displayed below."
            : "INSUFFICIENT EVIDENCE: No supportable failure chain is available; the controlled result remains unresolved.",
        );
        setPendingAction(null);
        setError("");
      })
      .catch((err) => {
        if (sequence === requestSequence.current && err.message !== "STALE_CONTEXT") {
          setError(err.message);
          setActionStatus(`BACKEND ERROR: Unknowns and Failure Chain could not be completed (${err.message}).`);
          setPendingAction(null);
        }
      });
  };
  const runCounterfactual = () => {
    const sequence = requestSequence.current;
    setCounterfactualStatus("VALIDATING");
    setCounterfactual(null);
    fetch(`/api/v1/investigations/${investigationId}/counterfactuals`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        temporal_mode: mode,
        as_of: mode === "current" ? null : `${asOf}T00:00:00Z`,
        intervention_type: counterfactualType,
        intervention_target: counterfactualTarget,
        intervention_description: `Explore the constrained alternative condition where ${counterfactualTarget} is removed from the candidate explanation.`,
      }),
    })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail?.message ?? response.statusText);
        return payload;
      })
      .then((payload) => {
        if (sequence !== requestSequence.current) return;
        setCounterfactual(payload.result);
        setCounterfactualStatus(payload.status ?? "SUCCESS");
      })
      .catch((err) => {
        if (sequence === requestSequence.current)
          setCounterfactualStatus(
            err.message.includes("INSUFFICIENT") ? "INSUFFICIENT EVIDENCE" : `ERROR: ${err.message}`,
          );
      });
  };
  const generateBrief = () => {
    setActionStatus("RUNNING: Generating Investigation Brief...");
    fetch(`/api/v1/investigations/${investigationId}/briefs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ temporal_mode: mode, as_of: mode === "current" ? null : `${asOf}T00:00:00Z` }),
    })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail?.message ?? response.statusText);
        return payload;
      })
      .then((payload) => {
        setBrief(payload);
        setActiveTab("brief");
        setActionStatus(`SUCCESS: Investigation Brief v${payload.brief_version} generated for review.`);
      })
      .catch((err) => setActionStatus(`BACKEND ERROR: Brief could not be generated (${err.message}).`));
  };

  return (
    <section id="investigation-workspace" className="workspace-section">
      <div className="workspace-header">
        <div>
          <div className="section-title">
            <ClipboardList size={18} /> Investigation Workspace
          </div>
          <h2>{workspace?.investigation.investigation_identifier ?? "Investigation context"}</h2>
          <p>{workspace?.investigation.investigation_question ?? "Loading deterministic investigation context."}</p>
        </div>
        <div className="toolbar compact">
          <span className="context-summary">
            {humanize(mode)} {mode === "current" ? "context" : `as of ${asOf}`}
          </span>
          <div className="segmented">
            {(["current", "event", "known"] as const).map((item) => (
              <button key={item} className={mode === item ? "selected" : ""} disabled>
                {item}
              </button>
            ))}
          </div>
          <button className="primary-action" onClick={runAnalysis} disabled={Boolean(pendingAction)}>
            {" "}
            {pendingAction === "Run Analysis" ? "Running Analysis…" : "Run Analysis"}
          </button>
          <button className="primary-action secondary" onClick={runHypotheses} disabled={Boolean(pendingAction)}>
            {" "}
            {pendingAction === "Generate Hypotheses" ? "Generating…" : "Generate Hypotheses"}
          </button>
          <button className="primary-action secondary" onClick={runDay14} disabled={Boolean(pendingAction)}>
            {" "}
            {pendingAction === "Run Unknowns & Chain" ? "Running Unknowns & Chain…" : "Run Unknowns & Chain"}
          </button>
          <button className="primary-action" onClick={generateBrief}>
            Generate Investigation Brief
          </button>
        </div>
      </div>
      <div className="workflow-tabs" role="tablist" aria-label="Investigation workflow">
        {(
          [
            "overview",
            "evidence",
            "analysis",
            "hypotheses",
            "challenger",
            "unknowns",
            "failure-chain",
            "counterfactual",
            "brief",
            "assurance",
            "decision",
          ] as const
        ).map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={activeTab === tab}
            className={activeTab === tab ? "active" : ""}
            onClick={() => {
              setActiveTab(tab);
              document.getElementById(`workflow-${tab}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
          >
            {humanize(tab)}
          </button>
        ))}
      </div>
      <InvestigationTabSummary
        activeTab={activeTab}
        workspace={workspace}
        analysis={analysis}
        hypothesisSet={hypothesisSet}
        unknownSet={unknownSet}
        failureChains={failureChains}
        brief={brief}
        onOpenDecision={onOpenDecision}
      />
      {(actionStatus || pendingAction) && (
        <div className={`action-feedback ${actionStatus.startsWith("BACKEND") ? "error-feedback" : ""}`} role="status">
          {pendingAction ? actionStatus : actionStatus}
        </div>
      )}
      {error && <div className="error inline">{error}</div>}
      {workspace && (
        <div id="workflow-overview" className="workspace-grid">
          <Panel title="Context Health" icon={<ShieldCheck />}>
            <div className="context-health">
              <Metric icon={<FileText />} label="Evidence" value={workspace.evidence_context.length} />
              <Metric
                icon={<Network />}
                label="Graph Nodes"
                value={
                  workspace.relationship_context.metadata.node_count ?? workspace.relationship_context.nodes.length
                }
              />
              <Metric
                icon={<GitBranch />}
                label="Relationships"
                value={
                  workspace.relationship_context.metadata.relationship_count ??
                  workspace.relationship_context.relationships.length
                }
              />
            </div>
            <ul className="limitations">
              {workspace.limitations.slice(0, 5).map((item) => (
                <li key={item.code}>
                  <strong>{item.code}</strong>
                  <span>{item.description}</span>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Evidence Context" icon={<FileText />}>
            <div className="evidence-list">
              {workspace.evidence_context.slice(0, 6).map((item) => (
                <article key={item.evidence_identifier}>
                  <strong>{item.evidence_identifier}</strong>
                  <span>{item.title}</span>
                  <small>
                    {item.evidence_type} | {item.reliability_status} | anchors{" "}
                    {item.chunks.filter((chunk) => chunk.source_anchor).length}
                  </small>
                </article>
              ))}
            </div>
          </Panel>
          <Panel title="Retrieval & Guardrails" icon={<CircleDot />}>
            <div className="guardrail-list">
              <p>
                <strong>Retrieval:</strong> {workspace.retrieval_context?.status ?? "Not requested"} (
                {workspace.retrieval_context?.results_count ?? 0} results)
              </p>
              <p>
                <strong>Temporal mode:</strong> {String(workspace.temporal_context.mode)}{" "}
                {workspace.temporal_context.as_of ? `as of ${workspace.temporal_context.as_of}` : ""}
              </p>
              <p>
                <strong>Human authority:</strong>{" "}
                {workspace.guardrails.human_authority_required ? "Required" : "Not recorded"}
              </p>
              <p>
                <strong>Causality:</strong> {workspace.guardrails.generates_causality ? "Generated" : "Not generated"}
              </p>
            </div>
          </Panel>
        </div>
      )}
      <section id="workflow-analysis" className="workflow-action">
        <h3>Analysis</h3>
        <p>Grounded observations and possible explanations for the selected context.</p>
        <button className="primary-action" onClick={runAnalysis} disabled={Boolean(pendingAction)}>
          {pendingAction === "Run Analysis" ? "Running Analysis…" : "Run Analysis"}
        </button>
      </section>
      {analysis && (
        <div className="analysis-grid">
          <AnalysisPanel title="Key Observations" items={analysis.observations.slice(0, 4)} />
          <AnalysisPanel title="Possible Explanations" items={analysis.possible_explanations.slice(0, 4)} />
          <AnalysisPanel title="Contradictory Evidence" items={analysis.contradictions.slice(0, 4)} />
          <AnalysisPanel title="Missing Information" items={analysis.missing_information.slice(0, 4)} />
          <AnalysisPanel title="Questions To Investigate" items={analysis.questions_to_investigate.slice(0, 5)} />
          <Panel title="Validation / Provenance" icon={<ShieldCheck />}>
            <div className="guardrail-list">
              <p>
                <strong>Status:</strong> {analysis.status}
              </p>
              <p>
                <strong>Grounding:</strong> {String(analysis.validation_summary.material_grounding_coverage)}
              </p>
              <p>
                <strong>Source anchors:</strong> {String(analysis.validation_summary.evidence_source_anchor_coverage)}
              </p>
              <p>
                <strong>Provider:</strong> {String(analysis.model_provenance.provider)}
              </p>
            </div>
          </Panel>
        </div>
      )}
      <section id="workflow-hypotheses" className="workflow-action">
        <h3>Competing hypotheses</h3>
        <p>Preserves support, contradiction, gaps, and falsification conditions without choosing a winner.</p>
        <button className="primary-action secondary" onClick={runHypotheses} disabled={Boolean(pendingAction)}>
          {pendingAction === "Generate Hypotheses" ? "Generating…" : "Generate Hypotheses"}
        </button>
      </section>
      {hypothesisSet && (
        <div className="hypothesis-section">
          <div className="section-title">
            <GitBranch size={18} /> Competing Hypotheses
          </div>
          {hypothesisSet.hypotheses.length === 0 && (
            <div className="empty-result">
              No supportable hypotheses are available for the selected temporal context. This is a controlled
              abstention, not a negative conclusion.
            </div>
          )}
          <div className="hypothesis-grid">
            {hypothesisSet.hypotheses.map((hypothesis) => (
              <article className="hypothesis-card" key={hypothesis.hypothesis_id}>
                <span className="category">{hypothesis.status}</span>
                <h3>{hypothesis.statement}</h3>
                <p>
                  <strong>Temporal fit:</strong> {hypothesis.temporal_consistency.status}
                </p>
                <p>
                  <strong>Support:</strong>{" "}
                  {hypothesis.supporting_evidence[0]?.rationale ?? "No supporting evidence recorded."}
                </p>
                <p>
                  <strong>Contradiction:</strong>{" "}
                  {hypothesis.contradicting_evidence[0]?.rationale ?? "No contradiction recorded."}
                </p>
                <p>
                  <strong>Gap:</strong> {hypothesis.evidence_gaps[0] ?? "No gap recorded."}
                </p>
                <p>
                  <strong>Would weaken:</strong>{" "}
                  {hypothesis.falsification_conditions[0] ?? "No falsification condition recorded."}
                </p>
              </article>
            ))}
          </div>
          <Panel title="Hypothesis Validation" icon={<ShieldCheck />}>
            <div className="guardrail-list">
              <p>
                <strong>Status:</strong> {hypothesisSet.status}
              </p>
              <p>
                <strong>Grounding:</strong> {String(hypothesisSet.validation_summary.material_grounding_coverage)}
              </p>
              <p>
                <strong>Source anchors:</strong> {String(hypothesisSet.validation_summary.source_anchor_coverage)}
              </p>
              <p>
                <strong>No winner score:</strong>{" "}
                {hypothesisSet.comparison.every((row) => row.no_winner_score) ? "Preserved" : "Check required"}
              </p>
            </div>
          </Panel>
        </div>
      )}
      <section id="workflow-challenger" className="workflow-action">
        <h3>Challenger, unknowns, and failure chain</h3>
        <p>Surfaces challenges and material unknowns. An unresolved failure chain is a valid controlled result.</p>
        <button className="primary-action secondary" onClick={runDay14} disabled={Boolean(pendingAction)}>
          {pendingAction === "Run Unknowns & Chain" ? "Running controlled checks…" : "Run Challenger, Unknowns & Chain"}
        </button>
      </section>
      {challengeSet && (
        <div className="analysis-grid">
          <Panel title="AI Challenger" icon={<ShieldCheck />}>
            <div className="analysis-list">
              {challengeSet.challenges.length === 0 && <p className="empty">No material challenge identified.</p>}
              {challengeSet.challenges.map((item) => (
                <article key={item.challenge_id}>
                  <span>
                    {item.challenge_type} | {item.status} | {item.materiality}
                  </span>
                  <p>{item.statement}</p>
                  <small>{item.rationale}</small>
                </article>
              ))}
            </div>
          </Panel>
        </div>
      )}
      {unknownSet && (
        <div id="workflow-unknowns" className="analysis-grid">
          <Panel title="Unknowns Radar" icon={<AlertTriangle />}>
            <div className="analysis-list">
              {unknownSet.unknowns.length === 0 && <p className="empty">No material unknowns identified.</p>}
              {unknownSet.unknowns.map((item) => (
                <article key={item.unknown_id}>
                  <span>
                    {item.category} | {item.status} | {item.materiality}
                  </span>
                  <p>
                    <strong>{item.statement}</strong>
                  </p>
                  <p>Why it matters: {item.why_it_matters}</p>
                  <small>Resolution: {item.resolution_requirement}</small>
                </article>
              ))}
            </div>
          </Panel>
          <div id="workflow-failure-chain">
            <Panel title="Failure Chain Intelligence" icon={<GitBranch />}>
              <div className="analysis-list">
                {!failureChains?.chains.length && (
                  <p className="empty">
                    No supportable failure chain is available for this context. The chain remains unresolved.
                  </p>
                )}
                {failureChains?.chains.map((chain) => (
                  <article key={chain.chain_id}>
                    <span>{chain.overall_status}</span>
                    <p>{chain.chain_statement}</p>
                    {chain.links.map((link) => (
                      <small key={link.link_id}>
                        {link.from_entity_or_state} — {link.relationship} → {link.to_entity_or_state} [
                        {link.epistemic_status}]
                      </small>
                    ))}
                  </article>
                ))}
              </div>
            </Panel>
          </div>
        </div>
      )}
      <section id="workflow-evidence" className="panel empty-state">
        <h3>Evidence review</h3>
        <p>
          Use the evidence context above to see identifiers, reliability, and source anchors for the selected
          investigation.
        </p>
      </section>
      <section id="workflow-counterfactual" className="panel counterfactual-panel">
        <div className="section-title">
          <GitBranch size={18} /> Constrained Counterfactual
        </div>
        <p className="helper-copy">
          Explore how the current explanation changes under a controlled alternative condition. Results are hypothetical
          and are not observed evidence.
        </p>
        <div className="counterfactual-controls">
          <select
            value={counterfactualType}
            onChange={(event) => setCounterfactualType(event.target.value)}
            aria-label="Intervention type"
          >
            <option value="REMOVE_CHANGE">Remove change</option>
            <option value="REPLACE_COMPONENT_REVISION">Replace component revision</option>
            <option value="REMOVE_SUPPLIER_CHANGE">Remove supplier change</option>
            <option value="REMOVE_FAILURE_CHAIN_LINK">Remove failure-chain link</option>
          </select>
          <input
            value={counterfactualTarget}
            onChange={(event) => setCounterfactualTarget(event.target.value)}
            aria-label="Counterfactual target"
            placeholder="Readable target, e.g. Component Rev B"
          />
          <button
            className="primary-action"
            onClick={runCounterfactual}
            disabled={counterfactualStatus === "VALIDATING"}
          >
            {counterfactualStatus === "VALIDATING" ? "Validating…" : "Run Counterfactual"}
          </button>
        </div>
        <p className="action-feedback" role="status">
          Status: {counterfactualStatus}
        </p>
        {counterfactual && (
          <div className="counterfactual-result">
            <strong>{counterfactual.label}</strong>
            <h3>What stays the same</h3>
            <ul>
              {counterfactual.invariants?.map((item: string) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <h3>What changes / becomes unsupported</h3>
            <ul>
              {counterfactual.relationships_no_longer_supported?.map((item: string) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <h3>What remains unexplained</h3>
            <ul>
              {counterfactual.observations_still_unexplained?.map((item: string) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <h3>Limitations</h3>
            <ul>
              {counterfactual.limitations?.map((item: any, index: number) => (
                <li key={index}>{typeof item === "string" ? item : item.description}</li>
              ))}
            </ul>
            <p>
              <strong>Conclusion:</strong> {counterfactual.conclusion}
            </p>
          </div>
        )}
      </section>
      <section id="workflow-brief" className="panel brief-panel">
        <div className="section-title">
          <FileText size={18} /> Investigation Brief
        </div>
        {!brief ? (
          <>
            <p>Assemble a versioned, evidence-grounded package for human review.</p>
            <button className="primary-action" onClick={generateBrief}>
              Generate Investigation Brief
            </button>
          </>
        ) : (
          <>
            <h2>{brief.title}</h2>
            <p>
              Version {brief.brief_version} · {brief.status} · {brief.temporal_mode}
            </p>
            <div className="advisory-box">
              <strong>AI-assisted content requires human review.</strong>
              <p>This Brief does not establish root cause or causality.</p>
            </div>
            {Object.entries(brief.content).map(([key, value]) => (
              <article key={key}>
                <h3>{humanize(key)}</h3>
                <pre>{JSON.stringify(value, null, 2)}</pre>
              </article>
            ))}
            <details>
              <summary>Provenance</summary>
              <pre>{JSON.stringify(brief.provenance, null, 2)}</pre>
            </details>
          </>
        )}
      </section>
      <section id="workflow-assurance" className="panel">
        <div className="section-title">
          <ShieldCheck size={18} /> AI Assurance
        </div>
        <h2>Deterministic Trust Engine</h2>
        <p>
          Assurance validates evidence grounding, citation integrity, tenant and ProductVersion context, temporal
          context, unsupported claims, causality restraint, provenance, and human authority.
        </p>
        <div className="guardrail-list">
          <p>
            <strong>Status:</strong> Assurance results are persisted per AI execution.
          </p>
          <p>
            <strong>Policy:</strong> Controlled AI Trust Policy
          </p>
          <p>
            <strong>Causality:</strong> NOT ESTABLISHED by assurance.
          </p>
          <p>
            <strong>Human review:</strong> REQUIRED. Assurance does not approve decisions.
          </p>
          <p>
            <strong>Confidence:</strong> No fabricated numeric confidence score is used.
          </p>
        </div>
      </section>
      <section id="workflow-decision" className="panel empty-state">
        <h3>Decision readiness</h3>
        <p>AI outputs inform the workflow. Authorized humans record decisions in the Decision Center.</p>
        <button className="primary-action" onClick={onOpenDecision}>
          Open Decision Center
        </button>
      </section>
    </section>
  );
}

createRoot(document.getElementById("root")!).render(
  <AppErrorBoundary>
    <App />
  </AppErrorBoundary>,
);
