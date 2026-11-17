/** E1: AI governance on one screen, read from GET /api/v1/admin/ai-governance (an organization's administrator or the
 * person who started a free trial) and GET /api/v1/platform-admin/ai-governance (counts per organization). */

export const AI_GOVERNANCE_PATH = "/api/v1/admin/ai-governance";
export const PLATFORM_AI_GOVERNANCE_PATH = "/api/v1/platform-admin/ai-governance";

export type ApprovedProvider = {
  name: string;
  kind: string;
  terms: string | null;
  checked_on: string | null;
  region: string | null;
  trains_on_data: string;
  why: string;
  warning?: string | null;
  in_trial_chain: boolean;
};
export type Providers = {
  approved: ApprovedProvider[];
  not_used: Array<{ name: string; why: string }>;
  trial_chain: string[];
};
export type Verdicts = Record<string, number>;
export type GovernanceOutput = {
  id: string;
  ref: string | null;
  what: string;
  at: string | null;
  provider: string | null;
  model: string | null;
  prompt_version: string | null;
  sources: number;
  reviews: Verdicts;
  recorded: boolean;
};
export type GovernanceCall = {
  id: string;
  feature: string;
  at: string | null;
  provider: string | null;
  model: string | null;
  prompt_version: string | null;
  sources: number;
  outcome: string;
  review: string;
};
export type Agreement = { ACCEPTED: number; EDITED: number; REJECTED: number };
export type Disagreement = {
  subject_type: string;
  ref: string | null;
  decision: "EDITED" | "REJECTED";
  reason: string | null;
  reviewer: string | null;
  at: string | null;
  recorded: boolean;
};
export type AiGovernance = {
  statement: string;
  recorded_label: string;
  providers: Providers;
  controls: {
    organization_on: boolean;
    free_trial: boolean;
    trial_chain_on: boolean;
    features: Array<{ key: string; label: string; enabled: boolean }>;
    people: Array<{ name: string | null; ai: string }> | null;
  };
  outputs: { live: number; recorded: number; items: GovernanceOutput[] };
  calls: { total: number; by_outcome: Record<string, number>; items: GovernanceCall[] };
  agreement: { live: Agreement; recorded: Agreement; disagreements: Disagreement[] };
};
export type PlatformAiGovernance = {
  statement: string;
  recorded_label: string;
  providers: Providers;
  organizations: Array<{
    tenant_id: string;
    organization: string | null;
    organization_on: boolean | null;
    live: number;
    recorded: number;
    calls: number;
    ACCEPTED: number;
    EDITED: number;
    REJECTED: number;
  }>;
};

export const NOT_RECORDED = "Not recorded";
/** The share of reviewed outputs a person accepted as they were (null when nothing was reviewed). Pure. */
export function agreementShare(agreement: Agreement): number | null {
  const total = agreement.ACCEPTED + agreement.EDITED + agreement.REJECTED;
  return total ? Math.round((agreement.ACCEPTED / total) * 100) : null;
}

export const disagreementWord = (decision: Disagreement["decision"]) => (decision === "EDITED" ? "Edited" : "Rejected");
