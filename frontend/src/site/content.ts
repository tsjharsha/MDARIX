// Structure and new copy for the consolidated 8-page MDARIX website.
// Existing copy lives verbatim in ./legacyContent.ts and is reused here, so nothing from the old site is lost.
import {
  capabilityCopy,
  capabilityStatus,
  evidenceCapability,
  investigationCapability,
  lifecycleContent,
  menus,
  platformCapabilityData,
  solutionHeroVisuals,
  solutionOverrides,
  anchorPages,
} from "./legacyContent";

export const img = (name: string) => `/site/${name}.webp`;

export type Capability = {
  slug: string;
  label: string;
  title: string;
  summary: string;
  cards: { title: string; text: string }[];
  steps: string[];
  image?: { src: string; alt: string };
};

/** Written for the capabilities that previously only had generated placeholder copy. */
const writtenCapabilities: Record<string, Omit<Capability, "slug" | "label" | "image">> = {
  hypotheses: {
    title: "Keep competing explanations side by side.",
    summary:
      "MDARIX organizes possible explanations for a signal as separate hypotheses, each with the evidence that supports it, the evidence that contradicts it, its assumptions and its gaps, so a plausible story is never mistaken for proof.",
    cards: [
      {
        title: "More than one explanation",
        text: "Capture each candidate explanation on its own instead of letting the first plausible story become the default.",
      },
      {
        title: "Evidence on both sides",
        text: "List supporting, contradicting and contextual evidence for every hypothesis, each linked to its source record.",
      },
      {
        title: "Assumptions in the open",
        text: "Write down what each hypothesis assumes, so reviewers can test the assumption rather than the conclusion.",
      },
      {
        title: "Status, not verdict",
        text: "Hypotheses carry a review status. MDARIX does not declare a root cause; authorized people decide what is accepted.",
      },
    ],
    steps: ["Trend", "Hypotheses", "Support", "Contradict", "Unknowns", "Review"],
  },
  unknowns: {
    title: "See what the investigation still cannot establish.",
    summary:
      "The Unknowns Radar lists what is missing before anyone decides: incomplete traceability, missing lot references, unavailable sources, stale records and unsupported links, each with the evidence that would close it.",
    cards: [
      {
        title: "Missing evidence, named",
        text: "Show which records, tests or source systems the investigation has not yet seen, instead of silently ignoring them.",
      },
      {
        title: "Broken traceability",
        text: "Flag complaints without lot references, components without supplier links and changes without effective dates.",
      },
      {
        title: "What would close the gap",
        text: "Pair each unknown with the evidence or request that would resolve it, so the next step is obvious.",
      },
      {
        title: "Carried into the decision",
        text: "Open unknowns stay visible in the decision context, so nobody signs off without seeing what is still uncertain.",
      },
    ],
    steps: ["Scope", "Expected evidence", "Found", "Missing", "Request", "Review"],
  },
  "failure-chain": {
    title: "Trace a possible failure path, link by link.",
    summary:
      "Failure-chain intelligence lays out a candidate path from component or change, through mechanism and failure mode, to the observed effect, and marks every link as supported, contradicted or not yet evidenced.",
    cards: [
      {
        title: "Explicit links",
        text: "Break a suspected failure into component, mechanism, failure mode and effect, so each step can be examined on its own.",
      },
      {
        title: "Evidence per link",
        text: "Attach the records that support or contradict each link. A chain is only as strong as its weakest evidenced step.",
      },
      {
        title: "Incomplete chains stay incomplete",
        text: "Unsupported links are shown as gaps rather than filled in, and feed directly into the Unknowns Radar.",
      },
      {
        title: "Connected to risk",
        text: "Relate the chain to known hazards, failure modes and risk controls from the product risk file.",
      },
    ],
    steps: ["Component", "Mechanism", "Failure mode", "Effect", "Evidence", "Unknowns"],
  },
  counterfactual: {
    title: "Ask what would change if the facts were different.",
    summary:
      "Counterfactual analysis compares scenarios, such as excluding lots from one supplier or one site, to see whether the signal pattern would still hold. It sharpens scope and questions; it does not prove cause.",
    cards: [
      {
        title: "Scenario comparison",
        text: "Re-examine the signal with a version, supplier, lot range or time window removed, and compare the pattern side by side.",
      },
      {
        title: "Scope, not causality",
        text: "Use the result to focus the investigation and the scope assessment, never as a substitute for evidence of cause.",
      },
      {
        title: "Assumptions recorded",
        text: "Every scenario keeps its assumptions and data limitations with it, so reviewers can judge how far to rely on it.",
      },
    ],
    steps: ["Baseline", "Scenario", "Compare", "Limitations", "Review"],
  },
  "decision-center": {
    title: "Make the decision where all the evidence is.",
    summary:
      "The Decision Center brings readiness, findings, competing hypotheses, contradictions, unknowns and limitations into one place, separates the AI advisory from the human decision, and records the decision with a controlled signature.",
    cards: [
      {
        title: "Decision readiness",
        text: "See whether material unknowns, contradictions or missing evidence remain before choosing an action.",
      },
      {
        title: "Controlled options",
        text: "Choose from defined dispositions such as continue the investigation, request evidence or escalate, with a written rationale.",
      },
      {
        title: "AI advises, people decide",
        text: "An optional AI advisory is shown separately and cannot finalize a decision.",
      },
      {
        title: "Signature with accountability",
        text: "Approval requires approval authority for the person's role, re-authentication and a recorded meaning; nobody can approve their own decision.",
      },
    ],
    steps: ["Readiness", "Context", "Options", "Rationale", "Sign", "Record"],
  },
  "investigation-brief": {
    title: "Hand over the investigation as one reviewable brief.",
    summary:
      "The Investigation Brief assembles the question, product scope, timeline, evidence, hypotheses, unknowns and limitations into a versioned document that reviewers can read, challenge and approve.",
    cards: [
      {
        title: "Versioned and dated",
        text: "Every brief has a version, a time view and a review state, so you always know which picture someone approved.",
      },
      {
        title: "Provenance included",
        text: "Each statement keeps its source references, so a reader can go from the summary straight to the record.",
      },
      {
        title: "Limitations up front",
        text: "Known gaps and data limitations are part of the brief, not footnotes.",
      },
    ],
    steps: ["Question", "Scope", "Findings", "Unknowns", "Limitations", "Review"],
  },
  challenger: {
    title: capabilityCopy.challenger.title,
    summary: capabilityCopy.challenger.copy,
    cards: [
      {
        title: "Challenge the favorite",
        text: "Test the leading explanation against contradicting records and alternative explanations before it hardens into a conclusion.",
      },
      {
        title: "Name the weak assumption",
        text: "Point to the assumption a hypothesis depends on most, and what evidence would confirm or break it.",
      },
      {
        title: "Visible to reviewers",
        text: "Challenges stay attached to the hypothesis, so approvers see what was questioned and how it was answered.",
      },
    ],
    steps: ["Hypothesis", "Challenge", "Contradictions", "Alternatives", "Review"],
  },
  "ai-assurance": {
    title: capabilityCopy["ai-assurance"].title,
    summary: capabilityCopy["ai-assurance"].copy,
    cards: [
      {
        title: "Grounded or withheld",
        text: "AI statements must cite authorized evidence; when the evidence is thin, MDARIX holds back rather than guess.",
      },
      {
        title: "No causal overreach",
        text: "Guardrails stop unsupported root-cause claims and keep interpretation separate from observation.",
      },
      {
        title: "Tenant boundary enforced",
        text: "AI sees only the records the requesting person is authorized to see, within their organization.",
      },
      {
        title: "Measured, not asserted",
        text: "Evaluation against known scenarios shows how the AI performs, including where it should abstain.",
      },
    ],
    steps: ["Retrieve", "Ground", "Guardrails", "Evaluate", "Review"],
  },
  "ai-provenance": {
    title: capabilityCopy["ai-provenance"].title,
    summary: capabilityCopy["ai-provenance"].copy,
    cards: [
      {
        title: "Cited to the source",
        text: "Every AI-assisted statement links back to the evidence passages and records it was built from.",
      },
      {
        title: "Model and context recorded",
        text: "Keep which model, version and time view produced an output, alongside the inputs it was given.",
      },
      {
        title: "Inspectable later",
        text: "Reviewers and auditors can reconstruct where an interpretation came from long after it was produced.",
      },
    ],
    steps: ["Observation", "Source", "Model", "Output", "Review"],
  },
  "human-review": {
    title: capabilityCopy["human-review"].title,
    summary: capabilityCopy["human-review"].copy,
    cards: [
      {
        title: "Authority by role",
        text: "Only roles your organization grants approval authority can approve; read-only users cannot.",
      },
      {
        title: "Segregation of duties",
        text: "The author of a decision cannot approve it. Another authorized person must.",
      },
      {
        title: "Re-authentication and meaning",
        text: "Signing asks the person to confirm their identity and records what the signature means and which version it covers.",
      },
    ],
    steps: ["Evidence", "Review", "Authority", "Sign", "Record"],
  },
  "audit-trail": {
    title: capabilityCopy["audit-trail"].title,
    summary: capabilityCopy["audit-trail"].copy,
    cards: [
      {
        title: "Append-only history",
        text: "Administrative actions, decisions and signatures are recorded with who, when, what changed and why.",
      },
      {
        title: "Tamper evidence",
        text: "Audit events are chained so that changing a past record would be detectable.",
      },
      {
        title: "Ready to export",
        text: "Administrators can export the audit trail and an evidence package for review or inspection.",
      },
    ],
    steps: ["Action", "Actor", "Version", "Signature", "Export"],
  },
  "enterprise-administration": {
    title: capabilityCopy["enterprise-administration"].title,
    summary: capabilityCopy["enterprise-administration"].copy,
    cards: [
      {
        title: "Separate data per customer",
        text: "Every record carries its organization, the database enforces that boundary on every query (row-level security), and every request is scoped to the signed-in organization.",
      },
      {
        title: "Customer self-administration",
        text: "Customer administrators invite users, assign roles and review their own audit trail. Connections and field mappings are configured in a pilot.",
      },
      {
        title: "Identity and access",
        text: "Authenticator-app MFA, session limits and immediate sign-out on suspension. Single sign-on is planned.",
      },
      {
        title: "Plans and entitlements",
        text: "In a pilot: plans, seats and features are set centrally and visible to each customer.",
      },
    ],
    steps: ["Tenant", "Identity", "Access", "Integrations", "Assurance", "Operations"],
  },
};

