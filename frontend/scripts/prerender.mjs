// Pre-render the website's pages into the build (WEB-05), the last step of `npm run build`:
//
//   tsc && vite build                         the app, as before: dist/index.html is the application shell
//   vite build --ssr src/site/prerender.tsx   the pages' server-side renderer, into dist-prerender/ (not shipped)
//   node scripts/prerender.mjs                this script
//
// For every page in public/sitemap.xml it writes a copy of dist/index.html with that page's own <title>, description,
// robots rule, canonical address and link-preview tags (src/site/seo.ts pageHead, the same data the browser applies),
// and with the page's static HTML inside <div id="root">, so crawlers and link previews that run no JavaScript read
// the page itself. "/" becomes dist/home.html and "/platform" dist/platform/index.html. The pages' inline style
// attributes become classes of one stylesheet (dist/assets/prerender-<hash>.css): the CSP allows no inline style, so
// the browser would refuse them and log each one. dist/index.html itself stays the plain shell: Caddy serves it for
// the application, sign-in and every other address (infrastructure/docker/Caddyfile). The browser mounts the app
// with createRoot, which replaces the pre-rendered markup with the same page (src/main.tsx).
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..");
export const DIST = join(FRONTEND, "dist");
export const RENDERER = join(FRONTEND, "dist-prerender", "prerender.js");
const SITEMAP = join(FRONTEND, "public", "sitemap.xml");
export const SITE_URL = "https://mdarix.com";
/** The home page's file: dist/index.html is the application shell, so "/" has a file of its own (Caddyfile). */
export const HOME_FILE = "home.html";
/** The "Page not found" page, sent with a 404 status for an address that is no page (Caddyfile, WEB-17). */
export const NOT_FOUND_FILE = "404.html";
const ROOT = '<div id="root"></div>';

/** Where the page at ``path`` is written, relative to dist. */
export function outputFile(path) {
  if (path === "/") return HOME_FILE;
  if (!/^\/[a-z0-9-]+(\/[a-z0-9-]+)*$/.test(path)) throw new Error(`Not a website page address: ${path}`);
  return `${path.slice(1)}/index.html`;
}

const attribute = (value) =>
  String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const text = (value) => String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** The tags a page's head carries for itself (``head`` is seo.ts pageHead). The site uses only twitter:card, which
 * stays in the template: X reads og:title and og:description. */
export function headTags(head) {
  return [
    `<title>${text(head.title)}</title>`,
    `<meta name="description" content="${attribute(head.description)}" />`,
    `<meta name="robots" content="${attribute(head.robots)}" />`,
    head.url ? `<link rel="canonical" href="${attribute(head.url)}" />` : null,
    `<meta property="og:title" content="${attribute(head.title)}" />`,
    `<meta property="og:description" content="${attribute(head.description)}" />`,
    head.url ? `<meta property="og:url" content="${attribute(head.url)}" />` : null,
  ].filter(Boolean);
}

// The template's own copies of the tags above (index.html words them for the home page), removed before the page's
// own are written.
const PAGE_TAGS = [
  /<title>[\s\S]*?<\/title>\s*/g,
  /<meta\s+name="(?:description|robots)"[\s\S]*?\/?>\s*/g,
  /<meta\s+property="og:(?:title|description|url)"[\s\S]*?\/?>\s*/g,
  /<link\s+rel="canonical"[\s\S]*?\/?>\s*/g,
];

const unescape = (value) =>
  value
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
const START_TAG_WITH_STYLE = /<([a-zA-Z][\w:-]*)((?:\s[^<>]*?)?)\sstyle="([^"]*)"([^<>]*?)>/g;

/**
 * The markup with every style="..." attribute replaced by a class (``classes`` maps a declaration list to its class,
 * shared by all pages). The CSP (style-src 'self', infrastructure/docker/Caddyfile) refuses inline styles: as
 * attributes in the HTML they would be dropped and logged; React sets the same styles through the DOM once the app
 * runs, which the CSP allows. Each declaration keeps an inline style's weight with !important.
 */
export function moveInlineStyles(markup, classes) {
  return markup.replace(START_TAG_WITH_STYLE, (_tag, name, before, style, after) => {
    const declarations = unescape(style).trim();
    if (!declarations) return `<${name}${before}${after}>`;
    let className = classes.get(declarations);
    if (!className) {
      className = `pr-${createHash("sha256").update(declarations).digest("hex").slice(0, 10)}`;
      classes.set(declarations, className);
    }
    const attributes = `${before}${after}`;
    if (/\sclass="/.test(attributes))
      return `<${name}${attributes.replace(/\sclass="([^"]*)"/, (_match, value) => ` class="${`${value} ${className}`.trim()}"`)}>`;
    const closing = attributes.endsWith("/") ? "/" : "";
    return `<${name}${closing ? attributes.slice(0, -1) : attributes} class="${className}"${closing}>`;
  });
}

/** The stylesheet for ``moveInlineStyles``' classes. */
export function inlineStylesheet(classes) {
  const rules = [];
  for (const [declarations, name] of classes) {
    const body = declarations
      .split(/;(?![^(]*\))/)
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => (/!important$/.test(item) ? item : `${item} !important`))
      .join(";");
    rules.push(`.${name}{${body}}`);
  }
  return `/* Inline styles of the pre-rendered website pages (scripts/prerender.mjs). */\n${rules.join("\n")}\n`;
}

