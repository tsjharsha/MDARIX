import { useState } from "react";
import { Check, ClipboardList, X } from "lucide-react";
import { errorText, send, useResource } from "../../customer-admin/shared";

export type CitationOption = { code: string; label: string; reference: string; chapter: string };
type Focus = { citations: string[]; options: CitationOption[] };

export const FOCUS_PATH = "/api/v1/trial/focus";
const SKIPPED_KEY = "mdarix.trial.focus-skipped";

function skipped(): boolean {
  try {
    return window.localStorage.getItem(SKIPPED_KEY) === "1";
  } catch {
    return false;
  }
}

/** "Your focus: CAPA effectiveness, risk file": the chosen themes in a few words (exported for its test). */
export function focusText(chosen: readonly string[], options: readonly CitationOption[]): string {
  return options
    .filter((option) => chosen.includes(option.code))
    .map((option) => option.label)
    .join("; ");
}

/**
 * "What were you cited for?": the organization ticks the themes of its warning letter, form 483 or notified body
 * findings (backend/app/trial/citations.py); the chapters that answer them are marked and come first, and the MDARIX
 * team prepares the one-to-one demo around them. Once chosen it folds into one line; it can be skipped.
 */
export function CitedFor({ onSaved }: { onSaved: () => void }) {
  const focus = useResource<Focus>(FOCUS_PATH);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [hidden, setHidden] = useState(skipped);
  const data = focus.data;
  if (!data) return null;
  const chosen = data.citations;
  const open = editing || (!chosen.length && !hidden);
  if (!open && !chosen.length) return null;
  const selection = draft ?? chosen;
  const toggle = (code: string) =>
    setDraft(selection.includes(code) ? selection.filter((item) => item !== code) : [...selection, code]);
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await send(FOCUS_PATH, "PUT", { citations: selection });
      setEditing(false);
      setDraft(null);
      focus.reload();
      onSaved();
    } catch (failure) {
      setError(errorText(failure, "Your choice was not saved. Please try again."));
    } finally {
      setBusy(false);
    }
  };
  if (!open)
    return (
      <p className="uw-cited-line">
        <ClipboardList size={16} aria-hidden="true" /> <b>Your focus:</b> {focusText(chosen, data.options)}.{" "}
        <button type="button" className="ac-link" onClick={() => setEditing(true)}>
          Change
        </button>
      </p>
    );
  return (
    <section className="ac-panel uw-cited" aria-labelledby="uw-cited-title">
      <header className="ac-panel-head">
        <div>
          <p className="ac-eyebrow">Start where it hurts</p>
          <h2 id="uw-cited-title">What were you cited for?</h2>
        </div>
      </header>
      <p className="uw-trial-note">
        Tick what FDA, a notified body or your own audit found. The story starts with those chapters, and the MDARIX
        team prepares your one-to-one demo around them. Only your trial team and the MDARIX team see it.
      </p>
      <ul className="uw-cited-options">
        {data.options.map((option) => (
          <li key={option.code}>
            <label className={selection.includes(option.code) ? "is-on" : ""}>
              <input type="checkbox" checked={selection.includes(option.code)} onChange={() => toggle(option.code)} />
              <span>
                {option.label}
                <small>{option.reference}</small>
              </span>
            </label>
          </li>
        ))}
      </ul>
      {error && (
        <p className="uw-flag-critical" role="alert">
          {error}
        </p>
      )}
      <div className="ca-action-row">
        <button type="button" className="ac-primary" onClick={() => void save()} disabled={busy || !selection.length}>
          <Check size={15} aria-hidden="true" /> {busy ? "Saving…" : "Start the story there"}
        </button>
        <button
          type="button"
          className="ac-link"
          onClick={() => {
            setEditing(false);
            setDraft(null);
            if (!chosen.length) {
              try {
                window.localStorage.setItem(SKIPPED_KEY, "1");
              } catch {
                // Without storage the question simply returns on the next visit.
              }
              setHidden(true);
            }
          }}
        >
          <X size={14} aria-hidden="true" /> {chosen.length ? "Cancel" : "Not now"}
        </button>
      </div>
    </section>
  );
}
