import { useCallback, useEffect, useMemo, useState } from "react";
import { SwitchOrganization } from "../shared/SwitchOrganization";
import { HelpMenu } from "../shared/HelpMenu";
import {
  Bot,
  Briefcase,
  Building2,
  FileSearch,
  Gavel,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareText,
  Package,
  Radio,
  Rocket,
  Search,
  ShieldCheck,
  UserRound,
  X,
} from "lucide-react";
import "../admin/console/admin-console.css";
import "../customer-admin/customer-admin.css";
import "./workspace.css";
import { signOut, useIdleSignOut } from "../shared/session";
import {
  TRIAL_ONLY_SECTIONS,
  WORKSPACE_SECTIONS,
  WorkspaceContext,
  sectionAllowed,
  type SessionContext,
  type WorkspaceApi,
  type WorkspaceSection,
} from "./workspaceContext";
import { useWorkContext } from "./useWorkContext";
import { ContextBar } from "./ContextBar";
import { DashboardSection } from "./sections/Dashboard";
import { ColumnScopeProvider } from "../tables/ColumnChooser";
import { MyWorkSection } from "./sections/MyWork";
import { ProductsSection } from "./sections/Products";
import { SignalsSection } from "./sections/Signals";
import { InvestigationsSection } from "./sections/Investigations";
import { EvidenceSection } from "./sections/Evidence";
import { DecisionsSection } from "./sections/Decisions";
import { IntelligenceSection } from "./sections/Intelligence";
import { TrustSection } from "./sections/Trust";
import { AccountSection } from "./sections/Account";
import { GettingStartedSection, type TrialStatus } from "./sections/GettingStarted";
import { FeedbackPrompt, FeedbackSection } from "./sections/Feedback";
import { requestJson } from "../../app/apiClient";

const NAV: Record<WorkspaceSection, { icon: typeof Package; description: string; context: boolean }> = {
  "Getting started": { icon: Rocket, description: "Your free trial, step by step", context: false },
  Dashboard: { icon: LayoutDashboard, description: "Live quality status", context: false },
  "My Work": { icon: Briefcase, description: "Assignments and reviews", context: true },
  Products: { icon: Package, description: "Product 360 and versions", context: true },
  Signals: { icon: Radio, description: "Complaints and trends", context: true },
  Investigations: { icon: FileSearch, description: "Cases and workspace", context: true },
  Evidence: { icon: Search, description: "Library and provenance", context: true },
  Decisions: { icon: Gavel, description: "Review, sign and verify", context: true },
  Intelligence: { icon: Bot, description: "Ask, regulatory, risk", context: true },
  "Trust & Audit": { icon: ShieldCheck, description: "AI assurance and records", context: true },
  "My Account": { icon: UserRound, description: "Profile, security, access", context: false },
  "Share feedback": { icon: MessageSquareText, description: "Tell us about your trial", context: false },
};

/** Legacy URL views map onto the new sections, so existing links and bookmarks keep working. */
export const VIEW_TO_SECTION: Record<string, [WorkspaceSection, string?]> = {
  home: ["Dashboard"],
  "my-work": ["My Work"],
  products: ["Products"],
  signals: ["Signals"],
  story: ["Investigations", "Story"],
  persona: ["Dashboard"],
  ask: ["Intelligence", "Ask MDARIX"],
  investigations: ["Investigations"],
  evidence: ["Evidence"],
  decision: ["Decisions"],
  assurance: ["Trust & Audit", "AI assurance"],
  audit: ["Trust & Audit", "Audit trail"],
  "regulatory-copilot": ["Intelligence", "Regulatory copilot"],
  "risk-traceability": ["Intelligence", "Risk & traceability"],
  "signature-verification": ["Decisions", "Verify a signature"],
};

