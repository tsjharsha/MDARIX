import React, { useEffect, useRef, useState } from "react";
import { ArrowRight, ChevronDown, Menu, X } from "lucide-react";
import "./site/site.css";
import { DEMO_REQUESTS_OFFERED } from "./site/offer";
import { VideosPage } from "./site/videos";
import { QUESTIONS_PATH, QuestionPage, QuestionsPage, questionAt } from "./site/questions";
import { applyPageMeta } from "./site/seo";
import { menuMove, menuPanelId, type MenuFocus } from "./site/menuKeys";
import { lifecycleStages, platformGroups, platformPageOf, solutionGroups, FUTURE_LIFECYCLE } from "./site/content";
import {
  CompanyPage,
  HomePage,
  LifecyclePage,
  PlatformGroupPage,
  PlatformPage,
  RegulationsPage,
  ResourcesPage,
  RoadmapPage,
  SITE_PAGES,
  SolutionsPage,
  TrustPage,
  type SitePage,
} from "./site/pages";
import {
  ContactPage,
  LEGAL_PAGES,
  AccessibilityPage,
  LegalDocumentPage,
  NotFoundPage,
  SecurityPage,
  useSiteInfo,
  type LegalPath,
} from "./site/legal";

// Pages outside the main navigation: legal documents, security and contact. Anything else is "not found".
const INFO_PAGES = ["/privacy", "/terms", "/trial-agreement", "/security", "/accessibility", "/contact"] as const;
type Page = SitePage | (typeof INFO_PAGES)[number] | "not-found";

// The website was consolidated from ~65 URLs into a few pages. Every old URL lands on the section that now holds its
// content, so existing links and bookmarks keep working.
export const LEGACY_PAGES: Record<string, string> = {
  "/why-mdarix": "/trust#principles",
  "/ai-trust": "/trust#ai",
  "/integrations": "/trust#integrations",
  // Pricing was removed until plans and billing are offered; its links go to the contact page.
  "/pricing": "/contact",
  "/plans": "/contact",
  "/capabilities": "/platform",
  "/regulations": "/trust/regulations",
};
// Former anchors whose section moved to a page of its own: the standards (home page and Trust) to Regulations, the
// roadmap (home page and Platform) to the roadmap page.
const MOVED_ANCHORS: Record<string, string> = {
  "/#standards": "/trust/regulations",
  "/trust#trust-standards": "/trust/regulations",
  "/#scope-title": "/roadmap",
  "/platform#scope-title": "/roadmap",
};
const LIFECYCLE_SLUGS = new Set(lifecycleStages.flatMap((stage) => stage.items.map((item) => item.slug)));
const PLATFORM_SLUGS = new Set(
  platformGroups.flatMap((group) => group.capabilities.map((capability) => capability.slug)),
);

export function resolveSitePath(path: string, hash: string): { page: Page; hash: string } {
  const clean = path.replace(/\/+$/, "") || "/";
  const moved = MOVED_ANCHORS[`${clean}#${hash}`];
  if (moved) return { page: moved as Page, hash: "" };
  // The former single Platform page's anchors (/platform#challenger, /platform#decision-intelligence) open the page
  // that now holds the capability, at its section; a former group anchor opens its page at the top.
  if (clean === "/platform" && hash) {
    const target = platformPageOf(hash);
    if (target) return { page: target.path, hash: target.id === hash ? "" : hash };
  }
  // The roadmap was a section of the lifecycle page; its lifecycle anchors (/roadmap#capa) still open there.
  if (clean === "/roadmap" && (LIFECYCLE_SLUGS.has(hash) || FUTURE_LIFECYCLE.has(hash)))
    return { page: "/product-lifecycle", hash };
  if ((SITE_PAGES as readonly string[]).includes(clean)) return { page: clean as SitePage, hash };
  if ((INFO_PAGES as readonly string[]).includes(clean)) return { page: clean as Page, hash };
  if (clean.startsWith("/platform/")) {
    // A former capability page (/platform/challenger) opens its section on the Platform page that holds it.
    const slug = clean.slice("/platform/".length);
    const target = PLATFORM_SLUGS.has(slug) ? platformPageOf(slug) : undefined;
    if (target) return { page: target.path, hash: slug };
    if (LIFECYCLE_SLUGS.has(slug) || FUTURE_LIFECYCLE.has(slug)) return { page: "/product-lifecycle", hash: slug };
    return { page: "/platform", hash: "" };
  }
  const legacy = LEGACY_PAGES[clean];
  if (legacy) {
    const [page, anchor] = legacy.split("#");
    // A legacy page's own anchor (e.g. /why-mdarix#not-qms or /roadmap#capa) wins over the default section.
    return { page: page as Page, hash: hash || anchor || "" };
  }
  return { page: "not-found", hash: "" };
}

type NavMenu = {
  name: string;
  title: string;
  href: string;
  /** Further pages, listed under Overview. */
  more?: { label: string; href: string }[];
  groups: { title?: string; links: { label: string; href: string; note?: string; description?: string }[] }[];
};

