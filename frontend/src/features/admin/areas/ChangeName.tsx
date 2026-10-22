import { useId, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { errorText, send } from "../../customer-admin/shared";
import { DialogBehaviour } from "../../shared/DialogBehaviour";

/** The longest name an account can have (auth_users.display_name; backend/app/access/configuration.py). */
export const NAME_MAX = 120;

/** A name as the server stores it: trimmed, inner runs of spaces as one. */
export const cleanName = (value: string) => value.split(/\s+/).filter(Boolean).join(" ");

/** Why a new name cannot be saved yet, or null when it can (the server checks the same rules). */
export function nameProblem(value: string, current: string | null | undefined): string | null {
  const name = cleanName(value);
  if (!name) return "Enter a name.";
  if (name.length > NAME_MAX) return `A name can have at most ${NAME_MAX} characters (this one has ${name.length}).`;
  if (/[\u0000-\u001f\u007f]/.test(name)) return "A name cannot contain control characters.";
  if (name === cleanName(current ?? "")) return "This is the current name.";
  return null;
}

/** Change name is offered for an account of the administrator's own organization (where the change applies). */
export const canChangeName = (account: { tenant_id?: string | null }, myTenantId: string | undefined) =>
  !!myTenantId && account.tenant_id === myTenantId;

/** Save the new name (PATCH of display_name only; the server audits the name before and after). */
export const renameAccount = (id: string, value: string) =>
  send(`/api/v1/admin/control-plane/users/${id}`, "PATCH", { values: { display_name: cleanName(value) } });

/**
 * Change the name an account shows everywhere (lists, assignments, the audit trail's actor), confirmed in one dialog
 * that says the change before it is made. The email address, role and access stay as they are.
 */
export function ChangeNameDialog({
  account,
  onClose,
  onDone,
}: {
  account: { id: string; email: string; display_name?: string | null };
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const id = useId();
  const current = account.display_name || "";
  const [value, setValue] = useState(current);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const problem = nameProblem(value, current);
  const name = cleanName(value);
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      await renameAccount(account.id, name);
      onDone(`Name changed to ${name}.`);
    } catch (reason) {
      setError(errorText(reason, "The name was not changed."));
      setBusy(false);
    }
  };
  return (
    <div className="ac-modal-backdrop" role="presentation">
      <DialogBehaviour onClose={onClose} />
      <form className="ac-modal" role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} onSubmit={save}>
        <p className="ac-eyebrow">Confirm change · recorded in the audit trail</p>
        <h2 id={`${id}-title`}>Change the name of {current || account.email}?</h2>
        <p>
          The new name shows wherever this account appears. The email address ({account.email}), the role and the access
          stay as they are.
        </p>
        <label className="ca-field">
          New name
          <input
            value={value}
            maxLength={NAME_MAX + 20}
            autoComplete="off"
            aria-invalid={!!problem && value !== current}
            aria-describedby={`${id}-hint`}
            onChange={(event) => setValue(event.target.value)}
          />
        </label>
        <p id={`${id}-hint`} className="ac-muted">
          {problem && value !== current ? problem : `1 to ${NAME_MAX} characters.`}
        </p>
        {error && (
          <p className="ca-inline-error" role="alert">
            <AlertTriangle size={15} aria-hidden="true" /> {error}
          </p>
        )}
        <div className="ac-modal-actions">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy || !!problem}>
            {busy ? "Working…" : "Change name"}
          </button>
        </div>
      </form>
    </div>
  );
}
