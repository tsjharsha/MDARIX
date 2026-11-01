/**
 * An API failure the screen can act on: the server's own message (never a raw object or a JSON parse error), its
 * error code, and the request id the server logged it under, so a person reporting the problem can quote it.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly requestId?: string;
  constructor(message: string, status: number, code?: string, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

/** The connection failed or timed out: nothing reached the server, or nothing came back in time. */
export const isUnreachable = (error: unknown) =>
  error instanceof ApiError && (error.status === 0 || [502, 503, 504].includes(error.status));

type RequestOptions = RequestInit & {
  timeoutMs?: number;
  retries?: number;
  /** A 401 normally sends the person to sign-in; the session check that decides where to go turns it off. */
  redirectOnUnauthorized?: boolean;
  /** A read the page makes on its own (a poll), not the person: it neither restarts the idle window here nor, through
   * BACKGROUND_HEADER, on the server, so a page left open still signs out after the idle timeout. */
  background?: boolean;
};

/** Marks a background request; the server then leaves the session's idle window alone (request_context.py). */
export const BACKGROUND_HEADER = "X-MDARIX-Background";

// The request id of the latest failed call, offered with "Report a problem" so support can find the server log.
let lastFailureRequestId: string | undefined;
export const lastFailedRequestId = () => lastFailureRequestId;

// Every successful call keeps the server session alive (it resets the idle timer); the session watch listens.
// Background reads (option `background`) do neither.
const activityListeners = new Set<() => void>();
export function onApiActivity(listener: () => void): () => void {
  activityListeners.add(listener);
  return () => activityListeners.delete(listener);
}

const STATUS_MESSAGES: Record<number, string> = {
  401: "Your session has ended. Sign in again to continue.",
  403: "Your role does not allow this.",
  404: "This item was not found in your organization.",
  413: "The file or request is too large.",
  429: "Too many requests in a short time. Wait a minute and try again.",
  502: "MDARIX is not reachable right now. Try again in a moment.",
  503: "MDARIX is not reachable right now. Try again in a moment.",
  504: "MDARIX took too long to answer. Try again in a moment.",
};

