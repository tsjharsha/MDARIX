import { useMemo, useState } from "react";
import { LayoutDashboard, LogOut, Menu, RefreshCw, Search, X } from "lucide-react";
import { requestJson } from "../../app/apiClient";
import { DOMAINS, PlatformAdminScreen } from "./PlatformAdminScreen";
import { AdminArea, isAreaDomain } from "./areas/AdminArea";
import { LEGACY_SECTIONS } from "./areas/sections";
import { AdminOverview, type OverviewTarget } from "./console/AdminOverview";
import { CustomersAndTenants } from "./customers/CustomersAndTenants";
import { SECTIONS as CUSTOMER_TENANT_SECTIONS, type Section as CustomerTenantSection } from "./customers/model";
import "./console/admin-console.css";

type Props = {
  securityContext: { display_name: string; active_role: string | null } | null;
  onNavigate: (view: any) => void;
  initialSection?: string;
};

type Location = { domain: string; item: string };

const OVERVIEW = "Overview";
const CUSTOMERS_AND_TENANTS = "Customers & Tenants";
// "Platform Overview" is replaced by the dashboard below; every other domain keeps its real workspaces.
const SECTIONS = DOMAINS.filter((domain) => domain[0] !== "Platform Overview");

function locationFor(target: OverviewTarget | string): Location {
  // A string is a domain, or "Domain:Section" for a deep link.
  const [domainName, deepItem] =
    typeof target === "string" ? (target.split(":", 2) as [string, string | undefined]) : [target.domain, target.item];
  const domain = SECTIONS.find((entry) => entry[0] === domainName);
  if (!domain) return { domain: OVERVIEW, item: OVERVIEW };
  const items = domain[3] as readonly string[];
  // Old section names (bookmarks, links from other screens) land on the section that replaced them.
  const requested = deepItem && !items.includes(deepItem) ? LEGACY_SECTIONS[deepItem] : deepItem;
  return { domain: domain[0], item: requested && items.includes(requested) ? requested : items[0] };
}

export function SimplifiedPlatformAdminScreen({ securityContext, onNavigate, initialSection = OVERVIEW }: Props) {
  const [location, setLocation] = useState<Location>(() =>
    (CUSTOMER_TENANT_SECTIONS as readonly string[]).includes(initialSection)
      ? locationFor({ domain: CUSTOMERS_AND_TENANTS, item: initialSection })
      : locationFor(initialSection),
  );
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
      .filter(({ domain, description, item }) => `${domain} ${description} ${item}`.toLowerCase().includes(term))
      .slice(0, 8);
  }, [query]);

  const open = (target: OverviewTarget | string) => {
    setLocation(locationFor(target));
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
          MDARIX <span>Administrator control plane</span>
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
          <button type="button" className="ac-secondary" onClick={signOut} aria-label="Sign out of MDARIX">
            <LogOut size={16} /> <span className="ac-hide-sm">Logout</span>
          </button>
        </div>
      </header>

      <div className="ac-body">
        <nav className={`ac-nav ${menuOpen ? "open" : ""}`} aria-label="Administrator navigation">
          <p className="ac-nav-label">Administrator control plane</p>
          <button
            type="button"
            className={location.domain === OVERVIEW ? "selected" : ""}
            aria-current={location.domain === OVERVIEW ? "page" : undefined}
            onClick={() => open(OVERVIEW)}
          >
            <LayoutDashboard size={18} aria-hidden="true" />
            <span>
              <strong>Overview</strong>
              <small>Status dashboard</small>
            </span>
          </button>
          {SECTIONS.map(([label, description, Icon, items]) => (
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
                <small>
                  {description} · {items.length}
                </small>
              </span>
            </button>
          ))}
        </nav>

        <main className="ac-main" data-admin-section={`${location.domain}:${location.item}`}>
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
                  <p className="ac-eyebrow">Administrator control plane</p>
                  <h1>Platform overview</h1>
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
              <AdminOverview
                refreshKey={refreshKey}
                onOpen={open}
                onCreateCustomer={() => open({ domain: CUSTOMERS_AND_TENANTS, item: "Onboarding" })}
                onUpdated={setUpdatedAt}
              />
              <section className="ac-areas" aria-label="Administration areas">
                <h2>Administration areas</h2>
                <div>
                  {SECTIONS.map(([label, description, Icon, items]) => (
                    <button type="button" key={label} onClick={() => open(label)}>
                      <Icon size={20} aria-hidden="true" />
                      <strong>{label}</strong>
                      <small>{description}</small>
                      <em>{items.length} sections</em>
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
                    <p className="ac-eyebrow">Administrator control plane · {activeDomain[1]}</p>
                    <h1>{activeDomain[0]}</h1>
                  </div>
                </div>
                <div className="ac-tabs" role="tablist" aria-label={`${activeDomain[0]} sections`}>
                  {(activeDomain[3] as readonly string[]).map((item) => (
                    <button
                      type="button"
                      role="tab"
                      key={item}
                      aria-selected={location.item === item}
                      className={location.item === item ? "selected" : ""}
                      onClick={() => setLocation({ domain: activeDomain[0], item })}
                    >
                      {item}
                    </button>
                  ))}
                </div>
                <div className="ac-workspace" role="tabpanel" aria-label={location.item}>
                  {location.domain === CUSTOMERS_AND_TENANTS ? (
                    <CustomersAndTenants
                      section={location.item as CustomerTenantSection}
                      onSection={(item) => setLocation({ domain: CUSTOMERS_AND_TENANTS, item })}
                    />
                  ) : isAreaDomain(location.domain) ? (
                    <AdminArea
                      key={`${location.domain}:${location.item}`}
                      domain={location.domain}
                      section={location.item}
                    />
                  ) : (
                    <PlatformAdminScreen
                      embedded
                      securityContext={securityContext}
                      onNavigate={onNavigate}
                      initialDomain={location.domain}
                      initialItem={location.item}
                      onLocationChange={(domain, item) => {
                        if (domain === "Platform Overview") open(OVERVIEW);
                        else if (domain !== location.domain || item !== location.item) setLocation({ domain, item });
                      }}
                    />
                  )}
                </div>
              </>
            )
          )}
        </main>
      </div>
    </div>
  );
}