const CAPABILITY_IMAGES: Record<string, [string, string]> = {
  "product-360": [
    "medtech-product-360-hero",
    "Product 360 view of a medical device with its versions, components and field signals",
  ],
  "reality-graph": [
    "medtech-product-reality-graph-hero",
    "Connected product reality graph linking components, suppliers, lots and evidence",
  ],
  "product-version": [
    "medtech-product-versioning",
    "Medical-device revisions compared side by side with their release context",
  ],
  timeline: ["medtech-timeline-intelligence", "Investigation timeline separating effective, recorded and known dates"],
  "ask-mdarix": ["medtech-ask-mdarix", "A quality engineer asking a scoped investigation question"],
  investigation: ["medtech-investigation-team", "Cross-functional MedTech team reviewing an investigation together"],
  evidence: ["medtech-evidence-intelligence-hero", "Evidence records connected with provenance and gaps"],
  hypotheses: [
    "medtech-hypotheses-hero",
    "Competing hypotheses compared against supporting and contradicting evidence",
  ],
  challenger: ["medtech-hero-challenger", "Investigation workspace comparing competing explanations against evidence"],
  unknowns: ["medtech-unknowns-hero", "Investigator reviewing missing evidence highlighted as open questions"],
  "failure-chain": ["medtech-failure-chain-hero", "Failure chain from component through mechanism to observed effect"],
  counterfactual: ["medtech-counterfactual-hero", "Scenario comparison of a signal with and without selected lots"],
  "decision-center": [
    "medtech-decision-center-hero",
    "Reviewer preparing a decision with the evidence package on the desk",
  ],
  "investigation-brief": ["medtech-investigation-brief-hero", "Investigation brief assembled for review"],
  "ai-assurance": [
    "medtech-hero-ai-assurance",
    "AI assurance workspace showing validation checkpoints and reviewer controls",
  ],
  "ai-provenance": [
    "medtech-hero-ai-provenance",
    "Evidence chain connecting device observations, source records and an AI insight",
  ],
  "human-review": ["medtech-hero-human-review", "Quality and regulatory reviewers examining evidence before approving"],
  "audit-trail": ["medtech-hero-audit-trail", "Audit timeline with version history and signed decision markers"],
  "enterprise-administration": [
    "medtech-hero-enterprise-administration",
    "Enterprise administration control room connecting tenants, identity, integrations and operations",
  ],
};

