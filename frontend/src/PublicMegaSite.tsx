import { useEffect, useRef, useState } from "react";
import { Menu, X } from "lucide-react";
import "./site/site.css";
import { DEMO_REQUESTS_OFFERED } from "./site/offer";
import { VideosPage } from "./site/videos";
import { QUESTIONS_PATH, QuestionPage, QuestionsPage, questionAt } from "./site/questions";
import { applyPageMeta } from "./site/seo";
import { CompanyPage, HomePage, PlatformPage, SITE_PAGES, TrustPage, type SitePage } from "./site/pages";
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

// Former page addresses, and the page and section that now hold their content, so existing links and bookmarks keep
// working (the web server sends each to the application shell: infrastructure/docker/Caddyfile @shell).
export const LEGACY_PAGES: Record<string, string> = {
  // The four Platform pages and the roadmap became sections of "How it works" (site refresh, Nov 2026).
  "/platform/product-360": "/platform#products",
  "/platform/investigations": "/platform#investigations",
  "/platform/decisions": "/platform#decisions",
  "/platform/trust": "/trust",
  "/roadmap": "/platform#availability",
  "/solutions": "/platform",
  "/product-lifecycle": "/platform#products",
  "/capabilities": "/platform",
  "/integrations": "/trust#integrations",
  // Trust and its regulations page are one page.
  "/trust/regulations": "/trust#markets",
  "/regulations": "/trust#markets",
  "/why-mdarix": "/trust#principles",
  "/ai-trust": "/trust#ai",
  // Resources was a list of the questions and the videos.
  "/resources": QUESTIONS_PATH,
  // Pricing was removed until plans and billing are offered; its links go to the contact page.
  "/pricing": "/contact",
  "/plans": "/contact",
};

// The former capability pages (/platform/challenger) and lifecycle pages (/platform/strategy): the section of the page
// that now holds the subject. Any other address under /platform/ opens "How it works".
const PRODUCT = "/platform#products";
const INVESTIGATIONS = "/platform#investigations";
const DECISIONS = "/platform#decisions";
const FORMER_SECTIONS: Record<string, string> = {
  "reality-graph": PRODUCT,
  "product-version": PRODUCT,
  timeline: PRODUCT,
  "ask-mdarix": INVESTIGATIONS,
  investigation: INVESTIGATIONS,
  evidence: INVESTIGATIONS,
  hypotheses: INVESTIGATIONS,
  challenger: INVESTIGATIONS,
  unknowns: INVESTIGATIONS,
  "failure-chain": DECISIONS,
  counterfactual: DECISIONS,
  "decision-center": DECISIONS,
  "investigation-brief": DECISIONS,
  "ai-assurance": "/trust#ai",
  "ai-provenance": "/trust#ai",
  "human-review": "/trust#principles",
  "audit-trail": "/trust#security",
  "enterprise-administration": "/trust#security",
};

// Former anchors whose section moved: the standards and the roadmap.
const MOVED_ANCHORS: Record<string, string> = {
  "/#standards": "/trust#markets",
  "/trust#trust-standards": "/trust#markets",
  "/#scope-title": "/platform#availability",
  "/platform#scope-title": "/platform#availability",
};

const split = (target: string) => {
  const [page, hash = ""] = target.split("#");
  return { page: page as Page, hash };
};

export function resolveSitePath(path: string, hash: string): { page: Page; hash: string } {
  const clean = path.replace(/\/+$/, "") || "/";
  const moved = MOVED_ANCHORS[`${clean}#${hash}`];
  if (moved) return split(moved);
  // The former single Platform page's anchors (/platform#challenger) open the section that now holds them.
  if (clean === "/platform" && FORMER_SECTIONS[hash]) return split(FORMER_SECTIONS[hash]);
  if ((SITE_PAGES as readonly string[]).includes(clean)) return { page: clean as SitePage, hash };
  if ((INFO_PAGES as readonly string[]).includes(clean)) return { page: clean as Page, hash };
  const legacy = LEGACY_PAGES[clean];
  if (legacy) {
    const target = split(legacy);
    // A legacy page's own anchor (/why-mdarix#not-qms) is kept only when the new page has no section of its own.
    return { page: target.page, hash: target.hash || hash };
  }
  if (clean.startsWith("/platform/")) return split(FORMER_SECTIONS[clean.slice("/platform/".length)] ?? "/platform");
  return { page: "not-found", hash: "" };
}

