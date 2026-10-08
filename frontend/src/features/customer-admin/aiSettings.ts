/*
 * Switching AI processing on or off for an organization (customer administrators under Security › AI processing,
 * platform administrators on the tenant page). Switching it ON needs an explicit acknowledgement that the
 * organization's content will be sent to the named provider after personal-data masking: the API refuses the
 * change without `acknowledgement: true` (422 AI_ACKNOWLEDGEMENT_REQUIRED) and records it in the audit trail.
 */

export type AiSettingsChange = { ai_processing_allowed: boolean; reason: string; acknowledgement?: true };

/** The PUT body: the acknowledgement is sent only when turning AI on, and only once the person confirmed it. */
export function aiSettingsPayload(turnOn: boolean, reason: string, acknowledged: boolean): AiSettingsChange {
  if (turnOn && !acknowledged) throw new Error("Confirm the acknowledgement before turning AI processing on.");
  return { ai_processing_allowed: turnOn, reason, ...(turnOn ? { acknowledgement: true as const } : {}) };
}

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
