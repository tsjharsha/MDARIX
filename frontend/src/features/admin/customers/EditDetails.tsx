import { useId, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Drawer, send } from "../../customer-admin/shared";
import {
  REASON_MAX,
  REASON_MIN,
  changeErrorText,
  changedFields,
  formFrom,
  formProblems,
  isVersionConflict,
  reasonReady,
  titleCase,
  type FieldGroup,
  type FormValues,
} from "./model";

/**
 * Edit a customer's or tenant's details in a drawer: the fields in groups, a required reason, and Save once something
 * changed. Only the changed fields are sent, with the version the page loaded, so a change made by someone else in
 * the meantime is refused instead of overwritten.
 */
export function EditDetails<T = unknown>({
  title,
  what,
  record,
  groups,
  url,
  choices = {},
  onClose,
  onSaved,
  onReload,
}: {
  title: string;
  what: "customer" | "tenant";
  record: { [key: string]: any; lock_version?: number | null };
  groups: FieldGroup[];
  /** The PATCH address. */
  url: string;
  /** Fields chosen from a fixed list (value → shown as the option). */
  choices?: { [key: string]: readonly string[] };
  onClose: () => void;
  onSaved: (response: T, changed: string[]) => void;
  /** Load the latest version after a conflict. */
  onReload: () => void;
}) {
  const id = useId();
  const [form, setForm] = useState<FormValues>(() => formFrom(record, groups));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const changes = changedFields(record, form, groups);
  const changed = Object.keys(changes);
  const problems = formProblems(form, groups);
  const canSave = !busy && changed.length > 0 && problems.length === 0 && reasonReady(reason);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    setBusy(true);
    setError("");
    setConflict(false);
    try {
      const response = await send<T>(url, "PATCH", {
        ...changes,
        reason: reason.trim(),
        lock_version: record.lock_version,
      });
      onSaved(response, changed);
    } catch (reason) {
      setError(changeErrorText(reason, what, "The details were not saved."));
      setConflict(isVersionConflict(reason));
      setBusy(false);
    }
  };

  const reasonLength = reason.trim().length;
  return (
    <Drawer title={title} onClose={onClose}>
      <form className="ca-form" onSubmit={save} aria-describedby={`${id}-intro`}>
        <p id={`${id}-intro`} className="ac-muted">
          Change what is out of date. Identifiers stay as they are. The change and its reason are kept in the audit
          trail.
        </p>
        {groups.map((group) => (
          <fieldset key={group.title} className="ca-drawer-section cc-fieldset">
            <legend>{group.title}</legend>
            {group.fields.map((field) => {
              const options = choices[field.key];
              const value = form[field.key] ?? "";
              const label = `${field.label}${field.required ? "" : " (optional)"}`;
              const update = (next: string) => setForm((current) => ({ ...current, [field.key]: next }));
              return (
                <label key={field.key} className="ca-field">
                  {label}
                  {options ? (
                    <select value={value} required={field.required} onChange={(event) => update(event.target.value)}>
                      {!options.includes(value) && (
                        <option value={value}>{value ? titleCase(value) : "Choose…"}</option>
                      )}
                      {options.map((option) => (
                        <option key={option} value={option}>
                          {titleCase(option)}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={field.type ?? "text"}
                      value={value}
                      required={field.required}
                      onChange={(event) => update(event.target.value)}
                    />
                  )}
                </label>
              );
            })}
          </fieldset>
        ))}
        <label className="ca-field">
          Reason for the change
          <textarea
            value={reason}
            rows={3}
            required
            minLength={REASON_MIN}
            maxLength={REASON_MAX}
            onChange={(event) => setReason(event.target.value)}
            placeholder={`At least ${REASON_MIN} characters, e.g. New billing contact from the renewal`}
            aria-describedby={`${id}-reason-help`}
          />
          <small id={`${id}-reason-help`} className="ac-muted">
            {reasonLength < REASON_MIN
              ? `${REASON_MIN - reasonLength} more character${REASON_MIN - reasonLength === 1 ? "" : "s"} needed.`
              : "Kept in the audit trail with the change."}
          </small>
        </label>
        {problems.length > 0 && (
          <ul className="ca-inline-error cc-problems" aria-live="polite">
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        {error && (
          <p className="ca-inline-error" role="alert">
            <AlertTriangle size={15} aria-hidden="true" /> {error}
            {conflict && (
              <>
                {" "}
                <button type="button" className="ac-link" onClick={onReload}>
                  <RefreshCw size={14} aria-hidden="true" /> Reload
                </button>
              </>
            )}
          </p>
        )}
        <p className="ac-muted" aria-live="polite">
          {changed.length
            ? `${changed.length} field${changed.length === 1 ? "" : "s"} changed.`
            : "Nothing changed yet."}
        </p>
        <div className="ac-modal-actions">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={!canSave}>
            {busy ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>
    </Drawer>
  );
}
