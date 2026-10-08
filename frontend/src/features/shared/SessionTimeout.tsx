import { useCallback, useEffect, useRef, useState } from "react";
import { Clock } from "lucide-react";
import { isUnreachable, onApiActivity, requestJson } from "../../app/apiClient";
import { DialogBehaviour } from "./DialogBehaviour";
import {
  ACTIVITY_KEY,
  afterActivity,
  sessionDeadlines,
  sessionStep,
  signOut,
  type Deadlines,
  type SessionTimes,
} from "./session";

const LOCAL_EVENTS = ["pointerdown", "keydown", "scroll"] as const;
// A quiet renewal is tried at most this often, so an absolute limit that cannot move is not asked about again and again.
const RENEW_RETRY_MS = 60_000;

const broadcast = (time: number) => {
  try {
    localStorage.setItem(ACTIVITY_KEY, String(time));
  } catch {
    // Without storage other tabs simply do not hear about this one; each still keeps its own session watch.
  }
};

export type IdleSignOut = {
  /** Shown two minutes before the session ends; null otherwise. */
  warning: { secondsLeft: number; absolute: boolean } | null;
  problem: string;
  busy: boolean;
  /** "Stay signed in": asks the server, which counts as activity. */
  stay: () => Promise<void>;
};

/**
 * The idle sign-out every signed-in shell runs (one per page): watches the server session, warns two minutes before
 * it ends, keeps an active person signed in, and signs out at the end. Requests to the server restart the idle
 * window; so do requests in another tab of the same browser. Render the result with <SessionTimeoutWarning>.
 */
export function useIdleSignOut(): IdleSignOut {
  const deadlines = useRef<Deadlines | null>(null);
  const activeSinceRequest = useRef(false);
  const lastRenew = useRef(0);
  const [warning, setWarning] = useState<{ secondsLeft: number; absolute: boolean } | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const session = await requestJson<SessionTimes>("/api/v1/auth/session", { retries: 0, timeoutMs: 10000 });
    deadlines.current = sessionDeadlines(session, Date.now());
    activeSinceRequest.current = false;
  }, []);

  useEffect(() => {
    void refresh().catch(() => {
      // Unknown end time (the server is unreachable): assume the configured window from now; never sign out for it.
      deadlines.current = sessionDeadlines(null, Date.now());
    });
    const onRequest = () => {
      const now = Date.now();
      if (deadlines.current) deadlines.current = afterActivity(deadlines.current, now);
      activeSinceRequest.current = false;
      broadcast(now);
    };
    const onLocal = () => {
      activeSinceRequest.current = true;
    };
    const onOtherTab = (event: StorageEvent) => {
      if (event.key !== ACTIVITY_KEY || !event.newValue || !deadlines.current) return;
      const time = Number(event.newValue);
      if (Number.isFinite(time)) deadlines.current = afterActivity(deadlines.current, Math.min(time, Date.now()));
    };
    const stop = onApiActivity(onRequest);
    LOCAL_EVENTS.forEach((name) => window.addEventListener(name, onLocal, { passive: true }));
    window.addEventListener("storage", onOtherTab);
    const timer = window.setInterval(() => {
      const current = deadlines.current;
      if (!current) return;
      const now = Date.now();
      let step = sessionStep(now, current.endsAt, activeSinceRequest.current);
      if (step === "renew" && now - lastRenew.current < RENEW_RETRY_MS) step = "warn";
      if (step === "end") {
        window.clearInterval(timer);
        void signOut(current.endsAt >= current.absoluteAt ? "expired" : "idle");
      } else if (step === "renew") {
        lastRenew.current = now;
        void refresh().catch(() => undefined);
      } else if (step === "warn")
        setWarning({
          secondsLeft: Math.max(0, Math.ceil((current.endsAt - now) / 1000)),
          absolute: current.endsAt >= current.absoluteAt,
        });
      else setWarning(null);
    }, 1000);
    return () => {
      stop();
      LOCAL_EVENTS.forEach((name) => window.removeEventListener(name, onLocal));
      window.removeEventListener("storage", onOtherTab);
      window.clearInterval(timer);
    };
  }, [refresh]);

  const stay = async () => {
    setBusy(true);
    setProblem("");
    try {
      await refresh();
      lastRenew.current = Date.now();
      setWarning(null);
    } catch (error) {
      // A 401 already sends the person to sign-in; anything else is a connection problem, not a sign-out.
      setProblem(
        isUnreachable(error)
          ? "MDARIX is not reachable, retrying. Your work on this page is kept."
          : "Your session could not be extended.",
      );
    } finally {
      setBusy(false);
    }
  };

  return { warning, problem, busy, stay };
}

/** The idle sign-out for a shell that has no other use for its state. */
export function SessionTimeoutWatch() {
  return <SessionTimeoutWarning session={useIdleSignOut()} />;
}

/** The two-minute warning: "Stay signed in" or "Sign out now". */
export function SessionTimeoutWarning({ session }: { session: IdleSignOut }) {
  const { warning, problem, busy, stay } = session;
  if (!warning) return null;
  const minutes = Math.floor(warning.secondsLeft / 60);
  const seconds = String(warning.secondsLeft % 60).padStart(2, "0");
  return (
    <div className="ac-modal-backdrop session-timeout" role="presentation">
      <DialogBehaviour onClose={() => void stay()} />
      <section
        className="ac-modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="session-timeout-title"
        aria-describedby="session-timeout-body"
      >
        <p className="ac-eyebrow">
          <Clock size={14} aria-hidden="true" /> Session
        </p>
        <h2 id="session-timeout-title">You will be signed out in {`${minutes}:${seconds}`}</h2>
        <p id="session-timeout-body">
          {warning.absolute
            ? "Your session is reaching its time limit. Save your work; if it cannot be extended, sign in again straight away."
            : "There has been no activity for a while. Unsaved changes on this page are lost when you are signed out."}
        </p>
        {problem && (
          <p className="ca-inline-error" role="alert">
            {problem}
          </p>
        )}
        <div className="ac-modal-actions">
          <button type="button" className="ac-secondary" onClick={() => void signOut()}>
            Sign out now
          </button>
          <button type="button" className="ac-primary" onClick={() => void stay()} disabled={busy}>
            {busy ? "Working…" : "Stay signed in"}
          </button>
        </div>
      </section>
    </div>
  );
}
