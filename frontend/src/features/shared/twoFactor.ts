import { ApiError } from "../../app/apiClient";

/**
 * Two-factor sign-in that a person manages themselves (GET /api/v1/auth/mfa/status): on or off, since when, how many
 * recovery codes are left, whether their role requires it, and whether a new authenticator app was started but not
 * yet confirmed. The server never sends the secret or a code here.
 */
export type MfaStatus = {
  enrolled: boolean;
  enrolled_at: string | null;
  recovery_codes_left: number;
  required_for_role: boolean;
  replacement_pending: boolean;
};

/** How many recovery codes a set holds (backend/app/mfa.py issues eight). */
export const RECOVERY_CODE_COUNT = 8;

/** What to say about the recovery codes left; a warning when few are. */
export function recoveryCodesNote(left: number): { text: string; low: boolean } {
  if (left <= 0)
    return {
      text: "You have no recovery codes left. Generate new ones now, so a lost phone does not lock you out.",
      low: true,
    };
  const low = left <= 2;
  const text = `${left} of ${RECOVERY_CODE_COUNT} recovery code${left === 1 ? "" : "s"} left.`;
  return { text: low ? `${text} Generate new ones soon.` : text, low };
}

/**
 * A typed code as the server expects it: six digits from the authenticator app, or, where a recovery code is
 * allowed, its hex digits and the dash (xxxxxxxx-xxxxxxxx).
 */
export function cleanCode(value: string, allowRecovery: boolean): string {
  if (allowRecovery && /[a-fA-F-]/.test(value))
    return value
      .replace(/[^0-9a-fA-F-]/g, "")
      .toLowerCase()
      .slice(0, 17);
  return value.replace(/\D/g, "").slice(0, allowRecovery ? 17 : 6);
}

const REAUTH_MESSAGES: Record<string, string> = {
  REAUTHENTICATION_REQUIRED: "Enter your current password and a code from your authenticator app.",
  REAUTHENTICATION_FAILED: "The password or the code is wrong. Check both and try again.",
  MFA_TEMPORARILY_LOCKED: "Too many wrong attempts. Wait 15 minutes, then try again.",
  RATE_LIMITED: "Too many attempts. Wait a few minutes, then try again.",
  MFA_CODE_INVALID: "That code did not match. Enter the code your new authenticator app shows now.",
  MFA_NOT_ENROLLED: "Two-factor sign-in is not on for your account yet. Set it up first.",
};

/** The plain-English reason a change to two-factor sign-in was refused. */
export function reauthMessage(reason: unknown, fallback: string): string {
  const code = reason instanceof ApiError ? reason.code : undefined;
  if (code && REAUTH_MESSAGES[code]) return REAUTH_MESSAGES[code];
  return reason instanceof ApiError && reason.message ? reason.message : fallback;
}

/** The text of the recovery codes file (download) and of "Copy all": the codes, and how to use and keep them. */
export function recoveryCodesText(codes: readonly string[], account: string | null | undefined, issued: Date): string {
  return [
    "MDARIX recovery codes",
    account ? `Account: ${account}` : null,
    `Issued: ${issued.toISOString().slice(0, 16).replace("T", " ")} UTC`,
    "",
    "Each code signs you in once when your authenticator app is not at hand.",
    "Keep them private, like a password. Generating new codes makes these stop working.",
    "",
    ...codes.map((code, index) => `${index + 1}. ${code}`),
    "",
  ]
    .filter((line) => line !== null)
    .join("\n");
}

/** Where "Replace authenticator app" goes: the setup page, which comes back here when done. */
export function replaceAuthenticatorHref(returnTo: string): string {
  return `/mfa?setup=1&returnTo=${encodeURIComponent(returnTo)}`;
}
