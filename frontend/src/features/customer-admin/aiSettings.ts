/*
 * Switching AI processing on or off for an organization (customer administrators under Security › AI processing,
 * platform administrators on the tenant page). Switching it ON needs an explicit acknowledgement that the
 * organization's content will be sent to the named provider after personal-data masking: the API refuses the
 * change without `acknowledgement: true` (422 AI_ACKNOWLEDGEMENT_REQUIRED) and records it in the audit trail.
 */

export type AiSettingsChange = {
  ai_processing_allowed: boolean;
  reason: string;
  acknowledgement?: true;
  trial_acknowledgement?: true;
  features?: Record<string, boolean>;
  password?: string;
  mfa_code?: string;
  /** The settings' version as read: a change by someone else since then is refused (409 STALE_RECORD). */
  lock_version?: number;
};

/** Signature-grade re-authentication: the customer administrator's password and authenticator code (C6). */
export type ReAuthentication = { password: string; mfaCode: string };

const proofOf = (proof?: ReAuthentication) =>
  proof ? { password: proof.password, ...(proof.mfaCode.trim() ? { mfa_code: proof.mfaCode.trim() } : {}) } : {};

/** The PUT body: the acknowledgement is sent only when turning AI on, and only once the person confirmed it. A
 * customer administrator also re-authenticates to turn AI on (the server refuses it otherwise); a free trial adds
 * its own acknowledgement (sample data only, free AI services). */
export function aiSettingsPayload(
  turnOn: boolean,
  reason: string,
  acknowledged: boolean,
  proof?: ReAuthentication,
  trial = false,
): AiSettingsChange {
  if (turnOn && !acknowledged) throw new Error("Confirm the acknowledgement before turning AI processing on.");
  if (!turnOn) return { ai_processing_allowed: false, reason };
  return {
    ai_processing_allowed: true,
    reason,
    acknowledgement: true,
    ...(trial ? { trial_acknowledgement: true as const } : {}),
    ...proofOf(proof),
  };
}

/** The change, tied to the settings' version the screen read (older servers send none, so nothing is added). */
export function withLockVersion(change: AiSettingsChange, lockVersion?: number | null): AiSettingsChange {
  return typeof lockVersion === "number" ? { ...change, lock_version: lockVersion } : change;
}

/** One AI feature on or off; AI processing itself keeps its current state. Turning a feature on re-authenticates. */
export function aiFeaturePayload(
  aiOn: boolean,
  feature: string,
  turnOn: boolean,
  reason: string,
  proof?: ReAuthentication,
): AiSettingsChange {
  if (turnOn && !proof?.password) throw new Error("Enter your password to turn an AI feature on.");
  return {
    ai_processing_allowed: aiOn,
    reason,
    features: { [feature]: turnOn },
    ...(turnOn ? proofOf(proof) : {}),
  };
}

export type AiFeature = {
  key: string;
  label: string;
  intended_use: string;
  risk: "LOW" | "MEDIUM";
  never: string;
  offered: boolean;
  enabled: boolean;
  /** Offered and allowed on this server (MDARIX_AI_FEATURES); otherwise shown off and locked. */
  platform_allowed: boolean;
};

/** Why a feature's switch is locked, or null when the administrator may change it. */
export function featureLock(feature: AiFeature): string | null {
  if (!feature.offered) return "Not offered";
  if (!feature.platform_allowed) return "Not available on this service";
  return null;
}

/** The sentence a free trial's administrator confirms as well (owner decisions T5, T7). */
export const TRIAL_AI_ACKNOWLEDGEMENT =
  "AI in the free trial works on the sample data only, through free AI services that may process it outside India.";

/** The provider named in the acknowledgement: the one the server reports, or a plain description. */
export const providerLabel = (providerName: string | null | undefined) =>
  providerName?.trim() || "the AI provider configured for this server";

/** The sentence the person confirms before AI processing is turned on. */
export function aiAcknowledgement(providerName: string | null | undefined, onBehalfOf?: string): string {
  const provider = providerLabel(providerName);
  return onBehalfOf
    ? `On ${onBehalfOf}'s instruction, I acknowledge that records ${onBehalfOf}'s AI features need for an answer will be sent to ${provider}, after personal information is masked.`
    : `I acknowledge that records our AI features need for an answer will be sent to ${provider}, after personal information is masked.`;
}

/** What masking covers, in the words of docs/runbooks/ENVIRONMENT_VARIABLES.md (MDARIX_GENAI_PII_MASKING). */
export const MASKING_SUMMARY =
  'Email addresses, phone numbers, dates of birth, record and other identifying numbers and addresses are masked before sending, and so are names that are labelled or follow a title or role word (for example "Patient:", "Dr", "Nurse"). A name written on its own in free text is not always recognised, so keep names in labelled fields.';
