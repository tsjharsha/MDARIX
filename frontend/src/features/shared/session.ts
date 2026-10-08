import { requestJson, signInPath } from "../../app/apiClient";

// The server signs a session out after this much inactivity (MDARIX_SESSION_IDLE_MINUTES, 30 by default). The
// browser uses it only when the session answer does not say when this session ends.
export const IDLE_SIGN_OUT_MS = 30 * 60 * 1000;
// The browser warns this long before the session ends, so nobody loses a half-written form without notice.
export const SESSION_WARNING_MS = 2 * 60 * 1000;
// Activity in one tab keeps the others from signing the person out (they share one server session).
export const ACTIVITY_KEY = "mdarix:session-activity";

export type SignOutReason = "idle" | "expired";

/** End the server session, drop any tenant-scoped browser state, and return to sign-in. A timed-out session says
 * why and comes back to the same page after the next sign-in; a chosen sign-out starts afresh. */
export async function signOut(reason?: SignOutReason) {
  await requestJson("/api/v1/auth/signout", { method: "POST", retries: 0 }).catch(() => undefined);
  try {
    sessionStorage.clear();
  } catch {
    // Storage can be unavailable (private mode); nothing tenant-scoped is kept there then.
  }
  window.location.replace(reason ? signInPath(reason, window.location) : "/signin");
}

export type SessionTimes = { idle_expires_at?: string | null; expires_at?: string | null };
export type Deadlines = {
  /** When the session ends if nothing happens (the earlier of the idle and the absolute limit). */
  endsAt: number;
  /** The absolute limit: no activity extends the session past it (sliding renewal may move it later). */
  absoluteAt: number;
  /** How long activity keeps the session alive: each request to the server restarts this window. */
  idleWindowMs: number;
};

const parse = (value: string | null | undefined) => {
  const time = value ? Date.parse(value) : Number.NaN;
  return Number.isNaN(time) ? null : time;
};

/**
 * When this session ends, from the session answer (`idle_expires_at`, `expires_at`). Without those fields (an older
 * server) the configured 30 minutes from now are assumed, and no absolute limit is known.
 */
export function sessionDeadlines(session: SessionTimes | null, now: number, fallbackMs = IDLE_SIGN_OUT_MS): Deadlines {
  const absolute = parse(session?.expires_at) ?? Number.POSITIVE_INFINITY;
  const idle = parse(session?.idle_expires_at);
  const idleAt = idle !== null && idle > now ? idle : now + fallbackMs;
  // The idle window is measured right after the server saw this request, so it is the full window.
  const idleWindowMs = idle !== null && idle > now ? Math.max(idle - now, SESSION_WARNING_MS) : fallbackMs;
  return { endsAt: Math.min(idleAt, absolute), absoluteAt: absolute, idleWindowMs };
}

/** After a request the server counted as activity: the idle window starts again, never past the absolute limit. */
export function afterActivity(deadlines: Deadlines, now: number): Deadlines {
  return { ...deadlines, endsAt: Math.min(now + deadlines.idleWindowMs, deadlines.absoluteAt) };
}

export type SessionStep = "wait" | "renew" | "warn" | "end";

/**
 * What the session watch does now. Close to the end, a person who has been typing or clicking (activity the server
 * cannot see) is kept signed in quietly; someone who has been away is asked first; at the end, they are signed out.
 */
export function sessionStep(now: number, endsAt: number, activeSinceLastRequest: boolean): SessionStep {
  if (now >= endsAt) return "end";
  if (now >= endsAt - SESSION_WARNING_MS) return activeSinceLastRequest ? "renew" : "warn";
  return "wait";
}