const slugOf = (href: string) => href.split("/").pop() ?? "";

function capabilityFor(slug: string, label: string): Capability {
  const image = CAPABILITY_IMAGES[slug]
    ? { src: img(CAPABILITY_IMAGES[slug][0]), alt: CAPABILITY_IMAGES[slug][1] }
    : undefined;
  const existing =
    slug === "investigation"
      ? investigationCapability
      : slug === "evidence"
        ? evidenceCapability
        : platformCapabilityData[slug];
  if (existing)
    return {
      slug,
      label,
      title: capabilityCopy[slug]?.title ?? existing.kicker.split("·").pop()?.trim() ?? label,
      summary: existing.summary,
      cards: existing.cards,
      steps: existing.steps,
      image,
    };
  const written = writtenCapabilities[slug];
  return { slug, label, ...written, image };
}

/** The website's three availability labels, the stages of the roadmap (capabilityStatus), in its order. */
export type Availability = "Available today" | "In a pilot" | "Planned";
export const AVAILABILITY: readonly Availability[] = ["Available today", "In a pilot", "Planned"];

/**
 * Where each Platform capability stands, from the roadmap (capabilityStatus) and the product as it runs: a free trial
 * always gets the MVP's screens (backend/app/feature_set.py, app/featureSet.ts), and what the MVP parks (the Products
 * screen, the Decision Center, counterfactuals, AI assurance) runs on the full product, in a pilot. AI is off during
 * the trial, so every AI capability is "Planned" (after evaluation). `note` says what the label means in the product today. Nothing
 * moves to "Available today" until it works in a trial workspace (WEB-14: the labels are the roadmap's three words).
 */