/** A readable message from any error body the API (or a proxy in front of it) can return. */
export function errorMessageFrom(payload: unknown, status: number): string {
  const detail = (payload as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    // Request validation (422): one line per field, named by the last part of its location.
    const lines = detail
      .map((item) => {
        const field = Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : undefined;
        const text = typeof item?.msg === "string" ? item.msg : "";
        return text ? (typeof field === "string" ? `${field.replace(/_/g, " ")}: ${text}` : text) : "";
      })
      .filter(Boolean);
    if (lines.length) return `Check the form: ${lines.join("; ")}.`;
  }
  if (detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string")
    return (detail as { message: string }).message;
  return STATUS_MESSAGES[status] ?? `The request could not be completed (error ${status}).`;
}

function requestIdFrom(payload: unknown, response: Response): string | undefined {
  const detail = (payload as { detail?: unknown } | null)?.detail;
  const fromBody =
    detail && typeof detail === "object" && !Array.isArray(detail)
      ? ((detail as { request_id?: unknown; correlation_id?: unknown }).request_id ??
        (detail as { correlation_id?: unknown }).correlation_id)
      : undefined;
  if (typeof fromBody === "string" && fromBody) return fromBody;
  return response.headers?.get?.("X-Request-ID") ?? undefined;
}

const PRIVATE_ROOTS = ["/app", "/platform-admin"];
const inPrivateApp = (pathname: string) =>
  PRIVATE_ROOTS.some((root) => pathname === root || pathname.startsWith(`${root}/`));

/** The sign-in address that brings the person back to where they were. */
export function signInPath(reason: "idle" | "expired" | undefined, location: { pathname: string; search: string }) {
  const params = new URLSearchParams();
  if (reason) params.set("reason", reason);
  if (inPrivateApp(location.pathname)) params.set("returnTo", `${location.pathname}${location.search}`);
  const query = params.toString();
  return query ? `/signin?${query}` : "/signin";
}

// Operator calls whose MFA refusal is about the action itself (an operator without an authenticator) and is shown in
// that action's own dialog. A signature's refusals have their own codes (SIGNATURE_CODE_INVALID,
// SIGNATURE_MFA_NOT_SET_UP), so every signing form shows them in place and keeps what was typed; MFA_REQUIRED from any
// other call means the sign-in still owes its second factor. The server enforces MFA either way.
const ACTION_MFA_CALLS = ["/legal-hold", "/activation-link"];

/** Where an MFA refusal sends the browser: the second-factor page for an unfinished sign-in, nowhere for an action. */
export function mfaRedirectFor(path: string, status: number, code: string | undefined): string | null {
  if (status !== 403 || ACTION_MFA_CALLS.some((part) => path.includes(part))) return null;
  if (code === "MFA_REQUIRED") return "/mfa";
  if (code === "MFA_ENROLLMENT_REQUIRED") return "/mfa?setup=1";
  return null;
}

// Calls that answer 401 for a wrong password or code, not for an ended session.
const CREDENTIAL_CALLS = ["/api/v1/auth/signin", "/api/v1/auth/signout", "/api/v1/auth/mfa"];

/** Whether a 401 means "the session is gone": then the person signs in again and comes back. */
export function endsSession(path: string, status: number, code: string | undefined, pathname: string) {
  return (
    status === 401 &&
    code !== "INVALID_CREDENTIALS" &&
    !CREDENTIAL_CALLS.some((prefix) => path.startsWith(prefix)) &&
    inPrivateApp(pathname)
  );
}

let redirecting = false;

export async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    timeoutMs = 15000,
    retries = options.method && options.method !== "GET" ? 0 : 1,
    redirectOnUnauthorized = true,
    background = false,
    ...init
  } = options;
  let lastError: unknown;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    let timedOut = false;
    const timer = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    // A caller's own cancel (a screen that closed) still stops the request.
    const callerSignal = init.signal;
    const relay = () => controller.abort();
    callerSignal?.addEventListener?.("abort", relay);
    try {
      const response = await fetch(path, {
        credentials: "same-origin",
        ...init,
        signal: controller.signal,
        headers: {
          Accept: "application/json",
          // Files and form data carry their own type; a string body is JSON unless the caller says otherwise.
          ...(typeof init.body === "string" ? { "Content-Type": "application/json" } : {}),
          ...(background ? { [BACKGROUND_HEADER]: "1" } : {}),
          ...init.headers,
        },
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = (payload as { detail?: { code?: unknown } } | null)?.detail;
        const code = detail && typeof detail === "object" && !Array.isArray(detail) ? detail.code : undefined;
        const codeText = typeof code === "string" ? code : undefined;
        const error = new ApiError(
          errorMessageFrom(payload, response.status),
          response.status,
          codeText,
          requestIdFrom(payload, response),
        );
        if (error.requestId) lastFailureRequestId = error.requestId;
        // The session ended (idle timeout, expiry, revoked elsewhere): sign in again and come back here.
        if (
          redirectOnUnauthorized &&
          !redirecting &&
          endsSession(path, response.status, codeText, window.location?.pathname ?? "")
        ) {
          redirecting = true;
          window.location.replace(
            signInPath(codeText === "SESSION_IDLE_TIMEOUT" ? "idle" : "expired", window.location),
          );
        }
        // The second factor is still due: go where that is handled.
        const mfaPage = mfaRedirectFor(path, response.status, codeText);
        if (mfaPage) window.location.replace(mfaPage);
        throw error;
      }
      if (!background) activityListeners.forEach((listener) => listener());
      return payload as T;
    } catch (error) {
      lastError = error;
      if (error instanceof ApiError) throw error;
      if (callerSignal?.aborted) throw error;
      if (attempt === retries)
        throw timedOut
          ? new ApiError(
              "MDARIX took too long to answer, so the request was stopped. Try again; if it keeps happening, report a problem.",
              0,
              "TIMEOUT",
            )
          : new ApiError("MDARIX could not be reached. Check your connection and try again.", 0, "NETWORK_ERROR");
      await new Promise((resolve) => window.setTimeout(resolve, 150 * (attempt + 1)));
    } finally {
      window.clearTimeout(timer);
      callerSignal?.removeEventListener?.("abort", relay);
    }
  }
  throw lastError instanceof Error ? lastError : new Error("Request failed");
}

/** How long an AI action (analysis, hypotheses, briefs, drafts) may take before the screen gives up waiting. */
export const AI_TIMEOUT_MS = 60_000;

/** Send JSON with the shared client: same error handling, request id and session rules as every other call. */
export function postJson<T>(path: string, body: unknown, options: RequestOptions = {}): Promise<T> {
  return requestJson<T>(path, { method: "POST", body: JSON.stringify(body), ...options });
}

/** One line for a failed action: the server's message, plus the reference to quote to support when there is one. */
export function describeError(error: unknown, fallback: string): string {
  const message = error instanceof Error && error.message ? error.message : fallback;
  return error instanceof ApiError && error.requestId ? `${message} (reference ${error.requestId})` : message;
}
