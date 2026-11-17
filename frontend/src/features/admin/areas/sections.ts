// The sections of the platform administrator's areas. Each section shows its own real data; capabilities without
// a backend yet are not shown (see docs/architecture/MDARIX_PLATFORM_ADMIN_CONSOLE.md).

export const DATA_SECTIONS = [
  "Data model",
  "Mappings",
  "Releases",
  "Rules & reference data",
  "Customer configuration",
] as const;
export const PLANS_SECTIONS = ["Plans", "Subscriptions", "Renewals", "Reminders"] as const;
/** Trial organizations: every free-trial link in one place, and only those (TO-1). */
export const TRIAL_ORGANIZATIONS = "Trial organizations";
export const TRIAL_SECTIONS = ["Requests", "Trials", "Ending and deletion", "Feedback"] as const;
export const IDENTITY_SECTIONS = [
  "Platform users",
  "Customer administrators",
  "Customer users",
  "Roles & permissions",
  "Effective access",
] as const;
export const INTEGRATION_SECTIONS = [
  "Connector catalog",
  "Runs & failures",
  "Reconciliation",
  "Credentials",
  "Source schemas",
] as const;

/**
 * Data & Integrations: everything needed to bring a customer's data into MDARIX, in the order it is done. Define what
 * MDARIX keeps, connect the customer's systems, map their fields, release the configuration, then run and check it.
 * (It brings together the former Data & Configuration and Integrations areas; each screen is unchanged.)
 */
export const DATA_AND_INTEGRATIONS = "Data & Integrations";
export const DATA_INTEGRATION_STAGES = [
  { stage: "Define", sections: ["Data model", "Rules & reference data"] },
  { stage: "Connect", sections: ["Connector catalog", "Source schemas", "Credentials"] },
  { stage: "Map", sections: ["Mappings", "Customer configuration"] },
  { stage: "Release", sections: ["Releases"] },
  { stage: "Run", sections: ["Runs & failures", "Reconciliation"] },
] as const;
export const DATA_INTEGRATION_SECTIONS = [
  "Data model",
  "Rules & reference data",
  "Connector catalog",
  "Source schemas",
  "Credentials",
  "Mappings",
  "Customer configuration",
  "Releases",
  "Runs & failures",
  "Reconciliation",
] as const;

/** What each step of Data & Integrations is for, in one line. */
export const DATA_INTEGRATION_GUIDE: Record<string, string> = {
  "Data model": "The records MDARIX keeps (products, complaints, investigations…) and their fields.",
  "Rules & reference data": "The controlled values, transformations and checks that mappings use.",
  "Connector catalog": "The source systems a customer can connect (QMS, ERP, PLM…) and their connector versions.",
  "Source schemas": "The records and fields each source system offers, ready to be mapped.",
  Credentials: "Connection secrets for the platform's own connections, held in the secret store.",
  Mappings: "Which source field fills which MDARIX field; new mappings start as drafts.",
  "Customer configuration": "One tenant's products, connections and the mapping versions it uses.",
  Releases: "Approve mappings and publish them; a released version can be rolled back.",
  "Runs & failures": "Every integration run across tenants, and what failed.",
  Reconciliation: "After each run, the records kept are checked against the source system.",
};

/** The stage a Data & Integrations step belongs to, with its position (1-based) among all steps. */
export const dataIntegrationStep = (section: string) => {
  const index = (DATA_INTEGRATION_SECTIONS as readonly string[]).indexOf(section);
  if (index < 0) return null;
  const stage = DATA_INTEGRATION_STAGES.find((item) => (item.sections as readonly string[]).includes(section));
  return { number: index + 1, total: DATA_INTEGRATION_SECTIONS.length, stage: stage?.stage ?? "" };
};
export const AI_SECTIONS = ["Overview", "Governance", "Evaluations", "AI runs", "Agents & guardrails"] as const;
export const SECURITY_SECTIONS = ["Overview", "Audit trail", "Support access", "Retention"] as const;
export const OPERATIONS_SECTIONS = [
  "System health",
  "Queues & jobs",
  "Email & notifications",
  // Problems people report from the help menu (FUN-07, 0.10.37).
  "Problem reports",
  "Tenant cells",
  "Developer API",
] as const;

/**
 * What each section of the other areas is for, in one line, shown under the area's header. Data & Integrations is
 * explained by its own step guide (DATA_INTEGRATION_GUIDE).
 */
