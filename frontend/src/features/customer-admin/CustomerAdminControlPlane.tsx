import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SwitchOrganization } from "../shared/SwitchOrganization";
import { HelpMenu } from "../shared/HelpMenu";
import {
  Bell,
  Briefcase,
  Building2,
  Database,
  FileClock,
  FileSignature,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  Plug,
  ShieldCheck,
  Users,
  WalletCards,
  X,
} from "lucide-react";
import { signOut } from "../shared/session";
import { useFocusOnChange } from "../shared/focus";
import { SessionTimeoutWarning, useIdleSignOut } from "../shared/SessionTimeout";
import { SectionErrorBoundary } from "../../app/ErrorBoundary";
import { PARKED_CUSTOMER_ADMIN_SECTIONS, featureSetOf } from "../../app/featureSet";
import "../admin/console/admin-console.css";
import "./customer-admin.css";
import "../workspace/areaNav.css";
import { ConsoleContext, SECTIONS, type ConsoleApi, type Section, type TenantContext } from "./context";
import { ConfirmDialog, type Confirmation } from "./shared";
import { Dashboard } from "./sections/Dashboard";
import { SectionSummary } from "./sections/summaries";
import { ColumnScopeProvider } from "../tables/ColumnChooser";
import { UsersSection } from "./sections/Users";
import { AccessSection } from "./sections/Access";
import { IntegrationsSection } from "./sections/Integrations";
import { DataMappingSection } from "./sections/DataMapping";
import { SubscriptionSection } from "./sections/Subscription";
import { SecuritySection } from "./sections/Security";
import { NotificationsSection } from "./sections/Notifications";
import { AuditSection } from "./sections/Audit";
import { ReviewsSection } from "./sections/Reviews";
import { OrganizationSection } from "./sections/Organization";

// `description` is the short line in the side navigation; `purpose` is the one-line explanation under the page heading.
const NAV: Record<Section, { icon: typeof Users; description: string; purpose: string }> = {
  Dashboard: {
    icon: LayoutDashboard,
    description: "Live organization status",
    purpose: "What needs your attention today, and how your organization is using MDARIX.",
  },
  Users: {
    icon: Users,
    description: "People, invitations, access",
    purpose: "Invite people, choose what they can do, and suspend or remove access when they leave.",
  },
  "Roles & Access": {
    icon: KeyRound,
    description: "Roles, permission sets, approvals",
    purpose: "Build your own roles from permission sets, and decide who may approve decisions.",
  },
  Integrations: {
    icon: Plug,
    description: "Connections and syncs",
    purpose: "Connect the systems your records come from, and check that each sync arrived complete.",
  },
  "Data Mapping": {
    icon: Database,
    description: "Mappings and releases",
    purpose: "Decide how fields from your systems become MDARIX records. Every change is approved before use.",
  },
  "Plan & Subscription": {
    icon: WalletCards,
    description: "Plan, seats, renewal",
    purpose: "Your plan, how many seats are in use, and when your subscription renews.",
  },
  Security: {
    icon: ShieldCheck,
    description: "MFA, AI processing, events",
    purpose: "How sign-in is protected, whether AI may be used, and recent security events.",
  },
  Notifications: {
    icon: Bell,
    description: "Reminders and contacts",
    purpose: "Who is reminded before your subscription ends, and when.",
  },
  Audit: {
    icon: FileClock,
    description: "Audit trail and exports",
    purpose: "A permanent record of every administrative change, which you can search and download.",
  },
  Reviews: {
    icon: FileSignature,
    description: "Signed reviews",
    purpose: "The audit trail review, the access review and the configuration snapshot your organization signs.",
  },
  Organization: {
    icon: Building2,
    description: "Profile and products",
    purpose: "Your organization's details, your products, and a full copy of your data.",
  },
};

/** The sections this feature set offers (app/featureSet.ts): under mvp the connections and mapping are parked. */
export function customerAdminSections(featureSet: string | null | undefined): readonly Section[] {
  if (featureSetOf(featureSet) !== "mvp") return SECTIONS;
  return SECTIONS.filter((name) => !PARKED_CUSTOMER_ADMIN_SECTIONS.includes(name));
}

/**
 * The five groups of customer administration (UX2, Persona Blueprint wave D), in place of eleven areas side by side:
 * each group opens its first section, and a group with more than one section shows them in its own small menu. The
 * sections, their addresses and their server checks are unchanged.
 */
