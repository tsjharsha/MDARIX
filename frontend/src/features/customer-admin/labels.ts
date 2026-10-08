/*
 * Plain-English words for the codes the server sends (statuses, types, actions), as the customer administrator
 * should read them. Presentation only: the codes themselves are still what is sent and compared. A code that is not
 * listed is made readable ("AUTHENTICATION_FAILED" becomes "Authentication failed"); a name is shown as it is.
 */

const WORDS: Record<string, string> = {
  // Lifecycle of roles, permission sets, rules, connections and mappings
  ACTIVE: "Active",
  DRAFT: "Draft",
  RETIRED: "Retired",
  SUPERSEDED: "Replaced",
  VALIDATION: "Being checked",
  READY_FOR_APPROVAL: "Waiting for approval",
  APPROVED: "Approved",
  RELEASED: "Released",
  PUBLISHED: "Published",
  ENABLED: "On",
  DISABLED: "Off",
  // People (customerAdminModel.userStatusLabel words the pending states for a person)
  INVITED: "Invited",
  SUSPENDED: "Suspended",
  LOCKED: "Locked",
  DEACTIVATED: "Deactivated",
  OFFBOARDED: "Offboarded",
  ERASED: "Personal data erased",
  // Runs, checks, exports
  QUEUED: "Waiting to start",
  RUNNING: "In progress",
  READY: "Ready",
  EXPIRED: "Expired",
  SUCCESS: "Succeeded",
  SUCCEEDED: "Succeeded",
  COMPLETE: "Completed",
  COMPLETED: "Completed",
  FAILED: "Failed",
  FAILURE: "Failed",
  ERROR: "Failed",
  PARTIAL: "Partly completed",
  HEALTHY: "Healthy",
  INVALID_CONFIGURATION: "Settings need attention",
  NOT_CONFIGURED: "Not set up",
  RECONCILED: "Counts match",
  MATCHED: "Counts match",
  MISMATCH: "Counts differ",
  PASS: "Passed",
  FAIL: "Failed",
  IMPORTED: "Imported",
  SENT: "Sent",
  VERIFIED: "Verified",
  // Single sign-on
  OIDC: "OpenID Connect",
  SAML: "SAML 2.0",
  SSO_MFA: "Single sign-on with MFA",
  SSO: "Single sign-on only",
  PASSWORD_MFA: "Password with MFA",
  // Field rules
  DIRECT: "Copied as is",
  // AI providers
  OPENAI: "OpenAI",
  AZURE_OPENAI: "Azure OpenAI",
  ANTHROPIC: "Anthropic",
  BEDROCK: "Amazon Bedrock",
};

/** Short forms that read badly once a code is put in sentence case ("Mfa", "Openai"). */
const ACRONYMS: Record<string, string> = {
  ai: "AI",
  api: "API",
  capa: "CAPA",
  csv: "CSV",
  erp: "ERP",
  id: "ID",
  idp: "identity provider",
  ip: "IP",
  json: "JSON",
  mdarix: "MDARIX",
  mfa: "MFA",
  oidc: "OpenID Connect",
  openai: "OpenAI",
  plm: "PLM",
  pms: "PMS",
  saml: "SAML",
  sod: "separation of duties",
  sso: "SSO",
  url: "URL",
};

const CODE_LIKE = /^[A-Za-z0-9]+([_.][A-Za-z0-9]+)*$/;

/** A code as words: the known wording, else the code in sentence case; a name (mixed case, spaces) as it is. */
export function readable(value: unknown, fallback = "—"): string {
  const raw = String(value ?? "").trim();
  if (!raw) return fallback;
  const key = raw.toUpperCase().replace(/[\s.-]+/g, "_");
  if (WORDS[key]) return WORDS[key];
  // "Complaint" or "Quality team" are names already; only SHOUTING, lower-case or snake_case codes are reworded.
  const isCode =
    CODE_LIKE.test(raw) &&
    (raw.includes("_") || raw.includes(".") || raw === raw.toUpperCase() || raw === raw.toLowerCase());
  if (!isCode) return raw;
  const words = raw
    .toLowerCase()
    .split(/[_.]+/)
    .map((word) => ACRONYMS[word] ?? word)
    .join(" ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Who a reminder or contact is for. */
const RECIPIENTS: Record<string, string> = {
  CUSTOMER_ADMIN: "Customer administrators",
  BILLING_CONTACT: "Billing contact",
  BUSINESS_CONTACT: "Business contact",
  ACCOUNT_OWNER: "Account owner",
};

export const recipientLabel = (value: unknown) => RECIPIENTS[String(value ?? "").toUpperCase()] ?? readable(value);

/** "1 user", "3 users". */
export const plural = (count: number, one: string, many = `${one}s`) =>
  `${count.toLocaleString()} ${count === 1 ? one : many}`;
