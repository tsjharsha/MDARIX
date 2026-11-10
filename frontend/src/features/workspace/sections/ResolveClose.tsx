import { useState } from "react";
import { CheckCircle2, RotateCcw } from "lucide-react";
import { errorText, formatDate, send } from "../../customer-admin/shared";
import { useCan, useWorkspace } from "../workspaceContext";
import { DecideAndSign } from "./common";
import { InlineError } from "./boardParts";
import { TrainingPanel } from "./MarketAssessment";
import { problemCodeText, useImdrfLinks } from "./ProblemCode";
import { formatDay } from "../../../app/dates";
import {
  isNewCode,
  REOPEN_MIN,
  reportabilityLine,
  resolveBody,
  resolveCovers,
  resolveFormOf,
  resolvePath,
  resolveProblem,
  type ResolveForm,
  type ResolveScreen,
} from "../resolveClose";

/** A classification choice with its source value and the "other" words (shared with the decision tree). */
export function ClassificationField({
  label,
  options,
  value,
  text,
  source,
  onChange,
}: {
  label: string;
  options: Record<string, string>;
  value: string;
  text: string;
  source?: string | null;
  onChange: (value: string, text: string) => void;
}) {
  const shownSource = source && source !== options[value] ? source : null;
  return (
    <div className="ca-field">
      <label>
        {label}
        <select value={value} onChange={(event) => onChange(event.target.value, text)}>
          {Object.entries(options).map(([code, name]) => (
            <option key={code} value={code}>
              {name}
            </option>
          ))}
        </select>
      </label>
      {shownSource && <span className="uw-cr-meta">Source value: “{shownSource}” (not on the list)</span>}
      {value === "OTHER" && (
        <input aria-label={`${label}: other`} value={text} onChange={(event) => onChange(value, event.target.value)} />
      )}
    </div>
  );
}

function Choice({
  label,
  options,
  value,
  onChange,
  empty = "Choose…",
}: {
  label: string;
  options: Record<string, string>;
  value: string;
  onChange: (value: string) => void;
  empty?: string;
}) {
  return (
    <label className="ca-field">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">{empty}</option>
        {Object.entries(options).map(([code, name]) => (
          <option key={code} value={code}>
            {name}
          </option>
        ))}
      </select>
    </label>
  );
}

function Text({
  label,
  value,
  onChange,
  long = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  long?: boolean;
}) {
  return (
    <label className="ca-field">
      {label}
      {long ? (
        <textarea rows={2} value={value} onChange={(event) => onChange(event.target.value)} />
      ) : (
        <input value={value} onChange={(event) => onChange(event.target.value)} />
      )}
    </label>
  );
}

/**
 * "Resolve and close" (B7, spec 1.2): what happened, the problem, troubleshooting and resolution, why no investigation,
 * the cause, the classification, customer told and the reportability line, then one signature. In MDARIX Complete it
 * closes the complaint; in Connect it marks it ready to close in the QMS. Flat by design (G-2): the drawer's plain
 * sections, no decoration. A closed complaint shows when it closed and the Reopen form.
 */