export const ADMIN_GROUPS: ReadonlyArray<{ label: string; icon: typeof Users; sections: readonly Section[] }> = [
  {
    label: "Organization",
    icon: Building2,
    sections: ["Dashboard", "Organization", "Plan & Subscription", "Notifications"],
  },
  { label: "People & access", icon: Users, sections: ["Users", "Roles & Access"] },
  { label: "Data & connections", icon: Plug, sections: ["Integrations", "Data Mapping"] },
  { label: "AI & security", icon: ShieldCheck, sections: ["Security"] },
  { label: "Audit", icon: FileClock, sections: ["Audit", "Reviews"] },
];

/** The groups this feature set offers, each with only its offered sections; an empty group is left out (under mvp,
 * Data & connections: its connections and mapping are parked). */
export const adminGroups = (offered: readonly Section[]) =>
  ADMIN_GROUPS.map((group) => ({ ...group, sections: group.sections.filter((name) => offered.includes(name)) })).filter(
    (group) => group.sections.length > 0,
  );

const groupOf = (section: Section) => ADMIN_GROUPS.find((group) => group.sections.includes(section));

/** The console's own idle sign-out; inside the workspace's shell the workspace runs its own. */
function ConsoleIdle() {
  const idle = useIdleSignOut();
  return <SessionTimeoutWarning session={idle} />;
}