export const SECTION_GUIDE: Record<string, Record<string, string>> = {
  "Customers & Tenants": {
    Customers: "Every customer organization and its status. Open one to see its tenants and administrators.",
    Tenants: "Each customer's separate workspaces: their plan, administrators, sign-in, AI use and data.",
  },
  [TRIAL_ORGANIZATIONS]: {
    Requests:
      "Free-trial requests to approve or decline, and the pilot and one-to-one demo requests made from free trials.",
    Trials: "Every free trial: days left, usage and progress. Open one to extend, end, convert or delete its data.",
    "Ending and deletion": "Requests to end a trial early, trials due for deletion, and the deletion run.",
    Feedback: "What trial users told us about MDARIX, and the quotes that may appear on the website.",
  },
  "Plans & Licensing": {
    Plans: "The plans a tenant can be on, with the features and limits each one includes.",
    Subscriptions: "Which plan each tenant is on and its license period; change the plan or its limits here.",
    Renewals: "Licenses by when they end, so renewals are handled before access stops.",
    Reminders: "When renewal reminder emails are sent, and what they say.",
  },
  "Identity & Access": {
    "Platform users": "MDARIX staff who administer the platform.",
    "Customer administrators": "The people who manage each customer's own users.",
    "Customer users": "Everyone else with an account in a customer's tenant (read-only here).",
    "Roles & permissions": "What each role is allowed to do.",
    "Effective access": "Everything one person can do, and why.",
  },
  "AI Control Center": {
    Overview: "Which AI model is in use, how often it ran in the last 30 days and how fast it answers.",
    Governance: "Approved providers, and each organization's AI outputs and reviews, with sample answers apart.",
    Evaluations: "Test results that show the AI gives the expected answers before a release.",
    "AI runs": "Every recent AI run: for which tenant, with which model, and how it went.",
    "Agents & guardrails": "The AI assistants in MDARIX and the safety limits they work within.",
  },
  Security: {
    Overview: "How each tenant's data is kept separate and protected.",
    "Audit trail": "Every recorded change across tenants: who did what, when and why.",
    "Support access": "Time-limited access that lets our support team look into a customer's tenant.",
    Retention: "How long audit records are kept, and the earliest date any may be deleted.",
  },
  Operations: {
    "System health": "Whether the platform's services are up and the background worker is running.",
    "Queues & jobs": "Work waiting in the background, work that gave up after retries, and customer setup jobs.",
    "Email & notifications": "Whether the platform can send email, and the renewal reminders waiting to go out.",
    "Problem reports":
      "Problems people reported from the help menu: answer the reporter by email, then close the report.",
    "Tenant cells": "Each customer's own MDARIX, as its heartbeats describe it: health, versions, jobs and packages.",
    "Developer API": "For developers: what other systems can ask MDARIX to do. Not needed to run the platform.",
  },
};

/** Requests' purpose while the website offers demo requests (app/featureSet.ts websiteDemoRequestsOffered). */
const REQUESTS_WITH_WEBSITE_DEMOS = "Demo and trial requests from prospective customers.";

/** The one-line purpose of a section, or "" when the area explains itself another way. Requests names the website's
 * demo requests only while the website offers them (`websiteDemos`). */
export const sectionGuide = (area: string, section: string, websiteDemos = false) =>
  websiteDemos && area === TRIAL_ORGANIZATIONS && section === "Requests"
    ? REQUESTS_WITH_WEBSITE_DEMOS
    : (SECTION_GUIDE[area]?.[section] ?? "");

/** Words the header search also finds a section by (what can be done there, not only its name). */
export const SECTION_KEYWORDS: Record<string, string> = {
  [`${TRIAL_ORGANIZATIONS}:Trials`]: "trial extend convert end early support access pilot",
  [`${TRIAL_ORGANIZATIONS}:Requests`]: "trial approve decline onboarding demo",
  [`${TRIAL_ORGANIZATIONS}:Ending and deletion`]: "trial end early delete purge retention",
};

/**
 * Sections that moved to another area: "Area:Section" (or a bare section name) and where it opens now. Old links and
 * bookmarks keep working.
 */
export const MOVED_SECTIONS: Record<string, { domain: string; item: string }> = {
  "Customers & Tenants:Trials": { domain: TRIAL_ORGANIZATIONS, item: "Trials" },
  "Customers & Tenants:Feedback": { domain: TRIAL_ORGANIZATIONS, item: "Feedback" },
  "Identity & Access:Onboarding": { domain: TRIAL_ORGANIZATIONS, item: "Requests" },
  Trials: { domain: TRIAL_ORGANIZATIONS, item: "Trials" },
  Feedback: { domain: TRIAL_ORGANIZATIONS, item: "Feedback" },
  Onboarding: { domain: TRIAL_ORGANIZATIONS, item: "Requests" },
};

/** Where an "Area:Section" (or a bare section name) opens now, following MOVED_SECTIONS; else unchanged. */
export const movedTarget = (domain: string, item?: string): { domain: string; item?: string } =>
  MOVED_SECTIONS[item ? `${domain}:${item}` : domain] ?? { domain, item };

