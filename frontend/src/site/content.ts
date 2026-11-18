// The website's words that more than one page (or the app's guides) use. Keep every sentence true to what the
// product does today, or say plainly that it comes in a pilot or is planned. No prices, no certification claims, no
// customer names, no figures that were not measured.

/** What the free trial gives a team, in the words of the trial agreement (legal/trial-agreement.md). */
export const trialIncludes: string[] = [
  "30 days, free, with no credit card",
  "Up to 50 people and 5,000 uploaded rows",
  "Sample data that tells the quality story in ten chapters",
  "Your own Excel or CSV exports, checked for problems and personal data before import",
  "Fourteen step-by-step videos",
  "AI on the trial's sample data only, with outputs labelled as AI proposals that a person reviews",
];

/** The five work areas of the product, in the order a complaint travels (the app's navigation). */
export const WORK_AREAS = [
  {
    id: "today",
    name: "Today",
    line: "Your queue, your deadlines and the one thing to do next.",
    points: [
      "Each person opens on their own part of the work: cases to log, triage, investigate, review or sign",
      "Legal clocks and overdue items first, with who owns each one",
      "Reminders before a deadline and a backup when someone is away",
    ],
  },
  {
    id: "cases",
    name: "Cases",
    line: "Intake, triage, contact with the reporter and reportability.",
    points: [
      "A call logged as it comes in, with a check of what it still needs",
      "Complaints closed as inquiries or “no fault found” brought back for a second look",
      "Routine complaints closed at service level with one signed disposition and a documented reason",
    ],
  },
  {
    id: "investigations",
    name: "Investigations",
    line: "Signal, evidence, possible causes, brief and decision, as one path.",
    points: [
      "Evidence for and against each possible cause, side by side",
      "Open questions stated, not hidden: a conclusion shows what supports it and what is still unknown",
      "A versioned investigation brief, written by one person and reviewed by another",
    ],
  },
  {
    id: "products",
    name: "Products",
    line: "The product behind every complaint: versions, components, suppliers, lots and markets.",
    points: [
      "The product version in the field on the event date, not today's version",
      "What changed between versions, such as a new supplier or a reduced inspection",
      "Lot impact: every lot that shares a suspect part, with units released, shipped and in stock",
    ],
  },
  {
    id: "decisions",
    name: "Decisions & Reports",
    line: "Approvals, reportability decision guides and authority reports.",
    points: [
      "A reportability assessment per market, each against its legal clock, with its reason kept",
      "Authority worksheets filled from your records, with what is missing marked",
      "Decisions signed with your password and authenticator code; nobody signs their own work",
    ],
  },
] as const;

/** Where each capability stands: in the free trial today, in a pilot, or planned. */
export const AVAILABILITY = [
  {
    label: "In the free trial today",
    note: "In every workspace. Start on sample data, then on your own exports. No integration and no credit card.",
    items: [
      "Products, versions and lots from your own exports",
      "Complaint signals: a count rule and a trend check per product version",
      "Investigations with evidence, possible causes and open questions",
      "Reportability per market, counted from the day you became aware",
      "Authority report forms filled from your records: FDA 3500A with its eMDR file, EU and GB MIR, Health Canada problem report, India MvPI",
      "Signed decisions, CAPA effectiveness checks and an inspector summary",
      "Lot impact for a confirmed signal",
      "Authenticator-app MFA and a complete audit trail",
    ],
  },
  {
    label: "In a pilot",
    note: "Built and validated with your team on your real data.",
    items: [
      "Live connections to your QMS, PLM, ERP and supplier systems",
      "Your fields mapped to the MDARIX model with governed templates",
      "Workflow roles with separation of duties and your own administrator",
      "A dedicated database for your organization",
    ],
  },
  {
    label: "Planned",
    note: "Not available yet. Design partners help decide what comes first.",
    items: [
      "AI on your own data, switched on only after it is evaluated with your team",
      "Single sign-on over OpenID Connect or SAML",
      "Ready-made connectors for named QMS, PLM and ERP products",
    ],
  },
] as const;

/** The markets whose reportability MDARIX assesses, with the legal basis from the standards catalog
 * (features/shared/standards.json, mirrored from backend/app/standards.py). */
export const MARKETS = [
  { region: "United States", name: "FDA medical device reporting", basis: ["CFR803_50", "CFR803_53"] },
  { region: "EU and Northern Ireland", name: "EU MDR vigilance", basis: ["MDR_87"] },
  { region: "Great Britain", name: "UK medical devices vigilance", basis: ["UK_MDR"] },
  { region: "Canada", name: "Mandatory problem reporting", basis: ["CA_MDR"] },
  { region: "India", name: "Adverse event reporting (MvPI worksheet)", basis: ["IN_MDR"] },
] as const;

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