const NAV = [
  ["Product", "/platform"],
  ["Trust", "/trust"],
  ["Questions", QUESTIONS_PATH],
  ["Company", "/company"],
] as const;

const FOOTER: Array<{ title: string; links: [string, string][] }> = [
  {
    title: "Product",
    links: [
      ["How it works", "/platform"],
      ["What you get", "/platform#availability"],
      ["Markets and regulations", "/trust#markets"],
      ["Trust", "/trust"],
    ],
  },
  {
    title: "Learn",
    links: [
      ["Questions and answers", QUESTIONS_PATH],
      ["Free trial videos", "/videos"],
    ],
  },
  {
    title: "Company",
    links: [
      ["About MDARIX", "/company"],
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

/** Whether the header marks a navigation item as the current page: a question under Questions too. */
function isCurrent(href: string, page: Page): boolean {
  if (href === QUESTIONS_PATH) return page === QUESTIONS_PATH || Boolean(questionAt(page));
  return page === href;
}

export function PublicMegaSite({ path }: { path: string }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [{ page, hash }, setLocation] = useState(() => resolveSitePath(path, window.location.hash.slice(1)));
  const siteInfo = useSiteInfo();
  const firstPage = useRef(true);
  const question = questionAt(page);

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
    const close = (event: KeyboardEvent) => event.key === "Escape" && setMobileOpen(false);
    window.addEventListener("hashchange", update);
    window.addEventListener("popstate", update);
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("hashchange", update);
      window.removeEventListener("popstate", update);
      window.removeEventListener("keydown", close);
    };
  }, []);

  const close = () => setMobileOpen(false);

  return (
    <div className="mdx-site">
      <a className="ms-skip" href="#main">
        Skip to content
      </a>
      <header className="ms-header">
        <div className="ms-header-inner">
          <a className="ms-brand" href="/" aria-label="MDARIX home">
            <span className="ms-logo" aria-hidden="true">
              M
            </span>
            MDARIX
          </a>
          <button
            type="button"
            className="ms-menu-button"
            aria-expanded={mobileOpen}
            aria-controls="public-navigation"
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            {mobileOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
          </button>
          <nav id="public-navigation" className={mobileOpen ? "is-open" : ""} aria-label="Main">
            {NAV.map(([label, href]) => (
              <a
                key={href}
                href={href}
                className={isCurrent(href, page) ? "is-current" : undefined}
                aria-current={isCurrent(href, page) ? "page" : undefined}
                onClick={close}
              >
                {label}
              </a>
            ))}
            <span className="ms-nav-actions">
              <a href="/signin">Sign in</a>
              {DEMO_REQUESTS_OFFERED ? (
                <a className="ms-btn ms-btn-primary" href="/request-demo" onClick={close}>
                  Request a demo
                </a>
              ) : (
                <a className="ms-btn ms-btn-primary" href="/signup" onClick={close}>
                  Start free trial
                </a>
              )}
            </span>
          </nav>
        </div>
      </header>

      <main id="main" className="ms-main">
        {page === "/" && <HomePage />}
        {page === "/platform" && <PlatformPage />}
        {page === "/trust" && <TrustPage />}
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
            <a className="ms-brand" href="/">
              <span className="ms-logo" aria-hidden="true">
                M
              </span>
              MDARIX
            </a>
            <p>From complaint to a defensible decision, and the right report in every market.</p>
            <a className="ms-btn ms-btn-primary" href="/signup">
              Start free trial
            </a>
          </div>
          {FOOTER.map((column) => (
            <section key={column.title} aria-label={column.title}>
              <h2>{column.title}</h2>
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
          <span className="ms-footer-trademarks">
            Product names mentioned on this site and in MDARIX are trademarks of their owners. MDARIX is not affiliated
            with or endorsed by them.
          </span>
        </div>
      </footer>
    </div>
  );
}