export const CAPABILITY_AVAILABILITY: Record<string, { status: Availability; note: string }> = {
  "product-360": {
    status: "In a pilot",
    note: "The Product 360 screen is not in the free trial: there, products, versions and lots are read through Readiness, Complaints and Signals. The screen itself is opened in a pilot.",
  },
  "reality-graph": {
    status: "In a pilot",
    note: "The connected graph is part of the Product 360 screen, opened in a pilot. In the free trial each complaint and case is linked to its product version and lot.",
  },
  "product-version": {
    status: "Available today",
    note: "Complaints, signals and trend checks are counted per product version, and every screen of a case works on the version you choose.",
  },
  timeline: {
    status: "Available today",
    note: "A case can be read as it is now, as it happened, or as it was known on a date you choose.",
  },
  "ask-mdarix": {
    status: "Available today",
    note: "AI is off during the trial: Ask MDARIX answers from your records by its rules and says so. Answers written by AI are planned, after evaluation.",
  },
  investigation: {
    status: "Available today",
    note: "Every case has one page: scope, evidence, analysis, reviews, the decision brief and the decision.",
  },
  evidence: {
    status: "Available today",
    note: "Evidence comes from the exports you import. Live connections to your systems are built in a pilot.",
  },
  hypotheses: {
    status: "Available today",
    note: "Hypotheses, contradictions and open questions are written and judged by hand in a case's Intelligence tab.",
  },
  challenger: {
    status: "Planned",
    note: "Planned, after evaluation. AI is off during the trial; the AI challenge of a hypothesis is switched on only once it is evaluated.",
  },
  unknowns: {
    status: "Available today",
    note: "A case's open questions and missing evidence, written by hand, stay visible up to the decision.",
  },
  "failure-chain": {
    status: "Available today",
    note: "Written by hand in a case's Intelligence tab. Ready-made chain templates are not in the free trial.",
  },
  counterfactual: {
    status: "In a pilot",
    note: "Not in the free trial. Scenario comparison comes in a pilot, once it is validated.",
  },
  "decision-center": {
    status: "Available today",
    note: "In the free trial this is a case's Decision step: readiness, the brief and the signed decision on one page.",
  },
  "investigation-brief": {
    status: "Available today",
    note: "A case's Decision Brief, versioned and reviewed before the decision is signed.",
  },
  "ai-assurance": {
    status: "Planned",
    note: "Planned, after evaluation. AI is off during the trial; its assurance checks are evaluated before AI is switched on.",
  },
  "ai-provenance": {
    status: "Planned",
    note: "Planned, after evaluation. AI is off during the trial; each AI output will record its sources and model once AI is switched on.",
  },
  "human-review": {
    status: "Available today",
    note: "Decisions are signed with your password and authenticator code, and whoever writes a brief never reviews or signs it.",
  },
  "audit-trail": {
    status: "Available today",
    note: "Records › Audit trail holds every action, decision and signature, ready to export.",
  },
  "enterprise-administration": {
    status: "Available today",
    note: "Users, MFA and your own audit trail today; in the free trial everyone has the same role. Workflow roles, customer administration, connections and field mappings come in a pilot; single sign-on is planned.",
  },
};