export function ResolveClosePanel({
  screen,
  onDone,
  onTree,
  onTrained,
}: {
  screen: ResolveScreen;
  onDone: () => void;
  /** Open the full decision tree instead (escalate by choice, a known issue). */
  onTree: () => void;
  onTrained: () => void;
}) {
  const disposition = screen.disposition;
  const complaint = disposition.complaint;
  const triage = useCan("signal.triage");
  const opener = useCan("investigation.create");
  const quality = useCan("quality.review");
  const canSign = triage || opener || quality;
  const { notify } = useWorkspace();
  const [form, setForm] = useState<ResolveForm>(() => resolveFormOf(screen));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const links = useImdrfLinks([form.problemCode.trim().toUpperCase()]);
  const set = (patch: Partial<ResolveForm>) => setForm((current) => ({ ...current, ...patch }));
  const missing = disposition.training_required ? disposition.training.filter((item) => item.state !== "CURRENT") : [];
  const problem = resolveProblem(screen, form, !missing.length);
  const close = screen.offer.full;
  const fresh = isNewCode(screen, form.problemCode);
  const corrections = disposition.corrections;

  if (screen.closed) return <ReopenPanel screen={screen} onDone={onDone} />;

  const sign = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await send(resolvePath(complaint.id), "POST", resolveBody(screen, form, close));
      notify(
        close
          ? screen.mode === "COMPLETE"
            ? `${complaint.ref}: resolved and closed.`
            : `${complaint.ref}: resolved, ready to close in your QMS.`
          : `${complaint.ref}: resolved. It closes once the open items are done.`,
      );
      onDone();
    } catch (failure) {
      setError(errorText(failure, "Nothing was signed."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="uw-dp uw-rc" onSubmit={sign} aria-label={screen.button}>
      <section className="ca-drawer-section">
        <h3>What happened</h3>
        <p>
          {complaint.product_name ?? "No product"}
          {complaint.version ? ` · ${complaint.version}` : ""}
          {complaint.lot ? ` · lot ${complaint.lot}` : ""}
          {complaint.awareness_date ? ` · aware ${formatDay(complaint.awareness_date)}` : ""}
        </p>
        {complaint.description && <q className="uw-cr-text">{complaint.description}</q>}
        <p className="uw-cr-meta">
          Triage complete · {screen.offer.routine ? "routine path" : "every relevant market signed not reportable"}
        </p>
      </section>

      <section className="ca-drawer-section">
        <h3>Problem</h3>
        {screen.problem_code_read_only ? (
          <p>
            Problem code: {complaint.problem_code ? problemCodeText(complaint.problem_code, links) : "none"}
            {!complaint.problem_code && (
              <span className="uw-hint"> Your QMS sends none: recurrence checks cannot run.</span>
            )}
          </p>
        ) : (
          <label className="ca-field">
            Problem code
            <input
              list="rc-problem-codes"
              value={form.problemCode}
              onChange={(event) => set({ problemCode: event.target.value })}
            />
            <datalist id="rc-problem-codes">
              {screen.problem_codes.map((code) => (
                <option key={code} value={code}>
                  {problemCodeText(code, links)}
                </option>
              ))}
            </datalist>
            {form.problemCode.trim() && links[form.problemCode.trim().toUpperCase()] && (
              <span className="uw-cr-meta">{problemCodeText(form.problemCode.trim().toUpperCase(), links)}</span>
            )}
          </label>
        )}
        {fresh && (
          <div className="uw-hint" role="note">
            <p>
              This code was never recorded on {complaint.product_name ?? "this product"}: a new failure mode escalates
              to an investigation, unless it is known behaviour documented in your instructions for use or risk file.
            </p>
            <Text
              label="Known behaviour, documented in (reference)"
              value={form.knownBehaviour}
              onChange={(value) => set({ knownBehaviour: value })}
            />
            <button type="button" className="ac-link" onClick={onTree}>
              Escalate instead
            </button>
          </div>
        )}
        <Text
          label="Problem description (optional, masked like the Case words)"
          value={form.problemDescription}
          onChange={(value) => set({ problemDescription: value })}
          long
        />
      </section>

      <section className="ca-drawer-section">
        <h3>Troubleshooting and resolution</h3>
        <Text
          label="Troubleshooting (from what was tried on the call)"
          value={form.troubleshooting}
          onChange={(value) => set({ troubleshooting: value })}
          long
        />
        <div className="ca-form-grid">
          <Choice
            label="Correction"
            options={corrections}
            value={form.correctionType}
            onChange={(value) =>
              set({ correctionType: value, ...(value === "NO_FAULT_FOUND" ? { attribution: "UNDETERMINED" } : {}) })
            }
          />
          <Choice
            label="Device returned"
            options={screen.device_returned}
            value={form.deviceReturned}
            onChange={(value) => set({ deviceReturned: value })}
            empty="Not recorded"
          />
        </div>
        <Text label="Correction" value={form.correction} onChange={(value) => set({ correction: value })} />
        <Text label="Result" value={form.result} onChange={(value) => set({ result: value })} />
        <Text
          label={
            screen.ticket_corrections.includes(form.correctionType)
              ? "Service ticket (service work was done)"
              : "Service ticket (optional)"
          }
          value={form.serviceTicket}
          onChange={(value) => set({ serviceTicket: value })}
        />
      </section>

      <section className="ca-drawer-section">
        <h3>Why no investigation ({disposition.no_investigation_clause})</h3>
        <Choice
          label="Reason"
          options={screen.reasons}
          value={form.reason}
          onChange={(value) => set({ reason: value })}
        />
        {form.reason === "OTHER" && (
          <Text label="Your reason" value={form.rationale} onChange={(value) => set({ rationale: value })} long />
        )}
        <ul className="uw-dp-basis" aria-label="Facts checked">
          <li>
            Similar complaints on this product and problem code in the last 12 months: {screen.similar_last_12_months}
          </li>
          <li>
            Escalation triggers met:{" "}
            {disposition.trigger_codes.length || fresh ? "a new failure mode, answered above" : "none"}
          </li>
        </ul>
      </section>

      <section className="ca-drawer-section">
        <h3>Cause and classification</h3>
        <div className="ca-form-grid">
          <Choice
            label="Cause"
            options={Object.fromEntries(disposition.attributions.map((item) => [item.code, item.label]))}
            value={form.attribution}
            onChange={(value) => set({ attribution: value })}
          />
          {form.attribution === "UNDETERMINED" && (
            <Text
              label="Why it cannot be attributed"
              value={form.attributionReason}
              onChange={(value) => set({ attributionReason: value })}
            />
          )}
          <ClassificationField
            label="Where it was used"
            options={disposition.use_environments}
            value={form.useEnvironment}
            text={form.useEnvironmentText}
            source={disposition.classification.source_values.use_environment}
            onChange={(value, text) => set({ useEnvironment: value, useEnvironmentText: text })}
          />
          <ClassificationField
            label="Who used it"
            options={disposition.user_types}
            value={form.userType}
            text={form.userTypeText}
            source={disposition.classification.source_values.user_type}
            onChange={(value, text) => set({ userType: value, userTypeText: text })}
          />
        </div>
      </section>

      <section className="ca-drawer-section">
        <h3>Customer told</h3>
        <p className="uw-cr-meta">
          {screen.reporters_with_contact
            ? `A reply is logged for each reporter with a contact (${screen.reporters_with_contact}). MDARIX sends nothing itself.`
            : screen.no_contact_reason
              ? `No contact held: ${screen.no_contact_reason}.`
              : "MDARIX sends nothing itself: record how you told the customer."}
        </p>
        <div className="ca-form-grid">
          <Choice
            label="How"
            options={screen.told_how}
            value={form.toldHow}
            onChange={(value) => set({ toldHow: value })}
          />
          {form.toldHow !== "NOT_POSSIBLE" && (
            <label className="ca-field">
              When (now if left empty)
              <input
                type="datetime-local"
                value={form.toldAt}
                onChange={(event) => set({ toldAt: event.target.value })}
              />
            </label>
          )}
        </div>
        {form.toldHow === "NOT_POSSIBLE" ? (
          <Text
            label="Why not (anonymous, unreachable)"
            value={form.toldReason}
            onChange={(value) => set({ toldReason: value })}
          />
        ) : (
          <div className="ca-form-grid">
            <Text label="Note" value={form.toldNote} onChange={(value) => set({ toldNote: value })} />
            <Text label="QMS letter ID" value={form.qmsLetterId} onChange={(value) => set({ qmsLetterId: value })} />
          </div>
        )}
      </section>

      <section className="ca-drawer-section">
        <h3>Reportability</h3>
        <p>{reportabilityLine(screen)}</p>
      </section>

      {!close && screen.offer.blocking.length > 0 && (
        <p className="uw-hint" role="note">
          Resolve only: closing waits for {screen.offer.blocking.join("; ")}. Signing over an open item is done on the
          normal Ready to close step.
        </p>
      )}

      {missing.length > 0 && (
        <TrainingPanel
          documents={missing}
          colleagues={disposition.trained_colleagues}
          required
          onDone={onTrained}
          note="Read the disposition rules and the coding criteria, then confirm each."
        />
      )}

      {canSign ? (
        <section className="ca-drawer-section uw-dp-sign">
          <h3>
            <CheckCircle2 size={15} aria-hidden="true" /> One signature covers
          </h3>
          <ul>
            {resolveCovers(screen, close).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          {screen.owner.id && !screen.owner.is_me && (
            <label className="ca-check">
              <input
                type="checkbox"
                checked={form.takeOver}
                onChange={(event) => set({ takeOver: event.target.checked })}
              />{" "}
              Take over as owner from {screen.owner.name ?? "a colleague"}
            </label>
          )}
          {disposition.current && (
            <Text
              label="Why the disposition changes"
              value={form.changeReason}
              onChange={(value) => set({ changeReason: value })}
            />
          )}
          <div className="ca-form-grid">
            <DecideAndSign />
            <label className="ca-field">
              Your password
              <input
                type="password"
                autoComplete="current-password"
                value={form.password}
                onChange={(event) => set({ password: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Authenticator code
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                value={form.code}
                onChange={(event) => set({ code: event.target.value })}
              />
            </label>
          </div>
          {problem && <p className="uw-hint">{problem}</p>}
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy || !!problem}>
              {busy ? "Signing…" : close ? screen.button : "Resolve"}
            </button>
            <button type="button" className="ac-link" onClick={onTree}>
              Use the full decision tree (escalate by choice)
            </button>
          </div>
        </section>
      ) : (
        <p className="uw-hint">Resolving needs signal triage, investigation opening or quality review.</p>
      )}
      <InlineError text={error} />
    </form>
  );
}

/** A complaint MDARIX closed: when, and Reopen with a reason (no signature: reopening is the safe direction). */
export function ReopenPanel({ screen, onDone }: { screen: ResolveScreen; onDone: () => void }) {
  const { notify } = useWorkspace();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const complaint = screen.disposition.complaint;
  const short = reason.trim().replace(/\s+/g, " ").length < REOPEN_MIN;
  const reopen = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await send(resolvePath(complaint.id, "/reopen"), "POST", { reason });
      notify(`${complaint.ref}: reopened.`);
      onDone();
    } catch (failure) {
      setError(errorText(failure, "The complaint was not reopened."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="uw-dp uw-rc" onSubmit={reopen} aria-label="Reopen">
      <section className="ca-drawer-section">
        <h3>
          <CheckCircle2 size={15} aria-hidden="true" /> Closed in MDARIX
        </h3>
        <p>
          {complaint.ref} was resolved and closed{screen.closed_at ? ` on ${formatDate(screen.closed_at)}` : ""}. New
          harm reopens it by itself; reopen it here when new information calls for it.
        </p>
        <Text label={`Why it reopens (at least ${REOPEN_MIN} characters)`} value={reason} onChange={setReason} long />
        <div className="ca-action-row">
          <button type="submit" className="ac-secondary" disabled={busy || short}>
            <RotateCcw size={15} aria-hidden="true" /> {busy ? "Reopening…" : "Reopen"}
          </button>
        </div>
      </section>
      <InlineError text={error} />
    </form>
  );
}
