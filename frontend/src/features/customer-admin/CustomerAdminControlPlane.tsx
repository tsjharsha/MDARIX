import { useCallback, useEffect, useRef, useState } from "react";
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

const NAV: Record<Section, { icon: typeof Users; description: string }> = {
  Dashboard: { icon: LayoutDashboard, description: "Live organization status" },
  Users: { icon: Users, description: "People, invitations, access" },
  "Roles & Access": { icon: KeyRound, description: "Roles, permission sets, approvals" },
  Integrations: { icon: Plug, description: "Connections and syncs" },
  "Data Mapping": { icon: Database, description: "Mappings and releases" },
  "Plan & Subscription": { icon: WalletCards, description: "Plan, seats, renewal" },
  Security: { icon: ShieldCheck, description: "MFA, AI processing, events" },
  Notifications: { icon: Bell, description: "Reminders and contacts" },
  Audit: { icon: FileClock, description: "Audit trail and exports" },
  Organization: { icon: Building2, description: "Profile and products" },
};

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

  const open = useCallback((section: Section, tab?: string) => {
    setLocation((current) => ({ section, tab, key: current.key + 1 }));
    setMenuOpen(false);
    setMessage(null);
    window.scrollTo({ top: 0 });
  }, []);
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
            {SECTIONS.map((name) => {
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
              Every page shows only {tenantName}. Your organization is set by your sign-in, never by the browser.
            </p>
          </nav>

          <main className="ac-main" id="app-main" tabIndex={-1} data-customer-admin-section={section}>
            <div className="ac-page-head">
              <div>
                <p className="ac-eyebrow">Customer administration</p>
                <h1 ref={heading} tabIndex={-1}>
                  {section}
                </h1>
                <p>{NAV[section].description}</p>
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
