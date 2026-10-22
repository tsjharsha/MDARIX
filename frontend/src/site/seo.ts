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
      "Medical device complaint handling, FDA and EU MDR reporting clocks, trend signals, investigations and CAPA in one traceable place. Free 30-day trial.",
  },
  "/platform": {
    title: "Platform: Product 360, investigations and signed decisions · MDARIX",
    description:
      "Link every complaint to its product, version, lot, component and supplier, weigh evidence and hypotheses, and sign decisions with a full audit trail.",
  },
  "/platform/product-360": {
    title: "Product 360: the product, version and lot behind every complaint · MDARIX",
    description:
      "How MDARIX ties each medical device complaint to its product, version, lot, component and supplier, and what the free trial offers today.",
  },
  "/platform/investigations": {
    title: "Complaint investigations with evidence and hypotheses · MDARIX",
    description:
      "Investigate medical device complaints in one case: evidence, competing hypotheses and open questions side by side, and Ask MDARIX on your records.",
  },
  "/platform/decisions": {
    title: "Investigation decisions, briefs and failure chains · MDARIX",
    description:
      "Failure chains, a versioned decision brief and a decision signed with password and authenticator code, with open questions carried into it.",
  },
  "/platform/trust": {
    title: "Human review, audit trail and AI safeguards · MDARIX",
    description:
      "Signed human review, an append-only audit trail and customer administration today. AI assurance comes in a pilot; AI is off in the trial.",
  },
  "/roadmap": {
    title: "Roadmap: available today, in a pilot, planned · MDARIX",
    description:
      "What every MDARIX workspace and the free trial can use today, what comes in a pilot, and what is planned, such as single sign-on.",
  },
  "/solutions": {
    title: "Solutions for medical device quality and regulatory teams · MDARIX",
    description:
      "For quality leaders, investigators, regulatory affairs and supplier quality: complaint backlogs, reportability decisions, trend signals and CAPA follow-through.",
  },
  "/product-lifecycle": {
    title: "Medical device lifecycle, design controls and post-market feedback · MDARIX",
    description:
      "How design-control records, the risk file and field complaints connect from concept to post-market surveillance, and how MDARIX traces a field problem back.",
  },
  "/trust": {
    title: "Trust: human decisions, audit trails and validated AI · MDARIX",
    description:
      "Investigation decisions signed by people, an audit trail, authenticator MFA, isolated customer data, and AI that cites evidence and stays off until validated.",
  },
  "/trust/regulations": {
    title: "FDA, EU MDR, UK and Canada reporting and MedTech standards · MDARIX",
    description:
      "MDR reporting windows, ISO 13485, QMSR, ISO 14971, IEC 62304 and Part 11: the evidence MDARIX organizes. MDARIX does not certify compliance.",
  },
  "/resources": {
    title: "Resources on complaint handling and post-market surveillance · MDARIX",
    description:
      "Guides and step-by-step videos on medical device complaint handling, MDR reportability, signal detection, investigations and CAPA effectiveness.",
  },
  "/company": {
    title: "About MDARIX",
    description:
      "MDARIX builds post-market intelligence for medical device makers: complaints, product context, evidence and human review in one traceable place.",
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
      "Yes: a free 30-day trial for up to 3 users and 5,000 uploaded rows, sample data first, then your own complaint exports. No demo call, no credit card.",
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
      "The terms of the MDARIX 30-day free trial: up to 3 users and 5,000 uploaded rows, no credit card, and what happens to your data when it ends.",
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
      "Try MDARIX free for 30 days with up to 3 users: sample data on day one, then your own complaint exports. No credit card.",
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
