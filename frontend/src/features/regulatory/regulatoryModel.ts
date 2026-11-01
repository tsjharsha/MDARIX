import { ApiError, describeError } from "../../app/apiClient";

/*
 * The regulatory copilot's contract (backend/app/regulatory_router.py, regulatory_intelligence/copilot.py): a draft
 * is the citation-checked section layout, with section text written by the language model from the organization's
 * authorized records when AI is available (AI_DRAFTED) or the layout only (RULES_ONLY, with the reason). Approval
 * is signature-grade: the approver re-enters their password and, when signatures need MFA, an authenticator code.
 */

export const TEMPLATES = ["GSPR", "CER", "IFU", "ESTAR_510K"] as const;
export type Template = (typeof TEMPLATES)[number];

export const TEMPLATE_LABELS: Record<Template, string> = {
  GSPR: "GSPR checklist (EU MDR Annex I)",
  CER: "Clinical evaluation report",
  IFU: "Instructions for use",
  ESTAR_510K: "eSTAR 510(k) preparation",
};

/** The sections each template asks for (regulatory_intelligence/service.py: AUTHORING_SECTIONS), in order. */
export const AUTHORING_SECTIONS: Record<Template, readonly string[]> = {
  GSPR: ["device_scope", "general_requirements", "risk_controls", "verification_evidence", "residual_risks"],
  CER: [
    "device_description",
    "state_of_the_art",
    "clinical_evaluation_plan",
    "clinical_evidence",
    "benefit_risk_conclusion",
    "post_market_follow_up",
  ],
  IFU: [
    "intended_purpose",
    "indications_and_contraindications",
    "warnings_and_precautions",
    "instructions",
    "residual_risks",
    "storage_and_disposal",
  ],
  ESTAR_510K: [
    "device_description",
    "indications_for_use",
    "substantial_equivalence",
    "performance_testing",
    "labeling",
  ],
};

export const sectionTitle = (id: string) => id.replace(/_/g, " ").replace(/^\w/, (letter) => letter.toUpperCase());

export type DraftForm = {
  template: Template;
  identifier: string;
  title: string;
  investigationId: string;
  claims: string;
  sections: Record<string, string>;
};

/** The body of POST /api/v1/regulatory/draft: claims one per line, only the template's own non-empty sections. */
export function draftRequest(form: DraftForm) {
  const claims = form.claims
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((text, index) => ({ claim_id: `claim-${index + 1}`, text }));
  const sections = Object.fromEntries(
    AUTHORING_SECTIONS[form.template]
      .map((id) => [id, (form.sections[id] ?? "").trim()] as const)
      .filter(([, text]) => text),
  );
  return {
    document_type: form.template,
    ...(form.identifier.trim() ? { document_identifier: form.identifier.trim() } : {}),
    ...(form.title.trim() ? { title: form.title.trim() } : {}),
    ...(form.investigationId ? { investigation_id: form.investigationId } : {}),
    claims,
    citations: [],
    authoring_sections: sections,
    change_reason: "Regulatory copilot draft",
  };
}

export type AiChecks = {
  cited?: string[];
  unverified_citations?: string[];
  causal_or_decision_wording?: string[];
  notes?: string[];
  flagged?: boolean;
};

export type DraftSection = {
  section_id?: string;
  title?: string;
  content?: string;
  status?: string;
  ai_draft?: string;
  ai_checks?: AiChecks;
  human_review_required?: boolean;
  // A claim the author asked to be supported (rules draft): its citations and confidence.
  claim_id?: string;
  text?: string;
  confidence?: string;
  unsupported?: boolean;
};

export type Assistance = {
  status?: "AI_DRAFTED" | "RULES_ONLY" | string;
  reason_code?: string | null;
  user_message?: string;
  model?: string | null;
  provider?: string | null;
  sections_drafted?: string[];
};

