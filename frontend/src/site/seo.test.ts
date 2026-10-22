import { describe, expect, it } from "vitest";
import robotsFile from "../../public/robots.txt?raw";
import sitemap from "../../public/sitemap.xml?raw";
import indexHtml from "../../index.html?raw";
import { INDEXED_PATHS, PAGE_META, SITE_URL } from "./seo";
import { SITE_PAGES } from "./pages";

// A Windows checkout may turn the file's line endings into CRLF; the rules are the same.
const robots = robotsFile.replace(/\r\n/g, "\n");

describe("what search engines read", () => {
  it("gives every website page its own title and a description short enough to show in full", () => {
    for (const page of SITE_PAGES) expect(PAGE_META[page], page).toBeDefined();
    const titles = new Set<string>();
    for (const [path, meta] of Object.entries(PAGE_META)) {
      expect(meta.description.length, path).toBeLessThanOrEqual(160);
      expect(meta.description.length, path).toBeGreaterThan(40);
      expect(meta.title, path).toContain("MDARIX");
      titles.add(meta.title);
    }
    expect(titles.size).toBe(Object.keys(PAGE_META).length);
    // The words medical-device quality teams search with.
    const home = `${PAGE_META["/"].title} ${PAGE_META["/"].description}`;
    for (const words of ["complaint handling", "post-market surveillance", "medical device", "CAPA", "MDR"])
      expect(home.toLowerCase()).toContain(words.toLowerCase());
  });

  it("lists exactly the indexable pages in the sitemap", () => {
    const listed = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
    expect(listed).toEqual(INDEXED_PATHS.map((path) => `${SITE_URL}${path}`));
  });

  it("opens the website to crawlers and keeps sign-in, the application and the API out", () => {
    expect(robots).toContain("Allow: /");
    for (const path of ["/app", "/platform-admin", "/api/", "/signin", "/reset-password"])
      expect(robots).toContain(`Disallow: ${path}\n`);
    expect(robots).not.toContain("Disallow: /signup");
    expect(robots).toContain(`Sitemap: ${SITE_URL}/sitemap.xml`);
  });

  it("names mdarix.com as the website's one address, never the former mdarix.in (0.10.46)", () => {
    expect(SITE_URL).toBe("https://mdarix.com");
    // mdarix.in only redirects to mdarix.com now; its email addresses (support@, privacy@) stay as they are.
    for (const [name, text] of Object.entries({ robots, sitemap, indexHtml }))
      expect(text, name).not.toMatch(/(https?:\/\/|www\.)mdarix\.in\b/);
  });

  it("describes the organization for link previews and search without a person's name or address", () => {
    expect(indexHtml).toContain('property="og:image" content="https://mdarix.com/og-image.png"');
    expect(indexHtml).toContain('"@type": "Organization"');
    // The static page never claims a canonical address: each page sets its own (seo.ts).
    expect(indexHtml).not.toContain('rel="canonical"');
    const everything = `${indexHtml} ${JSON.stringify(PAGE_META)}`;
    expect(everything).not.toMatch(/Telikicherla|Srinivas|address"|streetAddress/i);
  });
});