/** Whether the header search `term` (lower case) finds this section: its area, purpose, name or keywords. */
export const sectionMatches = (term: string, domain: string, description: string, item: string) =>
  `${domain} ${description} ${item} ${SECTION_KEYWORDS[`${domain}:${item}`] ?? ""}`.toLowerCase().includes(term);

/** Area name -> its sections, for the areas this folder renders. */
export const AREA_SECTIONS: Record<string, readonly string[]> = {
  "Plans & Licensing": PLANS_SECTIONS,
  [DATA_AND_INTEGRATIONS]: DATA_INTEGRATION_SECTIONS,
  "Identity & Access": IDENTITY_SECTIONS,
  "AI Control Center": AI_SECTIONS,
  Security: SECURITY_SECTIONS,
  Operations: OPERATIONS_SECTIONS,
};

/** Former area names (bookmarks, links from other screens) and the area that replaced them. */
export const DOMAIN_ALIASES: Record<string, string> = {
  "Data & Configuration": DATA_AND_INTEGRATIONS,
  Integrations: DATA_AND_INTEGRATIONS,
};

/** Where an old bookmark or link lands in the new structure. */
export const LEGACY_SECTIONS: Record<string, string> = {
  // Data & Configuration
  "Configuration 360": "Mappings",
  "Mapping 360": "Mappings",
  "Configuration Release 360": "Releases",
  "Customer Configuration 360": "Customer configuration",
  "Canonical Object 360": "Data model",
  "Schema 360": "Data model",
  "Canonical data model": "Data model",
  "Transformation library": "Rules & reference data",
  "Reference data": "Rules & reference data",
  "Validation rules": "Rules & reference data",
  "Configuration sets": "Mappings",
  "Customer baselines": "Customer configuration",
  "Customer overrides": "Customer configuration",
  "Customer baselines & overrides": "Customer configuration",
  "Change requests": "Releases",
  "Dependencies & impact": "Releases",
  Deployments: "Releases",
  "Import / Export": "Mappings",
  "Configuration health": "Mappings",
  "Upgrade center": "Customer configuration",
  "Master data": "Customer configuration",
  "Data mapping": "Mappings",
  "Validation & data quality": "Mappings",
  "Mapping versions": "Mappings",
  "Configuration releases": "Releases",
  Entitlements: "Plans",
  Expirations: "Renewals",
  "Reminder rules": "Reminders",
  "Platform roles": "Roles & permissions",
  "Permission sets": "Roles & permissions",
  "Effective Permissions": "Effective access",
  "Customer integrations": "Connector catalog",
  "Integration registry": "Connector catalog",
  "Integration runs": "Runs & failures",
  "Failures & logs": "Runs & failures",
  "Integration health": "Runs & failures",
  "Schema registry": "Source schemas",
  "API & contract registry": "Source schemas",
  "API & schemas": "Source schemas",
  "AI overview": "Overview",
  "Models & versions": "Overview",
  "Golden Evaluation": "Evaluations",
  "Trust & Assurance": "Evaluations",
  "Release Assurance": "Evaluations",
  "AI executions": "AI runs",
  Executions: "AI runs",
  Agents: "Agents & guardrails",
  Guardrails: "Agents & guardrails",
  "Security overview": "Overview",
  "Tenant isolation": "Overview",
  "Encryption & residency": "Overview",
  "Security events": "Audit trail",
  "Jobs & queues": "Queues & jobs",
  Notifications: "Email & notifications",
  "Email templates": "Email & notifications",
  "Developer & API": "Developer API",
};

/** A reminder template rendered with sample values, as the recipient would read it. */
export const previewTemplate = (text: string, sample: Record<string, string>) =>
  text.replace(/\{\{\s*([a-z_]+)\s*\}\}/g, (match, name: string) => sample[name] ?? match);

/** The merge variables a template uses, so only those are declared to the server. */
export const templateVariables = (text: string) => [
  ...new Set([...text.matchAll(/\{\{\s*([a-z_]+)\s*\}\}/g)].map((match) => match[1])),
];

/** Thresholds typed as "90, 45, 14" -> [90, 45, 14] (unique, descending), or an error. */
export const parseThresholds = (text: string): { days: number[]; error?: string } => {
  const parts = text
    .split(/[,\s]+/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (!parts.length) return { days: [], error: "Enter at least one number of days." };
  const days = parts.map(Number);
  if (days.some((value) => !Number.isInteger(value) || value < 0 || value > 365))
    return { days: [], error: "Use whole numbers of days between 0 and 365." };
  return { days: [...new Set(days)].sort((a, b) => b - a) };
};
