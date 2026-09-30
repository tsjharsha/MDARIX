import { useEffect } from "react";
import { requestJson } from "../../app/apiClient";

// Signs a user out after this much inactivity, in addition to the server's 60-minute session expiry.
export const IDLE_SIGN_OUT_MS = 30 * 60 * 1000;

/** End the server session, drop any tenant-scoped browser state, and return to sign-in. */
export async function signOut(reason?: string) {
  await requestJson("/api/v1/auth/signout", { method: "POST", retries: 0 }).catch(() => undefined);
  try {
    sessionStorage.clear();
  } catch {
    // Storage can be unavailable (private mode); nothing tenant-scoped is kept there then.
  }
  window.location.replace(reason ? `/signin?reason=${reason}` : "/signin");
}

export function useIdleSignOut(timeoutMs = IDLE_SIGN_OUT_MS) {
  useEffect(() => {
    let timer = window.setTimeout(() => void signOut("idle"), timeoutMs);
    const reset = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void signOut("idle"), timeoutMs);
    };
    const events = ["pointerdown", "keydown", "scroll"] as const;
    events.forEach((name) => window.addEventListener(name, reset, { passive: true }));
    return () => {
      window.clearTimeout(timer);
      events.forEach((name) => window.removeEventListener(name, reset));
    };
  }, [timeoutMs]);
}
