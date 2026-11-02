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
  Telescope,
  TrendingUp,
  Upload,
  Users,
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
  NEW_ONLY_SECTIONS,
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
import { AlertsBell } from "./sections/Reminders";
import { ColumnScopeProvider } from "../tables/ColumnChooser";
import { MyWorkSection, NewMyWorkSection } from "./sections/MyWork";
import { ComplaintViews } from "./sections/ComplaintViews";
import { ProductsSection } from "./sections/Products";
import { ComplaintsSection } from "./sections/Complaints";
import { SignalsSection } from "./sections/Signals";
import { InvestigationsSection } from "./sections/Investigations";
import { EvidenceSection } from "./sections/Evidence";
import { DecisionsSection } from "./sections/Decisions";
import { NewRecordsSection, RecordsSection } from "./sections/Records";
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
import { LookAheadSection } from "./sections/LookAhead";
import { LOOK_AHEAD_SUBTITLE, LOOK_AHEAD_SUMMARY } from "./partyPreview";
import { NEXT_STEPS_SUBTITLE, NEXT_STEPS_SUMMARY } from "../help/trialNextSteps";
import { requestJson } from "../../app/apiClient";
import { rolesSummary } from "../../app/roles";
import { caseFromSearch, caseLinkStart, searchWithoutCase } from "./savedContext";
import { signalFromSearch, signalLinkStart } from "./signals";
import { zoneName } from "../../app/dates";
import { PARKED_SECTIONS, featureSetOf, routeFor } from "../../app/featureSet";
import { NEW_MENU, NEW_PLACES, OLD_VIEWS, navigationOf, placeLabel, placeOf } from "../../app/linkTable";
import { TrendsSection } from "./sections/Trends";
import { SettingsSection } from "./sections/Settings";
import { TeamSection } from "./sections/Team";
import { ComplaintPage } from "./sections/ComplaintPage";
import { carryOverColumnChoices, columnScopeFor } from "../tables/columnViews";
import {
  addressFor,
  isWorkspaceHistoryState,
  locationFromAddress,
  restoreKind,
  type WorkspaceHistoryState,
} from "./workspaceAddress";

/**
 * Each section's menu entry: `description` is the short line under its name in the menu, `guide` the one-line purpose
 * under the page heading (what you do here, in plain words).
 */
/** What the trial's records are (the server's PRACTICE_LABEL, backend/app/reportability/markets.py). */
const TRIAL_DATA_NOTE =
  "Practice record: made in a free trial with sample or de-identified data. Not your regulatory record. PDFs carry this as a watermark.";

