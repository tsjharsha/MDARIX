// What search engines and link previews read about each public page: a title and a description in the words people
// search with (complaint handling, post-market surveillance, MDR reportability, CAPA), the page's one canonical
// address, and whether it may be indexed. public/sitemap.xml lists the same indexable pages (seo.test.ts checks it).
// Keep every description true to what the product does today, under 160 characters, and free of personal names.
// The same tags are written into each page's own HTML file at build time (scripts/prerender.mjs, pageHead below), so
// crawlers and link previews that run no JavaScript read them too (WEB-05); the browser keeps them up to date.

export const SITE_URL = "https://mdarix.com";
export const SHARE_IMAGE = `${SITE_URL}/og-image.png`;

export type PageMeta = { title: string; description: string };

export const PAGE_META = {
  "/": {
    title: "MDARIX · Post-market surveillance and complaint handling for medical devices",
    description:
      "Medical device complaint handling to a signed decision and the right MDR report in every market, with product, evidence and CAPA linked. Free 30-day trial.",
  },
  "/platform": {
    title: "How MDARIX works: cases, investigations, products and reports · MDARIX",
    description:
      "Five places, one product story: Today, Cases, Investigations, Products, and Decisions & Reports. What is in the free trial, in a pilot and planned.",
  },
  "/trust": {
    title: "Trust: human decisions, audit trail, AI and regulations · MDARIX",
    description:
      "Decisions signed by people, an audit trail, authenticator MFA, isolated customer data, AI that only proposes, and reporting for the US, EU, GB, Canada, India.",
  },
  "/company": {
    title: "About MDARIX and how to start",
    description:
      "MDARIX is built for small and mid-size medical device makers and exporters. Start with a free trial, then a pilot on your real data.",
  },
  "/videos": {
    title: "Free trial videos: from first complaint to signed CAPA · MDARIX",
    description:
      "Fourteen short videos that walk a medical device quality team through the MDARIX free trial, from the first complaint to a signed CAPA decision.",
  },
  "/questions": {
    title: "Questions and answers on complaint trending and reportability · MDARIX",
    description:
      "Direct answers on trending medical device complaints, MDR reportability, the ISO 14971 risk file and CAPA effectiveness, and what MDARIX does about each.",
  },
  "/questions/how-to-trend-medical-device-complaints": {
    title: "How do I trend medical device complaints? · MDARIX",
    description:
      "Count clusters, compare each product version's complaint rate with its own history and use units in the field as the denominator. How MDARIX does it.",
  },
  "/questions/when-is-a-complaint-reportable": {
    title: "When does a complaint become a reportable event? · MDARIX",
    description:
      "21 CFR Part 803 and EU MDR Article 87 in brief: what is reportable, the reporting windows from the day of awareness, and who decides.",
  },
  "/questions/post-market-data-and-the-risk-file": {
    title: "How should post-market data feed the risk file? · MDARIX",
    description:
      "ISO 14971:2019 clause 10 in brief: review post-market information for safety, review the risk file where it matters, and record every risk review.",
  },
  "/questions/complaint-signal-vs-trend": {
    title: "What is the difference between a complaint signal and a trend? · MDARIX",
    description:
      "A trend measures how a complaint rate changes against its history; a signal is an observation a person triages. Neither is a conclusion about cause.",
  },
  "/questions/show-capa-effectiveness": {
    title: "How do I show a CAPA was effective? · MDARIX",
    description:
      "Set the criteria before the action, measure complaint recurrence from the right date, and sign the result. What ISO 13485 asks and what MDARIX does.",
  },
  "/questions/try-complaint-trending-on-your-own-data": {
    title: "Can I try complaint trending on my own data without a demo call? · MDARIX",
    description:
      "Yes: a free 30-day trial for up to 50 people and 5,000 uploaded rows, sample data first, then your own complaint exports. No demo call, no credit card.",
  },
  "/questions/does-mdarix-replace-our-qms": {
    title: "Does MDARIX replace our QMS or complaint software? · MDARIX",
    description:
      "No. MDARIX works beside your QMS or complaint software. Your QMS keeps the complaint record, CAPA and change control.",
  },
  "/privacy": {
    title: "Privacy policy · MDARIX",
    description:
      "How MDARIX collects, uses and protects personal data, including your rights under India's Digital Personal Data Protection Act, 2023.",
  },
  "/terms": {
    title: "Terms of service · MDARIX",
    description: "The terms that govern use of the MDARIX website and service.",
  },
  "/trial-agreement": {
    title: "Free trial agreement · MDARIX",
    description:
      "The terms of the MDARIX 30-day free trial: up to 50 people and 5,000 uploaded rows, no credit card, and what happens to your data when it ends.",
  },
  "/security": {
    title: "Security · MDARIX",
    description: "How MDARIX protects customer data and accounts, and how to report a security issue.",
  },
  "/accessibility": {
    title: "Accessibility statement · MDARIX",
    description:
      "What MDARIX has done to make its website and application accessible, the gaps we know of, and how to report a problem.",
  },
  "/contact": {
    title: "Contact MDARIX",
    description: "Contact the MDARIX team about the free trial, a design-partner pilot or security.",
  },
  "/signup": {
    title: "Start your free 30-day trial · MDARIX",
    description:
      "Try MDARIX free for 30 days with up to 50 people: sample data on day one, then your own complaint exports. No credit card.",
  },
} satisfies Record<string, PageMeta>;

