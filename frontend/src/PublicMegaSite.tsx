import { useEffect, useState } from "react";
import { ArrowRight, ChevronDown, Menu, X } from "lucide-react";
import "./site/site.css";
import { lifecycleStages, platformGroups, solutionGroups, FUTURE_LIFECYCLE } from "./site/content";
import {
  CompanyPage,
  HomePage,
  LifecyclePage,
  PlatformPage,
  ResourcesPage,
  SITE_PAGES,
  SolutionsPage,
  TrustPage,
  type SitePage,
} from "./site/pages";

// The website was consolidated from ~65 URLs into 8 pages. Every old URL lands on the section that now holds its
// content, so existing links and bookmarks keep working.
const LEGACY_PAGES: Record<string, string> = {
  "/why-mdarix": "/trust#principles",
  "/ai-trust": "/trust#ai",
  "/security": "/trust#security",
  "/integrations": "/trust#integrations",
  // Pricing was removed until plans and billing are offered; its links go to Get started.
  "/pricing": "/company#contact",
  "/plans": "/company#contact",
  "/capabilities": "/platform",
  "/roadmap": "/product-lifecycle#roadmap",
  "/request-demo": "/company#contact",
};
const LIFECYCLE_SLUGS = new Set(lifecycleStages.flatMap((stage) => stage.items.map((item) => item.slug)));
const PLATFORM_SLUGS = new Set(
  platformGroups.flatMap((group) => group.capabilities.map((capability) => capability.slug)),
);

export function resolveSitePath(path: string, hash: string): { page: SitePage; hash: string } {
  const clean = path.replace(/\/+$/, "") || "/";
  if ((SITE_PAGES as readonly string[]).includes(clean)) return { page: clean as SitePage, hash };
  if (clean.startsWith("/platform/")) {
    const slug = clean.slice("/platform/".length);
    if (PLATFORM_SLUGS.has(slug)) return { page: "/platform", hash: slug };
    if (LIFECYCLE_SLUGS.has(slug) || FUTURE_LIFECYCLE.has(slug)) return { page: "/product-lifecycle", hash: slug };
    return { page: "/platform", hash: "" };
  }
  const legacy = LEGACY_PAGES[clean];
  if (legacy) {
    const [page, anchor] = legacy.split("#");
    // A legacy page's own anchor (e.g. /why-mdarix#not-qms or /roadmap#capa) wins over the default section.
    return { page: page as SitePage, hash: hash || anchor || "" };
  }
  return { page: "/", hash: "" };
}

type NavMenu = {
  name: string;
  title: string;
  href: string;
  groups: { title: string; links: { label: string; href: string; note?: string }[] }[];
};

const NAV_MENUS: NavMenu[] = [
  {
    name: "Platform",
    title: "Platform & AI",
    href: "/platform",
    groups: platformGroups.map((group) => ({
      title: group.title,
      links: group.capabilities.map((capability) => ({
        label: capability.label,
        href: `/platform#${capability.slug}`,
      })),
    })),
  },
  {
    name: "Solutions",
    title: "Solutions",
    href: "/solutions",
    groups: solutionGroups.map((group) => ({
      title: group.title,
      links: group.items.map((item) => ({ label: item.label, href: `/solutions#${item.key}` })),
    })),
  },
  {
    name: "Product Lifecycle",
    title: "Product Lifecycle",
    href: "/product-lifecycle",
    groups: lifecycleStages.map((stage) => ({
      title: stage.title,
      links: stage.items.map((item) => ({
        label: item.label,
        href: item.href ?? `/product-lifecycle#${item.slug}`,
        note: item.future ? "Future" : undefined,
      })),
    })),
  },
  {
    name: "Trust",
    title: "Trust",
    href: "/trust",
    groups: [
      {
        title: "Why MDARIX",
        links: [
          { label: "Not another QMS", href: "/trust#not-qms" },
          { label: "Evidence before inference", href: "/trust#evidence" },
          { label: "Humans decide", href: "/trust#humans-decide" },
        ],
      },
      {
        title: "Trust foundations",
        links: [
          { label: "AI trust & assurance", href: "/trust#ai" },
          { label: "Security & access", href: "/trust#security" },
          { label: "Integration approach", href: "/trust#integrations" },
        ],
      },
    ],
  },
];

const FOOTER: Array<{ title: string; links: [string, string][] }> = [
  {
    title: "Platform",
    links: [
      ["Product 360", "/platform#product-360"],
      ["Investigation intelligence", "/platform#investigation-intelligence"],
      ["Decision intelligence", "/platform#decision-intelligence"],
      ["Trust & governance", "/platform#trust-governance"],
    ],
  },
  {
    title: "Solutions",
    links: [
      ["By challenge", "/solutions#challenges"],
      ["By role", "/solutions#roles"],
      ["By investigation", "/solutions#investigations"],
      ["Product lifecycle", "/product-lifecycle"],
    ],
  },
  {
    title: "Trust",
    links: [
      ["Why MDARIX", "/trust#principles"],
      ["AI trust", "/trust#ai"],
      ["Security & access", "/trust#security"],
      ["Integrations", "/trust#integrations"],
    ],
  },
  {
    title: "Company",
    links: [
      ["About MDARIX", "/company"],
      ["Resources", "/resources"],
      ["Request a demo", "/company#contact"],
    ],
  },
];