export function UserWorkspace({ session, initialView }: { session: SessionContext | null; initialView?: string }) {
  const work = useWorkContext();
  const [start] = useState(() => VIEW_TO_SECTION[initialView ?? "home"] ?? ["Dashboard"]);
  const [location, setLocation] = useState<{ section: WorkspaceSection; tab?: string; key: number }>({
    section: start[0],
    tab: start[1],
    key: 0,
  });
  const [menuOpen, setMenuOpen] = useState(false);
  const [message, setMessage] = useState<{ text: string; tone: "good" | "critical" } | null>(null);
  const [trial, setTrial] = useState<TrialStatus | null>(null);
  useIdleSignOut();

  useEffect(() => {
    requestJson<TrialStatus>("/api/v1/trial/status")
      .then(setTrial)
      .catch(() => setTrial(null));
  }, []);

  const visibleSections = useMemo(
    () =>
      WORKSPACE_SECTIONS.filter(
        (section) =>
          (!TRIAL_ONLY_SECTIONS.includes(section) || trial?.is_trial) && sectionAllowed(section, session?.allowed_menu),
      ),
    [session?.allowed_menu, trial?.is_trial],
  );
  const open = useCallback(
    (section: WorkspaceSection, tab?: string) => {
      setLocation((current) => ({ section, tab, key: current.key + 1 }));
      setMenuOpen(false);
      setMessage(null);
      window.scrollTo({ top: 0 });
    },
    [setLocation],
  );
  const notify = useCallback((text: string, tone: "good" | "critical" = "good") => setMessage({ text, tone }), []);

  // A free-trial user starts on Getting started, unless they followed a link to a specific screen.
  useEffect(() => {
    if (trial?.is_trial && (initialView ?? "home") === "home")
      setLocation((current) => (current.key === 0 ? { ...current, section: "Getting started" } : current));
  }, [trial?.is_trial]);

  // A section the server's menu does not grant is never rendered, even from an old link.
  useEffect(() => {
    if (!visibleSections.includes(location.section)) open(visibleSections[0] ?? "My Account");
  }, [visibleSections, location.section]);

  const tenantName = session?.current_tenant?.tenant_name ?? "Your organization";
  const api: WorkspaceApi = { session, work, open, notify };
  const { section, tab } = location;

  return (
    <WorkspaceContext.Provider value={api}>
      <div className="admin-console user-workspace">
        <header className="ac-header">
          <a className="app-skip" href="#app-main">
            Skip to content
          </a>
          <button
            type="button"
            className="ac-menu-toggle"
            aria-label={menuOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((value) => !value)}
          >
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <div className="ac-brand">MDARIX</div>
          <div className="uw-tenant" title="Every screen shows only this organization's data">
            <Building2 size={15} aria-hidden="true" />
            <span>{tenantName}</span>
          </div>
          {trial?.is_trial && (
            <button type="button" className="uw-trial-badge" onClick={() => open("Getting started")}>
              Free trial · {trial.days_left} {trial.days_left === 1 ? "day" : "days"} left
            </button>
          )}
          <div className="ac-user">
            <span>
              <strong>{session?.display_name ?? "User"}</strong>
              <small>{session?.active_role ?? "No active role"}</small>
            </span>
            <SwitchOrganization />
            <HelpMenu onGettingStarted={trial?.is_trial ? () => open("Getting started") : undefined} />
            <button
              type="button"
              className="ac-secondary"
              onClick={() => void signOut()}
              aria-label="Sign out of MDARIX"
            >
              <LogOut size={16} /> <span className="ac-hide-sm">Logout</span>
            </button>
          </div>
        </header>

        <div className="ac-body">
          <nav className={`ac-nav ${menuOpen ? "open" : ""}`} aria-label="Workspace navigation">
            <p className="ac-nav-label">Workspace</p>
            {visibleSections.map((name) => {
              const { icon: Icon, description } = NAV[name];
              return (
                <button
                  type="button"
                  key={name}
                  className={section === name ? "selected" : ""}
                  aria-current={section === name ? "page" : undefined}
                  onClick={() => open(name)}
                >
                  <Icon size={18} aria-hidden="true" />
                  <span>
                    <strong>{name}</strong>
                    <small>{description}</small>
                  </span>
                </button>
              );
            })}
            <p className="ca-nav-scope">
              Evidence before inference. Authorized humans decide. You see only {tenantName}'s data.
            </p>
          </nav>

          <main className="ac-main" id="app-main" tabIndex={-1} data-workspace-section={section}>
            <div className="ac-page-head">
              <div>
                <p className="ac-eyebrow">{tenantName}</p>
                <h1>{section}</h1>
                <p>{NAV[section].description}</p>
              </div>
            </div>
            {NAV[section].context && <ContextBar />}
            {trial?.is_trial && section !== "Share feedback" && (
              <FeedbackPrompt onOpen={() => open("Share feedback")} />
            )}
            {message && (
              <div className={`ac-message tone-${message.tone}`} role="status">
                {message.text}
                <button type="button" className="ac-link" onClick={() => setMessage(null)} aria-label="Dismiss message">
                  <X size={14} />
                </button>
              </div>
            )}
            {/* Every list on a page offers the field chooser; each page remembers its own choice of columns. */}
            <ColumnScopeProvider key={location.key} scope={`workspace:${section}`}>
              <div className="ca-section">
                {section === "Getting started" && <GettingStartedSection />}
                {section === "Dashboard" && <DashboardSection />}
                {section === "My Work" && <MyWorkSection tab={tab} />}
                {section === "Products" && <ProductsSection tab={tab} />}
                {section === "Signals" && <SignalsSection tab={tab} />}
                {section === "Investigations" && <InvestigationsSection tab={tab} />}
                {section === "Evidence" && <EvidenceSection tab={tab} />}
                {section === "Decisions" && <DecisionsSection tab={tab} />}
                {section === "Intelligence" && <IntelligenceSection tab={tab} />}
                {section === "Trust & Audit" && <TrustSection tab={tab} />}
                {section === "My Account" && <AccountSection tab={tab} />}
                {section === "Share feedback" && <FeedbackSection />}
              </div>
            </ColumnScopeProvider>
          </main>
        </div>
      </div>
    </WorkspaceContext.Provider>
  );
}
