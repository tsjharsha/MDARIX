import type { Tone } from "../admin/console/dashboardModel";

/**
 * The automatic trust check every AI result gets as it is saved (trust_engine/auto.py, policy
 * MDARIX_AI_TRUST_POLICY_R1_V2): whether the sources it cites exist, whether it states a cause, a probability or a
 * decision that belongs to people, whether it asserts certainty, and who wrote it. A passed check means the result is
 * grounded and worded within policy, not that it is true: a person decides.
 */
export type TrustStatus = "PASS" | "PASS_WITH_LIMITATIONS" | "BLOCKED" | "NOT_CHECKED";
export type TrustCheckStatus = "PASS" | "WARNING" | "BLOCKED";
export type TrustCheck = { check: string; status: TrustCheckStatus; message: string };
export type TrustSummary = {
  id?: string | null;
  status: TrustStatus;
  label: string;
  policy?: string;
  author?: "AI" | "RULES" | null;
  checks?: TrustCheck[];
  limitations?: string[];
};

export const TRUST_TONE: Record<TrustStatus, Tone> = {
  PASS: "good",
  PASS_WITH_LIMITATIONS: "warning",
  BLOCKED: "critical",
  NOT_CHECKED: "neutral",
};

export const TRUST_LABEL: Record<TrustStatus, string> = {
  PASS: "Trust check passed",
  PASS_WITH_LIMITATIONS: "Trust check passed with limitations",
  BLOCKED: "Trust check blocked",
  NOT_CHECKED: "Not checked",
};

export const CHECK_TITLE: Record<string, string> = {
  EVIDENCE_GROUNDING: "Cited sources exist",
  RESTRICTED_CLAIMS: "No cause, probability or decision stated as fact",
  CERTAINTY_WORDING: "No asserted certainty",
  PROVENANCE: "Provider and model recorded",
  TENANT_INTEGRITY: "Belongs to this organization",
};

const STATUSES: readonly TrustStatus[] = ["PASS", "PASS_WITH_LIMITATIONS", "BLOCKED", "NOT_CHECKED"];

/** A trust summary from an API value, or null when there is none (rules output without an AI result, older data). */
export function trustOf(value: unknown): TrustSummary | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const status = STATUSES.find((item) => item === raw.status);
  if (!status) return null;
  const checks = Array.isArray(raw.checks)
    ? raw.checks
        .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
        .map((item) => ({
          check: String(item.check ?? ""),
          status: (["PASS", "WARNING", "BLOCKED"].includes(String(item.status))
            ? item.status
            : "PASS") as TrustCheckStatus,
          message: String(item.message ?? ""),
        }))
    : undefined;
  return {
    id: typeof raw.id === "string" ? raw.id : null,
    status,
    label: typeof raw.label === "string" && raw.label ? raw.label : TRUST_LABEL[status],
    policy: typeof raw.policy === "string" ? raw.policy : undefined,
    author: raw.author === "AI" || raw.author === "RULES" ? raw.author : null,
    checks,
    limitations: Array.isArray(raw.limitations) ? raw.limitations.map(String) : undefined,
  };
}

/** The checks that did not pass, most serious first. */
export function trustIssues(trust: TrustSummary | null): TrustCheck[] {
  const order: Record<TrustCheckStatus, number> = { BLOCKED: 0, WARNING: 1, PASS: 2 };
  return (trust?.checks ?? [])
    .filter((check) => check.status !== "PASS")
    .sort((left, right) => order[left.status] - order[right.status]);
}

/** One line for the badge's accessible name: the verdict and, when it did not pass, the first reason. */
export function trustSentence(trust: TrustSummary | null): string {
  if (!trust) return "";
  const issue = trustIssues(trust)[0];
  return issue ? `${trust.label}: ${issue.message}` : trust.label;
}