export type IndexedPath = keyof typeof PAGE_META;
export const INDEXED_PATHS = Object.keys(PAGE_META) as IndexedPath[];

const NOT_FOUND: PageMeta = {
  title: "Page not found · MDARIX",
  description: "This page does not exist. The MDARIX website starts at mdarix.com.",
};

function setMeta(attribute: "name" | "property", key: string, content: string) {
  let tag = document.head.querySelector<HTMLMetaElement>(`meta[${attribute}="${key}"]`);
  if (!tag) {
    tag = document.createElement("meta");
    tag.setAttribute(attribute, key);
    document.head.appendChild(tag);
  }
  tag.content = content;
}

function setCanonical(href: string | null) {
  let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!href) {
    link?.remove();
    return;
  }
  if (!link) {
    link = document.createElement("link");
    link.rel = "canonical";
    document.head.appendChild(link);
  }
  link.href = href;
}

/** What a website page's head says: its title and description, the indexing rule, its canonical address and the
 * link-preview tags. ``url`` is null for the "not found" page, which is never indexed. */
export type PageHead = { title: string; description: string; robots: string; url: string | null };

/** The head of a website page (``null``: the "not found" page). One source for the browser (applyPageMeta) and for
 * the pre-rendered HTML files (scripts/prerender.mjs). */
export function pageHead(path: IndexedPath | null): PageHead {
  const meta = path ? PAGE_META[path] : NOT_FOUND;
  return {
    title: meta.title,
    description: meta.description,
    robots: path ? "index, follow" : "noindex, follow",
    url: path ? `${SITE_URL}${path === "/" ? "/" : path}` : null,
  };
}

/** Title, description, canonical address, link-preview tags and indexing rule for a website page. ``null`` is the
 * "not found" page: never indexed, no canonical address. */
export function applyPageMeta(path: IndexedPath | null) {
  const head = pageHead(path);
  document.title = head.title;
  setMeta("name", "description", head.description);
  setMeta("name", "robots", head.robots);
  setCanonical(head.url);
  setMeta("property", "og:title", head.title);
  setMeta("property", "og:description", head.description);
  if (head.url) setMeta("property", "og:url", head.url);
}

/** Sign-in, account and application screens: kept out of search results. */
export function applyPrivatePageMeta(title?: string) {
  if (title) document.title = title;
  setMeta("name", "robots", "noindex, nofollow");
  setCanonical(null);
}
