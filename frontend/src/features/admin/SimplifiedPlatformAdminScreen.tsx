import { Fragment, useCallback, useMemo, useState } from "react";
import { PARKED_ADMIN_FALLBACK, adminAreasFor, featureSetOf, websiteDemoRequestsOffered } from "../../app/featureSet";
import { SwitchOrganization } from "../shared/SwitchOrganization";
import { HelpMenu } from "../shared/HelpMenu";
import { LayoutDashboard, LogOut, Menu, RefreshCw, Search, X } from "lucide-react";
import { requestJson } from "../../app/apiClient";
import { DOMAINS } from "./consoleDomains";
import { AdminArea, isAreaDomain } from "./areas/AdminArea";
import { SectionErrorBoundary } from "../../app/ErrorBoundary";
import { nextTabIndex } from "../shared/focus";
import {
  DATA_INTEGRATION_STAGES,
  DOMAIN_ALIASES,
  LEGACY_SECTIONS,
  TRIAL_ORGANIZATIONS,
  dataIntegrationStep,
  movedTarget,
  sectionMatches,
  sectionGuide,
} from "./areas/sections";
import { AdminOverview, type OverviewTarget } from "./console/AdminOverview";
import { CustomersAndTenants } from "./customers/CustomersAndTenants";
import { SECTIONS as CUSTOMER_TENANT_SECTIONS, type Section as CustomerTenantSection } from "./customers/model";
import { TrialOrganizations, type TrialSection } from "./trials/TrialOrganizations";
import { trialAiPanel } from "./trials/TrialAiPanel";
import "./console/admin-console.css";

type Props = {
  securityContext: { display_name: string; active_role: string | null; feature_set?: string } | null;
  initialSection?: string;
};

type Location = { domain: string; item: string };

// The landing page (formerly "Overview"); any unknown or old target opens it.
const OVERVIEW = "Dashboard";
const CUSTOMERS_AND_TENANTS = "Customers & Tenants";
/** The initial section that opens the new-customer wizard (App.tsx, the former create-customer screen). */
const NEW_CUSTOMER = "New customer";
// "Platform Overview" is replaced by the dashboard below; every other domain keeps its real workspaces.
const ALL_AREAS = DOMAINS.filter((domain) => domain[0] !== "Platform Overview");
type Area = (typeof ALL_AREAS)[number];

/** Where a target opens among the areas this feature set offers (a parked area opens the dashboard). */
function locationFor(target: OverviewTarget | string, SECTIONS: readonly Area[]): Location {
  // A string is a domain, or "Domain:Section" for a deep link.
  const [askedDomain, askedItem] =
    typeof target === "string" ? (target.split(":", 2) as [string, string | undefined]) : [target.domain, target.item];
  // Sections that moved to another area (free trials, their requests and feedback: Trial organizations).
  const { domain: requestedDomain, item: deepItem } = movedTarget(askedDomain, askedItem);
  // Former area names (Data & Configuration, Integrations) open the area that replaced them.
  const domainName = DOMAIN_ALIASES[requestedDomain] ?? requestedDomain;
  const domain = SECTIONS.find((entry) => entry[0] === domainName);
  if (!domain) return { domain: OVERVIEW, item: OVERVIEW };
  const items = domain[3] as readonly string[];
  // Old section names (bookmarks, links from other screens) land on the section that replaced them.
  // A section the MVP parks opens the one that replaces it (renewals: subscriptions), else the area's first.
  const requested =
    deepItem && !items.includes(deepItem) ? (LEGACY_SECTIONS[deepItem] ?? PARKED_ADMIN_FALLBACK[deepItem]) : deepItem;
  return { domain: domain[0], item: requested && items.includes(requested) ? requested : items[0] };
}