const NAV: Record<WorkspaceSection, { icon: typeof Package; description: string; guide: string; context: boolean }> = {
  "Getting started": {
    icon: Rocket,
    description: "Your free trial, as a story",
    guide:
      "Your trial as a story, chapter by chapter: what your records show and where to try it. Start with the sample data, then upload your own export.",
    context: false,
  },
  Readiness: {
    icon: ShieldAlert,
    description: "Inspection checks, oversight",
    guide:
      "What an inspector or auditor would find in your records today and, under Oversight, what is overdue or due soon. Every number opens its records.",
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
    description: "Triage, first contact, backlog",
    guide:
      "Triage urgent events first, check calls for hidden complaints, close routine complaints and find complaints hidden as cancellations, inquiries or No Fault Found.",
    context: false,
  },
  Signals: {
    icon: Radio,
    description: "Triage complaints and trends",
    guide:
      "Review new signals, decide what each needs and follow complaint trends. A signal is an observation, not a cause.",
    context: true,
  },
  Investigations: {
    icon: FileSearch,
    description: "Open and work your cases",
    guide: "Open a case and work through it step by step, with its evidence and possible explanations.",
    context: true,
  },
  Evidence: {
    icon: Search,
    description: "Case evidence and sources",
    guide:
      "The evidence behind each case and where each record came from: supporting, contradicting and missing, side by side.",
    context: true,
  },
  Decisions: {
    icon: Gavel,
    description: "Approve, sign and verify",
    guide:
      "Review decision briefs, sign decisions and verify signatures. Each signature keeps the exact content approved.",
    context: true,
  },
  Records: {
    icon: BadgeCheck,
    description: "CAPA checks, risk file input",
    guide:
      "What you hand an inspector or a management review: each CAPA's effectiveness check, and whether post-market data reached the risk file.",
    context: false,
  },
  Intelligence: {
    icon: Bot,
    description: "Ask questions, regulatory, risk",
    guide: "Ask questions about your records and check regulatory and risk links. Each answer shows its sources.",
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
    description: "Bring in Excel or CSV files",
    guide:
      "Bring in Excel or CSV files from your quality, product and supplier systems. Each file is checked in full before anything is saved.",
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
  "Look ahead": {
    icon: Telescope,
    description: LOOK_AHEAD_SUBTITLE,
    guide: LOOK_AHEAD_SUMMARY,
    context: false,
  },
  "Next steps": {
    icon: Signpost,
    description: NEXT_STEPS_SUBTITLE,
    guide: NEXT_STEPS_SUMMARY,
    context: false,
  },
  // The new navigation's own screens (0.10.68).
  Trends: {
    icon: TrendingUp,
    description: "Is a product problem rising?",
    guide:
      "Each product version against its own history, and the trends to review. A trend is an observation, not a cause.",
    context: true,
  },
  Settings: {
    icon: Settings2,
    description: "Rules, windows, guides, calendar",
    guide:
      "How MDARIX counts and checks for your organization. Each setting says who can change it; everyone can read it.",
    context: false,
  },
  Team: {
    icon: Users,
    description: "Who works here",
    guide: "The people in your organization and their roles.",
    context: false,
  },
  Complaint: {
    icon: ClipboardList,
    description: "One complaint",
    guide: "",
    context: false,
  },
};

/** The new navigation's menu lines and page purposes (0.10.68), where they differ from the classic ones. */
const NEW_NAV: Partial<Record<WorkspaceSection, { description: string; guide: string }>> = {
  "My Work": {
    description: "What needs you today",
    guide: "Your next step first, then your tasks, approvals, requests and the queues your roles work.",
  },
  Complaints: {
    description: "Every complaint, in views",
    guide:
      "One list of complaints. Choose a view: to triage, due soon, past target, reporting and more. Each complaint opens its own page.",
  },
  Records: {
    description: "Readiness, documents, audit trail",
    guide:
      "What you hand an inspector: inspection readiness, documents, decision and CAPA records, the audit trail and every export.",
  },
  "My Account": {
    description: "Profile, security, away",
    guide: "Your profile, sign-in security, the roles you hold, and when you will be away.",
  },
};

/** Under the MVP feature set Records and My Work also hold what the parked sections did (app/featureSet.ts). */
const MVP_NAV: Partial<Record<WorkspaceSection, { description: string; guide: string }>> = {
  "My Work": {
    description: "Your tasks, approvals and requests",
    guide:
      "Everything waiting for you: your tasks, work your roles can pick up, decisions to sign and evidence requests.",
  },
  Records: {
    description: "CAPA checks, risk file, audit trail",
    guide:
      "What you hand an inspector: CAPA effectiveness checks, risk file input, the audit trail, reports and signature verification.",
  },
};

/** A section's menu line and purpose under this feature set and navigation. */
const navText = (section: WorkspaceSection, mvp: boolean, fresh = false) =>
  (fresh && NEW_NAV[section]) || (mvp && MVP_NAV[section]) || NAV[section];

/** Former and current addresses (/app/<view>) map onto sections, so existing links and bookmarks keep working (the
 * old -> new link table, app/linkTable.json). */
export const VIEW_TO_SECTION = OLD_VIEWS as Record<string, [WorkspaceSection, string?]>;

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
  // The organization's navigation: the new one (stage 7) only under the MVP feature set, whose screens have addresses.
  const navigation = featureSet === "mvp" ? navigationOf(session?.navigation) : "classic";
  const fresh = navigation === "new";
  // The screen the address names (?section=, ?step=, ?tab=), under the MVP feature set only.
  const [addressed] = useState(() =>
    featureSet === "mvp"
      ? locationFromAddress(window.location.pathname, window.location.search, VIEW_TO_SECTION, WORKSPACE_SECTIONS)
      : null,
  );
  const [start] = useState(() => {
    // The new navigation starts on My work, whose main button names the next step.
    const base =
      fresh && (initialView ?? "home") === "home"
        ? (["My Work"] as [WorkspaceSection])
        : (VIEW_TO_SECTION[initialView ?? "home"] ?? ["Dashboard"]);
    const [section, tab] = addressed
      ? [addressed.section, addressed.tab]
      : caseLink
        ? caseLinkStart(initialView, base)
        : signalLinkStart(initialView, base, signalLink);
    const routed = routeFor(section, tab, featureSet, navigation);
    return [routed.section as WorkspaceSection, routed.tab] as const;
  });
  const [location, setLocation] = useState<{ section: WorkspaceSection; tab?: string; key: number }>({
    section: start[0],
    tab: start[1],
    key: 0,
  });
  // The tab the section shows now, with the record, panel and filters it carries (each section reports a change; the
  // case page its step), for the screen's address; undefined until the section reports one.
  const [shown, setShown] = useState<string | undefined>(undefined);
  // Whether the next address replaces the current history entry (a filter changed) instead of adding one.
  const replaceNext = useRef(false);
  // Lists' column choices were kept under the section's name until 0.10.67: carried to the screen's view id once.
  useState(() => {
    try {
      return carryOverColumnChoices(window.localStorage);
    } catch {
      return 0; // No storage in this browser: nothing to carry over.
    }
  });
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
          (fresh ? !!NEW_PLACES[section] : !NEW_ONLY_SECTIONS.includes(section)) &&
          sectionAllowed(section, session?.allowed_menu, session?.business_permissions),
      ),
    [session?.allowed_menu, session?.business_permissions, trial?.is_trial, featureSet, fresh],
  );
  // The new navigation's menu: the four main screens; Settings, Team and Account sit at the top right.
  const menuSections = fresh ? visibleSections.filter((name) => NEW_MENU.main.includes(name)) : visibleSections;
  const topSections = fresh ? visibleSections.filter((name) => NEW_MENU.top.includes(name)) : [];
  const open = useCallback(
    (section: WorkspaceSection, tab?: string) => {
      const routed = routeFor(section, tab, featureSet, navigation);
      setLocation((current) => ({
        section: routed.section as WorkspaceSection,
        tab: routed.tab,
        key: current.key + 1,
      }));
      setShown(undefined);
      setMenuOpen(false);
      setMessage(null);
      window.scrollTo({ top: 0 });
    },
    [setLocation, featureSet, navigation],
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
    open(section, placeOf(chapter.opens).tab);
  };
  const reportTab = useCallback((tab: string, how: "push" | "replace" = "push") => {
    replaceNext.current = how === "replace";
    setShown(tab);
  }, []);

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
      notify(`${caseLink} could not be opened right now. Open it from Investigations.`, "critical");
  }, [caseLinkState]);

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
  // The screen (location.key) whose history entry the address is now.
  const entryKey = useRef(-1);
  const caseResolving = work.caseLink?.state === "resolving";
  useEffect(() => {
    if (featureSet !== "mvp" || caseResolving) return;
    const onCasePage = location.section === "Investigations";
    const tab = shown ?? location.tab;
    const next = addressFor({ section: location.section, tab, caseRef: onCasePage ? caseRef : null });
    const { pathname, search, hash } = window.location;
    const state: WorkspaceHistoryState = {
      mdarixWorkspace: true,
      section: location.section,
      tab,
      caseId: work.investigationId || null,
      productId: work.productId || null,
    };
    // An address opened as it is (a link, a refresh) already reads right, but its entry must still hold the screen,
    // or Back to it would restore nothing (a panel opened after it stayed open).
    if (next === `${pathname}${search}`) window.history.replaceState(state, "", `${next}${hash}`);
    else {
      // A filter (or a tab said when a section opens) replaces this screen's own entry; the first address of a
      // newly opened screen is always a new entry, so Back returns to the screen before it.
      const replace =
        !addressSynced.current || restoring.current || (replaceNext.current && entryKey.current === location.key);
      if (replace) window.history.replaceState(state, "", `${next}${hash}`);
      else window.history.pushState(state, "", `${next}${hash}`);
    }
    if (entryKey.current === location.key) replaceNext.current = false;
    entryKey.current = location.key;
    addressSynced.current = true;
    restoring.current = false;
  }, [featureSet, caseResolving, location.key, location.section, location.tab, shown, caseRef]);

  // Back and Forward restore the screen and its case from what the history entry kept.
  const workRef = useRef(work);
  workRef.current = work;
  const shownRef = useRef({ section: location.section as string, tab: shown ?? location.tab });
  shownRef.current = { section: location.section, tab: shown ?? location.tab };
  useEffect(() => {
    if (featureSet !== "mvp") return;
    const onPopState = (event: PopStateEvent) => {
      if (!isWorkspaceHistoryState(event.state)) return;
      const state = event.state;
      // The same tab with another panel or filter: only what it carries changes (a panel closes or opens again);
      // another tab or screen is opened afresh. The address is already the entry's, so nothing is pushed for it.
      const kind = restoreKind(shownRef.current, state);
      if (kind !== "nothing") restoring.current = true;
      if (kind === "carried") setShown(state.tab);
      else if (kind === "screen") {
        setLocation((current) => ({ section: state.section, tab: state.tab, key: current.key + 1 }));
        setShown(state.tab);
      }
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
  const api: WorkspaceApi = {
    session,
    work,
    open,
    notify,
    reportStep: reportTab,
    reportTab,
    shownTab: shown ?? location.tab,
    isTrial: !!trial?.is_trial,
    navigation,
  };
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
          <div className="ac-brand">
            <i className="ac-brand-tile" aria-hidden="true">
              M
            </i>
            <b className="ac-brand-word">MDARIX</b>
          </div>
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
          {/* One label for the trial's data (V5), instead of practice notes on seven screens; PDFs carry a watermark. */}
          {trial?.is_trial && (
            <span className="ms-chip uw-sample-chip" title={TRIAL_DATA_NOTE}>
              {(trial.sample?.complaints ?? 0) > 0 ? "Sample data" : "Practice records"}
            </span>
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
            <AlertsBell onOpen={() => open("My Work")} />
            {/* The new navigation: Settings, Help, Team and Account at the top right (0.10.68). */}
            {topSections
              .filter((name) => name !== "My Account")
              .map((name) => {
                const { icon: Icon } = NAV[name];
                return (
                  <button
                    type="button"
                    key={name}
                    className={section === name ? "ac-secondary selected" : "ac-secondary"}
                    aria-current={section === name ? "page" : undefined}
                    onClick={() => open(name)}
                  >
                    <Icon size={16} aria-hidden="true" />{" "}
                    <span className="ac-hide-sm">{placeLabel(name, navigation)}</span>
                  </button>
                );
              })}
            <HelpMenu
              onGettingStarted={trial?.is_trial ? () => open("Getting started", "Your data") : undefined}
              more={
                fresh
                  ? [
                      ...(trial?.is_trial
                        ? [{ label: "Look ahead", detail: LOOK_AHEAD_SUBTITLE, onSelect: () => open("Look ahead") }]
                        : []),
                      {
                        label: "Share feedback",
                        detail: "Tell us what to improve",
                        onSelect: () => open("Share feedback"),
                      },
                    ]
                  : []
              }
            />
            {topSections.includes("My Account") && (
              <button
                type="button"
                className={section === "My Account" ? "ac-secondary selected" : "ac-secondary"}
                aria-current={section === "My Account" ? "page" : undefined}
                onClick={() => open("My Account")}
              >
                <UserRound size={16} aria-hidden="true" /> <span className="ac-hide-sm">Account</span>
              </button>
            )}
            <button type="button" className="ac-secondary" onClick={() => void signOut()} aria-label="Sign out">
              <LogOut size={16} /> <span className="ac-hide-sm">Sign out</span>
            </button>
          </div>
        </header>

        <div className="ac-body">
          <nav className={`ac-nav ${menuOpen ? "open" : ""}`} aria-label="Workspace navigation">
            <p className="ac-nav-label">Workspace</p>
            {menuSections.map((name) => {
              const { icon: Icon } = NAV[name];
              const { description } = navText(name, featureSet === "mvp", fresh);
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
                    <strong>{placeLabel(name, navigation)}</strong>
                    <small>{description}</small>
                  </span>
                </button>
              );
            })}
            <p className="ca-nav-scope">You see only {tenantName}'s data.</p>
          </nav>

          <main
            className="ac-main"
            id="app-main"
            tabIndex={-1}
            data-workspace-section={section}
            data-navigation={navigation}
          >
            {choosingStart ? (
              <p className="ac-empty" role="status">
                Opening your workspace…
              </p>
            ) : (
              <>
                {/* One complaint's page has its own header (sections/ComplaintPage.tsx). */}
                {section !== "Complaint" && (
                  <div className="ac-page-head">
                    <div>
                      <p className="ac-eyebrow">{tenantName}</p>
                      <h1 ref={heading} tabIndex={-1}>
                        {placeLabel(section, navigation)}
                      </h1>
                      <p>{navText(section, featureSet === "mvp", fresh).guide}</p>
                      <p className="ac-page-zone">Times are in {zoneName()}.</p>
                    </div>
                  </div>
                )}
                {NAV[section].context && (!fresh || section === "Investigations" || section === "Trends") && (
                  <ContextBar />
                )}
                {/* A colleague the owner invited is greeted by name on their first screens (UX-26). */}
                {trial?.is_trial && <ColleagueWelcome me={trial.me} />}
                {trial?.is_trial && section !== "Share feedback" && (
                  <FeedbackPrompt onOpen={() => open("Share feedback")} />
                )}
                {trial?.is_trial && <ChapterDone refreshKey={location.key} onOpen={openChapter} />}
                {message && (
                  <div className={`ac-message uw-notice tone-${message.tone}`} role="status">
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
                <ColumnScopeProvider key={location.key} scope={columnScopeFor(section)}>
                  <SectionErrorBoundary name={section} resetKey={location.key}>
                    <div className="ca-section">
                      {section === "Getting started" && <GettingStartedSection focus={tab} />}
                      {section === "Readiness" && <ReadinessSection tab={tab} />}
                      {section === "Dashboard" && <DashboardSection />}
                      {section === "My Work" && (fresh ? <NewMyWorkSection tab={tab} /> : <MyWorkSection tab={tab} />)}
                      {section === "Products" && <ProductsSection tab={tab} />}
                      {section === "Complaints" &&
                        (fresh ? <ComplaintViews tab={tab} /> : <ComplaintsSection tab={tab} />)}
                      {section === "Signals" && <SignalsSection tab={tab} />}
                      {section === "Investigations" && <InvestigationsSection tab={tab} />}
                      {section === "Evidence" && <EvidenceSection tab={tab} />}
                      {section === "Decisions" && <DecisionsSection tab={tab} />}
                      {section === "Records" &&
                        (fresh ? <NewRecordsSection tab={tab} /> : <RecordsSection tab={tab} />)}
                      {section === "Intelligence" && <IntelligenceSection tab={tab} />}
                      {section === "Trust & Audit" && <TrustSection tab={tab} />}
                      {section === "My Account" && <AccountSection tab={tab} />}
                      {section === "Import data" && <ImportDataSection focus={tab} />}
                      {section === "Share feedback" && <FeedbackSection isTrial={!!trial?.is_trial} />}
                      {section === "Look ahead" && trial?.is_trial && <LookAheadSection focus={tab} />}
                      {section === "Next steps" && trial?.is_trial && <TrialNextStepsSection />}
                      {section === "Trends" && <TrendsSection tab={tab} />}
                      {section === "Settings" && <SettingsSection tab={tab} />}
                      {section === "Team" && <TeamSection onAdminConsole={onAdminConsole} />}
                      {section === "Complaint" && <ComplaintPage tab={tab} heading={heading} />}
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
