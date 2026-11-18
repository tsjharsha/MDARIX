import { describe, expect, it } from "vitest";
import { LEGACY_PAGES, resolveSitePath } from "../PublicMegaSite";
import { QUESTIONS_PATH, QUESTION_PATHS } from "./questions";
import { SITE_PAGES } from "./pages";
import { INDEXED_PATHS, renderPage, type IndexedPath } from "./prerender";

// The pages removed in the site refresh (Nov 2026) and the page and section that now hold each one.
const REMOVED_PAGES: Record<string, [string, string]> = {
  "/platform/product-360": ["/platform", "products"],
  "/platform/investigations": ["/platform", "investigations"],
  "/platform/decisions": ["/platform", "decisions"],
  "/platform/trust": ["/trust", ""],
  "/roadmap": ["/platform", "availability"],
  "/solutions": ["/platform", ""],
  "/product-lifecycle": ["/platform", "products"],
  "/trust/regulations": ["/trust", "markets"],
  "/resources": [QUESTIONS_PATH, ""],
};

// The 19 former capability pages of the first site, each sent to the section that now covers it.
const FORMER_CAPABILITY_PAGES: Record<string, [string, string]> = {
  "/platform/reality-graph": ["/platform", "products"],
  "/platform/product-version": ["/platform", "products"],
  "/platform/timeline": ["/platform", "products"],
  "/platform/ask-mdarix": ["/platform", "investigations"],
  "/platform/investigation": ["/platform", "investigations"],
  "/platform/evidence": ["/platform", "investigations"],
  "/platform/hypotheses": ["/platform", "investigations"],
  "/platform/challenger": ["/platform", "investigations"],
  "/platform/unknowns": ["/platform", "investigations"],
  "/platform/failure-chain": ["/platform", "decisions"],
  "/platform/counterfactual": ["/platform", "decisions"],
  "/platform/decision-center": ["/platform", "decisions"],
  "/platform/investigation-brief": ["/platform", "decisions"],
  "/platform/ai-assurance": ["/trust", "ai"],
  "/platform/ai-provenance": ["/trust", "ai"],
  "/platform/human-review": ["/trust", "principles"],
  "/platform/audit-trail": ["/trust", "security"],
  "/platform/enterprise-administration": ["/trust", "security"],
};

describe("website addresses", () => {
  it("opens the four pages, the videos, the legal, security and contact pages", () => {
    for (const path of [
      "/",
      "/platform",
      "/trust",
      "/company",
      "/videos",
      "/privacy",
      "/terms",
      "/trial-agreement",
      "/security",
      "/accessibility",
      "/contact",
    ])
      expect(resolveSitePath(path, "")).toEqual({ page: path, hash: "" });
  });

  it("opens the questions and answers, each question on its own page", () => {
    for (const path of [QUESTIONS_PATH, ...QUESTION_PATHS]) {
      expect(resolveSitePath(path, ""), path).toEqual({ page: path, hash: "" });
      expect(resolveSitePath(`${path}/`, ""), path).toEqual({ page: path, hash: "" });
    }
    expect(resolveSitePath("/questions/how-to-trend", "")).toEqual({ page: "not-found", hash: "" });
  });

  it("shows a not-found page for unknown addresses instead of the home page", () => {
    expect(resolveSitePath("/no-such-page", "")).toEqual({ page: "not-found", hash: "" });
    expect(resolveSitePath("/privacy-policy", "x")).toEqual({ page: "not-found", hash: "" });
  });

  it("sends every page removed in the refresh to the section that now holds it", () => {
    for (const [path, [page, hash]] of Object.entries(REMOVED_PAGES)) {
      expect(LEGACY_PAGES[path], path).toBeDefined();
      expect((SITE_PAGES as readonly string[]).includes(path), path).toBe(false);
      expect(resolveSitePath(path, ""), path).toEqual({ page, hash });
      expect(resolveSitePath(`${path}/`, ""), path).toEqual({ page, hash });
    }
  });

  it("keeps the older former addresses working", () => {
    expect(resolveSitePath("/pricing", "")).toEqual({ page: "/contact", hash: "" });
    expect(resolveSitePath("/plans/", "")).toEqual({ page: "/contact", hash: "" });
    expect(resolveSitePath("/ai-trust", "")).toEqual({ page: "/trust", hash: "ai" });
    expect(resolveSitePath("/why-mdarix", "")).toEqual({ page: "/trust", hash: "principles" });
    expect(resolveSitePath("/regulations", "")).toEqual({ page: "/trust", hash: "markets" });
    expect(resolveSitePath("/integrations", "")).toEqual({ page: "/trust", hash: "integrations" });
    expect(resolveSitePath("/capabilities", "")).toEqual({ page: "/platform", hash: "" });
  });

  it("sends each former capability page, and the former single page's anchors, to their section", () => {
    for (const [path, [page, hash]] of Object.entries(FORMER_CAPABILITY_PAGES)) {
      expect(resolveSitePath(path, ""), path).toEqual({ page, hash });
      const slug = path.slice("/platform/".length);
      expect(resolveSitePath("/platform", slug), slug).toEqual({ page, hash });
    }
    // A former lifecycle page or anything else under /platform/ opens How it works.
    expect(resolveSitePath("/platform/strategy", "")).toEqual({ page: "/platform", hash: "" });
    expect(resolveSitePath("/platform", "no-such-section")).toEqual({ page: "/platform", hash: "no-such-section" });
  });

  it("sends the moved standards and roadmap anchors to their sections", () => {
    expect(resolveSitePath("/", "standards")).toEqual({ page: "/trust", hash: "markets" });
    expect(resolveSitePath("/trust", "trust-standards")).toEqual({ page: "/trust", hash: "markets" });
    expect(resolveSitePath("/", "scope-title")).toEqual({ page: "/platform", hash: "availability" });
  });

  it("lands every redirect and every link between the pages on a section that exists", () => {
    const rendered = new Map<string, string>();
    const html = (page: string) => {
      if (!rendered.has(page)) rendered.set(page, renderPage(page as IndexedPath));
      return rendered.get(page)!;
    };
    const targets = [...Object.values(REMOVED_PAGES), ...Object.values(FORMER_CAPABILITY_PAGES)];
    for (const [page, hash] of targets) if (hash) expect(html(page), `${page}#${hash}`).toContain(`id="${hash}"`);
    // Every internal link on every page opens a page (and its section) instead of "not found".
    for (const path of INDEXED_PATHS) {
      for (const [, href] of html(path).matchAll(/href="(\/[^"]*)"/g)) {
        if (/^\/(signin|signup|request-demo|assets|media|site\/app\/)/.test(href)) continue;
        const [address, anchor = ""] = href.split("#");
        const target = resolveSitePath(address, anchor);
        expect(target.page, `${path} -> ${href}`).not.toBe("not-found");
        if (target.hash) expect(html(target.page), `${path} -> ${href}`).toContain(`id="${target.hash}"`);
      }
    }
  });
});