export function PublicMegaSite({ path }: { path: string }) {
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [{ page, hash }, setLocation] = useState(() => resolveSitePath(path, window.location.hash.slice(1)));

  // Normalize legacy URLs in the address bar, then bring the requested section into view.
  useEffect(() => {
    const target = `${page}${hash ? `#${hash}` : ""}`;
    if (`${window.location.pathname}${window.location.hash}` !== target) window.history.replaceState(null, "", target);
    document.title = page === "/" ? "MDARIX · Product investigation intelligence" : `MDARIX · ${pageTitle(page)}`;
    if (hash) window.setTimeout(() => document.getElementById(hash)?.scrollIntoView({ block: "start" }), 60);
    else window.scrollTo({ top: 0 });
  }, [page, hash]);

  useEffect(() => {
    const update = () => setLocation(resolveSitePath(window.location.pathname, window.location.hash.slice(1)));
    window.addEventListener("hashchange", update);
    window.addEventListener("popstate", update);
    return () => {
      window.removeEventListener("hashchange", update);
      window.removeEventListener("popstate", update);
    };
  }, []);

  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenMenu(null);
        setMobileOpen(false);
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);

  const closeMenus = () => {
    setOpenMenu(null);
    setMobileOpen(false);
  };
  const activeMenu = NAV_MENUS.find((menu) => menu.name === openMenu);

  return (
    <div className="mdx-site" onClick={() => openMenu && setOpenMenu(null)}>
      <a className="ms-skip" href="#main">
        Skip to content
      </a>
      <header className="ms-header" onClick={(event) => event.stopPropagation()}>
        <a className="ms-brand" href="/" aria-label="MDARIX home">
          <span className="ms-logo" aria-hidden="true">
            M
          </span>
          MDARIX<small>Product intelligence</small>
        </a>
        <button
          className="ms-menu-button"
          aria-expanded={mobileOpen}
          aria-controls="public-navigation"
          aria-label={mobileOpen ? "Close menu" : "Open menu"}
          onClick={() => setMobileOpen(!mobileOpen)}
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
        <nav id="public-navigation" className={mobileOpen ? "is-open" : ""} aria-label="Main">
          {NAV_MENUS.map(({ name }) => (
            <button
              key={name}
              type="button"
              aria-expanded={openMenu === name}
              className={NAV_MENUS.find((menu) => menu.name === name)?.href === page ? "is-current" : ""}
              onClick={() => setOpenMenu(openMenu === name ? null : name)}
            >
              {name} <ChevronDown size={14} aria-hidden="true" />
            </button>
          ))}
          <a href="/resources" className={page === "/resources" ? "is-current" : ""} onClick={closeMenus}>
            Resources
          </a>
          <a href="/company" className={page === "/company" ? "is-current" : ""} onClick={closeMenus}>
            Company
          </a>
          <div className="ms-nav-actions">
            <a href="/signin">Sign in</a>
            <a className="ms-btn ms-btn-primary" href="/company#contact" onClick={closeMenus}>
              Request a demo
            </a>
          </div>
        </nav>
        {activeMenu && (
          <div className="ms-mega" role="region" aria-label={`${activeMenu.title} menu`}>
            <div className="ms-mega-intro">
              <span className="ms-eyebrow">{activeMenu.title}</span>
              <a className="ms-link" href={activeMenu.href} onClick={closeMenus}>
                Overview <ArrowRight size={14} aria-hidden="true" />
              </a>
            </div>
            {activeMenu.groups.map((group) => (
              <section key={group.title}>
                <h2>{group.title}</h2>
                {group.links.map((link) => (
                  <a key={link.label} href={link.href} onClick={closeMenus}>
                    {link.label}
                    {link.note && <small>{link.note}</small>}
                  </a>
                ))}
              </section>
            ))}
          </div>
        )}
      </header>

      <main id="main" className="ms-main">
        {page === "/" && <HomePage />}
        {page === "/platform" && <PlatformPage />}
        {page === "/solutions" && <SolutionsPage />}
        {page === "/product-lifecycle" && <LifecyclePage />}
        {page === "/trust" && <TrustPage />}
        {page === "/resources" && <ResourcesPage />}
        {page === "/company" && <CompanyPage />}
      </main>

      <footer className="ms-footer">
        <div className="ms-footer-top">
          <div className="ms-footer-brand">
            <a className="ms-brand ms-brand-light" href="/">
              <span className="ms-logo" aria-hidden="true">
                M
              </span>
              MDARIX
            </a>
            <p>Evidence-first investigation intelligence for medical-device teams.</p>
            <div className="ms-cta-row">
              <a className="ms-btn ms-btn-light" href="/signup">
                Get started
              </a>
              <a className="ms-btn ms-btn-ghost-light" href="/signin">
                Sign in
              </a>
            </div>
          </div>
          {FOOTER.map((column) => (
            <section key={column.title}>
              <h3>{column.title}</h3>
              {column.links.map(([label, href]) => (
                <a key={label} href={href}>
                  {label}
                </a>
              ))}
            </section>
          ))}
        </div>
        <div className="ms-footer-bottom">
          <span>MDARIX — System of Intelligence, not System of Record.</span>
          <span>Evidence before inference · Humans decide</span>
        </div>
      </footer>
    </div>
  );
}

function pageTitle(page: SitePage) {
  return {
    "/": "Home",
    "/platform": "Platform",
    "/solutions": "Solutions",
    "/product-lifecycle": "Product lifecycle",
    "/trust": "Trust",
    "/resources": "Resources",
    "/company": "Company",
  }[page];
}