export const PLATFORM_PATHS = [
  "/platform/product-360",
  "/platform/investigations",
  "/platform/decisions",
  "/platform/trust",
] as const;
export type PlatformPath = (typeof PLATFORM_PATHS)[number];

/** The four Platform pages, one per group of the original Platform menu, each holding its capabilities as sections. */
const PLATFORM_PAGE_DEFS: Record<
  string,
  { path: PlatformPath; name: string; headline: string; copy: string; blurb: string }
> = {
  "Product Intelligence": {
    path: "/platform/product-360",
    name: "Product 360",
    headline: "Know the product, the version and the lot behind every complaint.",
    copy: "The device as it exists across versions, components, suppliers, lots and time, so an investigation starts from the right product record.",
    blurb: "Products, versions, lots and time",
  },
  "Investigation Intelligence": {
    path: "/platform/investigations",
    name: "Investigations",
    headline: "Investigate with the evidence, the explanations and the gaps side by side.",
    copy: "One governed case for each question: the evidence, competing hypotheses and what is still unknown stay visible, so a plausible story is never mistaken for proof.",
    blurb: "Evidence, hypotheses and open questions",
  },
  "Decision Intelligence": {
    path: "/platform/decisions",
    name: "Decisions",
    headline: "Decide where all the evidence is, and sign it.",
    copy: "Failure chains, the decision brief and the decision itself in one place, with what is still uncertain carried into the decision.",
    blurb: "Failure chains, briefs and signed decisions",
  },
  "Trust & Governance": {
    path: "/platform/trust",
    name: "Trust",
    headline: "People decide, every step is recorded, and AI stays off until it is validated.",
    copy: "Signed human review and a complete audit trail today; customer administration in a pilot; the AI safeguards are planned, after evaluation.",
    blurb: "Human review, audit trail and AI safeguards",
  },
};

/** The Platform pages: the four groups of the original Platform menu, in its order. */
export const platformGroups = menus.Platform.map((group) => ({
  ...PLATFORM_PAGE_DEFS[group.title],
  title: group.title,
  id: group.title.toLowerCase().replace(/[^a-z]+/g, "-"),
  capabilities: group.items.map((item) => ({
    ...capabilityFor(slugOf(item.href), item.label),
    availability: CAPABILITY_AVAILABILITY[slugOf(item.href)],
  })),
}));
export type PlatformGroup = (typeof platformGroups)[number];

/** The Platform page that holds a capability (by its slug), or that a former group anchor named. */
export function platformPageOf(slugOrGroup: string): PlatformGroup | undefined {
  return platformGroups.find(
    (group) => group.id === slugOrGroup || group.capabilities.some((capability) => capability.slug === slugOrGroup),
  );
}

export const productStructureTitles: Record<string, string> = {
  "product-360": "See the whole device in one place.",
  "reality-graph": "Map how everything about the product connects.",
  "product-version": "Know exactly which revision you are investigating.",
  timeline: "Separate what happened from what was known, and when.",
  "ask-mdarix": "Ask a precise question and get a cited, bounded answer.",
  investigation: "Run the investigation in one governed workspace.",
  evidence: "Bring scattered evidence into one authorized context.",
};

