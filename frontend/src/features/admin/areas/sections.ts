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
export const IDENTITY_SECTIONS = ["Platform users", "Roles & permissions", "Effective access"] as const;
export const INTEGRATION_SECTIONS = [
  "Connector catalog",
  "Runs & failures",
  "Reconciliation",
  "Credentials",
  "API & schemas",
] as const;
export const AI_SECTIONS = ["Overview", "Evaluations", "Executions", "Agents & guardrails"] as const;
export const SECURITY_SECTIONS = ["Overview", "Audit trail", "Support access", "Retention"] as const;
export const OPERATIONS_SECTIONS = [
  "System health",
  "Queues & jobs",
  "Email & notifications",
  "Developer API",
] as const;

/** Area name -> its sections, for the areas this folder renders. */
export const AREA_SECTIONS: Record<string, readonly string[]> = {
  "Plans & Licensing": PLANS_SECTIONS,
  "Data & Configuration": DATA_SECTIONS,
  "Identity & Access": IDENTITY_SECTIONS,
  Integrations: INTEGRATION_SECTIONS,
  "AI Control Center": AI_SECTIONS,
  Security: SECURITY_SECTIONS,
  Operations: OPERATIONS_SECTIONS,
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
  "Schema registry": "API & schemas",
  "API & contract registry": "API & schemas",
  "AI overview": "Overview",
  "Models & versions": "Overview",
  "Golden Evaluation": "Evaluations",
  "Trust & Assurance": "Evaluations",
  "Release Assurance": "Evaluations",
  "AI executions": "Executions",
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
