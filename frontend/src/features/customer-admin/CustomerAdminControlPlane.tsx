import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SwitchOrganization } from "../shared/SwitchOrganization";
import { HelpMenu } from "../shared/HelpMenu";
import {
  Bell,
  Briefcase,
  Building2,
  Database,
  FileClock,
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

export function CustomerAdminControlPlane({
  securityContext,
  onOpenWorkspace,
}: {
  securityContext: TenantContext | null;
  products?: unknown[];
  investigations?: unknown[];
  onNavigate?: (view: any) => void;
  /** Switch into the investigation workspace with an Investigator's rights (same account, App.tsx decides). */
  onOpenWorkspace?: () => void;
}) {
  const [location, setLocation] = useState<{ section: Section; tab?: string; key: number }>({
    section: "Dashboard",
    key: 0,
  });
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [message, setMessage] = useState<{ text: string; tone: "good" | "critical" } | null>(null);
  const idle = useIdleSignOut();
  const heading = useRef<HTMLHeadingElement>(null);
  useFocusOnChange(heading, location.key);

  const featureSet = securityContext?.feature_set;
  const sections = useMemo(() => customerAdminSections(featureSet), [featureSet]);
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

  return (
    <ConsoleContext.Provider value={api}>
      <div className="admin-console customer-admin-console">
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
          <nav className={`ac-nav ${menuOpen ? "open" : ""}`} aria-label="Customer administration navigation">
            <p className="ac-nav-label">{tenantName}</p>
            {sections.map((name) => {
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
              Everything here belongs to {tenantName} only. No other organization can see it.
            </p>
          </nav>

          <main className="ac-main" id="app-main" tabIndex={-1} data-customer-admin-section={section}>
            <div className="ac-page-head">
              <div>
                <p className="ac-eyebrow">Customer administration</p>
                <h1 ref={heading} tabIndex={-1}>
                  {section}
                </h1>
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
                  {section === "Organization" && <OrganizationSection />}
                </div>
              </SectionErrorBoundary>
            </ColumnScopeProvider>
          </main>
        </div>

        <SessionTimeoutWarning session={idle} />
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
