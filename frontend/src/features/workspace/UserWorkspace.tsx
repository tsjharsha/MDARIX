import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  Settings2,
  ShieldCheck,
  Upload,
  UserRound,
  X,
} from "lucide-react";
import "../admin/console/admin-console.css";
import "../customer-admin/customer-admin.css";
import "./workspace.css";
import { signOut } from "../shared/session";
import { useFocusOnChange } from "../shared/focus";
import { SessionTimeoutWarning, useIdleSignOut } from "../shared/SessionTimeout";
import { SectionErrorBoundary } from "../../app/ErrorBoundary";
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
import { ImportDataSection } from "./sections/ImportData";
import { requestJson } from "../../app/apiClient";
import { rolesSummary } from "../../app/roles";
import { caseFromSearch, caseLinkStart, searchWithoutCase } from "./savedContext";
import { searchWithoutSignal, signalFromSearch, signalLinkStart } from "./signals";

/**
 * Each section's menu entry: `description` is the short line under its name in the menu, `guide` the one-line purpose
 * under the page heading (what you do here, in plain words).
 */
const NAV: Record<WorkspaceSection, { icon: typeof Package; description: string; guide: string; context: boolean }> = {
  "Getting started": {
    icon: Rocket,
    description: "Your free trial, step by step",
    guide: "Set up your trial one step at a time: add your data, invite your team and try a first investigation.",
    context: false,
  },
  Dashboard: {
    icon: LayoutDashboard,
    description: "Today's quality status",
    guide: "What needs attention today across your products, signals, investigations and decisions.",
    context: false,
  },
  "My Work": {
    icon: Briefcase,
    description: "Your tasks and reviews",
    guide: "Everything waiting for you: tasks assigned to you, work your roles can pick up, and evidence requests.",
    context: true,
  },
  Products: {
    icon: Package,
    description: "Products, versions and lots",
    guide: "One view of the selected product version: its parts, lots, suppliers, complaints and known data gaps.",
    context: true,
  },
  Signals: {
    icon: Radio,
    description: "Triage complaints and trends",
    guide:
      "Review new signals, decide what each needs and follow complaint trends. Signals are recorded observations, not conclusions about cause.",
    context: true,
  },
  Investigations: {
    icon: FileSearch,
    description: "Open and work your cases",
    guide:
      "Open a case and work through it step by step. MDARIX organizes evidence and possible explanations; it never concludes a root cause for you.",
    context: true,
  },
  Evidence: {
    icon: Search,
    description: "Case evidence and sources",
    guide:
      "The evidence behind each case and where every record came from. Supporting, contradicting and missing evidence stay visible side by side.",
    context: true,
  },
  Decisions: {
    icon: Gavel,
    description: "Approve, sign and verify",
    guide:
      "Review decision briefs, record and sign decisions, and verify signatures. Only people with approval authority can sign, and each signature is recorded with the exact content approved.",
    context: true,
  },
  Intelligence: {
    icon: Bot,
    description: "Ask questions, regulatory, risk",
    guide:
      "Ask questions about your records and check regulatory and risk links. AI answers show their sources and limits and never make the decision for you.",
    context: true,
  },
  "Trust & Audit": {
    icon: ShieldCheck,
    description: "Audit trail and AI checks",
    guide: "The permanent record of who did what and when, and how the AI assistants are checked and limited.",
    context: true,
  },
  "Import data": {
    icon: Upload,
    description: "Bring in CSV files",
    guide:
      "Bring records from your quality, product and supplier systems in as CSV files. Each file is checked in full before anything is saved; by default a file with any problem imports nothing, or you can import the rows that pass and get the others back to fix.",
    context: false,
  },
  "My Account": {
    icon: UserRound,
    description: "Profile, security, access",
    guide: "Your profile, sign-in security and the roles you hold in this organization.",
    context: false,
  },
  "Share feedback": {
    icon: MessageSquareText,
    description: "Tell us what to improve",
    guide: "Tell us what works and what to improve.",
    context: false,
  },
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

export function UserWorkspace({
  session,
  initialView,
  onAdminConsole,
}: {
  session: SessionContext | null;
  initialView?: string;
  /** A customer administrator working here returns to their console (App.tsx). */
  onAdminConsole?: () => void;
}) {
  // A link to a case (/app/investigations?case=INV000147) opens that case, on its product, in the view's section.
  const [caseLink] = useState(() => caseFromSearch(window.location.search));
  // A link to a signal (/app/signals?signal=SIG000023) opens that signal in Signals (the case link wins over it).
  const [signalLink] = useState(() => (caseLink ? null : signalFromSearch(window.location.search)));
  const work = useWorkContext(caseLink);
  const [start] = useState(() => {
    const base = VIEW_TO_SECTION[initialView ?? "home"] ?? ["Dashboard"];
    return caseLink ? caseLinkStart(initialView, base) : signalLinkStart(initialView, base, signalLink);
  });
  const [location, setLocation] = useState<{ section: WorkspaceSection; tab?: string; key: number }>({
    section: start[0],
    tab: start[1],
    key: 0,
  });
  const [menuOpen, setMenuOpen] = useState(false);
  const [message, setMessage] = useState<{ text: string; tone: "good" | "critical" } | null>(null);
  const [trial, setTrial] = useState<TrialStatus | null>(null);
  const idle = useIdleSignOut();
  const heading = useRef<HTMLHeadingElement>(null);
  useFocusOnChange(heading, location.key);

  useEffect(() => {
    requestJson<TrialStatus>("/api/v1/trial/status")
      .then(setTrial)
      .catch(() => setTrial(null));
  }, []);

  const visibleSections = useMemo(
    () =>
      WORKSPACE_SECTIONS.filter(
        (section) =>
          (!TRIAL_ONLY_SECTIONS.includes(section) || trial?.is_trial) &&
          sectionAllowed(section, session?.allowed_menu, session?.business_permissions),
      ),
    [session?.allowed_menu, session?.business_permissions, trial?.is_trial],
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

  // Once the case link is resolved it leaves the address (a reload then starts from the saved context), and a case
  // that could not be opened is said so.
  const caseLinkState = work.caseLink?.state;
  useEffect(() => {
    if (!caseLink || !caseLinkState || caseLinkState === "resolving") return;
    const { pathname, search, hash } = window.location;
    window.history.replaceState(window.history.state, "", `${pathname}${searchWithoutCase(search)}${hash}`);
    if (caseLinkState === "not-found")
      notify(`${caseLink} was not found in your organization, or your role cannot open it.`, "critical");
    else if (caseLinkState === "failed")
      notify(`${caseLink} could not be opened right now. Choose it in the context bar above.`, "critical");
  }, [caseLinkState]);

  // The signal link has been taken into the start screen: it leaves the address, so a reload starts on the inbox.
  // Signals itself says when the signal cannot be found.
  useEffect(() => {
    if (!signalLink) return;
    const { pathname, search, hash } = window.location;
    window.history.replaceState(window.history.state, "", `${pathname}${searchWithoutSignal(search)}${hash}`);
  }, [signalLink]);

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
            <button
              type="button"
              className="uw-trial-badge"
              onClick={() => open("Getting started")}
              aria-label={`Free trial, ${trial.days_left} ${trial.days_left === 1 ? "day" : "days"} left`}
            >
              <span className="uw-trial-badge-long" aria-hidden="true">
                Free trial · {trial.days_left} {trial.days_left === 1 ? "day" : "days"} left
              </span>
              <span className="uw-trial-badge-short" aria-hidden="true">
                Trial · {trial.days_left}d
              </span>
            </button>
          )}
          <div className="ac-user">
            <span>
              <strong>{session?.display_name ?? "User"}</strong>
              <small>{rolesSummary(session)}</small>
            </span>
            {onAdminConsole && (
              <button
                type="button"
                className="ac-secondary"
                onClick={onAdminConsole}
                aria-label="Admin console"
                title="Back to customer administration"
              >
                <Settings2 size={16} aria-hidden="true" /> <span className="ac-hide-sm">Admin console</span>
              </button>
            )}
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
                <h1 ref={heading} tabIndex={-1}>
                  {section}
                </h1>
                <p>{NAV[section].guide}</p>
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
              <SectionErrorBoundary name={section} resetKey={location.key}>
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
                  {section === "Import data" && <ImportDataSection />}
                  {section === "Share feedback" && <FeedbackSection isTrial={!!trial?.is_trial} />}
                </div>
              </SectionErrorBoundary>
            </ColumnScopeProvider>
          </main>
        </div>
        <SessionTimeoutWarning session={idle} />
      </div>
    </WorkspaceContext.Provider>
  );
}