/** One page's HTML: the built shell with the page's head tags after the viewport tag, its markup in the root and,
 * when given, the stylesheet that holds its inline styles. */
export function pageHtml(template, head, markup, stylesheet = null) {
  if (template.split(ROOT).length !== 2) throw new Error(`The template must hold ${ROOT} exactly once`);
  let html = template;
  for (const pattern of PAGE_TAGS) html = html.replace(pattern, "");
  const viewport = html.match(/<meta\s+name="viewport"[^>]*>\s*/);
  if (!viewport) throw new Error("The template has no viewport tag to place the page's tags after");
  const indent = "\n    ";
  const at = viewport.index + viewport[0].trimEnd().length;
  html = `${html.slice(0, at)}${indent}${headTags(head).join(indent)}${html.slice(at)}`;
  if (stylesheet)
    html = html.replace("</head>", `  <link rel="stylesheet" href="${attribute(stylesheet)}" />\n  </head>`);
  return html.replace(ROOT, `<div id="root">${markup}</div>`);
}

/** The page addresses public/sitemap.xml lists, in order. */
export function sitemapPaths(xml) {
  return [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => {
    const url = match[1].trim();
    if (!url.startsWith(SITE_URL)) throw new Error(`The sitemap lists an address outside ${SITE_URL}: ${url}`);
    return url.slice(SITE_URL.length) || "/";
  });
}

/** The words a reader sees in some markup, without tags: what the build checks each page has plenty of. */
export const visibleText = (markup) =>
  markup
    .replace(/<(script|style)[\s\S]*?<\/\1>/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();

async function main() {
  const shell = join(DIST, "index.html");
  if (!existsSync(shell)) throw new Error("dist/index.html is missing: run vite build first");
  if (!existsSync(RENDERER)) throw new Error("dist-prerender/prerender.js is missing: run vite build --ssr first");
  const template = readFileSync(shell, "utf-8");
  const { INDEXED_PATHS, pageHead, renderPage, renderNotFoundPage } = await import(pathToFileURL(RENDERER).href);
  const listed = sitemapPaths(readFileSync(SITEMAP, "utf-8"));
  if (JSON.stringify(listed) !== JSON.stringify(INDEXED_PATHS))
    throw new Error(`public/sitemap.xml and src/site/seo.ts list different pages: ${listed} / ${INDEXED_PATHS}`);
  const classes = new Map();
  const pages = INDEXED_PATHS.map((path) => {
    const markup = moveInlineStyles(renderPage(path), classes);
    const words = visibleText(markup).split(" ").length;
    // A page that rendered next to nothing would be served to crawlers as is: stop the build instead.
    if (words < 100) throw new Error(`${path} rendered only ${words} words`);
    if (/\sstyle="/.test(markup)) throw new Error(`${path} still holds an inline style`);
    return { path, markup, words };
  });
  // The "Page not found" page: never indexed, no canonical address (pageHead(null)).
  const missing = moveInlineStyles(renderNotFoundPage(), classes);
  if (!visibleText(missing).includes("Page not found")) throw new Error("the not-found page rendered no heading");
  if (/\sstyle="/.test(missing)) throw new Error("the not-found page still holds an inline style");
  const css = inlineStylesheet(classes);
  const stylesheet = `/assets/prerender-${createHash("sha256").update(css).digest("hex").slice(0, 10)}.css`;
  writeFileSync(join(DIST, stylesheet.slice(1)), css);
  const written = [];
  for (const { path, markup, words } of pages) {
    const file = join(DIST, outputFile(path));
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, pageHtml(template, pageHead(path), markup, stylesheet));
    written.push({ path, file: outputFile(path), bytes: statSync(file).size, words });
  }
  writeFileSync(join(DIST, NOT_FOUND_FILE), pageHtml(template, pageHead(null), missing, stylesheet));
  rmSync(join(FRONTEND, "dist-prerender"), { recursive: true, force: true });
  const width = Math.max(...written.map((item) => item.path.length));
  console.log(`Pre-rendered ${written.length} website pages (dist/index.html stays the application shell),`);
  console.log(`their ${classes.size} inline styles in dist${stylesheet} (${(css.length / 1024).toFixed(1)} kB),`);
  console.log(`and the "Page not found" page as dist/${NOT_FOUND_FILE}:`);
  for (const item of written)
    console.log(
      `  ${item.path.padEnd(width)}  dist/${item.file}  ${(item.bytes / 1024).toFixed(1)} kB  ${item.words} words`,
    );
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  main().catch((error) => {
    console.error(`prerender: ${error.message}`);
    process.exit(1);
  });
}
