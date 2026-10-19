// What search engines and link previews read about each public page: a title and a description in the words people
// search with (complaint handling, post-market surveillance, MDR reportability, CAPA), the page's one canonical
// address, and whether it may be indexed. public/sitemap.xml lists the same indexable pages (seo.test.ts checks it).
// Keep every description true to what the product does today, under 160 characters, and free of personal names.

export const SITE_URL = "https://mdarix.in";
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
      "Signed human review, an append-only audit trail and customer administration today. AI assurance comes with design partners; AI is off in the trial.",
  },
  "/roadmap": {
    title: "Roadmap: available today, with design partners, planned · MDARIX",
    description:
      "What every MDARIX workspace and the free trial can use today, what is built with design partners, and what is planned, such as single sign-on.",
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
  description: "This page does not exist. The MDARIX website starts at mdarix.in.",
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

/** Title, description, canonical address, link-preview tags and indexing rule for a website page. ``null`` is the
 * "not found" page: never indexed, no canonical address. */
export function applyPageMeta(path: IndexedPath | null) {
  const meta = path ? PAGE_META[path] : NOT_FOUND;
  const url = path ? `${SITE_URL}${path === "/" ? "/" : path}` : null;
  document.title = meta.title;
  setMeta("name", "description", meta.description);
  setMeta("name", "robots", path ? "index, follow" : "noindex, follow");
  setCanonical(url);
  setMeta("property", "og:title", meta.title);
  setMeta("property", "og:description", meta.description);
  if (url) setMeta("property", "og:url", url);
}

/** Sign-in, account and application screens: kept out of search results. */
export function applyPrivatePageMeta(title?: string) {
  if (title) document.title = title;
  setMeta("name", "robots", "noindex, nofollow");
  setCanonical(null);
}
