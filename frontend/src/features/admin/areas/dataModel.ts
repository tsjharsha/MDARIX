// Plain-language helpers for the Data & Configuration area.

/** Who may change a canonical field, in words (the server's override policy codes). */
export const changePolicyLabel = (policy: string | null | undefined) => {
  switch (String(policy ?? "").toUpperCase()) {
    case "PLATFORM_ONLY":
      return "MDARIX only";
    case "RESTRICTED":
      return "Customer, with approval";
    case "CUSTOMER_OVERRIDE_ALLOWED":
      return "Customer";
    case "":
      return "—";
    default:
      return String(policy)
        .toLowerCase()
        .replace(/_/g, " ")
        .replace(/^\w/, (letter) => letter.toUpperCase());
  }
};

/** How many field rules a stored mapping has (a list under "rules", "fields", or one key per field). */
export const mappingRuleCount = (rules: unknown) => {
  if (!rules || typeof rules !== "object") return 0;
  const value = rules as Record<string, unknown>;
  if (Array.isArray(value.rules)) return value.rules.length;
  if (value.fields && typeof value.fields === "object")
    return Array.isArray(value.fields) ? value.fields.length : Object.keys(value.fields).length;
  return Object.keys(value).filter((key) => !key.startsWith("_")).length;
};

/** The release pipeline, in order; each stage gathers the statuses the server uses. */
export const RELEASE_STEPS = [
  { key: "draft", label: "Draft", statuses: ["DRAFT", "VALIDATION"] },
  { key: "waiting", label: "Waiting for approval", statuses: ["READY_FOR_APPROVAL"] },
  { key: "approved", label: "Approved", statuses: ["APPROVED"] },
  { key: "released", label: "Released", statuses: ["RELEASED", "ACTIVE"] },
  { key: "superseded", label: "Rolled back", statuses: ["SUPERSEDED"] },
] as const;

/** The pipeline stage a status belongs to (its key), or undefined. */
export const releaseStageOf = (status: unknown) =>
  RELEASE_STEPS.find((step) => (step.statuses as readonly string[]).includes(String(status ?? "").toUpperCase()))?.key;

type NextAction = {
  action: "REQUEST_APPROVAL" | "APPROVE" | "PROMOTE" | "ROLLBACK";
  label: string;
  explain: string;
  done: string;
};

/** The one step a mapping can take next from its status, or null when there is none. */
export const nextReleaseAction = (status: unknown): NextAction | null => {
  switch (String(status ?? "").toUpperCase()) {
    case "DRAFT":
    case "VALIDATION":
      return {
        action: "REQUEST_APPROVAL",
        label: "Request approval",
        explain: "A different administrator must then approve it before it can be released.",
        done: "approval requested.",
      };
    case "READY_FOR_APPROVAL":
      return {
        action: "APPROVE",
        label: "Approve",
        explain: "You cannot approve a request you made yourself.",
        done: "approved.",
      };
    case "APPROVED":
      return {
        action: "PROMOTE",
        label: "Release",
        explain: "The mapping goes live for new data.",
        done: "released.",
      };
    case "RELEASED":
    case "ACTIVE":
      return {
        action: "ROLLBACK",
        label: "Roll back",
        explain: "The mapping stops being used; the previous behavior applies again.",
        done: "rolled back.",
      };
    default:
      return null;
  }
};

/**
 * A mapping status in words. A rolled-back mapping is SUPERSEDED on the server (rollback is the only step that sets
 * it), so it reads "Rolled back" everywhere, as its release stage does.
 */
export const mappingStatusLabel = (status: unknown) => {
  const value = String(status ?? "").toUpperCase();
  if (value === "SUPERSEDED") return "Rolled back";
  if (value === "READY_FOR_APPROVAL") return "Waiting for approval";
  if (!value) return "Unknown";
  return value.charAt(0) + value.slice(1).toLowerCase().replace(/_/g, " ");
};

/** "v2" or "2" -> "Version 2". */
export const versionLabel = (version: unknown) => {
  const text = String(version ?? "").trim();
  return text ? `Version ${text.replace(/^v(?=\d)/i, "")}` : "—";
};
