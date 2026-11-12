import { ApiError, describeError } from "../../../app/apiClient";

/*
 * Data governance of one organization as the platform screens show it (backend/app/tenant_export_api.py,
 * legal_hold_api.py, access/platform_customer_admins.py): the legal hold, the export-or-waiver step before its
 * data is deleted, the honest result of a deletion that could not remove everything at once, and the one-time
 * activation link for a person whose invitation email never arrived.
 */

export type DataExport = {
  id: string;
  status: string;
  reason: string;
  summary: { tables: number; rows: number; files: number } | null;
  size_bytes?: number | null;
  sha256?: string | null;
  created_at: string;
  completed_at?: string | null;
  expires_at: string | null;
  /** Whether the signed-in person asked for it: only they can download it (RSK-036). */
  yours?: boolean;
};

/**
 * The export a deletion counts as the hand-back: the newest READY export completed after the organization was
 * suspended (any READY export when no suspension date is known). The server applies the same rule; null when there
 * is none, and then a waiver reason is needed instead.
 */
export function exportAfterSuspension(
  exports: DataExport[],
  suspendedAt: string | null | undefined,
): DataExport | null {
  const since = suspendedAt ? Date.parse(suspendedAt) : Number.NaN;
  const ready = exports
    .filter((row) => String(row.status).toUpperCase() === "READY" && row.completed_at)
    .filter((row) => Number.isNaN(since) || Date.parse(String(row.completed_at)) >= since)
    .sort((a, b) => Date.parse(String(b.completed_at)) - Date.parse(String(a.completed_at)));
  return ready[0] ?? null;
}

export type HandBack = { kind: "export" } | { kind: "waiver"; reason: string };

export const WAIVER_MIN = 10;

/** Whether the hand-back step is answered: an export exists to rely on, or a waiver reason long enough. */
export function handBackReady(handBack: HandBack, available: DataExport | null): boolean {
  return handBack.kind === "export" ? available !== null : handBack.reason.trim().length >= WAIVER_MIN;
}

/** The body of POST .../purge. The waiver reason is sent only when the administrator chose to waive the export. */
export function purgeRequest(
  reason: string,
  password: string,
  tenantKey: string,
  handBack: HandBack | null,
  mfaCode = "",
) {
  return {
    reason: reason.trim(),
    password,
    confirm_tenant_key: tenantKey.trim(),
    ...(mfaCode ? { mfa_code: mfaCode } : {}),
    ...(handBack?.kind === "waiver" ? { export_waiver_reason: handBack.reason.trim() } : {}),
  };
}

export type PurgeResult = {
  status?: string;
  incomplete?: Record<string, string>;
  files_deleted?: number;
  users_pseudonymized?: number;
};

const STEP_NAMES: Record<string, string> = {
  files: "stored files",
  plane: "the dedicated database",
  rows: "late records",
};

/** What a deletion did, honestly: archived, or records deleted while files are still being removed (PURGING). */
export function purgeOutcome(
  name: string,
  result: PurgeResult | null | undefined,
): { tone: "good" | "warning"; text: string } {
  if (String(result?.status ?? "").toUpperCase() === "PURGING") {
    const steps = Object.keys(result?.incomplete ?? {}).map((step) => STEP_NAMES[step] ?? step);
    return {
      tone: "warning",
      text:
        `${name}'s records are deleted; files are still being removed${steps.length ? ` (${steps.join(", ")})` : ""}. ` +
        "This finishes automatically. The tenant shows as Purging until then.",
    };
  }
  return { tone: "good", text: `${name}'s data has been deleted and the tenant is archived.` };
}

export type LegalHold = {
  legal_hold: boolean;
  legal_hold_reason: string | null;
  legal_hold_set_at: string | null;
  legal_hold_set_by: string | null;
  // The User ID (USR…) of the administrator who set the hold; the account reference above is never shown.
  legal_hold_set_by_business_id?: string | null;
};

const MFA_MESSAGES: Record<string, string> = {
  MFA_REQUIRED: "Complete multi-factor sign-in on your own account first, then try again.",
  MFA_ENROLLMENT_REQUIRED: "Set up an authenticator app on your own account first (My Account, Security).",
};

const LEGAL_HOLD_MESSAGES: Record<string, string> = {
  ...MFA_MESSAGES,
  LEGAL_HOLD_NOT_SET: "There is no legal hold to release.",
};

const ACTIVATION_MESSAGES: Record<string, string> = {
  MFA_REQUIRED: "Set up multi-factor authentication on your own account before issuing activation links.",
  ACCOUNT_ALREADY_ACTIVE: "This person has already activated their account; send a password reset instead.",
  ACCOUNT_NOT_INVITED: "Only an account waiting for activation can get a link; resend the invitation first.",
};

function explained(messages: Record<string, string>, error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.code && messages[error.code]) {
    return error.requestId ? `${messages[error.code]} (reference ${error.requestId})` : messages[error.code];
  }
  return describeError(error, fallback);
}

/** Why a legal-hold change was refused, in words (the MFA refusals included). */
export const legalHoldError = (error: unknown) =>
  explained(LEGAL_HOLD_MESSAGES, error, "The legal hold was not changed.");

/** Why an activation link was not issued, in words. */
export const activationLinkError = (error: unknown) =>
  explained(ACTIVATION_MESSAGES, error, "The activation link was not issued.");

/** The legal-hold request body (the server requires a reason of at least 10 characters both ways). */
export const legalHoldRequest = (hold: boolean, reason: string) => ({ hold, reason: reason.trim() });
