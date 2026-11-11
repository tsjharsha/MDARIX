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
  ROLE_LABELS,
  ROLE_MARKETS,
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
      {settings.data && <RolesBody settings={settings.data} onSaved={settings.reload} />}
    </Panel>
  );
}

/**
 * B9 (B9-D8): the organization's role in each market (Manufacturer unless set). It picks the rules MDARIX applies to
 * that market's assessments: an importer or user facility in the US has its own rules and section F of Form 3500A.
 * Changed only by a person with regulatory approval, with a reason (audited); signed conclusions keep their rules.
 */
export function RolesBody({ settings, onSaved }: { settings: ReportabilitySettings; onSaved: () => void }) {
  const { notify } = useWorkspace();
  const canEdit = useCan("regulatory.approve");
  const offered = settings.roles_offered ?? {};
  const current = settings.reporting_roles ?? {};
  const [market, setMarket] = useState(Object.keys(offered)[0] ?? "");
  const [role, setRole] = useState(current[market] ?? "MANUFACTURER");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!Object.keys(offered).length) return null;
  const changed = (current[market] ?? "MANUFACTURER") !== role;
  const short = reason.trim().length < 10;
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!changed || short) return;
    setBusy(true);
    setError("");
    try {
      await send("/api/v1/complaints/reportability-roles", "PUT", { market, role, reason: reason.trim() });
      notify(`Your role in ${ROLE_MARKETS[market] ?? market} is now ${ROLE_LABELS[role] ?? role}.`);
      setReason("");
      onSaved();
    } catch (failure) {
      setError(errorText(failure, "The role was not saved."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="ca-drawer-section">
      <h3>Your role in each market</h3>
      <p className="ac-muted">
        Manufacturer unless you set it. An importer or a US user facility reports under its own rules (for the US: 21
        CFR 803.40 and 803.30, starter, for your consultant to confirm). A change applies to drafts at their next save;
        signed conclusions keep the rules they were signed under.
      </p>
      <dl className="ca-facts">
        {Object.keys(offered).map((code) => (
          <div key={code}>
            <dt>{ROLE_MARKETS[code] ?? code}</dt>
            <dd>{ROLE_LABELS[current[code] ?? "MANUFACTURER"]}</dd>
          </div>
        ))}
      </dl>
      {canEdit && (
        <form className="ca-form" onSubmit={submit}>
          <div className="ca-form-grid">
            <label className="ca-field">
              <span>Market</span>
              <select
                value={market}
                onChange={(event) => {
                  setMarket(event.target.value);
                  setRole(current[event.target.value] ?? "MANUFACTURER");
                }}
              >
                {Object.keys(offered).map((code) => (
                  <option key={code} value={code}>
                    {ROLE_MARKETS[code] ?? code}
                  </option>
                ))}
              </select>
            </label>
            <label className="ca-field">
              <span>Role</span>
              <select value={role} onChange={(event) => setRole(event.target.value)}>
                {(offered[market] ?? []).map((code) => (
                  <option key={code} value={code}>
                    {ROLE_LABELS[code] ?? code}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="ca-field">
            <span>Reason (at least 10 characters, kept in the audit trail)</span>
            <input value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} />
          </label>
          {error && <InlineError text={error} />}
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy || !changed || short}>
              Save role
            </button>
          </div>
        </form>
      )}
    </section>
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
      const saved = await send<ReportabilitySettings>(
        "/api/v1/complaints/reportability-settings",
        "PUT",
        windowsBody(forms, lookback, reason),
      );
      notify(
        saved?.longer_than_law?.length
          ? "The reporting windows were saved. A window ends after the law's period: see the warning."
          : "The reporting windows were saved.",
      );
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
      {(settings.longer_than_law ?? []).map((warning) => (
        <p key={`${warning.window}-${warning.market}`} className="ac-message tone-warning" role="status">
          {warning.message} The market assessment and triage use the period that applies to each event.
        </p>
      ))}
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