const NAV_MENUS: NavMenu[] = [
  {
    name: "Platform",
    title: "Platform",
    href: "/platform",
    // Four pages, each holding its capabilities as sections.
    groups: platformGroups.map((group) => ({
      links: [{ label: group.name, href: group.path, description: group.blurb }],
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
    more: [{ label: "Roadmap", href: "/roadmap" }],
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
          { label: "Regulations", href: "/trust/regulations" },
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
      ["Overview", "/platform"],
      ...platformGroups.map((group): [string, string] => [group.name, group.path]),
      ["Roadmap", "/roadmap"],
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
      ["Regulations", "/trust/regulations"],
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
      ["Questions and answers", QUESTIONS_PATH],
      ["Free trial videos", "/videos"],
      ...(DEMO_REQUESTS_OFFERED ? [["Request a demo", "/request-demo"] as [string, string]] : []),
      ["Contact", "/contact"],
    ],
  },
  {
    title: "Legal",
    links: [
      ["Privacy policy", "/privacy"],
      ["Terms of service", "/terms"],
      ["Free trial agreement", "/trial-agreement"],
      ["Security", "/security"],
      ["Accessibility", "/accessibility"],
    ],
  },
];

/** The menu a page belongs to, so the header marks it: a Platform page under Platform, Regulations under Trust. */
function isCurrentMenu(name: string, page: Page): boolean {
  const menu = NAV_MENUS.find((item) => item.name === name);
  if (!menu) return false;
  if (menu.href === page || menu.more?.some((link) => link.href === page)) return true;
  return page.startsWith(`${menu.href}/`);
}

export function PublicMegaSite({ path }: { path: string }) {
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [{ page, hash }, setLocation] = useState(() => resolveSitePath(path, window.location.hash.slice(1)));
  const siteInfo = useSiteInfo();
  const firstPage = useRef(true);
  const question = questionAt(page);
  // The questions and answers are resources: the header marks Resources on them too.
  const inResources = page === "/resources" || page === QUESTIONS_PATH || Boolean(question);

  // Normalize legacy URLs in the address bar (a "not found" address is left as typed), then bring the requested
  // section into view.
  useEffect(() => {
    const target = `${page}${hash ? `#${hash}` : ""}`;
    if (page !== "not-found" && `${window.location.pathname}${window.location.hash}` !== target)
      window.history.replaceState(null, "", target);
    applyPageMeta(page === "not-found" ? null : page);
    if (hash) window.setTimeout(() => document.getElementById(hash)?.scrollIntoView({ block: "start" }), 60);
    // A page opened from its address keeps where the reader already is: it was readable before the app started
    // (pre-rendered, WEB-05), and a jump to the top would undo any scrolling done meanwhile.
    else if (!firstPage.current) window.scrollTo({ top: 0 });
    firstPage.current = false;
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

  // The header menus' buttons and the open menu's panel, for the keyboard order (WEB-10, site/menuKeys.ts).
  const menuButtons = useRef<Record<string, HTMLButtonElement | null>>({});
  const menuPanel = useRef<HTMLDivElement | null>(null);
  const navigation = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // Escape from inside an open menu, or from its button, puts the focus back on the button.
        const opener = openMenu ? menuButtons.current[openMenu] : null;
        const active = document.activeElement;
        if (opener && active && (active === opener || menuPanel.current?.contains(active))) opener.focus();
        setOpenMenu(null);
        setMobileOpen(false);
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [openMenu]);

  const closeMenus = () => {
    setOpenMenu(null);
    setMobileOpen(false);
  };
  const activeMenu = NAV_MENUS.find((menu) => menu.name === openMenu);

  // Tab from an open menu's button goes into the menu; Shift+Tab from its first link back to the button; Tab past its
  // last link closes it and goes on to the header item after the button. Escape is handled above.
  const menuLinks = () => Array.from(menuPanel.current?.querySelectorAll<HTMLAnchorElement>("a[href]") ?? []);
  const moveInMenu = (event: React.KeyboardEvent, focus: MenuFocus) => {
    if (!openMenu || event.key === "Escape") return;
    const move = menuMove(event.key, event.shiftKey, focus);
    const opener = menuButtons.current[openMenu];
    if (!move || !opener) return;
    const links = menuLinks();
    if (move === "first-link") {
      if (!links.length) return;
      event.preventDefault();
      links[0].focus();
    } else if (move === "button") {
      event.preventDefault();
      opener.focus();
    } else if (move === "close-and-continue") {
      const items = Array.from(navigation.current?.querySelectorAll<HTMLElement>("button, a[href]") ?? []);
      const next = items[items.indexOf(opener) + 1];
      if (!next) return;
      event.preventDefault();
      setOpenMenu(null);
      next.focus();
    }
  };
  const onMenuKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const links = menuLinks();
    const index = links.indexOf(document.activeElement as HTMLAnchorElement);
    if (index >= 0) moveInMenu(event, { at: "link", index, count: links.length });
  };

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
          onClick={() => {
            setMobileOpen(!mobileOpen);
            setOpenMenu(null);
          }}
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
        <nav id="public-navigation" ref={navigation} className={mobileOpen ? "is-open" : ""} aria-label="Main">
          {NAV_MENUS.map(({ name }) => (
            <button
              key={name}
              ref={(element) => {
                menuButtons.current[name] = element;
              }}
              type="button"
              aria-expanded={openMenu === name}
              aria-controls={openMenu === name ? menuPanelId(name) : undefined}
              className={isCurrentMenu(name, page) ? "is-current" : ""}
              onClick={() => setOpenMenu(openMenu === name ? null : name)}
              onKeyDown={(event) => openMenu === name && moveInMenu(event, { at: "button" })}
            >
              {name} <ChevronDown size={14} aria-hidden="true" />
            </button>
          ))}
          <a href="/resources" className={inResources ? "is-current" : ""} onClick={closeMenus}>
            Resources
          </a>
          <a href="/company" className={page === "/company" ? "is-current" : ""} onClick={closeMenus}>
            Company
          </a>
          <div className="ms-nav-actions">
            <a href="/signin">Sign in</a>
            {DEMO_REQUESTS_OFFERED ? (
              <a className="ms-btn ms-btn-primary" href="/request-demo" onClick={closeMenus}>
                Request a demo
              </a>
            ) : (
              <a className="ms-btn ms-btn-primary" href="/signup" onClick={closeMenus}>
                Start free trial
              </a>
            )}
          </div>
        </nav>
        {activeMenu && (
          <div
            className="ms-mega"
            id={menuPanelId(activeMenu.name)}
            ref={menuPanel}
            role="region"
            aria-label={`${activeMenu.title} menu`}
            onKeyDown={onMenuKeyDown}
          >
            <div className="ms-mega-intro">
              <span className="ms-eyebrow">{activeMenu.title}</span>
              <a className="ms-link" href={activeMenu.href} onClick={closeMenus}>
                Overview <ArrowRight size={14} aria-hidden="true" />
              </a>
              {activeMenu.more?.map((link) => (
                <a key={link.href} className="ms-link" href={link.href} onClick={closeMenus}>
                  {link.label} <ArrowRight size={14} aria-hidden="true" />
                </a>
              ))}
            </div>
            {activeMenu.groups.map((group, index) => (
              <section key={group.title ?? index}>
                {group.title && <h2>{group.title}</h2>}
                {group.links.map((link) =>
                  link.description ? (
                    <a key={link.label} className="ms-mega-page" href={link.href} onClick={closeMenus}>
                      <strong>{link.label}</strong>
                      <span>{link.description}</span>
                    </a>
                  ) : (
                    <a key={link.label} href={link.href} onClick={closeMenus}>
                      {link.label}
                      {link.note && <small>{link.note}</small>}
                    </a>
                  ),
                )}
              </section>
            ))}
          </div>
        )}
      </header>

      <main id="main" className="ms-main">
        {page === "/" && <HomePage />}
        {page === "/platform" && <PlatformPage />}
        {platformGroups.map((group) => page === group.path && <PlatformGroupPage key={group.path} path={group.path} />)}
        {page === "/roadmap" && <RoadmapPage />}
        {page === "/trust/regulations" && <RegulationsPage />}
        {page === "/solutions" && <SolutionsPage />}
        {page === "/product-lifecycle" && <LifecyclePage />}
        {page === "/trust" && <TrustPage />}
        {page === "/resources" && <ResourcesPage />}
        {page === "/company" && <CompanyPage />}
        {page === "/videos" && <VideosPage />}
        {page === QUESTIONS_PATH && <QuestionsPage />}
        {question && <QuestionPage question={question} />}
        {page in LEGAL_PAGES && <LegalDocumentPage path={page as LegalPath} />}
        {page === "/security" && <SecurityPage />}
        {page === "/accessibility" && <AccessibilityPage />}
        {page === "/contact" && <ContactPage />}
        {page === "not-found" && <NotFoundPage />}
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
                Start free trial
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
          <span>
            © {new Date().getFullYear()} {siteInfo?.company_name ?? "MDARIX"}
            {siteInfo?.company_address ? ` · ${siteInfo.company_address}` : ""}
            {siteInfo?.support_email && (
              <>
                {" · "}
                <a href={`mailto:${siteInfo.support_email}`}>{siteInfo.support_email}</a>
              </>
            )}
          </span>
          <span>System of Intelligence, not System of Record · Evidence before inference · Humans decide</span>
          <span className="ms-footer-trademarks">
            Product names mentioned on this site and in MDARIX are trademarks of their owners. MDARIX is not affiliated
            with or endorsed by them.
          </span>
        </div>
      </footer>
    </div>
  );
}
