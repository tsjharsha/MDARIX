import { describe, expect, it } from "vitest";
import indexHtml from "../../index.html?raw";
import sitemap from "../../public/sitemap.xml?raw";
import {
  HOME_FILE,
  NOT_FOUND_FILE,
  headTags,
  inlineStylesheet,
  moveInlineStyles,
  outputFile,
  pageHtml,
  sitemapPaths,
  visibleText,
} from "../../scripts/prerender.mjs";
import { INDEXED_PATHS, NOT_FOUND_PATH, pageHead, renderNotFoundPage, renderPage } from "./prerender";
import { PAGE_META } from "./seo";
import { QUESTIONS_PATH, QUESTION_PATHS } from "./questions";

// What crawlers and link previews read without JavaScript (WEB-05): every page of the sitemap as its own HTML file,
// with its own head and its text (scripts/prerender.mjs, run by npm run build).
const attribute = (value: string) => value.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
const count = (html: string, part: string) => html.split(part).length - 1;
const JSON_LD = '<script type="application/ld+json">';

describe("the pre-rendered page an unknown address gets (WEB-17)", () => {
  it("is the website's Page not found page, never indexed and without a canonical address", () => {
    const markup = moveInlineStyles(renderNotFoundPage(), new Map());
    const html = pageHtml(indexHtml, pageHead(null), markup, "/assets/prerender-test.css");
    expect(NOT_FOUND_FILE).toBe("404.html");
    expect(INDEXED_PATHS as readonly string[]).not.toContain(NOT_FOUND_PATH);
    expect(html).toContain("<title>Page not found · MDARIX</title>");
    expect(html).toContain('<meta name="robots" content="noindex, follow" />');
    expect(html).not.toContain('rel="canonical"');
    expect(markup).toContain('<h1 id="not-found-title">Page not found</h1>');
    expect(markup).toContain("Go to the home page");
    // The website's frame (header and footer) is there too.
    expect(markup).toContain("Skip to content");
    expect(markup).not.toMatch(/\sstyle="/);
  });
});

describe("the pre-rendered website pages", () => {
  const classes = new Map<string, string>();
  const pages = INDEXED_PATHS.map((path) => {
    const markup = moveInlineStyles(renderPage(path), classes);
    return { path, markup, html: pageHtml(indexHtml, pageHead(path), markup, "/assets/prerender-test.css") };
  });

  it("covers exactly the pages of the sitemap, the home page in a file of its own", () => {
    expect(sitemapPaths(sitemap)).toEqual(INDEXED_PATHS);
    // 21 pages, then (0.10.45) the questions and answers: their index and six questions.
    expect(INDEXED_PATHS).toHaveLength(28);
    expect(INDEXED_PATHS.filter((path) => path.startsWith(QUESTIONS_PATH))).toEqual([
      QUESTIONS_PATH,
      ...QUESTION_PATHS,
    ]);
    expect(outputFile("/")).toBe(HOME_FILE);
    expect(HOME_FILE).not.toBe("index.html");
    expect(outputFile("/platform")).toBe("platform/index.html");
    expect(outputFile("/trust/regulations")).toBe("trust/regulations/index.html");
    expect(outputFile(QUESTION_PATHS[0])).toBe(`${QUESTION_PATHS[0].slice(1)}/index.html`);
    expect(() => outputFile("/../secret")).toThrow();
  });

  it("gives each page its own title, description, canonical address and link-preview tags, once each", () => {
    for (const { path, html: page } of pages) {
      const meta = PAGE_META[path];
      const url = `https://mdarix.in${path}`;
      // The head only: the page's drawings carry SVG <title> elements of their own.
      const html = page.slice(0, page.indexOf("</head>"));
      expect(count(html, "<title>"), path).toBe(1);
      expect(html, path).toContain(`<title>${meta.title.replace(/&/g, "&amp;")}</title>`);
      expect(count(html, 'name="description"'), path).toBe(1);
      expect(html, path).toContain(`<meta name="description" content="${attribute(meta.description)}" />`);
      expect(count(html, 'rel="canonical"'), path).toBe(1);
      expect(html, path).toContain(`<link rel="canonical" href="${url}" />`);
      expect(html, path).toContain(`<meta property="og:title" content="${attribute(meta.title)}" />`);
      expect(html, path).toContain(`<meta property="og:description" content="${attribute(meta.description)}" />`);
      expect(html, path).toContain(`<meta property="og:url" content="${url}" />`);
      expect(html, path).toContain('<meta name="robots" content="index, follow" />');
      // The template's shared tags stay: the share image, twitter:card, the organization's JSON-LD.
      expect(html, path).toContain('property="og:image" content="https://mdarix.in/og-image.png"');
      expect(html, path).toContain('name="twitter:card"');
      expect(html, path).toContain('"@type": "Organization"');
    }
    expect(new Set(pages.map(({ html }) => html.match(/<title>(.*?)<\/title>/)?.[1])).size).toBe(pages.length);
  });

  it("puts the page's own text inside the root, readable without JavaScript", () => {
    for (const { path, markup, html } of pages) {
      expect(html, path).toContain(`<div id="root">${markup}</div>`);
      expect(visibleText(markup).split(" ").length, path).toBeGreaterThan(100);
      expect(markup, path).toMatch(/<h1[\s>]/);
      // The CSP allows no inline script or style: the page adds no script, and its inline styles are classes of one
      // stylesheet. A JSON-LD block is data, which no browser runs: the template has the organization's, and the
      // questions and answers carry their own (questions.tsx).
      expect(count(html, "<script") - count(html, JSON_LD), path).toBe(
        count(indexHtml, "<script") - count(indexHtml, JSON_LD),
      );
      expect(count(markup, JSON_LD), path).toBe(path.startsWith(QUESTIONS_PATH) ? 1 : 0);
      for (const block of markup.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g))
        expect(JSON.parse(block[1])["@type"], path).toBe(path === QUESTIONS_PATH ? "CollectionPage" : "FAQPage");
      expect(html, path).not.toMatch(/\sstyle="/);
      expect(html, path).toContain('<link rel="stylesheet" href="/assets/prerender-test.css" />');
    }
    const text = (path: string) => visibleText(pages.find((page) => page.path === path)!.markup);
    expect(text("/")).toContain("Start free trial");
    expect(text("/platform/investigations")).toContain("hypotheses");
    expect(text("/trust/regulations")).toContain("ISO 13485");
    // The videos page lists the fourteen videos before videos.json has said which are ready, without "Coming soon".
    expect(text("/videos")).toContain("MDARIX Free Trial, Step by Step");
    expect(text("/videos")).not.toContain("Coming soon");
    // A legal page's text is served live (MDARIX_LEGAL_DIR): its frame is pre-rendered, with the way to get the text.
    expect(text("/privacy")).toContain("Privacy policy");
    expect(pages.find((page) => page.path === "/privacy")!.markup).toContain("<noscript>");
    expect(text("/signup")).toContain("30");
    expect(text(QUESTION_PATHS[1])).toContain("When does a complaint become a reportable event?");
    expect(text(QUESTIONS_PATH)).toContain("How do I show a CAPA was effective?");
  });

  it("turns inline styles into classes of a stylesheet, as strong as an inline style", () => {
    const styles = new Map<string, string>();
    const markup = moveInlineStyles(
      '<li style="animation-delay:1.2s">a</li><i class="support" style="width:64%"></i>' +
        '<text x="1" style="font-size:max(14px, var(--sc-floor, 0px));letter-spacing:-0.02em">b</text>' +
        '<span style="animation-delay:1.2s"></span><img style="width:2px" alt=""/>',
      styles,
    );
    expect(markup).not.toContain("style=");
    expect(styles.size).toBe(4);
    const delay = styles.get("animation-delay:1.2s")!;
    expect(markup).toContain(`<li class="${delay}">a</li>`);
    expect(markup).toContain(`<span class="${delay}"></span>`);
    expect(markup).toContain(`<i class="support ${styles.get("width:64%")}"></i>`);
    expect(markup).toContain(`<img alt="" class="${styles.get("width:2px")}"/>`);
    const css = inlineStylesheet(styles);
    expect(css).toContain(`.${delay}{animation-delay:1.2s !important}`);
    expect(css).toContain("font-size:max(14px, var(--sc-floor, 0px)) !important;letter-spacing:-0.02em !important");
  });

  it("escapes what it writes into the head", () => {
    const tags = headTags({ title: 'A & "B" <c>', description: "d & e", robots: "index, follow", url: null });
    expect(tags).toContain('<title>A &amp; "B" &lt;c&gt;</title>');
    expect(tags).toContain('<meta name="description" content="d &amp; e" />');
    expect(tags.some((tag) => tag.includes("canonical"))).toBe(false);
  });

  it("leaves the application shell alone: no canonical, no page text (the application and sign-in get it)", () => {
    expect(indexHtml).toContain('<div id="root"></div>');
    expect(indexHtml).not.toContain('rel="canonical"');
    for (const path of ["/app", "/platform-admin", "/signin", "/mfa", "/reset-password"])
      expect(INDEXED_PATHS as readonly string[]).not.toContain(path);
    // Without JavaScript the animated parts show complete (public/noscript.css); the link is inside <noscript>.
    expect(indexHtml).toContain('<noscript><link rel="stylesheet" href="/noscript.css" /></noscript>');
  });
});