/** Solutions page: three ways in, each item with its image and both the long and short copy. */
const solutionGroupDefs: Array<{ title: string; id: string; keys: string[] }> = [
  {
    title: "By challenge",
    id: "challenges",
    keys: ["complaints", "changes", "affected", "supplier", "evidence", "challenge", "unknowns"],
  },
  {
    title: "By role",
    id: "roles",
    keys: [
      "quality-leaders",
      "investigators",
      "regulatory",
      "product",
      "supplier-quality",
      "manufacturing",
      "executives",
    ],
  },
  {
    title: "By investigation",
    id: "investigations",
    keys: [
      "complaint-investigation",
      "version-investigation",
      "change-investigation",
      "supplier-investigation",
      "component-investigation",
      "lot-investigation",
      "risk-investigation",
      "cross-system",
    ],
  },
];

const menuLabel = (key: string) =>
  menus.Solutions.flatMap((group) => group.items).find((item) => item.href.endsWith(`#${key}`))?.label ?? key;

export const solutionGroups = solutionGroupDefs.map((group) => ({
  ...group,
  items: group.keys.map((key) => {
    const main = solutionOverrides[key] ?? anchorPages[key];
    const short = anchorPages[key];
    const visual = solutionHeroVisuals[key];
    return {
      key,
      label: menuLabel(key),
      eyebrow: main.eyebrow.replace(/^Solution\s*[·-]\s*/, "").replace(/^Role\s*·\s*/, ""),
      title: main.title,
      copy: main.copy,
      short: short && short.copy !== main.copy ? short : undefined,
      image: visual ? { src: img(visual.src.replace(/^\/|\.png$/g, "")), alt: visual.alt } : undefined,
    };
  }),
}));

/** Lifecycle areas that are product direction, not available workflows (the old menu meant to badge these). */
export const FUTURE_LIFECYCLE = new Set([
  "strategy",
  "clinical-need",
  "requirements",
  "design",
  "design-controls",
  "verification",
  "clinical",
  "regulatory",
  "manufacturing",
  "recall",
  "monitoring",
  "retirement",
]);

/** Product lifecycle page: the four stages from the original menu, each item marked current or future. */
export const lifecycleStages = menus["Product Lifecycle"].map((group) => ({
  title: group.title,
  id: group.title.toLowerCase().replace(/[^a-z]+/g, "-"),
  items: group.items.map((item) => {
    const slug = item.href.includes("#") ? item.href.split("#").pop()! : slugOf(item.href);
    const future = FUTURE_LIFECYCLE.has(slug);
    const content = lifecycleContent[slug];
    // Current items link to where the capability is described; detailed lifecycle copy is on this page.
    const href = future
      ? undefined
      : item.href.startsWith("/solutions")
        ? item.href
        : content
          ? `/product-lifecycle#${slug}`
          : `${platformPageOf(slug)?.path ?? "/platform"}#${slug}`;
    return { slug, label: item.label, future, title: content?.title, copy: content?.copy, href };
  }),
}));

export { capabilityStatus };

/**
 * After the trial (Company page, below the free trial's steps): what follows a free trial, in the terms the trial
 * workspace's Next steps page uses (features/help/trialNextSteps.ts). Prices are never shown: they come in a written
 * proposal. It links to nothing inside the application.
 */
export const afterTheTrial = {
  eyebrow: "After the trial",
  title: "Then a pilot on your real data.",
  copy: "When the trial has shown how MDARIX works, the next step is a pilot: MDARIX working on your real complaints, connected to your own systems, run by your own team.",
  points: [
    [
      "Your real data only",
      "The pilot works on your own records from your complaint, QMS, PLM and ERP systems. There is no sample data in it.",
    ],
    [
      "A dedicated database, run by MDARIX",
      "Your pilot has a dedicated MDARIX transactional database, set up only for your organization and run by MDARIX. Your QMS keeps the complaint record, CAPA and change control. Free trials share the MDARIX platform, with each organization's records kept apart.",
    ],
    [
      "2 to 3 weeks of setup and validation",
      "Setup, configuration and validation testing take at least 2 to 3 weeks. The pilot starts once you have signed off the setup.",
    ],
    [
      "Paid, with a design-partner discount",
      "The pilot runs from 3 months to 1 year, priced for your scope and usage in a written proposal. Design partners receive a discount.",
    ],
  ] as const,
} as const;