/** How the draft was written, in one line the person can trust: by the model from their records, or layout only. */
export function draftOutcome(assistance: Assistance | undefined | null): {
  aiDrafted: boolean;
  title: string;
  message: string;
} {
  if (assistance?.status === "AI_DRAFTED")
    return {
      aiDrafted: true,
      title: "Drafted by AI from your records",
      message:
        assistance.user_message ||
        "The model drafted the sections from your organization's records; review every section.",
    };
  return {
    aiDrafted: false,
    title: "Rules only: section layout, no AI text",
    message:
      assistance?.user_message ||
      "No AI text was written for this draft; the sections are the layout only. Write or paste the text yourself.",
  };
}

/** The sections a template asks for, apart from the author's claims. */
export const authoringSections = (sections: DraftSection[] | undefined) =>
  (sections ?? []).filter((section) => section.section_id);
export const claimSections = (sections: DraftSection[] | undefined) =>
  (sections ?? []).filter((section) => section.claim_id);

/** What the citation and wording checks found in one AI-written section, as short lines (empty when clean). */
export function checkFindings(checks: AiChecks | undefined): string[] {
  if (!checks) return [];
  const findings: string[] = [];
  if (checks.unverified_citations?.length)
    findings.push(`Cites records that were not in its sources: ${checks.unverified_citations.join(", ")}`);
  if (checks.causal_or_decision_wording?.length)
    findings.push(`Causal or decision wording to rewrite: ${checks.causal_or_decision_wording.join("; ")}`);
  for (const note of checks.notes ?? []) findings.push(note);
  return findings;
}

/** The approval request: the transition, the reason, and the re-authentication (a code only when one was typed). */
export function approvalRequest(lockVersion: number, reason: string, password: string, code: string) {
  const mfa = code.replace(/\s+/g, "");
  return {
    status: "APPROVED",
    expected_lock_version: lockVersion,
    reason: reason.trim(),
    password,
    ...(mfa ? { mfa_code: mfa } : {}),
  };
}

const APPROVAL_REFUSALS: Record<string, string> = {
  REAUTHENTICATION_REQUIRED: "Enter your password to approve this document.",
  INVALID_REAUTHENTICATION:
    "Your password was not accepted. Check it and try again; after five failed attempts approving is locked for 15 minutes.",
  SIGNATURE_CODE_INVALID:
    "Enter the current six-digit code from your authenticator app (the code was missing or not accepted).",
  SIGNATURE_MFA_NOT_SET_UP:
    "Approving needs an authenticator app. Set one up under My Account, Security, then approve again.",
  ADMINISTRATOR_CANNOT_SIGN:
    "Administrators do not approve controlled documents; an approver of your organization must do this.",
  SIGNATURE_TEMPORARILY_LOCKED:
    "Too many failed attempts: approving and signing are locked for 15 minutes. Try again later.",
  SOD_DENIED: "You wrote this document or one of its versions, so another approver must approve it.",
  PERMISSION_DENIED: "Your role cannot approve regulatory documents.",
  REGULATORY_DOCUMENT_VERSION_CONFLICT:
    "The document changed since you opened it. Close this dialog, reload it and try again.",
};

/** Why an approval was refused, in words for every refusal the server gives, with the reference to quote. */
export function approvalError(error: unknown): string {
  if (error instanceof ApiError && error.code && APPROVAL_REFUSALS[error.code]) {
    const text = APPROVAL_REFUSALS[error.code];
    return error.requestId ? `${text} (reference ${error.requestId})` : text;
  }
  return describeError(error, "The document was not approved.");
}

/** The transitions the server allows from each status (regulatory_router.update_regulatory_status). */
export const NEXT_STATUSES: Record<string, string[]> = {
  DRAFT: ["IN_REVIEW", "ARCHIVED"],
  IN_REVIEW: ["DRAFT", "APPROVED", "ARCHIVED"],
  APPROVED: ["ARCHIVED"],
  ARCHIVED: [],
};
