// Why MDARIX answered without the AI model, in words a user can act on.
//
// The server sends a stable refusal code with its own sentence (genai/provider.py REFUSAL_MESSAGES). The same
// sentences live here so an answer stored before the server sent `user_message` still reads correctly; the
// server's sentence wins when present.

export type RefusalCode =
  | "GENAI_MONTHLY_BUDGET_REACHED"
  | "GENAI_DISABLED_FOR_ORGANIZATION"
  | "GENAI_PROVIDER_NOT_ALLOWED"
  | "GENAI_UNAVAILABLE";

export const REFUSAL_MESSAGES: Record<RefusalCode, string> = {
  GENAI_MONTHLY_BUDGET_REACHED: "Your organization's monthly AI allowance is used up; an administrator can raise it.",
  GENAI_DISABLED_FOR_ORGANIZATION:
    "AI processing is switched off for your organization; an administrator can enable it under Security › AI processing.",
  GENAI_PROVIDER_NOT_ALLOWED:
    "No AI service approved for customer data is configured here, so MDARIX answered from its rules; please contact MDARIX support.",
  GENAI_UNAVAILABLE:
    "The AI service is not available right now, so MDARIX answered from its rules; please try again in a few minutes.",
};

export type Refusal = { code: RefusalCode; message: string };

const isCode = (value: unknown): value is RefusalCode =>
  typeof value === "string" && Object.prototype.hasOwnProperty.call(REFUSAL_MESSAGES, value);

/** The refusal in an Ask response (`response.refusal`, or a refused advisory), or null when the model answered. */
export function refusalOf(response: unknown): Refusal | null {
  const body = (response ?? {}) as Record<string, any>;
  const refusal = body.refusal && typeof body.refusal === "object" ? body.refusal : body;
  if (refusal.status !== "REFUSED" && !body.refusal) return null;
  const code: RefusalCode = isCode(refusal.code) ? refusal.code : "GENAI_UNAVAILABLE";
  const message =
    typeof refusal.user_message === "string" && refusal.user_message.trim()
      ? refusal.user_message
      : REFUSAL_MESSAGES[code];
  return { code, message };
}

/** The scope row in an answer's technical details: narrowed to one investigation, or the whole organization. */
export function scopeLabel(investigationScoped: boolean): string {
  return investigationScoped ? "Yes" : "No (organization-wide)";
}
