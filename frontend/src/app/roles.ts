/**
 * Role names people read. The server sends role codes (INVESTIGATOR, RISK_REVIEWER) and, from Phase 1, their labels
 * too; a screen shows the label, never the raw code. These labels match the server's own (session context `roles`,
 * the user list's `role_label`), so a screen that has only a code still shows the same words.
 */
export const ROLE_LABELS: Record<string, string> = {
  TRIAGE_LEAD: "PMS / Signal Triage Lead",
  INVESTIGATOR: "Quality Investigator",
  RISK_REVIEWER: "Risk Reviewer",
  REGULATORY_REVIEWER: "Regulatory Reviewer",
  REVIEWER: "Quality Reviewer",
  APPROVER: "Authorized Decision Maker",
  LEADER: "Leader (Quality Manager)",
  VIEWER: "Viewer",
  CUSTOMER_ADMIN: "Customer Administrator",
  PLATFORM_ADMIN: "Platform Administrator",
};

/** The business roles work can be routed to (a task's role queue); administrators manage, they do not work tasks. */
export const WORKFLOW_ROLE_CODES = [
  "TRIAGE_LEAD",
  "INVESTIGATOR",
  "RISK_REVIEWER",
  "REGULATORY_REVIEWER",
  "REVIEWER",
  "APPROVER",
  "LEADER",
] as const;

/** A role as the session context, the task summary and the role editor send it. */
export type RoleRef = { code: string; label?: string | null; source?: "account" | "additional" | string };

const roleCode = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

const CODE_LIKE = /^[A-Z][A-Z0-9_]*$/;

/**
 * The label to show for a role: the server's label when it sent one, else the known label for its code, else a
 * readable form of a code ("QA_LEAD" becomes "Qa Lead") and any other name (an organization's own role) as it is.
 */
export function roleLabel(code: unknown, label?: unknown): string {
  const given = typeof label === "string" ? label.trim() : "";
  if (given) return given;
  const raw = String(code ?? "").trim();
  if (!raw) return "";
  const known = ROLE_LABELS[roleCode(raw)];
  if (known) return known;
  if (!CODE_LIKE.test(raw)) return raw;
  return raw
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/**
 * The roles a person holds, as labels in the order the server listed them (account role first), without repeats.
 * Without a `roles` list (an older session) it falls back to the active role.
 */
export function roleLabels(session: { roles?: RoleRef[] | null; active_role?: string | null } | null | undefined) {
  const roles = Array.isArray(session?.roles) ? session.roles : [];
  const labels = roles.map((role) => roleLabel(role?.code, role?.label)).filter(Boolean);
  if (!labels.length) {
    const active = roleLabel(session?.active_role);
    if (active) labels.push(active);
  }
  return labels.filter((label, index) => labels.indexOf(label) === index);
}

/** "Quality Investigator + Risk Reviewer" for the header; `fallback` when the person has no role at all. */
export function rolesSummary(
  session: { roles?: RoleRef[] | null; active_role?: string | null } | null | undefined,
  fallback = "No active role",
): string {
  const labels = roleLabels(session);
  return labels.length ? labels.join(" + ") : fallback;
}
