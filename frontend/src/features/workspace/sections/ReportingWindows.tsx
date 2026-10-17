import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Empty, Panel } from "../../admin/console/charts";
import { errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { useCan, useWorkspace } from "../workspaceContext";
import {
  BLANK_WINDOW,
  REPORT_LIMITS,
  TRIGGERS,
  TRIGGER_LABELS,
  windowForm,
  windowLength,
  windowsBody,
  windowsChanged,
  windowsProblem,
  type ReportabilitySettings,
  type WindowForm,
} from "../reportability";
import { countOf } from "./common";
import { InlineError } from "./boardParts";
import { BasisChips, BasisNote } from "../../shared/Basis";

/**
 * Complaints › Reporting windows: the windows the reportability watch counts against, entered from the organization's
 * own procedure (FDA, EU or any other authority). Changed by a person with regulatory approval, with a reason;
 * versioned and audited. A window started from a template keeps the template's regulatory basis, shown as chips.
 */
export function ReportingWindows() {
  const settings = useResource<ReportabilitySettings>("/api/v1/complaints/reportability-settings");
  return (
    <Panel eyebrow="Complaints" title="Reporting windows" source={settings}>
      {settings.data && <WindowsBody key={settings.data.version} settings={settings.data} onSaved={settings.reload} />}
    </Panel>
  );
}

/** The windows and, for a person with regulatory approval, the form that changes them (exported for its unit test). */
export function WindowsBody({ settings, onSaved }: { settings: ReportabilitySettings; onSaved: () => void }) {
  const { notify } = useWorkspace();
  const canEdit = useCan("regulatory.approve");
  const [forms, setForms] = useState<WindowForm[]>(() => settings.windows.map(windowForm));
  const [lookback, setLookback] = useState(String(settings.lookback_days));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const changed = windowsChanged(settings, forms, lookback);
  const problem = windowsProblem(forms, lookback, reason);
  const update = (key: number, patch: Partial<WindowForm>) =>
    setForms((current) => current.map((form) => (form.key === key ? { ...form, ...patch } : form)));
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!changed || problem) return;
    setBusy(true);
    setError("");
    try {
      await send("/api/v1/complaints/reportability-settings", "PUT", windowsBody(forms, lookback, reason));
      notify("The reporting windows were saved.");
      onSaved();
    } catch (failure) {
      setError(errorText(failure, "The reporting windows were not saved."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <p className="ac-muted">
        Each window starts a clock when a complaint from one of its markets reports what it names, counted from the day
        your organization became aware. Enter them from your complaint handling procedure; MDARIX keeps the clock and
        your reviewer decides reportability.
      </p>
      <dl className="ca-facts">
        <div>
          <dt>Windows</dt>
          <dd>{settings.windows.length ? countOf(settings.windows.length, "window") : "None yet"}</dd>
        </div>
        <div>
          <dt>Looks back</dt>
          <dd>{countOf(settings.lookback_days, "day")}</dd>
        </div>
        <div>
          <dt>Version</dt>
          <dd>{settings.version || "Never set"}</dd>
        </div>
        <div>
          <dt>Changed</dt>
          <dd>
            {settings.updated_at ? formatDate(settings.updated_at) : "—"}
            {settings.updated_by_name ? ` · ${settings.updated_by_name}` : ""}
          </dd>
        </div>
      </dl>
      {!canEdit &&
        (settings.windows.length ? (
          <ul className="uw-rw-windows">
            {settings.windows.map((window) => (
              <li key={window.name}>
                <strong>{window.name}</strong>
                <span>
                  {windowLength(window)} · starts on{" "}
                  {window.triggers.map((trigger) => TRIGGER_LABELS[trigger].toLowerCase()).join(", ")} ·{" "}
                  {window.markets.length ? countOf(window.markets.length, "market") : "every market"}
                </span>
                {window.note && <small>{window.note}</small>}
                <BasisChips ids={window.basis} />
              </li>
            ))}
          </ul>
        ) : (
          <Empty
            title="No reporting windows yet"
            detail="A person with regulatory approval enters them from your procedure."
          />
        ))}
      {canEdit && (
        <form className="ca-form" onSubmit={submit}>
          {forms.map((form, index) => (
            <fieldset className="ca-drawer-section uw-rw-window" key={form.key}>
              <legend>Window {index + 1}</legend>
              {form.basis.length > 0 && (
                <p className="ac-muted">
                  Basis: <BasisChips ids={form.basis} />
                </p>
              )}
              <div className="ca-form-grid">
                <label className="ca-field">
                  Name
                  <input
                    value={form.name}
                    maxLength={REPORT_LIMITS.nameMax}
                    onChange={(event) => update(form.key, { name: event.target.value })}
                  />
                </label>
                <label className="ca-field">
                  Days
                  <input
                    type="number"
                    inputMode="numeric"
                    min={REPORT_LIMITS.days[0]}
                    max={REPORT_LIMITS.days[1]}
                    value={form.days}
                    onChange={(event) => update(form.key, { days: event.target.value })}
                  />
                </label>
                <label className="ca-field">
                  Counted in
                  <select
                    value={form.dayBasis}
                    onChange={(event) => update(form.key, { dayBasis: event.target.value as WindowForm["dayBasis"] })}
                  >
                    <option value="CALENDAR">Calendar days</option>
                    <option value="WORK">Work days (Monday to Friday)</option>
                  </select>
                </label>
              </div>
              <fieldset className="uw-rw-triggers">
                <legend>The clock starts when a complaint reports</legend>
                {TRIGGERS.map((trigger) => (
                  <label className="ca-check" key={trigger}>
                    <input
                      type="checkbox"
                      checked={form.triggers.includes(trigger)}
                      onChange={(event) =>
                        update(form.key, {
                          triggers: event.target.checked
                            ? [...form.triggers, trigger]
                            : form.triggers.filter((item) => item !== trigger),
                        })
                      }
                    />
                    {TRIGGER_LABELS[trigger]}
                  </label>
                ))}
              </fieldset>
              <label className="ca-field">
                Markets (countries as your complaints record them, comma separated; empty for every market)
                <textarea
                  rows={2}
                  value={form.markets}
                  onChange={(event) => update(form.key, { markets: event.target.value })}
                />
              </label>
              <label className="ca-field">
                Note for the reviewer
                <input
                  value={form.note}
                  maxLength={REPORT_LIMITS.noteMax}
                  onChange={(event) => update(form.key, { note: event.target.value })}
                />
              </label>
              <div className="ca-action-row">
                <button
                  type="button"
                  className="ac-link"
                  onClick={() => setForms((current) => current.filter((item) => item.key !== form.key))}
                >
                  <Trash2 size={14} aria-hidden="true" /> Remove this window
                </button>
              </div>
            </fieldset>
          ))}
          <section className="ca-drawer-section">
            <h3>Add a window</h3>
            <p className="ac-muted">
              Templates are a starting point: check each against your procedure before saving. Windows that rest on a
              judgment are left to your reviewer and are named in each template&apos;s note.
            </p>
            <div className="ca-action-row uw-rw-templates">
              {settings.templates
                .filter((template) => !forms.some((form) => form.name.trim() === template.name))
                .map((template) => (
                  <button
                    type="button"
                    key={template.name}
                    className="ac-secondary"
                    onClick={() => setForms((current) => [...current, windowForm(template)])}
                  >
                    <Plus size={14} aria-hidden="true" /> {template.name} <BasisChips ids={template.basis} />
                  </button>
                ))}
              <button
                type="button"
                className="ac-secondary"
                onClick={() => setForms((current) => [...current, windowForm(BLANK_WINDOW)])}
              >
                <Plus size={14} aria-hidden="true" /> A blank window
              </button>
            </div>
          </section>
          <div className="ca-form-grid">
            <label className="ca-field">
              Look back (days)
              <input
                type="number"
                inputMode="numeric"
                min={REPORT_LIMITS.lookback[0]}
                max={REPORT_LIMITS.lookback[1]}
                value={lookback}
                onChange={(event) => setLookback(event.target.value)}
              />
            </label>
          </div>
          <label className="ca-field">
            Reason for the change
            <textarea
              rows={2}
              value={reason}
              placeholder="e.g. Procedure QP-08 revision 4, section 6"
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          {changed && problem && <p className="uw-hint">{problem}</p>}
          <InlineError text={error} />
          <p className="ac-muted">A change makes a new version of the windows, recorded in the audit trail.</p>
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-secondary"
              disabled={busy || (!changed && !reason)}
              onClick={() => {
                setForms(settings.windows.map(windowForm));
                setLookback(String(settings.lookback_days));
                setReason("");
              }}
            >
              Undo changes
            </button>
            <button type="submit" className="ac-primary" disabled={busy || !changed || !!problem}>
              {busy ? "Saving…" : "Save reporting windows"}
            </button>
          </div>
        </form>
      )}
      {(canEdit ? [...forms, ...settings.templates] : settings.windows).some((window) => window.basis.length > 0) && (
        <BasisNote />
      )}
    </>
  );
}
