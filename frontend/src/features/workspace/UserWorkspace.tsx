import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SwitchOrganization } from "../shared/SwitchOrganization";
import { HelpMenu } from "../shared/HelpMenu";
import {
  Bot,
  Briefcase,
  BadgeCheck,
  Building2,
  ClipboardList,
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
  ShieldAlert,
  Signpost,
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
import { ReadinessSection } from "./sections/Readiness";
import { ColumnScopeProvider } from "../tables/ColumnChooser";
import { MyWorkSection } from "./sections/MyWork";
import { ProductsSection } from "./sections/Products";
import { ComplaintsSection } from "./sections/Complaints";
import { SignalsSection } from "./sections/Signals";
import { InvestigationsSection } from "./sections/Investigations";
import { EvidenceSection } from "./sections/Evidence";
import { DecisionsSection } from "./sections/Decisions";
import { RecordsSection } from "./sections/Records";
import { ChapterDone } from "./sections/ChapterDone";
import type { StoryChapter } from "./trialStory";
import { IntelligenceSection } from "./sections/Intelligence";
import { TrustSection } from "./sections/Trust";
import { AccountSection } from "./sections/Account";
import { GettingStartedSection, type TrialStatus } from "./sections/GettingStarted";
import { FeedbackPrompt, FeedbackSection } from "./sections/Feedback";
import { ColleagueWelcome } from "./sections/ColleagueWelcome";
import { ImportDataSection } from "./sections/ImportData";
import { TrialNextStepsSection } from "./sections/TrialNextSteps";
import { NEXT_STEPS_SUBTITLE, NEXT_STEPS_SUMMARY } from "../help/trialNextSteps";
import { requestJson } from "../../app/apiClient";
import { rolesSummary } from "../../app/roles";
import { caseFromSearch, caseLinkStart, searchWithoutCase } from "./savedContext";
import { searchWithoutSignal, signalFromSearch, signalLinkStart } from "./signals";
import { PARKED_SECTIONS, featureSetOf, routeFor } from "../../app/featureSet";
import {
  addressFor,
  isWorkspaceHistoryState,
  locationFromAddress,
  type WorkspaceHistoryState,
} from "./workspaceAddress";

/**
 * Each section's menu entry: `description` is the short line under its name in the menu, `guide` the one-line purpose
 * under the page heading (what you do here, in plain words).
 */
const NAV: Record<WorkspaceSection, { icon: typeof Package; description: string; guide: string; context: boolean }> = {
  "Getting started": {
    icon: Rocket,
    description: "Your free trial, as a story",
    guide:
      "The quality loop MDARIX closes, chapter by chapter: what your records show in each, why inspectors care in 2026, and where to try it. Start with the sample data, then upload your own export.",
    context: false,
  },
  Readiness: {
    icon: ShieldAlert,
    description: "What an inspector would find",
    guide:
      "What an FDA investigator or a notified-body auditor would find in your complaints, reports, trends and CAPAs today, read from your own records. Every number opens the records behind it.",
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
  Complaints: {
    icon: ClipboardList,
    description: "Second look and backlog",
    guide:
      "Find complaints hidden as cancellations, inquiries or No Fault Found, and see which open complaints wait in no signal and no case past your target. A person decides; MDARIX never changes your records.",
    context: false,
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
  Records: {
    icon: BadgeCheck,
    description: "CAPA checks, risk file input",
    guide:
      "What you hand an inspector or a management review: every CAPA's effectiveness check, planned with criteria and a date, reminded before the day, and signed with its result and the evidence seen; and whether each product's post-market data reached its risk file.",
    context: false,
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
  "Next steps": {
    icon: Signpost,
    description: NEXT_STEPS_SUBTITLE,
    guide: NEXT_STEPS_SUMMARY,
    context: false,
  },
};

/** Under the MVP feature set Records and My Work also hold what the parked sections did (app/featureSet.ts). */
const MVP_NAV: Partial<Record<WorkspaceSection, { description: string; guide: string }>> = {
  "My Work": {
    description: "Your tasks, approvals and requests",
    guide:
      "Everything waiting for you: tasks assigned to you, work your roles can pick up, decisions awaiting your signature and evidence requests.",
  },
  Records: {
    description: "CAPA checks, risk file, audit trail",
    guide:
      "What you hand an inspector or a management review: every CAPA's effectiveness check, signed with its result and the evidence seen; whether post-market data reached the risk file; the audit trail with each case's timeline; reports; and signature verification.",
  },
};

/** A section's menu line and purpose under this feature set. */
const navText = (section: WorkspaceSection, mvp: boolean) => (mvp && MVP_NAV[section]) || NAV[section];

/** Legacy URL views map onto the new sections, so existing links and bookmarks keep working. */
export const VIEW_TO_SECTION: Record<string, [WorkspaceSection, string?]> = {
  home: ["Dashboard"],
  readiness: ["Readiness"],
  "my-work": ["My Work"],
  products: ["Products"],
  complaints: ["Complaints"],
  signals: ["Signals"],
  story: ["Investigations", "Story"],
  persona: ["Dashboard"],
  ask: ["Intelligence", "Ask MDARIX"],
  investigations: ["Investigations"],
  evidence: ["Evidence"],
  decision: ["Decisions"],
  records: ["Records"],
  assurance: ["Trust & Audit", "AI assurance"],
  audit: ["Trust & Audit", "Audit trail"],
  "regulatory-copilot": ["Intelligence", "Regulatory copilot"],
  "risk-traceability": ["Intelligence", "Risk & traceability"],
  "signature-verification": ["Decisions", "Verify a signature"],
  "next-steps": ["Next steps"],
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
  // Under the MVP feature set a case's evidence is a step of the case page (app/featureSet.ts routeFor), and every
  // screen has its own address (workspaceAddress.ts).
  const featureSet = featureSetOf(session?.feature_set);
  // The screen the address names (?section=, ?step=, ?tab=), under the MVP feature set only.
  const [addressed] = useState(() =>
    featureSet === "mvp"
      ? locationFromAddress(window.location.pathname, window.location.search, VIEW_TO_SECTION, WORKSPACE_SECTIONS)
      : null,
  );
  const [start] = useState(() => {
    const base = VIEW_TO_SECTION[initialView ?? "home"] ?? ["Dashboard"];
    const [section, tab] = addressed
      ? [addressed.section, addressed.tab]
      : caseLink
        ? caseLinkStart(initialView, base)
        : signalLinkStart(initialView, base, signalLink);
    const routed = routeFor(section, tab, featureSet);
    return [routed.section as WorkspaceSection, routed.tab] as const;
  });
  const [location, setLocation] = useState<{ section: WorkspaceSection; tab?: string; key: number }>({
    section: start[0],
    tab: start[1],
    key: 0,
  });
  // The step the case page shows (it reports each change), for its address.
  const [step, setStep] = useState<string | undefined>(undefined);
  const [menuOpen, setMenuOpen] = useState(false);
  const [message, setMessage] = useState<{ text: string; tone: "good" | "critical" } | null>(null);
  const [trial, setTrial] = useState<TrialStatus | null>(null);
  const [trialChecked, setTrialChecked] = useState(false);
  const idle = useIdleSignOut();
  const heading = useRef<HTMLHeadingElement>(null);
  useFocusOnChange(heading, location.key);

  useEffect(() => {
    requestJson<TrialStatus>("/api/v1/trial/status")
      .then(setTrial)
      .catch(() => setTrial(null))
      .finally(() => setTrialChecked(true));
  }, []);
  // The default start screen waits for the trial status: a trial starts on Getting started, so showing the usual first
  // screen meanwhile made it flash before Getting started.
  const choosingStart = !trialChecked && (initialView ?? "home") === "home" && !addressed;

  const visibleSections = useMemo(
    () =>
      WORKSPACE_SECTIONS.filter(
        (section) =>
          (!TRIAL_ONLY_SECTIONS.includes(section) || trial?.is_trial) &&
          !(featureSet === "mvp" && PARKED_SECTIONS.includes(section)) &&
          sectionAllowed(section, session?.allowed_menu, session?.business_permissions),
      ),
    [session?.allowed_menu, session?.business_permissions, trial?.is_trial, featureSet],
  );
  const open = useCallback(
    (section: WorkspaceSection, tab?: string) => {
      const routed = routeFor(section, tab, featureSet);
      setLocation((current) => ({
        section: routed.section as WorkspaceSection,
        tab: routed.tab,
        key: current.key + 1,
      }));
      setStep(undefined);
      setMenuOpen(false);
      setMessage(null);
      window.scrollTo({ top: 0 });
    },
    [setLocation, featureSet],
  );
  const notify = useCallback((text: string, tone: "good" | "critical" = "good") => setMessage({ text, tone }), []);
  // A trial's next chapter, opened from the "chapter done" banner: its screen (and its case), else Getting started.
  const openChapter = (chapter: StoryChapter) => {
    const section = chapter.opens.section as WorkspaceSection;
    if (
      chapter.code === "YOUR_DATA" ||
      section === "Getting started" ||
      !sectionAllowed(section, session?.allowed_menu, session?.business_permissions)
    )
      return open("Getting started");
    if (chapter.case) work.setInvestigationId(chapter.case.id, chapter.case.product_id);
    open(section, chapter.opens.tab ?? undefined);
  };
  const reportStep = useCallback((tab: string) => setStep(tab), []);

  // Once the case link is resolved it leaves the address (a reload then starts from the saved context), and a case
  // that could not be opened is said so.
  const caseLinkState = work.caseLink?.state;
  useEffect(() => {
    if (!caseLink || !caseLinkState || caseLinkState === "resolving") return;
    // Under the MVP feature set the address keeps naming the case (workspaceAddress.ts), so it stays.
    if (featureSet !== "mvp") {
      const { pathname, search, hash } = window.location;
      window.history.replaceState(window.history.state, "", `${pathname}${searchWithoutCase(search)}${hash}`);
    }
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
    if (trial?.is_trial && (initialView ?? "home") === "home" && !addressed)
      setLocation((current) => (current.key === 0 ? { ...current, section: "Getting started" } : current));
  }, [trial?.is_trial]);

  // Under the MVP feature set the address follows the screen: the section, and on the case page the case and its step
  // (workspaceAddress.ts). Each move is a new history entry, so Back returns to the previous screen; the first
  // address, and one restored by Back or Forward, replace the current entry instead.
  const selectedCase = work.investigations.find((item) => String(item.id) === work.investigationId);
  const caseRef = selectedCase ? (selectedCase.business_id ?? selectedCase.investigation_identifier ?? null) : null;
  const addressSynced = useRef(false);
  const restoring = useRef(false);
  const caseResolving = work.caseLink?.state === "resolving";
  useEffect(() => {
    if (featureSet !== "mvp" || caseResolving) return;
    const onCasePage = location.section === "Investigations";
    const tab = onCasePage ? (step ?? location.tab) : location.tab;
    const next = addressFor({ section: location.section, tab, caseRef: onCasePage ? caseRef : null });
    const { pathname, search, hash } = window.location;
    if (next !== `${pathname}${search}`) {
      const state: WorkspaceHistoryState = {
        mdarixWorkspace: true,
        section: location.section,
        tab,
        caseId: work.investigationId || null,
        productId: work.productId || null,
      };
      if (addressSynced.current && !restoring.current) window.history.pushState(state, "", `${next}${hash}`);
      else window.history.replaceState(state, "", `${next}${hash}`);
    }
    addressSynced.current = true;
    restoring.current = false;
  }, [featureSet, caseResolving, location.key, location.section, location.tab, step, caseRef]);

  // Back and Forward restore the screen and its case from what the history entry kept.
  const workRef = useRef(work);
  workRef.current = work;
  useEffect(() => {
    if (featureSet !== "mvp") return;
    const onPopState = (event: PopStateEvent) => {
      if (!isWorkspaceHistoryState(event.state)) return;
      const state = event.state;
      restoring.current = true;
      setLocation((current) => ({ section: state.section, tab: state.tab, key: current.key + 1 }));
      setStep(state.tab);
      const current = workRef.current;
      if (state.caseId && state.caseId !== current.investigationId)
        current.setInvestigationId(state.caseId, state.productId ?? undefined);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [featureSet]);

  // A section the server's menu does not grant is never rendered, even from an old link. A trial-only section (a link
  // to Next steps in a reminder email) waits for the trial status before it is judged.
  useEffect(() => {
    if (!trialChecked && TRIAL_ONLY_SECTIONS.includes(location.section)) return;
    if (!visibleSections.includes(location.section)) open(visibleSections[0] ?? "My Account");
  }, [visibleSections, location.section, trialChecked]);

  const tenantName = session?.current_tenant?.tenant_name ?? "Your organization";
  const api: WorkspaceApi = { session, work, open, notify, reportStep, isTrial: !!trial?.is_trial };
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
            <HelpMenu onGettingStarted={trial?.is_trial ? () => open("Getting started", "Your data") : undefined} />
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
              const { icon: Icon } = NAV[name];
              const { description } = navText(name, featureSet === "mvp");
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
            {choosingStart ? (
              <p className="ac-empty" role="status">
                Opening your workspace…
              </p>
            ) : (
              <>
                <div className="ac-page-head">
                  <div>
                    <p className="ac-eyebrow">{tenantName}</p>
                    <h1 ref={heading} tabIndex={-1}>
                      {section}
                    </h1>
                    <p>{navText(section, featureSet === "mvp").guide}</p>
                  </div>
                </div>
                {NAV[section].context && <ContextBar />}
                {/* A colleague the owner invited is greeted by name on their first screens (UX-26). */}
                {trial?.is_trial && <ColleagueWelcome me={trial.me} />}
                {trial?.is_trial && section !== "Share feedback" && (
                  <FeedbackPrompt onOpen={() => open("Share feedback")} />
                )}
                {trial?.is_trial && <ChapterDone refreshKey={location.key} onOpen={openChapter} />}
                {message && (
                  <div className={`ac-message tone-${message.tone}`} role="status">
                    {message.text}
                    <button
                      type="button"
                      className="ac-link"
                      onClick={() => setMessage(null)}
                      aria-label="Dismiss message"
                    >
                      <X size={14} />
                    </button>
                  </div>
                )}
                {/* Every list on a page offers the field chooser; each page remembers its own choice of columns. */}
                <ColumnScopeProvider key={location.key} scope={`workspace:${section}`}>
                  <SectionErrorBoundary name={section} resetKey={location.key}>
                    <div className="ca-section">
                      {section === "Getting started" && <GettingStartedSection focus={tab} />}
                      {section === "Readiness" && <ReadinessSection />}
                      {section === "Dashboard" && <DashboardSection />}
                      {section === "My Work" && <MyWorkSection tab={tab} />}
                      {section === "Products" && <ProductsSection tab={tab} />}
                      {section === "Complaints" && <ComplaintsSection tab={tab} />}
                      {section === "Signals" && <SignalsSection tab={tab} />}
                      {section === "Investigations" && <InvestigationsSection tab={tab} />}
                      {section === "Evidence" && <EvidenceSection tab={tab} />}
                      {section === "Decisions" && <DecisionsSection tab={tab} />}
                      {section === "Records" && <RecordsSection tab={tab} />}
                      {section === "Intelligence" && <IntelligenceSection tab={tab} />}
                      {section === "Trust & Audit" && <TrustSection tab={tab} />}
                      {section === "My Account" && <AccountSection tab={tab} />}
                      {section === "Import data" && <ImportDataSection />}
                      {section === "Share feedback" && <FeedbackSection isTrial={!!trial?.is_trial} />}
                      {section === "Next steps" && trial?.is_trial && <TrialNextStepsSection />}
                    </div>
                  </SectionErrorBoundary>
                </ColumnScopeProvider>
              </>
            )}
          </main>
        </div>
        <SessionTimeoutWarning session={idle} />
      </div>
    </WorkspaceContext.Provider>
  );
}