export function CustomerAdminControlPlane({
  securityContext,
  onOpenWorkspace,
  embedded = false,
  initialSection,
  onSection,
}: {
  securityContext: TenantContext | null;
  products?: unknown[];
  investigations?: unknown[];
  onNavigate?: (view: any) => void;
  /** Switch into the investigation workspace with an Investigator's rights (same account, App.tsx decides). */
  onOpenWorkspace?: () => void;
  /** Inside the workspace's shell (UX2, Avatar › Administration): no header, side menu or idle timer of its own. */
  embedded?: boolean;
  /** The section the address names (embedded: /app/customer-admin?tab=Users). */
  initialSection?: string;
  /** Each section opened, for the workspace's address. */
  onSection?: (section: Section) => void;
}) {
  const featureSet = securityContext?.feature_set;
  const sections = useMemo(() => customerAdminSections(featureSet), [featureSet]);
  const [location, setLocation] = useState<{ section: Section; tab?: string; key: number }>(() => ({
    section: sections.includes(initialSection as Section) ? (initialSection as Section) : "Dashboard",
    key: 0,
  }));
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [message, setMessage] = useState<{ text: string; tone: "good" | "critical" } | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useFocusOnChange(heading, location.key);

  const open = useCallback(
    (section: Section, tab?: string) => {
      // A parked section (an old link, a dashboard tile) opens the dashboard instead.
      const offered = sections.includes(section);
      setLocation((current) => ({
        section: offered ? section : "Dashboard",
        tab: offered ? tab : undefined,
        key: current.key + 1,
      }));
      setMenuOpen(false);
      setMessage(null);
      window.scrollTo({ top: 0 });
    },
    [sections],
  );
  const notify = useCallback((text: string, tone: "good" | "critical" = "good") => setMessage({ text, tone }), []);
  useEffect(() => onSection?.(location.section), [location.section]);

  // The workspace side navigation (App.tsx) can still request a section by name.
  useEffect(() => {
    const handler = (event: Event) => {
      // "Overview" is the former name of the Dashboard.
      const requested = String((event as CustomEvent).detail).replace(/^Overview$/, "Dashboard");
      if ((SECTIONS as readonly string[]).includes(requested)) open(requested as Section);
    };
    window.addEventListener("customer-admin-section", handler);
    return () => window.removeEventListener("customer-admin-section", handler);
  }, [open]);

  const api: ConsoleApi = { context: securityContext, open, confirm: setConfirmation, notify };
  const tenantName = securityContext?.current_tenant?.tenant_name ?? "Your organization";
  const { section, tab } = location;
  const groups = adminGroups(sections);
  const group = groupOf(section);
  const within = groups.find((item) => item.label === group?.label)?.sections ?? [];
  const Body = embedded ? "div" : "main";

  const groupMenu = (
    <>
      {groups.map(({ label, icon: Icon, sections: inGroup }) => (
        <button
          type="button"
          key={label}
          className={group?.label === label ? "selected" : ""}
          aria-current={group?.label === label ? "page" : undefined}
          onClick={() => open(inGroup[0])}
        >
          <Icon size={18} aria-hidden="true" />
          <span>
            <strong>{label}</strong>
            {!embedded && <small>{inGroup.join(", ")}</small>}
          </span>
        </button>
      ))}
    </>
  );

  return (
    <ConsoleContext.Provider value={api}>
      <div className={`admin-console customer-admin-console${embedded ? " is-embedded" : ""}`}>
        {!embedded && (
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
              MDARIX <span>Customer administration · {tenantName}</span>
            </div>
            <div className="ac-user">
              <span>
                <strong>{securityContext?.display_name ?? "Customer Administrator"}</strong>
                <small>Customer Administrator</small>
              </span>
              {onOpenWorkspace && (
                <button
                  type="button"
                  className="ac-secondary"
                  onClick={onOpenWorkspace}
                  aria-label="Open workspace"
                  title="Work on investigations with an Investigator's rights"
                >
                  <Briefcase size={16} aria-hidden="true" /> <span className="ac-hide-sm">Open workspace</span>
                </button>
              )}
              <SwitchOrganization />
              <HelpMenu />
              <button type="button" className="ac-secondary" onClick={() => void signOut()} aria-label="Sign out">
                <LogOut size={16} /> <span className="ac-hide-sm">Sign out</span>
              </button>
            </div>
          </header>
        )}

        <div className="ac-body">
          {!embedded && (
            <nav className={`ac-nav ${menuOpen ? "open" : ""}`} aria-label="Customer administration navigation">
              <p className="ac-nav-label">{tenantName}</p>
              {groupMenu}
              <p className="ca-nav-scope">
                Everything here belongs to {tenantName} only. No other organization can see it.
              </p>
            </nav>
          )}

          <Body
            className="ac-main"
            id={embedded ? undefined : "app-main"}
            tabIndex={embedded ? undefined : -1}
            data-customer-admin-section={section}
          >
            {embedded && (
              <nav className="uw-areanav ca-groups" aria-label="Administration areas">
                {groupMenu}
              </nav>
            )}
            {within.length > 1 && (
              <nav className="uw-areanav" aria-label={`${group?.label ?? "Administration"} pages`}>
                {within.map((name) => (
                  <button
                    type="button"
                    key={name}
                    aria-current={section === name ? "page" : undefined}
                    onClick={() => open(name)}
                  >
                    {name}
                  </button>
                ))}
              </nav>
            )}
            <div className="ac-page-head">
              <div>
                <p className="ac-eyebrow">{embedded ? group?.label : "Customer administration"}</p>
                {embedded ? (
                  <h2 ref={heading} tabIndex={-1}>
                    {section}
                  </h2>
                ) : (
                  <h1 ref={heading} tabIndex={-1}>
                    {section}
                  </h1>
                )}
                <p>{NAV[section].purpose}</p>
              </div>
            </div>
            {message && (
              <div className={`ac-message tone-${message.tone}`} role="status">
                {message.text}
                <button type="button" className="ac-link" onClick={() => setMessage(null)} aria-label="Dismiss message">
                  <X size={14} />
                </button>
              </div>
            )}
            {/* Every list on a page offers the field chooser; each page remembers its own choice of columns. */}
            <ColumnScopeProvider key={location.key} scope={`customer-admin:${section}`}>
              <SectionErrorBoundary name={section} resetKey={location.key}>
                <div className="ca-section">
                  <SectionSummary section={section} />
                  {section === "Dashboard" && <Dashboard />}
                  {section === "Users" && <UsersSection tab={tab} />}
                  {section === "Roles & Access" && <AccessSection tab={tab} />}
                  {section === "Integrations" && <IntegrationsSection tab={tab} />}
                  {section === "Data Mapping" && <DataMappingSection tab={tab} />}
                  {section === "Plan & Subscription" && <SubscriptionSection />}
                  {section === "Security" && <SecuritySection tab={tab} />}
                  {section === "Notifications" && <NotificationsSection />}
                  {section === "Audit" && <AuditSection />}
                  {section === "Reviews" && <ReviewsSection />}
                  {section === "Organization" && <OrganizationSection />}
                </div>
              </SectionErrorBoundary>
            </ColumnScopeProvider>
          </Body>
        </div>

        {!embedded && <ConsoleIdle />}
        <ConfirmDialog
          request={confirmation}
          onClose={() => setConfirmation(null)}
          onDone={(text) => {
            setConfirmation(null);
            notify(text);
          }}
        />
      </div>
    </ConsoleContext.Provider>
  );
}