export function SimplifiedPlatformAdminScreen({ securityContext, initialSection = OVERVIEW }: Props) {
  // Under the MVP feature set some areas and sections are parked (app/featureSet.ts adminAreasFor).
  const featureSet = featureSetOf(securityContext?.feature_set);
  const SECTIONS = useMemo(() => adminAreasFor(ALL_AREAS, featureSet), [featureSet]);
  // Website demo requests, only where the website offers them and the server serves their route.
  const websiteDemos = websiteDemoRequestsOffered(featureSet);
  const [location, setLocation] = useState<Location>(() =>
    initialSection === NEW_CUSTOMER
      ? locationFor({ domain: CUSTOMERS_AND_TENANTS, item: "Customers" }, SECTIONS)
      : (CUSTOMER_TENANT_SECTIONS as readonly string[]).includes(initialSection)
        ? locationFor({ domain: CUSTOMERS_AND_TENANTS, item: initialSection }, SECTIONS)
        : locationFor(initialSection, SECTIONS),
  );
  // "New customer" (the dashboard button, or the former create-customer screen) opens the wizard on Customers.
  const [createCustomer, setCreateCustomer] = useState(initialSection === NEW_CUSTOMER);
  const creatingStarted = useCallback(() => setCreateCustomer(false), []);
  const [refreshKey, setRefreshKey] = useState(0);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [query, setQuery] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [message, setMessage] = useState<{ tone: "good" | "critical"; text: string } | null>(null);

  const searchResults = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return [];
    return SECTIONS.flatMap((domain) =>
      (domain[3] as readonly string[]).map((item) => ({ domain: domain[0], description: domain[1], item })),
    )
      .filter(({ domain, description, item }) => sectionMatches(term, domain, description, item))
      .slice(0, 8);
  }, [query, SECTIONS]);

  const open = (target: OverviewTarget | string) => {
    setLocation(locationFor(target, SECTIONS));
    setMenuOpen(false);
    setQuery("");
    setMessage(null);
  };
  const activeDomain = SECTIONS.find((domain) => domain[0] === location.domain);

  const signOut = async () => {
    await requestJson("/api/v1/auth/signout", { method: "POST", retries: 0 }).catch(() => undefined);
    window.location.replace("/signin");
  };

  return (
    <div className="admin-console">
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
          MDARIX <span>Platform administration</span>
        </div>
        <div className="ac-search">
          <label>
            <Search size={16} aria-hidden="true" />
            <input
              aria-label="Search administration sections"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search sections, e.g. subscriptions, MFA, mapping"
            />
          </label>
          {query.trim() && (
            <div className="ac-search-results" role="listbox" aria-label="Matching sections">
              {searchResults.length ? (
                searchResults.map((result) => (
                  <button
                    type="button"
                    role="option"
                    aria-selected={false}
                    key={`${result.domain}-${result.item}`}
                    onClick={() => open(result)}
                  >
                    <strong>{result.item}</strong>
                    <small>{result.domain}</small>
                  </button>
                ))
              ) : (
                <p className="ac-muted">No matching section.</p>
              )}
            </div>
          )}
        </div>
        <div className="ac-user">
          <span>
            <strong>{securityContext?.display_name ?? "Administrator"}</strong>
            <small>{securityContext?.active_role ?? "Platform Administrator"}</small>
          </span>
          <SwitchOrganization />
          <HelpMenu />
          <button type="button" className="ac-secondary" onClick={signOut} aria-label="Sign out">
            <LogOut size={16} /> <span className="ac-hide-sm">Sign out</span>
          </button>
        </div>
      </header>

      <div className="ac-body">
        <nav className={`ac-nav ${menuOpen ? "open" : ""}`} aria-label="Administrator navigation">
          <p className="ac-nav-label">Platform administration</p>
          <button
            type="button"
            className={location.domain === OVERVIEW ? "selected" : ""}
            aria-current={location.domain === OVERVIEW ? "page" : undefined}
            onClick={() => open(OVERVIEW)}
          >
            <LayoutDashboard size={18} aria-hidden="true" />
            <span>
              <strong>Dashboard</strong>
              <small>Live platform status</small>
            </span>
          </button>
          {SECTIONS.map(([label, description, Icon]) => (
            <button
              type="button"
              key={label}
              className={location.domain === label ? "selected" : ""}
              aria-current={location.domain === label ? "page" : undefined}
              onClick={() => open(label)}
            >
              <Icon size={18} aria-hidden="true" />
              <span>
                <strong>{label}</strong>
                <small>{description}</small>
              </span>
            </button>
          ))}
        </nav>

        <main
          className="ac-main"
          id="app-main"
          tabIndex={-1}
          data-admin-section={`${location.domain}:${location.item}`}
        >
          {message && (
            <div className={`ac-message tone-${message.tone}`} role="status">
              {message.text}
              <button type="button" className="ac-link" onClick={() => setMessage(null)} aria-label="Dismiss message">
                <X size={14} />
              </button>
            </div>
          )}

          {location.domain === OVERVIEW ? (
            <>
              <div className="ac-page-head">
                <div>
                  <p className="ac-eyebrow">Platform administration</p>
                  <h1>Dashboard</h1>
                  <p>Live status across customers, subscriptions, integrations, security and operations.</p>
                </div>
                <div className="ac-page-actions">
                  <span className="ac-muted">
                    {updatedAt
                      ? `Updated ${updatedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
                      : "Loading"}
                  </span>
                  <button type="button" className="ac-secondary" onClick={() => setRefreshKey((value) => value + 1)}>
                    <RefreshCw size={16} /> Refresh
                  </button>
                </div>
              </div>
              <SectionErrorBoundary name="The dashboard" resetKey={refreshKey}>
                <AdminOverview
                  refreshKey={refreshKey}
                  onOpen={open}
                  onCreateCustomer={() => {
                    setCreateCustomer(true);
                    open({ domain: CUSTOMERS_AND_TENANTS, item: "Customers" });
                  }}
                  onUpdated={setUpdatedAt}
                  integrations={SECTIONS.some((area) => area[0] === "Data & Integrations")}
                />
              </SectionErrorBoundary>
              <section className="ac-areas" aria-label="Administration areas">
                <h2>Administration areas</h2>
                <div>
                  {SECTIONS.map(([label, description, Icon]) => (
                    <button type="button" key={label} onClick={() => open(label)}>
                      <Icon size={20} aria-hidden="true" />
                      <strong>{label}</strong>
                      <small>{description}</small>
                    </button>
                  ))}
                </div>
              </section>
            </>
          ) : (
            activeDomain && (
              <>
                <div className="ac-page-head">
                  <div>
                    <p className="ac-eyebrow">Platform administration · {activeDomain[1]}</p>
                    <h1>{activeDomain[0]}</h1>
                    {/* One line on what the open section is for (Data & Integrations has its own step guide). */}
                    {sectionGuide(activeDomain[0], location.item, websiteDemos) && (
                      <p className="ac-muted">{sectionGuide(activeDomain[0], location.item, websiteDemos)}</p>
                    )}
                  </div>
                </div>
                <div
                  className="ac-tabs"
                  role="tablist"
                  aria-label={`${activeDomain[0]} sections`}
                  onKeyDown={(event) => {
                    // Arrow keys, Home and End move between the sections (WAI-ARIA tabs pattern).
                    const items = activeDomain[3] as readonly string[];
                    const next = nextTabIndex(event.key, Math.max(0, items.indexOf(location.item)), items.length);
                    if (next === null) return;
                    event.preventDefault();
                    setLocation({ domain: activeDomain[0], item: items[next] });
                    const buttons = event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]');
                    buttons[next]?.focus();
                  }}
                >
                  {(() => {
                    const tab = (item: string) => {
                      const step = dataIntegrationStep(item);
                      return (
                        <button
                          type="button"
                          role="tab"
                          key={item}
                          tabIndex={location.item === item ? 0 : -1}
                          aria-selected={location.item === item}
                          className={location.item === item ? "selected" : ""}
                          onClick={() => setLocation({ domain: activeDomain[0], item })}
                        >
                          {step && (
                            <span className="ac-tab-step" aria-hidden="true">
                              {step.number}
                            </span>
                          )}
                          {item}
                        </button>
                      );
                    };
                    const items = activeDomain[3] as readonly string[];
                    // Data & Integrations is a sequence: each stage keeps its name and its numbered steps together.
                    if (!items.every((item) => dataIntegrationStep(item)))
                      return items.map((item) => <Fragment key={item}>{tab(item)}</Fragment>);
                    return DATA_INTEGRATION_STAGES.map((stage) => (
                      <span className="ac-tab-group" key={stage.stage}>
                        <span className="ac-tab-stage" aria-hidden="true">
                          {stage.stage}
                        </span>
                        {stage.sections.map((item) => tab(item))}
                      </span>
                    ));
                  })()}
                </div>
                <div className="ac-workspace" role="tabpanel" aria-label={location.item}>
                  <SectionErrorBoundary
                    name={`${activeDomain[0]} · ${location.item}`}
                    resetKey={`${location.domain}:${location.item}`}
                  >
                    {location.domain === CUSTOMERS_AND_TENANTS ? (
                      <CustomersAndTenants
                        section={location.item as CustomerTenantSection}
                        onSection={(item) => setLocation({ domain: CUSTOMERS_AND_TENANTS, item })}
                        startCreating={createCustomer}
                        onCreatingStarted={creatingStarted}
                      />
                    ) : location.domain === TRIAL_ORGANIZATIONS ? (
                      <TrialOrganizations
                        section={location.item as TrialSection}
                        onSection={(item) => setLocation({ domain: TRIAL_ORGANIZATIONS, item })}
                        websiteDemos={websiteDemos}
                        trialAiPanel={trialAiPanel}
                        onOpenCustomers={() => open({ domain: CUSTOMERS_AND_TENANTS, item: "Customers" })}
                      />
                    ) : isAreaDomain(location.domain) ? (
                      <AdminArea
                        key={`${location.domain}:${location.item}`}
                        domain={location.domain}
                        section={location.item}
                        onSection={(item) => setLocation({ domain: location.domain, item })}
                      />
                    ) : null}
                  </SectionErrorBoundary>
                </div>
              </>
            )
          )}
        </main>
      </div>
    </div>
  );
}
