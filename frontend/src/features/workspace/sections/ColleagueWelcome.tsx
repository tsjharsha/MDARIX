import { useState } from "react";
import { Hand, X } from "lucide-react";

/** The signed-in person in their trial (GET /api/v1/trial/status `me`, backend/app/trial/team.py person). */
export type TrialPerson = {
  joined_at?: string | null;
  /** The trial owner's name, for a colleague they invited; null for the owner. */
  invited_by?: string | null;
  organization?: string | null;
};

const DISMISSED_KEY = "mdarix.trial.colleague-welcome-seen";
// The greeting is for a colleague's first days only; after that it never comes back, dismissed or not.
const WELCOME_DAYS = 2;

/** "Asha Rao invited you to Orbit Medical Devices' free trial." (UX-26). Null for the trial owner. */
export function welcomeText(me: TrialPerson | null | undefined): string | null {
  const inviter = (me?.invited_by ?? "").trim();
  if (!inviter) return null;
  const organization = (me?.organization ?? "").trim();
  if (!organization) return `${inviter} invited you to this MDARIX free trial.`;
  const owner = /s$/i.test(organization) ? `${organization}'` : `${organization}'s`;
  return `${inviter} invited you to ${owner} free trial.`;
}

/** Whether to greet now: a colleague in their first days who has not closed the greeting (exported for tests). */
export function showWelcome(me: TrialPerson | null | undefined, dismissed: boolean, now = Date.now()): boolean {
  if (dismissed || !welcomeText(me)) return false;
  const joined = me?.joined_at ? Date.parse(me.joined_at) : NaN;
  return !Number.isFinite(joined) || now - joined < WELCOME_DAYS * 24 * 3600 * 1000;
}

function wasDismissed(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

/**
 * A one-time greeting for a colleague the trial owner invited, at the top of their first screens: who invited them
 * and where to begin. Closed for good with "Got it" (UX-26).
 */
export function ColleagueWelcome({
  me,
  onStart,
}: {
  me: TrialPerson | null | undefined;
  /** Opens Getting started (0.10.82, U-21: the greeting named it with no link). */
  onStart?: () => void;
}) {
  const key = `${DISMISSED_KEY}:${me?.organization ?? ""}`;
  const [dismissed, setDismissed] = useState(() => wasDismissed(key));
  if (!showWelcome(me, dismissed)) return null;
  const close = () => {
    try {
      window.localStorage.setItem(key, "1");
    } catch {
      // Without storage the greeting simply ends after the person's first days.
    }
    setDismissed(true);
  };
  return (
    <aside className="uw-feedback-prompt uw-colleague-welcome" aria-label="Welcome">
      <Hand size={22} aria-hidden="true" />
      <div>
        <strong>{welcomeText(me)}</strong>
        <p>
          Welcome to MDARIX. You work on the same records as your colleagues. Your own first piece of work is on Home;
          Getting started follows one sample investigation from the signal to the action, in seven steps.{" "}
          {onStart && (
            <button type="button" className="ac-link" onClick={onStart}>
              Open Getting started
            </button>
          )}
        </p>
      </div>
      <button type="button" className="ac-secondary" onClick={close}>
        <X size={16} aria-hidden="true" /> Got it
      </button>
    </aside>
  );
}
