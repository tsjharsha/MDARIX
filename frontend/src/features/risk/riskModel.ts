import type { Tone } from "../admin/console/dashboardModel";

/*
 * The risk register and ISO 14971 traceability as GET /api/v1/risk/register and /api/v1/risk/traceability return
 * them (backend/app/risk/service.py). The imported quality-system records carry no hazard, harm, severity,
 * probability or risk level: the server reports those as not captured (null), and so does this screen. Nothing here
 * estimates a score.
 */

export type LinkedControl = {
  id: string;
  control_identifier: string;
  control_type?: string | null;
  description?: string | null;
  status?: string | null;
  verification_evidence: Array<{
    id: string;
    evidence_identifier: string;
    title?: string | null;
    evidence_type?: string;
  }>;
};

export type RiskItem = {
  id: string;
  risk_identifier: string;
  description?: string | null;
  status?: string | null;
  product?: { id: string; product_identifier: string; name?: string | null } | null;
  product_version?: { id: string; version_identifier: string } | null;
  hazard?: string | null;
  harm?: string | null;
  severity?: string | number | null;
  probability?: string | number | null;
  risk_level?: string | null;
  residual_risk: { state: string; basis: string };
  failure_modes: Array<{ id: string; failure_mode_identifier: string; name?: string | null }>;
  controls: LinkedControl[];
  requirements: Array<{ id: string; requirement_identifier: string; text?: string | null; status?: string | null }>;
  open_complaints_on_product: number;
  source_system?: string | null;
  recorded_at?: string | null;
};

export type RegisterPage = {
  items: RiskItem[];
  total: number;
  limit: number;
  offset: number;
  next_offset: number | null;
  fields_not_captured: string[];
  data_notice: string;
};

export type Chain = {
  risk_id: string;
  risk_identifier: string;
  product: string | null;
  requirements: string[];
  failure_modes: string[];
  controls: string[];
  verification_evidence: string[];
  residual_risk: string;
  complete: boolean;
};

export type Traceability = {
  chains: Chain[];
  counts: {
    risks: number;
    requirements: number;
    failure_modes: number;
    controls: number;
    complete_chains: number;
    unlinked: Record<string, number>;
  };
  unlinked: Record<string, string[]>;
  standard: string;
  data_notice: string;
};

export const PAGE_SIZE = 25;
export const NOT_CAPTURED = "Not captured in your data";

export const registerPath = (offset: number, limit = PAGE_SIZE) =>
  `/api/v1/risk/register?${new URLSearchParams({ limit: String(limit), offset: String(Math.max(0, offset)) })}`;

export const reviewRequestPath = (riskId: string) => `/api/v1/risk/${encodeURIComponent(riskId)}/review-request`;

/** A register field as shown: its value, or that the organization's records do not hold it. */
export const fieldOrNotCaptured = (value: unknown) =>
  value === null || value === undefined || String(value).trim() === "" ? NOT_CAPTURED : String(value);

/** The ISO 14971 columns the imported records do not carry, by label (from the server's own list). */
export function notCapturedLabels(fields: string[] | undefined): string[] {
  const names: Record<string, string> = {
    hazard: "Hazard",
    harm: "Harm",
    severity: "Severity",
    probability: "Probability",
    risk_level: "Risk level",
  };
  return (fields ?? []).map((field) => names[field] ?? field.replace(/_/g, " "));
}

const RESIDUAL: Record<string, { label: string; tone: Tone }> = {
  NO_CONTROLS_LINKED: { label: "No control linked", tone: "serious" },
  CONTROLLED_WITHOUT_VERIFICATION_EVIDENCE: { label: "Controlled, not verified", tone: "warning" },
  CONTROLLED_WITH_VERIFICATION_EVIDENCE: { label: "Controlled, verification evidence linked", tone: "good" },
};

/** What the records support about residual risk, in words with a tone (never a score). */
export function residualLabel(state: string | undefined): { label: string; tone: Tone } {
  return (
    RESIDUAL[String(state ?? "")] ?? {
      label: state ? state.replace(/_/g, " ").toLowerCase() : "Unknown",
      tone: "neutral",
    }
  );
}

/** "Risks 26–50 of 61" for a page of the register. */
export function pageSummary(total: number, offset: number, shown: number): string {
  if (!total || !shown) return `${total} risks`;
  return `Risks ${offset + 1}–${offset + shown} of ${total}`;
}

/** A review request needs a reason the server accepts (at least 10 characters once trimmed). */
export const reviewReasonValid = (reason: string) => reason.trim().length >= 10;

export type Gap = {
  key: string;
  label: string;
  items: string[];
  /** What the person can do about it. */
  fix: string;
  /** The listed identifiers are risks (they can be found in the chains below). */
  risks: boolean;
};

const GAPS: Array<Omit<Gap, "items">> = [
  {
    key: "risks_without_control",
    label: "Risks without a control",
    fix: "Record the risk control in your quality system and import it with its link to the risk.",
    risks: true,
  },
  {
    key: "controls_without_verification_evidence",
    label: "Controls without verification evidence",
    fix: "Link the verification or validation evidence for each control (test report, inspection record).",
    risks: false,
  },
  {
    key: "risks_without_requirement",
    label: "Risks without a requirement",
    fix: "Link the design requirement that mitigates each risk.",
    risks: true,
  },
  {
    key: "risks_without_failure_mode",
    label: "Risks without a failure mode",
    fix: "Link the failure modes that can lead to each risk.",
    risks: true,
  },
  {
    key: "requirements_without_risk",
    label: "Requirements not linked to a risk",
    fix: "Link each requirement to the risk it mitigates, or confirm it is not a risk control.",
    risks: false,
  },
  {
    key: "failure_modes_without_risk",
    label: "Failure modes not linked to a risk",
    fix: "Link each failure mode to the risk it can lead to.",
    risks: false,
  },
  {
    key: "controls_without_risk",
    label: "Controls not linked to a risk",
    fix: "Link each control to the risk it controls.",
    risks: false,
  },
];

/** The traceability gaps that have entries, most consequential first, each with what to do about it. */
export function traceabilityGaps(unlinked: Record<string, string[]> | undefined): Gap[] {
  return GAPS.map((gap) => ({ ...gap, items: unlinked?.[gap.key] ?? [] })).filter((gap) => gap.items.length > 0);
}

/** The chains matching a search (risk, product or any linked identifier), complete ones last when asked. */
export function filterChains(chains: Chain[], query: string, gapsOnly: boolean): Chain[] {
  const needle = query.trim().toLowerCase();
  return chains.filter((chain) => {
    if (gapsOnly && chain.complete) return false;
    if (!needle) return true;
    return [
      chain.risk_identifier,
      chain.product ?? "",
      ...chain.requirements,
      ...chain.failure_modes,
      ...chain.controls,
      ...chain.verification_evidence,
    ].some((value) => value.toLowerCase().includes(needle));
  });
}

/** Which links a chain is missing, in words ("requirement, verification evidence"); empty when complete. */
export function missingLinks(chain: Chain): string[] {
  const missing: string[] = [];
  if (!chain.requirements.length) missing.push("requirement");
  if (!chain.failure_modes.length) missing.push("failure mode");
  if (!chain.controls.length) missing.push("control");
  if (!chain.verification_evidence.length) missing.push("verification evidence");
  return missing;
}
